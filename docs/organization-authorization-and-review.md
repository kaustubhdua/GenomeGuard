# Institutional organization authorization and consent — implementation status

**Status: not implemented in the active first-party runtime.** This document is a boundary statement and implementation plan, not a description of deployed controls.

## Current runtime contract

The active application is the first-party Python/Starlette API. The browser does not use Supabase Auth, Supabase Edge Functions, PostgREST, or the legacy Supabase organization/consent migrations.

Current credentials are application API keys:
- X-API-Key authenticates a provisioned researcher application role.
- X-Admin-Key authenticates a steward/reviewer application role.
- X-Donor-Key is reserved for the synthetic donor demonstration.
- Demo personas and keys are available only when explicit demo mode is enabled.

These keys do **not** establish a person's real-world identity, institutional affiliation, organization membership, ethics approval, data-access committee approval, or participant consent. A researcher label or institution string supplied to the application is not proof of identity.

## Organization authorization: required future control

Before controlled-access or participant-specific datasets are enabled, an institutional deployment must integrate a trusted identity provider using OIDC (or an institution-approved equivalent). The server must validate issuer, audience, signature, expiry, nonce/state and relevant authentication context; resolve organization membership from a trusted server-side source; and enforce authorization on every protected API route.

Required authorization properties:
- deny by default when identity, organization, role, or policy evidence is missing or ambiguous;
- scope requests, reviews, datasets, exports, and audit views to the authorized organization;
- enforce separation of researcher, reviewer, consent-steward, administrator, and operator duties;
- prevent users from self-assigning roles or choosing trusted organization IDs in browser input;
- support session/key revocation, expiry, credential rotation, MFA policy, and access review;
- test cross-user and cross-tenant denial against the exact deployed release.

GA4GH AAI and Passports are relevant interoperability references; they are not a drop-in substitute for institutional identity proofing or local authorization policy.

## Participant consent: required future control

The current public 1000 Genomes research mode uses a dataset-level public-release policy mapping. Local demo mode uses synthetic consent attributes. Neither is participant-specific consent for GenomeGuard's use case. The active first-party runtime does not currently provide an authoritative participant-consent ledger or a complete consent withdrawal enforcement path.

Before participant-specific data workflows are enabled, the data controller must define and operate:
- an authoritative, access-controlled consent evidence source and provenance chain;
- participant and dataset identity reconciliation that avoids exposing identifiers to researchers;
- permitted purposes, data categories, recipients, jurisdiction, expiry, and policy version;
- withdrawal, expiry, correction, and re-consent lifecycle handling;
- a mandatory decision-time check so withdrawn, expired, missing, or ambiguous consent blocks access and downstream release;
- evidence of the consent source and decision inputs in a privacy-minimizing audit record;
- institutional ethics, legal, privacy, and data-access committee approval.

A FHIR R4 Consent export or a DUO code is an interoperability representation, not proof that consent is valid, current, attributable to a participant, or legally sufficient.

## Review and release separation

A human review workflow must distinguish request review from actual data release. Approval should create a reviewed, time-bounded authorization state; it must not itself expose genotypes. A separate release gate must re-check identity, organization, purpose, dataset terms, participant consent where applicable, expiry/withdrawal, policy version, and output-risk controls at the moment of release.

## GA4GH references

- Data Use Ontology (DUO): https://www.ga4gh.org/product/data-use-ontology-duo/ — standardized machine-readable data-use terms.
- Machine-Readable Consent Guidance: https://www.ga4gh.org/product/machine-readable-consent-guidance-mrcg/ — mapping consent language to DUO.
- GA4GH AAI and Passports: https://www.ga4gh.org/product/authorisation-and-authentication-infrastructure-aai/ and https://www.ga4gh.org/product/passports/ — researcher authorization interoperability.
- GA4GH Data Security Infrastructure Policy: https://github.com/ga4gh/data-security/blob/master/DSIP/DSIP_v4.0.md — access-control, authorization, and minimum-privilege guidance.

## Release rule

Until the identity, organization, consent, withdrawal, and decision-time release controls above are implemented and independently verified, keep the service limited to synthetic demonstrations and reviewed public aggregate/research data under source-specific terms. Do not upload private or controlled-access participant genomic data. Do not describe the current runtime as institutionally authenticated, participant-consent-aware, legally compliant, or production-ready.
