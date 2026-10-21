FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
RUN pip install -e .
COPY frontend ./frontend
COPY docs ./docs
COPY scripts ./scripts
# Secrets come from the environment at run time, never from the image.
# GG_MASTER_KEY: base64 of 32 random bytes (python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
# GG_ADMIN_API_KEY: the steward key.
ENV GG_DB_PATH=/data/genomeguard.sqlite3 PORT=8000
RUN useradd -m app && mkdir -p /data && chown app /data
USER app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT}"]
