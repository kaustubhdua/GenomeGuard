// Public catalogue endpoints served by the local GenomeGuard backend.
// Previously called Supabase Edge Functions with a hardcoded publishable key.
// Now calls the same Python backend that serves all other pages — zero external dependencies.

export async function loadPublicCatalogue(resource, options = {}) {
  if (!["datasets", "chromosomes"].includes(resource)) {
    throw new TypeError("Unsupported public catalogue resource");
  }
  const assembly = resource === "chromosomes" && ["GRCh37", "GRCh38"].includes(options.assembly)
    ? options.assembly : "GRCh38";
  const query = resource === "chromosomes" ? `?assembly=${encodeURIComponent(assembly)}` : "";
  const path = `/catalogue/${resource}${query}`;
  try {
    const response = await fetch(path, {
      method: "GET",
      headers: { Accept: "application/json" },
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
