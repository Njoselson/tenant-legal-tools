"""
ClaimType enum for tenant legal guidance system.

REFERENCE ONLY — these values are NOT used as a validation gate during ingestion.
Claim types are dynamic graph nodes created automatically at ingestion time.
This enum exists only for API display purposes (display_name, description).

Do NOT call ClaimType.from_string() in ingestion code paths — it silently falls
back to OTHER for unrecognized values, which is the root cause of the
SUCCESSION_RIGHTS → OTHER bug that was fixed in M4c.
"""

from enum import Enum


class ClaimType(str, Enum):
    """
    Reference enum of known claim types — used only for API display.
    Ingestion creates claim_type nodes dynamically; this enum is not authoritative.
    """

    # Rent-related claims
    RENT_OVERCHARGE = "RENT_OVERCHARGE"
    RENT_STABILIZATION_VIOLATION = "RENT_STABILIZATION_VIOLATION"

    # Deregulation claims
    DEREGULATION_CHALLENGE = "DEREGULATION_CHALLENGE"
    HIGH_RENT_VACANCY_CHALLENGE = "HIGH_RENT_VACANCY_CHALLENGE"

    # Habitability claims
    HABITABILITY_VIOLATION = "HABITABILITY_VIOLATION"
    HP_ACTION_REPAIRS = "HP_ACTION_REPAIRS"
    BREACH_OF_WARRANTY_OF_HABITABILITY = "BREACH_OF_WARRANTY_OF_HABITABILITY"

    # Landlord misconduct
    HARASSMENT = "HARASSMENT"
    ILLEGAL_LOCKOUT = "ILLEGAL_LOCKOUT"
    RETALIATORY_EVICTION = "RETALIATORY_EVICTION"

    # Security deposit
    SECURITY_DEPOSIT_RETURN = "SECURITY_DEPOSIT_RETURN"
    SECURITY_DEPOSIT_VIOLATION = "SECURITY_DEPOSIT_VIOLATION"

    # Lease violations
    LEASE_VIOLATION = "LEASE_VIOLATION"
    CONSTRUCTIVE_EVICTION = "CONSTRUCTIVE_EVICTION"

    # Discrimination
    HOUSING_DISCRIMINATION = "HOUSING_DISCRIMINATION"

    # Procedural
    IMPROPER_SERVICE = "IMPROPER_SERVICE"
    PROCEDURAL_DEFECT = "PROCEDURAL_DEFECT"

    # Generic/Other
    OTHER = "OTHER"

    @property
    def display_name(self) -> str:
        """Human-readable display name for UI presentation."""
        return self.value.replace("_", " ").title()

    @property
    def description(self) -> str:
        """Brief description of the claim type."""
        descriptions = {
            self.RENT_OVERCHARGE: "Landlord charging more rent than legally allowed",
            self.RENT_STABILIZATION_VIOLATION: "Violation of rent stabilization laws",
            self.DEREGULATION_CHALLENGE: "Challenging improper deregulation of rent-stabilized unit",
            self.HIGH_RENT_VACANCY_CHALLENGE: "Challenging high-rent vacancy decontrol",
            self.HABITABILITY_VIOLATION: "Unit conditions violating habitability standards",
            self.HP_ACTION_REPAIRS: "Housing court action to compel repairs",
            self.BREACH_OF_WARRANTY_OF_HABITABILITY: "Landlord breached implied warranty of habitability",
            self.HARASSMENT: "Landlord harassment of tenant",
            self.ILLEGAL_LOCKOUT: "Landlord illegally locked out tenant",
            self.RETALIATORY_EVICTION: "Eviction in retaliation for tenant exercising rights",
            self.SECURITY_DEPOSIT_RETURN: "Landlord failed to return security deposit",
            self.SECURITY_DEPOSIT_VIOLATION: "Violation of security deposit laws",
            self.LEASE_VIOLATION: "Landlord violated lease terms",
            self.CONSTRUCTIVE_EVICTION: "Conditions so bad tenant forced to leave",
            self.HOUSING_DISCRIMINATION: "Discrimination in housing based on protected class",
            self.IMPROPER_SERVICE: "Defective service of legal papers",
            self.PROCEDURAL_DEFECT: "Procedural defect in legal proceeding",
            self.OTHER: "Other claim type",
        }
        return descriptions.get(self, "")
