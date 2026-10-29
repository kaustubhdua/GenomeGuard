import base64
from dataclasses import replace

import pytest

from app.config import Settings, validate_settings


def secure_settings(**overrides):
    base = Settings(
        demo_mode=False,
        database_url="postgresql://genomeguard:test@localhost:5432/genomeguard",
        admin_api_key="a-unique-admin-secret-with-more-than-32-chars",
        master_key=base64.b64encode(b"x" * 32).decode(),
        allow_tamper_demo=False,
        real_cohort_file="/tmp/authorized-real-cohort.npz",
        dataset_id="approved-cohort-2026-01",
    )
    return replace(base, **overrides)


def test_non_demo_settings_accept_postgresql_and_secure_keys():
    validate_settings(secure_settings())


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"database_url": ""}, "GG_DATABASE_URL"),
        ({"database_url": "sqlite:///genomeguard.sqlite3"}, "GG_DATABASE_URL"),
        ({"admin_api_key": "demo-admin-key"}, "GG_ADMIN_API_KEY"),
        ({"admin_api_key": ""}, "GG_ADMIN_API_KEY"),
        ({"admin_api_key": "short-secret"}, "GG_ADMIN_API_KEY"),
        ({"master_key": ""}, "GG_MASTER_KEY"),
        ({"master_key": "not-base64"}, "GG_MASTER_KEY"),
        ({"master_key": base64.b64encode(b"short").decode()}, "GG_MASTER_KEY"),
        ({"allow_tamper_demo": True}, "GG_ALLOW_TAMPER_DEMO"),
        ({"real_cohort_file": ""}, "GG_REAL_COHORT_FILE"),
        ({"dataset_id": "synthetic-cohort-1"}, "GG_DATASET_ID"),
    ],
)
def test_non_demo_settings_reject_unsafe_values(overrides, message):
    with pytest.raises(ValueError, match=message):
        validate_settings(secure_settings(**overrides))


def test_synthetic_demo_mode_keeps_no_key_guided_demo_available():
    validate_settings(Settings(demo_mode=True, admin_api_key="demo-admin-key",
                               master_key="", allow_tamper_demo=True))
