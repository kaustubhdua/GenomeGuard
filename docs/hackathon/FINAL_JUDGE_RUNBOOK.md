# GenomeGuard — final judge runbook

**Purpose:** deliver a reproducible, truthful 3-minute demo of the current synthetic-data prototype. This is a demo checklist, not a claim of production healthcare readiness.


## Latest repository evidence (2026-10-25)

The latest full CI and browser/accessibility suite passed on main commit [`ce5d85b5c5f3e1ebcf60f5f91bc084d3b05fc841`](https://github.com/kaustubhdua/GenomeGuard/commit/ce5d85b5c5f3e1ebcf60f5f91bc084d3b05fc841) in [run #40186140229](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40186140229). The run completed setup, lint, backend tests, evaluation smoke/full evaluation, scripted demo, JavaScript syntax checks, Python compilation, Playwright UI smoke, axe-core checks, and screenshot capture. The most recent separate [FHIR R4 validation run #40185627027](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40185627027) passed on commit `c7e73cfb2ba37f7d7c75f229c372f84e4eafa2d1`. [Beacon v2 core response-schema validation #40183378253](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378253) and [dependency audit/SBOM #40183378259](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378259) passed on the PR #14 merge commit `24dc4cd61a2f864a4dea281e586ec214236ac2df`. Real-genotype ingestion and pedigree-aware family-cohort evaluation passed in [Phase 3 run #40174766665](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40174766665) and [family-cohort run #40174766759](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40174766759). These checks ran on different commits; rerun relevant gates after any code change before tagging a release.

**Still a release blocker:** no public Render URL/deployed commit has been verified in this audit. Complete the deployment checklist below only after the Render workspace/service is explicitly selected and the actual URL is known. Do not claim production readiness based on CI alone.

## Go/no-go checklist (complete before the judging slot)

### Release and hosting
- [ ] Record the actual public URL, Render service name/ID, deployed commit SHA, and successful deploy timestamp from the Render dashboard. A `render.yaml` file is not proof of a live deployment.
- [ ] Confirm the deployed commit equals the reviewed GitHub `main` commit.
- [ ] Run `make deploy-smoke URL=<actual-public-url>` from a clean environment. Save the output with the commit SHA and UTC timestamp.
- [ ] Run the read-only deployed-browser smoke: install Playwright/Chromium if needed, then run `python scripts/live_ui_smoke.py --base <actual-public-url>`. It checks all nine routes in light/dark themes, JavaScript/HTTP errors, and 320/375/414 px overflow without submitting requests or changing demo state.
- [ ] Open the URL in a private/incognito browser, wait through any cold start, refresh once, and verify the page recovers normally.
- [ ] Keep the app on the synthetic demo cohort. Do not import or enter real participant data.
- [ ] If the service uses the free Render plan, expect idle spin-down after 15 minutes and a cold start of roughly one minute; local filesystem and SQLite changes are ephemeral. Seed/reset immediately before judging and do not promise durable history.

### Visual and interaction QA
- [ ] Visit Overview, Requests, Decision detail, Family exposure, Anomalies, Audit log, Patient view, Red-team results, and Federated analysis.
- [ ] Repeat in light and dark themes at desktop width and a 375 px mobile viewport.
- [ ] Run the guided tour from a fresh session and confirm every action changes state or produces a backend-derived result.
- [ ] Test keyboard-only navigation: visible focus, sensible tab order, no keyboard traps, working Escape behavior, and no controls reachable only by a pointer.
- [ ] Test 200% browser zoom/reflow, reduced-motion preference, form errors, unavailable API/loading retry, and mobile menu open/close.
- [ ] Check the current CI run and screenshot artifact before recording. Automated axe-core checks are a useful gate, not a substitute for manual assistive-technology review.

### Evidence and claims
- [ ] Save the exact GitHub SHA and links to the successful CI, Phase 3 real-data, family-cohort, FHIR, Beacon schema, and dependency audit workflows.
- [ ] Keep the provenance label visible: the default demo uses synthetic genotypes and simulated consent/requesters; optional 1000 Genomes workflows validate genotype ingestion only.
- [ ] Do not claim legal compliance, clinical readiness, formal differential privacy, audited homomorphic encryption, full Beacon certification, or real participant consent.

## Three-minute demo script

### 0:00–0:25 — Frame the problem

Say: “Genomic data can expose relatives as well as the person in a dataset. GenomeGuard is a governance prototype: agents gather and explain evidence, deterministic rules constrain the decision, and a human steward reviews risky requests. The demo uses synthetic records and simulated consent.”

Show the Overview provenance card before describing any results.

### 0:25–1:05 — Submit a researcher request

Open Requests and submit a permitted aggregate research request. Show the outcome, the policy explanation, the applied protection/transform, and the fact that the released output is aggregate rather than donor-level data.

Say: “The agent explains the decision; it does not override the rules. The output is transformed and subject to a privacy budget.”

### 1:05–1:40 — Show the human-review boundary

Open a held/high-risk request. Switch to the steward view, review the evidence and rationale, and approve or deny it. Show that the final decision is recorded with the reviewer attribution.

Say: “High-risk cases are escalated. The copilot is advisory; it cannot grant itself permission or replace the steward.”

### 1:40–2:15 — Demonstrate attack detection

Open Red-team results and show the differencing/probing scenario, then open Anomalies to show the account freeze and its timeline. Explain that this is a controlled evaluation on the demo cohort, not a universal security guarantee.

### 2:15–2:40 — Prove accountability

Open Audit log, verify the hash chain, and show the tamper-detection demonstration only if it is enabled in the synthetic demo. Do not use tamper controls against any non-demo environment.

### 2:40–3:00 — State the boundary and evidence

Say: “The real-data CI workflows validate ingestion and evaluation on public 1000 Genomes data, including a separate pedigree-aware cohort. Consent and request traffic remain simulated. This is a research prototype, not a clinical system. Our next milestone is live-deployment verification and independent privacy/security review.”

End on the repository and the passing CI/evaluation evidence, not a claim of production compliance.

## Expected result matrix

| Scenario | Expected behavior | Evidence to show |
|---|---|---|
| Permitted low-risk aggregate | Permit or permit-with-transform | Request result and transformation summary |
| Disallowed consent/purpose | Deny before release | Decision reason; no aggregate release |
| High-risk request | Hold/escalate for human review | Steward evidence and reviewer decision |
| Repeated probing | Alert/freeze according to configured thresholds | Red-team results and anomaly timeline |
| Audit integrity | Verify succeeds before tampering; detects a deliberate demo alteration | Audit verification result |
| Unauthenticated request | 401; no protected response | API smoke/tests, not a slide claim |

If an expected outcome differs, stop the demo, reset the synthetic dataset, rerun the scenario, and investigate rather than narrating around a failure.

## Verified automation evidence (check the latest run before presenting)

- Main CI, browser tests, responsive checks, axe-core scans, and screenshot artifact: [GitHub Actions CI](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/ci.yml).
- Real Phase 3 genotype ingestion/evaluation: [Real-data workflow](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/real-data-validation.yml).
- Pedigree-aware family cohort: [Family cohort workflow](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/family-data-validation.yml).
- FHIR R4 structural validation: [FHIR validation workflow](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/fhir-validation.yml).
- Beacon response-schema validation: [Beacon validation workflow](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/beacon-validation.yml).
- Dependency audit and SBOM: [Security audit workflow](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/security-audit.yml).

## External standards and hosting references

- [Render free-instance limitations](https://render.com/docs/free): free web services spin down after 15 idle minutes, can take about a minute to restart, and lose local filesystem changes on restarts/redeploys/spin-down.
- [HL7 FHIR R4 Consent](https://hl7.org/fhir/R4/consent.html): a structured resource supports interoperable consent representation, but enforcement depends on policy and access-control workflows.
- [GA4GH Beacon v2 specification and schemas](https://github.com/ga4gh-beacon/beacon-v2): core schema validation is not the same as full interoperability/conformance certification.
- [NIST SP 800-226](https://csrc.nist.gov/pubs/sp/800/226/final): use a formal privacy analysis before claiming a differential-privacy guarantee.
- [OWASP API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/): use object-level authorization, authentication, resource-consumption controls, and API inventory as the baseline for the next security pass.

## Final release rule

Do not mark the hackathon website “fully verified” until the public URL and deployed SHA are recorded, the read-only deployment smoke passes against that URL, and a human completes the manual walkthrough. Do not mark the platform “production healthcare ready” without real identity/consent governance, durable storage, formal privacy accounting, and independent security/legal review.