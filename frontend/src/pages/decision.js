import { api, isSteward, state } from "../api.js";
import { h, row, badge, lane, when, notice, errorText, reasonText, stepText, OUTCOME_LABEL, pct, workflow, timeline, pipeline } from "../ui.js";

export async function render([id]) {
  if (!state.demo && !state.authToken && !state.who && !state.adminKey) {
    return h("div", {}, h("h1", {}, "Request #" + id),
      notice("warn", "Connect with an issued researcher API key or steward key in the sign-in panel before viewing request details."),
      h("a", { href: "#/requests" }, "Back to requests"));
  }
  const res = await api("/requests/" + id);
  if (!res.ok) { const r = h("div", {}, h("h1", {}, "Request #" + id), notice("err", errorText(res)), h("a", { href: "#/requests" }, "Back to requests")); return r; }
  if (state.authToken) return renderSupabaseRequest(res.data, id);
  const d = res.data, q = d.request || {}, risk = d.risk || {}, tr = d.transform || {};
  const root = h("div", {});
  root.dataset.title = "Request #" + id;
  const eligible = (risk.consent || {}).eligible, considered = (risk.consent || {}).considered, ex = (risk.consent || {}).excluded_by_reason || {};
  const before = risk.before || {}, after = risk.assessment || {};
  root.append(h("a", { href: "#/requests" }, "All requests"),
    h("h1", { style: "margin-top:8px" }, "Request #" + d.id),
    h("p", { class: "lede" }, `${d.requester} asked for ${q.data_level} data for ${(q.purpose || "").replaceAll("_", " ")}${q.disease ? (state.demo ? " (" + q.disease + ")" : " (topic label: " + q.disease + "; not a cohort phenotype)") : ""}${q.is_commercial ? ", commercial use" : ""}. ${when(d.ts)}`));

  const flow = workflow(d);
  root.append(h("section", { class: "card", style: "margin-bottom:14px" }, h("div", { class: "card-h" }, h("h2", { class: "card-title", style: "margin:0" }, "How the agents handled it"), h("span", {}, "Agents advise, rules decide")), pipeline(flow), h("div", { style: "margin-top:18px" }, timeline(flow))));
  const ledger = h("div", { class: "ledger" });
  ledger.append(row("Decision", "Made by rules, explained by an agent",
    h("p", { class: "verdict o-" + d.outcome }, OUTCOME_LABEL[d.outcome] || d.outcome),
    h("p", {}, d.explanation),
    (d.reasons || []).length ? h("ul", { class: "plain" }, d.reasons.map((r) => h("li", {}, reasonText(r)))) : null,
    d.status === "held" ? notice("warn", "A human steward must review this request before anything is released.") : null,
    d.status === "approved_pending_release" ? notice("warn", "A steward approved the request. Data remains withheld until a separate governed release is re-validated.") : null,
    d.status === "needs_information" ? notice("warn", "The steward requested more information. No data was released.") : null));

  if (considered != null) {
    const out_ = Object.values(ex).reduce((a, b) => a + b, 0);
    ledger.append(row(state.demo ? "Simulated consent" : "Dataset policy", state.demo
      ? "Synthetic permissions used only for the local demonstration"
      : "Dataset-level public-release policy; not participant-specific consent",
      h("p", { style: "margin:0" }, h("b", {}, eligible), state.demo
        ? ` of ${considered} synthetic donors pass simulated permission rules.`
        : ` of ${considered} individuals pass the dataset-level policy mapping for this request.`),
      !state.demo ? h("p", { class: "muted" }, "This is not evidence of individual consent, clinical authorization, or legal approval.") : null,
      h("div", { class: "bar", role: "img", "aria-label": `${eligible} eligible of ${considered}` }, h("i", { class: "seg-ok", style: `width:${(100 * eligible) / (considered || 1)}%` }), h("i", { class: "seg-ex", style: `width:${(100 * out_) / (considered || 1)}%` })),
      Object.keys(ex).length ? h("ul", { class: "plain" }, Object.entries(ex).sort((a, b) => b[1] - a[1]).map(([k, v]) => h("li", {}, `${v} excluded: ${reasonText(k)}`))) : null));
  }

  if (before.band) {
    ledger.append(row("Re-identification risk", "Before and after protections",
      h("div", { class: "shift" }, h("div", {}, h("div", { class: "muted" }, "As requested"), lane(before.band)),
        h("span", { class: "arrow", "aria-hidden": "true" }), h("div", {}, h("div", { class: "muted" }, "As released"), lane(after.band || before.band))),
      (before.band_reasons || []).length ? h("p", { class: "muted" }, "Why it was flagged: " + before.band_reasons.map(reasonText).join("; ")) : null,
      h("dl", { class: "facts", style: "margin-top:10px" },
        h("dt", {}, "Donors in release"), h("dd", {}, String(after.n ?? before.n)),
        h("dt", {}, "Variants requested, then released"), h("dd", {}, `${before.n_variants} requested, ${after.n_variants} released`),
        after.membership_signal != null ? [h("dt", {}, "Membership signal"), h("dd", {}, Number(after.membership_signal).toFixed(2))] : null)));
  }

  const steps = tr.steps || [];
  if (before.band) {
    ledger.append(row("Protections", "Applied in order until risk is acceptable",
      steps.length ? h("ol", { class: "steps" }, steps.map((s) => h("li", {}, h("div", {}, h("b", {}, stepText(s.step)), h("div", { class: "muted" }, s.detail)), h("span", { class: "pill " + (s.band === "low" ? "good" : s.band === "high" ? "bad" : "warn") }, "risk now " + s.band))))
        : h("p", { style: "margin:0" }, "No protection was needed.")));
  }

  const fin = tr.final || {};
  const budget = !isSteward() ? await api("/me") : null;
  if (fin.epsilon || (budget && budget.ok)) {
    const b = budget && budget.ok ? budget.data : null;
    ledger.append(row("Privacy budget", "Epsilon, simple accounting",
      fin.epsilon ? h("p", { style: "margin:0 0 6px" }, `This release spent epsilon ${fin.epsilon} (noise scale ${Number(fin.noise_scale).toFixed(0)}).`) : h("p", { style: "margin:0 0 6px" }, "This release added no noise, so it spent no budget."),
      b ? [h("div", { class: "bar", role: "img", "aria-label": "budget used" }, h("i", { class: "seg-ok", style: `width:${(100 * b.epsilon_remaining) / b.epsilon_budget}%` })),
        h("div", { class: "legend" }, h("span", {}, `${b.epsilon_remaining.toFixed(2)} of ${b.epsilon_budget} remaining for this account`))] : null));
  }

  if (d.release) {
    const rel = d.release, vals = rel.values || [], ids = rel.variant_ids || [];
    ledger.append(row("Released data", `${rel.level}, ${vals.length} variants`,
      h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Variant"), h("th", { class: "num" }, rel.level === "frequency" ? "Allele frequency" : rel.level === "count" ? "Allele count" : "Present"))),
        h("tbody", {}, vals.slice(0, 30).map((v, i) => h("tr", {}, h("td", {}, h("a", { href: "#/variants?q=" + encodeURIComponent("v" + ids[i]) }, "v" + ids[i])), h("td", { class: "num" }, typeof v === "boolean" ? (v ? "yes" : "no") : String(v))))))),
      vals.length > 30 ? h("p", { class: "muted" }, `Showing 30 of ${vals.length}.`) : null,
      h("p", { class: "muted" }, "Aggregate only. No individual genotypes, donor identities or cohort membership are ever returned.")));
  } else if (d.status !== "held") {
    ledger.append(row("Released data", "", h("p", { style: "margin:0" }, "Nothing was released.")));
  }

  if (isSteward()) ledger.append(copilotRow(d), stewardPanel(d, before, after, tr));
  root.append(ledger);
  return root;
}


function renderSupabaseRequest(data, id) {
  const request = data.request || {};
  const decision = data.decision || {};
  const status = request.status || "pending_review";
  const statusText = {
    pending_review: "Waiting for steward review",
    needs_more_information: "More information requested",
    approved_pending_release: "Approved for review; release remains blocked",
    denied: "Denied",
  }[status] || status.replaceAll("_", " ");
  const root = h("div", {});
  root.dataset.title = "Request #" + id;
  root.append(
    h("a", { href: "#/requests" }, "All requests"),
    h("h1", { style: "margin-top:8px" }, "Request #" + id),
    h("p", { class: "lede" }, `${isSteward() ? "Organization request" : "Your request"} · ${(request.purpose || "").replaceAll("_", " ")} · ${request.data_level || "unspecified"} · ${when(request.created_at)}`),
    notice(status === "denied" ? "err" : status === "approved_pending_release" ? "warn" : "info", statusText),
    h("section", { class: "card" },
      h("h2", {}, "Request details"),
      h("dl", { class: "facts" },
        h("dt", {}, "Research purpose"), h("dd", {}, (request.purpose || "—").replaceAll("_", " ")),
        h("dt", {}, "Research topic"), h("dd", {}, request.disease || "Not specified"),
        h("dt", {}, "Data level"), h("dd", {}, request.data_level || "—"),
        h("dt", {}, "Commercial use"), h("dd", {}, request.is_commercial ? "Yes" : "No"),
        h("dt", {}, "Organization"), h("dd", {}, request.organization_id || "Verified membership"))),
    h("section", { class: "card", style: "margin-top:14px" },
      h("h2", {}, "Decision"),
      h("p", {}, decision.outcome ? OUTCOME_LABEL[decision.outcome] || decision.outcome : "No steward decision recorded yet."),
      h("p", { class: "muted" }, decision.explanation || "This request is stored for human review. The Supabase request API does not run the genomic policy engine or release data."),
      (decision.reasons || []).length ? h("ul", { class: "plain" }, decision.reasons.map((reason) => h("li", {}, reasonText(reason)))) : null,
      notice("warn", "No genomic data has been released by this request workflow. An approval is not a data-release authorization.")),
  );

  const history = data.review_history || [];
  root.append(h("section", { class: "card", style: "margin-top:14px" },
    h("h2", {}, "Review history"),
    history.length ? h("ol", { class: "plain" }, history.map((entry) =>
      h("li", {}, `${entry.outcome.replaceAll("_", " ")} · ${when(entry.created_at)} · ${entry.reason}`)))
      : h("p", { class: "muted" }, "No review actions have been recorded.")));

  if (isSteward() && ["pending_review", "needs_more_information"].includes(status)) {
    const reason = h("textarea", { rows: 3, maxlength: 2000, placeholder: "Explain the review decision (3–2000 characters)." });
    const message = h("div", { "aria-live": "polite" });
    const submitReview = async (outcome, button) => {
      const value = reason.value.trim();
      if (value.length < 3 || value.length > 2000) {
        message.replaceChildren(notice("err", "Enter a review reason between 3 and 2,000 characters."));
        return;
      }
      button.disabled = true;
      message.replaceChildren(notice("info", "Saving the review decision…"));
      const result = await api(`/requests/${id}/review`, {
        method: "POST", body: { outcome, reason: value },
      });
      button.disabled = false;
      if (!result.ok) {
        message.replaceChildren(notice("err", errorText(result)));
        return;
      }
      location.reload();
    };
    root.append(h("section", { class: "card", style: "margin-top:14px" },
      h("h2", {}, "Steward review"),
      h("label", { class: "f" }, "Reason", reason),
      h("div", { style: "display:flex;gap:10px;flex-wrap:wrap;margin-top:12px" },
        h("button", { onclick: (event) => submitReview("approved", event.target) }, "Approve for separate release review"),
        h("button", { class: "ghost", onclick: (event) => submitReview("needs_more_information", event.target) }, "Request more information"),
        h("button", { class: "danger", onclick: (event) => submitReview("denied", event.target) }, "Deny")),
      message));
  }
  return root;
}

function stewardPanel(d, before, after, tr) {
  const rel = before.relatives_exposed || {}, notes = tr.agent_notes || {};
  const msg = h("div", {});
  const review = async (action) => {
    const r = await api(`/requests/${d.id}/review`, { method: "POST", body: { reviewer: "steward", action } });
    if (r.ok) location.reload(); else msg.replaceChildren(notice("err", errorText(r)));
  };
  const release = async () => {
    const r = await api(`/requests/${d.id}/release`, { method: "POST", body: { reviewer: "steward" } });
    if (r.ok) location.reload(); else msg.replaceChildren(notice("err", errorText(r)));
  };
  const controls = d.status === "held" && d.needs_human
    ? h("div", { style: "margin-top:12px;display:flex;gap:10px;flex-wrap:wrap" },
      h("button", { onclick: () => review("approve") }, "Approve for separate release"),
      h("button", { class: "ghost", onclick: () => review("request_information") }, "Request more information"),
      h("button", { class: "danger", onclick: () => review("deny") }, "Deny"))
    : d.status === "approved_pending_release"
      ? h("div", { style: "margin-top:12px" },
        notice("warn", "This is a distinct release operation. Current policy, cohort size, risk and privacy budget will be checked again."),
        h("button", { onclick: release }, "Re-check and release governed aggregate"))
      : null;
  return row("Steward detail", "Not shown to researchers",
    h("dl", { class: "facts" },
      h("dt", {}, "Rare variants requested"), h("dd", {}, String(before.rare_variants ?? 0)),
      h("dt", {}, "Fewest carriers of any rare variant"), h("dd", {}, before.min_carriers ?? "none"),
      h("dt", {}, "Relatives exposed (simulated)"), h("dd", {}, String(rel.total ?? 0)),
      h("dt", {}, "Expected shared DNA, summed"), h("dd", {}, rel.expected_shared_dna != null ? Number(rel.expected_shared_dna).toFixed(2) : "n/a")),
    rel.total ? h("p", {}, h("a", { href: "#/family/" + d.id }, "Open the family tree"), " to see which relatives would be exposed.") : null,
    Object.keys(notes).length ? h("div", {}, h("h3", { style: "margin-top:12px" }, "Agent notes (advisory)"), h("ul", { class: "plain" }, Object.entries(notes).filter(([, t]) => t).map(([k, t]) => h("li", {}, h("b", {}, k + ": "), t)))) : null,
    controls,
    d.reviewed_by ? h("p", { class: "muted" }, `Reviewed by ${d.reviewed_by} on ${when(d.reviewed_at)}.`) : null, msg);
}

// ---- steward copilot: a read-only, tool-using agent. It advises; the human clicks. ----
const TOOL_LABEL = {
  case_summary: "Read the case", consent_counts: "Checked consent", risk_profile: "Measured risk",
  family_exposure: "Looked at relatives", requester_history: "Checked the account's history",
  privacy_budget: "Checked the privacy budget", audit_status: "Verified the audit chain",
};
const REC = {
  approve: ["good", "Approve"], deny: ["bad", "Deny"], more_info: ["warn", "Ask for more information"],
};

function toolSummary(tool, r) {
  const n = (x, d = 0) => (x == null ? d : x);
  switch (tool) {
    case "case_summary":
      return `${OUTCOME_LABEL[r.outcome] || r.outcome}${(r.reasons || []).length ? ": " + r.reasons.map(reasonText).join("; ") : ""}.`;
    case "consent_counts": {
      const c = r.consent || {};
      return c.considered == null ? "No policy count was recorded."
        : state.demo
          ? `${c.eligible} of ${c.considered} synthetic donors pass simulated permission rules.`
          : state.health?.provenance?.consent === "source_records"
            ? `${c.eligible} of ${c.considered} individuals pass source-matched consent rules.`
            : `${c.eligible} of ${c.considered} individuals pass the dataset-level policy mapping; this is not participant-specific consent.`;
    }
    case "risk_profile": {
      const b = r.risk_before || {}, a = r.risk_after || {};
      return `Risk ${b.band || "n/a"} as requested, ${a.band || "n/a"} as released; ${n(a.rare_variants)} rare variants left in the release.`;
    }
    case "family_exposure":
      return `${n(r.relatives_exposed_total)} relatives of ${n(r.subjects)} rare-variant carriers could be exposed (simulated model).`;
    case "requester_history":
      return `${n(r.history_requests)} earlier requests, ${n(r.history_denials)} denials, ${n(r.history_alerts)} alerts${r.frozen ? ", account frozen" : ""}.`;
    case "privacy_budget":
      return `${Number(n(r.epsilon_remaining)).toFixed(2)} of ${n(r.epsilon_budget)} epsilon left; this release costs ${n(r.epsilon)}.`;
    case "audit_status":
      return r.chain_ok === false ? "The audit chain does NOT verify." : `Intact, ${n(r.chain_length)} entries.`;
    default: return "";
  }
}

function copilotRow(d) {
  const out = h("div", { "aria-live": "polite" });
  const btn = h("button", { class: "ghost", onclick: () => run(true) }, "Investigate this request");
  const autorun = d.status === "held" && d.needs_human && !d.reviewed_by;

  function draw(c) {
    const [tone, label] = REC[c.recommendation] || ["", c.recommendation];
    out.replaceChildren(...[
      h("ol", { class: "steps" }, (c.steps || []).map((s) => h("li", {},
        h("div", {}, h("b", {}, `${s.step}. ${TOOL_LABEL[s.tool] || s.tool}`), h("div", { class: "muted" }, s.why), h("div", {}, toolSummary(s.tool, s.result || {}))),
        h("span", { class: "muted" }, "read only")))),
      h("div", { style: "margin-top:14px" }, h("span", { class: "pill " + tone }, "Copilot suggests: " + label), " ",
        h("span", { class: "muted" }, c.used_llm ? `written by ${c.model}` : "built-in planner, no model needed")),
      h("p", { style: "margin:10px 0" }, c.rationale),
      (c.questions || []).length ? h("div", {}, h("b", {}, "Questions for you"), h("ul", { class: "plain" }, c.questions.map((q) => h("li", {}, q)))) : null,
      c.rejected_reason ? h("p", { class: "muted" }, "A model answer was set aside (" + c.rejected_reason.replaceAll("_", " ") + "); the fixed rules' answer is shown.") : null,
      h("p", { class: "muted" }, c.authority),
      h("button", { class: "ghost", onclick: () => run(true) }, "Run again")].filter(Boolean));
  }

  async function run(refresh) {
    btn.disabled = true;
    out.replaceChildren(h("div", { class: "skeleton", style: "height:72px" }));
    const r = await api(`/requests/${d.id}/copilot${refresh ? "?refresh=true" : ""}`, { method: "POST" });
    btn.disabled = false;
    if (r.ok) draw(r.data); else out.replaceChildren(notice("err", errorText(r)), btn);
  }

  if (autorun) run(false);
  return row("Steward copilot", "An agent that investigates. Advisory only.",
    autorun ? null : h("p", { class: "muted", style: "margin-top:0" }, "A read-only agent chooses which evidence to gather (consent, risk, relatives, history, audit), then recommends. It cannot approve, deny or freeze anything."),
    autorun ? null : btn, out);
}
