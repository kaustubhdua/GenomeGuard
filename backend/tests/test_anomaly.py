import random

from app.core.anomaly import AnomalyConfig, AnomalyMonitor, QueryEvent

CFG = AnomalyConfig()


def ev(ts, variants=(1, 2, 3), cohort=range(100), flt=None, eps=0.0):
    return QueryEvent(ts, frozenset(variants), flt or {}, frozenset(cohort), eps)


def test_single_normal_query_is_ok():
    m = AnomalyMonitor()
    a = m.observe(1, ev(0))
    assert a.action == "ok" and a.score < 0.1 and not a.blocked


def test_rate_detector():
    m = AnomalyMonitor()
    for t in range(16):
        a = m.observe(1, ev(t * 2.0, variants=range(t, t + 3), cohort=range(100)))
    assert a.detectors["rate"]["score"] == 1.0 or a.detectors["rate"]["score"] > 0.8


def test_slow_researcher_has_zero_rate_score():
    m = AnomalyMonitor()
    scores = [m.observe(1, ev(t * 120.0, variants=range(t * 5, t * 5 + 5)))
              .detectors["rate"]["score"] for t in range(6)]
    assert max(scores) == 0.0


def test_near_duplicate_probing():
    m = AnomalyMonitor()
    base = list(range(20))
    last = None
    for i in range(7):  # same variants except one swapped each time -> Jaccard ~ 0.9
        last = m.observe(1, ev(i * 30.0, variants=base[:19] + [100 + i], flt={"population": "A"}))
    assert last.detectors["duplicate"]["score"] == 1.0


def test_exact_repeat_is_not_probing():
    m = AnomalyMonitor()
    for i in range(6):
        a = m.observe(1, ev(i * 30.0, variants=range(10)))
    assert a.detectors["duplicate"]["score"] == 0.0


def test_cohort_narrowing_toward_k_min():
    m = AnomalyMonitor()
    a = None
    for i, size in enumerate([200, 150, 110, 80, 60, 45, 30]):
        a = m.observe(1, ev(i * 60.0, variants=range(i * 10, i * 10 + 5), cohort=range(size)))
    assert a.detectors["narrowing"]["score"] == 1.0


def test_shrinking_but_far_from_k_min_scores_half():
    m = AnomalyMonitor()
    for i, size in enumerate([900, 800, 700, 600, 500]):
        a = m.observe(1, ev(i * 60.0, variants=range(i * 10, i * 10 + 5), cohort=range(size)))
    assert a.detectors["narrowing"]["score"] == 0.5


def test_differencing_guard_blocks_cohorts_differing_by_few_donors():
    m = AnomalyMonitor()
    m.observe(1, ev(0, cohort=range(100)))
    a = m.assess(1, ev(60, cohort=range(99)))  # differs by exactly one donor
    assert a.blocked and a.detectors["differencing"]["score"] == 1.0
    assert "1 donor" in a.detectors["differencing"]["reason"]


def test_differencing_ignores_large_differences_identical_cohorts_and_disjoint_variants():
    m = AnomalyMonitor()
    m.observe(1, ev(0, cohort=range(100)))
    assert not m.assess(1, ev(60, cohort=range(60))).blocked  # differ by 40 >= k_min
    assert not m.assess(1, ev(60, cohort=range(100))).blocked  # identical cohort
    assert not m.assess(1, ev(60, variants=(50, 51), cohort=range(99))).blocked  # other stats


def test_window_expiry_forgets_old_queries():
    m = AnomalyMonitor()
    m.observe(1, ev(0, cohort=range(100)))
    assert not m.assess(1, ev(CFG.window_s + 1, cohort=range(99))).blocked


def test_requesters_are_isolated():
    m = AnomalyMonitor()
    m.observe(1, ev(0, cohort=range(100)))
    assert not m.assess(2, ev(10, cohort=range(99))).blocked


def test_cumulative_exposure_epsilon_and_variants():
    m = AnomalyMonitor()
    a = m.observe(1, ev(0, variants=range(600), eps=0.5))
    assert a.detectors["cumulative"]["score"] == 1.0
    b = AnomalyMonitor().observe(1, ev(0, variants=range(10), eps=0.5))
    assert abs(b.detectors["cumulative"]["score"] - 0.5) < 1e-9


def triangulation_attack(m, rid=7, start=0.0):
    """Scripted attacker: fast, near-duplicate queries on a shrinking cohort that end in a
    one-donor difference."""
    out = []
    size = 300
    for i in range(14):
        out.append(m.observe(rid, ev(start + i * 4.0, variants=list(range(30)) + [200 + i],
                                     cohort=range(size), flt={"population": "A"}, eps=0.05)))
        size -= 18 if size > 60 else 1
    return out


def test_attack_is_throttled_blocked_and_frozen_and_unfreeze_works():
    m = AnomalyMonitor()
    res = triangulation_attack(m)
    actions = [a.action for a in res]
    assert "freeze" in actions and 7 in m.frozen
    assert any(a.blocked for a in res)
    first_freeze = actions.index("freeze")
    assert first_freeze <= 4  # caught early: 3 differencing hits -> frozen long before query 14
    assert "throttle" in actions[:first_freeze]  # escalating response: throttle before freeze
    assert m.assess(7, ev(1000)).action == "freeze"  # frozen requesters stay frozen
    m.unfreeze(7)
    assert 7 not in m.frozen and m.assess(7, ev(1000)).action == "ok"


def test_benign_researchers_are_not_flagged():
    """Varied cohorts, new variants every query, minutes apart: zero false positives."""
    rng = random.Random(3)
    flagged = 0
    total = 0
    for rid in range(50):
        m = AnomalyMonitor()
        t = 0.0
        for _ in range(8):
            t += rng.uniform(60, 400)
            vs = rng.sample(range(3000), rng.randint(5, 30))
            size = rng.randint(40, 500)
            cohort = rng.sample(range(600), min(size, 600))
            total += 1
            a = m.observe(rid, ev(t, variants=vs, cohort=cohort,
                                  flt={"population": rng.choice("ABC")}, eps=0.05))
            flagged += a.action != "ok" or a.blocked
    assert flagged == 0, f"{flagged}/{total} benign queries flagged"


def test_assessment_json_contains_no_donor_ids():
    m = AnomalyMonitor()
    m.observe(1, ev(0, cohort=range(100)))
    j = m.assess(1, ev(5, cohort=range(99))).to_json()
    assert set(j) == {"score", "action", "blocked", "detectors"}
    assert "[" not in str(j) and "frozenset" not in str(j)  # counts and text only, no id lists


def test_repeated_differencing_hits_escalate_throttle_then_freeze():
    m = AnomalyMonitor()
    m.observe(1, ev(0, cohort=range(100)))  # baseline query
    acts = [m.observe(1, ev(60 + i * 60, cohort=range(100 - i - 1))) for i in range(3)]
    assert [a.blocked for a in acts] == [True, True, True]
    assert [a.action for a in acts][1:] == ["throttle", "freeze"]
    assert 1 in m.frozen
