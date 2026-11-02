import { SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY } from "./supabase-config.js";
import { state, setSupabaseSession, clearSupabaseSession } from "./api.js";

async function authRequest(path, body, token = "") {
  try {
    const response = await fetch(SUPABASE_URL + "/auth/v1/" + path, {
      method: "POST",
      headers: {
        apikey: SUPABASE_PUBLISHABLE_KEY,
        "Content-Type": "application/json",
        ...(token ? { Authorization: "Bearer " + token } : {}),
      },
      body: JSON.stringify(body || {}),
    });
    let data = null;
    try { data = await response.json(); } catch { /* retain status */ }
    return { ok: response.ok, status: response.status, data };
  } catch {
    return { ok: false, status: 0, data: { message: "Cannot reach Supabase Auth. Check your connection and retry." } };
  }
}

export async function signIn(email, password) {
  const result = await authRequest("token?grant_type=password", { email, password });
  if (result.ok && result.data?.access_token) setSupabaseSession(result.data);
  return result;
}

export async function signUp(email, password, fullName) {
  const result = await authRequest("signup", {
    email, password,
    data: fullName ? { full_name: fullName } : {},
  });
  if (result.ok && result.data?.access_token) setSupabaseSession(result.data);
  return result;
}

export async function signOut() {
  if (state.authToken) await authRequest("logout", {}, state.authToken);
  clearSupabaseSession();
}
