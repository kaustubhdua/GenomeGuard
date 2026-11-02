// Public catalogue endpoints are served by the Supabase Edge Function. These routes are
// read-only and expose no participant-level records or privileged database credentials.
import { SUPABASE_EDGE_API, SUPABASE_PUBLISHABLE_KEY } from "./supabase-config.js";

export async function loadPublicCatalogue(resource, options = {}) {
  if (!["datasets", "chromosomes", "sources"].includes(resource)) {
    throw new TypeError("Unsupported public catalogue resource");
  }
  const assembly = resource === "chromosomes" && ["GRCh37", "GRCh38"].includes(options.assembly)
    ? options.assembly : "GRCh38";
  const query = resource === "chromosomes" ? `?assembly=${encodeURIComponent(assembly)}` : "";
  const path = `${SUPABASE_EDGE_API}/${resource}${query}`;
  try {
    const response = await fetch(path, {
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
