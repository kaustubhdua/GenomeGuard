# Tech Eximius Track 2 — release gate and completion audit

Last updated: 25 October 2026. This document separates automated evidence from work that still requires a real hosting account, external dataset access, or independent review.

## Latest verified repository baseline

The latest full code-and-browser verification passed on main commit `24dc4cd61a2f864a4dea281e586ec214236ac2df`: GitHub Actions run [#40183378269](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378269) passed setup, lint, seed, Python tests, evaluation smoke/full evaluation, scripted demo, JavaScript syntax checks, Python compilation, Playwright browser smoke, and pinned axe-core checks. It preserved judge-facing desktop/mobile screenshots as a 14-day CI artifact. The same commit passed the [GA4GH Beacon v2 schema workflow](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378253), [dependency vulnerability audit](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378259), and [FHIR R4 validator](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40183378296). Rerun all relevant workflows on the final submission SHA before tagging a release.

The UI/performance changes split page modules by route, prefetch chunks on link hover/focus, add reduced-motion-aware motion, expose route loading with `aria-busy`, recover from failed route imports, and apply native lazy loading/async decoding. The suite checks nine routes, light/dark themes, the guided tour, responsive overflow at 320/375/414 px, blocked localStorage, and critical/serious axe-core findings. The first axe run exposed contrast, SVG naming, and keyboard-scroll issues; fixes are merged and the updated suite passed.

The real-data path passed end-to-end on hosted GitHub Actions on `main`: [Phase 3 run #40174766665](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40174766665) built 600 samples × 3,000 variants and completed `eval-real`; [high-coverage family run #40174766759](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40174766759) verified 355 pedigree relationship pairs and completed `eval-real`. Source hashes and build parameters are recorded in [real-data.md](../real-data.md). The Phase 3 cohort has zero relative pairs by design; consent and query traffic remain simulated.

The FHIR R4 Consent export has passed the HL7 FHIR Validator 7.0.1 against R4 4.0.1 and the project's extension package: [run #40145035362](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40145035362) reported 0 errors and 0 warnings. The validator checks a generated synthetic Consent resource; it does not prove that consent is legally valid. Full Beacon v2 conformance beyond core response schemas, formal differential-privacy accounting, a public deployment URL, persistent hosting, real authenticated tenant isolation, and independent production security/privacy review remain open. Core response envelopes are checked against pinned official GA4GH Beacon v2 schemas in [run #40145035388](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40145035388); this is not full Beacon certification.

For the research-backed next steps, see [JUDGE_READINESS_PLAN.md](JUDGE_READINESS_PLAN.md); the practical three-minute demo script and go/no-go checklist are in [FINAL_JUDGE_RUNBOOK.md](FINAL_JUDGE_RUNBOOK.md).

## Product framing

**GenomeGuard** is a healthcare data-governance decision-support prototype. It evaluates research requests against consent-like rules, estimates disclosure risk, applies transformations, monitors suspicious query patterns, and records decisions in a tamper-evident audit chain. Its strongest differentiator is making *relative exposure* visible alongside the usual individual-level privacy risk.

The central claim for judges should be: **“Agents investigate and explain; deterministic policy code enforces the decision; a human retains authority over escalations.”** Do not claim that an LLM independently authorizes genomic data access.

## Criteria-to-evidence matrix

| Judging criterion | Evidence in repository | Remaining proof before submission |
|---|---|---|
| Innovation and creativity | Consent-aware governance, relative-exposure model, privacy/utility evaluation, Beacon-style endpoint, auditable decision trail | Demonstrate one coherent end-to-end story; explain what is novel relative to existing consent-management and genomic privacy tools |
| Relevance to Track 2 | Request triage, steward copilot, consent summaries, donor-facing portal and withdrawal flow | Show that each UI action changes backend state or returns a backend-derived result; distinguish governance simulation from clinical decision-making |
| Technical implementation | Python/Starlette API, encryption helpers, audit chain, DP-style noise and budget ledger, anomaly rules, agent tool loop, red-team harness | Run clean-clone setup, tests, lint, full evaluation and demo; inspect current CI result and retain logs |
| UI/UX and presentation | Multi-page UI, route code splitting, motion preferences, guided tour, read-only deployed-site smoke, responsive suite, pinned axe-core WCAG A/AA scan, screenshot artifacts | Automated axe/Playwright checks pass; manual keyboard, screen-reader, 200% zoom/reflow and user testing remain |
| Real-world impact | Addresses genomic privacy, consent restrictions, relatives' exposure, and accountable access | Use carefully sourced background claims; make clear this is not a clinical product and has not been independently security- or legally reviewed |
| Scalability and feasibility | Benchmark harness and scalability notes; SQLite-based single-process deployment | Re-run benchmark locally; describe single-process/SQLite limits and what changes for concurrent multi-site production |
| Team presentation and communication | Three-minute demo script and docs | Team must record and watch the final video, prepare a maximum-six-slide deck, add working repo/prototype/video links, and rehearse judge questions |

## Provenance policy — do not weaken this for the pitch

The default demo cohort is synthetic. Consent records and requester identities are simulated even if optional real 1000 Genomes genotypes are loaded. A real genotype file does **not** make its consent record real, does not make the platform production-ready, and does not establish legal compliance. Keep provenance visible in the UI, README, demo narration and result metadata.

Both the Phase 3 and high-coverage family loaders have passed end-to-end CI against public files, with source hashes, source filenames, build parameters, sample/variant counts and relationship counts recorded in `docs/real-data.md`. The latest main-branch CI is green; this does not imply a public Render service is live. This verifies ingestion and evaluation only; it does not turn simulated consent or requester identities into real ones. Never commit downloaded genomic data or real participant identifiers to this repository.

## Commands to run on a clean clone

Use Python 3.11+ and run these in order:

    make setup
    make seed
    make lint
    make test
    make eval
    make demo

Optional additional checks:

    make bench
    # Requires Playwright and a Chromium browser:
    python -m pip install playwright
    python -m playwright install chromium
    make ui-smoke
    # Read-only browser check for an already deployed service (all routes, themes, phone widths):
    make live-ui-smoke URL=https://your-service.onrender.com

Real-data experiments are optional and require separately downloaded inputs:

    make fetch-real
    # or, for a family-enriched cohort, after reviewing the upstream release terms:
    make real-trios VCF=path/to/chr22.vcf.gz PED=path/to/pedigree.txt
    make eval-real COHORT=data_real/1000g_trios.npz

Do not quote performance or evaluation figures from a different commit, dataset, seed, or machine. Save the command output and keep the generated results in sync with the code that produced them.

## Deployment gate

Before calling the prototype “deployed and working”:

- [ ] Confirm the public URL loads from a fresh browser session and from a phone network.
- [ ] Run `make deploy-smoke URL=https://your-service.onrender.com`; it checks the landing page, static assets, health/audit status, synthetic-data provenance, demo account availability and core API documentation without mutating state or printing keys.
- [ ] Run `make live-ui-smoke URL=https://your-service.onrender.com`; it visits all nine routes in light/dark themes, checks JavaScript/HTTP errors and checks 320/375/414 px overview layouts without changing demo state. Request-detail routes report a documented empty state if the instance has no requests yet.
- [ ] Exercise the full guided tour on a resettable synthetic demo/staging instance; it submits requests and changes demo state, so do not run it against a judge session you need to preserve.
- [ ] Confirm /health reports the expected data provenance and a valid audit chain.
- [ ] Verify that API errors, reloads, and a cold start do not leave the UI stuck.
- [ ] Confirm whether the host provides persistent storage. Without it, SQLite state and the audit history may reset on restart or redeploy; disclose that limitation.
- [ ] Set a strong random master key and admin key through the host's secret manager. Never commit them.
- [ ] Keep demo mode and the tamper button restricted to the synthetic demo. Do not use published demo credentials with real participant data.
- [ ] Record the deployed commit SHA, deployment timestamp, and test results.
- [ ] Copy the final audit head hash into an external record after the demo setup is complete. The hash chain detects edits; it does not prevent a privileged actor from rewriting and re-hashing the whole log.

## Security and scientific caveats to disclose

- This is a hackathon prototype, not a clinical decision system, not legal advice, and not certified compliant with DPDP, GDPR, HIPAA or GA4GH.
- Differential-privacy budget accounting is simplified; it must not be presented as a formally audited privacy guarantee.
- Paillier and federated examples are educational prototypes and need independent cryptographic/security review before production use.
- The attack harness is designed by the same project team as the defences and uses simplified scenarios. Results show behaviour under those scenarios, not a proof of privacy.
- The synthetic kinship model uses expected-average sharing; it is not a prediction for a real family or biobank.
- Real consent withdrawal, identity verification, steward authorization, retention/deletion policy, key management and external audit anchoring need production-grade integrations and review.

## Final sign-off checklist

- [ ] All checks above pass on the exact submission commit.
- [ ] No secrets, downloaded genomes, personal data, or stale runtime database are committed.
- [ ] README statements match the current implementation and current generated evaluation files.
- [ ] A judge can complete the demo without an LLM API key or external data download.
- [ ] The team can explain the consent engine, risk model, transformation ladder, anomaly guard, agent boundary, audit limitations, and each reported metric.
- [ ] The working prototype URL and demo video are public and tested.
- [ ] Slides are within the event's stated limit and all required links are on slide 1.

**Status rule:** until the clean-clone commands and deployed walkthrough have actually been run on the final commit, describe the project as “feature-built; final release verification pending,” not “fully production-ready.”
