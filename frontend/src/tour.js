// Guided tour: walks the scripted demo, and its two action steps call the real API (they send the
// researcher's request and run the probing account for real). Nothing here is canned: every
// outcome shown comes from the running system. State lives in this module, so the card survives
// page changes while the tour moves between pages.
import { api, stewardApi, state, setWho } from "./api.js";
import { h, OUTCOME_LABEL } from "./ui.js";

const RESEARCHER = "demo-researcher";
const ATTACKER = "demo-attacker";
const STUDY = { purpose: "disease_research", disease: "diabetes", data_level: "frequency", is_commercial: false, cohort_filter: {}, variant_filter: { min_maf: 0.1, limit: 20, include_planted: 2 } };
const CELL = { cohort_id: "DIABETES-STUDY", population: "POP_A" };
const DISEASES = ["diabetes", "cancer", "diabetes", "cardiovascular", "cancer", "diabetes"];

const ctx = { study: null, held: null };
let i = 0, el = null, noteEl = null;

async function latestId() {
  const r = await stewardApi("/requests");
  const rows = (r.ok && r.data.requests) || [];
  return rows.length ? rows[0].id : null;
}
async function heldId() {
  const r = await stewardApi("/requests");
  const rows = (r.ok && r.data.requests) || [];
  const x = rows.find((q) => q.status === "held" && q.needs_human);
  return x ? x.id : null;
}

const STEPS = [
  { title: "What this is", hash: "#/overview",
    text: "Genomic data can expose a person's relatives, who never agreed to anything. GenomeGuard sits in front of the data and decides who can see what, explains why, and keeps a record nobody can quietly edit. Agents advise. Fixed rules decide. A person signs off on anything risky." },
  { title: "A researcher asks for diabetes statistics", hash: () => (ctx.study ? "#/request/" + ctx.study : "#/requests"),
    text: "A registered researcher wants allele frequencies for a diabetes study, including two very rare variants. The system will check consent, score the risk, add protections and record everything.",
    action: { label: "Send the researcher's request", run: async () => {
      const r = await api("/requests", { method: "POST", key: RESEARCHER, body: STUDY });
      if (!r.ok) return { note: (r.data && (r.data.message || r.data.error)) || "The request could not be sent.", fail: true };
      ctx.study = r.data.id;
      const c = (r.data.risk || {}).consent || {};
      return { hash: "#/request/" + r.data.id, note: `${OUTCOME_LABEL[r.data.outcome] || r.data.outcome}. ${c.considered ? `${c.eligible} of ${c.considered} donors had consent that fits. ` : ""}Look at the protections applied and the explanation.` };
    } } },
  { title: "Relatives who never joined the study", hash: async () => "#/family/" + (ctx.study || (await latestId()) || 1),
    text: "Rare variants run in families. Each glowing dot is a relative of someone in the request who would be exposed if those variants were released. This is a model built from expected family sharing, and it is labelled that way." },
  { title: "A second account starts probing", hash: "#/anomalies",
    text: "This account sends many near-identical, narrowing queries, the classic way to isolate one person. Watch the monitor, the differencing guard and the freeze.",
    action: { label: "Run the probing account", run: async () => {
      let n = 0, frozen = false;
      for (let k = 0; k < 14; k++) {
        const r = await api("/requests", { method: "POST", key: ATTACKER, body: { purpose: "disease_research", disease: DISEASES[k % 6], is_commercial: k % 2 === 1, data_level: "frequency", cohort_filter: CELL, variant_filter: { min_maf: 0.1, limit: 20 + (k % 3) } } });
        if (r.status === 403) { frozen = true; break; }
        if (!r.ok) return { note: (r.data && r.data.message) || "A query failed.", fail: true };
        n++;
      }
      window.dispatchEvent(new Event("gg:refresh-who"));
      return { hash: "#/anomalies", note: frozen ? (n ? `The account was frozen after ${n} accepted queries. A held request is now waiting for a human.` : "That account was already frozen from an earlier run. A steward can unfreeze it on this page.") : `${n} queries were sent and the monitor has not frozen the account yet.` };
    } } },
  { title: "The steward copilot investigates", hash: async () => { ctx.held = await heldId(); return ctx.held ? "#/request/" + ctx.held : "#/requests"; },
    text: "On the held request, an agent chooses which evidence to gather (consent, risk, relatives, history, audit) and recommends. It can read but cannot approve, deny or freeze anything. Without an API key a built-in planner does the same job, so it never fails on stage." },
  { title: "Proof nothing was edited", hash: "#/audit",
    text: "Every step so far was added to a hash chain. Change any past entry and the chain breaks at exactly that entry. Press Verify now. Copy the head hash somewhere outside the system: that is what makes a full rewrite detectable. (The tamper button is demo-only and cannot be undone without a fresh database.)" },
  { title: "Measured, not claimed", hash: "#/redteam",
    text: "We attack our own system and report what happens, including where it fails and what the evaluation does not show. Every number comes from one command with fixed seeds." },
  { title: "The patient's side", hash: "#/donor", last: true,
    text: "Donors see what they agreed to, which statistics included them, and can change or withdraw consent. They can also download their consent as a standard FHIR record. This consent is simulated, because no real person consented to this system." },
];

function close() {
  if (el) el.remove();
  el = null;
  document.body.classList.remove("tour-open");
  document.removeEventListener("keydown", onKey);
}
function onKey(e) { if (e.key === "Escape") close(); }

async function go(step) {
  const hash = typeof step.hash === "function" ? await step.hash() : step.hash;
  if (hash && location.hash !== hash) location.hash = hash;
}

async function show(n) {
  i = Math.max(0, Math.min(STEPS.length - 1, n));
  const s = STEPS[i];
  if (!el) {
    el = h("section", { class: "tour", role: "dialog", "aria-label": "Guided tour", "aria-live": "polite" });
    document.body.append(el);
    document.body.classList.add("tour-open");
    document.addEventListener("keydown", onKey);
  }
  const title = h("h2", { tabindex: "-1" }, s.title);
  noteEl = h("p", { class: "tour-note", hidden: true });
  const act = s.action ? h("button", { onclick: () => runAction(s, act) }, s.action.label) : null;
  const nextBtn = h("button", { class: s.action ? "ghost" : "", onclick: () => (s.last ? close() : show(i + 1)) }, s.last ? "Finish" : "Next");
  el.replaceChildren(
    h("div", { class: "tour-top" }, h("span", { class: "tour-step" }, `Step ${i + 1} of ${STEPS.length}`),
      h("button", { class: "ghost tour-x", "aria-label": "Close the tour", onclick: close }, "Close")),
    h("div", { class: "tour-bar", role: "img", "aria-label": `Progress: step ${i + 1} of ${STEPS.length}` }, h("i", { style: `width:${((i + 1) / STEPS.length) * 100}%` })),
    title, h("p", {}, s.text), noteEl,
    h("div", { class: "tour-btns" }, i > 0 ? h("button", { class: "ghost", onclick: () => show(i - 1) }, "Back") : null, act, nextBtn));
  await go(s);
  title.focus({ preventScroll: true });
}

async function runAction(s, btn) {
  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = "Running…";
  const r = await s.action.run();
  btn.textContent = old;
  btn.disabled = false;
  noteEl.hidden = false;
  noteEl.textContent = r.note;
  noteEl.className = "tour-note " + (r.fail ? "bad" : "ok");
  if (r.hash) {
    // same page: the router only re-renders on a hash change, so ask it to refresh
    if (location.hash !== r.hash) location.hash = r.hash;
    else window.dispatchEvent(new HashChangeEvent("hashchange"));
  }
}

export const tourAvailable = () => !!state.demo;

export function startTour() {
  if (!state.demo) return; // demo accounts are only published in demo mode
  setWho("steward");
  window.dispatchEvent(new Event("gg:refresh-who"));
  ctx.study = null;
  ctx.held = null;
  show(0);
}

