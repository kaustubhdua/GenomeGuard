// Tiny API client. The "acting as" choice picks which header is sent:
// a researcher's X-API-Key, or the steward's X-Admin-Key. Demo keys come from /demo/requesters.
// Donors use their own X-Donor-Key (kept in memory only, never in storage).
function readStorage(key) {
  try { return localStorage.getItem(key) || ""; }
  catch { return ""; } // storage can be blocked by browser privacy settings
}

// Defer any remembered identity until the server confirms demo mode.
export const state = { who: "", adminKey: "", demo: null, health: null, readiness: null, me: null, donors: [], donor: null };

export const isSteward = () => state.who === "steward";

export function setWho(v) {
  state.who = v;
  // Demo personas are convenient for the public demo. Real credentials must stay in memory only.
  try {
    if (state.demo) localStorage.setItem("gg_who", v);
    else localStorage.removeItem("gg_who");
  } catch { /* storage can be blocked */ }
}

async function call(path, { method = "GET", body, headers = {} } = {}) {
  const hd = { Accept: "application/json", ...headers };
  if (body !== undefined) hd["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(path, { method, headers: hd, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    return { ok: false, status: 0, data: { error: "network", message: "Cannot reach the GenomeGuard API." } };
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  return { ok: res.ok, status: res.status, data };
}

// `opts.key` sends that requester key instead of the "acting as" choice (the guided tour uses it).
export function api(path, opts = {}) {
  const headers = {};
  if (opts.key) headers["X-API-Key"] = opts.key;
  else if (isSteward() && state.demo) headers["X-Admin-Key"] = state.demo.admin_key;
  else if (isSteward() && state.adminKey) headers["X-Admin-Key"] = state.adminKey;
  else if (state.who) headers["X-API-Key"] = state.who;
  const { key, ...rest } = opts; // eslint-disable-line no-unused-vars
  return call(path, { ...rest, headers });
}

// steward-level call regardless of who the app is acting as (admin key from the demo accounts)
export function stewardApi(path, opts = {}) {
  const headers = state.demo ? { "X-Admin-Key": state.demo.admin_key } :
    state.adminKey ? { "X-Admin-Key": state.adminKey } : {};
  return call(path, { ...opts, headers });
}

// patient-side calls: authenticated with the chosen donor's own key
export function donorApi(path, opts = {}) {
  const d = state.donor;
  return call(path, { ...opts, headers: d ? { "X-Donor-Key": d.key } : {} });
}

export async function connectKey(kind, key) {
  const result = kind === "steward"
    ? await call("/anomalies", { headers: { "X-Admin-Key": key } })
    : await call("/me", { headers: { "X-API-Key": key } });
  if (!result.ok) return result;
  if (kind === "steward") {
    state.adminKey = key;
    setWho("steward");
  } else {
    state.adminKey = "";
    setWho(key);
  }
  return result;
}

export function disconnectKey() {
  state.adminKey = "";
  setWho("");
}

export async function boot() {
  const h = await call("/health");
  state.health = h.data;
  state.readiness = null;
  state.demo = null;
  state.donors = [];
  if (!h.ok || !h.data?.demo_mode) {
    const readiness = await call("/health/ready");
    state.readiness = readiness.data || { ready: false, checks: {} };
    // Never call demo-only endpoints or reuse a demo key in real-data mode.
    state.who = "";
    state.adminKey = "";
    try { localStorage.removeItem("gg_who"); } catch { /* storage can be blocked */ }
    state.donor = null;
    return;
  }
  const [d, dn] = await Promise.all([call("/demo/requesters"), call("/demo/donors")]);
  state.demo = d.ok ? d.data : null;
  state.donors = dn.ok ? dn.data.donors : [];
  if (!state.demo) {
    state.who = "";
    state.adminKey = "";
    try { localStorage.removeItem("gg_who"); } catch { /* storage can be blocked */ }
    state.donor = null;
    return;
  }
  if (!state.donor && state.donors.length) state.donor = state.donors[0];
  const reqs = state.demo.requesters || [];
  const remembered = readStorage("gg_who");
  if (remembered === "steward" || reqs.some((r) => r.api_key === remembered)) {
    setWho(remembered);
  } else {
    setWho(reqs.length ? reqs[0].api_key : "");
  }
}
