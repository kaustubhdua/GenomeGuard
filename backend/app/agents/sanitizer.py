"""The ONLY door between genomic data and an LLM prompt.

Everything an agent is allowed to see passes through `sanitize`, which keeps a WHITELIST of keys
holding numbers, booleans, or short enumerated strings (reason codes, bands, levels). Anything
else is dropped, not masked: donor ids, genotype arrays, family ids, free text, notes, names,
cohort memberships, and any key we did not explicitly list never reach a prompt.

Rules enforced here:
  * a key must be in ALLOWED_KEYS (or be a data-dependent map key under ALLOWED_MAPS)
  * numbers must be finite; strings must match SAFE_STR (short, no free text)
  * lists are capped, so a long id list could not slip through even under an allowed key
  * numpy arrays and other objects are dropped
A unit test plants a canary string inside genotype data, ids and free text and asserts it never
appears in any prompt (tests/test_agents.py).
"""

from __future__ import annotations

import math
import re
from typing import Any

# keys whose values are numbers / booleans / enumerated strings produced by OUR code
ALLOWED_KEYS = frozenset({
    "outcome", "reasons", "band", "level", "step", "action", "credential_level", "data_level",
    "n", "n_variants", "eligible", "considered", "uniqueness_rate", "info_bits", "log2_n",
    "rare_variants", "rare_variants_masked", "min_carriers", "kin_linked_rare_pairs",
    "relatives_exposed_total", "close_total", "bin_width", "epsilon", "noise_scale",
    "epsilon_spent", "epsilon_remaining", "epsilon_budget", "score", "blocked",
    "risk_before", "risk_after", "steps", "final", "consent", "anomaly", "requester", "epsilon_ledger",
    "recommendation", "role", "needs_human", "requests", "released", "denied", "escalated",
    "alerts", "freezes", "reviews", "chain_ok", "chain_length", "period_days",
    "permit", "permit_with_transform", "deny", "escalate", "frozen", "history_requests",
    "history_denials", "history_alerts",
    "info_bits_mean", "rare_few_carriers", "rare_hidden", "membership_signal", "band_reasons",
    "below_k_min", "carrier_families", "relatives_exposed", "total", "subjects", "by_degree",
    "by_relation", "expected_shared_dna", "purpose", "disease", "is_commercial", "detail",
    "excluded", "n_steps", "reason", "agent_recommendation", "agrees", "tier", "window",
    "chain_head_short", "period",
})
# maps whose KEYS are data-dependent but enumerated by our code (reason codes, detector names...)
ALLOWED_MAPS = frozenset({
    "excluded_by_reason", "detectors", "outcomes", "denials_by_reason", "alerts_by_kind",
    "by_degree", "by_relation",
})

SAFE_STR = re.compile(r"^[a-z0-9_:\.\-]{1,48}$")
MAX_LIST = 20


def _safe_scalar(v: Any) -> tuple[bool, Any]:
    if isinstance(v, bool):
        return True, v
    if isinstance(v, int):
        return True, v
    if isinstance(v, float):
        return (True, round(v, 4)) if math.isfinite(v) else (False, None)
    if isinstance(v, str) and SAFE_STR.match(v):
        return True, v
    if v is None:
        return True, None
    return False, None


def _clean(v: Any, *, is_map: bool = False) -> tuple[bool, Any]:
    ok, s = _safe_scalar(v)
    if ok:
        return True, s
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            k = str(k)
            if is_map:
                if not SAFE_STR.match(k):
                    continue
                keep, c = _clean(x)
            else:
                if k not in ALLOWED_KEYS and k not in ALLOWED_MAPS:
                    continue
                keep, c = _clean(x, is_map=k in ALLOWED_MAPS)
            if keep:
                out[k] = c
        return True, out
    if isinstance(v, (list, tuple)):
        items = []
        for x in list(v)[:MAX_LIST]:
            keep, c = _clean(x)
            if keep:
                items.append(c)
        return True, items
    return False, None  # numpy arrays, objects, sets, bytes...


def sanitize(obj: dict) -> dict:
    """Whitelist-filter a facts dict. Returns a new, JSON-safe dict."""
    keep, out = _clean(obj)
    return out if keep and isinstance(out, dict) else {}
