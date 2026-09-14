import logging
import time
from datetime import datetime

from arango import ArangoClient

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.models.entities import (
    CaseDocumentNode,
    ClaimTypeNode,
    EntityType,
    EvidenceNode,
    LawNode,
    ProcedureNode,
    SourceAuthority,
    SourceType,
)
from tenant_legal_guidance.models.relationships import RelationshipType
from tenant_legal_guidance.utils.chunking import build_chunk_docs
from tenant_legal_guidance.utils.text import canonicalize_text, sha256

# Vertex collections for the 5 node types
VERTEX_COLLECTIONS = {
    EntityType.CLAIM_TYPE: "claim_types",
    EntityType.EVIDENCE: "evidence_nodes",
    EntityType.PROCEDURE: "procedures",
    EntityType.LAW: "laws",
    EntityType.CASE_DOCUMENT: "case_documents",
}

# Edge collections for the 3 relationship types
EDGE_COLLECTIONS = {
    RelationshipType.REQUIRES_EVIDENCE: "requires_evidence",
    RelationshipType.TYPICALLY_USES: "typically_uses",
    RelationshipType.CITES: "cites",
}

# Infrastructure collections (source, text, quote, provenance)
INFRA_VERTEX_COLLECTIONS = ["sources", "text_blobs", "quotes", "provenance"]


class ArangoDBGraph:
    def __init__(
        self,
        host: str | None = None,
        db_name: str | None = None,
        username: str | None = None,
        password: str | None = None,
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        settings = get_settings()
        self.host = host or settings.arango_host
        self.db_name = db_name or settings.arango_db_name
        self.username = username or settings.arango_username
        self.password = password or settings.arango_password
        self.max_retries = max_retries or settings.arango_max_retries
        self.retry_delay = retry_delay or settings.arango_retry_delay

        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Initializing ArangoDB connection to {self.host}")
        self._init_connection()
        self.logger.info("Initialized ArangoDBGraph")

    # ─── Connection ────────────────────────────────────────────────────────────

    def _init_connection(self):
        for attempt in range(self.max_retries):
            try:
                self.client = ArangoClient(hosts=self.host)
                sys_db = self.client.db("_system", username=self.username, password=self.password)
                if not sys_db.has_database(self.db_name):
                    self.logger.info(f"Creating database: {self.db_name}")
                    sys_db.create_database(
                        name=self.db_name,
                        users=[{
                            "username": self.username,
                            "password": self.password,
                            "active": True,
                            "extra": {"is_superuser": True},
                        }],
                    )
                self.db = self.client.db(self.db_name, username=self.username, password=self.password)
                version = self.db.version()
                self.logger.info(f"Connected to ArangoDB version {version}")
                self._init_collections()
                self._init_indexes()
                self._ensure_search_view()
                return
            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait = self.retry_delay * (attempt + 1)
                    self.logger.warning(f"Connect attempt {attempt+1} failed: {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    self.logger.error(f"Failed to connect after {self.max_retries} attempts: {e}")
                    raise ConnectionError(
                        f"Could not connect to ArangoDB at {self.host}."
                    ) from e

    def _init_collections(self):
        try:
            # Taxonomy vertex collections
            for et, name in VERTEX_COLLECTIONS.items():
                if not self.db.has_collection(name):
                    self.db.create_collection(name)
                    self.logger.info(f"Created vertex collection: {name}")

            # Infrastructure vertex collections
            for name in INFRA_VERTEX_COLLECTIONS:
                if not self.db.has_collection(name):
                    self.db.create_collection(name)
                    self.logger.info(f"Created vertex collection: {name}")

            # Edge collections
            for rt, name in EDGE_COLLECTIONS.items():
                if not self.db.has_collection(name):
                    self.db.create_collection(name, edge=True)
                    self.logger.info(f"Created edge collection: {name}")

            # Tagging edge collections (case_documents → taxonomy nodes)
            for tagging_coll in ("tagged_as", "demonstrates_evidence", "applied_procedure"):
                if not self.db.has_collection(tagging_coll):
                    self.db.create_collection(tagging_coll, edge=True)
                    self.logger.info(f"Created edge collection: {tagging_coll}")

            # Named graph for traversal queries
            graph_name = "legal_knowledge_graph"
            if not self.db.has_graph(graph_name):
                self.db.create_graph(
                    graph_name,
                    edge_definitions=[
                        {
                            "edge_collection": "requires_evidence",
                            "from_vertex_collections": ["claim_types"],
                            "to_vertex_collections": ["evidence_nodes"],
                        },
                        {
                            "edge_collection": "typically_uses",
                            "from_vertex_collections": ["claim_types"],
                            "to_vertex_collections": ["procedures"],
                        },
                        {
                            "edge_collection": "cites",
                            "from_vertex_collections": ["case_documents"],
                            "to_vertex_collections": ["laws"],
                        },
                        {
                            "edge_collection": "tagged_as",
                            "from_vertex_collections": ["case_documents"],
                            "to_vertex_collections": ["claim_types"],
                        },
                        {
                            "edge_collection": "demonstrates_evidence",
                            "from_vertex_collections": ["case_documents"],
                            "to_vertex_collections": ["evidence_nodes"],
                        },
                        {
                            "edge_collection": "applied_procedure",
                            "from_vertex_collections": ["case_documents"],
                            "to_vertex_collections": ["procedures"],
                        },
                    ],
                )
                self.logger.info(f"Created named graph: {graph_name}")
        except Exception as e:
            self.logger.error(f"Error initializing collections: {e}")
            raise

    def _init_indexes(self):
        try:
            # Taxonomy collections: index on status and jurisdiction
            for coll_name in list(VERTEX_COLLECTIONS.values()):
                if not self.db.has_collection(coll_name):
                    continue
                coll = self.db.collection(coll_name)
                for index in [
                    {"type": "persistent", "fields": ["status"], "name": "idx_status"},
                    {"type": "persistent", "fields": ["jurisdiction"], "name": "idx_jurisdiction"},
                ]:
                    try:
                        coll.add_index(index)
                    except Exception:
                        pass

            # Edge collections: index on _from and _to
            for coll_name in EDGE_COLLECTIONS.values():
                if not self.db.has_collection(coll_name):
                    continue
                coll = self.db.collection(coll_name)
                for index in [
                    {"type": "persistent", "fields": ["_from", "_to"], "name": "uniq_from_to",
                     "unique": True, "sparse": False},
                ]:
                    try:
                        coll.add_index(index)
                    except Exception:
                        pass

            # Sources: index on locator
            if self.db.has_collection("sources"):
                try:
                    self.db.collection("sources").add_index(
                        {"type": "persistent", "fields": ["locator"], "name": "idx_locator", "unique": True, "sparse": True}
                    )
                except Exception:
                    pass

            # text_blobs: unique index on sha256
            if self.db.has_collection("text_blobs"):
                try:
                    self.db.collection("text_blobs").add_index(
                        {"type": "persistent", "fields": ["sha256"], "name": "idx_blob_sha", "unique": True}
                    )
                except Exception:
                    pass

            # quotes: index on source_id
            if self.db.has_collection("quotes"):
                for index in [
                    {"type": "persistent", "fields": ["source_id", "start_offset", "end_offset"], "name": "idx_src_span"},
                    {"type": "persistent", "fields": ["quote_sha256"], "name": "idx_quote_sha"},
                ]:
                    try:
                        self.db.collection("quotes").add_index(index)
                    except Exception:
                        pass

            # case_documents: index on claim_types array for tagged lookup
            if self.db.has_collection("case_documents"):
                try:
                    self.db.collection("case_documents").add_index(
                        {"type": "persistent", "fields": ["claim_types[*]"], "name": "idx_claim_types"}
                    )
                except Exception:
                    pass

            self.logger.info("Initialized indexes")
        except Exception as e:
            self.logger.error(f"Error initializing indexes: {e}")
            raise

    def _ensure_search_view(self):
        view_name = "kg_entities_view"
        links: dict[str, dict] = {}
        text_field = {"analyzers": ["text_en"]}
        identity_field = {"analyzers": ["identity"]}

        for coll_name in list(VERTEX_COLLECTIONS.values()):
            if self.db.has_collection(coll_name):
                links[coll_name] = {
                    "includeAllFields": False,
                    "fields": {
                        "name": text_field,
                        "description": text_field,
                        "aliases": text_field,
                        "status": identity_field,
                        "jurisdiction": identity_field,
                        "entity_type": identity_field,
                    },
                }

        try:
            self.db.delete_view(view_name)
        except Exception:
            pass
        try:
            self.db.create_view(view_name, view_type="arangosearch", properties={"links": links})
            self.logger.info(f"Created ArangoSearch view: {view_name}")
        except Exception as e:
            self.logger.warning(f"Failed to create search view: {e}")

    # ─── Collection routing ─────────────────────────────────────────────────────

    def _get_collection_for_entity(self, entity_type: EntityType) -> str:
        return VERTEX_COLLECTIONS[entity_type]

    def _get_collection_for_relationship(self, relationship_type: RelationshipType) -> str:
        return EDGE_COLLECTIONS[relationship_type]

    # ─── Source / text / quote infrastructure ──────────────────────────────────

    def upsert_text_blob(self, text: str) -> str:
        try:
            canon = canonicalize_text(text)
            s = sha256(canon)
            blob_id = f"t:{s}"
            coll = self.db.collection("text_blobs")
            doc = {
                "_key": blob_id,
                "sha256": s,
                "text": canon,
                "length": len(canon),
                "encoding": "utf-8",
                "created_at": datetime.utcnow().isoformat(),
            }
            if not coll.has(blob_id):
                coll.insert(doc)
            return blob_id
        except Exception as e:
            self.logger.error(f"upsert_text_blob failed: {e}")
            return ""

    def upsert_source(
        self,
        locator: str,
        kind: str,
        title: str | None = None,
        jurisdiction: str | None = None,
        sha256: str | None = None,
        source_id: str | None = None,
    ) -> str:
        try:
            from tenant_legal_guidance.utils.text import generate_uuid_from_text

            if not source_id:
                source_id = generate_uuid_from_text(locator)
            coll = self.db.collection("sources")
            doc = {
                "_key": source_id,
                "kind": kind,
                "locator": locator,
                "title": title,
                "jurisdiction": jurisdiction,
                "sha256": sha256,
                "fetched_at": datetime.utcnow().isoformat(),
                "meta": {},
            }
            if coll.has(source_id):
                coll.update(doc)
            else:
                coll.insert(doc)
            return source_id
        except Exception as e:
            self.logger.error(f"upsert_source failed for {locator}: {e}")
            return ""

    def source_exists_by_locator(self, locator: str) -> bool:
        try:
            cursor = self.db.aql.execute(
                "FOR doc IN sources FILTER doc.locator == @locator LIMIT 1 RETURN doc",
                bind_vars={"locator": locator},
            )
            return len(list(cursor)) > 0
        except Exception as e:
            self.logger.debug(f"Error checking source existence: {e}")
            return False

    def get_existing_locators(self) -> set[str]:
        try:
            cursor = self.db.aql.execute("FOR doc IN sources RETURN doc.locator")
            return set(doc for doc in cursor if doc)
        except Exception as e:
            self.logger.warning(f"Error fetching existing locators: {e}")
            return set()

    def get_source_details_by_locators(self, locators: list[str]) -> dict[str, dict]:
        try:
            cursor = self.db.aql.execute(
                "FOR doc IN sources FILTER doc.locator IN @locators "
                "RETURN {locator: doc.locator, fetched_at: doc.fetched_at, "
                "source_id: doc._key, title: doc.title}",
                bind_vars={"locators": locators},
            )
            return {row["locator"]: row for row in cursor if row.get("locator")}
        except Exception as e:
            self.logger.warning(f"Error fetching source details: {e}")
            return {}

    def delete_source_by_locator(self, locator: str) -> bool:
        try:
            cursor = self.db.aql.execute(
                "FOR doc IN sources FILTER doc.locator == @locator REMOVE doc IN sources RETURN OLD",
                bind_vars={"locator": locator},
            )
            return len(list(cursor)) > 0
        except Exception as e:
            self.logger.warning(f"Error deleting source by locator: {e}")
            return False

    def register_source_with_text(
        self,
        locator: str,
        kind: str,
        full_text: str,
        title: str | None = None,
        jurisdiction: str | None = None,
        chunk_size: int = 3500,
    ) -> dict[str, object]:
        """Register source and prepare chunks for Qdrant. Returns chunk docs (not persisted to Arango)."""
        try:
            from tenant_legal_guidance.utils.text import generate_uuid_from_text

            canon = canonicalize_text(full_text)
            content_hash = sha256(canon)
            source_id = generate_uuid_from_text(locator or full_text)
            self.upsert_source(
                locator=locator,
                kind=kind,
                title=title,
                jurisdiction=jurisdiction,
                sha256=content_hash,
                source_id=source_id,
            )
            blob_id = self.upsert_text_blob(canon)
            settings = get_settings()
            target = int(getattr(settings, "chunk_chars_target", chunk_size) or chunk_size)
            overlap = int(getattr(settings, "chunk_overlap_chars", 0) or 0)
            chunks = build_chunk_docs(
                text=canon,
                source=locator,
                title=title,
                target_chars=target,
                overlap_chars=overlap,
            )
            chunk_ids = [f"{source_id}:{idx}" for idx, _ in enumerate(chunks)]
            return {
                "source_id": source_id,
                "blob_id": blob_id,
                "chunk_docs": chunks,
                "chunk_ids": chunk_ids,
                "total_length": len(canon),
                "chunk_size": target,
                "src_sha": content_hash,
            }
        except Exception as e:
            self.logger.error(f"register_source_with_text failed for {locator}: {e}")
            return {
                "source_id": "",
                "blob_id": "",
                "chunk_docs": [],
                "chunk_ids": [],
                "total_length": 0,
                "chunk_size": int(chunk_size),
                "src_sha": "",
            }

    def upsert_quote(
        self,
        source_id: str,
        start_offset: int,
        end_offset: int,
        quote_text: str | None = None,
        chunk_entity_id: str | None = None,
    ) -> str:
        try:
            src_sha = source_id.split(":", 1)[1] if ":" in source_id else ""
            qid = f"q:{src_sha}:{int(start_offset)}:{int(end_offset)}"
            qsha = sha256(canonicalize_text(quote_text or "")) if quote_text is not None else None
            coll = self.db.collection("quotes")
            doc = {
                "_key": qid,
                "source_id": source_id,
                "quote_sha256": qsha,
                "start_offset": int(start_offset),
                "end_offset": int(end_offset),
                "chunk_entity_id": chunk_entity_id,
                "created_at": datetime.utcnow().isoformat(),
            }
            if coll.has(qid):
                coll.update(doc)
            else:
                coll.insert(doc)
            return qid
        except Exception as e:
            self.logger.error(f"upsert_quote failed: {e}")
            return ""

    def attach_provenance(
        self,
        subject_type: str,
        subject_id: str,
        source_id: str,
        quote_id: str | None = None,
        citation: str | None = None,
        chunk_id: str | None = None,
        chunk_index: int | None = None,
    ) -> bool:
        try:
            coll = self.db.collection("provenance")
            base = f"{subject_type}:{subject_id}:{source_id}:{quote_id or ''}:{chunk_id or ''}"
            pid = f"prov:{sha256(base)}"
            doc = {
                "_key": pid,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "source_id": source_id,
                "quote_id": quote_id,
                "citation": citation,
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "added_at": datetime.utcnow().isoformat(),
            }
            if coll.has(pid):
                return False
            coll.insert(doc)
            return True
        except Exception as e:
            self.logger.error(f"attach_provenance failed: {e}")
            return False

    def get_quote_snippet(self, quote_id: str) -> dict[str, object] | None:
        try:
            q = self.db.collection("quotes").get(quote_id)
            if not q:
                return None
            s = self.db.collection("sources").get(q.get("source_id"))
            if not s:
                return None
            blob = self.db.collection("text_blobs").get(f"t:{s.get('sha256', '')}")
            if not blob:
                return None
            text = blob.get("text") or ""
            start = int(q.get("start_offset") or 0)
            end = int(q.get("end_offset") or 0)
            return {"text": text[start:end], "start_offset": start, "end_offset": end}
        except Exception as e:
            self.logger.error(f"get_quote_snippet failed: {e}")
            return None

    # ─── Taxonomy node CRUD ─────────────────────────────────────────────────────

    def upsert_taxonomy_node(
        self,
        node: ClaimTypeNode | EvidenceNode | ProcedureNode | LawNode,
    ) -> bool:
        """Write or update a taxonomy node. Merges chunk_ids and source_ids on update."""
        coll_name = self._get_collection_for_entity(node.entity_type)
        doc = node.model_dump(mode="json")
        doc["_key"] = node.id
        try:
            coll = self.db.collection(coll_name)
            existing = coll.get(node.id)
            if existing:
                doc["chunk_ids"] = list(set(existing.get("chunk_ids", []) + doc.get("chunk_ids", [])))
                doc["source_ids"] = list(set(existing.get("source_ids", []) + doc.get("source_ids", [])))
                coll.update({k: v for k, v in doc.items() if k != "_key"} | {"_key": node.id})
            else:
                coll.insert(doc)
            return True
        except Exception as e:
            self.logger.error(f"upsert_taxonomy_node failed for {node.id}: {e}")
            return False

    def upsert_case_document(self, doc: CaseDocumentNode) -> bool:
        """Write or update a CaseDocumentNode and its cites edges to canonical Laws."""
        doc_dict = doc.model_dump(mode="json")
        doc_dict["_key"] = doc.id
        try:
            coll = self.db.collection("case_documents")
            if coll.has(doc.id):
                coll.update(doc_dict)
            else:
                coll.insert(doc_dict)
            # Write cites edges to referenced law IDs
            for law_id in doc.citations:
                self.add_cites_edge(doc.id, law_id)
            # Materialize tagging arrays as graph edges
            for ct_id in doc.claim_types:
                self.add_tagged_as_edge(doc.id, ct_id)
            for ev_id in doc.evidence_presented:
                self.add_demonstrates_evidence_edge(doc.id, ev_id)
            for pr_id in doc.procedures_used:
                self.add_applied_procedure_edge(doc.id, pr_id)
            return True
        except Exception as e:
            self.logger.error(f"upsert_case_document failed for {doc.id}: {e}")
            return False

    def get_taxonomy_nodes(
        self,
        kind: str,
        jurisdiction: str | None = None,
        include_proposed: bool = True,
    ) -> list[dict]:
        """List taxonomy nodes, optionally filtered by jurisdiction/status."""
        kind_to_coll = {
            "claim_types": "claim_types",
            "evidence": "evidence_nodes",
            "procedures": "procedures",
            "laws": "laws",
        }
        coll_name = kind_to_coll.get(kind)
        if not coll_name:
            raise ValueError(f"Unknown taxonomy kind: {kind}")
        filters = []
        bind_vars: dict = {}
        if jurisdiction:
            filters.append("FILTER doc.jurisdiction == @jurisdiction")
            bind_vars["jurisdiction"] = jurisdiction
        if not include_proposed:
            filters.append("FILTER doc.status == 'canonical'")
        filter_str = "\n".join(filters)
        aql = f"FOR doc IN {coll_name}\n{filter_str}\nRETURN doc"
        try:
            return list(self.db.aql.execute(aql, bind_vars=bind_vars))
        except Exception as e:
            self.logger.error(f"get_taxonomy_nodes failed for {kind}: {e}")
            return []

    def get_taxonomy_snapshot(self) -> dict[str, list[dict]]:
        """Return all canonical taxonomy nodes, grouped by kind. Used by case tagger."""
        return {
            "claim_types": self.get_taxonomy_nodes("claim_types", include_proposed=False),
            "evidence": self.get_taxonomy_nodes("evidence", include_proposed=False),
            "procedures": self.get_taxonomy_nodes("procedures", include_proposed=False),
            "laws": self.get_taxonomy_nodes("laws", include_proposed=False),
        }

    def propose_taxonomy_entry(self, kind: str, entry: dict) -> str | None:
        """Write a proposed taxonomy entry (status=proposed). Idempotent on id."""
        kind_to_coll = {
            "claim_types": "claim_types",
            "evidence": "evidence_nodes",
            "procedures": "procedures",
            "laws": "laws",
        }
        coll_name = kind_to_coll.get(kind)
        if not coll_name or "id" not in entry:
            return None
        doc = {**entry, "status": "proposed", "_key": entry["id"]}
        try:
            self.db.collection(coll_name).insert(doc, overwrite=True, overwrite_mode="update")
            return entry["id"]
        except Exception as e:
            self.logger.error(f"propose_taxonomy_entry failed: {e}")
            return None

    def accept_proposed(
        self,
        node_id: str,
        kind: str,
        action: str,
        target_id: str | None = None,
    ) -> bool:
        """
        Act on a proposed taxonomy entry.
        action: 'promote' | 'merge_as_alias' | 'reject'
        """
        kind_to_coll = {
            "claim_types": "claim_types",
            "evidence": "evidence_nodes",
            "procedures": "procedures",
            "laws": "laws",
        }
        coll_name = kind_to_coll.get(kind)
        if not coll_name:
            return False
        coll = self.db.collection(coll_name)
        try:
            if action == "promote":
                coll.update({"_key": node_id, "status": "canonical"})
            elif action == "merge_as_alias" and target_id:
                target = coll.get(target_id)
                if target:
                    aliases = list(set(target.get("aliases", []) + [node_id]))
                    coll.update({"_key": target_id, "aliases": aliases})
                    coll.delete(node_id, ignore_missing=True)
            elif action == "reject":
                coll.delete(node_id, ignore_missing=True)
            return True
        except Exception as e:
            self.logger.error(f"accept_proposed failed for {node_id}: {e}")
            return False

    def entity_exists(self, entity_id: str) -> bool:
        for coll_name in VERTEX_COLLECTIONS.values():
            try:
                if self.db.collection(coll_name).has(entity_id):
                    return True
            except Exception:
                pass
        return False

    def get_entity(self, entity_id: str) -> dict | None:
        """Look up a node by _key across all taxonomy and case_document collections."""
        for coll_name in VERTEX_COLLECTIONS.values():
            try:
                doc = self.db.collection(coll_name).get(entity_id)
                if doc:
                    return doc
            except Exception:
                pass
        return None

    def delete_entity(self, entity_id: str) -> bool:
        """Delete a node and all its incident edges. Returns True if found and deleted."""
        for coll_name in VERTEX_COLLECTIONS.values():
            try:
                coll = self.db.collection(coll_name)
                if coll.has(entity_id):
                    full_id = f"{coll_name}/{entity_id}"
                    # Remove incident edges
                    for edge_coll_name in EDGE_COLLECTIONS.values():
                        try:
                            self.db.aql.execute(
                                "FOR e IN @@coll FILTER e._from == @id OR e._to == @id REMOVE e IN @@coll",
                                bind_vars={"@coll": edge_coll_name, "id": full_id},
                            )
                        except Exception:
                            pass
                    coll.delete(entity_id)
                    return True
            except Exception:
                pass
        return False

    # ─── Taxonomy edge CRUD ─────────────────────────────────────────────────────

    def add_requires_evidence_edge(
        self, claim_type_id: str, evidence_id: str, critical: bool = True
    ) -> bool:
        _from = f"claim_types/{claim_type_id}"
        _to = f"evidence_nodes/{evidence_id}"
        return self._upsert_edge("requires_evidence", _from, _to, {"critical": critical})

    def add_typically_uses_edge(self, claim_type_id: str, procedure_id: str) -> bool:
        _from = f"claim_types/{claim_type_id}"
        _to = f"procedures/{procedure_id}"
        return self._upsert_edge("typically_uses", _from, _to, {})

    def add_cites_edge(self, case_doc_id: str, law_id: str) -> bool:
        return self._upsert_edge("cites", f"case_documents/{case_doc_id}", f"laws/{law_id}", {})

    def add_tagged_as_edge(self, case_doc_id: str, claim_type_id: str) -> bool:
        return self._upsert_edge("tagged_as", f"case_documents/{case_doc_id}", f"claim_types/{claim_type_id}", {})

    def add_demonstrates_evidence_edge(self, case_doc_id: str, evidence_id: str) -> bool:
        return self._upsert_edge("demonstrates_evidence", f"case_documents/{case_doc_id}", f"evidence_nodes/{evidence_id}", {})

    def add_applied_procedure_edge(self, case_doc_id: str, procedure_id: str) -> bool:
        return self._upsert_edge("applied_procedure", f"case_documents/{case_doc_id}", f"procedures/{procedure_id}", {})

    def _upsert_edge(self, coll_name: str, _from: str, _to: str, extra: dict) -> bool:
        try:
            coll = self.db.collection(coll_name)
            doc = {"_from": _from, "_to": _to, **extra}
            # Unique index on (_from, _to) handles idempotency; ignore duplicate errors
            try:
                coll.insert(doc)
            except Exception as insert_err:
                if "unique" in str(insert_err).lower() or "1210" in str(insert_err):
                    if extra:
                        # Update attributes on existing edge
                        self.db.aql.execute(
                            "FOR e IN @@coll FILTER e._from == @f AND e._to == @t "
                            "UPDATE e WITH @extra IN @@coll",
                            bind_vars={"@coll": coll_name, "f": _from, "t": _to, "extra": extra},
                        )
                else:
                    raise
            return True
        except Exception as e:
            self.logger.error(f"_upsert_edge failed ({coll_name} {_from}->{_to}): {e}")
            return False

    # ─── Taxonomy traversals ────────────────────────────────────────────────────

    def get_required_evidence_for_claim_type(self, claim_type_id: str) -> list[dict]:
        """Graph traversal: ClaimType → requires_evidence → Evidence."""
        try:
            aql = """
            FOR v, e IN 1..1 OUTBOUND @start_id requires_evidence
                RETURN MERGE(v, {critical: e.critical})
            """
            cursor = self.db.aql.execute(
                aql, bind_vars={"start_id": f"claim_types/{claim_type_id}"}
            )
            return list(cursor)
        except Exception as e:
            self.logger.error(f"get_required_evidence_for_claim_type failed for {claim_type_id}: {e}")
            return []

    def get_required_procedures_for_claim_type(self, claim_type_id: str) -> list[dict]:
        """Graph traversal: ClaimType → typically_uses → Procedure."""
        try:
            aql = """
            FOR v IN 1..1 OUTBOUND @start_id typically_uses
                RETURN v
            """
            cursor = self.db.aql.execute(
                aql, bind_vars={"start_id": f"claim_types/{claim_type_id}"}
            )
            return list(cursor)
        except Exception as e:
            self.logger.error(f"get_required_procedures_for_claim_type failed for {claim_type_id}: {e}")
            return []

    def get_laws_for_claim_type(self, claim_type_id: str) -> list[dict]:
        """Return laws cited by cases that are tagged with this claim type, ranked by frequency."""
        try:
            aql = """
            FOR doc IN case_documents
                FILTER @cid IN doc.claim_types
                FOR law IN 1..1 OUTBOUND doc cites
                    COLLECT law_key = law._key, law_name = law.name, law_citation = law.citation,
                            law_description = law.description
                    WITH COUNT INTO n
                    SORT n DESC
                    LIMIT 10
                    RETURN {id: law_key, name: law_name, citation: law_citation,
                            description: law_description, case_count: n}
            """
            cursor = self.db.aql.execute(aql, bind_vars={"cid": claim_type_id})
            return list(cursor)
        except Exception as e:
            self.logger.error(f"get_laws_for_claim_type failed for {claim_type_id}: {e}")
            return []

    def get_cases_tagged_with(
        self,
        claim_type_ids: list[str],
        jurisdiction: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Return case documents tagged with any of the given claim_type_ids, ranked by overlap."""
        bind_vars: dict = {"ids": claim_type_ids, "limit": limit}
        jur_filter = ""
        if jurisdiction:
            jur_filter = "FILTER doc.jurisdiction == @jurisdiction"
            bind_vars["jurisdiction"] = jurisdiction
        aql = f"""
        FOR doc IN case_documents
            {jur_filter}
            FILTER LENGTH(INTERSECTION(doc.claim_types, @ids)) > 0
            SORT LENGTH(INTERSECTION(doc.claim_types, @ids)) DESC
            LIMIT @limit
            RETURN doc
        """
        try:
            return list(self.db.aql.execute(aql, bind_vars=bind_vars))
        except Exception as e:
            self.logger.error(f"get_cases_tagged_with failed: {e}")
            return []

    def get_all_claim_type_nodes(self) -> list[dict]:
        """Return all canonical claim type nodes."""
        return self.get_taxonomy_nodes("claim_types", include_proposed=False)

    def get_taxonomy_by_jurisdiction(
        self, jurisdiction: str, kind: str, include_proposed: bool = True
    ) -> list[dict]:
        return self.get_taxonomy_nodes(kind, jurisdiction=jurisdiction, include_proposed=include_proposed)

    # ─── Text search ────────────────────────────────────────────────────────────

    def search_entities_by_text(
        self,
        query: str,
        entity_types: list[str] | None = None,
        jurisdiction: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Full-text search over taxonomy nodes via ArangoSearch view."""
        kind_map = {
            "claim_type": "claim_types",
            "evidence": "evidence_nodes",
            "procedure": "procedures",
            "law": "laws",
            "case_document": "case_documents",
        }
        if entity_types:
            coll_filter = f"FILTER doc.entity_type IN {entity_types!r}"
        else:
            coll_filter = ""

        jur_filter = ""
        bind_vars: dict = {"query": query, "limit": limit}
        if jurisdiction:
            jur_filter = "FILTER doc.jurisdiction == @jurisdiction"
            bind_vars["jurisdiction"] = jurisdiction

        aql = f"""
        FOR doc IN kg_entities_view
            SEARCH ANALYZER(
                PHRASE(doc.name, @query, "text_en") OR
                PHRASE(doc.description, @query, "text_en") OR
                PHRASE(doc.aliases, @query, "text_en"),
                "text_en"
            )
            {coll_filter}
            {jur_filter}
            SORT BM25(doc) DESC
            LIMIT @limit
            RETURN doc
        """
        try:
            return list(self.db.aql.execute(aql, bind_vars=bind_vars))
        except Exception as e:
            self.logger.error(f"search_entities_by_text failed: {e}")
            return []

    # ─── Stats / admin ──────────────────────────────────────────────────────────

    def get_database_stats(self) -> dict[str, int]:
        try:
            stats = {}
            for info in self.db.collections():
                name = info["name"]
                if name.startswith("_"):
                    continue
                try:
                    stats[name] = self.db.collection(name).count()
                except Exception:
                    stats[name] = -1
            return stats
        except Exception as e:
            self.logger.error(f"Error getting database stats: {e}")
            return {}

    def reset_database(self, confirm: bool = False) -> dict[str, int]:
        if not confirm:
            raise ValueError("reset_database requires confirm=True.")
        try:
            deleted = {}
            for info in self.db.collections():
                name = info["name"]
                if name.startswith("_"):
                    continue
                try:
                    coll = self.db.collection(name)
                    n = coll.count()
                    coll.truncate()
                    deleted[name] = n
                    self.logger.info(f"Truncated {name}: {n} docs removed")
                except Exception as e:
                    self.logger.error(f"Error truncating {name}: {e}")
                    deleted[name] = -1
            return deleted
        except Exception as e:
            self.logger.error(f"Error resetting database: {e}")
            raise

    def drop_database(self, confirm: bool = False) -> bool:
        if not confirm:
            raise ValueError("drop_database requires confirm=True.")
        try:
            sys_db = self.client.db("_system", username=self.username, password=self.password)
            if sys_db.has_database(self.db_name):
                self.logger.warning(f"Dropping database {self.db_name}...")
                sys_db.delete_database(self.db_name)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error dropping database: {e}")
            raise
