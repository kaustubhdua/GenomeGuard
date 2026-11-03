# Offline ClinVar and Ensembl VEP training

The pathogenicity research training pipeline does not call the Ensembl REST API.
It uses a local Ensembl VEP CLI installation and cache. The public ClinVar summary
may be downloaded directly from NCBI's public FTP distribution; it is not an
authenticated API and requires no API key. To run without network access, place
the ClinVar file in the data directory before starting.

## Prepare local annotations

1. Install Ensembl VEP and its GRCh38 cache using the official Ensembl VEP
   installation instructions. Keep the cache on local disk.
2. Run the training script once to select a balanced ClinVar sample and create
   `.training-data/public-annotations/clinvar_selected_for_vep.vcf`. The first
   run stops with a clear message if the local VEP JSONL file is missing.
3. Annotate that VCF locally (no REST mode):

```bash
vep --offline --cache --assembly GRCh38 --json --everything \
  --input_file .training-data/public-annotations/clinvar_selected_for_vep.vcf \
  --output_file .training-data/public-annotations/ensembl_vep_offline.jsonl
```

Install any optional VEP plugins and their data files locally if their features
are required. CADD, SIFT, PolyPhen and population-frequency fields may be absent
from a local VEP run when the relevant cache/plugin data is not installed; the
training metadata reports feature coverage and missingness. Do not fill missing
annotations with fabricated values.

4. Re-run the training script. It validates exact chromosome/position/REF/ALT
   matches between selected ClinVar variants and VEP's JSON `input` field,
   then caches normalized annotations locally.

```bash
python -m app.ml.clinvar_vep_train --vep-jsonl \
  .training-data/public-annotations/ensembl_vep_offline.jsonl
```

The script still needs its optional ML dependencies (`pip install -e '.[ml]'`).
The model is research-only and is not clinically validated. Public data downloads
are a separate preparation step; the model-training and annotation steps above
run locally once the source files and VEP cache are present.
