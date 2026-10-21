import { api, isSteward } from "../api.js";
import { h, svg, row, notice, errorText, badge } from "../ui.js";

export async function render([id]) {
  const root = h("div", {});
  root.dataset.title = "Family exposure";
  root.append(h("h1", {}, "Family exposure"),
    h("p", { class: "lede" }, "Rare variants run in families. This shows which relatives of the people in a request could be exposed, including relatives who never joined the study."));
  if (!isSteward()) { root.append(notice("warn", "This view describes withheld variants and registry relatives, so only stewards can open it. Switch with “Acting as”.")); return root; }

  const list = await api("/requests");
  const choose = h("div", { class: "presets" }, ((list.data && list.data.requests) || []).slice(0, 12).map((r) => h("a", { class: "btn ghost", href: "#/family/" + r.id, style: "text-decoration:none;display:inline-flex;align-items:center", "aria-current": String(r.id) === id ? "true" : false }, "Request #" + r.id)));
  root.append(choose);
  const res = await api(`/requests/${id}/exposure`);
  if (!res.ok) { root.append(notice("err", res.status === 404 ? "No request #" + id + " yet. Send one from the Requests page first." : errorText(res))); return root; }
  const g = res.data, t = g.totals;
  root.append(notice("warn", h("b", {}, "Simulated model. "), g.model.replace(/^SIMULATED:\s*/, "")));
  const ledger = h("div", { class: "ledger" });
  ledger.append(row("Summary", `Request #${g.request_id}`,
    h("p", { style: "margin:0" }, h("b", {}, t.subjects), " people in the request carry a very rare variant. ", h("b", {}, t.exposed_relatives), " of their relatives are not in the request, yet would be exposed by it."),
    Object.keys(t.by_degree).length ? h("p", { class: "muted" }, "By genealogical distance: " + Object.entries(t.by_degree).map(([k, v]) => `${v} at 1/2^${k} expected sharing`).join(", ") + ".") : null));
  if (!g.families.length) ledger.append(row("Families", "", h("p", { class: "empty" }, "This request included no carriers of very rare variants, so no relatives are exposed.")));
  else ledger.append(row("Families", "Dark = carrier in the request. Glowing = relative who would be exposed. Hollow = relative also in the request.",
    h("div", { class: "split" }, g.families.map(familyGraph))));
  ledger.append(row("How to read it", "", h("p", { style: "margin:0" }, g.note + " Percentages are expected averages of shared DNA from the family tree. Real sharing varies, especially for distant cousins.")));
  root.append(ledger);
  return root;
}

function familyGraph(f) {
  const W = 360, H = 300, cx = W / 2, cy = H / 2, R = 108;
  const n = f.nodes.length, pos = {};
  const carriers = f.nodes.filter((x) => x.kind === "carrier"), rels = f.nodes.filter((x) => x.kind !== "carrier");
  // carriers sit on an inner ring, relatives on the outer ring
  carriers.forEach((c, i) => { const a = (2 * Math.PI * i) / Math.max(carriers.length, 1) - Math.PI / 2; const r = carriers.length > 1 ? 44 : 0; pos[c.id] = [cx + r * Math.cos(a), cy + r * Math.sin(a)]; });
  rels.forEach((c, i) => { const a = (2 * Math.PI * i) / Math.max(rels.length, 1) - Math.PI / 2; pos[c.id] = [cx + R * Math.cos(a), cy + R * Math.sin(a)]; });
  const root = svg("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${f.family}: ${carriers.length} carriers, ${rels.filter((r) => r.exposed).length} exposed relatives` });
  const seen = new Set();
  for (const e of f.edges) {
    const key = [e.from, e.to].sort().join("|"); if (seen.has(key)) continue; seen.add(key);
    const a = pos[e.from], b = pos[e.to]; if (!a || !b) continue;
    root.append(svg("line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "var(--ink-2)", "stroke-width": Math.max(1, e.shared * 6), opacity: 0.6 }, svg("title", {}, `${e.relation}, expected sharing ${(e.shared * 100).toFixed(1)}%`)));
  }
  for (const nd of f.nodes) {
    const [x, y] = pos[nd.id];
    const cls = nd.kind === "carrier" ? "node-carrier" : "node-relative " + (nd.exposed ? "exposed" : "safe");
    const g = svg("g", { class: cls }, svg("circle", { cx: x, cy: y, r: nd.kind === "carrier" ? 15 : 17, "stroke-width": 2 }),
      svg("title", {}, nd.kind === "carrier" ? "Carrier in this request" : `${nd.relation || "relative"}, ${(nd.shared * 100).toFixed(1)}% expected sharing${nd.exposed ? ", not in the request" : ", also in the request"}`));
    if (nd.kind !== "carrier") g.append(svg("text", { x, y: y + 32, "text-anchor": "middle" }, nd.relation || "relative"));
    root.append(g);
  }
  return h("figure", { class: "fam", style: "margin:0" }, h("figcaption", { style: "padding:6px 10px;font-weight:600" }, f.family), root);
}
