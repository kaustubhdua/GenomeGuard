# Public synthetic-demo image. It must never embed real participant or public-genotype cohorts.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
RUN pip install -e .
COPY frontend ./frontend
COPY docs ./docs
COPY scripts ./scripts
# The public demo is synthetic-only; research mode uses Dockerfile.research instead.
ENV GG_DB_PATH=/data/genomeguard.sqlite3 PORT=8000 GG_DEMO_MODE=true GG_ALLOW_TAMPER_DEMO=false GG_DATASET_ID=synthetic-cohort-1
RUN useradd -m app && mkdir -p /data && chown app /data
USER app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT}"]
