"""Load a REAL open dataset (1000 Genomes) into the same cohort format the synthetic generator
produces, so every other module (consent, risk, transform, anomaly, audit, UI) runs unchanged.

Run on a machine with internet access; the hosted CI workflow verifies the official download path:

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
import hashlib
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
PED_URL = f"{RELEASE_DIR}integrated_call_samples_v3.20130502.ALL.panel"
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

def _norm(h: str) -> str:
    return re.sub(r"[\s_\-]+", "", h.strip().lower())


# header aliases, after lower-casing and removing spaces/underscores. The original 1000 Genomes
# .ped uses "Family ID / Individual ID / Paternal ID / Maternal ID / Population"; the 3,202-sample
# high-coverage pedigree is understood to use "FamilyID / SampleID / FatherID / MotherID /
# Population" (check the header of the file you download: the loader fails loudly if none match).
_ALIASES = {
    "family": ("familyid",),
    "individual": ("individualid", "sampleid", "sample", "iid"),
    "father": ("paternalid", "fatherid", "father", "pat"),
    "mother": ("maternalid", "motherid", "mother", "mat"),
    "pop": ("population", "pop"),
}


def parse_ped(text: str) -> dict[str, dict]:
    """1000 Genomes pedigree file (tab- or whitespace-separated, header row). Returns
    sample -> info. Columns are found by header name, so extra columns do not matter."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("pedigree file is empty")
    sep = "\t" if "\t" in lines[0] else None  # None = any whitespace
    split = (lambda ln: ln.rstrip("\n").split("\t")) if sep else (lambda ln: ln.split())
    header = [_norm(h) for h in split(lines[0])]

    def col(key: str, required: bool = True) -> int | None:
        for name in _ALIASES[key]:
            if name in header:
                return header.index(name)
        if required:
            raise ValueError(f"pedigree file lacks a {key} column; header was {header}")
        return None

    i_fam = col("family", required=False)
    i_ind = col("individual")
    i_pop = col("pop")
    # The official Phase 3 sample panel has sample/population labels but no pedigree columns.
    # Treat each sample as unrelated instead of relying on a technical/working-only file.
    # If a family column is present, this is a pedigree file and parent columns remain required.
    i_pat = col("father", required=i_fam is not None)
    i_mat = col("mother", required=i_fam is not None)
    need = max(i_ind, i_pop, *(i for i in (i_fam, i_pat, i_mat) if i is not None))
    none = ("0", "", ".", "NA", "na")
    out = {}
    for ln in lines[1:]:
        f = split(ln)
        if len(f) <= need:
            continue
        sample = f[i_ind]
        family = f[i_fam] if i_fam is not None else sample
        father = f[i_pat] if i_pat is not None else None
        mother = f[i_mat] if i_mat is not None else None
        out[sample] = {
            "family": family,
            "father": None if father in none else father,
            "mother": None if mother in none else mother,
            "pop": f[i_pop],
        }
    return out


def choose_samples(info: dict[str, dict], available: list[str], n: int,
                   rng: np.random.Generator, family_first: bool) -> list[str]:
    """Pick n samples. With family_first, whole families that have two or more members in the
    VCF are taken first (so real parent/child and sibling links exist), then the rest are filled
    with random unrelated people. This makes the cohort FAMILY-ENRICHED by design; it is recorded
    in the cohort metadata so no slide can imply it mirrors the general population."""
    if not family_first:
        return sorted(rng.choice(available, size=n, replace=False).tolist())
    have = set(available)
    fam: dict[str, list[str]] = {}
    for s in available:
        fam.setdefault(info[s]["family"], []).append(s)
    multi = [sorted(m) for m in fam.values() if len(m) >= 2]
    singles = sorted(m[0] for m in fam.values() if len(m) == 1)
    order = rng.permutation(len(multi))
    chosen: list[str] = []
    for i in order:
        if len(chosen) + len(multi[i]) <= n:
            chosen.extend(multi[i])
    # then top up with unrelated people
    pool = [s for s in singles if s not in set(chosen)]
    rng.shuffle(pool)
    chosen.extend(pool[: n - len(chosen)])
    if len(chosen) < n:  # not enough singles: fill from anyone left
        rest = sorted(have - set(chosen))
        chosen.extend(rng.choice(rest, size=min(n - len(chosen), len(rest)),
                                 replace=False).tolist())
    return sorted(chosen)


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

def sha256_file(path: Path) -> str:
    """Hash a source file in bounded memory for reproducible data provenance."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_cohort(vcf: Path, ped_text: str, n_samples: int = 600, max_variants: int = 3000,
                 keep_prob: float = 0.004, seed: int = 1337, rare_maf: float = 0.01,
                 withdrawn_rate: float = 0.03, family_first: bool = False,
                 source_metadata_file: str = "provided-sample-metadata",
                 source_vcf_file: str | None = None) -> tuple[SyntheticCohort, dict]:
    rng = np.random.default_rng(seed)
    info = parse_ped(ped_text)
    in_vcf = [s for s in vcf_samples(vcf) if s in info]
    if len(in_vcf) < 30:
        raise ValueError("fewer than 30 VCF samples have pedigree/population info")
    n = min(n_samples, len(in_vcf))
    chosen = choose_samples(info, in_vcf, n, rng, family_first)
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
            "family_enriched": bool(family_first and rels), "seed": seed,
            "build_parameters": {"requested_samples": n_samples, "max_variants": max_variants,
                                 "keep_prob": keep_prob, "rare_maf": rare_maf,
                                 "withdrawn_rate": withdrawn_rate},
            "source_vcf_file": source_vcf_file or vcf.name, "source_vcf_sha256": sha256_file(vcf),
            "source_sample_metadata_file": source_metadata_file,
            "source_sample_metadata_sha256": hashlib.sha256(ped_text.encode("utf-8")).hexdigest(),
            "pedigree_relationships_present": bool(rels)}
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


def read_meta(path: str | Path) -> dict:
    """The metadata saved with a cohort file (source, whether genotypes are real, ...). Whether a
    dataset may be called real is decided by THIS, never by the fact that a file was supplied."""
    z = np.load(path, allow_pickle=False)
    return json.loads(str(z["meta"])) if "meta" in z.files else {}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--vcf", help="local VCF(.gz); default: download 1000G chr22")
    b.add_argument("--source-vcf-name", help="original source filename when --vcf is a renamed local cache")
    b.add_argument("--ped", help="local pedigree file or URL; default: official Phase 3 sample/population panel (unrelated samples)")
    b.add_argument("--chrom", default="22")
    b.add_argument("--out", default="data_real/1000g_chr22.npz")
    b.add_argument("--samples", type=int, default=600)
    b.add_argument("--variants", type=int, default=3000)
    b.add_argument("--keep-prob", type=float, default=0.004)
    b.add_argument("--seed", type=int, default=1337)
    b.add_argument("--no-family-first", action="store_true",
                   help="sample at random instead of taking whole families first")
    a = ap.parse_args(argv)
    cache = Path("data_real")
    if a.vcf:
        vcf = Path(a.vcf)
        source_vcf_name = a.source_vcf_name or vcf.name
    else:
        vcf_url = resolve_vcf_url(a.chrom)
        source_vcf_name = a.source_vcf_name or vcf_url.rsplit("/", 1)[-1]
        vcf = download(vcf_url, cache / f"chr{a.chrom}.vcf.gz")
    if a.ped and Path(a.ped).exists():
        ped_path = Path(a.ped)
        ped_text = ped_path.read_text()
        metadata_file = ped_path.name
    else:
        metadata_url = a.ped or PED_URL
        ped_text = download(metadata_url, cache / "samples.ped").read_text()
        metadata_file = metadata_url.rsplit("/", 1)[-1]
    c, meta = build_cohort(vcf, ped_text, a.samples, a.variants, a.keep_prob, a.seed,
                           family_first=not a.no_family_first, source_metadata_file=metadata_file,
                           source_vcf_file=source_vcf_name)
    save_cohort(c, meta, Path(a.out))
    print(json.dumps(meta, indent=2))
    print(f"wrote {a.out}\nrun with: GG_REAL_COHORT_FILE={a.out} make run")
    if meta["relative_pairs"] == 0:
        print("note: no relative pairs found (expected for the unrelated Phase 3 samples); the "
              "family-exposure demo will be empty. See the module docstring for trio data.")


if __name__ == "__main__":
    main()
