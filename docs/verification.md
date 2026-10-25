# Verification evidence

Latest reviewed main SHA: [`24dc4cd61a2f864a4dea281e586ec214236ac2df`](https://github.com/kaustubhdua/GenomeGuard/commit/24dc4cd61a2f864a4dea281e586ec214236ac2df).

- [Full CI workflow](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/ci.yml) — [run #40183378269](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378269) passed backend tests, lint, seeded demo, evaluation, scripted end-to-end demo, JavaScript/Python checks, Playwright routes, responsive layouts, reduced-motion and axe-core WCAG A/AA scans. It preserves desktop/mobile screenshots as a 14-day artifact.
- [1000 Genomes Phase 3 ingestion/evaluation](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40174766665) — 600 samples × 3,000 variants; source hashes/build parameters recorded.
- [High-coverage family cohort](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40174766759) — 600 samples and 355 observed pedigree relationship pairs; source metadata and simulated-consent status recorded.
- [HL7 FHIR R4 Consent validation](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378296) — synthetic Consent export validated with pinned HL7 FHIR Validator CLI 7.0.1 against R4 4.0.1 and project extension definitions.
- [GA4GH Beacon v2 core response-schema validation](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378253) — response envelopes checked against pinned official schemas; this is not full Beacon certification.
- [Dependency audit and CycloneDX SBOM](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378259) — resolved Python dependency set passed pinned pip-audit checks and generated an SBOM artifact.

## What these checks prove—and do not prove

These are automated checks on the cited commits. They do not prove that a public Render instance is live, that real consent exists, that Beacon v2 conformance is complete, or that the custom privacy accountant provides a formal differential-privacy guarantee. The high-coverage workflow validates real genotype/pedigree ingestion and a simulated evaluation; it does not validate clinical outcomes or a real consent-management process.

A public deployment has **not** been verified in this audit. Do not list a live URL or claim a deployed SHA until the actual hosting service is inspected and the URL passes `make deploy-smoke URL=<actual-url>` and `make live-ui-smoke URL=<actual-url>`. The repository's Render Blueprint is not proof that a service exists.

For the per-criterion evidence matrix and the remaining release blockers, see [`hackathon/HACKATHON_RELEASE_GATE.md`](hackathon/HACKATHON_RELEASE_GATE.md), [`hackathon/JUDGE_READINESS_PLAN.md`](hackathon/JUDGE_READINESS_PLAN.md), and [`hackathon/FINAL_JUDGE_RUNBOOK.md`](hackathon/FINAL_JUDGE_RUNBOOK.md).
