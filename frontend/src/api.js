// Tiny API client. The "acting as" choice picks which header is sent:
// a researcher's X-API-Key, or the steward's X-Admin-Key. Demo keys come from /demo/requesters.
export const state = { who: localStorage.getItem("gg_who") || "", demo: null, health: null, me: null };

export const isSteward = () => state.who === "steward";

export function setWho(v) {
  state.who = v;
  try { localStorage.setItem("gg_who", v); } catch { /* storage can be blocked */ }
}

export async function api(path, { method = "GET", body } = {}) {
  const headers = { Accept: "application/json" };
  if (isSteward() && state.demo) headers["X-Admin-Key"] = state.demo.admin_key;
  else if (state.who) headers["X-API-Key"] = state.who;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    return { ok: false, status: 0, data: { error: "network", message: "Cannot reach the GenomeGuard API." } };
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  return { ok: res.ok, status: res.status, data };
}

export async function boot() {
  const [h, d] = await Promise.all([api("/health"), api("/demo/requesters")]);
  state.health = h.data;
  state.demo = d.ok ? d.data : null;
  const reqs = state.demo ? state.demo.requesters : [];
  if (!state.who || (state.who !== "steward" && !reqs.some((r) => r.api_key === state.who))) {
    setWho(reqs.length ? reqs[0].api_key : "");
  }
}
