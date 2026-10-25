# Verification evidence

Read every result with its exact commit and workflow run. A passing workflow proves only the checks it ran; it does not establish production healthcare readiness.

## Current deployed research instance

- Public URL: https://genomeguard.onrender.com
- Render service: `srv-dbev1ka9lscs738813t0`
- Deployed application commit: `154ee80916e1a45080bc4160902516768afaee15`
- Render deployment: `dep-dbf0ijrrjlhs73951960` (status reported `live`)
- Current mode: non-demo research mode. The image is built from real public 1000 Genomes/IGSR chromosome 22 genotypes; 600 samples and 3,000 variants are loaded.
- Live research-mode checks: [run #40199498444](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40199498444) passed on commit `154ee80916e1a45080bc4160902516768afaee15`.
- Main CI: [run #40199498577](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40199498577) passed on the same commit.
- Real-genotype ingestion/evaluation: [run #40199498450](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40199498450) passed.
- FHIR R4 Consent schema validation: [run #40199498532](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40199498532) passed. This validates an interoperability artifact, not legal consent.
- GA4GH Beacon v2 response-schema validation: [run #40199498557](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40199498557) passed. This is core schema validation, not full Beacon certification.

## What the latest live research-mode run verified

The workflow checked the live `/health` response and provenance; confirmed non-demo mode; verified that the genotype source and policy file have SHA-256 hashes; checked that source-policy coverage matches the loaded sample count; and verified that the public-release policy is disclosed as dataset-level rather than participant-specific consent.

It also verified that `/health/ready` correctly returns HTTP 503 with `ready: false` while durable storage, external audit anchoring, and institutional identity integration remain unverified. Synthetic/demo-only routes were confirmed disabled, unauthenticated request/audit/admin operations were rejected, and the API catalog omitted disabled demo routes.

The same run passed:
- All nine UI routes in light and dark themes, with no observed JavaScript exceptions.
- Narrow viewport checks at 320px, 375px, and 414px without horizontal overflow.
- axe-core checks across all nine routes in both themes, with no critical or serious violations.
- Keyboard Tab navigation, command-palette navigation and Escape behavior.
- Mobile menu open/close behavior, reduced-motion preference, and 640px reflow checks.

Evidence: [live research-mode workflow #40199498444](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40199498444).

## Data and policy provenance: important distinction

The deployed genotype calls come from the public 1000 Genomes/IGSR release. The service uses a versioned, hashed mapping of the source's published public-release terms to a dataset-level, DUO-inspired policy. It does **not** fabricate individual consent records. This policy mapping is not participant-specific consent, is not independently authenticated or legally reviewed, and does not authorize using other datasets or private clinical records.

The live response reported 600 donors, 3,000 variants, a valid local audit chain, and template-based explanations (no live LLM configured). Relative exposure is a kinship model, not direct measurement of every participant's actual genetic sharing.

## Persistence and security boundaries

The Render service is on the free plan and has no configured persistent disk. Its SQLite database path is `/data/genomeguard.sqlite3`; the filesystem is ephemeral. Requests and audit history therefore must not be assumed to survive a restart, redeploy, or instance replacement. The current live research-mode run did not perform a new destructive persistence experiment.

The live smoke test proves that unauthenticated calls are rejected and that demo-only endpoints are disabled. It does not prove institutional identity: the current service uses provisioned API keys, not OIDC/SSO or verified organizational identities. A local hash chain detects accidental or partial edits but is not immutable against an actor who can rewrite the database and recompute the chain. There is no external audit anchor configured.

The `/health/ready` endpoint deliberately remains not-ready until these underlying capabilities are implemented and independently verified. Do not bypass this gate or submit private participant data.

## Earlier synthetic-demo evidence

The previous demo-mode deployment had a separate passing live workflow, [run #40193661761](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40193661761), and a persistence experiment found a pre-redeploy synthetic request missing after redeploy. That result describes the earlier deployment; it is not presented as a new experiment on the current real-public-genotype deployment.

## Research and product limitations

The privacy-budget ledger is simplified accounting, not a formal differential-privacy guarantee. Cryptographic/federated components are educational and not independently audited. The FHIR output is synthetic validation data; core Beacon response checks are not full certification. The public cohort's policy is dataset-level, not individual consent. The application has not undergone independent security, privacy, clinical, legal, or ethics review, and it is not a clinical service.

Human screen-reader testing remains outstanding; automated accessibility checks are not a substitute.

See [the threat model](threat-model.md), [evaluation results](eval-results.md), [real-data evaluation and provenance](real-data.md), [real cohort ingestion and consent requirements](real-cohort-consent.md), and [the hosted deployment record](production-deployment.md) for scope and reproduction details.
