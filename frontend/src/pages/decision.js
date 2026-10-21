import { api, isSteward, state } from "../api.js";
import { h, row, badge, lane, when, notice, errorText, reasonText, stepText, OUTCOME_LABEL, pct } from "../ui.js";

export async function render([id]) {
  const res = await api("/requests/" + id);
  if (!res.ok) { const r = h("div", {}, h("h1", {}, "Request #" + id), notice("err", errorText(res)), h("a", { href: "#/requests" }, "Back to requests")); return r; }
  const d = res.data, q = d.request || {}, risk = d.risk || {}, tr = d.transform || {};
  const root = h("div", {});
  root.dataset.title = "Request #" + id;
  const eligible = (risk.consent || {}).eligible, considered = (risk.consent || {}).considered, ex = (risk.consent || {}).excluded_by_reason || {};
  const before = risk.before || {}, after = risk.assessment || {};
  root.append(h("a", { href: "#/requests" }, "All requests"),
    h("h1", { style: "margin-top:8px" }, "Request #" + d.id),
    h("p", { class: "lede" }, `${d.requester} asked for ${q.data_level} data for ${(q.purpose || "").replaceAll("_", " ")}${q.disease ? " (" + q.disease + ")" : ""}${q.is_commercial ? ", commercial use" : ""}. ${when(d.ts)}`));

  const ledger = h("div", { class: "ledger" });
  ledger.append(row("Decision", "Made by rules, explained by an agent",
    h("p", { class: "verdict o-" + d.outcome }, OUTCOME_LABEL[d.outcome] || d.outcome),
    h("p", {}, d.explanation),
    (d.reasons || []).length ? h("ul", { class: "plain" }, d.reasons.map((r) => h("li", {}, reasonText(r)))) : null,
    d.status === "held" ? notice("warn", "A human steward must approve or deny this before anything is released.") : null));

  if (considered != null) {
    const out_ = Object.values(ex).reduce((a, b) => a + b, 0);
    ledger.append(row("Consent", "Who agreed to this use",
      h("p", { style: "margin:0" }, h("b", {}, eligible), ` of ${considered} donors in the requested group have consent that fits.`),
      h("div", { class: "bar", role: "img", "aria-label": `${eligible} eligible of ${considered}` }, h("i", { class: "seg-ok", style: `width:${(100 * eligible) / (considered || 1)}%` }), h("i", { class: "seg-ex", style: `width:${(100 * out_) / (considered || 1)}%` })),
      Object.keys(ex).length ? h("ul", { class: "plain" }, Object.entries(ex).sort((a, b) => b[1] - a[1]).map(([k, v]) => h("li", {}, `${v} excluded: ${reasonText(k)}`))) : null));
  }

  if (before.band) {
    ledger.append(row("Re-identification risk", "Before and after protections",
      h("div", { class: "shift" }, h("div", {}, h("div", { class: "muted" }, "As requested"), lane(before.band)),
        h("span", { class: "arrow", "aria-hidden": "true" }, "→"), h("div", {}, h("div", { class: "muted" }, "As released"), lane(after.band || before.band))),
      (before.band_reasons || []).length ? h("p", { class: "muted" }, "Why it was flagged: " + before.band_reasons.map(reasonText).join("; ")) : null,
      h("dl", { class: "facts", style: "margin-top:10px" },
        h("dt", {}, "Donors in release"), h("dd", {}, String(after.n ?? before.n)),
        h("dt", {}, "Variants requested → released"), h("dd", {}, `${before.n_variants} → ${after.n_variants}`),
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
        h("tbody", {}, vals.slice(0, 30).map((v, i) => h("tr", {}, h("td", {}, "v" + ids[i]), h("td", { class: "num" }, typeof v === "boolean" ? (v ? "yes" : "no") : String(v))))))),
      vals.length > 30 ? h("p", { class: "muted" }, `Showing 30 of ${vals.length}.`) : null,
      h("p", { class: "muted" }, "Aggregate only. No individual genotypes, donor identities or cohort membership are ever returned.")));
  } else if (d.status !== "held") {
    ledger.append(row("Released data", "", h("p", { style: "margin:0" }, "Nothing was released.")));
  }

  if (isSteward()) ledger.append(stewardPanel(d, before, after, tr));
  root.append(ledger);
  return root;
}

function stewardPanel(d, before, after, tr) {
  const rel = before.relatives_exposed || {}, notes = tr.agent_notes || {};
  const msg = h("div", {});
  const review = async (approve) => {
    const r = await api(`/requests/${d.id}/review`, { method: "POST", body: { reviewer: "steward", approve } });
    if (r.ok) location.reload(); else msg.replaceChildren(notice("err", errorText(r)));
  };
  return row("Steward detail", "Not shown to researchers",
    h("dl", { class: "facts" },
      h("dt", {}, "Rare variants requested"), h("dd", {}, String(before.rare_variants ?? 0)),
      h("dt", {}, "Fewest carriers of any rare variant"), h("dd", {}, before.min_carriers ?? "none"),
      h("dt", {}, "Relatives exposed (simulated)"), h("dd", {}, String(rel.total ?? 0)),
      h("dt", {}, "Expected shared DNA, summed"), h("dd", {}, rel.expected_shared_dna != null ? Number(rel.expected_shared_dna).toFixed(2) : "n/a")),
    rel.total ? h("p", {}, h("a", { href: "#/family/" + d.id }, "Open the family tree"), " to see which relatives would be exposed.") : null,
    Object.keys(notes).length ? h("div", {}, h("h3", { style: "margin-top:12px" }, "Agent notes (advisory)"), h("ul", { class: "plain" }, Object.entries(notes).filter(([, t]) => t).map(([k, t]) => h("li", {}, h("b", {}, k + ": "), t)))) : null,
    d.status === "held" && d.needs_human ? h("div", { style: "margin-top:12px;display:flex;gap:10px" }, h("button", { onclick: () => review(true) }, "Approve release"), h("button", { class: "danger", onclick: () => review(false) }, "Deny")) : null,
    d.reviewed_by ? h("p", { class: "muted" }, `Reviewed by ${d.reviewed_by} on ${when(d.reviewed_at)}.`) : null, msg);
}
