-- Exact-locus index for aggregate population-frequency lookups.
-- The query still joins the manifest and requires approved_public_research + loaded.
CREATE INDEX IF NOT EXISTS population_variant_frequency_exact_lookup_idx
  ON genomeguard.population_variant_frequency
  (chromosome, position, reference_allele, alternate_allele, dataset_id, population)
  INCLUDE (allele_count, allele_number, allele_frequency, homozygote_count);
