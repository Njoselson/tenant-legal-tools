"""
Taxonomy-constrained document tagger.

Makes a single LLM call per document, injecting the curated taxonomy IDs, and
maps the response back into a CaseDocumentNode. Unknown concepts are queued in
proposed_new for human review.
"""

import json
import logging
from datetime import datetime

from tenant_legal_guidance.models.entities import CaseDocumentNode, LegalDocumentType, SourceMetadata

logger = logging.getLogger(__name__)


class CaseTagger:
    def __init__(self, deepseek_client) -> None:
        self.deepseek = deepseek_client

    async def tag_document(
        self,
        text: str,
        metadata: SourceMetadata,
        source_id: str,
        chunk_ids: list[str],
        snapshot: dict,
    ) -> CaseDocumentNode:
        """
        Tag a document against the curated taxonomy.

        snapshot: dict with keys claim_types, evidence, procedures, laws — each a list
                  of {id, name, description, ...} dicts from get_taxonomy_snapshot().

        Returns a CaseDocumentNode ready for upsert_case_document().
        """
        from tenant_legal_guidance.prompts import get_document_tagging_prompt

        doc_type_str = (
            metadata.document_type.value
            if metadata.document_type
            else "unknown"
        )
        prompt = get_document_tagging_prompt(
            text=text,
            doc_type=doc_type_str,
            title=metadata.title,
            snapshot=snapshot,
        )

        raw = ""
        try:
            raw = await self.deepseek.chat_completion(prompt)
            data = _parse_json(raw)
        except Exception as e:
            logger.warning(f"CaseTagger LLM call failed for {metadata.source}: {e}")
            data = {}

        valid_claim_ids = {n["id"] for n in snapshot.get("claim_types", [])}
        valid_evidence_ids = {n["id"] for n in snapshot.get("evidence", [])}
        valid_procedure_ids = {n["id"] for n in snapshot.get("procedures", [])}
        valid_law_ids = {n["id"] for n in snapshot.get("laws", [])}

        claim_types = _filter_ids(data.get("claim_types", []), valid_claim_ids)
        evidence_presented = _filter_ids(data.get("evidence_presented", []), valid_evidence_ids)
        procedures_used = _filter_ids(data.get("procedures_used", []), valid_procedure_ids)
        citations = _filter_ids(data.get("citations", []), valid_law_ids)

        invalid = (
            set(data.get("claim_types", [])) - valid_claim_ids
            | set(data.get("evidence_presented", [])) - valid_evidence_ids
            | set(data.get("procedures_used", [])) - valid_procedure_ids
            | set(data.get("citations", [])) - valid_law_ids
        )
        if invalid:
            logger.warning(f"CaseTagger dropped {len(invalid)} unknown IDs for {metadata.source}: {invalid}")

        decision_date = None
        raw_date = data.get("decision_date")
        if raw_date:
            try:
                decision_date = datetime.fromisoformat(raw_date)
            except Exception:
                pass

        doc_id = source_id or _slug(metadata.source)

        raw_jur = (metadata.jurisdiction or "NYC").strip()
        jur_map = {
            "new york city": "NYC", "nyc": "NYC",
            "new york state": "NYS", "new york": "NYS", "nys": "NYS", "ny": "NYS",
        }
        jurisdiction = jur_map.get(raw_jur.lower(), "NYC")

        return CaseDocumentNode(
            id=doc_id,
            name=metadata.title or metadata.source,
            description=None,
            jurisdiction=jurisdiction,
            chunk_ids=chunk_ids,
            source_ids=[source_id] if source_id else [],
            claim_types=claim_types,
            evidence_presented=evidence_presented,
            procedures_used=procedures_used,
            citations=citations,
            proposed_new=data.get("proposed_new", []),
            case_name=data.get("case_name"),
            court=data.get("court"),
            docket_number=data.get("docket_number"),
            decision_date=decision_date,
            outcome=data.get("outcome"),
            holdings=data.get("holdings", []),
            remedies_awarded=data.get("remedies_awarded", []),
        )


def _parse_json(raw: str) -> dict:
    """Extract JSON from LLM output, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _filter_ids(ids: list, valid: set) -> list[str]:
    return [str(i) for i in ids if str(i) in valid]


def _slug(url: str) -> str:
    import hashlib
    return "doc:" + hashlib.sha256(url.encode()).hexdigest()[:12]
