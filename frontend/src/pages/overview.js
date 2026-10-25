import { api, state, isSteward } from "../api.js";
import { h, card, kpi, badge, pipeline, workflow, when, pct } from "../ui.js";
import { startTour, tourAvailable } from "../tour.js";

const ROSTER = [
  ["Consent agent", "Reads each donor's permissions and keeps out anyone who did not agree to this use."],
  ["Privacy risk agent", "Scores how easily someone could be re-identified, including their relatives."],
  ["Anomaly monitor", "Watches query patterns for probing and freezes accounts that look like attacks."],
  ["Explainer agent", "Tells the researcher in plain words why a request was approved, changed or refused."],
  ["Audit agent", "Writes every decision into a tamper-evident hash chain."],
  ["Consent concierge", "Answers donors' questions about who used their data. Fixed questions only."],
];

export async function render() {
  const [reqs, verify, ev, me] = await Promise.all([
    api("/requests"), api("/audit/verify"),
    state.demo ? api("/eval/results") : Promise.resolve({ ok: false }),
    isSteward() ? Promise.resolve({ ok: false }) : api("/me"),
  ]);
  const rows = reqs.ok ? reqs.data.requests || [] : [];
  const hl = state.health || {};
  const count = (o) => rows.filter((r) => r.outcome === o).length;
  const latest = rows[0];
  const root = h("div", { class: "stack" });

  // hero: the live pipeline for the latest decision, or an idle one
  const idle = [["Consent"], ["Risk"], ["Protect"], ["Watch"], ["Decide"], ["Explain"], ["Record"]].map(([short]) => ({ short, state: "idle" }));
  let stages = idle, caption = "Send a request and watch the agents work.";
  if (latest) {
    const full = await api("/requests/" + latest.id);
    if (full.ok) { stages = workflow(full.data).map((s) => ({ ...s, d: "" })); caption = `Latest request, #${latest.id}: ${(latest.request || {}).data_level} data for ${((latest.request || {}).purpose || "").replaceAll("_", " ")}.`; }
  }
  const pipe = pipeline(stages, { play: !!latest });
  const hero = h("section", { class: "card hero" },
    h("h1", { style: "margin:0 0 6px" }, "Govern genomic data access with auditable decisions."),
    h("p", { class: "lede" }, "GenomeGuard is a team of AI agents that sits in front of a genomic data store. They check consent, weigh re-identification risk, add protections and keep a tamper-evident record. The agents advise. Fixed rules decide, and a person signs off on anything risky."),
    h("div", { style: "display:flex;gap:10px;flex-wrap:wrap;margin:0 0 18px" },
      tourAvailable() ? h("button", { onclick: startTour }, "Guided walkthrough") : null,
      h("a", { class: tourAvailable() ? "btn ghost" : "btn", href: "#/requests" }, isSteward() ? "Review requests" : "Send a request"),
      state.demo ? h("a", { class: "btn ghost", href: "#/donor" }, "Participant view") : null),
    pipe, h("p", { class: "muted", style: "margin:12px 0 0;display:flex;gap:12px;align-items:center;flex-wrap:wrap" }, caption,
      latest ? h("button", { class: "ghost", onclick: () => pipe.replay() }, "Replay workflow") : null));
  root.append(hero);

  const pv = hl.provenance || {};
  if (pv.genotypes) root.append(card("Where the data comes from", "Labelled so nothing is overstated",
    h("dl", { class: "facts" },
      h("dt", {}, "Genotypes"), h("dd", {}, pv.genotypes_label),
      h("dt", {}, "Consent records"), h("dd", {}, pv.consent_label + (pv.consent === "simulated"
        ? " — simulated records; not valid participant consent."
        : " — imported source records; legal validity is not independently verified.")),
      h("dt", {}, "Relatives"), h("dd", {}, pv.relatives_label),
      h("dt", {}, "Agents"), h("dd", {}, pv.agents_label + ". They never see genotypes."),
      h("dt", {}, "Storage"), h("dd", {}, pv.encryption))));
  const chain = verify.ok ? verify.data : null;
  const evd = ev.ok ? ev.data : null;
  const diff = evd && evd.differencing ? evd.differencing.accuracy : null;
  root.append(h("div", { class: "grid g4" },
    kpi("Requests handled", rows.length, rows.length ? `${count("permit") + count("permit_with_transform")} released` : "none yet"),
    kpi("Held for a human", count("escalate"), "waiting for a steward", count("escalate") ? "escalate" : null),
    kpi("Denied", count("deny"), "blocked before any release", count("deny") ? "deny" : null),
    kpi("Audit chain", chain ? (chain.ok ? "Intact" : "Broken") : "n/a", chain ? `${chain.length} entries` : "", chain && !chain.ok ? "deny" : "permit")));

  const feed = rows.length
    ? h("ul", { class: "feed" }, rows.slice(0, 6).map((r) => h("li", {}, badge(r.outcome), h("a", { href: "#/request/" + r.id }, `#${r.id} ${((r.request || {}).purpose || "").replaceAll("_", " ")}, ${(r.request || {}).data_level}`), h("span", { class: "m" }, when(r.ts)))))
    : h("div", { class: "empty" }, state.demo
      ? "Nothing yet. Open Requests and run a demo preset."
      : "No requests yet. Submit an authorized request from the Requests page.");
  const proof = h("dl", { class: "facts" },
    h("dt", {}, "Differencing attack, no defence"), h("dd", {}, diff ? pct(diff.none.mean, 0) + " recovered" : "run make eval"),
    h("dt", {}, "Same attack with GenomeGuard"), h("dd", {}, diff ? pct(diff.ladder_plus_guard.mean, 0) + " (guessing is " + pct(diff.baseline.mean, 0) + ")" : "n/a"),
    h("dt", {}, "Donors / variants"), h("dd", {}, `${hl.donors ?? "n/a"} / ${hl.variants ?? "n/a"} (${pv.genotypes_label || "provenance unknown"})`),
    h("dt", {}, "Smallest cohort released"), h("dd", {}, String(hl.k_min ?? "n/a")));
  root.append(h("div", { class: "grid g-main" },
    card("Recent activity", rows.length ? h("a", { href: "#/requests" }, "All requests") : null, feed),
    state.demo ? card("Does it hold up?", h("a", { href: "#/redteam" }, "Red-team results"), proof) : null));

  const roster = state.demo ? ROSTER : ROSTER.filter(([name]) => name !== "Consent concierge");
  root.append(card("The agent team", "Agents advise, rules decide",
    h("div", { class: "grid g2" }, roster.map(([n, t]) => h("div", {}, h("b", {}, n), h("p", { class: "muted", style: "margin:2px 0 0" }, t))))));
  return root;
}
