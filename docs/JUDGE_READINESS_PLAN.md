# GenomeGuard — judge-readiness research and execution plan

Last researched: 25 October 2026. This is a prioritized engineering plan, not a claim that each item is already implemented or verified.

## Executive recommendation

Make the demo **trustworthy, repeatable, and easy to judge** before adding more features. The strongest story is: a researcher submits a genomic-data request; deterministic consent/risk policy constrains it; the steward copilot gathers only approved summaries; a human reviews escalations; the released result and decision are auditable. Keep the relative-exposure angle as the differentiator, but do not describe this prototype as a clinical tool or a legally compliant healthcare system.

## P0 — Before the judging session

### 1. Prove the deployed commit and run the demo from a fresh session
- Record the public URL, Render service ID, deployed commit SHA, deploy timestamp, and the health-check result.
- Run `make deploy-smoke URL=<actual-public-url>` against that exact deployment, then manually complete the guided tour on the deployed URL.
- Verify all nine routes, researcher/steward role switching, the donor view, request creation, held-request review, anomaly freeze, audit verification, and the red-team page.
- Test a cold start and an unavailable API. The app must show a useful error/retry state rather than a permanent skeleton.
- Never claim a hosted service is live solely because `render.yaml` exists or a CI-local server passed.

**Hosting caveat:** the checked-in Render Blueprint uses the free plan. Render documents that free web services spin down after 15 minutes without traffic, may take about a minute to wake, and lose local files/database state on spin-down/redeploy/restart. Free services cannot attach persistent disks. For a judging demo, seed only synthetic data immediately before presenting and clearly accept that it resets, or choose an appropriate paid/persistent database setup if persistent history is a requirement. See [Render free instance limitations](https://render.com/docs/free), [persistent disks](https://render.com/docs/disks), and [health checks](https://render.com/docs/health-checks).

### 2. Keep data provenance impossible to misunderstand
- Default to synthetic data; keep a visible provenance label on all relevant pages and exported reports.
- If using 1000 Genomes genotypes, show the source, genome build, sample/variant counts, file SHA-256, build settings, and whether the cohort was family-enriched.
- Consent/requester identities remain simulated even with real genotypes. Never call those real consents.
- Do not commit downloaded VCFs, sample-level genotype files, keys, or participant identifiers.
- Run the optional real-data loader on an internet-enabled machine, save the metadata and command output, and execute `make eval-real COHORT=data_real/1000g_chr22.npz` before presenting any results as a real-data evaluation. The Phase 3 collection has sample/panel files and chromosome-split VCFs, but its unrelated cohort is not sufficient to demonstrate relative exposure; use a documented pedigree/trio source for that specific scenario. [IGSR Phase 3 collection](https://www.internationalgenome.org/data-portal/data-collection/phase3).

### 3. Make the UI judge-ready without motion overload
- Preserve route-level JavaScript code splitting and intent-based prefetching; keep native lazy loading for below-the-fold media, but do not lazy-load critical above-the-fold assets.
- Run the Playwright UI suite on the exact commit. Add an axe-core/Playwright accessibility scan for all routes and interactive states; automated checks are only one part of accessibility review.
- Manually check keyboard-only navigation, visible focus, dialog focus/escape behavior, mobile navigation, 200% zoom/reflow, contrast, reduced motion, and form error announcements.
- Prefer short, purposeful motion that explains state changes. Honour `prefers-reduced-motion`; avoid decorative animation that delays task completion.
- Capture consistent screenshots of overview, request result, steward review, audit proof, and red-team results at desktop and mobile sizes.
- [MDN lazy loading and code splitting](https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/Lazy_loading), [Playwright accessibility testing](https://playwright.dev/docs/accessibility-testing), and [WCAG 2.2](https://www.w3.org/TR/wcag/).

## P1 — Standards and correctness gates

### 4. Validate Beacon against the current GA4GH Beacon v2 schema
The endpoint is currently described as Beacon-v2-style, not certified. Use the current [GA4GH Beacon v2 repository](https://github.com/ga4gh-beacon/beacon-v2) and its OpenAPI/JSON schemas to test successful, no-hit, denied, held, malformed, and count/boolean responses. Validate required fields, version metadata, error behavior, coordinate/reference semantics, and whether returned counts are consistent with privacy transformations. Only call it Beacon v2 conformant after schema-based tests pass; otherwise retain the "Beacon-style" wording.

### 5. Validate FHIR R4 Consent exports externally
- Run every generated Consent resource through the official [HL7 FHIR Validator](https://www.hl7.org/fhir/validator/) with the R4 definitions.
- Keep a golden valid fixture and negative fixtures for missing required fields, invalid status/scope, and invalid provision structure.
- Label exports as simulated/demo-derived and avoid implying that an export is itself a legally binding consent directive. HL7 explicitly distinguishes encoded consent content from the policy and workflow needed to make it legally enforceable. See [FHIR R4 Consent](https://hl7.org/fhir/R4/consent.html).

### 6. Tighten privacy claims and the evaluation evidence
- Current Laplace noise and per-requester epsilon ledger are useful educational mechanisms, but the project documents simplified accounting. Do not claim a formal differential-privacy guarantee until the privacy unit, adjacency, sensitivity, composition, budget reset behavior, and all release paths are specified and independently reviewed.
- Add a comparison experiment for utility and attack success at several privacy budgets and cohort sizes. Report seeds, dataset provenance, confidence/uncertainty, and exact commit SHA.
- Evaluate whether [OpenDP](https://docs.opendp.org/) can replace or independently cross-check the custom noise/accounting implementation. Treat migration as a measured engineering change, not a drop-in guarantee.
- Preserve fail-closed behavior for high-risk and record-level requests. Confirm that errors, retries, and repeated queries cannot bypass consent, anomaly controls, budget accounting, or the audit chain.

## P2 — Production direction (not a hackathon-night patch)

### 7. Replace demo identity and storage assumptions
- Move from public synthetic demo credentials to authenticated identities with explicit researcher, steward, and donor roles.
- Enforce ownership/tenant isolation at every API route and test cross-tenant read/write denial with two independent identities.
- Use managed persistent storage or a supported persistent disk; plan migrations, backups, restore tests, and audit-chain continuity. Do not put real genomic data in the current free/demo configuration.
- Rotate secrets, remove production access to the tamper-demo action, and keep secrets out of browser-visible configuration and logs.

### 8. Independent security and scientific review
- Threat-model re-identification, membership inference, differencing, query probing, insider access, key compromise, audit rewrite, and denial of service.
- Use an audited cryptographic implementation for production homomorphic encryption; the current pure-Python Paillier implementation explicitly is educational and unaudited.
- Commission privacy/scientific review of kinship assumptions, risk calibration, and utility trade-offs. A passing unit test is not a clinical validation or security certification.
- Document retention/deletion, incident response, data-use terms, and the legal review required for any real participant workflow.

## Judge demo flow (about 3 minutes)

1. Start on Overview and state the problem: genomic releases can expose both participants and relatives.
2. Submit the ordinary diabetes frequency request. Show the backend decision, consent exclusions, transformations, and audit record.
3. Submit the record-level or narrow-cohort request and show that it is held/denied rather than silently released.
4. Switch to steward view; show the read-only copilot evidence and human review.
5. Run the probing scenario; show the anomaly monitor freezing the scripted account.
6. Open audit verification and red-team results. State clearly that the data and consent records are synthetic unless the provenance label proves otherwise.

## Final release checklist

- [ ] Main CI green on the exact commit to be shown.
- [ ] Public deployment URL and deployed SHA independently verified.
- [ ] `make deploy-smoke` passes against the public URL.
- [ ] Guided tour completed from a fresh browser session on desktop and phone.
- [ ] No stuck loading states; API/network errors have a clear recovery path.
- [ ] Real-data ingestion and `eval-real` evidence saved if any result is presented as real.
- [ ] Beacon response schema tests and external FHIR R4 validation run, or limitations explicitly stated.
- [ ] Synthetic/real genotype provenance and simulated-consent warnings remain visible.
- [ ] Demo credentials and tamper controls are limited to the synthetic demo.
- [ ] Team rehearsed the demo, understands privacy caveats, and has a backup recording/screenshots.
