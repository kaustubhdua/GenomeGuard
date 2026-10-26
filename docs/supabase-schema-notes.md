# Supabase schema isolation

The selected Supabase project is shared at the project level, so GenomeGuard application tables must not be created in `public` by default.

- Application schema: `genomeguard`.
- Backend access: server-side PostgreSQL connection using `GG_DATABASE_URL`.
- Search path: `genomeguard, public`, set by `PostgresStore` before versioned migrations.
- Supabase Data API access: no direct `anon` or `authenticated` grants to this private schema.
- Frontend: never receives `GG_DATABASE_URL`, database passwords, Supabase secret keys, master encryption key, or steward key.

The `genomeguard` schema was created in project `common 1` and verified. At that moment, the project contained no application tables and no recorded migrations. Tables are created only when the backend runs its versioned migration after the Render secret is configured.

Verify after first successful startup:

```sql
select table_schema, table_name
from information_schema.tables
where table_schema = 'genomeguard'
order by table_name;
```

Run Supabase security and performance advisors after migration and review all findings. Do not enable RLS on application tables as a substitute for the existing backend authorization without first designing and testing a coherent access model: this application connects directly through PostgreSQL and does not use the Supabase Data API for application queries.
