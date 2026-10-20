"""Shared builders for service/API tests (no pytest fixtures, so tests stay simple)."""

import warnings

from starlette.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.service import bootstrap

warnings.filterwarnings("ignore", message="GG_MASTER_KEY")

RESEARCHER, ATTACKER, ANON, CONTROLLED = ("demo-researcher", "demo-attacker", "demo-anonymous",
                                          "demo-controlled")
ADMIN = {"X-Admin-Key": "demo-admin-key"}

DEMO_REQ = {"purpose": "disease_research", "disease": "diabetes", "data_level": "frequency",
            "cohort_filter": {}, "variant_filter": {"min_maf": 0.1, "limit": 20,
                                                    "include_planted": 2}}


def make_service(**kw):
    s = Settings()
    s.db_path = ":memory:"
    s.n_donors, s.n_variants, s.n_families = 300, 800, 60
    for k, v in kw.items():
        setattr(s, k, v)
    return bootstrap(s)


def make_client(**kw):
    svc = make_service(**kw)
    return svc, TestClient(create_app(svc))


def H(key):
    return {"X-API-Key": key}


def attack_queries(n=6):
    """A probing account: same narrow cell, tiny variations in consent flags and variant set."""
    cell = {"cohort_id": "DIABETES-STUDY", "population": "POP_A"}
    diseases = ["diabetes", "cancer", "diabetes", "cardiovascular", "cancer", "diabetes"]
    return [{"purpose": "disease_research", "disease": diseases[i % 6], "is_commercial": i % 2 == 1,
             "data_level": "frequency", "cohort_filter": cell,
             "variant_filter": {"min_maf": 0.1, "limit": 20 + (i % 3)}} for i in range(n)]
