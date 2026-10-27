# Supabase schema isolation

The selected Supabase project is shared at the project level, so GenomeGuard application tables must not be created in `public` by default.

- Application schema: `genomeguard`.
- Backend access: server-side PostgreSQL connection using `GG_DATABASE_URL`.
- Search path: `genomeguard, public`, set by `PostgresStore` before versioned migrations.
- Supabase Data API access: no direct `anon` or `authenticated` grants to this private schema.
- Frontend: never receives `GG_DATABASE_URL`, database passwords, Supabase secret keys, master encryption key, or steward key.

The `genomeguard` schema and 13 application tables are now present in project `common 1`; four schema/status migrations are recorded and the application tables are empty. The live Supabase security advisor reports RLS disabled on all 13 tables. A new defense-in-depth migration (`20261027010000_private_schema_rls.sql`) enables RLS and revokes browser-role privileges; it is committed for review but has **not** been applied to the live project. Direct SQL checks confirm `anon` and `authenticated` currently have no schema USAGE or table SELECT/INSERT privileges. The backend has not yet been connected to this database.

Verify after first successful startup:

```sql
select table_schema, table_name
from information_schema.tables
where table_schema = 'genomeguard'
order by table_name;
```

Run Supabase security and performance advisors after every migration. The proposed RLS migration intentionally adds no browser-facing policies because the current application uses a server-side PostgreSQL connection rather than the Supabase Data API. The backend connection and full integration tests must be verified before enabling it in the live project; do not grant browser roles access to genomic tables.
