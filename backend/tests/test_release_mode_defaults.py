"""Release-mode defaults must fail closed for non-demo cohort data."""

from app.config import Settings
from app.service import _release_enabled_for_mode
from tests.helpers import make_client


def test_governed_release_is_enabled_only_for_synthetic_demo_mode():
    settings = Settings()
    settings.demo_mode = True
    assert _release_enabled_for_mode(settings) is True

    settings.demo_mode = False
    assert _release_enabled_for_mode(settings) is False


def test_variant_search_uses_verified_public_catalogue_when_release_is_disabled(monkeypatch):
    service, client = make_client()
    service.release_enabled = False
    chromosome, position, _reference, _alternate = service.ds.coords[0]
    calls = []

    def public_lookup(chrom, pos, reference=None, alternate=None):
        calls.append((chrom, pos, reference, alternate))
        return [{"source": "verified-public-reference", "variant_id": "public-variant-1"}]

    monkeypatch.setattr(
        service.store, "verified_public_variant_search", public_lookup, raising=False,
    )
    response = client.get(f"/variants/search?q={chromosome}:{position}")

    assert response.status_code == 200
    assert response.json()["matches"] == [
        {"source": "verified-public-reference", "variant_id": "public-variant-1"}
    ]
    assert calls == [(chromosome, position, None, None)]
