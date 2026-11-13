// Tiny API client. Credentials are deliberately kept in tab memory only.
// Never read or write API keys to localStorage, sessionStorage, URLs, or logs.
// Synthetic demo personas use short-lived session headers; tokens stay in tab memory only.
import { beginOidcLogin, completeOidcCallback } from "./oidc.js";

// Defer any remembered identity until the server confirms demo mode.
export const state = {
  who: "", adminKey: "", demoSession: "", demo: null, health: null, readiness: null, bootError: "",
  me: null, donors: [], donor: null, oidc: null, oidcError: "", accessToken: "",
};

export const isSteward = () => state.who === "steward"
  || ["reviewer", "steward", "admin"].includes(state.me?.role);

export function setWho(v) {
  state.who = v;
  state.demoSession = "";
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
  if (state.accessToken) return { Authorization: "Bearer " + state.accessToken };
  if (state.demoSession) return { "X-Demo-Session": state.demoSession };
  if (isSteward()) {
    if (state.demo?.admin_key) return { "X-Admin-Key": state.demo.admin_key };
    if (state.adminKey) return { "X-Admin-Key": state.adminKey };
    return {};
  }
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
  const headers = state.accessToken ? { Authorization: "Bearer " + state.accessToken } :
    state.demo?.admin_key ? { "X-Admin-Key": state.demo.admin_key } :
    state.adminKey ? { "X-Admin-Key": state.adminKey } : {};
  return call(path, { ...opts, headers });
}

// patient-side calls: authenticated with the chosen donor's own key
export function donorApi(path, opts = {}) {
  const d = state.donor;
  return call(path, { ...opts, headers: d?.session_token ? { "X-Demo-Donor-Session": d.session_token } : {} });
}

export async function selectDemoRequester(requesterId) {
  const id = Number(requesterId);
  if (!Number.isSafeInteger(id) || id < 1) {
    return { ok: false, status: 400, data: { message: "Choose a valid demo persona." } };
  }
  const result = await call("/demo/session", { method: "POST", body: { requester_id: id } });
  if (!result.ok || !result.data?.session_token) return result;
  setWho(String(id));
  state.demoSession = result.data.session_token;
  state.me = result.data.requester || null;
  return result;
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
  state.demoSession = "";
  state.accessToken = "";
  state.me = null;
  setWho("");
}

export async function signInWithInstitution() {
  state.oidcError = "";
  try {
    await beginOidcLogin(state.oidc);
  } catch (error) {
    state.oidcError = error?.message || "Institutional sign-in could not start.";
    throw error;
  }
}

export function signOutInstitution() {
  state.accessToken = "";
  state.me = null;
  state.oidcError = "";
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
  if (!h.ok) return;
  if (!h.data?.demo_mode) {
    // Production uses institutional OIDC; demo personas and API keys are never reused.
    state.who = "";
    state.adminKey = "";
    state.demoSession = "";
    state.donor = null;
    try { localStorage.removeItem("gg_who"); } catch { /* storage can be blocked */ }
    const config = await call("/auth/oidc");
    state.oidc = config.ok ? config.data : null;
    if (!state.oidc?.enabled) {
      state.accessToken = "";
      state.me = null;
      return;
    }
    try {
      const token = await completeOidcCallback(state.oidc);
      if (token) state.accessToken = token;
      if (state.accessToken) {
        const profile = await call("/me", {
          headers: { Authorization: "Bearer " + state.accessToken },
        });
        if (profile.ok) {
          state.me = profile.data;
          state.oidcError = "";
        } else {
          state.accessToken = "";
          state.me = null;
          state.oidcError = profile.data?.message || "Your institutional session is not authorized.";
        }
      }
    } catch (error) {
      state.accessToken = "";
      state.me = null;
      state.oidcError = error?.message || "Institutional sign-in failed.";
    }
    return;
  }
  state.oidc = null;
  state.oidcError = "";
  state.accessToken = "";
  state.me = null;
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
  if (state.donors.length) {
    const donor = state.donors[0];
    const session = await call("/demo/donor-session", {
      method: "POST", body: { donor_id: donor.id },
    });
    state.donor = session.ok && session.data?.session_token
      ? { ...donor, session_token: session.data.session_token } : null;
    if (!state.donor) {
      state.bootError = session.data?.message || "Could not initialize the synthetic participant session.";
      return;
    }
  } else {
    state.donor = null;
  }
  const reqs = state.demo.requesters || [];
  // Persona discovery contains no credentials. Issue a short-lived session for the
  // first synthetic researcher; changing personas issues a new scoped session.
  if (reqs.length) {
    const desired = reqs.find((r) => String(r.id) === String(state.who)) || reqs[0];
    const selected = await selectDemoRequester(desired.id);
    if (!selected.ok) {
      state.bootError = selected.data?.message || "Could not initialize the synthetic researcher session.";
      state.who = "";
      state.demoSession = "";
      return;
    }
  } else {
    state.who = "";
    state.demoSession = "";
    state.bootError = "No synthetic demo personas are available.";
  }
}
