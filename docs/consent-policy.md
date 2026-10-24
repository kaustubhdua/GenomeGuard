# GenomeGuard demo consent policy

**This document describes demo behavior only. It is not a real participant consent form, legal advice, or an authorization to use human genomic data.**

GenomeGuard's public demo uses synthetic donor records and simulated consent attributes. A FHIR R4 `Consent` export is tagged as simulated so downstream systems and reviewers can distinguish it from a real consent record.

## Demo rules

- The demo may evaluate whether a synthetic record's consent attributes match a simulated research purpose.
- The export uses a pseudonymous reference; it must not expose internal donor numbers or identities.
- A simulated withdrawal makes the exported resource inactive in the demo.
- No real participant has consented to GenomeGuard through this demo. Do not use the exported resource to authorize real research, clinical care, or data sharing.
- Before any real deployment, the data controller must provide an approved consent policy, lawful basis, governance process, consent provenance, withdrawal workflow, access controls, and independent legal/ethics review.

## Scope

This policy URI is included in FHIR exports to make the demo's policy reference explicit. It does not turn simulated consent into legally effective consent.