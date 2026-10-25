# Verification evidence

Verification results must be read with their commit SHA and workflow run. A passing workflow is evidence for the checks it actually ran; it is not evidence that a hosted service is live or production-ready.

## Recent automated checks

- [Product/UI cleanup PR #21](https://github.com/kaustubhdua/GenomeGuard/pull/21) passed full CI on PR head `23ea4f7015d306264b44e72663a893683c8d3bdd` in [run #40188338091](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40188338091), including backend tests, lint, evaluation, scripted workflow, JavaScript/Python checks, browser routes, responsive layouts, accessibility checks, guided walkthrough, and screenshot capture. The PR was squash-merged as `32e019e0fb79c47573cead15d5dc5a926c6b61a4`; the merge commit contains the tested tree.
- [Previous main CI run #40186978293](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40186978293) passed on main commit `0f23dc5000a75125ce199fdad16a24d83ed7577e` before the cleanup merge.
- [Earlier full backend and browser suite #40186140229](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40186140229) passed on commit `ce5d85b5c5f3e1ebcf60f5f91bc084d3b05fc841`.
- [1000 Genomes Phase 3 ingestion/evaluation](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40174766665) — 600 samples × 3,000 variants; source hashes and build parameters are recorded.
- [High-coverage family cohort](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40174766759) — 600 samples and 355 observed pedigree relationship pairs; source metadata and simulated-consent status are recorded.
- [HL7 FHIR R4 Consent validation](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378296) — a synthetic Consent export was validated with pinned HL7 FHIR Validator CLI 7.0.1 against R4 4.0.1 and the project's extension definitions.
- [GA4GH Beacon v2 core response-schema validation](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378253) — response envelopes were checked against pinned official schemas; this is not full Beacon certification.
- [Dependency audit and CycloneDX SBOM](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378259) — the resolved Python dependency set passed the pinned pip-audit checks and an SBOM artifact was generated.

## What these checks do not prove

These are automated checks on the cited commits. They do not prove that a public Render instance is live, that real participant consent exists, that Beacon v2 conformance is complete, or that the privacy-budget implementation provides a formal differential-privacy guarantee. The high-coverage workflow validates real genotype/pedigree ingestion and a simulated evaluation; it does not validate clinical outcomes or a real consent-management process.

A public deployment has not been verified in the current repository evidence. Do not publish a live URL or deployed SHA until the actual hosting service has been inspected and the URL passes `make deploy-smoke URL=<actual-url>` and `make live-ui-smoke URL=<actual-url>`. The checked-in Render Blueprint is not proof that a service exists.

See [the threat model](threat-model.md), [evaluation results](eval-results.md), and [the application walkthrough](walkthrough.md) for implementation boundaries and reproduction steps.
