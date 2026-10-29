import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
};
function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: cors });
}
function error(status: number, code: string, message: string): Response {
  return json({ error: code, message }, status);
}
function objectBody(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
async function readJsonLimited(request: Request, maxBytes: number): Promise<{ ok: true; value: unknown } | { ok: false; status: 400 | 413 }> {
  const declaredLength = Number(request.headers.get("content-length") || "0");
  if (Number.isFinite(declaredLength) && declaredLength > maxBytes) return { ok: false, status: 413 };
  if (!request.body) return { ok: false, status: 400 };
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) {
        await reader.cancel();
        return { ok: false, status: 413 };
      }
      chunks.push(value);
    }
  } catch {
    return { ok: false, status: 400 };
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return { ok: true, value: JSON.parse(new TextDecoder().decode(bytes)) };
  } catch {
    return { ok: false, status: 400 };
  }
}
async function authenticatedUser(request: Request, url: string, serviceKey: string) {
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ")) return null;
  const response = await fetch(`${url}/auth/v1/user`, {
    headers: { apikey: serviceKey, Authorization: authorization },
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) return null;
  const user = await response.json();
  if (!user?.id || typeof user.id !== "string") return null;
  return user as { id: string; email?: string; user_metadata?: Record<string, unknown> };
}
async function rpc(url: string, serviceKey: string, name: string, body: Record<string, unknown>) {
  const response = await fetch(`${url}/rest/v1/rpc/${name}`, {
    method: "POST",
    headers: { apikey: serviceKey, Authorization: `Bearer ${serviceKey}`,
      "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body), signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new Error(`database_rpc_failed_${response.status}`);
  return await response.json();
}
Deno.serve(async (request: Request) => {
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  const url = Deno.env.get("SUPABASE_URL")?.replace(/\/$/, "");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !serviceKey) return error(503, "server_configuration_missing", "The API is not configured.");
  const path = new URL(request.url).pathname.replace(/\/$/, "");
  if (path.endsWith("/chromosomes") && request.method === "GET") {
    try {
      const [chromosomes, coverage] = await Promise.all([
        rpc(url, serviceKey, "gg_list_chromosome_reference", {}),
        rpc(url, serviceKey, "gg_list_chromosome_coverage", {}),
      ]);
      const coverageByChromosome = new Map(
        (Array.isArray(coverage) ? coverage : []).map((row: Record<string, unknown>) => [
          String(row.chromosome), {
            variant_count: Number(row.variant_count ?? 0),
            first_position: row.first_position ?? null,
            last_position: row.last_position ?? null,
            variant_data_loaded: Number(row.variant_count ?? 0) > 0,
          },
        ]),
      );
      const rows = Array.isArray(chromosomes) ? chromosomes.map((row: Record<string, unknown>) => ({
        ...row,
        data_coverage: coverageByChromosome.get(String(row.chromosome)) ?? {
          variant_count: 0, first_position: null, last_position: null, variant_data_loaded: false,
        },
      })) : [];
      return json({
        reference_assembly: "GRCh38",
        chromosome_count: rows.length,
        chromosomes: rows,
        provenance_note: "GRCh38 chromosome reference metadata is catalogued separately from variant/genotype data. A chromosome is not available for analysis unless variant_data_loaded is true and its dataset provenance is verified.",
      });
    } catch {
      return error(503, "chromosome_catalog_unavailable", "Chromosome reference metadata could not be loaded.");
    }
  }
  if (path.endsWith("/datasets") && request.method === "GET") {
    try {
      const datasets = await rpc(url, serviceKey, "gg_list_verified_public_datasets", {});
      const rows = Array.isArray(datasets) ? datasets : [];
      return json({
        datasets: rows,
        dataset_count: rows.length,
        provenance_note: "Only datasets reviewed for public research and marked loaded with verified non-zero counts are listed. Dataset-level reuse review is not participant-specific consent or clinical authorization.",
      });
    } catch {
      return error(503, "dataset_catalog_unavailable", "The verified dataset catalogue could not be loaded.");
    }
  }
  if (path.endsWith("/health") && request.method === "GET") {
    try {
      const response = await fetch(`${url}/rest/v1/genomeguard_deployment_status?id=eq.1&select=api_migration_complete,genomic_dataset_loaded,render_dependency_present,release_gate_passed,updated_at`, {
        headers: { apikey: serviceKey, Authorization: `Bearer ${serviceKey}` },
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) return json({ status: "not_ready", component: "supabase-api", error: "status_store_unavailable" }, 503);
      const rows = await response.json();
      return json({ status: "ok", component: "supabase-api", database_status_store: "reachable",
        api_migration_complete: Array.isArray(rows) && rows[0]?.api_migration_complete === true,
        note: "Liveness only; this does not indicate release readiness or complete API parity." });
    } catch { return error(503, "status_store_unreachable", "The status store is unavailable."); }
  }
  if (path.endsWith("/health/ready") && request.method === "GET") {
    return json({ status: "not_ready", ready: false, backend: "supabase-edge-functions",
      checks: { request_storage_migrated: true, complete_policy_engine_ported: false,
        genomic_dataset_loaded: false, institutional_identity_reviewed: false,
        durable_backup_restore_verified: false, external_audit_anchor_verified: false,
        full_frontend_route_parity: false },
      note: "Fail-closed migration gate. No genomic data access is granted by this API yet." }, 503);
  }
  if (path.endsWith("/requests") && request.method === "GET") {
    const user = await authenticatedUser(request, url, serviceKey);
    if (!user) return error(401, "unauthorized", "Sign in with your Supabase account first.");
    try {
      return json({ requests: await rpc(url, serviceKey, "gg_list_my_requests", { p_auth_user_id: user.id }) });
    } catch { return error(503, "database_unavailable", "Requests could not be loaded. Try again later."); }
  }
  if (path.endsWith("/requests") && request.method === "POST") {
    const user = await authenticatedUser(request, url, serviceKey);
    if (!user) return error(401, "unauthorized", "Sign in with your Supabase account first.");
    const parsed = await readJsonLimited(request, 16_384);
    if (!parsed.ok) return error(parsed.status, parsed.status === 413 ? "payload_too_large" : "bad_json",
      parsed.status === 413 ? "Request payload exceeds 16 KB." : "Send a valid JSON object.");
    const body = parsed.value;
    if (!objectBody(body)) return error(400, "bad_json", "Send a valid JSON object.");
    const purpose = typeof body.purpose === "string" ? body.purpose.trim() : "";
    const name = typeof body.name === "string" ? body.name.trim() : "";
    const institution = typeof body.institution === "string" ? body.institution.trim() : "";
    const level = typeof body.data_level === "string" ? body.data_level : "aggregate";
    const disease = typeof body.disease === "string" ? body.disease.trim() : "";
    if (purpose.length < 3 || purpose.length > 500 || name.length < 2 || name.length > 120 ||
        institution.length < 2 || institution.length > 200 ||
        !["aggregate", "frequency", "variant", "individual"].includes(level)) {
      return error(422, "invalid_request", "Check purpose, name, institution, and data level.");
    }
    try {
      const result = await rpc(url, serviceKey, "gg_submit_request", {
        p_auth_user_id: user.id, p_name: name, p_institution: institution, p_purpose: purpose,
        p_disease: disease || null, p_is_commercial: body.is_commercial === true,
        p_data_level: level, p_cohort_filter: objectBody(body.cohort_filter) ? body.cohort_filter : {},
        p_variant_filter: objectBody(body.variant_filter) ? body.variant_filter : {},
      });
      return json(result, 201);
    } catch { return error(503, "request_storage_failed", "The request could not be saved. No access was granted."); }
  }
  return error(404, "not_found", "This route has not been migrated to the Supabase backend yet.");
});
