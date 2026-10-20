from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="GenomeGuard",
    version="0.1.0",
    description="Consent-aware, relative-aware governance layer for genomic data. "
    "All data is synthetic.",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "synthetic_data_only": True, "k_min": settings.k_min}
