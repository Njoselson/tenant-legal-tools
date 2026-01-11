"""
Utilities for loading and managing test datasets for evaluation.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_entities_dataset(fixtures_dir: Path | None = None) -> dict[str, Any]:
    """
    Load entity test dataset.

    Returns:
        Dictionary with entity test cases
    """
    if fixtures_dir is None:
        fixtures_dir = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "evaluation"

    entities_path = fixtures_dir / "entities_dataset.json"

    if not entities_path.exists():
        # Fallback to existing test_entities.json if available
        fallback_path = fixtures_dir / "test_entities.json"
        if fallback_path.exists():
            logger.info(f"Using fallback entities dataset: {fallback_path}")
            with open(fallback_path) as f:
                data = json.load(f)
                # Convert to expected format
                return {
                    "entities": [
                        {
                            "entity_id": e.get("id"),
                            "expected_quote": e.get("expected_properties", {}).get("has_best_quote"),
                            "expected_chunks": e.get("expected_properties", {}).get("min_chunk_count", 1),
                            "expected_sources": e.get("expected_properties", {}).get("min_source_count", 1),
                            "entity_type": e.get("entity_type"),
                            "name": e.get("name"),
                        }
                        for e in data.get("entities", [])
                    ]
                }
        return {"entities": []}

    with open(entities_path) as f:
        return json.load(f)


def load_queries_dataset(fixtures_dir: Path | None = None) -> dict[str, Any]:
    """
    Load query test dataset.

    Returns:
        Dictionary with query test cases
    """
    if fixtures_dir is None:
        fixtures_dir = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "evaluation"

    queries_path = fixtures_dir / "queries_dataset.json"

    if not queries_path.exists():
        # Fallback to existing test_queries.json if available
        fallback_path = fixtures_dir / "test_queries.json"
        if fallback_path.exists():
            logger.info(f"Using fallback queries dataset: {fallback_path}")
            with open(fallback_path) as f:
                data = json.load(f)
                # Convert to expected format
                return {
                    "queries": [
                        {
                            "query_text": q.get("query_text"),
                            "expected_entities": q.get("expected_entities", []),
                            "expected_chunks": [],  # Not in original format
                            "expected_claim_types": [],  # Not in original format
                            "query_id": q.get("query_id"),
                        }
                        for q in data.get("queries", [])
                    ]
                }
        return {"queries": []}

    with open(queries_path) as f:
        return json.load(f)


def load_proof_chains_dataset(fixtures_dir: Path | None = None) -> dict[str, Any]:
    """
    Load proof chain test dataset.

    Returns:
        Dictionary with proof chain test cases
    """
    if fixtures_dir is None:
        fixtures_dir = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "evaluation"

    proof_chains_path = fixtures_dir / "proof_chains_dataset.json"

    if not proof_chains_path.exists():
        # Fallback to existing test_cases.json if available
        fallback_path = fixtures_dir / "test_cases.json"
        if fallback_path.exists():
            logger.info(f"Using fallback proof chains dataset: {fallback_path}")
            with open(fallback_path) as f:
                data = json.load(f)
                # Convert to expected format
                return {
                    "proof_chains": [
                        {
                            "issue": case.get("expected_metadata", {}).get("outcome", "unknown"),
                            "expected_laws": case.get("expected_entities", []),
                            "expected_remedies": case.get("expected_metadata", {}).get("relief_granted", []),
                            "expected_evidence": case.get("expected_evidence_count", 0),
                            "case_id": case.get("case_id"),
                        }
                        for case in data.get("cases", [])
                    ]
                }
        return {"proof_chains": []}

    with open(proof_chains_path) as f:
        return json.load(f)
