-- Per-chromosome coverage comes from actual rows in the private variants table.
-- Zero means reference metadata exists but variant records are not loaded.
create or replace function public.gg_list_chromosome_coverage()
returns table (chromosome text, variant_count bigint, first_position integer, last_position integer)
language sql stable security definer set search_path = ''
as $$
  select c.chromosome, count(v.id)::bigint, min(v.pos), max(v.pos)
  from genomeguard.chromosome_reference c
  left join genomeguard.variants v
    on upper(regexp_replace(coalesce(v.chrom, ''), '^chr', '', 'i')) = c.chromosome
  group by c.chromosome
  order by case when c.chromosome ~ '^[0-9]+$' then c.chromosome::integer else 100 end,
    case c.chromosome when 'X' then 1 when 'Y' then 2 when 'MT' then 3 else 0 end;
$$;
revoke all on function public.gg_list_chromosome_coverage() from public, anon, authenticated;
grant execute on function public.gg_list_chromosome_coverage() to service_role;
