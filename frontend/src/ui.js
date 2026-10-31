// Small DOM helpers shared by every page. No framework, no build step.
import { state } from "./api.js";
export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
export const svg = (tag, attrs, ...kids) => {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
  for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
};

// A banded "fingerprint" of a hash, drawn like a stained chromosome: one band per byte, shaded in
// five steps the way G-banding is. It is a deterministic rendering of the real value, so any change
// to the hash changes the picture. It never replaces the hash itself, which stays readable beside it.
let fpCount = 0;
const BAND_LEVELS = [0.05, 0.22, 0.42, 0.68, 0.92];
export function bands(hex, { width = 160, height = 14, label } = {}) {
  const clean = String(hex || "").toLowerCase().replace(/[^0-9a-f]/g, "");
  if (clean.length < 16) return null;
  const n = Math.min(32, Math.floor(clean.length / 2));
  const id = "fp" + ++fpCount;
  const w = width / n;
  const root = svg("svg", {
    class: "fp", width, height, viewBox: `0 0 ${width} ${height}`, role: "img", focusable: "false",
    "aria-label": label || "Banded fingerprint of this hash",
  });
  const clip = svg("clipPath", { id }, svg("rect", { width, height, rx: height / 2 }));
  const g = svg("g", { "clip-path": `url(#${id})` });
  for (let i = 0; i < n; i++) {
    const byte = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
    g.append(svg("rect", { x: (i * w).toFixed(2), width: (w + 0.4).toFixed(2), height, fill: "currentColor",
      "fill-opacity": BAND_LEVELS[Math.min(4, Math.floor(byte / 52))] }));
  }
  root.append(clip, g, svg("rect", { x: 0.5, y: 0.5, width: width - 1, height: height - 1, rx: (height - 1) / 2, fill: "none", stroke: "var(--control)" }));
  return root;
}

export const OUTCOME_LABEL = {
  permit: "Approved", permit_with_transform: "Approved with protections",
  deny: "Denied", escalate: "Held for human review",
};
export const badge = (o) => h("span", { class: "badge o-" + o }, OUTCOME_LABEL[o] || o);

const REASONS = {
  withdrawn: "the donor withdrew consent", purpose_unknown: "the purpose is not a recognised research purpose",
  purpose_not_health: "consent covers health research only", disease_mismatch: "consent is limited to a different disease",
  commercial_use_blocked: "consent forbids commercial use", methods_research_blocked: "consent forbids methods-development use",
  aggregate_blocked: "consent forbids aggregate-level use", controls_blocked: "consent forbids use as controls",
  population_restricted: "consent is limited to another population", unknown_consent: "the consent record was malformed",
  below_k_min: "the eligible cohort is below the minimum size", cohort_below_k_min: "the cohort is below the minimum size",
  credential_insufficient: "this account's credential tier does not allow that data level",
  cohort_too_small_for_tier: "the cohort is too small for an anonymous account", no_variants: "no variants matched the request",
  all_variants_below_maf_floor: "every requested variant was too rare to release",
  epsilon_budget_exhausted: "the privacy (epsilon) budget is used up", residual_high_risk: "risk stayed high after every protection",
  differencing_guard: "two queries differ by only a few donors, which could isolate them",
  requester_frozen: "the account is frozen pending human review", requester_throttled: "unusual query patterns need a human check",
  record_level_needs_approval: "record-level access always needs human approval",
  record_rows_never_released: "individual rows are never released automatically",
  rare_variant_few_carriers: "a rare variant has only a few carriers",
};
export const reasonText = (c) => REASONS[c] || String(c).replaceAll("_", " ");
export const stepText = (s) => ({
  drop_rare_variants: "Very rare variants dropped", downgrade_to_count: "Rows replaced by counts",
  generalise_bins: "Values rounded into bins", limit_variants: "Number of variants capped",
  laplace_noise: "Noise added (simplified privacy-budget accounting)", downgrade_to_boolean: "Answer reduced to yes or no",
}[s] || String(s).replaceAll("_", " "));

export const when = (iso) => { try { return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }); } catch { return iso; } };
export const pct = (x, d = 1) => (x == null ? "n/a" : (100 * x).toFixed(d) + "%");

export function row(label, sub, ...content) {
  return h("div", { class: "row" }, h("div", { class: "k" }, h("b", {}, label), sub || ""), h("div", { class: "c" }, content));
}

export function notice(kind, ...kids) { return h("div", { class: "notice " + kind, role: kind === "err" ? "alert" : "status" }, kids); }

// The banner every sample-data view carries. `leave` returns the person to the live view.
export function sampleNotice(message, leave) {
  return h("div", { class: "notice warn sample-bar", role: "status" },
    h("div", {}, h("span", { class: "sample-flag" }, "Sample data"), " ", message),
    leave ? h("button", { class: "ghost", onclick: leave }, "Back to the live view") : null);
}

export function errorText(res) {
  const d = res.data || {};
  if (res.status === 401) return "This view needs a different account. Use the “Acting as” menu to switch.";
  if (res.status === 403 && d.error === "requester_frozen") return "This account is frozen pending human review. A steward can unfreeze it.";
  return d.message || d.error || "Something went wrong (HTTP " + res.status + ").";
}

// risk lane: three bands, a pin marks where the risk sits
export function lane(band) {
  const pos = { low: 16.7, medium: 50, high: 83.3 }[band] ?? 50;
  return h("div", { class: "lane", role: "img", "aria-label": "Risk band: " + band },
    h("span", { class: "low" }, "low"), h("span", { class: "med" }, "medium"), h("span", { class: "high" }, "high"),
    h("i", { class: "pin", style: `left:${pos}%` }));
}

export function copy(text, btn) {
  const done = () => { const t = btn.textContent; btn.textContent = "Copied"; setTimeout(() => (btn.textContent = t), 1400); };
  if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, () => {});
  else done();
}

// minimal responsive SVG line chart. series: [{name, color, points:[[x,y],..], dash?}]
export function lineChart({ series, xLabel, yLabel, xMin, xMax, yMin = 0, yMax = 1, hlines = [], width = 640, height = 260, fmtX = (v) => v, fmtY = (v) => v, xTicks }) {
  const m = { l: 46, r: 14, t: 12, b: 38 };
  const w = width - m.l - m.r, hh = height - m.t - m.b;
  const xs = series.flatMap((s) => s.points.map((p) => p[0]));
  const x0 = xMin ?? Math.min(...xs), x1 = xMax ?? Math.max(...xs, x0 + 1);
  const X = (v) => m.l + ((v - x0) / (x1 - x0 || 1)) * w, Y = (v) => m.t + hh - ((v - yMin) / (yMax - yMin || 1)) * hh;
  const root = svg("svg", { class: "chart", viewBox: `0 0 ${width} ${height}`, role: "img",
    "aria-label": [yLabel, xLabel ? "by " + xLabel : ""].filter(Boolean).join(" ") || "Data chart" });
  for (let i = 0; i <= 4; i++) {
    const v = yMin + ((yMax - yMin) * i) / 4;
    root.append(svg("line", { x1: m.l, x2: m.l + w, y1: Y(v), y2: Y(v), stroke: "var(--rule-2)" }),
      svg("text", { x: m.l - 6, y: Y(v) + 4, "text-anchor": "end" }, fmtY(v)));
  }
  const ticks = xTicks || Array.from({ length: 5 }, (_, i) => x0 + ((x1 - x0) * i) / 4);
  for (const v of ticks) root.append(svg("text", { x: X(v), y: height - 16, "text-anchor": "middle" }, fmtX(v)));
  for (const hl of hlines) root.append(svg("line", { x1: m.l, x2: m.l + w, y1: Y(hl.y), y2: Y(hl.y), stroke: hl.color, "stroke-dasharray": "5 4" }),
    svg("text", { x: m.l + w, y: Y(hl.y) - 4, "text-anchor": "end", style: `fill:${hl.color}` }, hl.label));
  for (const s of series) {
    const d = s.points.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1)).join(" ");
    root.append(svg("path", { d, fill: "none", stroke: s.color, "stroke-width": 2.5, "stroke-dasharray": s.dash || "" }));
    for (const p of s.points) root.append(svg("circle", { cx: X(p[0]), cy: Y(p[1]), r: 3.5, fill: s.color }, svg("title", {}, `${s.name}: ${fmtX(p[0])}, ${fmtY(p[1])}`)));
  }
  root.append(svg("text", { x: m.l + w / 2, y: height - 1, "text-anchor": "middle" }, xLabel || ""),
    svg("text", { x: 12, y: m.t + hh / 2, transform: `rotate(-90 12 ${m.t + hh / 2})`, "text-anchor": "middle" }, yLabel || ""));
  return root;
}

export function legend(items) {
  return h("div", { class: "legend", style: "margin-top:8px" }, items.map(([name, color]) =>
    h("span", {}, h("span", { class: "sw", style: `background:${color}` }), name)));
}

// ---- agentic workflow components ----
const OUT_STATE = { permit: "ok", permit_with_transform: "warn", deny: "bad", escalate: "hold" };
const BAND_STATE = { low: "ok", medium: "warn", high: "bad" };
export const outState = (o) => OUT_STATE[o] || "ok";

// Turn one stored decision into the ordered steps the agents and rules took.
export function workflow(d) {
  const risk = d.risk || {}, cons = risk.consent || {}, before = risk.before || {}, after = risk.assessment || {};
  const tr = d.transform || {}, steps = tr.steps || [], reasons = d.reasons || [];
  const notes = tr.agent_notes || {};
  const frozen = reasons.includes("requester_frozen"), thr = reasons.includes("requester_throttled");
  const consentBad = cons.considered != null && !cons.eligible;
  return [
    { id: "consent", t: "Consent agent", short: "Consent", kind: "agent",
      state: consentBad ? "bad" : "ok",
      says: cons.considered == null
        ? (state.demo ? "Checked simulated participant permissions." : "Checked the dataset-level public-release policy; this is not participant-specific consent.")
        : state.demo
          ? `${cons.eligible} of ${cons.considered} synthetic donors pass simulated permission rules.`
          : state.health?.provenance?.consent === "source_records"
            ? `${cons.eligible} of ${cons.considered} samples pass the configured source-matched consent rules.`
            : `${cons.eligible} of ${cons.considered} samples pass the dataset-level policy mapping; this is not participant-specific consent.`,
      note: notes.consent },
    { id: "risk", t: "Privacy risk agent", short: "Risk", kind: "agent",
      state: BAND_STATE[before.band] || "ok",
      says: before.band ? `Re-identification risk ${before.band}${after.band && after.band !== before.band ? `, ${after.band} after protections` : ""}.` : "No risk score was needed.",
      note: notes.risk || notes.privacy },
    { id: "protect", t: "Protection ladder", short: "Protect", kind: "rule",
      state: steps.length ? "warn" : "ok",
      says: steps.length ? `${steps.length} protection${steps.length > 1 ? "s" : ""} applied: ${steps.map((s) => stepText(s.step).toLowerCase()).join("; ")}.` : "No protection was needed." },
    { id: "monitor", t: "Anomaly monitor", short: "Watch", kind: "agent",
      state: frozen ? "bad" : thr ? "warn" : "ok",
      says: frozen ? "Account frozen after unusual query patterns." : thr ? "Query pattern looked unusual, so a human check was required." : "Query pattern looked normal.",
      note: notes.anomaly },
    { id: "decide", t: "Access decision", short: "Decide", kind: "rule",
      state: outState(d.outcome), says: (OUTCOME_LABEL[d.outcome] || d.outcome) + ". Made by fixed rules, not by a model." },
    { id: "explain", t: "Explainer agent", short: "Explain", kind: "agent", state: "ok",
      says: "Wrote the plain-language reason for the researcher.", note: notes.explainer },
    { id: "audit", t: "Audit agent", short: "Record", kind: "agent", state: "ok",
      says: "Added the decision to the tamper-evident chain." },
  ];
}

// The request drawn as a chromosome: each stage is a band, and the access decision is the
// centromere, the waist the arms hang from. State is shown in colour and in words, never colour alone.
const STATE_WORD = { ok: "Passed", warn: "Caution", bad: "Flagged", hold: "Held", idle: "Waiting" };
export function pipeline(stages, { play = true, caption = false, idle = "" } = {}) {
  const says = caption ? h("p", { class: "pipe-says", "aria-live": "polite" }) : null;
  const els = [];
  const isDecide = (s, i) => s.id === "decide" || (!s.id && stages.length === 7 && i === 4);
  function pick(i) {
    els.forEach((e, k) => e.classList.toggle("picked", k === i));
    const s = stages[i];
    if (!says || !s) return;
    if (!s.says) { says.textContent = idle; return; }
    says.replaceChildren(...[h("b", {}, (s.t || s.short) + ". "), s.says, s.note ? h("span", { class: "note" }, "Agent note: " + s.note) : null].filter(Boolean));
  }
  stages.forEach((s, i) => {
    const state = s.state || "idle";
    const label = caption
      ? h("button", { class: "t", type: "button", onclick: () => pick(i), onfocus: () => pick(i) }, s.short || s.t)
      : h("div", { class: "t" }, s.short || s.t);
    els.push(h("div", { class: "stage " + state + (state === "idle" ? "" : " on") + (isDecide(s, i) ? " cen" : ""), style: `--i:${i}`, role: "listitem" },
      h("div", { class: "seg", "aria-hidden": "true" }),
      h("div", {}, label, h("span", { class: "st" }, STATE_WORD[state] || ""), s.d ? h("div", { class: "d" }, s.d) : null)));
  });
  const strip = h("div", { class: "pipe" + (play ? " play" : ""), role: "list" }, els);
  const el = says ? h("div", {}, strip, says) : strip;
  const decideAt = stages.findIndex(isDecide);
  if (caption) pick(decideAt >= 0 ? decideAt : 0);
  el.replay = () => { strip.classList.remove("play"); void strip.offsetWidth; strip.classList.add("play"); };
  return el;
}

export function timeline(stages) {
  return h("ol", { class: "tl" }, stages.map((s, i) =>
    h("li", { class: s.state || "ok", style: `--i:${i}` },
      h("span", { class: "dot", "aria-hidden": "true" }, String(i + 1)),
      h("div", { class: "who2" }, s.t, h("span", { class: "mode" }, s.kind === "agent" ? "Advises" : "Fixed rule")),
      h("p", { class: "says" }, s.says),
      s.note ? h("div", { class: "chips" }, h("span", { class: "pill agentnote" }, "Agent note: " + s.note)) : null)));
}

export function card(title, aside, ...kids) {
  return h("section", { class: "card" }, title ? h("div", { class: "card-h" }, h("h2", { class: "card-title" }, title), aside ? h("span", {}, aside) : null) : null, kids);
}

export function kpi(label, value, sub, tone) {
  return h("div", { class: "kpi" + (tone ? " o-" + tone : "") }, h("div", { class: "l" }, label), h("div", { class: "v" }, String(value)), sub ? h("div", { class: "s" }, sub) : null);
}
