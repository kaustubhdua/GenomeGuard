-- Support the GRCh37 assembly used by the 1000 Genomes Phase 3 VCF alongside GRCh38.
-- Reference metadata is distinct from observed variant/genotype data.
ALTER TABLE genomeguard.chromosome_reference
  DROP CONSTRAINT chromosome_reference_pkey;
ALTER TABLE genomeguard.chromosome_reference
  ADD PRIMARY KEY (reference_assembly, chromosome);
ALTER TABLE genomeguard.chromosome_reference
  DROP CONSTRAINT chromosome_reference_reference_assembly_check;
ALTER TABLE genomeguard.chromosome_reference
  ADD CONSTRAINT chromosome_reference_reference_assembly_check
  CHECK (reference_assembly IN ('GRCh37', 'GRCh38'));

INSERT INTO genomeguard.chromosome_reference
  (chromosome, reference_assembly, length_bp, kind, source_url)
VALUES
  ('1','GRCh37',249250621,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('2','GRCh37',243199373,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('3','GRCh37',198022430,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('4','GRCh37',191154276,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('5','GRCh37',180915260,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('6','GRCh37',171115067,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('7','GRCh37',159138663,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('8','GRCh37',146364022,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('9','GRCh37',141213431,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('10','GRCh37',135534747,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('11','GRCh37',135006516,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('12','GRCh37',133851895,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('13','GRCh37',115169878,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('14','GRCh37',107349540,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('15','GRCh37',102531392,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('16','GRCh37',90354753,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('17','GRCh37',81195210,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('18','GRCh37',78077248,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('19','GRCh37',59128983,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('20','GRCh37',63025520,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('21','GRCh37',48129895,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('22','GRCh37',51304566,'autosome','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('X','GRCh37',155270560,'sex','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('Y','GRCh37',59373566,'sex','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37'),
  ('MT','GRCh37',16569,'mitochondrial','https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh37')
ON CONFLICT (reference_assembly, chromosome) DO UPDATE
SET length_bp=excluded.length_bp, kind=excluded.kind, source_url=excluded.source_url;

DROP FUNCTION IF EXISTS public.gg_list_chromosome_reference();
CREATE FUNCTION public.gg_list_chromosome_reference(p_assembly text DEFAULT 'GRCh38')
RETURNS TABLE(chromosome text, reference_assembly text, length_bp bigint, kind text, source_url text)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path TO ''
AS $function$
  SELECT c.chromosome, c.reference_assembly, c.length_bp, c.kind, c.source_url
  FROM genomeguard.chromosome_reference c
  WHERE c.reference_assembly = p_assembly
  ORDER BY
    CASE WHEN c.chromosome ~ '^[0-9]+$' THEN c.chromosome::integer ELSE 100 END,
    CASE c.chromosome WHEN 'X' THEN 1 WHEN 'Y' THEN 2 WHEN 'MT' THEN 3 ELSE 0 END;
$function$;
REVOKE ALL ON FUNCTION public.gg_list_chromosome_reference(text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gg_list_chromosome_reference(text) TO service_role;

DROP FUNCTION IF EXISTS public.gg_list_chromosome_coverage();
CREATE FUNCTION public.gg_list_chromosome_coverage(p_assembly text DEFAULT 'GRCh38')
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
  WHERE c.reference_assembly = p_assembly
  GROUP BY c.chromosome
  ORDER BY
    CASE WHEN c.chromosome ~ '^[0-9]+$' THEN c.chromosome::integer ELSE 100 END,
    CASE c.chromosome WHEN 'X' THEN 1 WHEN 'Y' THEN 2 WHEN 'MT' THEN 3 ELSE 0 END;
$function$;
REVOKE ALL ON FUNCTION public.gg_list_chromosome_coverage(text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gg_list_chromosome_coverage(text) TO service_role;