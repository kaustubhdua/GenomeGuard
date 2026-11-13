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

## Machine-readable DUO mapping

The implementation maps the standard permission/modifier terms to the official DUO identifiers:

| Code | DUO identifier | Meaning |
|---|---|---|
| GRU | DUO:0000042 | General research use |
| HMB | DUO:0000006 | Health/medical/biomedical research |
| DS | DUO:0000007 | Disease-specific research; pair the disease restriction with a disease ontology identifier |
| POA | DUO:0000011 | Population origins or ancestry research only |
| NPU | DUO:0000045 | Not-for-profit organisation use only |
| NPUNCU | DUO:0000018 | Not-for-profit and non-commercial use only |
| NCU | DUO:0000046 | Non-commercial use only |
| NMDS | DUO:0000015 | No general methods research |
| NPOA | DUO:0000044 | Population origins or ancestry research prohibited |

`NAGR` (no aggregate-level general research) and `NCTRL` (no use as a control set)
are GenomeGuard-specific policy extensions. They are **not** DUO terms and must
not be serialized or presented as official DUO identifiers. They require an
institution-approved mapping or extension governance process before cross-system
interoperability can claim equivalence. The standard `NPOA` modifier is mapped to
DUO:0000044 and blocks the `population_genetics` and `ancestry_research` purposes.

DUO describes permitted data uses; it does not itself prove participant consent,
researcher identity, institutional authority, or access authorization. GenomeGuard
must retain its separate consent provenance and policy-enforcement controls.


## Commercial-use and organisation-type verification

`NCU` and `NPU` are distinct restrictions and must not be collapsed:

- `NCU` (DUO:0000046) requires a verified non-commercial-use classification for the specific research activity. An applicant's self-declared `is_commercial=false` value is not sufficient evidence.
- `NPU` (DUO:0000045) requires the requesting organisation itself to have a verified not-for-profit status. It is not equivalent to a non-commercial project declaration.
- `NPUNCU` (DUO:0000018) requires both conditions.
- `POA` (DUO:0000011) permits only population-origins/ancestry research; `NPOA` (DUO:0000044) prohibits those purposes.

The current application does not yet have an independently verified organisation/legal-entity registry or a DAC-verified commercial-purpose classification. Accordingly, service-level policy evaluation passes these attributes as unknown and fails closed for NCU/NPU/NPUNCU. The pure policy engine can evaluate verified attributes in tests, but this does not mean the production verification workflow exists. Implementing the registry and independent review workflow remains a production release blocker.


## Consent-basis fail-closed rule

A consent record must explicitly identify its basis. Missing `consent_basis` is
malformed and is rejected as `unknown_consent`; the policy engine never infers
participant-specific consent from an absent field. Synthetic demo records carry
`consent_basis=synthetic_demo` and are accepted only when the service is explicitly
in demo mode; this is never participant consent. Operator-supplied per-sample
consent records must explicitly carry `consent_basis=participant_record`.
Fallback consent generated for a real-genotype evaluation cohort is marked
`simulated` and is never accepted for data access. Public source terms must explicitly carry
`consent_basis=dataset_policy` plus their source-policy identifier, HTTPS URL,
and withdrawal limitations. Dataset-level terms still cannot authorize
individual-level record access.

## Signed consent event ordering

Signed participant consent events must carry an explicit timezone and must not be future-effective. GenomeGuard rejects timezone-naive and future-effective events because scheduled consent changes are not implemented. Each event must be strictly later than every previously applied event for the same participant and dataset; stale or out-of-order restores are rejected. PostgreSQL locks the participant row while checking and applying event order so concurrent event submissions cannot race and overwrite a newer consent state. SQLite serializes writers with its immediate transaction. This ordering control is an application safeguard, not proof that the external consent authority is institutionally accredited or that the event is legally valid.

## Disease-specific research and MONDO identifiers

DUO:0000007 (DS) must be paired with a disease ontology term; the EGA DAC guidance recommends MONDO to support automated evaluation. In institutional/research mode, GenomeGuard therefore treats the request and source-consent `disease` value as a MONDO CURIE (for example `MONDO:0005015`). A human-readable `disease_label` may accompany the code for display, but it is never used as the authorization key. Dataset-level policies using DS must also provide the MONDO identifier. The FHIR R4 export preserves the readable label and emits a separate `disease-ontology` Coding extension with the MONDO system and code.

The public synthetic demo remains clearly separated and may continue to use human-readable example labels; those simulated examples are not participant consent and cannot authorize institutional research-mode access. A MONDO identifier is a terminology identifier, not a diagnosis or clinical recommendation. Disease-term discovery must remain source-backed and user-selected.

## Donor self-service boundary

The donor self-service consent-edit and withdrawal/restore endpoints are synthetic-demo controls only. In institutional/research mode, both the API routes and service methods fail closed with `consent_authority_required`; participant consent changes and withdrawals must arrive through the configured signed authoritative consent-event workflow. A donor session token or free-text disease label is not an authority credential.

