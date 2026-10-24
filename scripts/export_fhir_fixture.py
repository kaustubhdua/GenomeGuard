"""Export one synthetic donor Consent resource for external FHIR R4 validation.

This creates only a synthetic demo record. It must not be used to export real participant data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import Settings
from app.service import bootstrap


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/tmp/genomeguard-consent-r4.json")
    args = parser.parse_args()
    settings = Settings()
    settings.db_path = ":memory:"
    settings.n_donors, settings.n_variants, settings.n_families = 300, 800, 60
    service = bootstrap(settings)
    donor = next(d for d in service.ds.donors
                 if not d.withdrawn and d.consent.get("use") == "DS")
    resource = service.donor_consent_fhir(donor.id)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(resource, indent=2) + "\n", encoding="utf-8")
    print(f"Exported one synthetic FHIR R4 Consent resource to {output}")
    print(f"resourceType={resource['resourceType']} status={resource['status']} simulated=true")


if __name__ == "__main__":
    main()
