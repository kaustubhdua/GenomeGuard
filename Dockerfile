FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
RUN pip install -e .
COPY frontend ./frontend
COPY docs ./docs
# Build a small cohort from the official public 1000 Genomes VCF at image-build time.
# Only the derived cohort is retained in the image; the downloaded source VCF and panel are removed.
# The policy is dataset-level public-release provenance, not participant-specific consent.
RUN python -m app.data.real build \
      --consent-policy-json docs/policies/igsr-1000-genomes-public-release.json \
      --out /app/data_real/1000g_phase3_chr22.npz --samples 600 --variants 3000 \
    && rm -f /app/data_real/chr22.vcf.gz /app/data_real/samples.ped
COPY scripts ./scripts
# Secrets come from the environment at run time, never from the image.
# GG_MASTER_KEY: base64 of 32 random bytes (python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
# GG_ADMIN_API_KEY: the steward key.
ENV GG_DB_PATH=/data/genomeguard.sqlite3 PORT=8000 GG_REAL_COHORT_FILE=/app/data_real/1000g_phase3_chr22.npz GG_DATASET_ID=igsr-1000g-phase3-public-release
RUN useradd -m app && mkdir -p /data && chown app /data
USER app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT}"]
