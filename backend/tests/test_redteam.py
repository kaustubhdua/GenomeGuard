import numpy as np

from app.core.dataset import Dataset
from redteam import attacks as A
from redteam.benign_traffic import run_benign, wilson
from redteam.run_eval import run_all, to_markdown


def ds():
    return Dataset.synthetic(n_donors=300, n_variants=800, n_families=60, seed=7)


def test_auc_known_values():
    assert A.auc(np.array([3, 4, 5]), np.array([0, 1, 2])) == 1.0
    assert A.auc(np.array([0, 1, 2]), np.array([3, 4, 5])) == 0.0
    assert A.auc(np.array([1, 1]), np.array([1, 1])) == 0.5  # ties count half


def test_mean_ci_and_wilson():
    m, ci = A.mean_ci([1.0, 1.0, 1.0])
    assert m == 1.0 and ci == 0.0
    lo, hi = wilson(0, 100)
    assert lo == 0.0 and 0.0 < hi < 0.05
    lo, hi = wilson(50, 100)
    assert lo < 0.5 < hi


def test_differencing_guard_beats_no_defence():
    r = A.differencing_attack(ds(), trials=8, seed=1)["accuracy"]
    assert r["none"]["mean"] == 1.0  # subtracting two exact counts recovers the target
    assert r["ladder_plus_guard"]["mean"] <= r["baseline"]["mean"] + 1e-9  # no better than guessing


def test_noise_lowers_membership_auc():
    d = ds()
    raw = A.membership_inference(d, 80, 100, None, None, trials=6)["auc"]
    noisy = A.membership_inference(d, 80, 100, 0.05, 0.5, trials=6)["auc"]
    assert raw > noisy and noisy < 0.6


def test_triangulation_monitor_detects_fast_attacker_only():
    fast = A.triangulation_attack(5.0, trials=6)
    slow = A.triangulation_attack(1200.0, trials=6)  # gap longer than the 15 minute window
    assert fast["frozen_rate"] == 1.0
    assert slow["frozen_rate"] == 0.0  # documented limitation, reported in eval-results.md


def test_beacon_hiding_rare_variants_removes_flips():
    r = A.beacon_update_flip(ds(), 3, "genomeguard", trials=6)
    assert r["mean_flipped_positions"] == 0.0


def test_benign_traffic_is_deterministic_and_mostly_served():
    a = run_benign(ds(), sessions=30, seed=5)
    b = run_benign(ds(), sessions=30, seed=5)
    assert a == b
    assert a["served_rate"] > 0.8


def test_eval_quick_runs_and_renders_every_section():
    md = to_markdown(run_all(quick=True))
    for heading in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "do NOT show"):
        assert heading in md
