# Contributing

Thanks for helping improve GenomeGuard. Contributions should make the system more correct, reproducible, understandable, and honest about its privacy and security boundaries.

## Development setup

Requirements: Python 3.11 or newer. Docker is optional.

```bash
make setup
make seed
make lint
make test
make eval-smoke
make demo
```

For browser, responsive, and automated accessibility checks, install Playwright and Chromium as described in the CI workflow, then run:

```bash
make ui-smoke
```

Run the full evaluation before changing privacy controls or interpreting benchmark results:

```bash
make eval
```

## Contribution expectations

- Add regression tests for behavior changes, especially authorization, consent policy, privacy-budget accounting, anomaly controls, and audit integrity.
- Keep deterministic policy enforcement separate from model-generated explanations. Agents must not gain write access or authority to loosen policy decisions.
- Preserve visible data provenance. Default demo identities and consent records are simulated even when an optional workflow uses public real-genotype data.
- Document assumptions, limitations, data sources, fixed seeds, and reproducible evaluation steps when changing scientific or privacy claims.
- Do not describe the Beacon-style endpoint as certified/conformant unless the required conformance work has actually been completed.
- Do not commit secrets, downloaded genomic files, sample-level cohorts, or participant identifiers.
- Every published number must come from a rerunnable script with fixed seeds; regenerate `docs/eval-results.md` with `make eval` after changing a defence or attack.
- Keep animations purposeful and respect reduced-motion preferences; test keyboard navigation, mobile layouts, and accessible error states.

## Pull requests

1. Explain the problem and user-visible effect.
2. Include tests or a clear reason a test is not applicable.
3. Run the relevant checks above and link any supporting CI run.
4. State any remaining limitations or unverified behavior.
5. Avoid bundling unrelated formatting or dependency changes with behavioral fixes.

The CI workflow is the authoritative automated gate for the repository. Manual review is still required for deployment behavior, assistive-technology usability, and any security or scientific claims.
