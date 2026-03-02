"""
ClaimType enum for tenant legal guidance system.

Provides validated, enumerated claim types for legal claims with fuzzy matching
to handle inconsistent string representations in existing data.
"""

from enum import Enum


class ClaimType(str, Enum):
    """
    Enumerated claim types for the tenant legal guidance system.

    Each claim type represents a specific legal cause of action that a tenant
    can pursue. The enum values are UPPERCASE_SNAKE_CASE for consistency with
    existing database storage.
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

    @classmethod
    def from_string(cls, value: str | None) -> "ClaimType":
        """
        Convert string to ClaimType with fuzzy matching.

        Handles case insensitivity, underscores/spaces/hyphens, and common
        abbreviations. Falls back to OTHER for unrecognized values.

        Args:
            value: String representation of claim type (case-insensitive)

        Returns:
            Matching ClaimType enum value, or OTHER if no match found
        """
        if not value:
            return cls.OTHER

        # Normalize: uppercase, replace separators with underscores
        normalized = value.upper().replace(" ", "_").replace("-", "_")

        # Direct match by value
        try:
            return cls(normalized)
        except ValueError:
            pass

        # Try by name
        try:
            return cls[normalized]
        except KeyError:
            pass

        # Fuzzy matching for common variations and abbreviations
        fuzzy_map = {
            # Deregulation variations
            "DEREG": cls.DEREGULATION_CHALLENGE,
            "DEREGULATED": cls.DEREGULATION_CHALLENGE,
            "DECONTROL": cls.DEREGULATION_CHALLENGE,
            "VACANCY_DECONTROL": cls.DEREGULATION_CHALLENGE,
            "HIGH_RENT_VACANCY": cls.HIGH_RENT_VACANCY_CHALLENGE,
            "HRV": cls.HIGH_RENT_VACANCY_CHALLENGE,
            # Rent overcharge variations
            "OVERCHARGE": cls.RENT_OVERCHARGE,
            "RENT_OVER": cls.RENT_OVERCHARGE,
            "ILLEGAL_RENT": cls.RENT_OVERCHARGE,
            # Habitability variations
            "HP_ACTION": cls.HP_ACTION_REPAIRS,
            "HP": cls.HP_ACTION_REPAIRS,
            "REPAIRS": cls.HP_ACTION_REPAIRS,
            "HABITABILITY": cls.HABITABILITY_VIOLATION,
            "WARRANTY_OF_HABITABILITY": cls.BREACH_OF_WARRANTY_OF_HABITABILITY,
            "UNINHABITABLE": cls.HABITABILITY_VIOLATION,
            # Harassment variations
            "HARASS": cls.HARASSMENT,
            "INTIMIDATION": cls.HARASSMENT,
            # Lockout variations
            "LOCKOUT": cls.ILLEGAL_LOCKOUT,
            "ILLEGAL_LOCK": cls.ILLEGAL_LOCKOUT,
            # Security deposit variations
            "DEPOSIT": cls.SECURITY_DEPOSIT_RETURN,
            "SECURITY": cls.SECURITY_DEPOSIT_RETURN,
            # Eviction variations
            "RETALIATION": cls.RETALIATORY_EVICTION,
            "RETALIATORY": cls.RETALIATORY_EVICTION,
            "CONSTRUCTIVE": cls.CONSTRUCTIVE_EVICTION,
            # Discrimination variations
            "DISCRIMINATION": cls.HOUSING_DISCRIMINATION,
            "FAIR_HOUSING": cls.HOUSING_DISCRIMINATION,
        }

        # Check for fuzzy matches (partial matching)
        for key, claim_type in fuzzy_map.items():
            if key in normalized or normalized in key:
                return claim_type

        return cls.OTHER

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


# Convenience groupings for filtering
RENT_RELATED_CLAIMS = frozenset({
    ClaimType.RENT_OVERCHARGE,
    ClaimType.RENT_STABILIZATION_VIOLATION,
    ClaimType.DEREGULATION_CHALLENGE,
    ClaimType.HIGH_RENT_VACANCY_CHALLENGE,
})

HABITABILITY_CLAIMS = frozenset({
    ClaimType.HABITABILITY_VIOLATION,
    ClaimType.HP_ACTION_REPAIRS,
    ClaimType.BREACH_OF_WARRANTY_OF_HABITABILITY,
})

LANDLORD_MISCONDUCT_CLAIMS = frozenset({
    ClaimType.HARASSMENT,
    ClaimType.ILLEGAL_LOCKOUT,
    ClaimType.RETALIATORY_EVICTION,
})
