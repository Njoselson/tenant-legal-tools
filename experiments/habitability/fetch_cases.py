"""Fetch the four seminal opinions from CourtListener (read-only) into opinions/.

Run from the repo root:
    uv run python experiments/habitability/fetch_cases.py
"""

import asyncio
import html
import os
import re
import sys
from pathlib import Path

import aiohttp

from tenant_legal_guidance.services.court_listener import CourtListenerClient

HERE = Path(__file__).parent
FALLBACK_ENV = Path.home() / "code" / "tenant_legal_guidance" / ".env"
# (slug, query, citation that picks the right hit)
CASES = [
    ("park-west", '"Park West Management" Mitchell', "47 N.Y.2d 316"),
    ("solow", 'Solow Wellner "warranty of habitability"', "86 N.Y.2d 582"),
    ("eastside", '"Eastside Exhibition" "210 East 86th"', "18 N.Y.3d 617"),
    ("jangla", "Jangla Gravagna", "112 Misc. 2d 642"),
]


def load_token() -> str:
    tok = os.environ.get("COURTLISTENER_API_TOKEN", "")
    if tok:
        return tok
    for env_file in (Path(".env"), FALLBACK_ENV):
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("COURTLISTENER_API_TOKEN="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("COURTLISTENER_API_TOKEN not found")


def strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text))


async def main() -> None:
    cl = CourtListenerClient(api_token=load_token())
    await asyncio.sleep(60)  # earlier burst hit the 429 limit
    for slug, query, cite in [c for c in CASES if len(sys.argv) < 2 or c[0] in sys.argv[1:]]:
        await asyncio.sleep(15)
        hits = await cl.search_opinions(query, max_results=8)
        hit = next((h for h in hits if cite in h["citation"]), None)
        if not hit:
            print(f"{slug}: no hit for {cite}")
            continue
        async with aiohttp.ClientSession(headers=cl.headers, timeout=cl.timeout) as session:
            cluster = await cl._get(session, f"{cl.BASE}/clusters/{hit['cluster_id']}/")
            body = ""
            for op_url in (cluster or {}).get("sub_opinions", []):
                op = await cl._get(session, op_url)
                for field in ("plain_text", "html_with_citations", "html_lawbox", "html_columbia", "html"):
                    if op and op.get(field):
                        body += strip_html(op[field]) + "\n\n"
                        break
        out = HERE / "opinions" / f"{slug}.txt"
        out.write_text(f"{hit['case_name']} | {hit['court']} | {hit['date_filed']} | {hit['citation']}\n{hit['absolute_url']}\n\n{body}")
        print(f"{slug}: {len(body)} chars -> {out.name}")


asyncio.run(main())
