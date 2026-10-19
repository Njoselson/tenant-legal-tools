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
