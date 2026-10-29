# Supabase schema isolation

The selected Supabase project is shared with BharatSim. GenomeGuard must not write to `public` or alter the `bharatsim` schema.

- Governance/catalogue schema: `genomeguard` (normalized dataset, organization, consent, request RPC and deployment-status objects).
- Python decision-engine persistence schema: `genomeguard_runtime` (the legacy Store contract: cohort metadata, encrypted genotype blobs, requesters, requests, decisions, epsilon ledger and audit chain).
- Backend access: server-side PostgreSQL connection using `GG_DATABASE_URL`; the connection role must be provisioned by an operator with least-privilege grants on the runtime schema.
- Runtime search path: `genomeguard_runtime, public`, set by `PostgresStore` before its versioned migration.
- Browser roles must not receive direct access to either private schema.
- Frontend: never receives `GG_DATABASE_URL`, database passwords, Supabase secret keys, master encryption key, or steward key.

**Important architecture boundary:** the normalized `genomeguard` genotype tables and the Python engine's `genomeguard_runtime` cohort store are not yet bridged. The runtime schema separation prevents the legacy Store's incompatible `CREATE TABLE` migration from colliding with existing normalized tables; it does not by itself complete dataset import or governance API parity. The manifest and normalized genotype tables must remain empty until a real, validated import has run.

The live project has the normalized governance schema and its migrations. The live database has no `USAGE` grant on `genomeguard` for `service_role`; that API role must not be treated as a PostgreSQL login. The production API still reports SQLite and the required server-side connection is not configured. A dedicated database login and schema grants must be provisioned and verified before enabling the cutover.

Verify after first successful startup:

```sql
select table_schema, table_name
from information_schema.tables
where table_schema = 'genomeguard'
order by table_name;
```

Run Supabase security and performance advisors after every migration. The proposed RLS migration intentionally adds no browser-facing policies because the current application uses a server-side PostgreSQL connection rather than the Supabase Data API. The backend connection and full integration tests must be verified before enabling it in the live project; do not grant browser roles access to genomic tables.
