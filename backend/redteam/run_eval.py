"""`make eval`: run every red-team experiment with fixed seeds and write
docs/eval-results.json (served to the UI) and docs/eval-results.md (generated: never hand-edited,
so every number in it is reproducible by re-running this command).

    python -m redteam.run_eval            # full run (about 1 minute)
    python -m redteam.run_eval --quick    # CI smoke test: few trials, writes nothing unless --write
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.core.dataset import Dataset
from app.core.params import DEFAULT
from redteam import attacks as A
from redteam.benign_traffic import run_benign

DOCS = Path(__file__).resolve().parents[2] / "docs"
MAIN_SEED = 1337
ROBUSTNESS_SEEDS = (2024, 7, 99)
MI_GRID_V = (25, 100, 500)
MI_EPS = (0.5, 1.0, 5.0, 20.0, 100.0)
TRI_GAPS = (5.0, 30.0, 120.0, 600.0, 1200.0)
BEACON_SIZES = (1, 3, 10, 30)


def load_dataset(cohort: str | None) -> tuple[Dataset, dict]:
    """The synthetic cohort by default, or a cohort file built by `python -m app.data.real build`.
    The file's SHA-256 goes into the results so anyone can check they ran on the same data."""
    if not cohort:
        return Dataset.synthetic(seed=MAIN_SEED), {"dataset": "synthetic"}
    from app.data.real import load_cohort, read_meta

    path = Path(cohort)
    meta = read_meta(path)
    is_real = bool(meta.get("genotypes_real"))  # the file's own metadata decides, not its existence
    ds = Dataset.from_cohort(load_cohort(path), "1000g-real" if is_real else "custom-cohort")
    return ds, {"dataset": "real_1000g" if is_real else "custom_cohort", "genotypes_real": is_real,
                "consent_simulated": bool(meta.get("consent_simulated", True)),
                "family_enriched": bool(meta.get("family_enriched")), "cohort_file": path.name,
                "cohort_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def run_all(quick: bool = False, cohort: str | None = None) -> dict:
    t = (lambda full, small: small) if quick else (lambda full, small: full)
    ds, label = load_dataset(cohort)
    out: dict = {
        "meta": {**label, "seed": MAIN_SEED, "donors": ds.n_donors,
                 "variants": ds.n_variants, "quick": quick,
                 "params": {"k_min": DEFAULT.k_min, "maf_floor": DEFAULT.maf_floor,
                            "freq_bin_width": DEFAULT.freq_bin_width,
                            "epsilon_budget": DEFAULT.epsilon_budget,
                            "epsilon_per_release": DEFAULT.epsilon_per_release,
                            "max_variants_noised": DEFAULT.max_variants_noised},
                 "command": "make eval-real COHORT=" + str(cohort) if cohort else "make eval"},
    }
    out["differencing"] = A.differencing_attack(ds, trials=t(100, 8))

    mi = []
    for V in MI_GRID_V:
        configs = [("raw", None, None), ("binned", 0.05, None)] + [
            (f"binned+eps={e}", 0.05, e) for e in MI_EPS]
        for name, bw, eps in configs:
            r = A.membership_inference(ds, n=100, V=V, bin_w=bw, eps=eps, trials=t(30, 3))
            r["config"] = name
            mi.append(r)
    out["membership"] = mi

    out["triangulation"] = [A.triangulation_attack(g, trials=t(60, 5)) for g in TRI_GAPS] + [
        A.triangulation_attack(5.0, trials=t(60, 5), monitor_on=False)]
    out["beacon"] = [A.beacon_update_flip(ds, u, m, trials=t(40, 5))
                     for u in BEACON_SIZES for m in ("boolean", "count", "genomeguard")]
    out["benign"] = run_benign(ds, sessions=t(500, 40))

    rob = []
    # robustness varies the synthetic generator's seed, so it only applies to synthetic data
    for seed in ([] if cohort else ROBUSTNESS_SEEDS[: t(3, 1)]):
        d2 = Dataset.synthetic(seed=seed)
        diff = A.differencing_attack(d2, trials=t(40, 4))
        raw = A.membership_inference(d2, 100, 100, None, None, trials=t(15, 2))
        dp = A.membership_inference(d2, 100, 25, 0.05, 0.5, trials=t(15, 2))
        tri = A.triangulation_attack(5.0, trials=t(30, 3))
        ben = run_benign(d2, sessions=t(150, 20), seed=seed)
        rob.append({"dataset_seed": seed,
                    "differencing_none": diff["accuracy"]["none"]["mean"],
                    "differencing_guarded": diff["accuracy"]["ladder_plus_guard"]["mean"],
                    "differencing_baseline": diff["accuracy"]["baseline"]["mean"],
                    "membership_auc_raw_V100": raw["auc"], "membership_auc_dp_V25": dp["auc"],
                    "triangulation_frozen_rate": tri["frozen_rate"],
                    "benign_flag_rate": ben["monitor_flag_rate"]})
    out["robustness"] = rob
    return out


# ---------------------------------------------------------------------------- markdown report
def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def to_markdown(r: dict) -> str:
    m, d = r["meta"], r["differencing"]
    acc = d["accuracy"]
    real = m.get("dataset") == "real_1000g"
    custom = m.get("dataset") == "custom_cohort"
    L = [
        "# Evaluation results",
        "",
        f"_Generated by `{m.get('command', 'make eval')}` (`backend/redteam/run_eval.py`). Do not "
        "edit by hand: re-run the command and every number below is reproduced from fixed seeds._",
        "",
        (f"Dataset: **1000 Genomes, real genotypes** ({m['donors']} donors, {m['variants']} variants"
         f"{', family-enriched by design' if m.get('family_enriched') else ''}; "
         f"consent records and query traffic are simulated; cohort file `{m['cohort_file']}`, "
         f"SHA-256 `{m['cohort_sha256'][:16]}...`; attack seed {m['seed']})." if real else
         f"Dataset: **custom cohort file, not marked as real genotypes** ({m['donors']} donors, "
         f"{m['variants']} variants; cohort file `{m['cohort_file']}`, SHA-256 "
         f"`{m['cohort_sha256'][:16]}...`; attack seed {m['seed']})." if custom else
         f"Dataset: **synthetic** ({m['donors']} donors, {m['variants']} variants, seed "
         f"{m['seed']}).") + f" Parameters: k_min={m['params']['k_min']}, MAF floor "
        f"{m['params']['maf_floor']}, bin width {m['params']['freq_bin_width']}, epsilon budget "
        f"{m['params']['epsilon_budget']}, epsilon per release {m['params']['epsilon_per_release']}, "
        f"at most {m['params']['max_variants_noised']} variants per noised release.",
        "",
        "## What these results do NOT show",
        "",
        ("- The genotypes are real, but they are a small sample (often family-enriched on purpose), "
         "consent records and query traffic are simulated, and results from one cohort do not carry "
         "over to another population or size." if real else
         "- This cohort file does not say its genotypes are real, so do not describe these as "
         "real-data results." if custom else
         "- All data is synthetic. Real genomes have linkage disequilibrium, population structure "
         "and relatives that this generator only approximates, so real attack success could differ "
         "in either direction."),
        "- The attackers are simplified and written by the same people as the defences. The "
        "triangulation attacker is the shape the monitor was designed to catch; the slow-attacker "
        "rows below show where it stops working.",
        "- The beacon experiment is a simplified replication of the update-flip idea "
        "(arXiv:2001.08852): no genome clustering is attempted, so the precision and recall "
        "reported are not the paper's.",
        "- The benign-traffic archetypes are our assumption of how researchers behave, not "
        "measured logs. The false-positive rates must be re-measured on real traffic.",
        "- Epsilon accounting is simple sequential composition, not a formal DP accountant.",
        "",
        "## 1. Differencing (tracker) attack",
        "",
        f"The attacker asks for a cohort of {d['n']} donors that includes the target, then the same "
        f"cohort without the target, and subtracts the two answers (10 variants, "
        f"{d['trials']} trials). Metric: share of the target's genotypes recovered exactly. "
        "`baseline` is guessing the most likely genotype from allele frequency.",
        "",
        "| Defence | Accuracy (mean, 95% CI) |",
        "|---|---|",
    ]
    names = {"none": "none", "dp_only": "Laplace noise only (epsilon = 1)",
             "ladder_only": "transform ladder only (per-query)",
             "ladder_plus_guard": "ladder + differencing guard", "baseline": "baseline (guess)"}
    for k, label in names.items():
        a = acc[k]
        L.append(f"| {label} | {_pct(a['mean'])} ± {_pct(a['ci95'])} |")
    L += ["", f"The guard blocked the second query in {_pct(d['guard_block_rate'])} of trials. "
          "Reading: the ladder alone does not stop differencing (each query is judged on its own); "
          "the guard does, bringing the attacker back to the guessing baseline.", ""]

    L += ["## 2. Membership inference on released frequencies (privacy vs utility)", "",
          "Likelihood-ratio test (Sankararaman-style): can an attacker holding a person's genotype "
          "tell whether they are in a 100-donor cohort whose allele frequencies were released? "
          "AUC 0.5 = no information, 1.0 = perfect. Utility = correlation / mean absolute error "
          "between released and true frequencies. `epsilon` is the TOTAL spent on the release "
          "(noise scale = 2 x variants / epsilon).", "",
          "| Variants | Release | AUC (95% CI) | Utility: corr | Utility: MAE |",
          "|---|---|---|---|---|"]
    for x in r["membership"]:
        L.append(f"| {x['V']} | {x['config']} | {x['auc']:.3f} ± {x['auc_ci95']:.3f} | "
                 f"{x['corr']:.3f} | {x['mae']:.4f} |")
    L += ["", "Reading: the ladder caps noised releases at "
          f"{m['params']['max_variants_noised']} variants because noise grows with the number of "
          "statistics released. The rows show the honest trade-off: releases that are accurate "
          "enough to be useful leak membership signal; releases noisy enough to hide it are not "
          "useful. This is the \"serious price in utility\" of DP on GWAS statistics.", ""]

    L += ["## 3. Many-narrow-queries triangulation", "",
          "A scripted attacker shrinks a cohort toward one person with nested cohorts, swapping "
          "one variant per query. `gap` is the time between queries. The 15-minute window means a "
          "patient attacker can evade rate-based detection.", "",
          "| Monitor | Gap (s) | Frozen | Median queries to first flag | to freeze | "
          "Smallest cohort answered |", "|---|---|---|---|---|---|"]
    for x in r["triangulation"]:
        L.append(f"| {'on' if x['monitor_on'] else 'off'} | {x['gap_s']:.0f} | "
                 f"{_pct(x['frozen_rate'])} | {x['median_queries_until_flag']} | "
                 f"{x['median_queries_until_freeze']} | "
                 f"{x['median_smallest_answered_cohort']} |")
    L += ["", f"Without the monitor, the floor is k_min = {m['params']['k_min']}: the attacker "
          "never gets an answer below it. Gaps longer than the window evade the sliding-window "
          "detectors; what still limits that attacker is k_min, the differencing guard and the "
          "epsilon budget, not the rate/duplicate detectors.", ""]

    L += ["## 4. Beacon update-flip attack (simplified replication)", "",
          "The attacker snapshots a beacon before and after `update` new donors are added and "
          "flags positions that flipped (boolean: absent to present; count: count rose). "
          "Precision = flagged positions the victim really carries; recall of rare positions = "
          "share of the victim's rare-variant positions flagged. `genomeguard` = boolean beacon "
          "with variants below the MAF floor unanswerable.", "",
          "| Update size | Mode | Mean flipped positions | Precision | Recall (rare positions) |",
          "|---|---|---|---|---|"]
    for x in r["beacon"]:
        p = "n/a (no flips)" if x["precision"] is None else f"{x['precision']:.3f}"
        rr = "n/a" if x["recall_of_rare_positions"] is None else f"{x['recall_of_rare_positions']:.3f}"
        L.append(f"| {x['update_size']} | {x['mode']} | {x['mean_flipped_positions']} | {p} | {rr} |")
    L += ["", "Reading: batching updates (larger update size) lowers the attacker's precision, as "
          "the paper suggests; count-level answers leak far more than boolean ones; hiding rare "
          "variants removes the flips entirely in this setup.", ""]

    b = r["benign"]
    L += ["## 5. Benign traffic: false positives", "",
          f"{b['sessions']} simulated researcher sessions ({b['queries']} queries) through the "
          "full pipeline (consent, ladder, monitor). Archetypes include ones that resemble "
          "probing (same variants across populations, narrowing filters, a fast automation "
          "script).", "",
          "| Metric | Value (95% CI) |", "|---|---|",
          f"| Sessions flagged by the monitor (any warn or worse) | {_pct(b['monitor_flag_rate'])} "
          f"[{_pct(b['monitor_flag_ci95'][0])}, {_pct(b['monitor_flag_ci95'][1])}] |",
          f"| Sessions throttled, frozen or guard-blocked | {_pct(b['monitor_hard_fp_rate'])} "
          f"[{_pct(b['monitor_hard_fp_ci95'][0])}, {_pct(b['monitor_hard_fp_ci95'][1])}] |",
          f"| Queries refused or escalated by the ladder | {_pct(b['ladder_refusal_rate'])} "
          f"[{_pct(b['ladder_refusal_ci95'][0])}, {_pct(b['ladder_refusal_ci95'][1])}] |",
          f"| Queries served (permit or permit with transform) | {_pct(b['served_rate'])} |",
          f"| Queries needing a transform | "
          f"{_pct(b['query_outcomes']['permit_with_transform'])} |", "",
          "| Archetype | Sessions | Flag rate | Hard FP rate |", "|---|---|---|---|"]
    for k, v in b["by_archetype"].items():
        L.append(f"| {k} | {v['sessions']} | {_pct(v['flag_rate'])} | {_pct(v['hard_fp_rate'])} |")
    L += ["", "A zero here means none occurred in this simulated traffic, not that false positives "
          "are impossible.", ""]

    if not r["robustness"]:
        return "\n".join(L + ["## 6. Robustness across dataset seeds", "",
                              "Not run for a real cohort: this section varies the synthetic "
                              "generator's seed.", ""])
    L += ["## 6. Robustness across dataset seeds", "",
          "| Dataset seed | Differencing: no defence | with guard | guess baseline | "
          "MI AUC raw (V=100) | MI AUC DP (V=25, eps=0.5) | Triangulation frozen | "
          "Benign flag rate |", "|---|---|---|---|---|---|---|---|"]
    for x in r["robustness"]:
        L.append(f"| {x['dataset_seed']} | {_pct(x['differencing_none'])} | "
                 f"{_pct(x['differencing_guarded'])} | {_pct(x['differencing_baseline'])} | "
                 f"{x['membership_auc_raw_V100']:.3f} | {x['membership_auc_dp_V25']:.3f} | "
                 f"{_pct(x['triangulation_frozen_rate'])} | {_pct(x['benign_flag_rate'])} |")
    L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="few trials (CI smoke test)")
    ap.add_argument("--write", action="store_true", help="write docs even in --quick mode")
    ap.add_argument("--cohort", help="evaluate a real cohort file (python -m app.data.real build); "
                    "results go to docs/eval-results-real.* so the synthetic ones are kept")
    a = ap.parse_args()
    res = run_all(quick=a.quick, cohort=a.cohort)
    md = to_markdown(res)
    if a.quick and not a.write:
        print(f"eval smoke OK ({len(md.splitlines())} report lines)")
        return
    stem = "eval-results-real" if a.cohort else "eval-results"
    DOCS.mkdir(exist_ok=True)
    (DOCS / f"{stem}.json").write_text(json.dumps(res, indent=1) + "\n")
    (DOCS / f"{stem}.md").write_text(md + "\n")
    print(f"wrote {DOCS / (stem + '.md')} and {stem}.json")


if __name__ == "__main__":
    main()
