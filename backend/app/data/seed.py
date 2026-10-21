"""`make seed`: create (or recreate) the database with the cohort and demo accounts, and print a
summary. Synthetic by default; set GG_REAL_COHORT_FILE to seed from a real 1000 Genomes build.

    python -m app.data.seed [--keep]      (default drops the existing database first)
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from app.config import get_settings
from app.service import bootstrap


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="do not delete an existing database")
    a = ap.parse_args()
    s = get_settings()
    if not a.keep and Path(s.db_path).exists():
        os.remove(s.db_path)
    svc = bootstrap(s)
    ds = svc.ds
    use = Counter(d.consent["use"] for d in ds.donors)
    summary = {
        "database": s.db_path,
        "source": f"real cohort {s.real_cohort_file} (consent simulated)"
        if s.real_cohort_file else "SYNTHETIC (all data is generated)",
        "donors": ds.n_donors, "variants": ds.n_variants,
        "families": len({d.family_id for d in ds.donors}),
        "populations": dict(Counter(d.population for d in ds.donors)),
        "rare_variants_(MAF<1%)": int((ds.maf < svc.p.rare_maf).sum()),
        "consent_use": dict(use), "withdrawn": sum(d.withdrawn for d in ds.donors),
        "related_pairs": len(ds.relationships),
        "planted_demo_variants": len(ds.planted),
        "audit_chain_ok": svc.audit.verify()["ok"],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
