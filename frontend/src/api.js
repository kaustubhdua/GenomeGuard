// Tiny API client. Credentials are deliberately kept in tab memory only.
// Never read or write API keys to localStorage, sessionStorage, URLs, or logs.
// Donors use their own X-Donor-Key and are also kept in memory only.

// Defer any remembered identity until the server confirms demo mode.
export const state = { who: "", adminKey: "", demo: null, health: null, readiness: null, bootError: "", me: null, donors: [], donor: null };

export const isSteward = () => state.who === "steward";

export function setWho(v) {
  state.who = v;
  // Clear credentials left by older builds; never persist the selected identity/key.
  try { localStorage.removeItem("gg_who"); } catch { /* storage can be blocked */ }
}

async function call(path, {
  method = "GET", body, rawBody, headers = {}, signal, timeoutMs = 30000,
} = {}) {
  const hd = { Accept: "application/json", ...headers };
  if (body !== undefined && rawBody !== undefined) {
    throw new TypeError("request cannot contain both JSON and raw bodies");
  }
  if (body !== undefined) hd["Content-Type"] = "application/json";
  let res;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const abort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  else signal?.addEventListener("abort", abort, { once: true });
  try {
    res = await fetch(path, {
      method, headers: hd,
      body: rawBody !== undefined ? rawBody : body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    const timedOut = error?.name === "AbortError";
    return { ok: false, status: 0, data: {
      error: signal?.aborted ? "cancelled" : timedOut ? "timeout" : "network",
      message: signal?.aborted
        ? "The upload was cancelled."
        : timedOut
        ? timeoutMs > 30000
          ? "The browser request timed out. Server-side QC may still be running; wait before retrying or use local processing."
          : "The API is taking longer than 30 seconds to respond. The service may be starting up; please retry."
        : "Cannot reach the GenomeGuard API. Check your connection and try again.",
    } };
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  return { ok: res.ok, status: res.status, data };
}

function authHeaders() {
  if (isSteward() && state.demo) return { "X-Admin-Key": state.demo.admin_key };
  if (isSteward() && state.adminKey) return { "X-Admin-Key": state.adminKey };
  if (state.who) return { "X-API-Key": state.who };
  return {};
}

// `opts.key` sends that requester key instead of the acting identity (the guided tour uses it).
export async function api(path, opts = {}) {
  const { key, ...rest } = opts;
  const headers = key ? { "X-API-Key": key } : authHeaders();
  return call(path, { ...rest, headers });
}

export function uploadVcfQc(file, assembly, expectedSha256, signal) {
  const headers = {
    ...authHeaders(),
    "Content-Type": "application/octet-stream",
    "X-Filename": encodeURIComponent(file.name),
    "X-Reference-Assembly": assembly,
  };
  if (expectedSha256) headers["X-Expected-Sha256"] = expectedSha256;
  return call("/admin/vcf-qc", {
    method: "POST", rawBody: file, headers, signal, timeoutMs: 30 * 60 * 1000,
  });
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
  // Every deployment uses the same first-party Python API. No hosted auth,
  // Edge Function, project URL, or browser publishable key is required.
  state.bootError = "";
  const [h, ready] = await Promise.all([
    call("/health"),
    call("/health/ready"),
  ]);
  state.health = h.data;
  if (!h.ok) state.bootError = h.data?.message || h.data?.error || "The GenomeGuard API is not responding.";
  state.readiness = ready.data || h.data?.readiness || { ready: false, checks: {} };
  state.demo = null;
  state.donors = [];
  if (!h.ok || !h.data?.demo_mode) {
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
  // Preserve an in-memory selection during this tab's lifetime, but never
  // restore credentials from browser storage after a reload.
  if (state.who === "steward" || reqs.some((r) => r.api_key === state.who)) return;
  if (!state.who) setWho(reqs.length ? reqs[0].api_key : "");
}
