# Verification evidence

- [CI workflow page](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/ci.yml) — representative full run after request-authorization hardening: [run #40176502384](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40176502384) on commit `de5287521161a3ee4b662a6f51f7a43823b14802`, including backend tests, request authorization/review regressions, evaluation, demo, JavaScript/Python checks, Playwright, responsive checks, axe-core, and a desktop/mobile screenshot artifact. Check the workflow page for the newest run.
- [1000 Genomes Phase 3 ingestion/evaluation workflow](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/real-data-validation.yml) — [successful run #40174766665](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40174766665), 600 samples × 3,000 variants.
- [High-coverage family cohort workflow](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/family-data-validation.yml) — [successful run #40174766759](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40174766759), 600 samples and 355 observed pedigree relationship pairs.
- [HL7 FHIR R4 Consent validation](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40173012914) — synthetic Consent export passed the pinned validator.
- [GA4GH Beacon v2 core response-schema validation](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40173357263) — schema-level checks only, not full certification.
- [Dependency audit and CycloneDX SBOM](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40173357246).

Use the workflow pages for the newest results and confirm the run SHA before presenting. These runs prove specific automated gates only. They do not prove that a public Render instance is live, that real consent exists, that Beacon v2 conformance is complete, or that the custom privacy accountant is formally differentially private. The high-coverage run validates pedigree-aware cohort building and simulated attack evaluation, not clinical or consent-management workflows.


For the per-criterion evidence matrix used for the hackathon submission, see [`hackathon/HACKATHON_RELEASE_GATE.md`](hackathon/HACKATHON_RELEASE_GATE.md). A public deployment has not been verified from this repository; list a live URL only after testing it with `make deploy-smoke`.
