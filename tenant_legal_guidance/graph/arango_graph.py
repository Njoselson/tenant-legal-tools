import logging
import os
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import torch
from arango import ArangoClient
from torch_geometric.data import Data

from tenant_legal_guidance.models.entities import EntityType, LegalEntity, SourceType, SourceAuthority
from tenant_legal_guidance.models.relationships import LegalRelationship, RelationshipType


class ArangoDBGraph:
    def __init__(
        self,
        host: str = None,
        db_name: str = None,
        username: str = None,
        password: str = None,
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        # Use environment variables with fallback to default values
        self.host = host or os.getenv("ARANGO_HOST", "http://localhost:8529")
        self.db_name = db_name or os.getenv("ARANGO_DB_NAME", "tenant_legal_kg")
        self.username = username or os.getenv("ARANGO_USERNAME", "root")
        self.password = password or os.getenv("ARANGO_PASSWORD", "")
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Initializing ArangoDB connection to {self.host}")

        # Initialize connection with retry logic
        self._init_connection()

        self.logger.info("Initialized ArangoDBGraph")

    def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity by id and all incident edges. Returns True if deleted, False if not found.
        The entity collection is inferred from the id prefix before ':'.
        """
        try:
            if ':' in entity_id:
                prefix = entity_id.split(':', 1)[0]
                prefix_to_type = {
                    'law': EntityType.LAW,
                    'remedy': EntityType.REMEDY,
                    'court_case': EntityType.COURT_CASE,
                    'legal_procedure': EntityType.LEGAL_PROCEDURE,
                    'damages': EntityType.DAMAGES,
                    'legal_concept': EntityType.LEGAL_CONCEPT,
                    'tenant_group': EntityType.TENANT_GROUP,
                    'campaign': EntityType.CAMPAIGN,
                    'tactic': EntityType.TACTIC,
                    'tenant': EntityType.TENANT,
                    'landlord': EntityType.LANDLORD,
                    'legal_service': EntityType.LEGAL_SERVICE,
                    'government_entity': EntityType.GOVERNMENT_ENTITY,
                    'legal_outcome': EntityType.LEGAL_OUTCOME,
                    'organizing_outcome': EntityType.ORGANIZING_OUTCOME,
                    'tenant_issue': EntityType.TENANT_ISSUE,
                    'event': EntityType.EVENT,
                    'document': EntityType.DOCUMENT,
                    'evidence': EntityType.EVIDENCE,
                    'jurisdiction': EntityType.JURISDICTION,
                }
                et = prefix_to_type.get(prefix)
                if et is None:
                    self.logger.warning(f"Unknown entity prefix for delete: {entity_id}")
                    return False
                coll_name = self._get_collection_for_entity(et)
            else:
                # Fallback: find collection that has the key
                coll_name = None
                for et in EntityType:
                    cn = self._get_collection_for_entity(et)
                    if self.db.collection(cn).has(entity_id):
                        coll_name = cn
                        break
                if coll_name is None:
                    return False

            coll = self.db.collection(coll_name)
            if not coll.has(entity_id):
                return False

            # Remove incident edges across all edge collections
            for rel_type in RelationshipType:
                edge_coll = self.db.collection(self._get_collection_for_relationship(rel_type))
                try:
                    aql = """
                    FOR e IN @@edge_coll
                        FILTER e._from == CONCAT(@from_coll, '/', @key) OR e._to == CONCAT(@to_coll, '/', @key)
                        REMOVE e IN @@edge_coll
                    """
                    bind_vars = {
                        '@edge_coll': edge_coll.name,
                        'from_coll': coll_name,
                        'to_coll': coll_name,
                        'key': entity_id,
                    }
                    self.db.aql.execute(aql, bind_vars=bind_vars)
                except Exception as e:
                    self.logger.warning(f"Failed removing edges for {entity_id} in {edge_coll.name}: {e}")

            # Remove the vertex
            coll.delete(entity_id)
            return True
        except Exception as e:
            self.logger.error(f"Error deleting entity {entity_id}: {e}")
            return False

    def delete_entities(self, entity_ids: List[str]) -> Dict[str, bool]:
        """Bulk delete entities by ids. Returns mapping id -> success flag."""
        results: Dict[str, bool] = {}
        for eid in entity_ids:
            results[eid] = self.delete_entity(eid)
        return results

    def _init_connection(self):
        """Initialize connection to ArangoDB with retry logic."""
        for attempt in range(self.max_retries):
            try:
                self.logger.debug(
                    f"Attempting to connect to ArangoDB (attempt {attempt + 1}/{self.max_retries})"
                )
                self.client = ArangoClient(hosts=self.host)

                # First connect to _system database to check/create our database
                sys_db = self.client.db("_system", username=self.username, password=self.password)

                # Check if our database exists
                if not sys_db.has_database(self.db_name):
                    self.logger.info(f"Creating database: {self.db_name}")
                    sys_db.create_database(
                        name=self.db_name,
                        users=[
                            {
                                "username": self.username,
                                "password": self.password,
                                "active": True,
                                "extra": {"is_superuser": True}
                            }
                        ],
                    )

                # Now connect to our database
                self.db = self.client.db(
                    self.db_name, username=self.username, password=self.password
                )

                # Test connection by getting server version
                version = self.db.version()
                self.logger.info(f"Successfully connected to ArangoDB version {version}")

                # Initialize collections, indexes, and search view
                self._init_collections()
                self._init_indexes()
                self._ensure_search_view()
                return

            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)  # Exponential backoff
                    self.logger.warning(
                        f"Failed to connect to ArangoDB (attempt {attempt + 1}/{self.max_retries}): {str(e)}. "
                        f"Retrying in {wait_time} seconds..."
                    )
                    time.sleep(wait_time)
                else:
                    self.logger.error(
                        f"Failed to connect to ArangoDB after {self.max_retries} attempts. "
                        f"Please ensure ArangoDB is running and accessible at {self.host}. "
                        f"Error: {str(e)}"
                    )
                    raise ConnectionError(
                        f"Could not connect to ArangoDB at {self.host}. "
                        "Please ensure the database is running and accessible."
                    ) from e

    def _init_collections(self):
        """Initialize required collections in ArangoDB."""
        try:
            # Create vertex collections for all entity types
            vertex_collections = [
                "actors",
                "laws",
                "remedies", 
                "court_cases",
                "legal_procedures",
                "damages",
                "legal_concepts",
                
                # Organizing entities
                "tenant_groups",
                "campaigns",
                "tactics",
                
                # Parties
                "tenants",
                "landlords",
                "legal_services",
                "government_entities",
                
                # Outcomes
                "legal_outcomes",
                "organizing_outcomes",
                
                # Issues and events
                "tenant_issues",
                "events",
                
                # Documentation and evidence
                "documents",
                "evidence",
                
                # Geographic and jurisdictional
                "jurisdictions"
            ]

            for collection in vertex_collections:
                if not self.db.has_collection(collection):
                    self.db.create_collection(collection)
                    self.logger.info(f"Created vertex collection: {collection}")

            # Create edge collections
            edge_collections = [
                "violates",
                "enables",
                "awards",
                "applies_to",
                "prohibits",
                "requires",
                "available_via",
                "filed_in",
                "provided_by",
                "supported_by",
                "results_in",
            ]

            for collection in edge_collections:
                if not self.db.has_collection(collection):
                    self.db.create_collection(collection, edge=True)
                    self.logger.info(f"Created edge collection: {collection}")

        except Exception as e:
            self.logger.error(f"Error initializing collections: {str(e)}")
            raise

    def _init_indexes(self):
        """Initialize required indexes in ArangoDB."""
        try:
            # Add indexes for each vertex collection
            for entity_type in EntityType:
                coll_name = self._get_collection_for_entity(entity_type)
                if not self.db.has_collection(coll_name):
                    continue
                coll = self.db.collection(coll_name)
                # Index on type and name for dedupe/lookups
                try:
                    coll.add_index({
                        "type": "persistent",
                        "fields": ["type", "name"],
                        "name": "idx_type_name"
                    })
                except Exception:
                    pass
                # Index on jurisdiction to speed filtering
                try:
                    coll.add_index({
                        "type": "persistent",
                        "fields": ["jurisdiction"],
                        "name": "idx_jurisdiction"
                    })
                except Exception:
                    pass

            # Edge collection indexes
            for rel_type in RelationshipType:
                edge_name = self._get_collection_for_relationship(rel_type)
                if not self.db.has_collection(edge_name):
                    continue
                edges = self.db.collection(edge_name)
                try:
                    edges.add_index({
                        "type": "persistent",
                        "fields": ["_from", "type"],
                        "name": "idx_from_type"
                    })
                except Exception:
                    pass
                try:
                    edges.add_index({
                        "type": "persistent",
                        "fields": ["_to"],
                        "name": "idx_to"
                    })
                except Exception:
                    pass

            self.logger.info("Initialized database indexes")

        except Exception as e:
            self.logger.error(f"Error initializing indexes: {str(e)}")
            raise

    def _ensure_search_view(self):
        """Create or update an ArangoSearch view over all entity collections."""
        try:
            view_name = "kg_entities_view"
            # Build links for all vertex collections
            links: Dict[str, Dict] = {}
            for entity_type in EntityType:
                coll_name = self._get_collection_for_entity(entity_type)
                if not self.db.has_collection(coll_name):
                    continue
                links[coll_name] = {
                    "includeAllFields": False,
                    "fields": {
                        "name": {"analyzers": ["text_en"]},
                        "description": {"analyzers": ["text_en"]},
                        "type": {"analyzers": ["identity"]},
                        "jurisdiction": {"analyzers": ["identity"]}
                    }
                }

            # Try to get the view; if it doesn't exist, create it
            view = None
            try:
                view = self.db.view(view_name)
            except Exception:
                # Fallback creation path compatible with older drivers
                try:
                    view = self.db.create_view(view_name, view_type="arangosearch", properties={"links": links})
                    self.logger.info(f"Created ArangoSearch view: {view_name}")
                except Exception as create_err:
                    self.logger.warning(f"Failed creating ArangoSearch view '{view_name}': {create_err}")
                    return

            # Update properties (if possible) to ensure links are current
            try:
                # Some driver versions use update_properties; others use update
                if hasattr(view, "update_properties"):
                    view.update_properties({"links": links})
                elif hasattr(view, "update"):
                    view.update({"links": links})
            except Exception as upd_err:
                self.logger.warning(f"Updating search view properties failed: {upd_err}")
        except Exception as e:
            self.logger.warning(f"Failed to ensure search view: {e}")

    def _get_collection_for_entity(self, entity_type: EntityType) -> str:
        """Get the appropriate collection name for an entity type."""
        collection_map = {
            # Legal entities
            EntityType.LAW: "laws",
            EntityType.REMEDY: "remedies",
            EntityType.COURT_CASE: "court_cases",
            EntityType.LEGAL_PROCEDURE: "legal_procedures",
            EntityType.DAMAGES: "damages",
            EntityType.LEGAL_CONCEPT: "legal_concepts",
            
            # Organizing entities
            EntityType.TENANT_GROUP: "tenant_groups",
            EntityType.CAMPAIGN: "campaigns",
            EntityType.TACTIC: "tactics",
            
            # Parties
            EntityType.TENANT: "tenants",
            EntityType.LANDLORD: "landlords",
            EntityType.LEGAL_SERVICE: "legal_services",
            EntityType.GOVERNMENT_ENTITY: "government_entities",
            
            # Outcomes
            EntityType.LEGAL_OUTCOME: "legal_outcomes",
            EntityType.ORGANIZING_OUTCOME: "organizing_outcomes",
            
            # Issues and events
            EntityType.TENANT_ISSUE: "tenant_issues",
            EntityType.EVENT: "events",
            
            # Documentation and evidence
            EntityType.DOCUMENT: "documents",
            EntityType.EVIDENCE: "evidence",
            
            # Geographic and jurisdictional
            EntityType.JURISDICTION: "jurisdictions"
        }
        return collection_map[entity_type]

    def _get_collection_for_relationship(self, relationship_type: RelationshipType) -> str:
        """Get the collection name for a relationship type."""
        return relationship_type.name.lower()

    def entity_exists(self, entity_id: str) -> bool:
        """Check if an entity exists in the graph."""
        # Search across all entity collections
        for entity_type in EntityType:
            collection = self.db.collection(self._get_collection_for_entity(entity_type))
            if collection.has(entity_id):
                return True
        return False

    def get_entity(self, entity_id: str) -> Optional[LegalEntity]:
        """Retrieve an entity by its ID."""
        # Extract entity type from ID prefix for efficient lookup
        if ':' in entity_id:
            type_prefix = entity_id.split(':', 1)[0]
            # Map prefix to entity type
            prefix_to_type = {
                # Legal entities
                'law': EntityType.LAW,
                'remedy': EntityType.REMEDY,
                'court_case': EntityType.COURT_CASE,
                'legal_procedure': EntityType.LEGAL_PROCEDURE,
                'damages': EntityType.DAMAGES,
                'legal_concept': EntityType.LEGAL_CONCEPT,
                
                # Organizing entities
                'tenant_group': EntityType.TENANT_GROUP,
                'campaign': EntityType.CAMPAIGN,
                'tactic': EntityType.TACTIC,
                
                # Parties
                'tenant': EntityType.TENANT,
                'landlord': EntityType.LANDLORD,
                'legal_service': EntityType.LEGAL_SERVICE,
                'government_entity': EntityType.GOVERNMENT_ENTITY,
                
                # Outcomes
                'legal_outcome': EntityType.LEGAL_OUTCOME,
                'organizing_outcome': EntityType.ORGANIZING_OUTCOME,
                
                # Issues and events
                'tenant_issue': EntityType.TENANT_ISSUE,
                'event': EntityType.EVENT,
                
                # Documentation and evidence
                'document': EntityType.DOCUMENT,
                'evidence': EntityType.EVIDENCE,
                
                # Geographic and jurisdictional
                'jurisdiction': EntityType.JURISDICTION
            }
            entity_type = prefix_to_type.get(type_prefix)
            if entity_type:
                collection = self.db.collection(self._get_collection_for_entity(entity_type))
                if collection.has(entity_id):
                    try:
                        data = collection.get(entity_id)
                        return self._parse_entity_from_doc(data, entity_type)
                    except Exception as e:
                        self.logger.error(
                            f"Error retrieving or parsing entity {entity_id}: {e}", exc_info=True
                        )
                        return None
        
        # Fallback: search across all collections if prefix doesn't match expected pattern
        self.logger.warning(f"Entity ID {entity_id} doesn't follow expected prefix pattern, falling back to full search")
        for entity_type in EntityType:
            collection = self.db.collection(self._get_collection_for_entity(entity_type))
            if collection.has(entity_id):
                try:
                    data = collection.get(entity_id)
                    return self._parse_entity_from_doc(data, entity_type)
                except Exception as e:
                    self.logger.error(
                        f"Error retrieving or parsing entity {entity_id}: {e}", exc_info=True
                    )
                    return None
        return None

    def find_entity_by_name(self, name: str, types: Optional[List[EntityType]] = None) -> Optional[LegalEntity]:
        """Find an entity by exact name across collections. Optionally restrict by types.
        Returns the first exact match found or None.
        """
        try:
            search_types = types or list(EntityType)
            for et in search_types:
                coll_name = self._get_collection_for_entity(et)
                if not self.db.has_collection(coll_name):
                    continue
                try:
                    aql = """
                    FOR doc IN @@coll
                        FILTER doc.name == @name
                        LIMIT 1
                        RETURN doc
                    """
                    cursor = self.db.aql.execute(aql, bind_vars={"@coll": coll_name, "name": name})
                    docs = list(cursor)
                    if docs:
                        return self._parse_entity_from_doc(docs[0], et)
                except Exception as sub_err:
                    self.logger.debug(f"Name lookup failed in {coll_name}: {sub_err}")
                    continue
            return None
        except Exception as e:
            self.logger.error(f"find_entity_by_name error: {e}")
            return None

    def find_entity_id_by_name(self, name: str, types: Optional[List[EntityType]] = None) -> Optional[str]:
        ent = self.find_entity_by_name(name, types)
        return ent.id if ent else None

    def _parse_entity_from_doc(self, data: Dict, entity_type: EntityType) -> LegalEntity:
        """Parse ArangoDB document into LegalEntity object."""
        # Extract source metadata from stored data
        stored_metadata = data.get("source_metadata", {})
        
        # Validate and clean entity type
        stored_type = data.get("type", "")
        valid_entity_type = entity_type.name  # Default to the collection's entity type
        
        # Try to validate the stored type
        if stored_type:
            try:
                # First try by enum NAME (e.g., "LAW")
                valid_entity_type = EntityType[stored_type].value
            except KeyError:
                try:
                    # Then try by enum VALUE (e.g., "law")
                    valid_entity_type = EntityType(stored_type).value
                except ValueError:
                    # If stored type is invalid, log it and use the collection's entity type
                    self.logger.warning(f"Invalid entity type '{stored_type}' for entity {data.get('_key', 'unknown')}, using {entity_type.name}")
                    valid_entity_type = entity_type.value
        
        # Map ArangoDB document to LegalEntity fields
        entity_data = {
            "id": data["_key"],  # Use _key as id
            "entity_type": valid_entity_type,
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "attributes": {k: v for k, v in data.items() 
                        if k not in ["_key", "type", "name", "description", "source_metadata", "jurisdiction"]},
            "source_metadata": {
                "source": stored_metadata.get("source", data["_key"]),  # Use stored source or fallback
                "source_type": stored_metadata.get("source_type", SourceType.INTERNAL),
                "authority": stored_metadata.get("authority", SourceAuthority.INFORMATIONAL_ONLY),
                "document_type": stored_metadata.get("document_type"),
                "organization": stored_metadata.get("organization"),
                "title": stored_metadata.get("title"),
                "jurisdiction": stored_metadata.get("jurisdiction"),
                "created_at": stored_metadata.get("created_at"),
                "processed_at": stored_metadata.get("processed_at"),
                "last_updated": stored_metadata.get("last_updated"),
                "cites": stored_metadata.get("cites", []),
                "attributes": stored_metadata.get("attributes", {})
            }
        }
        return LegalEntity(**entity_data)

    def add_entity(self, entity: LegalEntity, overwrite: bool = False) -> bool:
        """Add a legal entity to the knowledge graph. Returns True if added/updated, False if skipped."""
        collection = self.db.collection(self._get_collection_for_entity(entity.entity_type))

        # Convert source metadata to dict and handle datetime serialization
        source_metadata = entity.source_metadata.dict()
        for field in ['created_at', 'processed_at', 'last_updated']:
            if field in source_metadata and source_metadata[field]:
                if isinstance(source_metadata[field], datetime):
                    source_metadata[field] = source_metadata[field].isoformat()
                elif isinstance(source_metadata[field], str):
                    # Already a string, keep as is
                    pass
                else:
                    # Convert to string if it's not already
                    source_metadata[field] = str(source_metadata[field])

        # Ensure required fields are present
        if 'source' not in source_metadata or not source_metadata['source']:
            source_metadata['source'] = entity.id

        # Validation: id prefix must match entity_type value
        expected_prefix = entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type)
        if ':' in entity.id:
            prefix = entity.id.split(':', 1)[0]
            if prefix != expected_prefix:
                self.logger.warning(f"Entity id prefix/type mismatch: id='{entity.id}' vs type='{expected_prefix}'.")

        # Promote jurisdiction to top-level field when available
        top_level_jurisdiction: Optional[str] = None
        # Prefer explicit top-level in attributes if present
        if isinstance(entity.attributes, dict) and 'jurisdiction' in entity.attributes:
            top_level_jurisdiction = str(entity.attributes.get('jurisdiction'))
        elif source_metadata.get('jurisdiction'):
            top_level_jurisdiction = str(source_metadata.get('jurisdiction'))

        # Prepare document with required fields
        doc = {
            "_key": entity.id,
            "type": (entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type)).lower(),
            "name": entity.name,
            "description": entity.description,
            "source_metadata": source_metadata,
            **entity.attributes,
        }
        if top_level_jurisdiction:
            doc["jurisdiction"] = top_level_jurisdiction

        # Auto-populate URL for evidence/document entities from source when available
        try:
            etype_value = entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type).lower()
            source_str = source_metadata.get('source') if isinstance(source_metadata, dict) else None
            if isinstance(source_str, str) and source_str.startswith(('http://', 'https://')):
                if etype_value in ('evidence', 'document') and not doc.get('url'):
                    doc['url'] = source_str
        except Exception:
            # Non-fatal; continue without url
            pass

        if collection.has(entity.id):
            if overwrite:
                self.logger.warning(f"Overwriting existing entity: {entity.id}")
                collection.update(doc)
                return True
            else:
                self.logger.debug(f"Skipping duplicate entity: {entity.id}")
                return False
        else:
            self.logger.info(f"Adding new entity: {entity.id} ({entity.entity_type.name})")
            collection.insert(doc)
            return True

    def _select_canonical_source(self, existing_meta: Dict, new_meta: Dict) -> Dict:
        """Choose canonical source metadata comparing authority then recency."""
        try:
            # Map SourceAuthority order (higher is better)
            order = {
                SourceAuthority.BINDING_LEGAL_AUTHORITY.value: 6,
                SourceAuthority.PERSUASIVE_AUTHORITY.value: 5,
                SourceAuthority.OFFICIAL_INTERPRETIVE.value: 4,
                SourceAuthority.REPUTABLE_SECONDARY.value: 3,
                SourceAuthority.PRACTICAL_SELF_HELP.value: 2,
                SourceAuthority.INFORMATIONAL_ONLY.value: 1,
            }
            ex = existing_meta or {}
            ne = new_meta or {}
            ex_auth = ex.get("authority")
            ne_auth = ne.get("authority")
            ex_score = order.get(ex_auth if isinstance(ex_auth, str) else getattr(ex_auth, "value", None), 0)
            ne_score = order.get(ne_auth if isinstance(ne_auth, str) else getattr(ne_auth, "value", None), 0)
            if ne_score > ex_score:
                return ne
            if ne_score < ex_score:
                return ex
            # Tie-breaker: most recent created_at/processed_at
            def _parse(dt):
                try:
                    if isinstance(dt, str):
                        return datetime.fromisoformat(dt.replace('Z', '+00:00'))
                except Exception:
                    return None
                return dt
            ne_ts = _parse(ne.get("created_at")) or _parse(ne.get("processed_at"))
            ex_ts = _parse(ex.get("created_at")) or _parse(ex.get("processed_at"))
            if ne_ts and (not ex_ts or ne_ts > ex_ts):
                return ne
            return ex or ne
        except Exception:
            return new_meta or existing_meta

    def upsert_entity_provenance(self, entity: LegalEntity, provenance_entry: Dict) -> bool:
        """Upsert an entity; if it exists, merge provenance, mentions_count, and possibly canonical source.
        Returns True if inserted or updated.
        """
        try:
            coll_name = self._get_collection_for_entity(entity.entity_type)
            coll = self.db.collection(coll_name)
            if coll.has(entity.id):
                doc = coll.get(entity.id)
                # Merge description if missing or new has content and existing empty
                if (not doc.get("description")) and entity.description:
                    doc["description"] = entity.description
                # Merge attributes (non-destructive)
                if isinstance(entity.attributes, dict):
                    for k, v in entity.attributes.items():
                        if k not in doc:
                            doc[k] = v
                # Merge provenance list
                prov_list = doc.get("provenance", []) or []
                def _key(p):
                    src = (p or {}).get("source", {})
                    return f"{src.get('source')}::{(p or {}).get('quote','')[:64]}"
                seen = { _key(p) for p in prov_list }
                # Enrich provenance with stable id and length/anchor_url if possible
                def _enrich(p: Dict) -> Dict:
                    if not isinstance(p, dict):
                        return p
                    try:
                        if 'provenance_id' not in p or not p.get('provenance_id'):
                            src = (p.get('source') or {}).get('source') or ''
                            q = (p.get('quote') or '')
                            pid = f"prov:{abs(hash(src + '::' + q[:64]))}"
                            p['provenance_id'] = pid
                        if 'length' not in p and p.get('quote'):
                            p['length'] = len(p.get('quote'))
                        # Anchor URL: if source is URL and offset present, append as fragment for later use
                        src_url = (p.get('source') or {}).get('source')
                        if isinstance(src_url, str) and src_url.startswith(('http://','https://')) and p.get('offset') is not None:
                            try:
                                p['anchor_url'] = f"{src_url}#p={max(1, int(p.get('offset') or 0)//500)}"
                            except Exception:
                                p['anchor_url'] = src_url
                    except Exception:
                        pass
                    return p
                if provenance_entry and _key(provenance_entry) not in seen:
                    prov_list.append(_enrich(provenance_entry))
                # Backfill enrich existing ones
                prov_list = [_enrich(p) for p in prov_list]
                doc["provenance"] = prov_list
                # Mentions count: unique sources
                unique_sources = { (p.get("source", {}) or {}).get("source") for p in prov_list if isinstance(p, dict) }
                doc["mentions_count"] = len({ s for s in unique_sources if s })
                # Canonical source selection
                existing_meta = doc.get("source_metadata") or {}
                new_meta = entity.source_metadata.dict() if hasattr(entity.source_metadata, "dict") else entity.source_metadata
                doc["source_metadata"] = self._select_canonical_source(existing_meta, new_meta)
                coll.update(doc)
                return True
            else:
                # New insert with provenance
                base_inserted = self.add_entity(entity, overwrite=False)
                if base_inserted:
                    doc = coll.get(entity.id)
                    if provenance_entry:
                        # Enrich new provenance
                        penr = provenance_entry
                        try:
                            src = (penr.get('source') or {}).get('source') or ''
                            q = (penr.get('quote') or '')
                            penr['provenance_id'] = penr.get('provenance_id') or f"prov:{abs(hash(src + '::' + q[:64]))}"
                            if 'length' not in penr and penr.get('quote'):
                                penr['length'] = len(penr.get('quote'))
                            src_url = (penr.get('source') or {}).get('source')
                            if isinstance(src_url, str) and src_url.startswith(('http://','https://')) and penr.get('offset') is not None:
                                try:
                                    penr['anchor_url'] = f"{src_url}#p={max(1, int(penr.get('offset') or 0)//500)}"
                                except Exception:
                                    penr['anchor_url'] = src_url
                        except Exception:
                            pass
                        doc["provenance"] = [penr]
                    else:
                        doc["provenance"] = []
                    unique_sources = { (provenance_entry or {}).get("source", {}).get("source") }
                    doc["mentions_count"] = len({ s for s in unique_sources if s })
                    coll.update(doc)
                    return True
                return False
        except Exception as e:
            self.logger.error(f"upsert_entity_provenance failed for {entity.id}: {e}")
            return False

    def add_relationship(self, relationship: LegalRelationship) -> bool:
        """Add a relationship between entities. Returns True if added, False otherwise."""
        if not self.entity_exists(relationship.source_id):
            self.logger.error(
                f"Cannot add relationship: Source entity {relationship.source_id} not found"
            )
            return False
        if not self.entity_exists(relationship.target_id):
            self.logger.error(
                f"Cannot add relationship: Target entity {relationship.target_id} not found"
            )
            return False

        collection = self.db.collection(
            self._get_collection_for_relationship(relationship.relationship_type)
        )

        # Get source and target entity types to determine collections
        source_entity = self.get_entity(relationship.source_id)
        target_entity = self.get_entity(relationship.target_id)
        
        if not source_entity or not target_entity:
            self.logger.error("Could not determine entity types for relationship")
            return False

        # Format _from and _to with collection names
        from_collection = self._get_collection_for_entity(source_entity.entity_type)
        to_collection = self._get_collection_for_entity(target_entity.entity_type)
        
        # Deduplicate: skip if identical edge exists
        try:
            aql = """
            FOR e IN @@edge
                FILTER e._from == CONCAT(@from_coll, '/', @from_id) AND e._to == CONCAT(@to_coll, '/', @to_id) AND e.type == @type
                LIMIT 1
                RETURN e
            """
            cur = self.db.aql.execute(aql, bind_vars={
                "@edge": self._get_collection_for_relationship(relationship.relationship_type),
                "from_coll": from_collection,
                "to_coll": to_collection,
                "from_id": relationship.source_id,
                "to_id": relationship.target_id,
                "type": relationship.relationship_type.name,
            })
            if list(cur):
                self.logger.debug("Skipping duplicate relationship insertion")
                return False
        except Exception as e:
            self.logger.debug(f"Edge dedup check failed (continuing): {e}")

        # Create edge document
        edge_doc = {
            "_from": f"{from_collection}/{relationship.source_id}",
            "_to": f"{to_collection}/{relationship.target_id}",
            "type": relationship.relationship_type.name,
            "weight": relationship.weight,
            "conditions": relationship.conditions,
            **relationship.attributes,
        }

        try:
            collection.insert(edge_doc)
            self.logger.debug(
                f"Added relationship: {relationship.source_id} --{relationship.relationship_type.name}--> {relationship.target_id}"
            )
            return True
        except Exception as e:
            self.logger.error(f"Error adding relationship: {e}", exc_info=True)
            return False

    def to_pytorch_geometric(self) -> Data:
        """Convert the graph to PyTorch Geometric format."""
        # Collect all nodes and their features
        node_features = []
        node_mapping = {}  # Map node IDs to indices

        for entity_type in EntityType:
            collection = self.db.collection(self._get_collection_for_entity(entity_type))
            for doc in collection.all():
                # Extract just the entity ID from the _key
                node_id = doc["_key"]
                node_mapping[node_id] = len(node_features)
                # Convert entity attributes to feature vector
                features = self._entity_to_features(doc)
                node_features.append(features)

        # Convert to tensor
        x = torch.tensor(node_features, dtype=torch.float)

        # Collect all edges
        edge_index = []
        edge_attr = []

        for rel_type in RelationshipType:
            collection = self.db.collection(self._get_collection_for_relationship(rel_type))
            for doc in collection.all():
                try:
                    # Extract entity IDs from _from and _to paths
                    source_id = doc["_from"].split("/")[-1]
                    target_id = doc["_to"].split("/")[-1]
                    
                    if source_id in node_mapping and target_id in node_mapping:
                        source_idx = node_mapping[source_id]
                        target_idx = node_mapping[target_id]
                        edge_index.append([source_idx, target_idx])
                        # Convert edge attributes to feature vector
                        edge_features = self._relationship_to_features(doc)
                        edge_attr.append(edge_features)
                    else:
                        self.logger.warning(
                            f"Skipping edge {doc['_from']} -> {doc['_to']} due to missing node mapping. "
                            f"Source: {source_id} (in mapping: {source_id in node_mapping}), "
                            f"Target: {target_id} (in mapping: {target_id in node_mapping})"
                        )
                except Exception as e:
                    self.logger.error(f"Error processing edge {doc.get('_from', 'unknown')} -> {doc.get('_to', 'unknown')}: {e}")
                    continue

        # Convert to tensors
        if edge_index:
            edge_index = torch.tensor(edge_index, dtype=torch.long).t()
            edge_attr = torch.tensor(edge_attr, dtype=torch.float)
        else:
            # No edges found, create empty tensors
            edge_index = torch.empty((2, 0), dtype=torch.long)
            edge_attr = torch.empty((0, len(RelationshipType) + 1), dtype=torch.float)  # +1 for weight

        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)

    def _entity_to_features(self, entity_doc: Dict) -> List[float]:
        """Convert entity document to feature vector."""
        # This is a placeholder - you'll need to implement proper feature extraction
        # based on your specific needs
        features = []
        # Add entity type one-hot encoding
        entity_type = entity_doc.get("type", "")
        for et in EntityType:
            features.append(1.0 if et.value == entity_type or et.name == entity_type else 0.0)
        # Add other features as needed
        return features

    def _relationship_to_features(self, rel_doc: Dict) -> List[float]:
        """Convert relationship document to feature vector."""
        # This is a placeholder - you'll need to implement proper feature extraction
        # based on your specific needs
        features = []
        # Add relationship type one-hot encoding
        rel_type = rel_doc.get("type", "")
        for rt in RelationshipType:
            features.append(1.0 if rt.name == rel_type else 0.0)
        # Add weight
        features.append(rel_doc.get("weight", 1.0))
        # Add other features as needed
        return features

    def find_relevant_laws(self, issue: str) -> List[str]:
        """Find laws relevant to a legal issue using ArangoSearch (BM25/PHRASE)."""
        query = """
        FOR doc IN kg_entities_view
            SEARCH ANALYZER(
                (PHRASE(doc.name, @term) OR PHRASE(doc.description, @term)) AND doc.type == "law",
                "text_en"
            )
            SORT BM25(doc) DESC, TFIDF(doc) DESC
            LIMIT 50
            RETURN DISTINCT doc.name
        """
        try:
            cursor = self.db.aql.execute(query, bind_vars={"term": issue})
            return list(cursor)
        except Exception as e:
            self.logger.error(f"Error executing law search: {e}")
            return []

    def get_all_entities(self) -> List[LegalEntity]:
        """Get all entities from the knowledge graph."""
        entities = []
        try:
            for entity_type in EntityType:
                collection = self.db.collection(self._get_collection_for_entity(entity_type))
                for doc in collection.all():
                    try:
                        entity = self._parse_entity_from_doc(doc, entity_type)
                        entities.append(entity)
                    except Exception as entity_error:
                        self.logger.warning(f"Error parsing entity {doc.get('_key', 'unknown')}: {entity_error}")
                        continue  # Skip this entity and continue with others
            return entities
        except Exception as e:
            self.logger.error(f"Error getting all entities: {e}")
            return []
    
    def get_all_relationships(self) -> List[LegalRelationship]:
        """Get all relationships from the knowledge graph."""
        relationships = []
        try:
            for rel_type in RelationshipType:
                collection = self.db.collection(self._get_collection_for_relationship(rel_type))
                for doc in collection.all():
                    # Parse relationship from document
                    relationship = LegalRelationship(
                        source_id=doc["_from"].split("/")[-1],
                        target_id=doc["_to"].split("/")[-1],
                        relationship_type=rel_type,
                        conditions=doc.get("conditions", []),
                        weight=doc.get("weight", 1.0),
                        attributes=doc.get("attributes", {})
                    )
                    relationships.append(relationship)
            return relationships
        except Exception as e:
            self.logger.error(f"Error getting all relationships: {e}")
            return []

    def _collection_for_entity_id(self, entity_id: str) -> Optional[str]:
        """Infer vertex collection name from id prefix, or scan to find it."""
        try:
            if ':' in entity_id:
                prefix = entity_id.split(':', 1)[0]
                mapping = {
                    'law': EntityType.LAW,
                    'remedy': EntityType.REMEDY,
                    'court_case': EntityType.COURT_CASE,
                    'legal_procedure': EntityType.LEGAL_PROCEDURE,
                    'damages': EntityType.DAMAGES,
                    'legal_concept': EntityType.LEGAL_CONCEPT,
                    'tenant_group': EntityType.TENANT_GROUP,
                    'campaign': EntityType.CAMPAIGN,
                    'tactic': EntityType.TACTIC,
                    'tenant': EntityType.TENANT,
                    'landlord': EntityType.LANDLORD,
                    'legal_service': EntityType.LEGAL_SERVICE,
                    'government_entity': EntityType.GOVERNMENT_ENTITY,
                    'legal_outcome': EntityType.LEGAL_OUTCOME,
                    'organizing_outcome': EntityType.ORGANIZING_OUTCOME,
                    'tenant_issue': EntityType.TENANT_ISSUE,
                    'event': EntityType.EVENT,
                    'document': EntityType.DOCUMENT,
                    'evidence': EntityType.EVIDENCE,
                    'jurisdiction': EntityType.JURISDICTION,
                }
                et = mapping.get(prefix)
                if et is not None:
                    return self._get_collection_for_entity(et)
            # Fallback scan
            for et in EntityType:
                cn = self._get_collection_for_entity(et)
                if self.db.collection(cn).has(entity_id):
                    return cn
        except Exception:
            pass
        return None

    def get_relationships_among(self, node_ids: List[str]) -> List[LegalRelationship]:
        """Return relationships where both endpoints are within node_ids."""
        try:
            id_set = set(node_ids)
            rels: List[LegalRelationship] = []
            for rel_type in RelationshipType:
                edge_name = self._get_collection_for_relationship(rel_type)
                aql = """
                FOR e IN @@edge
                    LET from_id = SPLIT(e._from, '/')[1]
                    LET to_id = SPLIT(e._to, '/')[1]
                    FILTER from_id IN @ids AND to_id IN @ids
                    RETURN { from_id, to_id, weight: e.weight, conditions: e.conditions }
                """
                cursor = self.db.aql.execute(aql, bind_vars={"@edge": edge_name, "ids": list(id_set)})
                for row in cursor:
                    rels.append(LegalRelationship(
                        source_id=row["from_id"],
                        target_id=row["to_id"],
                        relationship_type=rel_type,
                        conditions=row.get("conditions"),
                        weight=row.get("weight", 1.0),
                        attributes={}
                    ))
            return rels
        except Exception as e:
            self.logger.error(f"get_relationships_among error: {e}")
            return []

    def get_neighbors(self, node_ids: List[str], per_node_limit: int = 50, direction: str = "both") -> Tuple[List[LegalEntity], List[LegalRelationship]]:
        """Get 1-hop neighbors and connecting relationships for the given node ids.
        direction: 'out', 'in', or 'both'
        """
        try:
            neighbors: Dict[str, LegalEntity] = {}
            rels: List[LegalRelationship] = []
            dir_filter_out = direction in ("out", "both")
            dir_filter_in = direction in ("in", "both")

            for nid in node_ids:
                coll_name = self._collection_for_entity_id(nid)
                if not coll_name:
                    continue
                # For each edge collection, find incident edges
                for rel_type in RelationshipType:
                    edge_name = self._get_collection_for_relationship(rel_type)
                    # Outbound
                    if dir_filter_out:
                        aql_out = """
                        FOR e IN @@edge
                            FILTER e._from == CONCAT(@coll, '/', @key)
                            LIMIT @limit
                            RETURN e
                        """
                        cursor_out = self.db.aql.execute(aql_out, bind_vars={"@edge": edge_name, "coll": coll_name, "key": nid, "limit": per_node_limit})
                        for e in cursor_out:
                            to_id = e["_to"].split("/")[-1]
                            rels.append(LegalRelationship(
                                source_id=nid,
                                target_id=to_id,
                                relationship_type=rel_type,
                                conditions=e.get("conditions"),
                                weight=e.get("weight", 1.0),
                                attributes={}
                            ))
                            # Fetch neighbor doc
                            to_coll = e["_to"].split("/")[0]
                            try:
                                doc = self.db.collection(to_coll).get(to_id)
                                # Infer entity type by collection name via reverse lookup
                                et = None
                                for t in EntityType:
                                    if self._get_collection_for_entity(t) == to_coll:
                                        et = t
                                        break
                                if et:
                                    neighbors[to_id] = self._parse_entity_from_doc(doc, et)
                            except Exception:
                                pass
                    # Inbound
                    if dir_filter_in:
                        aql_in = """
                        FOR e IN @@edge
                            FILTER e._to == CONCAT(@coll, '/', @key)
                            LIMIT @limit
                            RETURN e
                        """
                        cursor_in = self.db.aql.execute(aql_in, bind_vars={"@edge": edge_name, "coll": coll_name, "key": nid, "limit": per_node_limit})
                        for e in cursor_in:
                            from_id = e["_from"].split("/")[-1]
                            rels.append(LegalRelationship(
                                source_id=from_id,
                                target_id=nid,
                                relationship_type=rel_type,
                                conditions=e.get("conditions"),
                                weight=e.get("weight", 1.0),
                                attributes={}
                            ))
                            # Fetch neighbor doc
                            from_coll = e["_from"].split("/")[0]
                            try:
                                doc = self.db.collection(from_coll).get(from_id)
                                et = None
                                for t in EntityType:
                                    if self._get_collection_for_entity(t) == from_coll:
                                        et = t
                                        break
                                if et:
                                    neighbors[from_id] = self._parse_entity_from_doc(doc, et)
                            except Exception:
                                pass
            return list(neighbors.values()), rels
        except Exception as e:
            self.logger.error(f"get_neighbors error: {e}")
            return [], []
    
    
    def _fallback_text_search(self, search_term: str, types: Optional[List[EntityType]], jurisdiction: Optional[str], limit: int) -> List[LegalEntity]:
        """Fallback search using AQL LIKE across all collections when ArangoSearch is unavailable."""
        try:
            results: List[LegalEntity] = []
            term = f"%{search_term}%"
            type_filter = None
            types_values: Optional[List[str]] = None
            if types:
                types_values = [t.value for t in types]
                type_filter = True

            j_filter = jurisdiction is not None

            # Iterate collections and query top-K per collection
            for entity_type in EntityType:
                coll_name = self._get_collection_for_entity(entity_type)
                if not self.db.has_collection(coll_name):
                    continue

                aql = """
                FOR doc IN @@coll
                    FILTER (
                        LIKE(LOWER(doc.name), LOWER(@term), true) OR 
                        LIKE(LOWER(doc.description), LOWER(@term), true)
                    )
                    """
                if type_filter:
                    aql += "\n    FILTER doc.type IN @types"
                if j_filter:
                    aql += "\n    FILTER doc.jurisdiction == @jurisdiction"
                aql += "\n    LIMIT @limit\n    RETURN doc"

                bind_vars: Dict[str, object] = {
                    "@coll": coll_name,
                    "term": term,
                    "limit": limit,
                }
                if type_filter:
                    bind_vars["types"] = types_values
                if j_filter:
                    bind_vars["jurisdiction"] = jurisdiction

                try:
                    cursor = self.db.aql.execute(aql, bind_vars=bind_vars)
                    for doc in cursor:
                        # Build entity
                        et = entity_type
                        results.append(self._parse_entity_from_doc(doc, et))
                except Exception as sub_err:
                    self.logger.warning(f"Fallback search failed on {coll_name}: {sub_err}")

                if len(results) >= limit:
                    break

            return results[:limit]
        except Exception as e:
            self.logger.error(f"Fallback text search error: {e}")
            return []

    def search_entities_by_text(self, search_term: str, types: Optional[List[EntityType]] = None, jurisdiction: Optional[str] = None, limit: int = 50) -> List[LegalEntity]:
        """Search for entities by text in name or description using ArangoSearch."""
        try:
            filters = []
            bind_vars: Dict[str, object] = {"term": search_term, "limit": limit}
            if types:
                # Convert to values (lowercase) for matching doc.type
                type_values = [t.value for t in types]
                bind_vars["types"] = type_values
                filters.append("doc.type IN @types")
            if jurisdiction:
                bind_vars["jurisdiction"] = jurisdiction
                filters.append("doc.jurisdiction == @jurisdiction")
            filter_clause = (" AND " + " AND ".join(filters)) if filters else ""

            aql = f"""
            FOR doc IN kg_entities_view
                SEARCH ANALYZER(
                    (PHRASE(doc.name, @term) OR PHRASE(doc.description, @term)){filter_clause}
                    , "text_en"
                )
                SORT BM25(doc) DESC, TFIDF(doc) DESC
                LIMIT @limit
                RETURN doc
            """
            try:
                cursor = self.db.aql.execute(aql, bind_vars=bind_vars)
            except Exception as e:
                # If view missing, ensure and retry; else fallback
                msg = str(e)
                self.logger.warning(f"ArangoSearch view issue detected: {msg}. Ensuring view and retrying/falling back...")
                try:
                    self._ensure_search_view()
                    cursor = self.db.aql.execute(aql, bind_vars=bind_vars)
                except Exception as retry_err:
                    self.logger.warning(f"Retry with view failed: {retry_err}. Using fallback LIKE search.")
                    return self._fallback_text_search(search_term, types, jurisdiction, limit)

            results: List[LegalEntity] = []
            for doc in cursor:
                # Infer entity type from stored doc.type or from id prefix
                et_value = doc.get("type")
                et: Optional[EntityType] = None
                if et_value:
                    try:
                        et = EntityType(et_value)
                    except Exception:
                        et = None
                if et is None:
                    key = doc.get("_key", "")
                    if ":" in key:
                        prefix = key.split(":", 1)[0]
                        try:
                            et = EntityType(prefix)
                        except Exception:
                            et = None
                # Default to LAW if unknown (rare)
                et = et or EntityType.LAW
                results.append(self._parse_entity_from_doc(doc, et))
            return results
        except Exception as e:
            self.logger.error(f"Error searching entities by text: {e}")
            return []

    def migrate_types_to_values(self) -> Dict[str, int]:
        """Migrate stored entity 'type' from enum NAME (e.g., 'LAW') to enum VALUE (e.g., 'law').
        Returns a dict of collection -> updated_count.
        """
        updated_counts: Dict[str, int] = {}
        for entity_type in EntityType:
            collection_name = self._get_collection_for_entity(entity_type)
            collection = self.db.collection(collection_name)
            updated = 0
            try:
                for doc in collection.all():
                    stored_type = doc.get("type")
                    if not stored_type:
                        continue
                    target_value = None
                    # If it's already the value, skip
                    if stored_type == entity_type.value:
                        continue
                    # If matches enum NAME, convert to value
                    if stored_type == entity_type.name:
                        target_value = entity_type.value
                    else:
                        # Try to coerce by name/value lookup
                        try:
                            target_value = EntityType[stored_type].value
                        except KeyError:
                            try:
                                target_value = EntityType(stored_type).value
                            except ValueError:
                                self.logger.warning(
                                    f"Skipping migration for {doc.get('_key', 'unknown')} in {collection_name}: unknown type '{stored_type}'"
                                )
                                continue
                    if target_value and target_value != stored_type:
                        doc["type"] = target_value
                        collection.update(doc)
                        updated += 1
                updated_counts[collection_name] = updated
                self.logger.info(f"Migrated {updated} docs in {collection_name} to type values")
            except Exception as e:
                self.logger.error(f"Error migrating collection {collection_name}: {e}")
                updated_counts[collection_name] = -1
        return updated_counts

    def compute_next_steps(self, issues: List[str], jurisdiction: Optional[str] = None) -> List[Dict]:
        """Compute deterministic next steps from issues through applicable laws, remedies, procedures, and evidence.
        This is a heuristic placeholder; refine with AQL/graph traversal later.
        """
        steps: List[Dict] = []
        try:
            # Gather candidate laws by simple name match
            laws_coll = self.db.collection(self._get_collection_for_entity(EntityType.LAW))
            remedies_coll = self.db.collection(self._get_collection_for_entity(EntityType.REMEDY))
            procedures_coll = self.db.collection(self._get_collection_for_entity(EntityType.LEGAL_PROCEDURE))
            evidence_coll = self.db.collection(self._get_collection_for_entity(EntityType.EVIDENCE))

            # Simple scan; replace with AQL + relationships when populated
            candidate_laws = []
            for doc in laws_coll.all():
                name = doc.get("name", "").lower()
                if any(term.lower() in name for term in issues):
                    candidate_laws.append(doc)

            # Build steps
            for law in candidate_laws:
                step = {
                    "issue_match": law.get("name", ""),
                    "law": law.get("name", ""),
                    "remedies": [],
                    "procedures": [],
                    "evidence": [],
                }
                # Heuristic associations by keywords
                law_text = (law.get("name", "") + " " + law.get("description", "")).lower()

                # Remedies
                for r in remedies_coll.all():
                    r_text = (r.get("name", "") + " " + r.get("description", "")).lower()
                    if any(k in r_text for k in ["hp action", "overcharge", "abatement", "complaint", "311", "dhcr"]):
                        step["remedies"].append(r.get("name", ""))

                # Procedures
                for p in procedures_coll.all():
                    p_text = (p.get("name", "") + " " + p.get("description", "")).lower()
                    if any(k in p_text for k in ["file", "petition", "action", "hearing", "notice", "court"]):
                        step["procedures"].append(p.get("name", ""))

                # Evidence
                for e in evidence_coll.all():
                    e_text = (e.get("name", "") + " " + e.get("description", "")).lower()
                    if any(k in e_text for k in ["receipt", "photo", "violation", "history", "letter", "record"]):
                        step["evidence"].append(e.get("name", ""))

                steps.append(step)
        except Exception as e:
            self.logger.warning(f"compute_next_steps fallback used due to error: {e}")
        return steps

    def build_legal_chains(self, issues: List[str], jurisdiction: Optional[str] = None, limit: int = 25) -> List[Dict]:
        """Build explicit chains (issue -> law -> remedy -> procedure -> evidence) with citations via AQL traversal.
        Returns a list of chains with nodes, edges, and source_metadata for citations.
        """
        try:
            bind_vars: Dict[str, object] = {
                "issues": issues or [],
                "jurisdiction": jurisdiction,
                "limit": limit,
            }
            aql = """
            LET terms = @issues
            LET j = @jurisdiction
            FOR issue IN tenant_issues
              FILTER LENGTH(terms) == 0 OR (
                LIKE(LOWER(issue.name), LOWER(CONCAT('%', terms[0], '%')), true) OR
                (LENGTH(terms) > 1 AND LIKE(LOWER(issue.name), LOWER(CONCAT('%', terms[1], '%')), true)) OR
                (LENGTH(terms) > 2 AND LIKE(LOWER(issue.name), LOWER(CONCAT('%', terms[2], '%')), true))
              )
              FOR law IN INBOUND issue applies_to
                FILTER !j OR law.jurisdiction == j
                FOR remedy IN OUTBOUND law enables
                  FOR proc IN OUTBOUND remedy available_via
                  FOR ev IN OUTBOUND law requires
                    LIMIT @limit
                    RETURN {
                      chain: [
                        {type: "tenant_issue", id: issue._key, name: issue.name, cite: issue.source_metadata},
                        {rel: "APPLIES_TO"},
                        {type: "law", id: law._key, name: law.name, cite: law.source_metadata},
                        {rel: "ENABLES"},
                        {type: "remedy", id: remedy._key, name: remedy.name, cite: remedy.source_metadata},
                        {rel: "AVAILABLE_VIA"},
                        {type: "legal_procedure", id: proc._key, name: proc.name, cite: proc.source_metadata},
                        {rel: "REQUIRES"},
                        {type: "evidence", id: ev._key, name: ev.name, cite: ev.source_metadata}
                      ],
                      score: 1.0
                    }
            """
            cursor = self.db.aql.execute(aql, bind_vars=bind_vars)
            return list(cursor)
        except Exception as e:
            self.logger.error(f"Error building legal chains: {e}")
            return []
