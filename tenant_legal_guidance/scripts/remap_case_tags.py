#!/usr/bin/env python3
"""
Remap case_document tags from merged or deleted taxonomy ids to their survivors.

atlas08 applied the atlas06 audit to the taxonomy YAMLs: 106 proposed nodes
were merged into a survivor and 19 deleted. Any case_document still tagged with
one of those ids points at a node that `seed_taxonomy --prune` will remove, and
prune keeps such nodes alive while anything references them. This rewrites
both the tag arrays on case_documents and the tagging edges, deterministically
from the atlas06 table below (no LLM). Deleted ids are dropped.

Order matters: run this before `make seed-taxonomy PRUNE=1`.

Usage:
  uv run python -m tenant_legal_guidance.scripts.remap_case_tags [--dry-run]
"""

import argparse
import logging
import sys

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

# atlas06 merge table (Operon task "ATLAS - Audit Proposed Taxonomy Bucket"),
# applied to the YAML by atlas08. old id -> survivor id, or None when deleted.
MERGE_MAP: dict[str, dict[str, str | None]] = {
    "claim_types": {
        "dhcr_determination_challenge": None,
        "disability_ac_accommodation": "failure_to_provide_reasonable_accommodation",
        "disability_or_elderly_protection": None,
        "disability_rent_increase_exemption": None,
        "emergency_hp_action": "hp_action_repairs",
        "excessive_rent_increase": "rent_overcharge",
        "failure_to_maintain_cooling": "service_reduction",
        "failure_to_maintain_services": "service_reduction",
        "failure_to_provide_essential_services": "habitability_violation",
        "failure_to_renew_lease": "rent_stabilization_violation",
        "fair_housing_act_discrimination": "housing_discrimination",
        "fraudulent_rent_registration": "fraudulent_deregulation",
        "group_hp_action": "hp_action_repairs",
        "heat_violation": "habitability_violation",
        "hot_water_violation": "habitability_violation",
        "illegal_eviction": "illegal_lockout",
        "illegal_eviction_roommate": "illegal_lockout",
        "illegal_rent_increase": "rent_overcharge",
        "rent_abatement": "breach_warranty_habitability",
        "rent_freeze_and_reduction": "service_reduction",
        "repair_neglect": "habitability_violation",
        "senior_citizen_rent_increase_exemption": None,
        "treble_damages": None,
        "unlawful_ac_fees": "rent_overcharge",
    },
    "laws": {
        "421a_tax_exemption_law": "421a_tax_abatement",
        "dhcr_regulation_on_fraud": None,
        "dhcr_regulations": "rent_stabilization_code",
        "etpa_section_5": "etpa",
        "fheps_regulation": None,
        "fuel_pass_along_prohibition": "hstpa_2019",
        "high_rent_deregulation_law": "nyc_admin_26_504_2",
        "high_rent_high_income_decontrol": "nyc_admin_26_504_2",
        "hpd_code_27-2009": "nyc_admin_27_2005",
        "hpd_mold_violation_classes": None,
        "mdr_law_78": "mdl_78",
        "nyc_admin_code_26_504_2": "nyc_admin_26_504_2",
        "nyc_admin_code_26_516": "nyc_admin_26_516",
        "nyc_admin_code_27-2013": None,
        "nyc_admin_code_ch4_rent_stabilization": "rent_stabilization_law",
        "nyc_admin_code_title_26_ch2": "nyc_admin_code_26_301",
        "nyc_hmc_subchapter_5": "nyc_admin_27_2115",
        "nyc_housing_code_harassment": "nyc_admin_27_2005d",
        "nyc_human_rights_law": "nyc_admin_8_107",
        "nyc_rent_and_rehabilitation_law": "rent_control_law_nyc",
        "nys_penal_law_harassment": "penal_law_241_05",
        "rent_guidelines_board": "rgb_annual_order",
        "rgb_guidelines": "rgb_annual_order",
        "rsc_9_nycrr_2520": "rent_stabilization_code",
        "rsc_section_2525_3": "iai_cap_law",
        "state_enabling_authority_1962": "rent_control_law_nyc",
        "vacancy_increase_law": "rsc_2522_5",
    },
    "procedures": {
        "311_complaint_for_heat_hot_water": "hpd_complaint",
        "department_of_health_complaint": "hpd_complaint",
        "dhcr_administrative_appeal": "dhcr_par_proceeding",
        "dhcr_complaint_cooling": "dhcr_rent_decrease_filing",
        "hpd_attorney_involvement": None,
        "letter_of_complaint": None,
        "small_claims_action": "small_claims_court",
    },
    "evidence_nodes": {
        "apartment_improvement_records": "iai_documentation",
        "bedbug_inspection_report": "expert_report",
        "certified_mail_letter": "written_notice_to_landlord",
        "certified_mail_notices": "written_notice_to_landlord",
        "certified_mail_receipt": "landlord_non_response_evidence",
        "commitment_letters": "public_assistance_docs",
        "complaint_correspondence": "written_notice_to_landlord",
        "complaint_to_government_agency": "311_complaint_record",
        "court_decision": None,
        "court_papers_or_demand_letter": "rent_demand_letter",
        "dhcr_deregulation_orders": "dhcr_order_determination",
        "dhcr_determination_order": "dhcr_order_determination",
        "documents_money_orders_applications": None,
        "eviction_notices": "predicate_notice",
        "evidence_of_harassing_conduct": "harassment_incident_log",
        "expert_inspection_report": "expert_report",
        "first_lease_rent_stabilized": "lease_agreement",
        "government_agency_complaints": "311_complaint_record",
        "harassment_logs": "harassment_incident_log",
        "heating_system_device_evidence": "photos_video_conditions",
        "hot_water_temp_measurements": "temperature_logs",
        "housing_court_filings": "prior_court_orders",
        "hpd_complaint_record": "311_complaint_record",
        "hpd_violation_records": "hpd_violation_record",
        "inspection_reports": "hpd_inspection_report",
        "landlord_name_and_address": "building_ownership_records",
        "lease_agreements": "lease_agreement",
        "lease_and_vacancy_documents": "dhcr_rent_history",
        "lease_or_written_contract": "lease_agreement",
        "letter_of_complaint": "written_notice_to_landlord",
        "mci_cost_documentation": "mci_application_record",
        "money_orders": "rent_receipts",
        "most_recent_lease_market": "lease_agreement",
        "notice_of_defects_to_landlord": "written_notice_to_landlord",
        "photographs_of_conditions": "photos_video_conditions",
        "photos_and_text_messages": "photos_video_conditions",
        "photos_videos_harassment": "harassment_incident_log",
        "previous_tenant_rent_info": "dhcr_rent_history",
        "prior_lease_agreements": "lease_agreement",
        "proof_of_senior_status": "proof_of_disability_or_elderly_status",
        "property_records_acris": "building_ownership_records",
        "public_assistance_breakdown": "public_assistance_docs",
        "public_assistance_case_documents": "public_assistance_docs",
        "ra_89c_form": None,
        "ra_94_form": None,
        "receipts": "rent_receipts",
        "record_of_willful_act_or_negligence": None,
        "relocation_payment_schedule": None,
        "rent_breakdown_from_landlord": "rent_demand_letter",
        "rent_history": "dhcr_rent_history",
        "rent_receipts_and_ledgers": "rent_receipts",
        "rent_regulated_lease": "lease_agreement",
        "rent_stabilization_application": "dhcr_rent_registration",
        "rent_threshold_records": "dhcr_rent_history",
        "repair_request_logs": "repair_request_communications",
        "rgb_guidelines": None,
        "rn_26_notice": "rent_increase_notices",
        "signed_rental_agreement": "lease_agreement",
        "state_issued_id": None,
        "tax_return_income_proof": "income_threshold_records",
        "temperature_readings": "temperature_logs",
        "tenant_complaint_records": "harassment_incident_log",
        "tenant_witness_testimony": "witness_affidavits",
        "vacancy_decontrol_records": "dhcr_rent_history",
        "who_owns_what_data": "building_ownership_records",
        "witness_testimony": "witness_affidavits",
        "written_lease_agreement": "lease_agreement",
    },
}

# taxonomy collection -> (case_document field, tagging edge collection)
TAG_FIELDS = {
    "claim_types": ("claim_types", "tagged_as"),
    "laws": ("citations", "cites"),
    "procedures": ("procedures_used", "applied_procedure"),
    "evidence_nodes": ("evidence_presented", "demonstrates_evidence"),
}


def remap_ids(ids: list[str] | None, mapping: dict[str, str | None]) -> list[str]:
    """Map each id through `mapping`, dropping deleted ids and duplicates, keeping order."""
    out: list[str] = []
    for old in ids or []:
        new = mapping[old] if old in mapping else old
        if new is not None and new not in out:
            out.append(new)
    return out


def plan_doc_updates(docs: list[dict]) -> list[dict]:
    """One {_key, field, old, new} entry per case_document field that changes."""
    updates = []
    for doc in docs:
        for coll, (field, _) in TAG_FIELDS.items():
            old = list(doc.get(field) or [])
            new = remap_ids(old, MERGE_MAP[coll])
            if new != old:
                updates.append({"_key": doc["_key"], "field": field, "old": old, "new": new})
    return updates


def plan_edge_moves(coll: str, edges: list[dict]) -> list[tuple[dict, str | None]]:
    """(edge, new _to or None) for each tagging edge pointing at a merged/deleted node."""
    mapping = MERGE_MAP[coll]
    moves = []
    for e in edges:
        key = e["_to"].split("/", 1)[1]
        if key in mapping:
            target = mapping[key]
            moves.append((e, f"{coll}/{target}" if target else None))
    return moves


def _move_edge(db, edge_coll: str, edge: dict, new_to: str | None) -> None:
    if new_to:
        try:
            db.collection(edge_coll).insert({"_from": edge["_from"], "_to": new_to})
        except Exception as e:
            # Unique (_from, _to) index: the doc already has the survivor edge.
            if "unique" not in str(e).lower() and "1210" not in str(e):
                raise
    db.collection(edge_coll).delete(edge["_key"], ignore_missing=True)


def run(dry_run: bool) -> tuple[int, int]:
    kg = ArangoDBGraph()
    db = kg.db
    docs = list(db.aql.execute("FOR d IN case_documents RETURN d"))
    updates = plan_doc_updates(docs)
    for u in updates:
        logger.info(f"  doc {u['_key']} {u['field']}: {u['old']} -> {u['new']}")
        if not dry_run:
            db.collection("case_documents").update({"_key": u["_key"], u["field"]: u["new"]})

    edge_moves = 0
    for coll, (_, edge_coll) in TAG_FIELDS.items():
        stale = [f"{coll}/{k}" for k in MERGE_MAP[coll]]
        edges = list(
            db.aql.execute(
                "FOR e IN @@ec FILTER e._to IN @stale RETURN e",
                bind_vars={"@ec": edge_coll, "stale": stale},
            )
        )
        for edge, new_to in plan_edge_moves(coll, edges):
            logger.info(f"  edge {edge_coll} {edge['_from']}: {edge['_to']} -> {new_to}")
            if not dry_run:
                _move_edge(db, edge_coll, edge, new_to)
            edge_moves += 1

    verb = "Would update" if dry_run else "Updated"
    logger.info(f"{verb} {len(updates)} tag field(s) and {edge_moves} tagging edge(s)")
    return len(updates), edge_moves


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="Report changes; write nothing")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
