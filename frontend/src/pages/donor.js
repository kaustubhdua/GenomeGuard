import { state, donorApi } from "../api.js";
import { h, notice, when, errorText } from "../ui.js";

const USE = { gru: "any research", hmb: "health, medical or biomedical research", ds: "research on one named disease" };
const MOD = { ncu: "no commercial use", npu: "no for-profit use", nmds: "no methods development", nagr: "no aggregate analysis", nctrl: "not as a control group" };
const CHIPS = [["who_used", "Who used my data?"], ["what_allowed", "What did I allow?"], ["how_withdraw", "How do I withdraw?"], ["relatives", "What about my relatives?"], ["security", "Is it secure?"]];
const plain = (s) => String(s || "").replaceAll("_", " ");

export async function render() {
  const root = h("div", { class: "donor" });
  if (!state.donors.length) return h("div", { class: "empty" }, "Simulated participant records are unavailable because the sample-data mode is disabled.");
  const body = h("div", { class: "stack" });
  const pick = h("select", { id: "persona", "aria-label": "Simulated participant", onchange: (e) => { state.donor = state.donors.find((d) => String(d.id) === e.target.value); load(); } },
    state.donors.map((d) => h("option", { value: d.id }, d.label)));
  pick.value = state.donor.id;
  root.append(h("h1", {}, "Your data, in your hands"),
    h("p", { class: "lede" }, "This view illustrates participant consent controls. The records are simulated; changes affect only this local demonstration and are not real-world consent actions."),
    h("label", { class: "f", for: "persona", style: "font-family:var(--sans)" }, "Simulated participant (not a real consent record)", pick), body);
  const flash = h("div", { "aria-live": "polite" });

  async function load() {
    body.replaceChildren(h("div", { class: "skeleton", style: "height:120px" }));
    const res = await donorApi("/donor/" + state.donor.id);
    if (!res.ok) { body.replaceChildren(notice("err", errorText(res))); return; }
    draw(res.data);
  }

  function draw(p) {
    const c = p.consent, mods = (c.modifiers || []).map((m) => MOD[m.toLowerCase()] || m);
    const use = (USE[(c.use || "").toLowerCase()] || c.use) + (c.disease ? `: ${c.disease}` : "");
    const answer = h("div", {});
    const ask = async (intent, btn) => {
      document.querySelectorAll(".donor .chipbtn").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      const r = await donorApi(`/donor/${p.id}/ask`, { method: "POST", body: { intent } });
      answer.replaceChildren(r.ok ? h("div", { class: "answer", role: "status" }, h("div", {}, r.data.answer), h("span", { class: "by" }, "Written by the consent concierge from fixed facts. It never sees your genome and cannot be asked free-form questions.")) : notice("err", errorText(r)));
    };
    const confirm = h("div", {});
    const act = async (path) => {
      const r = await donorApi(`/donor/${p.id}/${path}`, { method: "POST", body: {} });
      if (r.ok) { flash.replaceChildren(notice("ok", path === "withdraw" ? "Consent withdrawn. No future request will include you." : "Consent restored.")); draw(r.data); } else flash.replaceChildren(notice("err", errorText(r)));
    };
    const askConfirm = () => confirm.replaceChildren(h("div", { class: "confirm" },
      h("span", {}, p.withdrawn ? "Allow future research use again?" : "Withdraw from all future requests?"),
      h("button", { class: p.withdrawn ? "" : "danger", onclick: () => act(p.withdrawn ? "restore" : "withdraw") }, p.withdrawn ? "Yes, restore" : "Yes, withdraw"),
      h("button", { class: "ghost", onclick: () => confirm.replaceChildren() }, "Cancel")));

    const form = consentForm(p, (r) => { if (r.ok) { flash.replaceChildren(notice("ok", "Saved. Your new choices apply to future requests.")); draw(r.data); } else flash.replaceChildren(notice("err", errorText(r))); });
    const acc = p.accesses || [];
    body.replaceChildren(
      h("section", { class: "card" }, h("div", { class: "promise" + (p.withdrawn ? " off" : "") }, h("div", { class: "seal", "aria-hidden": "true" }, p.withdrawn ? "!" : "✓"),
        h("div", {}, h("h2", { style: "margin:0 0 4px" }, p.withdrawn ? "You have withdrawn" : "You are in control"),
          h("p", { style: "margin:0" }, p.note))),
        h("div", { class: "confirm" }, h("button", { class: p.withdrawn ? "" : "ghost danger", onclick: askConfirm }, p.withdrawn ? "Restore my consent" : "Withdraw my consent")), confirm, flash),
      h("section", { class: "card" }, h("h2", { style: "margin-top:0" }, "What you agreed to"),
        h("p", {}, "Your data may be used for ", h("b", {}, use), mods.length ? ", with these limits: " + mods.join(", ") : "", c.population ? `, for the ${c.population} group only` : "", "."),
        c.consent_date ? h("p", { class: "muted", style: "margin:0 0 10px" }, "Consent given on " + c.consent_date + ".") : null,
        h("button", { class: "ghost", onclick: () => download(p) }, "Download my consent (FHIR)"),
        h("p", { class: "muted", style: "margin:8px 0 0" }, "A standard health-data format your clinic or another system can read. These are demo records, so the file is marked as simulated.")),
      h("section", { class: "card" }, h("h2", { style: "margin-top:0" }, "Change what you agree to"), form),
      h("section", { class: "card" }, h("h2", { style: "margin-top:0" }, "Who used statistics that included you"),
        acc.length ? h("ul", { class: "timeline-d" }, acc.map((a) => h("li", {}, h("span", { class: "when" }, when(a.ts)), h("span", {}, `${a.institution || "A researcher"} studied ${plain(a.purpose)}${a.disease ? " (" + a.disease + ")" : ""}, receiving ${plain(a.level)} figures.`))))
          : h("p", { class: "muted" }, "No researcher has received statistics that included you yet."),
        p.access_total > acc.length ? h("p", { class: "muted" }, `Showing ${acc.length} of ${p.access_total}.`) : null),
      h("section", { class: "card" }, h("h2", { style: "margin-top:0" }, "Ask the consent concierge"),
        h("div", { style: "display:flex;gap:8px;flex-wrap:wrap" }, CHIPS.map(([k, t]) => { const b = h("button", { class: "chipbtn", "aria-pressed": "false", onclick: () => ask(k, b) }, t); return b; })), answer));
  }
  await load();
  return root;
}

const DISEASES = ["diabetes", "cancer", "cardiovascular", "asthma"];

function consentForm(p, done) {
  const c = p.consent, mods = new Set((c.modifiers || []).map((m) => m.toUpperCase()));
  const use = h("select", { id: "c-use", onchange: () => (dis.hidden = use.value !== "DS") },
    [["GRU", "Any research"], ["HMB", "Health, medical or biomedical research"], ["DS", "Research on one disease"]].map(([v, t]) => h("option", { value: v }, t)));
  use.value = (c.use || "GRU").toUpperCase();
  const disSel = h("select", { id: "c-dis" }, DISEASES.map((d) => h("option", { value: d }, d)));
  disSel.value = c.disease || DISEASES[0];
  const dis = h("label", { class: "f", for: "c-dis", hidden: use.value !== "DS" }, "Which disease", disSel);
  const boxes = Object.entries(MOD).map(([k, t]) => {
    const cb = h("input", { type: "checkbox", id: "m-" + k, value: k.toUpperCase() });
    cb.checked = mods.has(k.toUpperCase());
    return h("label", { for: "m-" + k, style: "display:flex;gap:8px;align-items:center;font-family:var(--sans);font-size:14px" }, cb, "Do not allow: " + t.replace(/^no /, "").replace(/^not as a /, ""));
  });
  const save = h("button", { onclick: async () => {
    const body = { use: use.value, disease: use.value === "DS" ? disSel.value : null, modifiers: boxes.map((l) => l.firstChild).filter((x) => x.checked).map((x) => x.value) };
    save.disabled = true;
    done(await donorApi(`/donor/${p.id}/consent`, { method: "PUT", body }));
    save.disabled = false;
  } }, "Save my choices");
  return h("div", { class: "stack", style: "font-family:var(--sans)" }, h("label", { class: "f", for: "c-use" }, "My data may be used for", use), dis, h("div", { class: "stack", style: "gap:8px" }, boxes), h("div", {}, save));
}

async function download(p) {
  const r = await donorApi(`/donor/${p.id}/consent.fhir.json`);
  if (!r.ok) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(r.data, null, 2)], { type: "application/fhir+json" }));
  const a = h("a", { href: url, download: `consent-${r.data.id}.fhir.json` });
  document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}
