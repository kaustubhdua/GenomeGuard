"""Validate live synthetic Beacon endpoint responses against pinned GA4GH Beacon v2 schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.validators import RefResolver

from tests.helpers import H, RESEARCHER, make_client


def validate(schema_root: Path, schema_name: str, payload: dict, label: str) -> None:
    schema_path = schema_root / "responses" / schema_name
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    resolver = RefResolver(base_uri=schema_path.resolve().as_uri(), referrer=schema)
    errors = sorted(Draft202012Validator(schema, resolver=resolver).iter_errors(payload),
                    key=lambda e: (list(e.absolute_path), e.message))
    if errors:
        details = "; ".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)
        raise AssertionError(f"{label} does not match {schema_name}: {details}")
    print(f"PASS {label}: {schema_name}")


def common_variant(service) -> dict:
    j = next(i for i in range(service.ds.n_variants)
             if service.ds.maf[i] >= 0.2 and i not in set(service.ds.planted))
    chrom, pos, _ref, alt = service.ds.coords[j]
    return {"referenceName": chrom, "start": pos, "alternateBases": alt}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: beacon_schema_smoke.py PATH_TO_BEACON_V2/framework/json")
    schema_root = Path(sys.argv[1]).resolve()

    # Positive boolean and count responses, each from an isolated demo service.
    for granularity, schema_name in (("boolean", "beaconBooleanResponse.json"),
                                     ("count", "beaconCountResponse.json")):
        service, client = make_client()
        params = {**common_variant(service), "requestedGranularity": granularity}
        response = client.get("/beacon/g_variants", params=params, headers=H(RESEARCHER))
        assert response.status_code == 200, (response.status_code, response.text)
        validate(schema_root, schema_name, response.json(), f"{granularity} success")

    # A valid no-hit response must use the same response envelope.
    _, client = make_client()
    response = client.get("/beacon/g_variants",
                          params={"referenceName": "not-a-real-contig", "start": 1},
                          headers=H(RESEARCHER))
    assert response.status_code == 200, (response.status_code, response.text)
    validate(schema_root, "beaconBooleanResponse.json", response.json(), "boolean no-hit")

    # Denials and malformed requests use BeaconErrorResponse, not a null exists value.
    service, client = make_client()
    params = {**common_variant(service), "purpose": "disease_research",
              "disease": "not_a_real_disease"}
    response = client.get("/beacon/g_variants", params=params, headers=H(RESEARCHER))
    assert response.status_code in (403, 503), (response.status_code, response.text)
    validate(schema_root, "beaconErrorResponse.json", response.json(), "governance denial")

    response = client.get("/beacon/g_variants",
                          params={**common_variant(service), "purpose": "not_a_supported_research_purpose"},
                          headers=H(RESEARCHER))
    assert response.status_code == 422, (response.status_code, response.text)
    validate(schema_root, "beaconErrorResponse.json", response.json(), "invalid purpose")

    response = client.get("/beacon/g_variants", headers=H(RESEARCHER))
    assert response.status_code == 422, (response.status_code, response.text)
    validate(schema_root, "beaconErrorResponse.json", response.json(), "malformed request")

    response = client.get("/beacon/g_variants",
                          params=common_variant(service))
    assert response.status_code == 401, (response.status_code, response.text)
    validate(schema_root, "beaconErrorResponse.json", response.json(), "authentication error")

    print("Beacon v2 schema smoke passed against pinned GA4GH schemas.")


if __name__ == "__main__":
    main()
