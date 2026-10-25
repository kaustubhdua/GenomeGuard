# Production deployment record

## Current hosted demo

- Public URL: https://genomeguard.onrender.com
- Hosting: Render web service, free plan, Singapore region
- Service: `srv-dbev1ka9lscs738813t0`
- Deployed source commit: `f50f31568e3b664e81f872dea98dc6a81b1bdb43`
- Render deployment: `dep-dbevdtrncjis73aov4og`
- Runtime: Docker, Python 3.12 image, Uvicorn
- Data mode: synthetic cohort; consent and requester personas are simulated
- Destructive audit-tampering demonstration: disabled in the hosted service environment
- Secrets: a generated master key and admin key are configured as Render environment variables; never copy them into repository files, screenshots, or issue comments.

The image build and Render deployment completed successfully. The latest deployed build is `dep-dbevdtrncjis73aov4og`, running app commit `f50f31568e3b664e81f872dea98dc6a81b1bdb43`. Render logs record Uvicorn startup completion and HTTP 200 for the root page. See the [Render service dashboard](https://dashboard.render.com/web/srv-dbev1ka9lscs738813t0) for current state.

## Verification

The main branch's [CI run on the deployed commit](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40193504185) passed the local backend, evaluation, browser, responsive, and automated accessibility checks.

A separate [live deployment smoke workflow](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/live-deployment-smoke.yml) checks the public health endpoint, static assets, provenance labels, API documentation, all nine UI routes in light and dark themes, responsive overflow, keyboard navigation, reduced motion, 640px reflow, and axe-core findings. It exercises live request governance and authorization using synthetic demo personas. [Run #40193661761](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40193661761) passed these checks on app commit `f50f31568e3b664e81f872dea98dc6a81b1bdb43`. The axe-core scan found no critical/serious violations or heading-order findings on any of the nine routes in either theme.

## Persistence and operational limitations

This deployment uses Render's free web-service plan and does not have a configured persistent disk. The application database path is `/data/genomeguard.sqlite3`, but the container filesystem is ephemeral. **Do not rely on requests, consent changes, or audit history surviving a restart, redeploy, or instance replacement.** A restart may reseed a fresh synthetic dataset and reset the local audit chain.

No production persistence guarantee, backup/restore process, external audit anchoring, multi-instance consistency, or disaster-recovery procedure has been verified. Do not store real participant information, private genomic data, or real consent records in this demo. The application is research software, not a clinical or production healthcare service.

The service configuration currently does not expose a platform-level `/health` health-check path; the endpoint is tested by the smoke workflow, but Render's own health-check configuration should be set to `/health` if the service settings permit it.

## Reproduce live checks

From a local clone with Python 3.11+, the project dependencies, and Playwright Chromium installed:

```bash
python scripts/deploy_smoke.py --base https://genomeguard.onrender.com
python scripts/live_api_smoke.py --base https://genomeguard.onrender.com
python scripts/live_ui_smoke.py --base https://genomeguard.onrender.com
npm install --prefix /tmp/gg-axe --no-save --package-lock=false axe-core@4.14.0
AXE_CORE_PATH=/tmp/gg-axe/node_modules/axe-core/axe.min.js python scripts/live_accessibility_smoke.py --base https://genomeguard.onrender.com
```

The API acceptance script creates three synthetic request records (permitted, denied, and held) and adds corresponding audit events. It does not change consent, freeze accounts, or tamper with audit history. Use it only against the synthetic demo. The UI smoke script is read-only and visits each of the nine routes in light and dark themes plus narrow mobile widths.

## Release status

A successful container build and a Render `live` status prove deployment, not product completeness. Before treating this as production-ready, the project would still need durable database storage, a real identity and consent architecture, independent security/privacy review, external audit anchoring, operational monitoring, backup/restore testing, and human accessibility review with assistive technology.
