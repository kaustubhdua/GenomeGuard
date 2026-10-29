-- Reference metadata for all human chromosomes in GRCh38.
-- This is an assembly catalogue, not a claim that genotype variants are loaded for every chromosome.
create table if not exists genomeguard.chromosome_reference (
  chromosome text primary key,
  reference_assembly text not null check (reference_assembly = 'GRCh38'),
  length_bp bigint not null check (length_bp > 0),
  kind text not null check (kind in ('autosome', 'sex', 'mitochondrial')),
  source_url text not null,
  created_at timestamptz not null default now()
);
alter table genomeguard.chromosome_reference enable row level security;
revoke all on table genomeguard.chromosome_reference from public, anon, authenticated, service_role;

insert into genomeguard.chromosome_reference (chromosome, reference_assembly, length_bp, kind, source_url) values
('1','GRCh38',248956422,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('2','GRCh38',242193529,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('3','GRCh38',198295559,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('4','GRCh38',190214555,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('5','GRCh38',181538259,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('6','GRCh38',170805979,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('7','GRCh38',159345973,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('8','GRCh38',145138636,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('9','GRCh38',138394717,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('10','GRCh38',133797422,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('11','GRCh38',135086622,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('12','GRCh38',133275309,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('13','GRCh38',114364328,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('14','GRCh38',107043718,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('15','GRCh38',101991189,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('16','GRCh38',90338345,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('17','GRCh38',83257441,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('18','GRCh38',80373285,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('19','GRCh38',58617616,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('20','GRCh38',64444167,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('21','GRCh38',46709983,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('22','GRCh38',50818468,'autosome','https://www.ncbi.nlm.nih.gov/grc/human'),
('X','GRCh38',156040895,'sex','https://www.ncbi.nlm.nih.gov/grc/human'),
('Y','GRCh38',57227415,'sex','https://www.ncbi.nlm.nih.gov/grc/human'),
('MT','GRCh38',16569,'mitochondrial','https://www.ncbi.nlm.nih.gov/grc/human')
on conflict (chromosome) do update set reference_assembly=excluded.reference_assembly,
length_bp=excluded.length_bp, kind=excluded.kind, source_url=excluded.source_url;

create index if not exists variants_chrom_pos_idx on genomeguard.variants (chrom, pos);

create or replace function public.gg_list_chromosome_reference()
returns table (chromosome text, reference_assembly text, length_bp bigint, kind text, source_url text)
language sql stable security definer set search_path = ''
as $$
  select c.chromosome, c.reference_assembly, c.length_bp, c.kind, c.source_url
  from genomeguard.chromosome_reference c
  order by case when c.chromosome ~ '^[0-9]+$' then c.chromosome::integer else 100 end,
    case c.chromosome when 'X' then 1 when 'Y' then 2 when 'MT' then 3 else 0 end;
$$;
revoke all on function public.gg_list_chromosome_reference() from public, anon, authenticated;
grant execute on function public.gg_list_chromosome_reference() to service_role;
