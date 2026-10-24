import base64
from dataclasses import replace

import pytest

from app.config import Settings, validate_settings


def secure_settings(**overrides):
    base = Settings(
        demo_mode=False,
        admin_api_key="a-unique-admin-secret-with-more-than-32-chars",
        master_key=base64.b64encode(b"x" * 32).decode(),
        allow_tamper_demo=False,
    )
    return replace(base, **overrides)


def test_non_demo_settings_accept_unique_admin_key_and_32_byte_master_key():
    validate_settings(secure_settings())


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"admin_api_key": "demo-admin-key"}, "GG_ADMIN_API_KEY"),
        ({"admin_api_key": ""}, "GG_ADMIN_API_KEY"),
        ({"admin_api_key": "short-secret"}, "GG_ADMIN_API_KEY"),
        ({"master_key": ""}, "GG_MASTER_KEY"),
        ({"master_key": "not-base64"}, "GG_MASTER_KEY"),
        ({"master_key": base64.b64encode(b"short").decode()}, "GG_MASTER_KEY"),
        ({"allow_tamper_demo": True}, "GG_ALLOW_TAMPER_DEMO"),
    ],
)
def test_non_demo_settings_reject_unsafe_values(overrides, message):
    with pytest.raises(ValueError, match=message):
        validate_settings(secure_settings(**overrides))


def test_synthetic_demo_mode_keeps_no_key_guided_demo_available():
    validate_settings(Settings(demo_mode=True, admin_api_key="demo-admin-key",
                               master_key="", allow_tamper_demo=True))
