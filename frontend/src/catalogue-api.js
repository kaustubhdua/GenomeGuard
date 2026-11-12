// Public catalogues are served by the first-party GenomeGuard API.
// Successful responses are shared briefly within this tab; failed responses are never cached.
const CACHE_TTL_MS = 20_000;
const MAX_RETRIES = 2;
const catalogueCache = new Map();
const inFlight = new Map();

function retryDelay(response, attempt) {
  const header = response.headers.get("Retry-After");
  if (header) {
    const seconds = Number(header);
    const until = Number.isFinite(seconds)
      ? seconds * 1000
      : Math.max(0, Date.parse(header) - Date.now());
    // Do not retry earlier than the server asks. If its requested wait is too
    // long for an interactive page, surface the 429 and let the user retry.
    return Number.isFinite(until) && until >= 0 && until <= 8_000 ? until : null;
  }
  return Math.min(400 * (2 ** attempt), 1_600);
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function loadPublicCatalogue(resource, options = {}) {
  if (!["datasets", "chromosomes", "sources"].includes(resource)) {
    throw new TypeError("Unsupported public catalogue resource");
  }
  const assembly = resource === "chromosomes" && ["GRCh37", "GRCh38"].includes(options.assembly)
    ? options.assembly : "GRCh38";
  const query = resource === "chromosomes" ? `?assembly=${encodeURIComponent(assembly)}` : "";
  const path = `/catalogue/${resource}${query}`;
  const cached = catalogueCache.get(path);
  if (!options.force && cached && cached.expiresAt > Date.now()) return cached.value;
  if (!options.force && inFlight.has(path)) return inFlight.get(path);

  const request = (async () => {
    let result = { ok: false, status: 0, data: null };
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt += 1) {
      try {
        const response = await fetch(path, {
          method: "GET",
          headers: { Accept: "application/json" },
          cache: "no-store",
          signal: AbortSignal.timeout(10_000),
        });
        let data = null;
        try { data = await response.json(); } catch { /* preserve gateway status */ }
        result = { ok: response.ok, status: response.status, data };
        if (response.ok) {
          catalogueCache.set(path, { value: result, expiresAt: Date.now() + CACHE_TTL_MS });
          return result;
        }
        if (![429, 502, 503, 504].includes(response.status) || attempt === MAX_RETRIES) {
          return result;
        }
        const delay = retryDelay(response, attempt);
        if (delay === null) return result;
        await wait(delay);
      } catch {
        result = { ok: false, status: 0, data: null };
        if (attempt === MAX_RETRIES) return result;
        await wait(Math.min(300 * (2 ** attempt), 900));
      }
    }
    return result;
  })();

  inFlight.set(path, request);
  try {
    return await request;
  } finally {
    if (inFlight.get(path) === request) inFlight.delete(path);
  }
}
