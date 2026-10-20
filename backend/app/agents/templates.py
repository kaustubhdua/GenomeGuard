"""Deterministic text for every agent role. Used when there is no API key (so the demo never
fails) and as the fallback when an LLM answer is missing or rejected. Inputs are the SANITIZED
facts only. Reason codes map to plain language here."""

from __future__ import annotations

REASON_PLAIN = {
    "withdrawn": "the donor withdrew consent",
    "purpose_unknown": "the purpose is not a recognised research purpose",
    "purpose_not_health": "consent covers health research only",
    "disease_mismatch": "consent is limited to a different disease",
    "commercial_use_blocked": "consent forbids commercial use",
    "methods_research_blocked": "consent forbids methods-development use",
    "aggregate_blocked": "consent forbids aggregate-level use",
    "controls_blocked": "consent forbids use as controls",
    "population_restricted": "consent is limited to another population",
    "unknown_consent": "the consent record was malformed",
    "below_k_min": "the eligible cohort is below the minimum size",
    "cohort_below_k_min": "the cohort is below the minimum size",
    "credential_insufficient": "the account's credential tier does not allow this data level",
    "cohort_too_small_for_tier": "the cohort is too small for an anonymous account",
    "no_variants": "no variants matched the request",
    "all_variants_below_maf_floor": "every requested variant was too rare to release",
    "epsilon_budget_exhausted": "the privacy (epsilon) budget is used up",
    "residual_high_risk": "risk stayed high after every protection",
    "differencing_guard": "two queries differ by only a few donors, which could isolate them",
    "requester_frozen": "the account is frozen pending human review",
    "requester_throttled": "unusual query patterns need a human check",
    "record_level_needs_approval": "record-level access always needs human approval",
    "record_rows_never_released": "individual genotype rows are never returned",
    "rare_variant_few_carriers": "a rare variant has only a few carriers",
    "membership_signal_high": "the release could reveal who is in the dataset",
    "membership_signal_medium": "the release carries some membership risk",
    "record_uniqueness_high": "many donors would be unique in the release",
    "record_uniqueness_medium": "some donors would be unique in the release",
}

STEP_PLAIN = {
    "drop_rare_variants": "very rare variants were dropped",
    "downgrade_to_count": "record-level rows were replaced by counts",
    "generalise_bins": "values were rounded into bins",
    "limit_variants": "the number of variants was capped",
    "laplace_noise": "calibrated random noise (differential privacy) was added",
    "downgrade_to_boolean": "the answer was reduced to yes/no",
}


def plain(code: str) -> str:
    return REASON_PLAIN.get(code, code.replace("_", " "))


def _excluded_text(ex: dict) -> str:
    if not ex:
        return ""
    parts = [f"{n} because {plain(r)}" for r, n in sorted(ex.items(), key=lambda kv: -kv[1])[:3]]
    return " Excluded: " + "; ".join(parts) + "."


def consent(f: dict) -> str:
    c = f.get("consent", {})
    return (f"{c.get('eligible', 0)} of {c.get('considered', 0)} donors in the requested cohort "
            f"had consent that matches this request." + _excluded_text(c.get("excluded_by_reason", {})))


def privacy(f: dict) -> str:
    b, a = f.get("risk_before", {}), f.get("risk_after", {})
    steps = [s.get("step") for s in f.get("steps", [])]
    done = "; ".join(plain_step(s) for s in steps) if steps else "no protection was needed"
    rel = (a.get("relatives_exposed") or b.get("relatives_exposed") or {}).get("total")
    tail = (f" Simulated model: {rel} relatives of carriers could be exposed by the original request."
            if rel else "")
    return (f"Re-identification risk was {b.get('band', 'unknown')} before and "
            f"{a.get('band', 'unknown')} after protection: {done}.{tail}")


def plain_step(step: str) -> str:
    return STEP_PLAIN.get(step, step.replace("_", " "))


def access(f: dict) -> str:
    rec = f.get("agent_recommendation", "escalate")
    return (f"Advisory view: {rec} (requester tier {f.get('tier', 'unknown')}, "
            f"{f.get('history_requests', 0)} earlier requests, {f.get('history_denials', 0)} denied, "
            f"{f.get('history_alerts', 0)} alerts).")


def anomaly(f: dict) -> str:
    a = f.get("anomaly", {})
    hot = [k for k, v in (a.get("detectors") or {}).items() if v.get("score", 0) >= 0.5]
    why = ", ".join(hot) if hot else "no detector above 0.5"
    return (f"Behaviour score {a.get('score', 0)} (action: {a.get('action', 'ok')}); signals: {why}."
            + (" This query was blocked by the differencing guard." if a.get("blocked") else ""))


def explainer(f: dict) -> str:
    out = f.get("outcome", "deny")
    reasons = [plain(r) for r in f.get("reasons", [])][:3]
    c = f.get("consent", {})
    steps = [plain_step(s.get("step", "")) for s in f.get("steps", [])]
    s1 = {
        "permit": "Your request was approved as asked.",
        "permit_with_transform": "Your request was approved with privacy protections applied.",
        "deny": "Your request was denied.",
        "escalate": "Your request needs a human reviewer before anything is released.",
    }.get(out, "Your request was processed.")
    if reasons:
        s1 += " Reason: " + "; ".join(reasons) + "."
    s2 = (f"Consent check: {c.get('eligible', 0)} of {c.get('considered', 0)} donors in your "
          f"cohort were eligible.")
    s3 = ("Protections applied: " + "; ".join(steps) + "." if steps
          else "No transformation was needed." if out.startswith("permit")
          else "Nothing was released.")
    return " ".join((s1, s2, s3))


def reviewer(f: dict) -> str:
    reasons = ", ".join(f.get("reasons", [])) or "none"
    q = [
        "Does the stated purpose match the requester's role and institution?",
        "Is the residual risk acceptable given the carriers' relatives in the registry?",
        "Should the account stay frozen after seeing its recent query pattern?",
    ]
    return (f"Case summary: outcome {f.get('outcome')}, reasons [{reasons}], risk band "
            f"{(f.get('risk_after') or {}).get('band', 'unknown')}. Questions for you: "
            + " ".join(f"({i + 1}) {x}" for i, x in enumerate(q))
            + " This is a recommendation only; you decide.")


def compliance(f: dict) -> str:
    o = f.get("outcomes", {})
    return (
        f"Period report ({f.get('period', 'all time')}): {f.get('requests', 0)} requests; "
        f"{o.get('permit', 0) + o.get('permit_with_transform', 0)} released "
        f"({o.get('permit_with_transform', 0)} with protections), {o.get('deny', 0)} denied, "
        f"{o.get('escalate', 0)} sent to human review. Alerts raised: {f.get('alerts', 0)}; "
        f"accounts frozen: {f.get('freezes', 0)}; human reviews: {f.get('reviews', 0)}. "
        f"Audit chain valid: {f.get('chain_ok')} ({f.get('chain_length', 0)} entries). "
        "Designed around the ideas of DPDP, GDPR and HIPAA (purpose limitation, consent "
        "withdrawal, security safeguards, breach evidence); it is not a certification or a "
        "statement of legal compliance."
    )


TEMPLATES = {"consent": consent, "privacy": privacy, "access": access, "anomaly": anomaly,
             "explainer": explainer, "reviewer": reviewer, "compliance": compliance}
