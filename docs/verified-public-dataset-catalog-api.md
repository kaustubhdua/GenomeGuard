# Verified public genomic catalogue API

The public catalogue is served by the first-party Python/Starlette API. It has no Supabase Edge Function, browser publishable key, hosted Auth dependency, or PostgREST access path.

## Routes

- `GET /catalogue/sources` — curated external source metadata and review boundaries.
- `GET /catalogue/datasets` — only verified public dataset manifests whose normalized sample, variant, and genotype-call counts reconcile with the stored rows.
- `GET /catalogue/chromosomes?assembly=GRCh37|GRCh38` — reference chromosome lengths plus coverage measured from verified normalized dataset imports.
- `GET /variants/search?q=22:105123:A:G` — exact coordinate metadata lookup only; no gene-symbol annotation is implied.
- `GET /variants/population-frequency?chromosome=22&position=105123&reference_allele=A&alternate_allele=G&assembly=GRCh38` — exact allele lookup against approved aggregate population references.

The browser uses same-origin routes. Vercel rewrites application requests to the configured GenomeGuard Python API. The local application serves the same routes directly.

## Dataset publication gate

A dataset appears in `/catalogue/datasets` only when all of the following hold:

- The manifest is reviewed and approved for the declared public-research use.
- The source release, HTTPS source URL, reference assembly, and SHA-256 are present.
- Import status is `loaded`.
- Stored sample, variant, and called-genotype counts are non-zero and reconcile with measured normalized rows.
- The imported source file and its reuse statement/citation match the reviewed manifest.

A manifest row is not proof of individual consent, scientific validity, or legal authorization. A source appearing in `/catalogue/sources` does not mean the artifact has been downloaded, checksum-verified, imported, or approved.

## PostgreSQL storage

The native migration `backend/migrations/002_normalized_public_references.sql` creates the `genomeguard` schema and its normalized sample, variant, genotype-call, dataset-manifest, and aggregate-frequency tables. It is applied by the numbered PostgreSQL migration runner. The older `supabase/` migrations are historical artifacts and must not be applied to a new installation.

The application queries the normalized tables using its server-side PostgreSQL connection. Aggregate population-frequency reads execute in a read-only transaction and filter to manifests with both `data_use_review='approved_public_research'` and `import_status='loaded'`. The endpoint never queries individual genotype calls for population-frequency responses.

## Empty and unavailable behavior

An empty catalogue is an honest result when no qualifying import exists. Missing schema, database access, or query support returns an unavailable response. The API never substitutes synthetic counts or invented population frequencies.

The local demo cohort is synthetic and is not inserted into the verified public catalogue. No public reference is claimed as imported merely because a source or manifest is listed.
