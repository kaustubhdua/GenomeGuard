# Supabase-free deployment

GenomeGuard's runtime is the first-party Python/Starlette application. Supabase is not required for local development, API calls, authentication, database access, catalogue discovery, or deployment.

## Runtime request path

- Browser pages call same-origin routes such as `/health`, `/requests`, and `/catalogue/sources`.
- The Starlette API serves the static frontend and implements the policy, risk, transformation, monitoring, and audit workflows.
- Local demo mode uses synthetic data and SQLite.
- Non-demo deployments use the first-party API-key contract and PostgreSQL through `GG_DATABASE_URL`.
- The frontend has no Supabase URL, publishable key, Auth client, Edge Function URL, or remote catalogue client.

## Local development

Requirements: Python 3.11+ and make.

```bash
make setup
make seed
make run
```

Open `http://127.0.0.1:8000`. The local defaults are a synthetic-data demonstration. Do not load private participant data.

## Docker demonstration

```bash
docker compose up --build
```

The Compose profile is explicitly a demo: it enables synthetic personas, uses a local volume, and has a development-only admin-key fallback. Do not expose this profile to the public internet.

## Standalone PostgreSQL deployment\n\nA local PostgreSQL-backed research deployment can be started with Docker Compose. The profile binds the API to loopback by default, waits for PostgreSQL health, and runs the native numbered migrations automatically:\n\n```bash\nexport GG_POSTGRES_PASSWORD=\"$(python -c 'import secrets; print(secrets.token_urlsafe(32))')\nexport GG_MASTER_KEY=\"$(python -c 'import os,base64; print(base64.b64encode(os.urandom(32)).decode())')\nexport GG_ADMIN_API_KEY=\"$(python -c 'import secrets; print(secrets.token_urlsafe(48))')\ndocker compose -f docker-compose.postgres.yml up --build\n```\n\nThis is a self-hosted research deployment profile, not a certification of production readiness. Protect the `.env` file if you use one, do not expose the database port, configure encrypted backups and tested restores, and keep the API behind TLS and a verified identity boundary before any controlled-data use. The public 1000 Genomes policy is dataset-level reuse permission, not individual participant consent.\n\n## Non-demo deployment

Configure all of the following in the server environment (never in frontend variables):

- `GG_DEMO_MODE=false`
- `GG_ALLOW_TAMPER_DEMO=false`
- `GG_DATABASE_URL`: dedicated PostgreSQL URL with least-privilege access to the GenomeGuard runtime schema
- `GG_MASTER_KEY`: base64-encoded 32-byte random key
- `GG_ADMIN_API_KEY`: unique secret of at least 32 characters
- `GG_REAL_COHORT_FILE`: reviewed, provenance-checked cohort artifact
- `GG_DATASET_ID`: unique dataset identifier

The API intentionally fails startup for an unsafe non-demo configuration. A PostgreSQL URL alone is not proof of durable backups, restore capability, or release authorization.

The current first-party authentication mechanism is API keys. Researcher and steward keys authenticate application roles but do not prove institutional affiliation. For institutional use, put the API behind an independently operated OIDC identity provider and enforce verified organization membership server-side. Do not replace this with a browser-side role selector.

## Hosted frontend

The Vercel static frontend rewrites application routes to the configured GenomeGuard Python API. Keep the rewrite pointed at a deployment running this repository's Starlette app. Do not add a second API origin or browser-held server credentials. The Render blueprint is one supported hosting option; any Docker-compatible host can run the same application.

## Historical Supabase artifacts

The `supabase/` directory and the dated Supabase migration reports are retained only as historical records of the abandoned migration attempt. They are not installed, invoked, or required by the current application. Do not apply those SQL migrations to a new deployment. The active source of truth is the Python API and its PostgreSQL store/migrations.

## Verification

Run:

```bash
make setup
make test
make lint
make eval-smoke
make demo
```

CI also checks that browser runtime sources do not import or call Supabase. Live deployment acceptance is a separate check and must be run against the exact deployed commit.
