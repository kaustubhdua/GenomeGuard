import { api, state, isSteward, setWho } from "../api.js";
import { h, row, badge, when, notice, errorText, reasonText } from "../ui.js";

const PURPOSES = ["disease_research", "health_research", "biomedical_research", "general_research", "population_genetics", "ancestry_research", "methods_development", "education"];
const DISEASES = ["", "diabetes", "cancer", "cardiovascular", "asthma"];
const LEVELS = ["frequency", "count", "boolean", "record"];

const PRESETS = [
  { name: "Diabetes frequency study", why: "A normal study: some donors are excluded by consent, rare variants are dropped.",
    body: { purpose: "disease_research", disease: "diabetes", data_level: "frequency", is_commercial: false, cohort_filter: {}, variant_filter: { min_maf: 0.1, limit: 20, include_planted: 2 } } },
  { name: "Same study, commercial use", why: "Donors whose consent forbids commercial use drop out.",
    body: { purpose: "disease_research", disease: "diabetes", data_level: "frequency", is_commercial: true, cohort_filter: {}, variant_filter: { min_maf: 0.1, limit: 20 } } },
  { name: "Narrow cohort", why: "One cohort and one population: small, so closer to the minimum size.",
    body: { purpose: "disease_research", disease: "diabetes", data_level: "frequency", is_commercial: false, cohort_filter: { cohort_id: "DIABETES-STUDY", population: "POP_A" }, variant_filter: { min_maf: 0.1, limit: 20 } } },
  { name: "Individual rows (record level)", why: "Registered accounts are refused; controlled access always needs a human.",
    body: { purpose: "disease_research", disease: "diabetes", data_level: "record", is_commercial: false, cohort_filter: {}, variant_filter: { min_maf: 0.1, limit: 10 } } },
];

function probeSequence() {
  const cell = { cohort_id: "DIABETES-STUDY", population: "POP_A" };
  const dis = ["diabetes", "cancer", "diabetes", "cardiovascular", "cancer", "diabetes"];
  return dis.map((d, i) => ({ purpose: "disease_research", disease: d, is_commercial: i % 2 === 1, data_level: "frequency", cohort_filter: cell, variant_filter: { min_maf: 0.1, limit: 20 + (i % 3) } }));
}

export async function render() {
  const root = h("div", {});
  root.dataset.title = "Requests";
  root.append(h("h1", {}, "Data requests"),
    h("p", { class: "lede" }, isSteward()
      ? "Every request from every account. Open one to review it."
      : "Ask for allele frequencies. GenomeGuard checks donor consent, scores re-identification risk, applies protections and records everything in the audit log."));
  const out = h("div", {});
  if (!isSteward()) root.append(formSection(out));
  root.append(out);
  const list = await api("/requests");
  out.append(listSection(list));
  return root;
}

function listSection(res) {
  if (!res.ok) return notice("err", errorText(res));
  const rows = res.data.requests || [];
  if (!rows.length) return h("div", { class: "empty" }, state.demo
    ? "No requests yet. Run a demo preset above to see a decision."
    : "No requests yet. Submit an authorized request above to evaluate the current cohort policy.");
  const t = h("div", { class: "tablewrap" }, h("table", {},
    h("thead", {}, h("tr", {}, h("th", {}, "#"), h("th", {}, "When"), isSteward() ? h("th", {}, "Account") : null, h("th", {}, "Request"), h("th", {}, "Outcome"))),
    h("tbody", {}, rows.map((r) => {
      const a = h("a", { href: "#/request/" + r.id }, "#" + r.id);
      const q = r.request || {};
      const tr = h("tr", { class: "link", onclick: () => (location.hash = "#/request/" + r.id) },
        h("td", {}, a), h("td", {}, when(r.ts)), isSteward() ? h("td", {}, r.requester) : null,
        h("td", {}, `${(q.purpose || "").replaceAll("_", " ")}${q.disease ? ", " + q.disease : ""}, ${q.data_level}`),
        h("td", {}, badge(r.outcome), r.status === "held" ? h("span", { class: "pill warn", style: "margin-left:8px" }, "waiting for review") : null));
      return tr;
    }))));
  return h("section", { class: "card request-history", "aria-labelledby": "request-history-title" },
    h("div", { class: "card-h" },
      h("h2", { id: "request-history-title" }, "Request history"),
      h("span", {}, `${rows.length} request${rows.length > 1 ? "s" : ""}`)),
    t);
}

function formSection(out) {
  const st = state.demo ? { ...PRESETS[0].body } : {
    purpose: "general_research", disease: null, data_level: "frequency", is_commercial: false,
    cohort_filter: {}, variant_filter: { min_maf: 0.01, limit: 20 },
  };
  const f = {};
  const sel = (id, label, opts, val) => {
    f[id] = h("select", { id, onchange: sync }, opts.map((o) => h("option", { value: o }, o === "" ? "any / none" : o.replaceAll("_", " "))));
    f[id].value = val;
    return h("label", { class: "f", for: id }, label, f[id]);
  };
  const inp = (id, label, val, type = "text") => { f[id] = h("input", { id, type, value: val, onchange: sync }); return h("label", { class: "f", for: id }, label, f[id]); };
  const preview = h("div", { "aria-live": "polite" });
  const msg = h("div", {});
  const form = h("div", { class: "form" },
    sel("purpose", "Purpose", PURPOSES, st.purpose),
    state.demo ? sel("disease", "Disease area", DISEASES, st.disease || "")
      : inp("disease", "Disease identifier (required only for disease-specific consent)", st.disease || ""),
    sel("level", "Data level", LEVELS, st.data_level), inp("pop", "Population filter", ""), inp("coh", "Cohort filter", ""),
    inp("maf", "Minimum allele frequency", st.variant_filter.min_maf, "number"), inp("lim", "Number of variants", st.variant_filter.limit, "number"),
    state.demo ? inp("pl", "Rare demo variants to include", st.variant_filter.include_planted || 0, "number") : null,
    h("label", { class: "f chk" }, (f.com = h("input", { type: "checkbox", id: "com", onchange: sync })), "Commercial use"));

  function body() {
    const cf = {};
    if (f.pop.value.trim()) cf.population = f.pop.value.trim();
    if (f.coh.value.trim()) cf.cohort_id = f.coh.value.trim();
    return { purpose: f.purpose.value, disease: f.disease.value || null, data_level: f.level.value, is_commercial: f.com.checked, cohort_filter: cf,
      variant_filter: { min_maf: Number(f.maf.value), limit: Number(f.lim.value), ...(state.demo ? { include_planted: Number(f.pl.value) } : {}) } };
  }
  function load(b) {
    f.purpose.value = b.purpose; f.disease.value = b.disease || ""; f.level.value = b.data_level; f.com.checked = !!b.is_commercial;
    f.pop.value = b.cohort_filter.population || ""; f.coh.value = b.cohort_filter.cohort_id || "";
    f.maf.value = b.variant_filter.min_maf; f.lim.value = b.variant_filter.limit;
    if (f.pl) f.pl.value = b.variant_filter.include_planted || 0;
    sync();
  }
  let timer;
  function sync() { clearTimeout(timer); timer = setTimeout(refreshPreview, 200); }
  async function refreshPreview() {
    const b = body();
    const q = new URLSearchParams({ purpose: b.purpose, commercial: String(b.is_commercial), data_level: b.data_level });
    if (b.disease) q.set("disease", b.disease);
    if (b.cohort_filter.population) q.set("population", b.cohort_filter.population);
    const r = await api("/consent/summary?" + q);
    if (!r.ok) { preview.replaceChildren(notice("warn", errorText(r))); return; }
    const c = r.data, ex = c.excluded_by_reason || {};
    const total = c.considered || 1, out_ = Object.values(ex).reduce((a, b2) => a + b2, 0);
    preview.replaceChildren(
      h("div", { class: "bar", role: "img", "aria-label": `${c.eligible} of ${c.considered} donors eligible` }, h("i", { class: "seg-ok", style: `width:${(100 * c.eligible) / total}%` }), h("i", { class: "seg-ex", style: `width:${(100 * out_) / total}%` })),
      h("div", { class: "legend" }, h("span", {}, h("b", {}, c.eligible), ` of ${c.considered} donors have consent that fits this request`),
        Object.entries(ex).sort((a, b2) => b2[1] - a[1]).map(([k, v]) => h("span", {}, `${v} excluded: ${reasonText(k)}`))));
  }
  async function submit(b, btn) {
    btn.disabled = true; msg.replaceChildren();
    const r = await api("/requests", { method: "POST", body: b });
    btn.disabled = false;
    if (r.ok) { location.hash = "#/request/" + r.data.id; return; }
    msg.replaceChildren(notice("err", errorText(r)));
    if (r.data && r.data.request_id) msg.append(h("a", { href: "#/request/" + r.data.request_id }, "See the recorded refusal"));
  }
  async function probe(btn) {
    btn.disabled = true; msg.replaceChildren(notice("ok", "Sending six narrow, slightly different queries from this account…"));
    const lines = [];
    for (const [i, q] of probeSequence().entries()) {
      const r = await api("/requests", { method: "POST", body: q });
      const d = r.data || {};
      lines.push(h("li", {}, `Query ${i + 1}: `, r.ok ? [badge(d.outcome), d.reasons && d.reasons.length ? " " + d.reasons.map(reasonText).join("; ") : ""] : h("span", { class: "pill bad" }, errorText(r))));
      msg.replaceChildren(notice("ok", h("ul", { class: "plain", style: "list-style:none;padding:0" }, lines)));
      if (r.status === 403) break;
    }
    btn.disabled = false;
    window.dispatchEvent(new Event("gg:refresh-who"));
    out.replaceChildren(listSection(await api("/requests")));
  }

  const submitBtn = h("button", { onclick: (e) => submit(body(), e.target) }, "Send request");
  const probeBtn = state.demo ? h("button", { class: "ghost", onclick: (e) => probe(e.target), title: "Demo: what a probing account looks like to the monitor" }, "Run probe sequence") : null;
  const reqs = state.demo ? state.demo.requesters : [];
  const att = reqs.find((r) => r.name === "Probe Account");
  const wrap = h("div", { class: "ledger" },
    row("New request", state.demo ? "Fill in or pick a preset" : "Submit a query against the imported cohort and current consent rules",
      state.demo ? h("div", { class: "presets" }, PRESETS.map((p) => h("button", { class: "ghost", title: p.why, onclick: () => load(p.body) }, p.name))) : null, form,
      h("div", { style: "margin-top:12px;display:flex;gap:10px;flex-wrap:wrap" }, submitBtn, probeBtn,
        att && state.who !== att.api_key ? h("button", { class: "ghost", onclick: () => { setWho(att.api_key); location.reload(); } }, "Switch to the probe account") : null), msg),
    row("Consent check", "Updates as you type", preview));
  load(state.demo ? PRESETS[0].body : st);
  return wrap;
}
