# Contributing

```
make setup          # virtualenv + dev dependencies
make lint test      # ruff and the backend test suite
make eval-smoke     # quick red-team evaluation
make demo           # scripted scenario against a throwaway server
make ui-smoke       # headless-browser checks (needs Playwright and Chromium)
```

Guidelines:

- **The decision stays deterministic.** Agents may explain and advise; they never see genotypes,
  donor ids or free text, and never decide. A change that lets model output relax a rule will be
  rejected. The canary tests in `backend/tests/test_agents.py` and `test_copilot.py` enforce this.
- **Every published number comes from a rerunnable script with fixed seeds.** If you change a
  defence or an attack, regenerate `docs/eval-results.md` with `make eval` and commit it.
- **Label provenance honestly.** A dataset counts as real only if the cohort file's metadata says
  so. Consent and requesters are simulated and must stay labelled.
- **Do not claim legal compliance.** Say "designed around the ideas of".
- Add a test with every behaviour change. The frontend has no build step: plain ES modules in
  `frontend/src`, checked by `make ui-smoke` (contrast, accessibility, phone widths).
- Never commit downloaded genomic files; `data_real/` is ignored on purpose.
