# Supabase + Vercel deployment

## Intended topology

- **Vercel:** serves the static files in `frontend/`. The checked-in `frontend/vercel.json` maps `/static/*` to the static frontend files and proxies application/API requests to the existing Render backend.
- **Render:** remains the Python/Starlette backend runtime. It is the only component that receives `GG_DATABASE_URL`, the master encryption key, and the steward key.
- **Supabase project `common 1`:** PostgreSQL persistence for GenomeGuard. Application tables and migrations are isolated in the `genomeguard` schema.
- **Public genotype source:** the backend must continue to use a real, provenance-checked cohort. Supabase is a database, not a substitute for the cohort artifact or source policy.

Do not import the Python backend as a Vercel serverless function in this deployment topology. The app expects a real cohort artifact, has startup/bootstrap work, and uses a persistent PostgreSQL connection and transaction model. The screenshots' Python-entrypoint failure occurs because the whole repository was selected as a Python Vercel project. Configure the Vercel project's **Root Directory** as `frontend` so it deploys the static UI instead.

## Supabase setup status

The selected project is `common 1` (`hkyieaovolkethovyenb`), region `ap-south-1`, PostgreSQL 17. The project had no application tables or recorded migrations at inspection time. The `genomeguard` schema was created and verified; it has no application tables until the backend's versioned migration runs.

The backend's PostgreSQL adapter sets `search_path` to `genomeguard, public` before running migrations. This prevents GenomeGuard's unqualified table names from colliding with unrelated applications in `public`. Do not grant the Supabase `anon` or `authenticated` roles access to this private application schema. The Python backend connects using a server-side database connection string.

## Configure the backend on Render

1. Open the Render service for GenomeGuard.
2. Obtain the connection string for the selected Supabase project from **Supabase → Project Settings → Database → Connection string**. Prefer the Supabase session pooler if the Render deployment cannot use IPv6/direct database connectivity; choose the provider-recommended mode for a long-running server. Require TLS.
3. Add the complete connection string as the Render environment variable `GG_DATABASE_URL`. Do not put this URL in Vercel, browser JavaScript, GitHub, or this document.
4. Keep `GG_MASTER_KEY` and `GG_ADMIN_API_KEY` in Render's secret environment variables. Never reuse the Supabase secret/service-role key as a GenomeGuard API key.
5. Verify `GG_DEMO_MODE=false`, `GG_ALLOW_TAMPER_DEMO=false`, the approved real-cohort file and dataset identifier, and all other mandatory settings. Do not invent participant consent records for the public 1000 Genomes dataset.
6. Deploy the backend. Its PostgreSQL adapter applies the versioned migration in the isolated `genomeguard` schema. Inspect Render logs for migration success; never log the database URL.
7. Verify that all expected tables exist under `genomeguard`, not `public`, and that `/health` works. `/health/ready` must remain fail-closed until the remaining production gates are independently satisfied.
8. Run an approved test request, read it back, restart/redeploy the backend, and verify request, decision, ledger and audit persistence. Use only authorized test identities and non-sensitive test activity.
9. Configure a backup policy and complete a restore drill against a separate, disposable target before claiming durable production operation.

### Connection string safety

Use the connection string copied from the Supabase dashboard; do not guess the database password or construct a URL from the project ID. If the database password is unknown, reset it in the Supabase dashboard and update Render's secret. Never share the password in chat or commit it to GitHub.

## Configure Vercel

1. The Vercel project `genome-guard` (`prj_Q2uhnuLdzXTo4JoZUXqzhW6YuICT`) has been located and its project settings updated to **Root Directory** `frontend`, static/Other framework, no build/install command, and output directory `.`.
2. Vercel SSO protection is now scoped to **preview deployments only**; production deployment URLs are intended to be publicly viewable while previews remain protected. This is suitable only for the existing public research prototype and does not make it safe for private participant data.
3. A GitHub-triggered preview deployment from this branch is now reported `READY`, confirming the linked Vercel build completed after the root-directory/protection settings update. The connected Vercel API denied direct creation of a production deployment, and the preview content could not be independently fetched because Vercel denied this connector access. Production deployment and live route acceptance therefore remain unverified.
4. No build command or API keys are required for the static frontend.
5. Verify that `/` serves the UI, `/static/src/style.css` resolves to the frontend stylesheet, and `/health` and application API paths proxy to Render. Then exercise the full UI in the preview.
6. Promote to production only after API routes, credentials, headers, error states and all core flows pass acceptance tests.

The Vercel configuration deliberately proxies API paths to the Render origin; it does not expose database credentials or Supabase secret keys to the browser. Vercel is not a replacement for the backend's data persistence.

## Acceptance checklist

- [ ] Vercel Root Directory is `frontend`, and the project is configured as static/Other rather than Python.
- [ ] UI HTML, stylesheet, modules and assets load successfully.
- [ ] API calls are proxied to the correct Render backend without browser CORS errors.
- [ ] Render connects to Supabase using TLS and `GG_DATABASE_URL` remains secret.
- [ ] GenomeGuard migrations and all app tables are in `genomeguard`, with no accidental writes to `public`.
- [ ] No browser bundle contains database credentials, Supabase secret keys or the steward key.
- [ ] Approved request/decision/audit records persist across a backend restart and redeploy.
- [ ] Backup and isolated restore drill pass.
- [ ] Security and Supabase advisors are reviewed after migration.
- [ ] Live research acceptance passes against the deployed Vercel URL and Render backend.
- [ ] Readiness remains blocked until institutional identity, consent governance, independent audit anchoring and other release requirements are verified.

## Scope boundary

This integration adds a deployment path and durable database target; it does not by itself establish institutional SSO, participant-specific consent, formal differential privacy, external audit anchoring, clinical suitability, or production certification. Continue to label GenomeGuard as a public-genotype research prototype until the completion audit's blockers are closed with evidence.
