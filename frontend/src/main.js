import { boot, state, setWho, isSteward } from "./api.js";
import { h } from "./ui.js";
import * as requests from "./pages/requests.js";
import * as decision from "./pages/decision.js";
import * as family from "./pages/family.js";
import * as anomalies from "./pages/anomalies.js";
import * as audit from "./pages/audit.js";
import * as redteam from "./pages/redteam.js";

const ROUTES = [
  { re: /^#\/requests$/, mod: requests, nav: "requests" },
  { re: /^#\/request\/(\d+)$/, mod: decision, nav: "requests" },
  { re: /^#\/family\/(\d+)$/, mod: family, nav: "family" },
  { re: /^#\/anomalies$/, mod: anomalies, nav: "anomalies" },
  { re: /^#\/audit$/, mod: audit, nav: "audit" },
  { re: /^#\/redteam$/, mod: redteam, nav: "redteam" },
];
const NAV = [["requests", "Requests", "#/requests", false], ["family", "Family exposure", "#/family/1", true],
  ["anomalies", "Anomalies", "#/anomalies", true], ["audit", "Audit log", "#/audit", true], ["redteam", "Red-team results", "#/redteam", false]];

let token = 0;
async function render() {
  const view = document.getElementById("view");
  const hash = location.hash || "#/requests";
  const hit = ROUTES.map((r) => [r, hash.match(r.re)]).find(([, m]) => m);
  drawNav(hit ? hit[0].nav : "");
  const mine = ++token;
  view.replaceChildren(h("p", { class: "muted" }, "Loading…"));
  const page = hit ? await hit[0].mod.render(hit[1].slice(1)) : h("div", { class: "empty" }, "That page does not exist. ", h("a", { href: "#/requests" }, "Go to requests"));
  if (mine !== token) return; // a newer navigation won
  view.replaceChildren(page);
  document.title = (page.dataset && page.dataset.title ? page.dataset.title + " · " : "") + "GenomeGuard";
  view.focus({ preventScroll: true });
}

function drawNav(active) {
  const nav = document.getElementById("nav");
  nav.replaceChildren(...NAV.map(([id, label, href, steward]) =>
    h("a", { href, "aria-current": id === active ? "page" : false }, label, steward ? h("span", { class: "tag" }, "steward") : null)));
}

function drawWho() {
  const sel = document.getElementById("who");
  const reqs = state.demo ? state.demo.requesters : [];
  sel.replaceChildren(...reqs.map((r) => h("option", { value: r.api_key }, `${r.name} (${r.tier})${r.frozen ? " · frozen" : ""}`)),
    state.demo ? h("option", { value: "steward" }, "Steward (reviewer)") : null);
  sel.value = state.who;
  document.getElementById("who-note").textContent = isSteward()
    ? "Sees audit, anomalies, family exposure and can review held requests."
    : "Researcher view: results only, no withheld detail.";
}

document.getElementById("who").addEventListener("change", (e) => { setWho(e.target.value); drawWho(); render(); });
window.addEventListener("hashchange", render);
window.addEventListener("gg:refresh-who", async () => { await boot(); drawWho(); });
boot().then(() => { drawWho(); render(); });
