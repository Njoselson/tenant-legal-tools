"""
Abstract interface for legal source search services.

This module defines the LegalSearchService abstract base class that all legal source
search implementations must follow (Justia, NYSCEF, NYC Admin Code, etc.).
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Represents a search result from a legal source."""

    url: str
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "url": self.url,
            "title": self.title,
            "metadata": self.metadata,
        }

    def to_manifest_entry(self) -> dict[str, Any]:
        """Convert to manifest entry format."""
        entry = {
            "locator": self.url,
            "kind": "URL",
            "title": self.title,
        }
        # Add metadata fields if present
        if "jurisdiction" in self.metadata:
            entry["jurisdiction"] = self.metadata["jurisdiction"]
        if "authority" in self.metadata:
            entry["authority"] = self.metadata["authority"]
        if "document_type" in self.metadata:
            entry["document_type"] = self.metadata["document_type"]
        if "organization" in self.metadata:
            entry["organization"] = self.metadata["organization"]
        return entry


class LegalSearchService(ABC):
    """Abstract base class for legal source search services.

    All legal source search implementations (Justia, NYSCEF, NYC Admin Code, etc.)
    must inherit from this class and implement the required methods.
    """

    def __init__(self, rate_limit_seconds: float = 2.0):
        """Initialize the search service.

        Args:
            rate_limit_seconds: Delay between requests (default: 2 seconds)
        """
        self.rate_limit = rate_limit_seconds
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def search(
        self,
        query: str | None = None,
        filters: dict[str, Any] | None = None,
        max_results: int = 50,
    ) -> list[SearchResult]:
        """Search for legal documents.

        Args:
            query: Search query string (keywords, case name, etc.)
            filters: Optional filters (jurisdiction, date_range, court, etc.)
            max_results: Maximum number of results to return

        Returns:
            List of SearchResult objects

        Raises:
            Exception: If search fails (network error, parsing error, etc.)
        """
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Get the name of this legal source.

        Returns:
            Source name (e.g., "Justia.com", "NYSCEF", "NYC Admin Code")
        """
        pass

    def _validate_filters(self, filters: dict[str, Any] | None) -> dict[str, Any]:
        """Validate and normalize filter parameters.

        Args:
            filters: Raw filter dictionary

        Returns:
            Validated and normalized filters
        """
        if filters is None:
            return {}
        return filters.copy()

    def _validate_max_results(self, max_results: int) -> int:
        """Validate max_results parameter.

        Args:
            max_results: Requested maximum results

        Returns:
            Validated max_results (clamped to reasonable range)
        """
        if max_results < 1:
            return 1
        if max_results > 1000:
            self.logger.warning(f"max_results {max_results} too large, clamping to 1000")
            return 1000
        return max_results

