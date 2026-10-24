# Running on real genomes (1000 Genomes)

GenomeGuard runs on synthetic data by default so a clean clone works without downloading genomes. The hosted GitHub Actions runner has now completed an end-to-end download, cohort build, and evaluation against the public 1000 Genomes Phase 3 chromosome 22 data. See [successful real-data validation run #40135423030](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40133801168). Local reproduction still requires internet access.

That run verifies the real-genotype ingestion/evaluation path only. It does **not** verify real participant consent or a family-relative exposure cohort; the Phase 3 panel is unrelated by design.

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

The official [IGSR 30x collection page](https://www.internationalgenome.org/data-portal/data-collection/1000genomes_30x) links the phased SNV/INDEL/SV VCFs and sample metadata for the 3,202-sample cohort. The publication identifies the pedigree metadata file as `1KGP.3202_samples.pedigree_info.txt` in the high-coverage working directory; see the [2022 Cell paper and its data availability](https://pmc.ncbi.nlm.nih.gov/articles/PMC9439720/).

The dedicated [high-coverage family-cohort workflow](https://github.com/kaustubhdua/GenomeGuard/actions/workflows/family-data-validation.yml) now downloads the official [chromosome-22 phased VCF](https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000G_2504_high_coverage/working/20220422_3202_phased_SNV_INDEL_SV/1kGP_high_coverage_Illumina.chr22.filtered.SNV_INDEL_SV_phased_panel.vcf.gz) and the combined [pedigree/population metadata](https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000G_2504_high_coverage/20130606_g1k_3202_samples_ped_population.txt). The current run is still in progress; do not claim the family cohort has passed until its metadata checks and evaluation succeed.

## Build it

```
make real-trios VCF=path/to/chr22.vcf.gz PED=path/to/pedigree.txt
GG_REAL_COHORT_FILE=data_real/1000g_trios.npz GG_DB_PATH=data_real/gg.sqlite3 make run
```

By default the build is **family-first** when a pedigree is supplied: it prefers families with two or more members in the VCF. The `family_enriched` metadata now reflects actual relationship pairs in the built cohort, not just the requested sampling option. If the source has no pedigree (as with Phase 3), the metadata correctly remains `family_enriched: false`. Do not describe a family-enriched cohort as representative of a population. Use `--no-family-first` on the module (`python -m app.data.real build ...`) for random sampling.

The default public Phase 3 panel provides sample and population labels but no family relationships; each sample is treated as unrelated. For real parent/child links, pass a separate pedigree file with family, individual, father, mother and population columns. The parser accepts tab- or whitespace-separated files and several header spellings
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

## Verified real-genotype evaluation (2026-10-24)

GitHub Actions downloaded the public Phase 3 chromosome 22 VCF, built a cohort with 600 samples and 3,000 variants, and ran `eval-real` successfully. Provenance metadata from that run:

- Source: 1000 Genomes (IGSR), file `ALL.chr22.phase3_shapeit2_mvncall_integrated_v5b.20130502.genotypes.vcf.gz`
- Source VCF SHA-256: `a90c16c4ff2b3196476d506ae13cb3047fae8670163c7c932c4b0239aef3daf5`
- Source sample metadata file: `integrated_call_samples_v3.20130502.ALL.panel`
- Source sample-metadata SHA-256: `b4023dc6ee2d62ee89c8d4d347db4d348e65518d66d346574cdae7a4bbd76858`
- Build parameters: 600 requested samples, 3,000 max variants, keep probability 0.004, rare-MAF threshold 0.01, simulated withdrawn rate 0.03
- Observed relative pairs: 0; `family_enriched: false`; `genotypes_real: true`; `consent_simulated: true`

Selected results from the generated evaluation report (attack/query traffic remains simulated):

- Differencing attack accuracy was 100.0% with no defence, 35.1% ± 3.0% with Laplace noise only, and 52.9% ± 3.2% with the ladder plus differencing guard; the guessing baseline was 52.9%. The guard blocked the second query in 100% of trials.
- Membership-inference AUC varied with release size and noise; at 500 variants, the simulated attack AUC was 0.721 for raw frequencies and 0.511 for binned frequencies with epsilon 0.5, with very low utility for the latter (correlation 0.020).
- The query monitor froze all tested attacks at 5-, 30-, and 120-second gaps, but froze none at 600- and 1,200-second gaps. This is a measured limitation of the simulated sliding-window monitor, not a claim that slow attacks are stopped.

These results are evidence for the real-genotype processing path, not a formal privacy guarantee. The evaluation itself explicitly documents simplified attackers, synthetic traffic, and simplified epsilon accounting. The full generated Markdown and JSON reports are preserved as artifacts in [run #40134445686](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40135423030) for 30 days.
## Verified high-coverage family-cohort evaluation (2026-10-24)

The dedicated high-coverage workflow passed on GitHub Actions: [run #40136240277](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40136240277). It downloaded the official IGSR high-coverage chromosome-22 phased variant VCF and the 3,202-sample pedigree/population metadata file, built a pedigree-aware cohort, and completed `eval-real`.

Verified cohort metadata:

- VCF: `1kGP_high_coverage_Illumina.chr22.filtered.SNV_INDEL_SV_phased_panel.vcf.gz`
- VCF SHA-256: `91aeaf0d1e805cf4223c5cbf12e22afc28db1709054c42bd668337219f8fddcc`
- Sample metadata: `20130606_g1k_3202_samples_ped_population.txt`
- Sample metadata SHA-256: `4e164b717433fc9bfc16e29b20e5b4659b4216185b3275322d421fe3d323c132`
- Selected samples: 600; variants: 3,000
- Observed relationship pairs: 355; `pedigree_relationships_present: true`; `family_enriched: true`
- `genotypes_real: true`; `consent_simulated: true`

The generated report shows strong trade-offs, not a production privacy guarantee. In this run, the differencing attack recovered 100% of target genotypes without a defence; Laplace noise alone reduced this to 31.0% ± 2.8%, and the ladder plus differencing guard reduced it to the guessing baseline of 55.1% ± 3.1% while blocking the second query in 100% of trials. The simulated monitor froze 100% of tested fast triangulation attacks at 5-, 30-, and 120-second gaps, but froze none at 600- and 1,200-second gaps. The report itself documents simplified attackers, synthetic query/consent data, and simplified sequential epsilon accounting.

The report is available as a 30-day aggregate-only artifact in the [family-cohort run](https://github.com/kaustubhdua/GenomeGuard/actions/runs/40136240277). Raw genomic cohorts are not uploaded as workflow artifacts.