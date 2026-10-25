# Verification evidence

Read each result together with its workflow run and tested commit. A passing workflow proves only the checks it actually ran; it does not prove production healthcare readiness.

## Main-branch application checks

- [Latest main CI run #40188898749](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40188898749) passed on app commit `8882f9958c664aa6012fe6a1ae0c6ee83dd6bd85`, including backend tests, lint, evaluation, scripted workflow, JavaScript/Python checks, browser routes, responsive layouts, automated accessibility checks, guided walkthrough, and screenshot capture.
- [Product/UI cleanup PR #21](https://github.com/kaustubhdua/GenomeGuard/pull/21) passed full CI on PR head `23ea4f7015d306264b44e72663a893683c8d3bdd` in [run #40188338091](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40188338091) and was squash-merged as `32e019e0fb79c47573cead15d5dc5a926c6b61a4`.
- [1000 Genomes Phase 3 ingestion/evaluation](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40188654628) — 600 samples × 3,000 variants; source hashes and build parameters are recorded.
- [High-coverage family cohort validation](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40188654612) — 600 samples and 355 observed pedigree relationship pairs; source metadata and simulated-consent status are recorded.
- [HL7 FHIR R4 Consent validation](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378296) — a synthetic Consent export was validated with pinned HL7 FHIR Validator CLI 7.0.1 against R4 4.0.1 and the project's extension definitions.
- [GA4GH Beacon v2 core response-schema validation](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378253) — response envelopes were checked against pinned official schemas; this is not full Beacon certification.
- [Dependency audit and CycloneDX SBOM](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378259) — the resolved Python dependency set passed the pinned pip-audit checks and an SBOM artifact was generated.

## Public deployment checks

- Public URL: https://genomeguard.onrender.com
- Render service: `srv-dbev1ka9lscs738813t0`
- Current deployed source commit at the time of the following run: `8882f9958c664aa6012fe6a1ae0c6ee83dd6bd85`
- Latest full live smoke run: [#40192847038](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40192847038) — passed health, static assets, synthetic-data and simulated-consent provenance, API docs, permit/deny/held workflows, requester isolation, invalid/absent credential rejection, steward access, audit verification, all nine routes in light and dark themes, responsive widths, keyboard command-palette navigation, mobile-menu behavior, reduced-motion preference, and 640px reflow.
- Persistence experiment: the synthetic request `3` existed before a manual redeploy of commit `8882f9958c664aa6012fe6a1ae0c6ee83dd6bd85`; after the redeploy, the live API returned 404 for that request. This confirms the current free service did not preserve its SQLite request history. The live run includes the check.

The live axe-core scan found no critical or serious violations. It did report a moderate `heading-order` finding on the Overview and Request details pages in the deployed `8882f995` build. The semantic heading fix is included in [PR #22](https://github.com/kaustubhdua/GenomeGuard/pull/22) and must be verified again after that code is deployed. A successful automated scan is not a substitute for human screen-reader testing.

## Limits and non-claims

All hosted data is synthetic; consent and requester identities are simulated. The current Render free service has no persistent disk, so requests and audit history can reset after restart or deploy. No production persistence, backup/restore, external audit anchoring, multi-instance consistency, or disaster-recovery process has been verified.

The public demo is not for real participant information, private genomic data, clinical decisions, or real consent records. The project has not undergone independent security, privacy, clinical, or legal review. The privacy-budget ledger is simplified accounting, not a formal differential-privacy guarantee; the cryptographic/federated components are educational; and core Beacon response checks are not full Beacon certification.

See [the threat model](threat-model.md), [evaluation results](eval-results.md), [the application walkthrough](walkthrough.md), and [the hosted deployment record](production-deployment.md) for boundaries and reproduction steps.
