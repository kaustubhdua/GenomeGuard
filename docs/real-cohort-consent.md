# Real cohort ingestion and consent provenance

GenomeGuard supports real genotype files and two distinct consent-provenance paths. Operator-supplied, source-matched participant records are preferred when a dataset provides them. For the public 1000 Genomes release, the optional dataset-level policy profile maps published public-release terms to DUO-inspired rules. That profile is **not participant-specific consent**, does not invent consent dates, and is not a legal or ethics determination.

## Production-mode invariant

With `GG_DEMO_MODE=false`, startup fails closed unless a real cohort file, non-simulated consent provenance, strong master key, unique admin key, disabled tamper-demo mode and database provenance match are established. This is a technical guard, not a determination that consent is legally valid.

The production-controls branch additionally requires separate runtime/migration PostgreSQL URLs and provides required OIDC and consent-authority settings in the production Blueprint. Production OIDC and signed participant consent are enabled only after institution-specific issuer, audience, client, JWKS, organization allow-list, authority issuer and Ed25519 public key are supplied.

## Dataset-level policy for the public 1000 Genomes release

The checked-in profile at `docs/policies/igsr-1000-genomes-public-release.json` cites the official IGSR sample-collection principles. It maps dataset-level public-release terms to a broad DUO-inspired GRU class. It is represented as `consent_basis: dataset_policy`, not participant consent. Do not reuse it for controlled/private/clinical cohorts.

## Participant consent event updates

The production-controls branch supports externally signed Ed25519 events at `POST /admin/consent-events`. The trusted authority signs a canonical event containing exactly:

- `schema_version` = `1.0`
- `event_id` (UUID), `issuer`, `dataset_id`, `source_sample_id`
- `event_type`: `consent_updated`, `withdrawn`, or `restored`
- `effective_at` (ISO timestamp)
- `consent`: `use`, `disease`, `modifiers`, `population`, `consent_date`
- `signature`: base64url Ed25519 signature over canonical JSON of all preceding fields

The cohort database stores only a SHA-256 hash of the source sample identifier. The signed event is verified against `GG_CONSENT_AUTHORITY_PUBLIC_KEY` and `GG_CONSENT_AUTHORITY_ISSUER`, checked against the active dataset and exact sample mapping, and written to the append-only `consent_events` ledger. Duplicate event IDs are rejected. A restore event must carry a fresh complete consent record; previous consent is not silently reactivated. Dataset-policy records cannot be converted into participant consent.

This endpoint is intentionally unavailable until a trusted authority is configured. The institution must validate that the signing key is controlled by the actual data controller/consent source, the source-to-sample mapping is correct, and withdrawal timing is legally and operationally meaningful. A cryptographic signature does not prove legal authority or ethics approval.

## Build and run

Keep VCF, pedigree, consent JSON, generated cohort NPZ, private keys and credentials outside the Git repository. For an operator-supplied participant-record cohort:

```bash
python -m app.data.real build \
  --vcf /secure/source/cohort.vcf.gz \
  --ped /secure/source/pedigree.tsv \
  --consent-json /secure/source/consent-records.json \
  --out /secure/import/genomeguard-cohort.npz
```

The source sample mapping is retained only as a one-way hash for subsequent consent reconciliation. A cohort replacement is blocked once participant consent events exist; use a reviewed dataset-version migration rather than erasing the consent history.

## Release boundary

No real participant or controlled genomic data should be loaded until the institutional consent authority, OIDC identity source, organization authorization, PostgreSQL RLS, key custody, signed external audit anchoring, retention/recovery, privacy/legal/ethics and security review have been approved. GenomeGuard is not a clinical decision system.
