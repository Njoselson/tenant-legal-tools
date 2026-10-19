# Run record

Throwaway experiment, task 3uimind. Outputs are for the maintainer's markup only; the narratives are invented fixtures.

## Run 1: 2026-10-18

- **Model**: `deepseek-chat` (hardcoded in `DeepSeekClient.chat_completion`), temperature 0
- **System prompt** (from the client): "You are a legal expert assisting with tenant rights and housing law."
- **Context per call**: `prompt.md` with `materials.md` and one narrative substituted in. No retrieval, no graph.
- **Reproduce** (from the repo root, on branch `task/3uimind`; needs `DEEPSEEK_API_KEY` in the environment or in a `.env` file):

```bash
uv run python experiments/habitability/run.py
```

- **Result**: 8 narratives in, 8 files out under `outputs/`, one call each, no retries needed, no prompt changes between runs.

## Layout

- `materials.md`: statutes, code sections, six cases (court, year, holding, source), evidence for breach and for abatement
- `prompt.md`: the one reasoning prompt with its six fixed sections
- `narratives/01-08`: tenant-voice fixtures (clear win, aesthetic only, tenant-caused damage, withholding with no
  documentation, nonpayment with counterclaim, missing evidence, repair-and-deduct, common area plus smoke)
- `outputs/01-08`: raw model output, unedited

## Run 2: 2026-10-18 (corrected materials)

Reading the full opinions (CourtListener via the repo's `CourtListenerClient`, Solow via Cornell LII) found errors in run 1's `materials.md`:

- Solow: the 10% and 1-11% were Civil Court (trial) awards. The Appellate Term cut common-area to 5% and remanded; the Court of Appeals affirmed that and endorsed no percentage. Run 1 said "upheld".
- Park West: a 17-day maintenance/janitorial strike (garbage, rats, health emergency), not doorman/elevator. The 10% was Civil Court's cut to one month's rent, affirmed. The opinion does not discuss tenant notice as an element.
- RPL § 235-b(3): "court need not require expert testimony". Run 1 invented a strike/labor-dispute damages limit.
- RPL § 235-b(1) exception: "misconduct of the tenant ... or persons under his direction or control", not just "under the tenant's control".
- Eastside: 18 N.Y.3d 617 (2012), not 1035. A commercial partial-eviction case (12 sq ft of cross-bracing), not a habitability or code-violation case.
- Jangla: exists and read. Facts and test confirmed; notice about 7 p.m., locksmith called about noon next day, $120 claimed.

- **Model**: `deepseek-chat`, temperature 0; same `prompt.md`, narratives and command as run 1.
- **Fetch opinions**: `uv run python experiments/habitability/fetch_cases.py [slug ...]` (needs `COURTLISTENER_API_TOKEN`; rate-limited, so single slugs retry better). Opinion text is in `opinions/`.
- **Reproduce**: `uv run python experiments/habitability/run.py`
- Run 1 files kept as `materials-v1.md` and `outputs-v1/`; run 2 is `materials.md` and `outputs/`.
