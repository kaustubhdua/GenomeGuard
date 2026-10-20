from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.db import Base, init_db
from app.main import app


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["synthetic_data_only"] is True


def test_all_tables_created():
    engine = create_engine("sqlite://")
    init_db(engine)
    names = set(inspect(engine).get_table_names())
    expected = {
        "donors", "genotypes", "relationships", "variants", "requesters", "requests",
        "decisions", "epsilon_ledger", "audit_log", "alerts",
    }
    assert expected <= names
    assert expected <= set(Base.metadata.tables)
