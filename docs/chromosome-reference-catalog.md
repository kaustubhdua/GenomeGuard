# GenomeGuard chromosome reference catalogue

GenomeGuard's backend target is Supabase project `common 1` (`hkyieaovolkethovyenb`): Supabase PostgreSQL stores private application data and Supabase Edge Functions serve the API. Render is a legacy research prototype, not the target backend for this work.

## What was added

- A private `genomeguard.chromosome_reference` table for the GRCh38 reference assembly.
- Reference metadata for chromosomes 1–22, X, Y and mitochondrial chromosome MT (25 reference records).
- `public.gg_list_chromosome_reference()` and `public.gg_list_chromosome_coverage()` server-only RPCs; execute is revoked from `public`, `anon` and `authenticated`, and granted only to `service_role`.
- A `variants(chrom, pos)` index for chromosome-position lookups.
- `GET /functions/v1/genomeguard-api/chromosomes` returns reference lengths and per-chromosome counts based on actual rows in `genomeguard.variants`.

## Important coverage boundary

Reference chromosome metadata is not genotype data. At initial verification the `genomeguard.variants` table was empty, so all 25 chromosomes had zero variant rows. The endpoint must report that fact and must not imply that whole-genome variant/genotype analysis is ready.

The legacy public research build currently samples chromosome 22 only. Importing real variants for additional chromosomes requires a provenance-checked source, explicit build/assembly handling, measured import size, and appropriate data-use review. No synthetic variant rows were inserted to make coverage look complete.

## Verification

- Direct SQL returned 25 reference rows: 22 autosomes, X, Y and MT.
- Direct coverage RPC returned one row per chromosome and zero variants when the variant table is empty.
- The API function was deployed to Supabase as version 4; a live HTTP endpoint check should be recorded separately from SQL-level verification.

## Frontend chromosome explorer

The frontend now includes a dedicated `#/chromosomes` explorer with a responsive coverage table, chromosome filtering, a loaded-only filter, reference lengths, actual variant counts, observed coordinate ranges, and a fail-closed unavailable state. It calls the same-origin `/chromosomes` API path through the existing API client. **Do not consider this route production-connected until the user's planned Vercel-to-Supabase routing change is applied and browser-tested.** Until then the page explicitly reports the service as unavailable rather than substituting mock counts.
