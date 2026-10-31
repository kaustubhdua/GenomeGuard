import { api, state, isSteward } from "../api.js";
import { h, card, kpi, badge, bands, pipeline, workflow, when, pct, notice } from "../ui.js";
import { sampleStages } from "../sample-data.js";
import { startTour, tourAvailable } from "../tour.js";

const DEMO_ROSTER = [
  ["Consent agent (demo)", "Uses simulated participant permissions for local demonstration only; these are not real consent records."],
  ["Privacy risk assessment", "Estimates re-identification risk, including modeled relative exposure; it is not a clinical or independently validated risk score."],
  ["Anomaly monitor", "Checks query patterns for selected probing signals and may flag or freeze demo accounts."],
  ["Decision explainer (templates)", "Explains decisions using built-in templates; it does not imply a live language model is connected."],
  ["Audit log", "Records events in a locally hash-chained log. The chain is tamper-evident, not an independent immutable anchor."],
  ["Consent concierge (demo)", "Provides fixed scripted answers for the demo; it is not a real participant support channel."],
];

const READINESS_LABELS = {
  demo_mode_disabled: "Demo mode must be disabled",
  real_genotype_provenance: "Real genotype provenance must be verified",
  participant_consent_records_verified: "Required participant consent records must be verified",
  destructive_tamper_demo_disabled: "Destructive demo controls must be disabled",
  postgres_storage_configured: "PostgreSQL persistence must be configured",
  durable_storage_verified: "Durable persistence and recovery must be verified",
  external_audit_anchor_verified: "Independent audit anchoring must be verified",
  institutional_identity_provider_verified: "Institutional identity must be verified",
};

const RESEARCH_ROSTER = [
  ["Dataset policy provenance", "Applies the documented public-release policy mapping for this dataset. It is not participant-specific consent or a legal authorization decision."],
  ["Privacy risk assessment", "Computes heuristic risk estimates on public genotype data; these are research signals, not independently validated risk guarantees."],
  ["Query-pattern monitoring", "Checks selected query patterns for potential probing. Coverage is limited to the implemented detectors."],
  ["Decision explanations", "Uses built-in templates. No live LLM is configured for this hosted instance."],
  ["Tamper-evident audit log", "Records events in a local hash chain. No independently controlled external audit anchor is configured."],
  ["Human review workflow", "Supports authorized review where enabled; this deployment does not provide institutional SSO or verified organizational identity."],
];

export async function render() {
  const hasIdentity = !!(state.demo || state.who || state.adminKey);
  const healthAtStart = state.health || {};
  // Prefer the liveness snapshot when available. Older hosted API revisions may not
  // include it yet; the strict readiness endpoint returns useful JSON with HTTP 503.
  const readyRequest = healthAtStart.readiness
    ? Promise.resolve({ ok: true, status: 200, data: healthAtStart.readiness })
    : api("/health/ready");
  const [reqs, verify, ev, me, readyResult] = await Promise.all([
    hasIdentity ? api("/requests") : Promise.resolve({ ok: false, status: 401, data: null }),
    api("/audit/verify"),
    state.demo ? api("/eval/results") : Promise.resolve({ ok: false }),
    isSteward() || !hasIdentity ? Promise.resolve({ ok: false }) : api("/me"),
    readyRequest,
  ]);
  const rows = reqs.ok ? reqs.data.requests || [] : [];
  const hl = state.health || {};
  const readiness = hl.readiness ? { ok: true, data: hl.readiness } : readyResult;
  const count = (o) => rows.filter((r) => r.outcome === o).length;
  const latest = rows[0];
  const root = h("div", { class: "stack" });

  // hero: the latest request drawn as a chromosome of stages, or an idle one
  const idle = [["consent", "Consent"], ["risk", "Risk"], ["protect", "Protect"], ["monitor", "Watch"], ["decide", "Decide"], ["explain", "Explain"], ["audit", "Record"]]
    .map(([id, short]) => ({ id, short, state: "idle" }));
  let stages = idle, figureHead = "No requests yet", showingSample = false;
  if (latest) {
    const full = await api("/requests/" + latest.id);
    if (full.ok) {
      stages = workflow(full.data);
      const q = latest.request || {};
      figureHead = `Latest request #${latest.id}: ${q.data_level} data for ${(q.purpose || "").replaceAll("_", " ")}`;
    }
  }
  // with no request yet, play a labelled sample run so the figure is not an empty strip
  if (!latest) { stages = sampleStages(); showingSample = true; figureHead = "A request, stage by stage"; }
  const pipe = pipeline(stages, { play: !!latest || showingSample, caption: true, idle: "Send a request and each stage fills in here, ending at the access decision." });
  const hero = h("section", { class: "card hero" },
    h("div", { class: "hero-copy" },
      h("h1", {}, "Every request for genomic data gets a decision, a reason, and a record."),
      h("p", { class: "lede" }, state.demo
        ? "GenomeGuard demonstrates a research-access workflow with simulated participant permissions, risk checks, output protections and a tamper-evident audit log. Demo records are synthetic and are not real participant consent. Rules decide; advisory components do not grant access."
        : "This hosted research instance evaluates requests against a documented public-dataset policy, applies heuristic risk checks and output protections, and records decisions in a tamper-evident audit log. It uses public 1000 Genomes data; policy provenance is dataset-level, not participant-specific consent. Explanations use built-in templates, and no live LLM is configured."),
      h("div", { class: "hero-actions" },
        tourAvailable() ? h("button", { onclick: startTour }, "Guided walkthrough") : null,
        h("a", { class: tourAvailable() ? "btn ghost" : "btn", href: "#/requests" }, isSteward() ? "Review requests" : "Send a request"),
        state.demo ? h("a", { class: "btn ghost", href: "#/donor" }, "Participant view") : null)),
    h("div", { class: "hero-figure" },
      h("div", { class: "hero-figure-h" },
        h("span", {}, latest ? h("b", {}, figureHead) : [h("b", {}, figureHead), " ", h("span", { class: "sample-flag" }, "Sample data"), " ", h("span", { class: "muted" }, "Your own requests replace this.")]),
        h("button", { class: "ghost", onclick: () => pipe.replay() }, "Replay")),
      pipe));
  root.append(hero);

  if (!readiness.ok || readiness.data?.ready !== true) {
    const checks = readiness.data?.checks || {};
    const failed = Object.entries(checks).filter(([, ok]) => ok !== true)
      .map(([key]) => READINESS_LABELS[key] || key.replaceAll("_", " "));
    root.append(notice("warn",
      h("strong", {}, "Production readiness is not verified."),
      h("p", { class: "muted" }, "This deployment must be treated as a research prototype. A running API or successful page load does not prove durable storage, institutional identity, participant consent, or safe data release."),
      failed.length ? [h("p", { class: "fine" }, "Open release checks:"), h("ul", { class: "checks" }, failed.map((t) => h("li", {}, t)))]
        : h("p", { class: "fine" }, "The readiness endpoint is unavailable, so the system cannot verify its release controls.")));
  }

  const pv = hl.provenance || {};
  if (pv.genotypes) root.append(card("Where the data comes from", "Labelled so nothing is overstated",
    h("dl", { class: "facts" },
      h("dt", {}, "Genotypes"), h("dd", {}, pv.genotypes_label),
      h("dt", {}, "Consent / use-policy basis"), h("dd", {}, pv.consent_label + (
        pv.consent === "simulated"
          ? ". These are simulated records and not valid participant consent."
          : pv.consent === "source_policy"
            ? ". Mapped from public dataset terms; this is not participant-specific consent and has not been independently legally reviewed."
            : ". Imported source records; their legal validity is not independently verified.")),
      h("dt", {}, "Relatives"), h("dd", {}, pv.relatives_label),
      h("dt", {}, "Agents"), h("dd", {}, pv.agents_label + ". They never see genotypes."),
      h("dt", {}, "Storage"), h("dd", {}, pv.encryption))));
  const chain = verify.ok ? verify.data : null;
  const evd = ev.ok ? ev.data : null;
  const diff = evd && evd.differencing ? evd.differencing.accuracy : null;
  root.append(h("div", { class: "readout" },
    kpi("Requests handled", rows.length, rows.length ? `${count("permit") + count("permit_with_transform")} released` : "none yet"),
    kpi("Held for a human", count("escalate"), "waiting for a steward", count("escalate") ? "escalate" : null),
    kpi("Denied", count("deny"), "blocked before any release", count("deny") ? "deny" : null),
    kpi("Audit chain", chain ? (chain.ok ? "Intact" : "Broken") : "n/a",
      chain ? h("span", {}, `${chain.length} entries`, bands(chain.head_hash, { width: 132, height: 12, label: "Banded fingerprint of the audit chain head hash" })) : "",
      chain && !chain.ok ? "deny" : "permit")));

  const SAMPLE_FEED = [["permit_with_transform", "#3 disease research, frequency"], ["escalate", "#2 methods development, frequency"], ["deny", "#1 commercial use, genotype"]];
  const feed = rows.length
    ? h("ul", { class: "feed" }, rows.slice(0, 6).map((r) => h("li", {}, badge(r.outcome), h("a", { href: "#/request/" + r.id }, `#${r.id} ${((r.request || {}).purpose || "").replaceAll("_", " ")}, ${(r.request || {}).data_level}`), h("span", { class: "m" }, when(r.ts)))))
    : h("div", {},
      h("p", { class: "fine", style: "margin:0 0 6px" }, h("span", { class: "sample-flag" }, "Sample data"), state.demo ? "Open Requests and run a demo preset to replace these." : "Submit an authorized request from the Requests page to replace these."),
      h("ul", { class: "feed" }, SAMPLE_FEED.map(([o, t]) => h("li", {}, badge(o), h("span", {}, t), h("span", { class: "m" }, "sample")))));
  const proof = h("dl", { class: "facts" },
    h("dt", {}, "Differencing attack, no defence"), h("dd", {}, diff ? pct(diff.none.mean, 0) + " recovered" : "run make eval"),
    h("dt", {}, "Same attack with GenomeGuard"), h("dd", {}, diff ? pct(diff.ladder_plus_guard.mean, 0) + " (guessing is " + pct(diff.baseline.mean, 0) + ")" : "n/a"),
    h("dt", {}, "Donors / variants"), h("dd", {}, `${hl.donors ?? "n/a"} / ${hl.variants ?? "n/a"} (${pv.genotypes_label || "provenance unknown"})`),
    h("dt", {}, "Smallest cohort released"), h("dd", {}, String(hl.k_min ?? "n/a")));
  root.append(h("div", { class: "grid g-main" },
    card("Recent activity", rows.length ? h("a", { href: "#/requests" }, "All requests") : null, feed),
    state.demo ? card("Does it hold up?", h("a", { href: "#/redteam" }, "Red-team results"), proof) : null));

  const roster = state.demo ? DEMO_ROSTER : RESEARCH_ROSTER;
  root.append(card(state.demo ? "Demo workflow components" : "Research workflow components",
    state.demo ? "Simulated demonstration, not real participant governance" : "Implemented capabilities and their current limits",
    h("div", { class: "grid g2" }, roster.map(([n, t]) => h("div", {}, h("b", {}, n), h("p", { class: "muted", style: "margin:2px 0 0" }, t))))));
  return root;
}
