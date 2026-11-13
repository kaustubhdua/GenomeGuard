import { api, boot, state, setWho, selectDemoRequester, isSteward, signInWithInstitution, signOutInstitution } from "./api.js";
import { h } from "./ui.js";
import { startTour, tourAvailable } from "./tour.js";

const ROUTES = [
  { re: /^#\/chromosomes$/, load: () => import("./pages/chromosomes.js"), nav: "chromosomes", title: "Chromosomes" },
  { re: /^#\/datasets$/, load: () => import("./pages/datasets.js"), nav: "datasets", title: "Datasets" },
  { re: /^#\/sources$/, load: () => import("./pages/sources.js"), nav: "sources", title: "Source discovery" },
  { re: /^#\/research(?:\?.*)?$/, load: () => import("./pages/research.js"), nav: "research", title: "Research discovery" },
  { re: /^#\/variants(?:\?.*)?$/, load: () => import("./pages/variants.js"), nav: "variants", title: "Variant inspector" },
  { re: /^#\/dataset-qc$/, load: () => import("./pages/dataset-qc.js"), nav: "dataset-qc", title: "Dataset QC" },
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
  ["Overview", [["overview", "Overview", "#/overview"]]],
  ["Dataset Explorer", [["datasets", "Datasets", "#/datasets"], ["chromosomes", "Chromosomes", "#/chromosomes"],
    ["variants", "Variant inspector", "#/variants"], ["sources", "Source discovery", "#/sources"], ["research", "Research discovery", "#/research"]]],
  ["Research Requests", [["requests", "Requests", "#/requests"]]],
  ["Steward Review", [["requests", "Request review queue", "#/requests", true],
    ["dataset-qc", "Dataset QC", "#/dataset-qc", true], ["family", "Family exposure", "#/family/1", true]]],
  ["Audit & Security", [["anomalies", "Anomalies", "#/anomalies", true], ["audit", "Audit log", "#/audit", true]]],
  ["Research Lab", [["donor", "My data", "#/donor"], ["redteam", "Red-team results", "#/redteam"],
    ["federated", "Federated analysis", "#/federated"]]],
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
  view.replaceChildren(h("div", { class: "skeleton lattice-loader", role: "status", "aria-label": "Loading page" },
    h("div", { class: "lattice-cells", "aria-hidden": "true" }, Array.from({ length: 35 }, (_, i) => h("i", { style: "--cell:" + i }))),
    h("span", {}, "Preparing workspace"), h("small", {}, "Loading secure research view")));
  let page;
  try {
    if (hit && !state.demo && ["donor", "redteam", "federated"].includes(hit[0].nav)) {
      page = h("section", { class: "card empty-state" },
        h("h1", {}, "This workflow is not enabled for this deployment"),
        h("p", { class: "muted" }, "This workflow requires a provisioned research account and verified institutional identity. It is unavailable in guest preview mode."),
        h("a", { class: "btn ghost", href: "#/overview" }, "Return to overview"));
    } else if (hit) {
      const mod = await hit[0].load(); // route code is fetched only when the route is first visited
      if (mine !== token) return;
      page = await mod.render(hit[1].slice(1));
    } else {
      page = h("div", { class: "empty" }, "That page does not exist. ", h("a", { href: "#/overview" }, "Go to the overview"));
    }
  } catch (error) {
    if (mine !== token) return;
    console.error("GenomeGuard route render failed", { route: hash, title: hit?.[0]?.title }, error);
    page = h("section", { class: "card error-boundary", role: "alert" },
      h("h1", {}, "This page couldn't load"),
      h("p", { class: "muted" }, "The page failed to load. Your existing data has not been changed by this display error."),
      h("div", { class: "confirm" },
        h("button", { onclick: () => render() }, "Try again"),
        h("a", { class: "btn ghost", href: "#/overview" }, "Back to overview")));
  }
  if (mine !== token) return;
  if (page instanceof Element) {
    page.classList.add("page-enter");
    // Set image hints before inserting the page so the browser can defer off-screen
    // requests from the start instead of discovering them after they enter the DOM.
    page.querySelectorAll("img").forEach((img) => {
      if (!img.hasAttribute("loading")) img.loading = "lazy";
      if (!img.hasAttribute("decoding")) img.decoding = "async";
    });
  }
  view.replaceChildren(page);
  view.setAttribute("aria-busy", "false");
  document.title = (hit ? hit[0].title + " · " : "") + "GenomeGuard";
  view.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

function visibleNav() {
  const steward = isSteward();
  return NAV.map(([label, items]) => [label, items.filter(([id]) => {
    if (id === "requests") return label === (steward ? "Steward Review" : "Research Requests");
    if (["dataset-qc", "family", "anomalies", "audit"].includes(id)) return steward;
    if (["donor", "redteam", "federated"].includes(id)) return state.demo;
    return true;
  })]).filter(([, items]) => items.length);
}

function drawNav(active) {
  $("nav").replaceChildren(...visibleNav().map(([label, items]) =>
    h("div", { class: "nav-group" }, label ? h("div", { class: "nav-label" }, label) : null,
      items.map(([id, text, href, steward]) =>
        h("a", { href, "aria-current": id === active ? "page" : false }, text, steward ? h("span", { class: "tag" }, "steward") : null)))));
}

function drawWho() {
  const selector = $("who");
  const label = $("who-label");
  const note = $("who-note");
  // Account-free guest mode: only synthetic demo personas are selectable.
  if (state.demo) {
    $("auth-controls").replaceChildren();
    label.hidden = false;
    selector.hidden = false;
    const options = (state.demo.requesters || []).map((r) => [
      String(r.id), r.name || "Synthetic demo researcher",
    ]);
    selector.replaceChildren(...options.map(([value, text]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = text;
      return option;
    }));
    selector.value = state.who || "";
    note.textContent = "Synthetic guest preview · short-lived session · no API keys exposed";
  } else {
    label.hidden = true;
    selector.hidden = true;
    const controls = $("auth-controls");
    controls.replaceChildren();
    if (state.oidc?.enabled) {
      if (state.me) {
        controls.append(
          h("p", { class: "fine" }, "Signed in: " + (state.me.name || "Institutional user")
            + " · " + state.me.role),
          h("button", { type: "button", class: "btn ghost", onclick: () => {
            signOutInstitution();
            drawWho();
            drawNav("");
            render();
          } }, "Sign out of GenomeGuard")
        );
        note.textContent = "Institutional identity · " + (state.me.institution || "verified organization");
      } else {
        controls.append(h("button", {
          type: "button", class: "btn", onclick: async (event) => {
            const button = event.currentTarget;
            button.disabled = true;
            button.textContent = "Connecting…";
            try {
              await signInWithInstitution();
            } catch {
              drawWho();
            }
          },
        }, "Sign in with your institution"));
        note.textContent = state.oidcError || "Access is limited to provisioned institutional identities.";
      }
    } else {
      note.textContent = "Account creation and sign-in are disabled because institutional sign-in is not configured. Production research access remains disabled.";
    }
  }
}

function drawProv() {
  const p = (state.health || {}).provenance || {};
  const el = $("prov");
  if (!p.genotypes) { el.hidden = true; return; }
  el.textContent = p.genotypes_label + ", " + p.consent_label.toLowerCase();
  el.title = [p.genotypes_label, p.consent_label, p.relatives_label, p.agents_label, p.encryption].join(". ");
  el.classList.toggle("real", p.genotypes === "real_vcf");
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
    { text: "Switch to the researcher view", hint: "Acting as", run: async () => {
      const r = (state.demo || { requesters: [] }).requesters[0];
      if (r) await selectDemoRequester(r.id);
      drawWho(); drawNav(""); render();
    } },
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
$("who").addEventListener("change", async (e) => {
  const result = await selectDemoRequester(e.target.value);
  if (!result.ok) {
    $("who-note").textContent = result.data?.message || "Could not start the selected demo session.";
    return;
  }
  drawWho(); drawNav(""); render();
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
// Subtle magnetic hover + cursor spotlight, delegated so dynamic route cards work too.
const hoverView = $("view");
if (!matchMedia("(prefers-reduced-motion: reduce)").matches && !matchMedia("(hover: none)").matches) {
  let hoverCard = null;
  hoverView.addEventListener("pointermove", (e) => {
    const card = e.target.closest(".gg-metric, .gg-panel, .card, .gg-fact");
    if (card !== hoverCard) {
      if (hoverCard) hoverCard.style.removeProperty("--mx");
      hoverCard = card;
    }
    if (!card) return;
    const r = card.getBoundingClientRect();
    card.style.setProperty("--mx", ((e.clientX-r.left)/r.width*100).toFixed(1)+"%");
    card.style.setProperty("--my", ((e.clientY-r.top)/r.height*100).toFixed(1)+"%");
    card.style.setProperty("--mag-x", (((e.clientX-r.left)/r.width-.5)*5).toFixed(2)+"px");
    card.style.setProperty("--mag-y", (((e.clientY-r.top)/r.height-.5)*5).toFixed(2)+"px");
  }, { passive:true });
  hoverView.addEventListener("pointerleave", () => {
    if (hoverCard) {
      ["--mx","--my","--mag-x","--mag-y"].forEach(k=>hoverCard.style.removeProperty(k));
      hoverCard=null;
    }
  });
}
window.addEventListener("hashchange", render);
window.addEventListener("gg:refresh-who", async () => { await boot(); drawWho(); });
function drawConnectionStatus() {
  const el = $("connection-status");
  if (!state.bootError) {
    el.hidden = true;
    el.replaceChildren();
    return;
  }
  el.hidden = false;
  el.replaceChildren(
    h("span", {}, "GenomeGuard API is taking longer than expected. " + state.bootError),
    h("button", { type: "button", onclick: async () => {
      el.querySelector("button").disabled = true;
      el.querySelector("button").textContent = "Retrying…";
      await boot();
      drawWho();
      drawProv();
      drawConnectionStatus();
      if (!state.bootError) render();
    } }, "Retry connection")
  );
}

// Paint the shell immediately; the animated page skeleton remains visible during API startup.
drawWho();
drawProv();
render();
boot().then(() => {
  drawWho();
  drawProv();
  drawConnectionStatus();
  render();
}).catch(() => {
  state.bootError = "A startup error occurred. Check your connection and retry.";
  drawConnectionStatus();
});
