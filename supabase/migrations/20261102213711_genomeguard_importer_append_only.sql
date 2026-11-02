-- The VCF importer only appends validated rows; it never deletes or rewrites source calls.
-- Remove the legacy DELETE grants from the importer role as defense in depth.
REVOKE DELETE ON genomeguard.dataset_samples FROM genomeguard_importer;
REVOKE DELETE ON genomeguard.dataset_variants FROM genomeguard_importer;
REVOKE DELETE ON genomeguard.dataset_genotype_calls FROM genomeguard_importer;
