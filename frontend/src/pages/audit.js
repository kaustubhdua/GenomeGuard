import { api, isSteward, state } from "../api.js";
import { h, row, notice, errorText, copy } from "../ui.js";

const ANCHOR = "gg_anchor";
const getAnchor = () => { try { return JSON.parse(localStorage.getItem(ANCHOR) || "null"); } catch { return null; } };

export async function render() {
  const root = h("div", {});
  root.dataset.title = "Audit log";
  root.append(h("h1", {}, "Audit log"),
    h("p", { class: "lede" }, "Every request, decision, protection, alert and agent note is chained to the entry before it. Changing any past entry breaks the chain at that entry."));
  if (!isSteward()) { root.append(notice("warn", "The full log is for stewards. Anyone can still check that it is intact: "), h("p", {}, h("a", { href: "/audit/verify" }, "Verify the chain"), " · ", h("a", { href: "/audit/head" }, "Current head hash"))); return root; }
  const body = h("div", {});
  root.append(body);
  async function draw() {
    const a = getAnchor();
    const res = await api("/audit?limit=300");
    if (!res.ok) { body.replaceChildren(notice("err", errorText(res))); return; }
    const vq = a ? `?anchor_length=${a.length}&anchor_hash=${a.head_hash}` : "";
    const v = (await api("/audit/verify" + vq)).data || res.data.verify;
    const { head, entries } = res.data;
    const chrono = entries.slice().reverse();
    const bad = v.first_broken_index;
    let win = chrono.slice(-12);
    if (bad != null) { const i = chrono.findIndex((e) => e.idx === bad); win = chrono.slice(Math.max(0, i - 5), i + 7); }
    const strip = h("div", { class: "chain", role: "img", tabindex: "0", "aria-label": bad != null ? `Chain broken at entry ${bad}` : "Chain intact" });
    win.forEach((e, i) => {
      const isBad = e.idx === bad;
      if (i) strip.append(h("div", { class: "link-glyph" + (isBad ? " bad" : "") }));
      strip.append(h("div", { class: "blk" + (isBad ? " bad" : "") }, h("b", {}, "#" + e.idx), e.action, h("span", { class: "mono", title: e.hash }, "hash " + e.hash.slice(0, 12)), h("span", { class: "mono", title: e.prev_hash }, "prev " + e.prev_hash.slice(0, 12))));
    });
    const status = v.ok ? h("div", { class: "status ok" }, "Chain valid", h("span", { style: "font:14px var(--sans)" }, `${v.length} entries`))
      : h("div", { class: "status bad", role: "alert" }, bad != null ? `Broken at entry ${bad}` : "Anchor mismatch", h("span", { style: "font:14px var(--sans)" }, v.reason || ""));
    const copyBtn = h("button", { class: "ghost", onclick: (e) => copy(head.head_hash, e.target) }, "Copy hash");
    const anchorBtn = h("button", { class: "ghost", onclick: () => { try { localStorage.setItem(ANCHOR, JSON.stringify(head)); } catch {} draw(); } }, a ? "Replace saved anchor" : "Save as my anchor");
    const tIn = h("input", { type: "number", min: 1, max: head.length, value: Math.min(3, head.length), "aria-label": "Entry number", style: "width:90px" });
    const tamper = state.health && state.health.tamper_demo ? h("div", { style: "display:flex;gap:8px;align-items:center;margin-top:10px;flex-wrap:wrap" },
      h("button", { class: "danger", onclick: async () => { const r = await api("/admin/tamper/" + tIn.value, { method: "POST" }); if (!r.ok) body.prepend(notice("err", errorText(r))); else draw(); } }, "Tamper with entry"), tIn,
      h("button", { class: "ghost", onclick: async () => { const r = await api("/admin/untamper", { method: "POST" }); if (!r.ok) body.prepend(notice("err", errorText(r))); else draw(); } }, "Undo demo tamper"),
      h("span", { class: "muted" }, "Demo only. Undo removes just the demo marker, so the demo can be repeated; any other change to an entry stays detected.")) : null;
    const ledger = h("div", { class: "ledger" },
      row("Status", "Recomputed on every view", status, a ? h("p", { class: "muted" }, `Also checked against your saved anchor (${a.length} entries): ${v.ok ? "matches" : "does not match"}.`) : null,
        h("div", { style: "margin-top:10px" }, h("button", { class: "ghost", onclick: draw }, "Verify now"))),
      row("Head hash", `${head.length} entries`, h("code", { class: "hash" }, head.head_hash), h("div", { style: "display:flex;gap:8px;margin-top:8px;flex-wrap:wrap" }, copyBtn, anchorBtn),
        h("p", { class: "muted" }, "Copy this somewhere outside the system, such as the README or a slide. Someone with full database access could rewrite every hash, but not the copy you hold. The chain makes tampering detectable, not impossible.")),
      row("The chain", bad != null ? "Red block = first broken entry" : "Latest entries, oldest at the left", strip, tamper),
      row("Entries", "Newest first, click to expand", h("div", {}, entries.map((e) => h("details", { class: "entry" }, h("summary", {}, h("b", {}, "#" + e.idx), h("span", {}, `${e.action} `, h("span", { class: "muted" }, e.actor)), h("span", { class: "muted mono" }, e.ts.slice(11, 19))), h("pre", {}, JSON.stringify(e.payload, null, 2)))))));
    body.replaceChildren(ledger);
  }
  await draw();
  return root;
}
