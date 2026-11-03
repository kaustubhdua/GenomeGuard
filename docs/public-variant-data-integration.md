# Public variant annotation integration and retraining

This research workflow joins public NCBI ClinVar GRCh38 labels to public Ensembl
Variant Effect Predictor (VEP) annotations and trains a gene-held-out research model.

## Sources
- NCBI ClinVar variant summary: https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz
- Ensembl VEP: run locally with the GRCh38 offline cache; see [offline variant training](offline-variant-training.md)
- Ensembl VEP plugins and their locally installed data files are optional; no Ensembl REST endpoint is used

The workflow selects a deterministic, balanced subset (default 10,000) of variants
with GRCh38 coordinates and criteria-provided, non-conflicting ClinVar assertions.
It requests VEP annotations in batches of at most 200 and caches each response so
subsequent runs reuse the public annotation work. VEP-derived consequence/impact, CADD, SIFT and PolyPhen scores where returned,
transcript/canonical/MANE indicators, and colocated population-frequency values are
joined by exact chromosome-position-REF-ALT identity. Population frequency is extracted
for the queried alternate allele only (not the reference allele or all colocated alleles).
The frequency field is generic and must not be represented as a gnomAD-specific frequency.
The training metadata records per-feature annotation coverage and numeric missingness is
represented explicitly in the preprocessing pipeline.

## Run
In GitHub Actions, run **Public variant data integration and retraining** and confirm
the public-data input. The job downloads source data, annotates variants, trains,
evaluates and uploads a 30-day artifact. No model is committed to the repository.

## Evaluation and limits
The split uses the first fold of a stratified five-fold gene-disjoint partition, but only that fold is evaluated in this workflow. The dataset is a balanced
research sample, not prevalence-representative. Annotation coverage can be incomplete.
CADD availability depends on Ensembl's returned annotations. Metrics must be compared
with the earlier sequence-only baseline; do not assume improvement. This is not
independent external validation, ancestry-specific validation, or clinical validation.
Never use the model for diagnosis or patient-facing clinical decisions.
