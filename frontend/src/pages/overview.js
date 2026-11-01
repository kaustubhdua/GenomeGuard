import { api, state, isSteward } from "../api.js";
import { h, svg, badge, pipeline, workflow, when, pct } from "../ui.js";
import { startTour, tourAvailable } from "../tour.js";

const READINESS_LABELS = {
  demo_mode_disabled: "Demonstration mode must be disabled",
  real_genotype_provenance: "Genotype provenance must be verified",
  participant_consent_records_verified: "Participant consent evidence must be verified",
  destructive_tamper_demo_disabled: "Destructive controls must be disabled",
  postgres_storage_configured: "Durable PostgreSQL storage must be configured",
  durable_storage_verified: "Persistence and recovery must be verified",
  external_audit_anchor_verified: "Independent audit anchoring must be verified",
  institutional_identity_provider_verified: "Institutional identity must be verified",
};
const fmt = (n) => Number.isFinite(Number(n)) ? Number(n).toLocaleString("en-US") : "—";
const fact = (label, value, note = "") => h("div", { class: "gg-fact" },
  h("span", { class: "gg-fact-label" }, label), h("strong", {}, value ?? "Not reported"),
  note ? h("small", {}, note) : null);

function helixGraphic() {
  const stage = h("div", { class: "dna-stage", role: "img", "aria-label": "Interactive DNA double helix illustration. Drag horizontally to turn the helix." });
  const art = svg("svg", { viewBox: "0 0 440 300", class: "dna-art", role: "presentation", "aria-hidden": "true" });
  const strands = svg("g", {});
  art.append(strands);
  const draw = (phase = 0) => {
    strands.replaceChildren();
    const left = [], right = [];
    for (let i = 0; i <= 24; i++) {
      const y = 24 + i * 10.5, angle = i * Math.PI / 6 + phase;
      left.push([220 + Math.sin(angle) * 66, y]);
      right.push([220 - Math.sin(angle) * 66, y]);
    }
    const pathFor = (points) => points.map(([x,y],i) => (i ? "L " : "M ") + x.toFixed(1) + " " + y.toFixed(1)).join(" ");
    strands.append(
      svg("path", { d: pathFor(left), fill: "none", stroke: "#72e6ad", "stroke-width": 4, "stroke-linecap": "round", opacity: .9 }),
      svg("path", { d: pathFor(right), fill: "none", stroke: "#a99aff", "stroke-width": 4, "stroke-linecap": "round", opacity: .9 })
    );
    for (let i = 1; i < 24; i++) {
      const [x1,y] = left[i], [x2] = right[i];
      const front = Math.cos(i * Math.PI / 6 + phase) > 0;
      strands.append(
        svg("line", { x1, y1:y, x2, y2:y, stroke: front ? "#b8c9d4" : "#718d91", "stroke-width": front ? 2.8 : 1.7, "stroke-linecap":"round", opacity: front ? .85 : .38 }),
        svg("circle", { cx:x1, cy:y, r:front?4.1:3.2, fill:"#72e6ad" }),
        svg("circle", { cx:x2, cy:y, r:front?4.1:3.2, fill:"#a99aff" })
      );
    }
  };
  draw();
  stage.append(art, h("span", { class: "dna-drag-hint" }, "↔ DRAG TO TURN"));
  let dragging = false, lastX = 0, phase = 0;
  stage.addEventListener("pointerdown", (e) => {
    dragging = true; lastX = e.clientX; stage.classList.add("is-dragging");
    stage.setPointerCapture(e.pointerId);
  });
  stage.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    phase += (e.clientX - lastX) * .012;
    lastX = e.clientX;
    draw(phase);
  });
  const release = () => { dragging = false; stage.classList.remove("is-dragging"); };
  stage.addEventListener("pointerup", release);
  stage.addEventListener("pointercancel", release);
  return stage;
}
function metric(label, value, note, tone = "") {
  return h("article", { class: "gg-metric " + tone },
    h("div", { class: "gg-metric-top" }, h("span", {}, label), h("i", { "aria-hidden": "true" })),
    h("strong", {}, value), h("p", {}, note));
}
function workflowList() {
  const items = [
    ["01", "Policy evaluation", "Dataset use terms and request purpose are checked."],
    ["02", "Cohort eligibility", "Minimum cohort thresholds are enforced before release."],
    ["03", "Disclosure-risk assessment", "Heuristic risk signals are evaluated against the request."],
    ["04", "Output protection", "Aggregation and transformation controls are applied where required."],
    ["05", "Query monitoring", "Potentially probing request patterns are monitored."],
    ["06", "Human review", "Escalated decisions remain subject to authorized review."],
    ["07", "Audit record", "The decision is written to the tamper-evident event chain."],
  ];
  return h("ol", { class: "gg-workflow-list" }, items.map(([n, title, desc]) =>
    h("li", {}, h("span", { class: "gg-step-no" }, n), h("div", {},
      h("strong", {}, title), h("p", {}, desc)))));
}

export async function render() {
  const hasIdentity = !!(state.demo || state.who || state.adminKey), hl = state.health || {};
  // Keep the overview responsive when the API or audit store is cold: non-critical
  // panels get a short budget and never hold the first paint hostage.
  const quick = (promise, fallback, ms = 650) => Promise.race([
    promise,
    new Promise((resolve) => setTimeout(() => resolve(fallback), ms)),
  ]);
  const [reqs, verify, ev, readyResult] = await Promise.all([
    hasIdentity ? quick(api("/requests"), { ok: false, data: null }) : Promise.resolve({ ok: false, status: 401, data: null }),
    quick(api("/audit/verify"), { ok: false, data: null }),
    state.demo ? quick(api("/eval/results"), { ok: false }) : Promise.resolve({ ok: false }),
    hl.readiness ? Promise.resolve({ ok: true, status: 200, data: hl.readiness }) : quick(api("/health/ready"), { ok: false, data: null }),
  ]);
  const rows = reqs.ok ? (reqs.data.requests || []) : [];
  const readiness = hl.readiness ? { ok: true, data: hl.readiness } : readyResult;
  const chain = verify.ok ? verify.data : null;
  const latest = rows[0], pv = hl.provenance || {};
  const diff = ev.ok ? ev.data?.differencing?.accuracy : null;
  const root = h("div", { class: "stack gg-overview" });

  root.append(h("section", { class: "gg-command" },
    h("div", { class: "gg-command-copy" },
      h("div", { class: "gg-eyebrow" }, h("span", { class: hl.status === "ok" ? "gg-live-dot" : "gg-live-dot gg-live-dot-off" }), state.demo ? "DEMONSTRATION ENVIRONMENT / SYNTHETIC COHORT" : "GENOMIC DATA GOVERNANCE / RESEARCH WORKSPACE"),
      h("h1", {}, "Research access, governed with evidence."),
      h("p", {}, "A unified workspace for genomic dataset provenance, privacy-aware access decisions and accountable research operations."),
      h("div", { class: "gg-command-actions" },
        h("a", { class: "gg-primary-action", href: "#/requests" }, isSteward() ? "Open review queue" : "Create access request"),
        tourAvailable() ? h("button", { class: "gg-secondary-action", "aria-label": "Explore platform — Guided walkthrough", onclick: startTour }, "Explore platform") : null)),
    h("div", { class: "gg-command-art" }, helixGraphic(),
      h("div", { class: "gg-art-label" }, h("span", {}, "REFERENCE BUILD"),
        h("strong", {}, pv.genotypes_label || "Public research cohort")))));

  root.append(h("section", { class: "gg-metrics", "aria-label": "Research environment metrics" },
    metric("Individuals in cohort", fmt(hl.donors), pv.genotypes_label || "Reported by research API", "metric-green"),
    metric("Variant loci", fmt(hl.variants), "Loaded research variant set", "metric-blue"),
    metric("Minimum cohort threshold", fmt(hl.k_min), "Required before eligible aggregate release", "metric-violet"),
    metric("Audit chain", chain ? (chain.ok ? "Verified" : "Integrity issue") : "Unavailable",
      chain ? (chain.length ? fmt(chain.length) + " recorded events" : "No access events recorded yet") : "Integrity status unavailable", chain?.ok ? "metric-green" : "metric-amber")));

  root.append(h("section", { class: "gg-source-strip" },
    h("div", { class: "gg-source-heading" }, h("span", { class: "gg-section-index" }, "01"),
      h("div", {}, h("strong", {}, "Research dataset"), h("small", {}, "Live service-reported provenance"))),
    fact("Genotype source", pv.genotypes_label || "Not reported"),
    fact("Use-policy basis", pv.consent_label || "Not reported"),
    fact("Storage", hl.storage_backend || "Not reported"),
    fact("Release posture", readiness.data?.ready === true ? "Readiness checks passed" : "Research prototype")));

  const recent = h("section", { class: "gg-panel gg-activity" },
    h("div", { class: "gg-panel-head" },
      h("div", {}, h("span", { class: "gg-section-index" }, "02"), h("h2", {}, "Access activity")),
      h("a", { href: "#/requests" }, "View request register →")),
    rows.length
      ? h("div", { class: "gg-activity-list" }, rows.slice(0, 5).map((r) =>
          h("a", { class: "gg-activity-row", href: "#/request/" + r.id },
            h("span", { class: "gg-activity-id" }, "#" + r.id),
            h("span", { class: "gg-activity-description" },
              h("strong", {}, ((r.request || {}).purpose || "Research request").replaceAll("_", " ")),
              h("small", {}, ((r.request || {}).data_level || "Unspecified") + " · " + when(r.ts))),
            badge(r.outcome), h("span", { class: "gg-row-arrow" }, "↗"))))
      : h("div", { class: "gg-empty-activity" },
          h("div", { class: "gg-empty-icon" }, "↗"),
          h("div", {}, h("strong", {}, hasIdentity ? "No access requests recorded" : "Connect an authorized research identity"),
            h("p", {}, hasIdentity ? "New submissions and their review outcomes will appear here." :
              "Request-level activity is restricted to authenticated researchers and data stewards.")),
          h("a", { href: "#/requests" }, hasIdentity ? "Start a request →" : "Open request workspace →")));

  const governance = h("section", { class: "gg-panel gg-governance" },
    h("div", { class: "gg-panel-head" },
      h("div", {}, h("span", { class: "gg-section-index" }, "03"), h("h2", {}, "Governance controls")),
      h("a", { href: "#/audit" }, "Audit log →")),
    h("div", { class: "gg-governance-grid" },
      fact("Dataset provenance", pv.genotypes_label || "Not reported"),
      fact("Policy mapping", pv.consent_label || "Not reported"),
      fact("Audit integrity", chain ? (chain.ok ? "Verified" : "Integrity issue") : "Unavailable", chain ? (chain.length ? fmt(chain.length) + " entries checked" : "No access events recorded yet") : "No verification response"),
      fact("Model assistance", hl.agents_use_llm ? "Configured" : "Template-based explanations", "Advisory only; rules govern release"),
      fact("Minimum release cohort", fmt(hl.k_min), "Applied by policy engine"),
      fact("Identity assurance", readiness.data?.checks?.institutional_identity_provider_verified === true ? "Verified" : "Not verified", "Institutional identity provider")));
  root.append(h("div", { class: "gg-two-column" }, recent, governance));

  const flowPanel = h("section", { class: "gg-panel gg-workflow" },
    h("div", { class: "gg-panel-head" },
      h("div", {}, h("span", { class: "gg-section-index" }, "04"), h("h2", {}, "Decision architecture")),
      h("span", { class: "gg-panel-meta" }, "Seven-stage control path")),
    workflowList());
  // Detailed decision traces are loaded on their own route, never during overview paint.
  root.append(flowPanel);
  if (state.demo) root.append(h("section", { class: "gg-panel gg-evidence" },
    h("div", { class: "gg-panel-head" },
      h("div", {}, h("span", { class: "gg-section-index" }, "06"), h("h2", {}, "Privacy evaluation evidence")),
      h("a", { href: "#/redteam" }, "Evaluation details →")),
    h("div", { class: "gg-evidence-grid" },
      fact("Attack recovery without controls", diff ? pct(diff.none?.mean, 0) : "Unavailable",
        diff ? "Evaluation result" : "Evaluation results are not currently available"),
      fact("With GenomeGuard protections", diff ? pct(diff.ladder_plus_guard?.mean, 0) : "Unavailable",
        diff ? "Evaluation result" : "Evaluation results are not currently available"),
      fact("Baseline guessing", diff ? pct(diff.baseline?.mean, 0) : "Unavailable",
        diff ? "Evaluation result" : "Evaluation results are not currently available"))));
  return root;
}
