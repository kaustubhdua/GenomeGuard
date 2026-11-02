# GenomeGuard Supabase migration reconciliation — 3 November 2026

## Scope and safety

Project: Supabase `common 1` (`hkyieaovolkethovyenb`), region `ap-south-1`. This is a shared project. The migration history contains GenomeGuard and BharatSim migrations. All GenomeGuard objects remain in the private `genomeguard` schema; BharatSim objects and migrations are outside this repository's ownership and were not changed.

No data rows were inserted, updated, or deleted during this reconciliation. The live changes in this session were additive schema migrations only. No `supabase db push`, `migration repair`, or direct edits to `supabase_migrations.schema_migrations` were run.

## Applied live migrations represented by this repository

The local migration filenames previously used independent timestamps and did not match the versions recorded in the live Supabase migration history. That would make a future `supabase db push` treat already-applied migrations as pending. The repository filenames have now been aligned to the actual live version prefixes.

| Live version | Live migration name | Repository migration |
|---|---|---|
| 20261026194921 | genomeguard_schema | `20261026194921_genomeguard_schema.sql` |
| 20261026194950 | index_donor_access_request | `20261026194950_index_donor_access_request.sql` |
| 20261026195105 | deployment_status | `20261026195105_deployment_status.sql` |
| 20261026195207 | deployment_status_service_policy | `20261026195207_deployment_status_service_policy.sql` |
| 20261028180028 | genomeguard_private_schema_rls | `20261028180028_genomeguard_private_schema_rls.sql` |
| 20261029045250 | genomeguard_supabase_api_identity_foundation | `20261029045250_genomeguard_supabase_api_identity_foundation.sql` |
| 20261029045259 | genomeguard_supabase_request_api | `20261029045259_genomeguard_supabase_request_api.sql` |
| 20261029051616 | genomeguard_request_validation_hardening | `20261029051616_genomeguard_request_validation_hardening.sql` |
| 20261029061839 | genomeguard_chromosome_reference_catalog | `20261029061839_genomeguard_chromosome_reference_catalog.sql` |
| 20261029061914 | genomeguard_chromosome_variant_coverage | `20261029061914_genomeguard_chromosome_variant_coverage.sql` |
| 20261029075822 | genomeguard_variant_dataset_manifest | `20261029075822_genomeguard_variant_dataset_manifest.sql` |
| 20261029081133 | genomeguard_verified_public_dataset_catalog | `20261029081133_genomeguard_verified_public_dataset_catalog.sql` |
| 20261029084043 | genomeguard_organization_consent_workflows | `20261029084043_genomeguard_organization_consent_workflows.sql` |
| 20261029084053 | genomeguard_normalized_genotype_storage | `20261029084053_genomeguard_normalized_genotype_storage.sql` |
| 20261029084102 | genomeguard_request_details | `20261029084102_genomeguard_request_details.sql` |
| 20261029090645 | genomeguard_audit_append_only_and_consent_indexes | `20261029090645_genomeguard_audit_append_only_and_consent_indexes.sql` |
| 20261029094937 | genomeguard_request_history_membership_gate | `20261029094937_genomeguard_request_history_membership_gate.sql` |
| 20261029100140 | genomeguard_consent_steward_role | `20261029100140_genomeguard_consent_steward_role.sql` |
| 20261029100254 | genomeguard_api_events | `20261029100254_genomeguard_api_events.sql` |
| 20261029100358 | genomeguard_consent_steward_only | `20261029100358_genomeguard_consent_steward_only.sql` |
| 20261029100724 | genomeguard_api_events_constraints | `20261029100724_genomeguard_api_events_constraints.sql` |
| 20261029101432 | genomeguard_request_review_history | `20261029101432_genomeguard_request_review_history.sql` |
| 20261029101831 | genomeguard_review_history_append_only | `20261029101831_genomeguard_review_history_append_only.sql` |
| 20261029125817 | genomeguard_target_org_authorization | `20261029125817_genomeguard_target_org_authorization.sql` |
| 20261029132531 | genomeguard_review_history_fk_indexes | `20261029132531_genomeguard_review_history_fk_indexes.sql` |
| 20261029132749 | genomeguard_assembly_scoped_coverage | `20261029132749_genomeguard_assembly_scoped_coverage.sql` |
| 20261029132941 | genomeguard_assembly_aware_reference_catalogue | `20261029132941_genomeguard_assembly_aware_reference_catalogue.sql` |
| 20261102212149 | genomeguard_steward_review_queue | `20261102212149_genomeguard_steward_review_queue.sql` |
| 20261102212425 | genomeguard_auth_access_status | `20261102212425_genomeguard_auth_access_status.sql` |
| 20261102213657 | genomeguard_importer_privileges | `20261102213657_genomeguard_importer_privileges.sql` |
| 20261102213711 | genomeguard_importer_append_only | `20261102213711_genomeguard_importer_append_only.sql` |
| 20261102213726 | genomeguard_population_reference | `20261102213726_genomeguard_population_reference.sql` |

The live history also contains four BharatSim migrations (`20261027054905`, `20261027061609`, `20261030181640`, `20261101042942`). They are intentionally not represented or modified by this GenomeGuard repository.

## Reconstructed identity foundation migration

The live history includes `20261029045250_genomeguard_supabase_api_identity_foundation`, but the repository had no matching file. The original idempotent DDL was duplicated at the beginning of the later request-API migration. The missing file has been reconstructed from those statements and the live schema inspection:

- `genomeguard.requesters.auth_user_id` exists.
- `requesters_auth_user_id_unique` exists and is a partial unique index on non-null user IDs.

The duplicate DDL was removed from the request-API migration file and placed in the matching identity-foundation file. **The reconstructed file is not a byte-for-byte recovery of the original migration.** It is clearly marked in the SQL comments and requires human review before this repository is used to bootstrap a fresh Supabase project.

## Additive schema migrations applied during this work

The following previously unrecorded repository migrations were applied in dependency order and renamed to match the actual generated live versions:

- Importer role privileges: `20261102213657`.
- Importer append-only restrictions: `20261102213711`.
- Aggregate population-reference manifest/frequency schema: `20261102213726`.

Read-only verification confirms both importer roles exist, importer roles can insert into their scoped tables, and DELETE is not granted. The two population-reference tables exist and are empty. The `genomeguard` schema now has 25 tables. No dataset artifact has been imported.

## Remaining migration

`20261104000000_genomeguard_population_reference_reader.sql` is still unapplied. It is a future-dated migration intended to provide a restricted read path for aggregate reference frequencies. Do not apply it before its planned date and the corresponding reader RPC/Edge route have been reviewed and tested.

## Safe next step

The live version prefixes and local filenames now align for every applied GenomeGuard migration. Before running any future `supabase db push`, a reviewer must inspect the reconstructed identity-foundation migration and confirm that the repository's SQL content for each historical version matches the live project. Keep the four BharatSim migration records untouched. Never use migration repair as a shortcut for unresolved content differences.
