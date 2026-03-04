"""
Persistent storage for curation jobs and session manifests using ArangoDB.
"""

import json
import logging
from datetime import datetime
from typing import Any

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph

logger = logging.getLogger(__name__)


class CurationStorage:
    """Persistent storage for curation data using ArangoDB."""

    def __init__(self, knowledge_graph: ArangoDBGraph):
        self.kg = knowledge_graph
        self.db = knowledge_graph.db
        self._ensure_collections()

    def _ensure_collections(self):
        """Ensure collections exist for jobs and manifests."""
        try:
            # Jobs collection
            if not self.db.has_collection("curation_jobs"):
                self.db.create_collection("curation_jobs")
                logger.info("Created curation_jobs collection")

            # Manifests collection
            if not self.db.has_collection("curation_manifests"):
                self.db.create_collection("curation_manifests")
                logger.info("Created curation_manifests collection")
        except Exception as e:
            logger.error(f"Failed to ensure collections: {e}", exc_info=True)

    # Job storage methods
    def create_job(self, job_id: str, job_data: dict[str, Any]) -> bool:
        """Create a new ingestion job."""
        try:
            doc = {
                "_key": job_id,
                **job_data,
                "created_at": datetime.utcnow().isoformat(),
            }
            self.db.collection("curation_jobs").insert(doc, overwrite=True)
            return True
        except Exception as e:
            logger.error(f"Failed to create job {job_id}: {e}", exc_info=True)
            return False

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Get job by ID."""
        try:
            doc = self.db.collection("curation_jobs").get(job_id)
            if doc:
                # Remove ArangoDB internal fields for API response
                result = dict(doc)
                result.pop("_id", None)
                result.pop("_key", None)
                result.pop("_rev", None)
                return result
            return None
        except Exception as e:
            logger.error(f"Failed to get job {job_id}: {e}", exc_info=True)
            return None

    def update_job(self, job_id: str, updates: dict[str, Any]) -> bool:
        """Update job with new data."""
        try:
            self.db.collection("curation_jobs").update({"_key": job_id}, updates)
            return True
        except Exception as e:
            logger.error(f"Failed to update job {job_id}: {e}", exc_info=True)
            return False

    def list_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        """List recent jobs."""
        try:
            cursor = self.db.aql.execute(
                """
                FOR job IN curation_jobs
                    SORT job.created_at DESC
                    LIMIT @limit
                    RETURN job
                """,
                bind_vars={"limit": limit},
            )
            jobs = []
            for doc in cursor:
                result = dict(doc)
                result.pop("_id", None)
                result.pop("_key", None)
                result.pop("_rev", None)
                jobs.append(result)
            return jobs
        except Exception as e:
            logger.error(f"Failed to list jobs: {e}", exc_info=True)
            return []

    # Manifest storage methods
    def get_manifest(self, session_id: str) -> list[dict[str, Any]]:
        """Get manifest entries for a session."""
        try:
            doc = self.db.collection("curation_manifests").get(session_id)
            if doc and doc.get("entries"):
                return doc["entries"]
            return []
        except Exception as e:
            logger.debug(f"Manifest not found for session {session_id}: {e}")
            return []

    def set_manifest(self, session_id: str, entries: list[dict[str, Any]]) -> bool:
        """Set manifest entries for a session."""
        try:
            doc = {
                "_key": session_id,
                "entries": entries,
                "updated_at": datetime.utcnow().isoformat(),
            }
            self.db.collection("curation_manifests").insert(doc, overwrite=True)
            return True
        except Exception as e:
            logger.error(f"Failed to set manifest for session {session_id}: {e}", exc_info=True)
            return False

    def add_to_manifest(self, session_id: str, entries: list[dict[str, Any]]) -> int:
        """Add entries to existing manifest."""
        try:
            current_entries = self.get_manifest(session_id)
            # Merge and deduplicate by locator
            existing_locators = {e.get("locator") for e in current_entries if e.get("locator")}
            new_entries = [
                e for e in entries if e.get("locator") not in existing_locators
            ]
            updated_entries = current_entries + new_entries
            self.set_manifest(session_id, updated_entries)
            return len(new_entries)
        except Exception as e:
            logger.error(f"Failed to add to manifest for session {session_id}: {e}", exc_info=True)
            return 0

    def remove_from_manifest(self, session_id: str, urls: list[str]) -> int:
        """Remove entries from manifest by URLs."""
        try:
            current_entries = self.get_manifest(session_id)
            original_count = len(current_entries)
            updated_entries = [
                e for e in current_entries if e.get("locator") not in urls
            ]
            self.set_manifest(session_id, updated_entries)
            return original_count - len(updated_entries)
        except Exception as e:
            logger.error(f"Failed to remove from manifest for session {session_id}: {e}", exc_info=True)
            return 0

    def list_manifests(self) -> list[dict[str, Any]]:
        """List all manifests with metadata."""
        try:
            cursor = self.db.aql.execute(
                """
                FOR doc IN curation_manifests
                    RETURN {
                        manifest_id: doc._key,
                        entry_count: LENGTH(doc.entries || []),
                        updated_at: doc.updated_at
                    }
                """,
            )
            manifests = []
            for doc in cursor:
                manifests.append({
                    "manifest_id": doc["manifest_id"],
                    "entry_count": doc["entry_count"],
                    "updated_at": doc.get("updated_at"),
                })
            return manifests
        except Exception as e:
            logger.error(f"Failed to list manifests: {e}", exc_info=True)
            return []

