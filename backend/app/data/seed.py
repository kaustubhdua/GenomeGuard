"""`make seed`: generate the synthetic cohort and write it to the database.

Usage: python -m app.data.seed [--donors 600 --variants 3000 --families 120 --seed 1337]
Re-running drops and recreates all tables, so the result is always reproducible from the seed.
"""

from __future__ import annotations

import argparse
import io
import json
from datetime import datetime

import numpy as np

from app.config import settings
from app.data.synth import generate, summarize


def _blob(row: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.savez_compressed(buf, g=row.astype(np.int8))
    return buf.getvalue()


def load_genotype(blob: bytes) -> np.ndarray:
    return np.load(io.BytesIO(blob))["g"]


def seed_database(engine=None, **kwargs) -> dict:
    from sqlalchemy.orm import Session

    from app import db, models

    engine = engine or db.engine
    db.Base.metadata.drop_all(engine)
    db.init_db(engine)
    p = {
        "n_donors": settings.n_donors,
        "n_variants": settings.n_variants,
        "n_populations": settings.n_populations,
        "n_families": settings.n_families,
        "seed": settings.seed,
        "n_planted": settings.n_planted_rare,
        "rare_maf": settings.rare_maf,
    }
    p.update(kwargs)
    c = generate(**p)
    now = datetime(2026, 1, 1)
    v = c.variants
    with Session(engine) as s:
        s.add_all(
            models.Variant(
                id=i + 1, chrom=str(v["chrom"][i]), pos=int(v["pos"][i]), ref=str(v["ref"][i]),
                alt=str(v["alt"][i]), maf=float(v["maf"][i]), is_rare=bool(v["is_rare"][i]),
            )
            for i in range(len(v["pos"]))
        )
        for d in c.donors:
            s.add(
                models.Donor(
                    id=d["id"], cohort_id=d["cohort_id"], population=d["population"],
                    consent_json=d["consent"], family_id=d["family_id"],
                    withdrawn_at=now if d["withdrawn"] else None,
                )
            )
            s.add(models.Genotype(donor_id=d["id"], genotype_blob=_blob(c.genotypes[d["id"] - 1])))
        s.add_all(
            models.Relationship(
                donor_a=r["donor_a"], donor_b=r["donor_b"], relation=r["relation"],
                meioses=r["meioses"], shared_fraction=r["shared"],
            )
            for r in c.relationships
        )
        s.commit()
    out = summarize(c)
    out["planted_variant_ids"] = [j + 1 for j in c.planted]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--donors", type=int, default=settings.n_donors)
    ap.add_argument("--variants", type=int, default=settings.n_variants)
    ap.add_argument("--families", type=int, default=settings.n_families)
    ap.add_argument("--seed", type=int, default=settings.seed)
    a = ap.parse_args()
    summary = seed_database(
        n_donors=a.donors, n_variants=a.variants, n_families=a.families, seed=a.seed
    )
    print("GenomeGuard synthetic cohort (ALL DATA IS SYNTHETIC)")
    print(f"database: {settings.database_url}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
