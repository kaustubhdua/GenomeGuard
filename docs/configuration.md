# Configuration

All settings are environment variables with the prefix `GG_` (see `backend/app/config.py`;
privacy and anomaly thresholds live in `backend/app/core/params.py` and are overridable the same
way).

| Variable | Default | Meaning |
|---|---|---|
| `GG_DB_PATH` | `./genomeguard.sqlite3` | SQLite file (a fresh file is seeded on first start) |
| `GG_DATABASE_URL` | unset | PostgreSQL URL; required when `GG_DEMO_MODE=false`. Non-demo startup refuses to fall back to SQLite. Keep it server-side only. |
| `GG_DEMO_MODE` | `true` | Publish demo accounts and keys at `/demo/requesters`. Turn off for anything else |
| `GG_ALLOW_TAMPER_DEMO` | `false` | Enable the audit tamper exercise (demo only) |
| `GG_ADMIN_API_KEY` | `demo-admin-key` | Steward key. Outside demo mode it must be 32+ characters |
| `GG_MASTER_KEY` | unset: a fixed, publicly known development key, with a warning | base64 of 32 random bytes; encrypts the genotype matrix at rest |
| `GG_REAL_COHORT_FILE` | empty | Path to a cohort `.npz` built by `make fetch-real` or `make real-trios` |
| `GG_EVAL_JSON` | `docs/eval-results.json` | Evaluation file shown on the Red-team page |
| `GG_N_DONORS`, `GG_N_VARIANTS`, `GG_N_FAMILIES`, `GG_SEED` | 600, 3000, 120, 1337 | Synthetic cohort shape |
| `ANTHROPIC_API_KEY` | unset | Optional. Agents write explanations with a model; without it templates are used |
| `GG_LLM_MODEL` | `claude-sonnet-5-5` | Model used when a key is set |
| `PORT` | 8000 | Used by the Docker image |

Generate a master key: `python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"`.
