#!/usr/bin/env python3
"""
One-time migration: flatten per-type collections and nested provenance into
normalized collections: entities, edges, sources, text_blobs, quotes, provenance.

Safe to run multiple times; uses idempotent keys and ISO datetimes.
"""
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Optional

from arango import ArangoClient


def canonicalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def migrate(arango_host: str, db_name: str, username: str, password: str) -> Dict[str, int]:
    client = ArangoClient(hosts=arango_host)
    db = client.db(db_name, username=username, password=password)

    # Ensure normalized collections exist
    for name, is_edge in (
        ("entities", False),
        ("sources", False),
        ("text_blobs", False),
        ("quotes", False),
        ("provenance", False),
        ("edges", True),
    ):
        if not db.has_collection(name):
            db.create_collection(name, edge=is_edge)

    counts = {"entities": 0, "edges": 0, "provenance": 0, "quotes": 0, "sources": 0}

    # Move vertices
    vertex_collections = [
        "laws","remedies","court_cases","legal_procedures","damages","legal_concepts",
        "tenant_groups","campaigns","tactics",
        "tenants","landlords","legal_services","government_entities",
        "legal_outcomes","organizing_outcomes",
        "tenant_issues","events",
        "documents","evidence",
        "jurisdictions",
    ]

    for coll_name in vertex_collections:
        if not db.has_collection(coll_name):
            continue
        src = db.collection(coll_name)
        for doc in src.all():
            # Write to entities with the same _key and minimal fields
            ent = db.collection("entities")
            new_doc = {
                "_key": doc.get("_key"),
                "type": doc.get("type"),
                "name": doc.get("name"),
                "description": doc.get("description"),
                "jurisdiction": doc.get("jurisdiction"),
            }
            # Copy remaining custom attributes
            for k, v in doc.items():
                if k in {"_key","_id","_rev","type","name","description","jurisdiction","source_metadata","provenance","mentions_count"}:
                    continue
                new_doc[k] = v
            try:
                if ent.has(new_doc["_key"]):
                    ent.update(new_doc)
                else:
                    ent.insert(new_doc)
                    counts["entities"] += 1
            except Exception:
                pass

            # Flatten provenance if present
            prov_list = doc.get("provenance") or []
            if isinstance(prov_list, list):
                for p in prov_list:
                    try:
                        # Build/ensure source
                        src_meta = p.get("source") or {}
                        locator = src_meta.get("source") or src_meta.get("url") or doc.get("url") or new_doc["_key"]
                        # Try to use created_at/processed_at as ISO strings
                        fetched_at = src_meta.get("processed_at") or src_meta.get("created_at") or datetime.utcnow().isoformat()
                        sid = f"src:{(src_meta.get('sha256') or '')}"
                        if not sid or sid == "src:":
                            # fallback: create a source without sha, keyed by a hash of locator via server-side
                            # Using locator as key is acceptable temporarily
                            sid = locator
                        s = db.collection("sources")
                        if not s.has(sid):
                            s.insert({
                                "_key": sid,
                                "kind": str(src_meta.get("source_type") or "URL"),
                                "locator": locator,
                                "title": src_meta.get("title"),
                                "jurisdiction": src_meta.get("jurisdiction"),
                                "sha256": src_meta.get("sha256"),
                                "fetched_at": fetched_at,
                                "meta": {},
                            })
                            counts["sources"] += 1
                        # Create quote if text + offset present
                        quote_text = p.get("quote")
                        offset = p.get("offset")
                        quote_id = None
                        if isinstance(offset, int):
                            qid = f"q:{(src_meta.get('sha256') or '')}:{offset}:{offset + len(quote_text or '')}"
                            q = db.collection("quotes")
                            if not q.has(qid):
                                q.insert({
                                    "_key": qid,
                                    "source_id": sid,
                                    "quote_sha256": None,
                                    "start_offset": offset,
                                    "end_offset": offset + len(quote_text or ""),
                                    "chunk_entity_id": None,
                                    "created_at": datetime.utcnow().isoformat(),
                                })
                                counts["quotes"] += 1
                            quote_id = qid
                        # Insert provenance
                        prov = db.collection("provenance")
                        pid = f"prov:{new_doc['_key']}:{sid}:{quote_id or ''}"
                        if not prov.has(pid):
                            prov.insert({
                                "_key": pid,
                                "subject_type": "ENTITY",
                                "subject_id": new_doc["_key"],
                                "source_id": sid,
                                "quote_id": quote_id,
                                "citation": None,
                                "added_at": datetime.utcnow().isoformat(),
                            })
                            counts["provenance"] += 1
                    except Exception:
                        continue

    # Move edges
    edge_collections = [
        "violates","enables","awards","applies_to","prohibits","requires","available_via","filed_in","provided_by","supported_by","results_in","mentions",
    ]
    for edge_name in edge_collections:
        if not db.has_collection(edge_name):
            continue
        ec = db.collection(edge_name)
        for e in ec.all():
            try:
                db.collection("edges").insert({
                    "_from": e.get("_from"),
                    "_to": e.get("_to"),
                    "type": e.get("type"),
                    "weight": e.get("weight", 1.0),
                    "conditions": e.get("conditions"),
                    "attributes": e.get("attributes", {}),
                })
                counts["edges"] += 1
            except Exception:
                continue

    return counts


def main():
    parser = argparse.ArgumentParser(description="Migrate to normalized graph schema")
    parser.add_argument("--host", default="http://localhost:8529")
    parser.add_argument("--db", default="tenant_legal_kg")
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    summary = migrate(args.host, args.db, args.user, args.password)
    print(summary)


if __name__ == "__main__":
    main()


