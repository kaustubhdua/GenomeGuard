import { boot, state, setWho, isSteward } from "./api.js";
import { h } from "./ui.js";
import * as overview from "./pages/overview.js";
import * as requests from "./pages/requests.js";
import * as decision from "./pages/decision.js";
import * as family from "./pages/family.js";
import * as anomalies from "./pages/anomalies.js";
import * as audit from "./pages/audit.js";
import * as redteam from "./pages/redteam.js";
import * as federated from "./pages/federated.js";
import * as donor from "./pages/donor.js";
import { startTour, tourAvailable } from "./tour.js";

const ROUTES = [
  { re: /^#\/overview$/, mod: overview, nav: "overview", title: "Overview" },
  { re: /^#\/requests$/, mod: requests, nav: "requests", title: "Requests" },
  { re: /^#\/request\/(\d+)$/, mod: decision, nav: "requests", title: "Decision" },
  { re: /^#\/family\/(\d+)$/, mod: family, nav: "family", title: "Family exposure" },
  { re: /^#\/anomalies$/, mod: anomalies, nav: "anomalies", title: "Anomalies" },
  { re: /^#\/audit$/, mod: audit, nav: "audit", title: "Audit log" },
  { re: /^#\/donor$/, mod: donor, nav: "donor", title: "My data" },
  { re: /^#\/redteam$/, mod: redteam, nav: "redteam", title: "Red-team results" },
  { re: /^#\/federated$/, mod: federated, nav: "federated", title: "Federated analysis" },
];
const NAV = [
  [null, [["overview", "Overview", "#/overview"]]],
  ["Researcher", [["requests", "Requests", "#/requests"]]],
  ["Steward", [["family", "Family exposure", "#/family/1", true], ["anomalies", "Anomalies", "#/anomalies", true], ["audit", "Audit log", "#/audit", true]]],
  ["Patient", [["donor", "My data", "#/donor"]]],
  ["Evidence", [["redteam", "Red-team results", "#/redteam"], ["federated", "Federated analysis", "#/federated"]]],
];

const $ = (id) => document.getElementById(id);
let token = 0;

async function render() {
  const view = $("view");
  const hash = location.hash && location.hash !== "#" ? location.hash : "#/overview";
  const hit = ROUTES.map((r) => [r, hash.match(r.re)]).find(([, m]) => m);
  drawNav(hit ? hit[0].nav : "");
  $("crumb").textContent = hit ? hit[0].title : "Not found";
  $("shell").classList.remove("open");
  const mine = ++token;
  view.replaceChildren(h("div", { class: "skeleton", style: "height:120px" }));
  const page = hit ? await hit[0].mod.render(hit[1].slice(1)) : h("div", { class: "empty" }, "That page does not exist. ", h("a", { href: "#/overview" }, "Go to the overview"));
  if (mine !== token) return; // a newer navigation won
  view.replaceChildren(page);
  document.title = (hit ? hit[0].title + " · " : "") + "GenomeGuard";
  view.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

function drawNav(active) {
  $("nav").replaceChildren(...NAV.map(([label, items]) =>
    h("div", { class: "nav-group" }, label ? h("div", { class: "nav-label" }, label) : null,
      items.map(([id, text, href, steward]) =>
        h("a", { href, "aria-current": id === active ? "page" : false }, text, steward ? h("span", { class: "tag" }, "steward") : null)))));
}

function drawProv() {
  const p = (state.health || {}).provenance || {};
  const el = $("prov");
  if (!p.genotypes) { el.hidden = true; return; }
  el.textContent = p.genotypes_label + ", " + p.consent_label.toLowerCase();
  el.title = [p.genotypes_label, p.consent_label, p.relatives_label, p.agents_label, p.encryption].join(". ");
  el.classList.toggle("real", p.genotypes === "real_1000g");
}

function drawWho() {
  const sel = $("who");
  const reqs = state.demo ? state.demo.requesters : [];
  sel.replaceChildren(...reqs.map((r) => h("option", { value: r.api_key }, `${r.name} (${r.tier})${r.frozen ? " · frozen" : ""}`)),
    state.demo ? h("option", { value: "steward" }, "Steward (reviewer)") : null);
  sel.value = state.who;
  $("who-note").textContent = isSteward()
    ? "Sees audit, anomalies, family exposure and can review held requests."
    : "Researcher view: results only, no withheld detail.";
}

// ---- theme ----
function setTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem("gg_theme", t); } catch { /* ignore */ }
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme")
    || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  setTheme(cur === "dark" ? "light" : "dark");
}

// ---- command palette ----
const ACTIONS = () => [
  ...NAV.flatMap(([label, items]) => items.map(([, text, href]) => ({ text, hint: label || "Page", run: () => (location.hash = href) }))),
  { text: "Switch to the steward view", hint: "Acting as", run: () => { setWho("steward"); drawWho(); render(); } },
  { text: "Switch to the researcher view", hint: "Acting as", run: () => { const r = (state.demo || { requesters: [] }).requesters[0]; if (r) { setWho(r.api_key); drawWho(); render(); } } },
  { text: "Switch colour theme", hint: "Appearance", run: toggleTheme },
  ...(tourAvailable() ? [{ text: "Start the guided tour", hint: "Help", run: startTour }] : []),
];
let sel = 0, shown = [];
function openPalette() { $("cmdk").classList.add("open"); const i = $("cmdk-input"); i.value = ""; filter(); i.focus(); }
function closePalette() { $("cmdk").classList.remove("open"); }
function filter() {
  const q = $("cmdk-input").value.trim().toLowerCase();
  shown = ACTIONS().filter((a) => !q || a.text.toLowerCase().includes(q));
  sel = Math.min(sel, Math.max(0, shown.length - 1));
  paint();
}
function paint() {
  $("cmdk-list").replaceChildren(...shown.map((a, i) => h("li", { role: "option", "aria-selected": i === sel ? "true" : "false", onclick: () => choose(i) }, a.text, h("small", {}, a.hint))));
  if (!shown.length) $("cmdk-list").replaceChildren(h("li", {}, "Nothing matches"));
}
function choose(i) { const a = shown[i]; if (!a) return; closePalette(); a.run(); }

document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); return; }
  if (!$("cmdk").classList.contains("open")) return;
  if (e.key === "Escape") closePalette();
  else if (e.key === "ArrowDown") { e.preventDefault(); sel = (sel + 1) % Math.max(1, shown.length); paint(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); sel = (sel - 1 + shown.length) % Math.max(1, shown.length); paint(); }
  else if (e.key === "Enter") { e.preventDefault(); choose(sel); }
});
$("cmdk-input").addEventListener("input", () => { sel = 0; filter(); });
$("cmdk").addEventListener("click", (e) => { if (e.target === $("cmdk")) closePalette(); });
$("open-cmdk").addEventListener("click", openPalette);
$("theme").addEventListener("click", toggleTheme);
$("menu").addEventListener("click", () => $("shell").classList.toggle("open"));
$("scrim").addEventListener("click", () => $("shell").classList.remove("open"));
$("who").addEventListener("change", (e) => { setWho(e.target.value); drawWho(); render(); });
window.addEventListener("hashchange", render);
window.addEventListener("gg:refresh-who", async () => { await boot(); drawWho(); });
boot().then(() => { drawWho(); drawProv(); render(); });
