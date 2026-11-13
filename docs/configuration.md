# Configuration

GenomeGuard runs agent explanations and the steward copilot entirely offline using deterministic templates and a built-in rules planner. It does not call OpenAI, Anthropic, Google, or any hosted AI endpoint and requires no AI API key.

All settings are environment variables with the prefix `GG_` (see `backend/app/config.py`;
privacy and anomaly thresholds live in `backend/app/core/params.py` and are overridable the same
way).

| Variable | Default | Meaning |
|---|---|---|
| `GG_DB_PATH` | `./genomeguard.sqlite3` | SQLite file (a fresh file is seeded on first start) |
| `GG_DATABASE_URL` | unset | PostgreSQL URL; required when `GG_DEMO_MODE=false`. Non-demo startup refuses to fall back to SQLite. Keep it server-side only. |
| `GG_DEMO_MODE` | `true` | Publish synthetic persona metadata and issue short-lived, process-local demo sessions. No API or donor keys are returned by public persona endpoints. Turn off for anything else |
| `GG_ALLOW_TAMPER_DEMO` | `false` | Enable the audit tamper exercise (demo only) |
| `GG_ADMIN_API_KEY` | process-random in demo mode when unset | Steward key. Set a unique secret explicitly for any deployment that enables steward operations; outside demo mode it must be 32+ characters |
| `GG_MASTER_KEY` | unset: a fixed, publicly known development key, with a warning | base64 of 32 random bytes; encrypts the genotype matrix at rest |
| `GG_REAL_COHORT_FILE` | empty | Path to a cohort `.npz` built by `make fetch-real` or `make real-trios` |
| `GG_EVAL_JSON` | `docs/eval-results.json` | Evaluation file shown on the Red-team page |
| `GG_N_DONORS`, `GG_N_VARIANTS`, `GG_N_FAMILIES`, `GG_SEED` | 600, 3000, 120, 1337 | Synthetic cohort shape |
| `PORT` | 8000 | Used by the Docker image |

Generate a master key: `python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"`.


## Public synthetic demo sessions

In demo mode, GET /demo/requesters and GET /demo/donors return persona metadata only. They do not disclose requester API keys, donor keys or administrator credentials.

The browser obtains a short-lived (30-minute) requester session using POST /demo/session with a requester_id, and a donor session using POST /demo/donor-session with a donor_id. Tokens are held in tab memory and sent in X-Demo-Session or X-Demo-Donor-Session headers. They are scoped to one synthetic persona, expire after 30 minutes, and are capped at five active sessions per persona.

The session registry is in process memory. It is suitable only for the current single-process synthetic demo. Multi-worker or multi-instance deployments must replace it with a shared, expiring server-side session store before scaling. Static demo API keys are disabled by default. The test-only GG_TEST_ALLOW_STATIC_DEMO_KEYS flag must never be set on a hosted deployment.
