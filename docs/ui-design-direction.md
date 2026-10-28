# GenomeGuard UI design direction

## Intent

GenomeGuard is a research governance workspace, not a marketing landing page. The interface should feel calm, precise, and trustworthy while keeping provenance and limitations visible. The implementation retains the existing vanilla-JavaScript routes and interaction model; this change adds a CSS-only visual layer rather than introducing a new framework.

## Reference influence

The visual direction is informed by the public [NIRDHOOM repository](https://github.com/kaustubhdua/nihdhoom): warm cream surfaces, deep navy text, restrained India-green primary actions, saffron as a small accent, generous spacing, rounded but disciplined surfaces, and reduced-motion support. The theme is independently implemented for GenomeGuard's existing class names. No NIRDHOOM source assets or component code are copied into this stylesheet.

## Design decisions

- **Data-first hierarchy:** requests, decisions, audit verification, and provenance remain the primary content.
- **Truth over decoration:** no added fake KPIs, synthetic activity, fabricated uptime indicator, or decorative chart data.
- **Semantic color:** green means permitted/healthy, saffron means transformed/caution, red means denied/high risk, and navy-blue means escalation/review.
- **Accessible interaction:** visible keyboard focus, responsive layouts, and reduced-motion handling are preserved.
- **Low dependency surface:** CSS-only adaptation; no runtime dependency or third-party asset is introduced.
- **Honest identity:** the hosted research mode continues to disclose that it uses public 1000 Genomes data and dataset-level policy provenance, not participant-specific consent or institutional identity verification.

## Validation

The new stylesheet is linked after the existing base stylesheet so it can override design tokens without rewriting route code. CI must confirm JavaScript syntax, browser smoke routes, responsive behavior, and accessibility checks. A successful CI/build is not a substitute for independent visual inspection of the deployed URL.

## Known boundary

The stylesheet does not resolve database security, persistent storage, identity, consent, production deployment, backup/restore, or independent privacy/security review. These are tracked in the production readiness audit and must not be represented as completed by a visual polish change.
