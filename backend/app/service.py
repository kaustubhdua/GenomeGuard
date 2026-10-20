"""Decision orchestration (section 7.7) and every admin action. Framework-free: the HTTP layer is a
thin adapter over this class, so the whole product is testable without a web server.

`submit()` pipeline (THIS code decides; agents only explain/advise afterwards):

  validate -> credential tier -> consent filter -> variants -> risk + transform ladder ->
  anomaly monitor -> outcome -> (release + charge epsilon | hold for human | deny) -> agents

Outcome precedence once the anomaly monitor has spoken:
  differencing guard hit      -> deny  ("differencing_guard")
  monitor says freeze         -> account frozen, escalate to a human ("requester_frozen")
  ladder deny / escalate      -> deny / escalate
  monitor says throttle       -> hold for a human ("requester_throttled")
  controlled + record level   -> hold for a human ("record_level_needs_approval"); even after
                                 approval only transformed AGGREGATES are returned, never rows
  otherwise                   -> release (with protections if the ladder applied any)

Every step writes to the hash-chained audit log.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime

import numpy as np

from app.agents.base import AgentTeam
from app.agents.llm import LLM
from app.core import crypto
from app.core.anomaly import AnomalyConfig, AnomalyMonitor, QueryEvent
from app.core.audit_chain import AuditChain, jsonable
from app.core.consent import RESEARCH_PURPOSES, ConsentRequest, eligible_cohort
from app.core.dataset import Dataset
from app.core.params import DATA_LEVELS, DEFAULT, Params
from app.core.transform import TransformPlan, materialize, run_ladder
from app.store import AuditStore, Store, now_iso

SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]{1,32}$")
DISEASE = re.compile(r"^[a-z_]{1,32}$")
CHECKED_KEYS = ("cohort_id", "population")
INVERSE = {"parent": "child", "grandparent": "grandchild", "aunt/uncle": "niece/nephew"}


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}

    def to_json(self) -> dict:
        return {"error": self.code, "message": self.message, **self.extra}


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def inverse_relation(rel: str) -> str:
    for k, v in INVERSE.items():
        if rel.endswith(k):  # also "great-grandparent", "great-aunt/uncle"
            return rel[: -len(k)] + v
    return rel


class GenomeGuardService:
    def __init__(self, store: Store, ds: Dataset, p: Params = DEFAULT, *, master: bytes | None = None,
                 llm: LLM | None = None, llm_roles: set[str] | None = None,
                 allow_tamper: bool = False, admin_key: str = "demo-admin-key",
                 clock: Callable[[], float] = time.time) -> None:
        self.store, self.ds, self.p, self.clock = store, ds, p, clock
        self.master = master
        self.dataset_id = ds.dataset_id
        self.admin_hash = hash_key(admin_key)
        self.audit = AuditChain(AuditStore(store), allow_tamper=allow_tamper)
        self.monitor = AnomalyMonitor(AnomalyConfig.from_params(p))
        self.team = AgentTeam(llm or LLM(None, "template"), llm_roles)
        self.timeline: dict[int, list[dict]] = {}
        for r in store.requesters():
            if r["frozen_at"]:
                self.monitor.freeze(r["id"])

    # ================================================================== auth / requesters
    def authenticate(self, key: str | None) -> dict | None:
        return self.store.requester_by_key(hash_key(key)) if key else None

    def is_admin(self, key: str | None) -> bool:
        return bool(key) and hash_key(key) == self.admin_hash

    def create_requester(self, name: str, role: str, level: str, institution: str, key: str) -> int:
        rid = self.store.add_requester(name, role, level, institution, hash_key(key))
        self.audit.append("admin", "requester.created", {"requester_id": rid, "tier": level})
        return rid

    # ================================================================== validation
    def _validate(self, req: dict) -> dict:
        def bad(msg: str):
            raise ServiceError(422, "invalid_request", msg)

        purpose = req.get("purpose")
        if purpose not in RESEARCH_PURPOSES:
            bad(f"purpose must be one of {sorted(RESEARCH_PURPOSES)}")
        disease = req.get("disease")
        if disease is not None and not (isinstance(disease, str) and DISEASE.match(disease)):
            bad("disease must be lowercase letters/underscores")
        level = req.get("data_level", "frequency")
        if level not in DATA_LEVELS:
            bad(f"data_level must be one of {list(DATA_LEVELS)}")
        flt = req.get("cohort_filter") or {}
        if not isinstance(flt, dict) or set(flt) - set(CHECKED_KEYS):
            bad(f"cohort_filter keys allowed: {list(CHECKED_KEYS)}")
        for k, v in flt.items():
            vals = v if isinstance(v, list) else [v]
            if not vals or not all(isinstance(x, str) and SAFE_ID.match(x) for x in vals):
                bad(f"cohort_filter.{k} must be a short id string or list of them")
        vf = req.get("variant_filter") or {}
        if not isinstance(vf, dict):
            bad("variant_filter must be an object")
        return {"purpose": purpose, "disease": disease, "data_level": level,
                "is_commercial": bool(req.get("is_commercial", False)),
                "cohort_filter": flt, "variant_filter": vf}

    def resolve_variants(self, vf: dict) -> list[int]:
        """Variant filter -> 0-based indices. Either {"variant_ids": [1-based ids]} or
        {"min_maf": x, "limit": n, "include_planted": k}: first n variants with MAF >= x (the
        planted demo variants excluded) followed by the first k planted ones."""
        n = self.ds.n_variants
        if "variant_ids" in vf:
            ids = vf["variant_ids"]
            if (not isinstance(ids, list) or len(ids) > 5000
                    or not all(isinstance(i, int) and 1 <= i <= n for i in ids)):
                raise ServiceError(422, "invalid_request", f"variant_ids must be 1..{n}")
            return list(dict.fromkeys(i - 1 for i in ids))
        try:
            min_maf = float(vf.get("min_maf", 0.05))
            limit = min(int(vf.get("limit", 20)), 3000)
            planted_k = int(vf.get("include_planted", 0))
        except (TypeError, ValueError):
            raise ServiceError(422, "invalid_request", "bad variant_filter values") from None
        planted = set(self.ds.planted)
        common = [j for j in range(n) if j not in planted and self.ds.maf[j] >= min_maf][:limit]
        return common + list(self.ds.planted)[: max(0, planted_k)]

    # ================================================================== helpers
    def _history(self, rid: int) -> dict:
        rows = self.store.decisions(rid, limit=500)
        return {"history_requests": len(rows),
                "history_denials": sum(1 for r in rows if r["outcome"] == "deny"),
                "history_alerts": sum(1 for a in self.store.alerts(500) if a["requester_id"] == rid)}

    def _remaining(self, rid: int) -> float:
        return max(0.0, self.p.epsilon_budget - self.store.eps_spent(rid, self.dataset_id))

    def _charge(self, rid: int, eps: float) -> float:
        spent = self.store.eps_spent(rid, self.dataset_id) + eps
        self.store.set_eps_spent(rid, self.dataset_id, spent)
        self.audit.append("system", "budget.charged", {
            "requester_id": rid, "epsilon": eps, "epsilon_spent": round(spent, 4),
            "epsilon_remaining": round(max(0.0, self.p.epsilon_budget - spent), 4)})
        return spent

    def budget(self, rid: int) -> dict:
        spent = self.store.eps_spent(rid, self.dataset_id)
        return {"epsilon_budget": self.p.epsilon_budget, "epsilon_spent": round(spent, 4),
                "epsilon_remaining": round(max(0.0, self.p.epsilon_budget - spent), 4)}

    def _carriers(self, donor_ids: list[int], vidx: list[int]) -> list[int]:
        """Donors who carry a rare variant (MAF < rare_maf) inside this candidate release."""
        if not donor_ids or not vidx:
            return []
        v = np.asarray(vidx, dtype=int)
        rare = v[self.ds.maf[v] < self.p.rare_maf]
        if not len(rare):
            return []
        g = self.ds.genotypes[np.ix_(self.ds.rows(donor_ids), rare)]
        return [int(donor_ids[i]) for i in np.where((g > 0).any(axis=1))[0]]

    def _agent(self, role: str, facts: dict, actor: str = "agent") -> str:
        out = self.team.run(role, facts)
        self.audit.append(actor + ":" + role, "agent.output", out.audit())
        return out.text

    @staticmethod
    def _codes(rel: dict | None) -> dict | None:
        """Make relation names prompt-safe (no spaces or slashes)."""
        if not rel:
            return rel
        out = dict(rel)
        if "by_relation" in out:
            out["by_relation"] = {re.sub(r"[^a-z0-9]+", "_", k.lower()): v
                                  for k, v in out["by_relation"].items()}
        out.pop("model", None)
        return out

    def _facts(self, requester: dict, clean: dict, outcome: str, reasons: list[str], elig,
               ladder, assess, hist: dict) -> dict:
        tj = ladder.to_json() if ladder else {}
        rb, ra = dict(tj.get("risk_before") or {}), dict(tj.get("risk_after") or {})
        for r_, src in ((rb, ladder.risk_before if ladder else {}),
                        (ra, ladder.risk_after if ladder else {})):
            r_["relatives_exposed"] = self._codes(src.get("relatives_exposed"))
        return {
            "outcome": outcome, "reasons": reasons, "purpose": clean["purpose"],
            "disease": clean["disease"], "is_commercial": clean["is_commercial"],
            "data_level": clean["data_level"], "tier": requester["credential_level"],
            "consent": elig.counts_only() if elig else {}, "steps": tj.get("steps", []),
            "risk_before": rb, "risk_after": ra, "final": tj.get("final", {}),
            "anomaly": assess.to_json() if assess else {}, **hist,
        }

    def _advice(self, requester: dict, outcome: str, hist: dict, assess) -> str:
        if hist["history_denials"] >= 2 or hist["history_alerts"] >= 1 or (
                assess and assess.action != "ok"):
            return "escalate"
        return "permit" if outcome.startswith("permit") else outcome

    # ================================================================== submit
    def submit(self, requester: dict, req: dict, now: float | None = None) -> dict:
        now = self.clock() if now is None else now
        rid = requester["id"]
        clean = self._validate(req)
        req_id = self.store.add_request(rid, now_iso(), clean)
        actor = f"requester:{rid}"
        tier = requester["credential_level"]
        self.audit.append(actor, "request.received", {
            "request_id": req_id, "purpose": clean["purpose"], "disease": clean["disease"],
            "data_level": clean["data_level"], "is_commercial": clean["is_commercial"],
            "tier": tier, "cohort_filter": clean["cohort_filter"]})
        hist = self._history(rid)

        def finish(outcome, reasons, *, elig=None, ladder=None, assess=None, needs_human=False,
                   private=None, release=None, status=None) -> dict:
            facts = self._facts(requester, clean, outcome, reasons, elig, ladder, assess, hist)
            facts["agent_recommendation"] = self._advice(requester, outcome, hist, assess)
            text = self._agent("explainer", facts)
            notes = {"consent": self._agent("consent", facts),
                     "privacy": self._agent("privacy", facts),
                     "anomaly": self._agent("anomaly", facts),
                     "access": self._agent("access", facts)}
            if needs_human:
                notes["reviewer"] = self._agent("reviewer", facts)
            transform = ladder.to_json() if ladder else {}
            transform["agent_notes"] = notes
            transform["agent_agrees"] = (facts["agent_recommendation"] == outcome.split("_")[0]
                                         or facts["agent_recommendation"] == outcome)
            risk = {"consent": elig.counts_only() if elig else {},
                    "assessment": ladder.risk_after if ladder else {},
                    "before": ladder.risk_before if ladder else {}}
            self.store.save_decision(req_id, {
                "outcome": outcome, "reasons": reasons, "risk": risk, "transform": transform,
                "explanation": text, "needs_human": needs_human, "private": private,
                "release": release})
            self.store.set_request_status(req_id, status or (
                "released" if release is not None else "held" if needs_human else "denied"))
            self.audit.append("system", "decision.made", {
                "request_id": req_id, "outcome": outcome, "reasons": reasons,
                "needs_human": needs_human, "released": release is not None,
                "band_before": (ladder.risk_before.get("band") if ladder else None),
                "band_after": (ladder.risk_after.get("band") if ladder else None)})
            return self.store.decision(req_id)

        # -- frozen accounts get a hard 403 (decision recorded + audited) ---------------
        if requester["id"] in self.monitor.frozen:
            self.audit.append("system", "request.refused_frozen", {"request_id": req_id})
            finish("deny", ["requester_frozen"])
            raise ServiceError(403, "requester_frozen", "this account is frozen pending human "
                               "review", {"request_id": req_id, "reasons": ["requester_frozen"]})

        # -- credential tier ------------------------------------------------------------
        level = clean["data_level"]
        if (level == "record" and tier != "controlled") or (
                tier == "anonymous" and level not in ("boolean", "count")):
            self.audit.append("system", "tier.refused", {"request_id": req_id, "tier": tier,
                                                         "data_level": level})
            return finish("deny", ["credential_insufficient"])

        # -- consent ----------------------------------------------------------------------
        pop = clean["cohort_filter"].get("population")
        creq = ConsentRequest(clean["purpose"], clean["disease"], clean["is_commercial"], level,
                              pop if isinstance(pop, str) else None, clean["cohort_filter"])
        elig = eligible_cohort(creq, self.ds.donors)
        self.audit.append("system:consent", "consent.evaluated", {"request_id": req_id,
                                                                  **elig.counts_only()})
        vidx = self.resolve_variants(clean["variant_filter"])
        if not vidx:
            return finish("deny", ["no_variants"], elig=elig)
        if tier == "anonymous" and elig.n < 5 * self.p.k_min:
            return finish("deny", ["cohort_too_small_for_tier"], elig=elig)

        # -- risk + transform ladder (not charged yet) ----------------------------------
        ladder = run_ladder(self.ds, elig.donor_ids, vidx, level, self.p,
                            epsilon_available=self._remaining(rid), build_release=False,
                            rng=np.random.default_rng(req_id))
        self.audit.append("system:risk", "risk.estimated", {
            "request_id": req_id, "before": _brief(ladder.risk_before),
            "after": _brief(ladder.risk_after)})
        for st in ladder.steps:
            self.audit.append("system:transform", "transform.step", {"request_id": req_id, **st})

        # -- anomaly monitor --------------------------------------------------------------
        ev = QueryEvent(now, frozenset(vidx), clean["cohort_filter"],
                        frozenset(elig.donor_ids), ladder.epsilon_spent)
        a = self.monitor.observe(rid, ev)
        self._record_timeline(rid, now, a, elig.n)
        self.audit.append("system:anomaly", "anomaly.assessed", {"request_id": req_id,
                                                                 **a.to_json()})
        kw = {"elig": elig, "ladder": ladder, "assess": a}
        if a.action != "ok":
            self._alert(rid, a, req_id)

        private = {"kind": "release", "plan": {
            "level": ladder.plan.level, "variant_idx": list(ladder.plan.variant_idx),
            "bin_width": ladder.plan.bin_width, "epsilon": ladder.plan.epsilon},
            "subjects": self._carriers(elig.donor_ids, vidx)[:200], "cohort_filter":
            clean["cohort_filter"]}

        if a.blocked and a.action != "freeze":
            return finish("deny", ["differencing_guard"], **kw)
        if a.action == "freeze":
            self.store.set_frozen(rid, True)
            self.audit.append("system:anomaly", "requester.frozen", {
                "requester_id": rid, "request_id": req_id, "score": round(a.score, 3)})
            reasons = ["requester_frozen"] + (["differencing_guard"] if a.blocked else [])
            return finish("escalate", reasons, needs_human=True,
                          private={**private, "kind": "account"}, **kw)
        if ladder.outcome == "deny":
            return finish("deny", ladder.reasons, **kw)
        if ladder.outcome == "escalate":
            return finish("escalate", ladder.reasons, needs_human=True, private=private, **kw)
        if a.action == "throttle":
            return finish("escalate", ["requester_throttled"], needs_human=True,
                          private=private, **kw)
        if level == "record":
            return finish("escalate", ["record_level_needs_approval", "record_rows_never_released"],
                          needs_human=True, private=private, **kw)
        release = self._release(rid, req_id, elig.donor_ids, private["plan"], ladder.epsilon_spent)
        return finish(ladder.outcome, ladder.reasons, release=release, private=private, **kw)

    # ------------------------------------------------------------------ release
    def _release(self, rid: int, req_id: int, donor_ids: list[int], plan_d: dict,
                 eps: float) -> dict:
        plan = TransformPlan(plan_d["level"], tuple(plan_d["variant_idx"]), plan_d["bin_width"],
                             plan_d["epsilon"])
        assert plan.level != "record", "genotype rows are never returned"
        if eps:
            self._charge(rid, eps)
        out = materialize(self.ds.genotypes, donor_ids, plan, np.random.default_rng(req_id))
        out["variant_ids"] = [int(v) + 1 for v in plan.variant_idx]
        out["n_donors"] = len(donor_ids)
        out["epsilon_spent"] = eps
        self.audit.append("system", "release.issued", {
            "request_id": req_id, "level": plan.level, "n_variants": len(plan.variant_idx),
            "n_donors": len(donor_ids), "epsilon": eps,
            "release_sha256": hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()})
        return out

    # ------------------------------------------------------------------ monitor plumbing
    def _record_timeline(self, rid: int, now: float, a, cohort_n: int) -> None:
        d = a.detectors
        self.timeline.setdefault(rid, []).append({
            "t": now, "score": round(a.score, 3), "action": a.action, "cohort_n": cohort_n,
            "rate": round(d["rate"]["score"], 3), "similarity": round(d["duplicate"]["score"], 3),
            "narrowing": round(d["narrowing"]["score"], 3),
            "differencing": round(d["differencing"]["score"], 3)})

    def _alert(self, rid: int, a, req_id: int) -> None:
        top = max(a.detectors.items(), key=lambda kv: kv[1]["score"])
        kind = "differencing" if a.blocked else top[0]
        self.store.add_alert(rid, kind, a.score, {"request_id": req_id, **a.to_json()}, a.action)
        self.audit.append("system:anomaly", "alert.raised", {
            "requester_id": rid, "request_id": req_id, "kind": kind,
            "score": round(a.score, 3), "action": a.action})

    # ================================================================== human actions
    def review(self, req_id: int, reviewer: str, approve: bool) -> dict:
        d = self.store.decision(req_id)
        if not d:
            raise ServiceError(404, "not_found", "no such request")
        if not d["needs_human"] or d["reviewed_by"]:
            raise ServiceError(409, "not_reviewable", "request is not awaiting human review")
        priv = self.store.private(req_id)
        rid = d["requester_id"]
        now = now_iso()
        self.audit.append(f"human:{reviewer}", "review.approved" if approve else "review.denied",
                          {"request_id": req_id, "kind": priv.get("kind")})
        if priv.get("kind") == "account":
            if approve:
                self.unfreeze(rid, reviewer)
            self.store.update_decision(req_id, reviewed_by=reviewer, reviewed_at=now,
                                       needs_human=0)
            self.store.set_request_status(req_id, "reviewed")
            return self.store.decision(req_id)
        if not approve:
            self.store.update_decision(req_id, outcome="deny", reviewed_by=reviewer,
                                       reviewed_at=now, needs_human=0)
            self.store.set_request_status(req_id, "denied")
            return self.store.decision(req_id)
        # approve: re-check consent NOW (it may have changed), then release the stored plan
        r = d["request"]
        pop = r["cohort_filter"].get("population")
        creq = ConsentRequest(r["purpose"], r["disease"], r["is_commercial"], r["data_level"],
                              pop if isinstance(pop, str) else None, r["cohort_filter"])
        elig = eligible_cohort(creq, self.ds.donors)
        plan = priv["plan"]
        eps = plan["epsilon"] or 0.0
        if elig.n < self.p.k_min:
            self.store.update_decision(req_id, outcome="deny", reviewed_by=reviewer,
                                       reviewed_at=now, needs_human=0, reasons=["below_k_min"])
            self.store.set_request_status(req_id, "denied")
            return self.store.decision(req_id)
        if eps > self._remaining(rid) + 1e-12:
            self.store.update_decision(req_id, outcome="deny", reviewed_by=reviewer,
                                       reviewed_at=now, needs_human=0,
                                       reasons=["epsilon_budget_exhausted"])
            self.store.set_request_status(req_id, "denied")
            return self.store.decision(req_id)
        release = self._release(rid, req_id, elig.donor_ids, plan, eps)
        self.store.update_decision(req_id, outcome="permit_with_transform", reviewed_by=reviewer,
                                   reviewed_at=now, needs_human=0, release=release)
        self.store.set_request_status(req_id, "released")
        return self.store.decision(req_id)

    def freeze(self, rid: int, by: str = "admin") -> dict:
        if not self.store.requester(rid):
            raise ServiceError(404, "not_found", "no such requester")
        self.monitor.freeze(rid)
        self.store.set_frozen(rid, True)
        self.audit.append(f"human:{by}", "requester.frozen", {"requester_id": rid, "manual": True})
        return self.store.requester(rid)

    def unfreeze(self, rid: int, by: str = "admin") -> dict:
        if not self.store.requester(rid):
            raise ServiceError(404, "not_found", "no such requester")
        self.monitor.unfreeze(rid)
        self.store.set_frozen(rid, False)
        self.audit.append(f"human:{by}", "requester.unfrozen", {"requester_id": rid})
        return self.store.requester(rid)

    # ================================================================== read models
    def requests_for(self, requester: dict | None, limit: int = 200) -> list[dict]:
        rows = self.store.decisions(None if requester is None else requester["id"], limit)
        for r in rows:
            r.pop("release", None)  # lists stay light; detail view carries the release
        return rows

    def eligibility(self, requester: dict, purpose: str, disease: str | None,
                    commercial: bool, level: str, cohort_filter: dict) -> dict:
        clean = self._validate({"purpose": purpose, "disease": disease, "is_commercial": commercial,
                                "data_level": level, "cohort_filter": cohort_filter})
        pop = clean["cohort_filter"].get("population")
        creq = ConsentRequest(purpose, clean["disease"], commercial, level,
                              pop if isinstance(pop, str) else None, clean["cohort_filter"])
        return eligible_cohort(creq, self.ds.donors).counts_only()

    def anomalies(self) -> dict:
        reqs = {r["id"]: r for r in self.store.requesters()}
        return {"requesters": [
            {**reqs[rid], "frozen": rid in self.monitor.frozen,
             "timeline": tl[-60:]} for rid, tl in self.timeline.items() if rid in reqs]
            + [{**r, "frozen": r["id"] in self.monitor.frozen, "timeline": []}
               for r in reqs.values() if r["id"] not in self.timeline],
            "alerts": self.store.alerts(100)}

    def exposure(self, req_id: int) -> dict:
        """Family-exposure graph for the UI. Nodes use pseudonyms (S1.., R1..); no donor ids, no
        genotypes. SIMULATED MODEL: expected-average kinship, not a forecast about any database."""
        d = self.store.decision(req_id, with_release=False)
        if not d:
            raise ServiceError(404, "not_found", "no such request")
        subjects = self.store.private(req_id).get("subjects", [])
        in_cohort = set(subjects)
        fam = {x.id: x.family_id for x in self.ds.donors}
        by_family: dict[int, list[int]] = {}
        for s in subjects:
            by_family.setdefault(fam[s], []).append(s)
        families, total, by_degree = [], 0, {}
        for k, (fid, subs) in enumerate(sorted(by_family.items(), key=lambda kv: -len(kv[1]))[:6]):
            nodes, edges, seen = [], [], {}
            for i, s in enumerate(subs):
                sid = f"S{k + 1}.{i + 1}"
                seen[s] = sid
                nodes.append({"id": sid, "kind": "carrier", "label": "Rare-variant carrier"})
            for s in subs:
                for other, relation, shared in self.ds.relatives.get(s, []):
                    if shared < self.p.exposure_min_shared:
                        continue
                    if other not in seen:
                        rid_ = f"R{k + 1}.{len([n for n in nodes if n['kind'] == 'relative']) + 1}"
                        seen[other] = rid_
                        nodes.append({"id": rid_, "kind": "relative", "exposed": other not in
                                      in_cohort, "relation": "", "shared": 0.0})
                        if other not in in_cohort:
                            total += 1
                            deg = str(round(-np.log2(shared)))
                            by_degree[deg] = by_degree.get(deg, 0) + 1
                    node = next(n for n in nodes if n["id"] == seen[other])
                    if node["kind"] == "relative" and shared > node["shared"]:
                        node["shared"] = round(shared, 4)
                        node["relation"] = inverse_relation(relation) if self._is_a(
                            s, other, relation) else relation
                    edges.append({"from": seen[s], "to": seen[other], "relation": relation,
                                  "shared": round(shared, 4)})
            families.append({"family": f"Family {k + 1}", "nodes": nodes, "edges": edges})
        return {"request_id": req_id, "families": families,
                "totals": {"subjects": len(subjects), "exposed_relatives": total,
                           "by_degree": by_degree},
                "model": "SIMULATED: expected-average kinship from a synthetic pedigree; real "
                         "sharing varies and this is not a forecast about any real database.",
                "note": "Nodes are pseudonyms for this view only."}

    def _is_a(self, subject: int, other: int, relation: str) -> bool:
        """True if `subject` is donor_b of the stored pair (so the label must be inverted)."""
        for r in self.ds.relationships:
            if r["donor_a"] == other and r["donor_b"] == subject and r["relation"] == relation:
                return True
        return False

    # ------------------------------------------------------------------ audit / reports
    def audit_view(self, limit: int = 300, anchor: dict | None = None) -> dict:
        rows = self.audit.entries()
        return {"verify": self.audit.verify(anchor), "head": self.audit.head(),
                "entries": rows[-limit:][::-1]}

    def tamper(self, idx: int) -> dict:
        try:
            self.audit.tamper(idx)
        except PermissionError:
            raise ServiceError(403, "tamper_disabled",
                               "set GG_ALLOW_TAMPER_DEMO=true to enable the demo") from None
        except IndexError:
            raise ServiceError(404, "not_found", "no such audit entry") from None
        return self.audit.verify()

    def restore_demo(self) -> None:
        """Demo helper: rebuild the audit chain from scratch is NOT offered (that would defeat the
        point); instead the UI tells the presenter to restart with a fresh database."""
        raise ServiceError(405, "not_supported", "a tampered chain stays tampered; reset the DB")

    def compliance_report(self, start: str | None = None, end: str | None = None) -> dict:
        rows = self.store.decisions(None, 5000)
        if start:
            rows = [r for r in rows if r["ts"] >= start]
        if end:
            rows = [r for r in rows if r["ts"] <= end]
        outcomes: dict[str, int] = {}
        denials: dict[str, int] = {}
        for r in rows:
            outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
            if r["outcome"] == "deny":
                for c in r["reasons"]:
                    denials[c] = denials.get(c, 0) + 1
        alerts = [a for a in self.store.alerts(5000)
                  if (not start or a["ts"] >= start) and (not end or a["ts"] <= end)]
        entries = self.audit.entries()
        acts = [e["action"] for e in entries]
        v = self.audit.verify()
        facts = {"period": f"{(start or 'start')[:10]}_to_{(end or 'now')[:10]}".replace("-", "_"),
                 "requests": len(rows), "outcomes": outcomes, "denials_by_reason": denials,
                 "alerts": len(alerts), "freezes": acts.count("requester.frozen"),
                 "reviews": acts.count("review.approved") + acts.count("review.denied"),
                 "chain_ok": v["ok"], "chain_length": v["length"]}
        text = self._agent("compliance", facts)
        return {"facts": facts, "report": text, "generated_at": datetime.now(UTC).isoformat(
            timespec="seconds"), "head": self.audit.head()}


def _brief(r: dict) -> dict:
    keys = ("n", "level", "n_variants", "band", "band_reasons", "uniqueness_rate",
            "rare_variants", "rare_few_carriers", "membership_signal")
    out = {k: r.get(k) for k in keys}
    out["relatives_exposed_total"] = (r.get("relatives_exposed") or {}).get("total")
    return jsonable(out)


# ====================================================================== bootstrap
DEMO_REQUESTERS = [
    ("Dr. Amara Nwosu", "researcher", "registered", "Demo University", "demo-researcher"),
    ("Probe Account", "researcher", "registered", "Unknown Lab", "demo-attacker"),
    ("Public Viewer", "visitor", "anonymous", "-", "demo-anonymous"),
    ("Controlled-Access Lab", "researcher", "controlled", "Demo Hospital", "demo-controlled"),
]


def bootstrap(settings=None, p: Params = DEFAULT, store: Store | None = None,
              llm: LLM | None = None, **kwargs) -> GenomeGuardService:
    """Open (or create and seed) the database and return a ready service."""
    from app.config import get_settings
    from app.data.synth import generate

    s = settings or get_settings()
    store = store or Store(s.db_path)
    master = crypto.load_master_key(s.master_key)
    if not store.has_dataset():
        cohort = generate(n_donors=s.n_donors, n_variants=s.n_variants,
                          n_populations=s.n_populations, n_families=s.n_families, seed=s.seed,
                          n_planted=s.n_planted_rare, rare_maf=p.rare_maf)
        store.save_cohort(cohort, master, s.dataset_id)
    ds = store.load_dataset(master, s.dataset_id)
    llm = llm or LLM(s.anthropic_api_key, s.llm_model)
    svc = GenomeGuardService(store, ds, p, master=master, llm=llm, allow_tamper=s.allow_tamper_demo,
                             admin_key=s.admin_api_key, **kwargs)
    if not store.requesters():
        if s.demo_mode:
            for name, role, level, inst, key in DEMO_REQUESTERS:
                svc.create_requester(name, role, level, inst, key)
    return svc
