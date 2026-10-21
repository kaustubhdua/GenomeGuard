"""Load a REAL open dataset (1000 Genomes) into the same cohort format the synthetic generator
produces, so every other module (consent, risk, transform, anomaly, audit, UI) runs unchanged.

Run on YOUR machine (the build sandbox cannot reach the internet):

    python -m app.data.real build --out data_real/1000g_chr22.npz            # downloads, ~200 MB
    python -m app.data.real build --vcf my.vcf.gz --ped my.ped --out ...      # use local files
    GG_REAL_COHORT_FILE=data_real/1000g_chr22.npz make run

What is real and what is not (state this on any slide that mentions it):
  * REAL: genotypes, allele frequencies, population labels, and any parent/child links present in
    the pedigree file. 1000 Genomes participants consented to open public release.
  * SIMULATED: consent records. 1000 Genomes has no per-donor DUO consent, so each real genome is
    given a synthetic consent record (flagged `consent_simulated` in the file's metadata).
  * The Phase 3 release was built from deliberately UNRELATED people, so with the default files
    there are almost no relative pairs and the family-exposure demo will be sparse. For real
    families use the IGSR high-coverage release that includes 602 trios, by passing --vcf and
    --ped for it. Check IGSR's data-use terms before redistributing any rows; never commit them.

Parsing is plain Python (gzip + csv): no compiled VCF libraries needed.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

import numpy as np

from app.data import pedigree as ped
from app.data.synth import SyntheticCohort, _consent

BASE = "https://ftp.1000genomes.ebi.ac.uk/vol1/ftp"
RELEASE_DIR = f"{BASE}/release/20130502/"
PED_URL = f"{BASE}/technical/working/20130606_sample_info/20130606_g1k.ped"
VCF_NAME_RE = r"ALL\.chr{chrom}\.phase3_shapeit2_mvncall_integrated_v5[a-z]\.20130502\.genotypes\.vcf\.gz"


# ------------------------------------------------------------------------------ downloading

def download(url: str, dest: Path) -> Path:
    if dest.exists():
        print(f"using cached {dest}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        total, got = int(r.headers.get("Content-Length") or 0), 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            got += len(chunk)
            if total:
                print(f"\r  {got / 1e6:.0f}/{total / 1e6:.0f} MB", end="", file=sys.stderr)
    tmp.rename(dest)
    print()
    return dest


def resolve_vcf_url(chrom: str = "22") -> str:
    """Find the exact chromosome file name from the release directory listing instead of
    guessing the version letter (v5a / v5b)."""
    with urllib.request.urlopen(RELEASE_DIR, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    names = sorted(set(re.findall(VCF_NAME_RE.format(chrom=chrom), html)))
    if not names:
        raise RuntimeError(f"no chr{chrom} genotype VCF found in {RELEASE_DIR}; pass --vcf")
    return RELEASE_DIR + names[-1]


# ------------------------------------------------------------------------------ pedigree file

def parse_ped(text: str) -> dict[str, dict]:
    """1000 Genomes .ped (tab separated, header row). Returns sample -> info. Columns are found
    by header name so extra columns do not matter."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    header = [h.strip().lower() for h in lines[0].split("\t")]

    def col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        raise ValueError(f"pedigree file lacks any of {names}; header was {header}")

    i_fam, i_ind = col("family id", "familyid"), col("individual id", "individualid")
    i_pat, i_mat = col("paternal id", "paternalid"), col("maternal id", "maternalid")
    i_pop = col("population", "pop")
    out = {}
    for ln in lines[1:]:
        f = ln.split("\t")
        if len(f) <= max(i_fam, i_ind, i_pat, i_mat, i_pop):
            continue
        none = ("0", "", ".")
        out[f[i_ind]] = {"family": f[i_fam], "father": None if f[i_pat] in none else f[i_pat],
                         "mother": None if f[i_mat] in none else f[i_mat], "pop": f[i_pop]}
    return out


def relationships_from_pedigree(info: dict[str, dict], registered: list[str]) -> list[dict]:
    """Relative pairs among `registered` sample ids, derived from the pedigree with the SAME
    kinship model as the synthetic data (expected averages; real sharing varies)."""
    ids = list(info)
    for s in registered:
        if s not in info:
            ids.append(s)
            info = {**info, s: {"family": s, "father": None, "mother": None, "pop": ""}}
    # topological order: parents before children
    order, seen = [], set()

    def visit(s, stack=()):
        if s in seen or s in stack:
            return
        for p in (info[s]["father"], info[s]["mother"]):
            if p in info:
                visit(p, (*stack, s))
        seen.add(s)
        order.append(s)

    for s in ids:
        visit(s)
    pid = {s: i for i, s in enumerate(order)}
    people = [ped.Person(pid[s], 0, "U", pid.get(info[s]["father"]), pid.get(info[s]["mother"]))
              for s in order]
    idx = {s: i + 1 for i, s in enumerate(registered)}  # donor ids are 1-based
    out = []
    inv = {v: k for k, v in pid.items()}
    for a, b, name, meioses, shared in ped.pedigree_relationships(
            people, sorted(pid[s] for s in registered)):
        out.append({"donor_a": idx[inv[a]], "donor_b": idx[inv[b]], "relation": name,
                    "meioses": meioses, "shared": shared})
    return out


# ------------------------------------------------------------------------------ VCF parsing

def _open_text(path: Path):
    if str(path).endswith((".gz", ".bgz")):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8")
    return open(path, encoding="utf-8")


def vcf_samples(path: Path) -> list[str]:
    with _open_text(path) as f:
        for line in f:
            if line.startswith("#CHROM"):
                return line.rstrip("\n").split("\t")[9:]
    raise ValueError("no #CHROM header line in VCF")


_GT = {"0|0": 0, "0|1": 1, "1|0": 1, "1|1": 2, "0/0": 0, "0/1": 1, "1/0": 1, "1/1": 2}


def read_vcf(path: Path, sample_ids: list[str], keep_prob: float, max_variants: int,
             rng: np.random.Generator) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Stream the VCF once. Keep each biallelic SNP with probability `keep_prob`, up to
    `max_variants`. Returns (variant columns, genotypes[n_samples, n_variants] of alt counts)."""
    header = vcf_samples(path)
    col = {s: i for i, s in enumerate(header)}
    missing = [s for s in sample_ids if s not in col]
    if missing:
        raise ValueError(f"{len(missing)} requested samples are not in the VCF, e.g. {missing[:3]}")
    take = [9 + col[s] for s in sample_ids]
    chrom, pos, ref, alt, cols = [], [], [], [], []
    with _open_text(path) as f:
        for line in f:
            if line.startswith("#"):
                continue
            if rng.random() >= keep_prob:  # cheap rejection before any parsing
                continue
            fields = line.rstrip("\n").split("\t")
            r, a = fields[3], fields[4]
            if len(r) != 1 or len(a) != 1 or a not in "ACGT" or r not in "ACGT":
                continue  # SNPs only, biallelic only
            try:
                g = [_GT[fields[i][:3]] for i in take]
            except KeyError:
                continue  # missing / unphased oddities: skip the site
            chrom.append(fields[0])
            pos.append(int(fields[1]))
            ref.append(r)
            alt.append(a)
            cols.append(g)
            if len(cols) >= max_variants:
                break
    if not cols:
        raise ValueError("no usable variants found; raise --keep-prob")
    G = np.array(cols, dtype=np.int8).T
    return {"chrom": np.array(chrom), "pos": np.array(pos), "ref": np.array(ref),
            "alt": np.array(alt)}, G


# ------------------------------------------------------------------------------ build / load

def build_cohort(vcf: Path, ped_text: str, n_samples: int = 600, max_variants: int = 3000,
                 keep_prob: float = 0.004, seed: int = 1337, rare_maf: float = 0.01,
                 withdrawn_rate: float = 0.03) -> tuple[SyntheticCohort, dict]:
    rng = np.random.default_rng(seed)
    info = parse_ped(ped_text)
    in_vcf = [s for s in vcf_samples(vcf) if s in info]
    if len(in_vcf) < 30:
        raise ValueError("fewer than 30 VCF samples have pedigree/population info")
    n = min(n_samples, len(in_vcf))
    chosen = sorted(rng.choice(in_vcf, size=n, replace=False).tolist())
    cols, G = read_vcf(vcf, chosen, keep_prob, max_variants, rng)
    freq = G.sum(axis=0) / (2.0 * n)
    maf = np.minimum(freq, 1 - freq)
    donors = []
    for i, s in enumerate(chosen, start=1):
        pop = info[s]["pop"] or "UNK"
        donors.append({"id": i, "cohort_id": "1000G-" + pop, "population": pop,
                       "consent": _consent(rng, pop),  # SIMULATED consent
                       "family_id": i, "withdrawn": bool(rng.random() < withdrawn_rate)})
    fam_of = {}
    for d, s in zip(donors, chosen, strict=True):
        d["family_id"] = fam_of.setdefault(info[s]["family"], len(fam_of) + 1)
    rels = relationships_from_pedigree(info, chosen)
    variants = {**cols, "maf": maf, "is_rare": maf < rare_maf,
                "planted": np.zeros(len(maf), dtype=bool)}
    meta = {"source": "1000 Genomes (IGSR)", "samples": n, "variants": int(G.shape[1]),
            "relative_pairs": len(rels), "consent_simulated": True, "genotypes_real": True,
            "seed": seed}
    return SyntheticCohort(donors, G, variants, rels, [], seed), meta


def save_cohort(c: SyntheticCohort, meta: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, genotypes=c.genotypes,
                        **{f"v_{k}": np.asarray(v) for k, v in c.variants.items()},
                        donors=json.dumps(c.donors), relationships=json.dumps(c.relationships),
                        meta=json.dumps(meta))


def load_cohort(path: str | Path) -> SyntheticCohort:
    z = np.load(path, allow_pickle=False)
    variants = {k[2:]: z[k] for k in z.files if k.startswith("v_")}
    return SyntheticCohort(json.loads(str(z["donors"])), z["genotypes"], variants,
                           json.loads(str(z["relationships"])), [], 0)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--vcf", help="local VCF(.gz); default: download 1000G chr22")
    b.add_argument("--ped", help="local pedigree file or URL; default: 1000G sample info")
    b.add_argument("--chrom", default="22")
    b.add_argument("--out", default="data_real/1000g_chr22.npz")
    b.add_argument("--samples", type=int, default=600)
    b.add_argument("--variants", type=int, default=3000)
    b.add_argument("--keep-prob", type=float, default=0.004)
    b.add_argument("--seed", type=int, default=1337)
    a = ap.parse_args(argv)
    cache = Path("data_real")
    vcf = Path(a.vcf) if a.vcf else download(resolve_vcf_url(a.chrom),
                                              cache / f"chr{a.chrom}.vcf.gz")
    if a.ped and Path(a.ped).exists():
        ped_text = Path(a.ped).read_text()
    else:
        ped_text = download(a.ped or PED_URL, cache / "samples.ped").read_text()
    c, meta = build_cohort(vcf, ped_text, a.samples, a.variants, a.keep_prob, a.seed)
    save_cohort(c, meta, Path(a.out))
    print(json.dumps(meta, indent=2))
    print(f"wrote {a.out}\nrun with: GG_REAL_COHORT_FILE={a.out} make run")
    if meta["relative_pairs"] == 0:
        print("note: no relative pairs found (expected for the unrelated Phase 3 samples); the "
              "family-exposure demo will be empty. See the module docstring for trio data.")


if __name__ == "__main__":
    main()
