import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: corsHeaders });
}

Deno.serve(async (request: Request) => {
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders });
  if (request.method !== "GET") return json({ error: "method_not_allowed" }, 405);

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !serviceKey) {
    return json({ status: "not_ready", component: "supabase-edge-function", error: "server_configuration_missing" }, 503);
  }

  try {
    const response = await fetch(
      `${supabaseUrl.replace(/\/$/, "")}/rest/v1/genomeguard_deployment_status?id=eq.1&select=api_migration_complete,genomic_dataset_loaded,render_dependency_present,release_gate_passed,updated_at,notes`,
      {
        method: "GET",
        headers: {
          apikey: serviceKey,
          Authorization: `Bearer ${serviceKey}`,
          Accept: "application/json",
        },
        signal: AbortSignal.timeout(5000),
      },
    );

    if (!response.ok) {
      // Do not expose provider error bodies or credentials in a public health response.
      return json({ status: "not_ready", component: "supabase-edge-function", error: "status_store_unavailable" }, 503);
    }

    const rows = await response.json();
    if (!Array.isArray(rows) || rows.length !== 1) {
      return json({ status: "not_ready", component: "supabase-edge-function", error: "status_record_missing" }, 503);
    }

    const row = rows[0];
    const ready = row.release_gate_passed === true
      && row.api_migration_complete === true
      && row.genomic_dataset_loaded === true
      && row.render_dependency_present === false;

    return json({
      status: ready ? "ready" : "migration_incomplete",
      component: "supabase-edge-function",
      database_status_store: "reachable",
      api_migration_complete: row.api_migration_complete === true,
      genomic_dataset_loaded: row.genomic_dataset_loaded === true,
      render_dependency_present: row.render_dependency_present === true,
      release_gate_passed: row.release_gate_passed === true,
      updated_at: row.updated_at,
      note: "This endpoint reports migration status only. It does not claim GenomeGuard API parity or production readiness.",
    }, ready ? 200 : 503);
  } catch {
    return json({ status: "not_ready", component: "supabase-edge-function", error: "status_store_unreachable" }, 503);
  }
});
