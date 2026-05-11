"""
CourtListener API client for fetching NY court opinions.

Free REST API by the Free Law Project (courtlistener.com).
Register for a free token at: https://www.courtlistener.com/register/
Add to .env: COURTLISTENER_API_TOKEN=your_token_here

API docs: https://www.courtlistener.com/help/api/rest/
Rate limits: 5,000 requests/hour for authenticated users.
"""

import asyncio
import logging
import os
from typing import Any

import aiohttp
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.courtlistener.com/api/rest/v4/search/"

# Seconds between requests — keeps us comfortably under 5000/hr (= ~1.4/s)
_REQUEST_DELAY = 1.0
# Max retries on 429/403 before giving up on a request
_MAX_RETRIES = 3


class CourtListenerClient:
    """Client for the CourtListener REST API v4."""

    BASE = "https://www.courtlistener.com/api/rest/v4"

    def __init__(self, api_token: str | None = None):
        token = api_token or os.getenv("COURTLISTENER_API_TOKEN")
        if not token:
            raise ValueError(
                "CourtListener API token required. "
                "Register free at courtlistener.com/register/ "
                "and set COURTLISTENER_API_TOKEN in .env"
            )
        self.headers = {
            "Authorization": f"Token {token}",
            "Accept": "application/json",
        }
        self.timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)

    async def _get(
        self,
        session: aiohttp.ClientSession,
        url: str,
        params: list[tuple[str, str]] | None = None,
    ) -> dict[str, Any] | None:
        """
        Single GET with retry on 429/403 (max _MAX_RETRIES attempts).
        Returns parsed JSON or None on unrecoverable failure.
        """
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 401:
                        raise ValueError(
                            "CourtListener token rejected (401). "
                            "Check COURTLISTENER_API_TOKEN in .env"
                        )
                    if resp.status in (429, 403):
                        wait = _REQUEST_DELAY * (2 ** attempt)  # 2s, 4s, 8s
                        logger.warning(
                            f"CourtListener rate limit ({resp.status}) — "
                            f"attempt {attempt}/{_MAX_RETRIES}, waiting {wait:.0f}s"
                        )
                        if attempt == _MAX_RETRIES:
                            logger.error("Max retries hit — skipping this request")
                            return None
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    return await resp.json()

            except aiohttp.ClientError as e:
                logger.error(f"CourtListener request error: {e}")
                return None

        return None

    async def search_opinions(
        self,
        query: str,
        courts: list[str] | None = None,
        date_after: str | None = None,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search opinions via CourtListener v4 search API.

        Args:
            query: Full-text search query (e.g. "rent stabilization overcharge")
            courts: CourtListener court IDs to filter by. None = all courts.
            date_after: Only opinions filed after this date ("YYYY-MM-DD").
            max_results: Maximum number of results to return.

        Returns:
            List of opinion dicts: id, absolute_url, case_name, court,
            date_filed, citation, snippet.
        """
        params: list[tuple[str, str]] = [
            ("q", query),
            ("type", "o"),              # opinions
            ("order_by", "score desc"),
        ]

        if date_after:
            params.append(("filed_after", date_after))

        if courts:
            for court_id in courts:
                params.append(("court", court_id))

        results: list[dict[str, Any]] = []
        next_url: str | None = _SEARCH_URL
        first = True

        async with aiohttp.ClientSession(headers=self.headers, timeout=self.timeout) as session:
            while next_url and len(results) < max_results:
                data = await self._get(
                    session,
                    next_url,
                    params=params if first else None,
                )
                first = False

                if data is None:
                    break

                for hit in data.get("results", []):
                    if len(results) >= max_results:
                        break
                    results.append({
                        "id": hit.get("id"),
                        "absolute_url": hit.get("absolute_url", ""),
                        "case_name": hit.get("caseName") or hit.get("case_name", ""),
                        "court": hit.get("court", ""),
                        "court_id": hit.get("court_id", ""),
                        "date_filed": hit.get("dateFiled") or hit.get("date_filed", ""),
                        "citation": hit.get("citation", []),
                        "cluster_id": hit.get("cluster_id"),
                        "snippet": hit.get("snippet", ""),
                    })

                next_url = data.get("next") if len(results) < max_results else None

                # Pace requests — stay well under 5000/hr authenticated limit
                if next_url:
                    await asyncio.sleep(_REQUEST_DELAY)

        logger.info(f"CourtListener search '{query}': found {len(results)} opinions")
        return results

    async def get_opinion(self, opinion_id: int) -> dict[str, Any] | None:
        """Fetch a single opinion by ID. Returns full JSON including plain_text."""
        url = f"{self.BASE}/opinions/{opinion_id}/"
        async with aiohttp.ClientSession(headers=self.headers, timeout=self.timeout) as session:
            return await self._get(session, url)
