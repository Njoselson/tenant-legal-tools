"""Throwaway habitability reasoning experiment.

One DeepSeek call per narrative, with materials.md in context. No retrieval, no graph.
Reuses the repo's DeepSeekClient (model hardcoded to deepseek-chat, temperature 0).

Run from the repo root:
    uv run python experiments/habitability/run.py
"""

import asyncio
import os
from pathlib import Path

from tenant_legal_guidance.services.deepseek import DeepSeekClient

HERE = Path(__file__).parent
FALLBACK_ENV = Path.home() / "code" / "tenant_legal_guidance" / ".env"


def load_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    for env_file in (Path(".env"), FALLBACK_ENV):
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("DEEPSEEK_API_KEY not found in env or .env")


async def main() -> None:
    client = DeepSeekClient(load_key(), max_concurrent=4)
    template = (HERE / "prompt.md").read_text()
    materials = (HERE / "materials.md").read_text()
    out_dir = HERE / "outputs"
    out_dir.mkdir(exist_ok=True)

    async def run_one(path: Path) -> None:
        prompt = template.format(materials=materials, narrative=path.read_text().strip())
        answer = await client.chat_completion(prompt)
        (out_dir / path.name).write_text(f"# Output for {path.stem}\n\n{answer}\n")
        print(f"wrote outputs/{path.name}")

    await asyncio.gather(*(run_one(p) for p in sorted((HERE / "narratives").glob("*.md"))))


if __name__ == "__main__":
    asyncio.run(main())
