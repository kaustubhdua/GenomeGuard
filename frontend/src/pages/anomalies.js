import { api, isSteward, state } from "../api.js";
import { h, row, lineChart, legend, notice, errorText, when } from "../ui.js";

const TH = [{ y: 0.35, color: "var(--band-med)", label: "warn" }, { y: 0.55, color: "var(--transform)", label: "throttle" }, { y: 0.75, color: "var(--deny)", label: "freeze" }];

export async function render() {
  const root = h("div", {});
  root.dataset.title = "Anomalies";
  root.append(h("h1", {}, "Anomaly monitor"),
    h("p", { class: "lede" }, "Watches each account's query pattern: how fast, how similar, how tightly the cohort is shrinking, and whether two answers could be subtracted to isolate people."));
  if (!isSteward()) { root.append(notice("warn", "Detector scores would let an attacker tune queries to stay under them, so only stewards can see this view.")); return root; }
  const body = h("div", {});
  root.append(body);
  async function draw() {
    const res = await api("/anomalies");
    if (!res.ok) { body.replaceChildren(notice("err", errorText(res))); return; }
    const { requesters, alerts } = res.data;
    const ledger = h("div", { class: "ledger" });
    for (const r of requesters) ledger.append(requesterRow(r, draw));
    ledger.append(row("Alerts", `${alerts.length} raised`, alerts.length ? h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "When"), h("th", {}, "Account"), h("th", {}, "Signal"), h("th", { class: "num" }, "Score"), h("th", {}, "Action"))),
      h("tbody", {}, alerts.map((a) => h("tr", {}, h("td", {}, when(a.ts)), h("td", {}, a.requester), h("td", {}, h("a", { href: "#/request/" + (a.details || {}).request_id }, a.kind)), h("td", { class: "num" }, a.score.toFixed(2)), h("td", {}, h("span", { class: "pill " + (a.action_taken === "freeze" ? "bad" : "warn") }, a.action_taken))))))) : h("p", { class: "empty", style: "padding:0" }, "No alerts. Run the probe sequence from the Requests page to see one.")));
    body.replaceChildren(ledger);
  }
  await draw();
  const timer = setInterval(() => { if (!document.contains(root)) clearInterval(timer); else draw(); }, 4000);
  return root;
}

function requesterRow(r, redraw) {
  const tl = r.timeline || [];
  const pts = (k) => tl.map((e, i) => [i + 1, e[k] ?? 0]);
  const last = tl[tl.length - 1];
  const act = async (verb) => { await api(`/requesters/${r.id}/${verb}`, { method: "POST" }); window.dispatchEvent(new Event("gg:refresh-who")); redraw(); };
  return row(r.name, `${r.credential_level}, ${r.institution}`,
    h("p", { style: "margin:0 0 8px;display:flex;gap:10px;align-items:center;flex-wrap:wrap" },
      r.frozen ? h("span", { class: "pill bad" }, "frozen") : h("span", { class: "pill good" }, "active"),
      last ? h("span", { class: "muted" }, `${tl.length} queries, latest cohort ${last.cohort_n}, action ${last.action}`) : h("span", { class: "muted" }, "No queries yet"),
      r.frozen ? h("button", { class: "ghost", onclick: () => act("unfreeze") }, "Unfreeze") : h("button", { class: "ghost", onclick: () => act("freeze") }, "Freeze")),
    tl.length ? [lineChart({ series: [{ name: "score", color: "var(--ink)", points: pts("score") }, { name: "rate", color: "#2f6fe4", points: pts("rate"), dash: "4 3" }, { name: "similarity", color: "var(--glow)", points: pts("similarity"), dash: "2 3" }, { name: "differencing", color: "var(--deny)", points: pts("differencing") }],
      xLabel: "query number", yLabel: "score (0 to 1)", yMax: 1, hlines: TH, fmtX: (v) => Math.round(v), fmtY: (v) => v.toFixed(2), height: 230 }),
      legend([["total score", "var(--ink)"], ["query rate", "#2f6fe4"], ["near-duplicate similarity", "var(--glow)"], ["differencing guard", "var(--deny)"]])] : null);
}
