# Running on real genomes (1000 Genomes)

GenomeGuard runs on synthetic data by default so that a clean clone works with no download. This
page is how to switch the **genotypes and relatives** to real, openly released data. It has to be
run on a machine with internet access; the environment this repo was developed in could not
reach the 1000 Genomes servers, so **the end-to-end real-data run has not been done yet**. What has been
tested is the loader, against small fixtures that imitate the file formats (`backend/tests/test_real.py`).

## What becomes real, and what cannot

| Part | With the real build |
|---|---|
| Genotypes, allele frequencies, population labels | Real. 1000 Genomes participants consented to open public release of their genetic data. |
| Parent/child and sibling links | Real, from the pedigree file. Other relationships are derived with the same expected-average kinship model as the synthetic data. |
| Donor consent records | **Still simulated.** No real person consented to *this* system, and 1000 Genomes has no per-person DUO consent. The app labels this on every page, and the README and slides must too. |
| Requesters and query traffic | Demo accounts and scripted attacks. |

## Which release

- **Phase 3 (the loader's default).** Unrelated people by design, so almost no relatives exist
  and the family-exposure page will be sparse. Fine for testing, weak for the demo.
- **High-coverage release, 3,202 samples including 602 parent-child trios** (Byrska-Bishop et
  al., *Cell* 2022). This is the one that gives real families. The paper reports the sample and
  trio counts and that participants consented to public release.

Where the high-coverage files live: a Biostars answer points to the phased SNV/INDEL/SV VCFs at
`ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000G_2504_high_coverage/working/20220422_3202_phased_SNV_INDEL_SV/`.
**I could not confirm the per-chromosome file names or the pedigree file's name and location.**
Open the directory in a browser, pick one small chromosome (22 is a good start), and look in the
parent `1000G_2504_high_coverage/` directory for the pedigree. Do not guess file names.

## Build it

```
make real-trios VCF=path/to/chr22.vcf.gz PED=path/to/pedigree.txt
GG_REAL_COHORT_FILE=data_real/1000g_trios.npz GG_DB_PATH=data_real/gg.sqlite3 make run
```

By default the build is **family-first**: it takes whole families that have two or more members
in the VCF before filling the rest with unrelated people, so real parent/child links exist. That
makes the cohort **family-enriched on purpose**, and the cohort metadata records
`family_enriched: true`. Do not describe it as representative of a population. Use
`--no-family-first` on the module (`python -m app.data.real build ...`) for random sampling.

The pedigree parser accepts tab- or whitespace-separated files and several header spellings
(`Family ID / Individual ID / Paternal ID / Maternal ID`, or `FamilyID / SampleID / FatherID /
MotherID`, with a `Population` column). If your file uses different headers it stops with a
message naming the missing column and showing the header it found; add the spelling to `_ALIASES`
in `backend/app/data/real.py` and a fixture test.

## Before you show real rows

- Check IGSR's current data-use statement. The demo only ever shows aggregates and transformed
  releases, never rows, which is the safer position.
- Never commit downloaded files. `data_real/` should stay out of git (check `.gitignore`).
- After a real run, evaluate on that cohort: `make eval-real COHORT=data_real/1000g_trios.npz`.
  It writes `docs/eval-results-real.md` and `.json` (the synthetic `make eval` files are left
  alone; `GG_EVAL_JSON` points the app's Red-team page at the real file). Whether results are
  called "real" is decided by the cohort file's own metadata (`genotypes_real`), never by the
  fact that a file was supplied; a file without it is labelled "custom cohort". The report records
  the file's SHA-256 and skips the seed-robustness section, which is synthetic-only. Say on the
  slide which dataset the numbers came from; they will differ from the synthetic ones.
- Real genomes have linkage disequilibrium and population structure that the synthetic generator
  only approximates, so attack success could move in either direction.
