# Real cohort ingestion and consent provenance

GenomeGuard supports real genotype files and two distinct consent-provenance paths. Operator-supplied, source-matched participant records are preferred when a dataset provides them. For the public 1000 Genomes release, an optional dataset-level policy profile maps the project's published public-release terms to DUO-inspired rules. That profile is **not participant-specific consent**, does not invent consent dates, and is not a legal or ethics determination. The default importer still creates simulated consent only for local demo evaluation.

## Production-mode invariant

With `GG_DEMO_MODE=false`, startup now fails closed unless all of the following are true:

- `GG_REAL_COHORT_FILE` points to an existing cohort file whose embedded metadata declares real genotype provenance.
- That metadata declares `consent_simulated=false` and records an explicit consent match for every selected source sample.
- `GG_ADMIN_API_KEY` is a unique secret of at least 32 characters.
- `GG_MASTER_KEY` is a valid base64-encoded 32-byte key.
- `GG_ALLOW_TAMPER_DEMO=false`.
- The database's recorded provenance matches the configured cohort. GenomeGuard refuses to relabel an existing synthetic database as real.

This guard is a technical safety check, **not** a determination that consent is legally valid. An authorized data controller must confirm the lawful basis, participant permissions, institutional approvals, data-use terms, retention and withdrawal rules before importing any data.

## Dataset-level policy for the public 1000 Genomes release

The checked-in profile at `docs/policies/igsr-1000-genomes-public-release.json` cites the official IGSR sample-collection principles. Those principles describe public Internet release and future research uses, including academic, commercial, and government research; they also state that samples/data cannot be withdrawn after release. GenomeGuard maps that dataset-level description to the broad DUO-inspired `GRU` use class for this specific public reference dataset.

This is deliberately represented as `consent_basis: dataset_policy`, not as a per-participant consent record. No participant signature, consent date, or individual withdrawal state is fabricated. The UI and API provenance label must continue to say this is a dataset-level source-policy mapping and that independent legal/ethics review has not been performed. Do not reuse this profile for controlled-access data, private clinical cohorts, or any dataset with additional use restrictions.

Build the public reference cohort with:

```bash
python -m app.data.real build \
  --consent-policy-json docs/policies/igsr-1000-genomes-public-release.json \
  --out data_real/1000g_phase3_chr22.npz --samples 600 --variants 3000
```

The Docker image uses this command at build time and retains only the derived cohort, not the downloaded VCF or sample panel. Source hashes and build parameters are recorded in cohort metadata. This gives the research instance real public genotypes and a documented dataset-level policy, but does **not** make the service production-ready or suitable for private participant records.

## Consent JSON input

Pass `--consent-json /secure/path/consent-records.json` to the real cohort builder. The file is a JSON object keyed by the exact source sample identifiers in the VCF and pedigree. Every selected sample must have a record. Do not add names, email addresses, medical record numbers, or other direct identifiers.

Each record must include:

- `use`: `GRU`, `HMB`, or `DS`.
- `disease`: a disease label for `DS`; otherwise null if not applicable.
- `modifiers`: a list drawn from `NCU`, `NPU`, `NMDS`, `NAGR`, `NCTRL` (an empty list is allowed).
- `population`: a population restriction or null.
- `consent_date`: ISO date (`YYYY-MM-DD`).
- `withdrawn`: an explicit boolean reflecting the current recorded withdrawal status.

Illustrative shape only (not a real consent record and not permission to use any person's data):

```json
{
  "SOURCE_SAMPLE_ID": {
    "use": "GRU",
    "disease": null,
    "modifiers": [],
    "population": null,
    "consent_date": "2025-01-31",
    "withdrawn": false
  }
}
```

The example is deliberately a placeholder. Do not copy its values into real participant records without verifying the source documentation. If a selected sample is missing, malformed, or has an invalid date/status, cohort building stops rather than inventing a consent decision.

## Build and run

Use source files and consent records that your organization is authorized to process. Keep the VCF, pedigree, consent JSON, generated cohort NPZ, and any credentials outside the Git repository.

```bash
python -m app.data.real build \
  --vcf /secure/source/cohort.vcf.gz \
  --ped /secure/source/pedigree.tsv \
  --consent-json /secure/source/consent-records.json \
  --out /secure/import/genomeguard-cohort.npz
```

Then configure the service with the path to the generated cohort and a **new, empty database path** for that dataset:

```bash
GG_DEMO_MODE=false \
GG_ALLOW_TAMPER_DEMO=false \
GG_REAL_COHORT_FILE=/secure/import/genomeguard-cohort.npz \
GG_DB_PATH=/secure/persistent/genomeguard.sqlite3 \
GG_DATASET_ID=approved-cohort-2026-01 \
GG_MASTER_KEY='<base64-encoded-random-32-byte-key>' \
GG_ADMIN_API_KEY='<unique-random-secret-at-least-32-characters>' \
python -m app.main
```

Use your deployment platform's secret manager rather than putting secrets in shell history or deployment files. The paths above are examples; the container must actually have access to the files and durable storage must be configured and tested. A cohort database is bound cryptographically to its dataset ID and master key. Keep backups and key material under separate, documented access controls.

## Provisioning researcher API credentials

In non-demo mode, a steward can provision a machine-to-machine researcher credential through the protected API endpoint:

```http
POST /admin/requesters
X-Admin-Key: <steward-secret>
Content-Type: application/json

{"name":"Researcher Name","institution":"Verified Institution","credential_level":"registered"}
```

The response includes a randomly generated API key **once**. Deliver it through an approved secret-delivery channel; do not paste it into tickets, logs, or source control. Only `registered` and `controlled` tiers are accepted. The endpoint is disabled in demo mode. A steward must independently verify the researcher's identity, institutional affiliation, approvals and permitted use before provisioning; this API endpoint does not verify identity or replace institutional single sign-on, MFA, account recovery, revocation workflows or access reviews.

## What the importer does not establish

- It does not authenticate the provenance or signature of a consent document; it validates a structured operator-supplied record.
- It does not integrate an institutional identity provider, e-consent platform, IRB/ethics workflow, or legal review.
- It does not automatically ingest future consent changes from a source system. Withdrawal and consent updates must be propagated through an approved, monitored process.
- It does not make the local hash chain immutable. External anchoring and independently controlled audit storage are separate requirements.
- It does not make public datasets appropriate for every purpose. Follow the source's data-use terms and never upload controlled-access genotypes to a public demo.

For governance principles, see the [GA4GH framework for responsible sharing of genomic and health data](https://www.ga4gh.org/framework/) and the [NIH guidance for controlled-access genomic data](https://www.grants.nih.gov/policy-and-compliance/policy-topics/sharing-policies/accessing-data/using-genomic-data).
