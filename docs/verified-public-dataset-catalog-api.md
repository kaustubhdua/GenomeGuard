# Verified public dataset catalogue API

## Route

`GET /datasets` on the GenomeGuard Supabase Edge Function.

The route is read-only. It calls `public.gg_list_verified_public_datasets()`; it does not read the private manifest table directly from the browser.

## Visibility contract

A dataset is returned only when all of these are true in the private manifest:

- `data_use_review = 'approved_public_research'`
- `import_status = 'loaded'`
- variant, genotype-call, and sample counts are all greater than zero
- `imported_at` is present

The database function is `SECURITY DEFINER` with an empty search path, fully qualified object names, and execute privilege restricted to `service_role`. The underlying manifest has no direct grants to browser roles.

## Response

```json
{
  "datasets": [],
  "dataset_count": 0,
  "provenance_note": "Only datasets reviewed for public research and marked loaded with verified non-zero counts are listed. Dataset-level reuse review is not participant-specific consent or clinical authorization."
}
```

The empty array is the correct response when no qualifying dataset exists. Do not seed a placeholder row, infer coverage from the chromosome reference catalogue, or label an import as loaded before validating the actual source artifact and reconciling database counts.

## Security and failure behaviour

- The route never returns manifest rows that are pending review, rejected, failed, retired, or not fully loaded.
- A database/RPC failure returns HTTP 503 and no fabricated catalogue.
- The manifest table remains private; no broad browser table grants or RLS policies are added.
- This endpoint does not authorize access to genotype records or establish participant-specific consent.
- The endpoint is not considered production-integrated until the deployed frontend routing and live smoke test are verified.

## Verification

The deployment-config workflow applies migrations to a clean PostgreSQL database and checks that the function returns no datasets on an empty manifest, is not executable by `anon` or `authenticated`, and is executable by `service_role`.

The live catalogue remains empty until a source-reviewed import completes all required validation.

## Browser gateway authentication

The public read-only dataset and chromosome catalogue requests send the Supabase project's `sb_publishable_…` key in the `apikey` header. This key is designed for browser exposure and is not a service-role credential. All governed routes still require a verified Supabase user bearer token, and private schemas must remain inaccessible to browser roles. The repository's Gitleaks configuration narrowly allowlists this publishable-key format only in the public catalogue frontend paths; never add service-role keys, database URLs, or secret keys to the allowlist.
