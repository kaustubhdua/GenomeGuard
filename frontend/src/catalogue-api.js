// Public, read-only catalogue calls. The Supabase publishable key is intended for browser
// use; it is not a service-role secret. Governed API routes still require a verified user token.
const SUPABASE_URL = "https://hkyieaovolkethovyenb.supabase.co";
const SUPABASE_PUBLISHABLE_KEY = "sb_publishable_ZnV6zbGRzisNWOblNLgmYg_czCO4GXL";

export async function loadPublicCatalogue(resource, options = {}) {
  if (!["datasets", "chromosomes"].includes(resource)) {
    throw new TypeError("Unsupported public catalogue resource");
  }
  const assembly = resource === "chromosomes" && ["GRCh37", "GRCh38"].includes(options.assembly)
    ? options.assembly : "GRCh38";
  const query = resource === "chromosomes" ? `?assembly=${encodeURIComponent(assembly)}` : "";
  try {
    const response = await fetch(`${SUPABASE_URL}/functions/v1/genomeguard-api/${resource}${query}`, {
      method: "GET",
      headers: { Accept: "application/json", apikey: SUPABASE_PUBLISHABLE_KEY },
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    let data = null;
    try { data = await response.json(); } catch { /* non-JSON gateway errors remain unavailable */ }
    return { ok: response.ok, status: response.status, data };
  } catch {
    return { ok: false, status: 0, data: null };
  }
}