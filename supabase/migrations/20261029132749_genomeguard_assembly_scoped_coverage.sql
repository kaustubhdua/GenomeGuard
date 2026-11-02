-- Derive public chromosome coverage from normalized, provenance-approved genotype data.
-- Do not count the legacy `genomeguard.variants` table or mix coordinates from another assembly.
CREATE OR REPLACE FUNCTION public.gg_list_chromosome_coverage()
RETURNS TABLE(chromosome text, variant_count bigint, first_position integer, last_position integer)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path TO ''
AS $function$
  SELECT
    c.chromosome,
    count(v.id)::bigint,
    min(v.position),
    max(v.position)
  FROM genomeguard.chromosome_reference c
  LEFT JOIN genomeguard.dataset_variants v
    ON upper(regexp_replace(coalesce(v.chromosome, ''), '^chr', '', 'i')) = c.chromosome
   AND EXISTS (
     SELECT 1
     FROM genomeguard.variant_dataset_manifest m
     WHERE m.id = v.dataset_id
       AND m.reference_assembly = c.reference_assembly
       AND m.data_use_review = 'approved_public_research'
       AND m.import_status = 'loaded'
       AND m.sample_count > 0
       AND m.variant_count > 0
       AND m.genotype_call_count > 0
       AND m.imported_at IS NOT NULL
   )
  GROUP BY c.chromosome
  ORDER BY
    CASE WHEN c.chromosome ~ '^[0-9]+$' THEN c.chromosome::integer ELSE 100 END,
    CASE c.chromosome WHEN 'X' THEN 1 WHEN 'Y' THEN 2 WHEN 'MT' THEN 3 ELSE 0 END;
$function$;

REVOKE ALL ON FUNCTION public.gg_list_chromosome_coverage() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gg_list_chromosome_coverage() TO service_role;