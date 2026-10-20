"""Anomaly monitor (section 7.6): sliding-window detectors per requester. Pure Python.

Time is passed in with every event (seconds), so evaluations can replay simulated traffic.

Detectors, each -> score in [0, 1] plus a reason (all constants are in AnomalyConfig):
  rate         queries in the last 60 s above what a human researcher does
  duplicate    many NEAR-identical queries (Jaccard on variant sets and cohort filters >= 0.8 but
               not identical): the signature of probing with tiny changes
  narrowing    cohort sizes shrinking step after step toward k_min: triangulating one person
  differencing two recent cohorts that differ by fewer than k_min donors (and overlap on
               variants): the answers could be subtracted to isolate those donors. The classic
               "tracker" attack, and the same idea as the beacon before/after update attack.
               A hit BLOCKS that query on its own, whatever the total score.
  cumulative   distinct variants touched in the window and epsilon spent versus the budget

Total score = weighted sum (weights below, transparent and tunable). Actions:
  ok < warn < throttle < freeze; frozen requesters get 403 until a human unfreezes them.

The monitor never returns donor identities: only counts, scores and reasons.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field, replace

ACTIONS = ("ok", "warn", "throttle", "freeze")


@dataclass(frozen=True)
class AnomalyConfig:
    window_s: float = 900.0  # 15 minutes
    k_min: int = 20
    rate_ok_per_min: int = 3
    rate_max_per_min: int = 15
    dup_similarity: float = 0.8
    dup_saturate: int = 5  # this many near-duplicates -> score 1
    narrowing_saturate: int = 4  # this many consecutive shrinking steps -> score 1
    narrowing_zone: float = 4.0  # "close to k_min" means size <= zone * k_min
    max_distinct_variants: int = 500
    epsilon_budget: float = 1.0
    weights: tuple[tuple[str, float], ...] = (
        ("rate", 0.15), ("duplicate", 0.25), ("narrowing", 0.25),
        ("differencing", 0.20), ("cumulative", 0.15),
    )
    warn: float = 0.4
    throttle: float = 0.6
    freeze: float = 0.8
    diff_hits_throttle: int = 2  # differencing-guard hits in the window -> at least throttle
    diff_hits_freeze: int = 3  # ...and this many -> freeze (a human reviews)

    @classmethod
    def from_params(cls, p=None) -> AnomalyConfig:
        from app.core.params import DEFAULT

        p = p or DEFAULT
        return cls(window_s=p.anomaly_window_minutes * 60.0, k_min=p.k_min,
                   epsilon_budget=p.epsilon_budget, warn=p.anomaly_warn,
                   throttle=p.anomaly_throttle, freeze=p.anomaly_freeze)


@dataclass(frozen=True)
class QueryEvent:
    ts: float
    variants: frozenset[int]
    cohort_filter: dict = field(default_factory=dict, hash=False, compare=False)
    cohort_ids: frozenset[int] = frozenset()  # internal only; never returned
    epsilon: float = 0.0
    blocked: bool = False  # set by the monitor when the differencing guard fired


@dataclass
class Assessment:
    score: float
    action: str  # ok | warn | throttle | freeze
    blocked: bool  # differencing guard fired: block THIS query
    detectors: dict[str, dict]  # name -> {"score": float, "reason": str}

    def to_json(self) -> dict:
        return {"score": round(self.score, 3), "action": self.action, "blocked": self.blocked,
                "detectors": {k: {"score": round(v["score"], 3), "reason": v["reason"]}
                              for k, v in self.detectors.items()}}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _filter_items(flt: dict) -> set:
    items = set()
    for k, v in flt.items():
        for x in (v if isinstance(v, (list, tuple, set)) else [v]):
            items.add((k, str(x)))
    return items


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


class AnomalyMonitor:
    def __init__(self, config: AnomalyConfig | None = None) -> None:
        self.cfg = config or AnomalyConfig()
        self.events: dict[int, deque[QueryEvent]] = defaultdict(deque)
        self.frozen: set[int] = set()

    # ---- state -----------------------------------------------------------------
    def _recent(self, requester: int, now: float) -> list[QueryEvent]:
        q = self.events[requester]
        while q and now - q[0].ts > self.cfg.window_s:
            q.popleft()
        return list(q)

    def freeze(self, requester: int) -> None:
        self.frozen.add(requester)

    def unfreeze(self, requester: int) -> None:
        """Human action. Also clears the window so the requester starts fresh."""
        self.frozen.discard(requester)
        self.events[requester].clear()

    # ---- detectors -------------------------------------------------------------
    def _rate(self, recent: list[QueryEvent], ev: QueryEvent) -> dict:
        last_min = 1 + sum(1 for e in recent if ev.ts - e.ts <= 60.0)
        s = _clip((last_min - self.cfg.rate_ok_per_min)
                  / (self.cfg.rate_max_per_min - self.cfg.rate_ok_per_min))
        return {"score": s, "reason": f"{last_min} queries in the last minute"}

    def _duplicate(self, recent: list[QueryEvent], ev: QueryEvent) -> dict:
        fi = _filter_items(ev.cohort_filter)
        n = 0
        for e in recent:
            sim = (_jaccard(set(e.variants), set(ev.variants))
                   + _jaccard(_filter_items(e.cohort_filter), fi)) / 2
            if self.cfg.dup_similarity <= sim < 1.0:
                n += 1
        return {"score": _clip(n / self.cfg.dup_saturate),
                "reason": f"{n} near-identical earlier queries in the window"}

    def _narrowing(self, recent: list[QueryEvent], ev: QueryEvent) -> dict:
        sizes = [len(e.cohort_ids) for e in recent][-6:] + [len(ev.cohort_ids)]
        steps = 0
        for i in range(len(sizes) - 1, 0, -1):
            if sizes[i] < sizes[i - 1]:
                steps += 1
            else:
                break
        s = _clip(steps / self.cfg.narrowing_saturate)
        if sizes[-1] > self.cfg.narrowing_zone * self.cfg.k_min:
            s *= 0.5  # shrinking, but still far from a single person
        return {"score": s, "reason": f"{steps} consecutive shrinking cohorts (now {sizes[-1]})"}

    def _differencing(self, recent: list[QueryEvent], ev: QueryEvent) -> dict:
        best = None
        for e in recent:
            if not (set(e.variants) & set(ev.variants)):
                continue  # different statistics: subtracting answers tells nothing
            diff = len(e.cohort_ids ^ ev.cohort_ids)
            if 0 < diff < self.cfg.k_min:
                best = diff if best is None else min(best, diff)
        if best is None:
            return {"score": 0.0, "reason": "no overlapping cohort differences below k_min"}
        return {"score": 1.0, "reason": f"two queries differ by only {best} donor(s) "
                f"(< k_min={self.cfg.k_min})"}

    def _cumulative(self, recent: list[QueryEvent], ev: QueryEvent) -> dict:
        distinct = set(ev.variants)
        eps = ev.epsilon
        for e in recent:
            distinct |= set(e.variants)
            eps += e.epsilon
        s = max(len(distinct) / self.cfg.max_distinct_variants, eps / self.cfg.epsilon_budget)
        return {"score": _clip(s), "reason": f"{len(distinct)} distinct variants, "
                f"epsilon {eps:.2f}/{self.cfg.epsilon_budget:g}"}

    # ---- public API ------------------------------------------------------------
    def assess(self, requester: int, ev: QueryEvent) -> Assessment:
        """Score `ev` against the requester's window WITHOUT recording it."""
        recent = self._recent(requester, ev.ts)
        det = {
            "rate": self._rate(recent, ev),
            "duplicate": self._duplicate(recent, ev),
            "narrowing": self._narrowing(recent, ev),
            "differencing": self._differencing(recent, ev),
            "cumulative": self._cumulative(recent, ev),
        }
        score = sum(w * det[name]["score"] for name, w in self.cfg.weights)
        blocked = det["differencing"]["score"] >= 1.0
        hits = sum(1 for e in recent if e.blocked) + (1 if blocked else 0)
        if blocked:
            det["differencing"]["reason"] += f"; {hits} guard hit(s) in the window"
        if (requester in self.frozen or score >= self.cfg.freeze
                or hits >= self.cfg.diff_hits_freeze):
            action = "freeze"
        elif score >= self.cfg.throttle or hits >= self.cfg.diff_hits_throttle:
            action = "throttle"
        elif score >= self.cfg.warn:
            action = "warn"
        else:
            action = "ok"
        return Assessment(_clip(score), action, blocked, det)

    def observe(self, requester: int, ev: QueryEvent) -> Assessment:
        """Assess, then record the event (attempts count even when they are blocked) and apply
        a freeze if the score demands it."""
        a = self.assess(requester, ev)
        self.events[requester].append(replace(ev, blocked=a.blocked))
        if a.action == "freeze":
            self.frozen.add(requester)
        return a
