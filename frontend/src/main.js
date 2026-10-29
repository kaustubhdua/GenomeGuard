import { boot, connectKey, disconnectKey, state, setWho, isSteward } from "./api.js";
import { h } from "./ui.js";
import { startTour, tourAvailable } from "./tour.js";

const ROUTES = [
  { re: /^#\/chromosomes$/, load: () => import("./pages/chromosomes.js"), nav: "chromosomes", title: "Chromosomes" },
  { re: /^#\/datasets$/, load: () => import("./pages/datasets.js"), nav: "datasets", title: "Datasets" },
  { re: /^#\/overview$/, load: () => import("./pages/overview.js"), nav: "overview", title: "Overview" },
  { re: /^#\/requests$/, load: () => import("./pages/requests.js"), nav: "requests", title: "Requests" },
  { re: /^#\/request\/(\d+)$/, load: () => import("./pages/decision.js"), nav: "requests", title: "Decision" },
  { re: /^#\/family\/(\d+)$/, load: () => import("./pages/family.js"), nav: "family", title: "Family exposure" },
  { re: /^#\/anomalies$/, load: () => import("./pages/anomalies.js"), nav: "anomalies", title: "Anomalies" },
  { re: /^#\/audit$/, load: () => import("./pages/audit.js"), nav: "audit", title: "Audit log" },
  { re: /^#\/donor$/, load: () => import("./pages/donor.js"), nav: "donor", title: "My data" },
  { re: /^#\/redteam$/, load: () => import("./pages/redteam.js"), nav: "redteam", title: "Red-team results" },
  { re: /^#\/federated$/, load: () => import("./pages/federated.js"), nav: "federated", title: "Federated analysis" },
];
function prefetchRoute(hash) {
  const hit = ROUTES.find((r) => hash.match(r.re));
  if (!hit || hit.prefetched) return;
  hit.prefetched = true;
  hit.load().catch(() => { hit.prefetched = false; }); // a failed prefetch must remain retryable
}

const NAV = [
  [null, [["overview", "Overview", "#/overview"], ["chromosomes", "Chromosomes", "#/chromosomes"], ["datasets", "Datasets", "#/datasets"]]],
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
  view.setAttribute("aria-busy", "true");
  view.replaceChildren(h("div", { class: "skeleton", style: "height:120px", role: "status", "aria-label": "Loading page" }));
  let page;
  try {
    if (hit && !state.demo && ["donor", "redteam", "federated"].includes(hit[0].nav)) {
      page = h("section", { class: "card empty-state" },
        h("h1", {}, "This workflow is not enabled for this deployment"),
        h("p", { class: "muted" }, "This page uses demo personas or simulated federated data. It is disabled outside demo mode rather than presenting simulated results as real participant workflows."),
        h("a", { class: "btn ghost", href: "#/overview" }, "Return to overview"));
    } else if (hit) {
      const mod = await hit[0].load(); // route code is fetched only when the route is first visited
      if (mine !== token) return;
      page = await mod.render(hit[1].slice(1));
    } else {
      page = h("div", { class: "empty" }, "That page does not exist. ", h("a", { href: "#/overview" }, "Go to the overview"));
    }
  } catch {
    if (mine !== token) return;
    page = h("section", { class: "card error-boundary", role: "alert" },
      h("h1", {}, "This page couldn't load"),
      h("p", { class: "muted" }, "The page failed to load. Your existing data has not been changed by this display error."),
      h("div", { class: "confirm" },
        h("button", { onclick: () => render() }, "Try again"),
        h("a", { class: "btn ghost", href: "#/overview" }, "Back to overview")));
  }
  if (mine !== token) return; // a newer navigation won
  if (page instanceof Element) page.classList.add("page-enter");
  view.replaceChildren(page);
  view.setAttribute("aria-busy", "false");
  // Images added by future pages default to native lazy loading and async decode.
  view.querySelectorAll("img").forEach((img) => {
    if (!img.hasAttribute("loading")) img.loading = "lazy";
    if (!img.hasAttribute("decoding")) img.decoding = "async";
  });
  document.title = (hit ? hit[0].title + " · " : "") + "GenomeGuard";
  view.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

function visibleNav() {
  if (state.demo) return NAV;
  return NAV.map(([label, items]) => [label, items.filter(([id]) => {
    if (["donor", "redteam", "federated"].includes(id)) return false;
    if (["family", "anomalies", "audit"].includes(id)) return isSteward();
    return true;
  })]).filter(([, items]) => items.length);
}

function drawNav(active) {
  $("nav").replaceChildren(...visibleNav().map(([label, items]) =>
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
  el.classList.toggle("real", p.genotypes === "real_vcf");
}

function drawWho() {
  const sel = $("who");
  const label = $("who-label");
  const panel = $("auth-panel");
  if (!state.demo) {
    sel.hidden = true;
    label.hidden = true;
    panel.hidden = false;
    $("auth-kind").value = isSteward() ? "steward" : "researcher";
    $("who-note").textContent = isSteward()
      ? "Steward credentials are active in memory for this tab."
      : state.who ? "Researcher credentials are active in memory for this tab."
        : "Connect using a steward or researcher API key issued by your administrator.";
    return;
  }
  sel.hidden = false;
  label.hidden = false;
  panel.hidden = true;
  const reqs = state.demo.requesters || [];
  sel.replaceChildren(...reqs.map((r) => h("option", { value: r.api_key }, `${r.name} (${r.tier})${r.frozen ? " · frozen" : ""}`)),
    h("option", { value: "steward" }, "Steward (reviewer)"));
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
  ...visibleNav().flatMap(([label, items]) => items.map(([, text, href]) => ({ text, hint: label || "Page", run: () => (location.hash = href) }))),
  ...(state.demo ? [
    { text: "Switch to the steward view", hint: "Acting as", run: () => { setWho("steward"); drawWho(); drawNav(""); render(); } },
    { text: "Switch to the researcher view", hint: "Acting as", run: () => { const r = (state.demo || { requesters: [] }).requesters[0]; if (r) { setWho(r.api_key); drawWho(); drawNav(""); render(); } } },
  ] : []),
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
// Mobile drawer: closed means hidden from keyboard and screen readers too, and Escape or
// following a link closes it and gives focus back to the button.
function setMenu(open, returnFocus = false) {
  $("shell").classList.toggle("open", open);
  $("menu").setAttribute("aria-expanded", String(open));
  $("menu").setAttribute("aria-label", open ? "Close menu" : "Open menu");
  if (open) $("nav").querySelector("a")?.focus();
  else if (returnFocus) $("menu").focus();
}
$("menu").addEventListener("click", () => setMenu(!$("shell").classList.contains("open")));
$("scrim").addEventListener("click", () => setMenu(false));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && $("shell").classList.contains("open") && !$("cmdk").classList.contains("open")) setMenu(false, true);
});
window.addEventListener("hashchange", () => { if ($("shell").classList.contains("open")) setMenu(false); });
$("who").addEventListener("change", (e) => { setWho(e.target.value); drawWho(); drawNav(""); render(); });
$("connect-key").addEventListener("click", async () => {
  const key = $("api-key-input").value.trim();
  const kind = $("auth-kind").value;
  const status = $("auth-status");
  if (!key) { status.textContent = "Enter the API key issued to you."; return; }
  status.textContent = "Checking credentials…";
  $("connect-key").disabled = true;
  try {
    const result = await connectKey(kind, key);
    if (!result.ok) {
      status.textContent = result.status === 401 ? "The key was rejected. Check it with your administrator."
        : result.data?.message || "Could not verify this key.";
      return;
    }
    $("api-key-input").value = "";
    drawWho();
    status.textContent = "Connected. This key stays in memory for this tab and is not saved.";
    drawNav("");
    render();
  } finally {
    $("connect-key").disabled = false;
  }
});
$("auth-kind").addEventListener("change", () => { $("auth-status").textContent = ""; });
$("disconnect-key").addEventListener("click", () => {
  disconnectKey();
  $("api-key-input").value = "";
  $("auth-status").textContent = "Disconnected. Credentials have been cleared from this tab.";
  drawWho();
  drawNav("");
  render();
});
$("api-key-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); $("connect-key").click(); }
});
// Warm the route chunk when a visitor signals intent, without loading every page at startup.
for (const container of [ $("nav"), $("view") ]) {
  container.addEventListener("pointerover", (e) => {
    const link = e.target.closest("a[href^='#/']");
    if (link) prefetchRoute(link.getAttribute("href"));
  });
  container.addEventListener("focusin", (e) => {
    const link = e.target.closest("a[href^='#/']");
    if (link) prefetchRoute(link.getAttribute("href"));
  });
}
window.addEventListener("hashchange", render);
window.addEventListener("gg:refresh-who", async () => { await boot(); drawWho(); });
boot().then(() => { drawWho(); drawProv(); render(); });
