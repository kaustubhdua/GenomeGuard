import base64
import json

from tests.helpers import (
    ADMIN,
    ATTACKER,
    DEMO_REQ,
    RESEARCHER,
    H,
    attack_queries,
    make_client,
)


def test_health_and_docs_and_openapi():
    svc, c = make_client()
    h = c.get("/health").json()
    assert h["synthetic_data_only"] is True and h["audit_chain_ok"] is None
    assert c.get("/audit/verify").json()["ok"] is True
    assert h["provenance"]["genotypes"] == "synthetic" and h["provenance"]["consent"] == "simulated"
    assert h["participant_consent_records_verified"] is False
    assert h["participant_consent_records_matched"] == 0
    assert c.get("/docs").status_code == 200
    eps = c.get("/openapi.json").json()["endpoints"]
    assert {"POST /requests", "GET /audit/verify"} <= {f"{e['method']} {e['path']}" for e in eps}


def test_host_liveness_probe_does_not_initialize_service(monkeypatch):
    from starlette.testclient import TestClient

    import app.api as api_module

    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    def fail_bootstrap(*args, **kwargs):
        raise AssertionError("liveness must not bootstrap the database or cohort")

    monkeypatch.setattr(api_module, "bootstrap", fail_bootstrap)
    client = TestClient(api_module.create_app())
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "deployment": {
        "platform": None, "git_commit": None,
    }}


def test_health_reports_render_deployment_commit_without_exposing_other_environment(monkeypatch):
    from starlette.testclient import TestClient

    import app.api as api_module

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "a" * 40)
    monkeypatch.setenv("RENDER_GIT_BRANCH", "main")
    monkeypatch.setenv("GG_ADMIN_API_KEY", "must-not-be-returned")
    service, _ = make_client()
    response = TestClient(api_module.create_app(service)).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["deployment"] == {"platform": "render", "git_commit": "a" * 40}
    assert "must-not-be-returned" not in response.text


def test_host_liveness_reports_render_commit_without_bootstrapping(monkeypatch):
    from starlette.testclient import TestClient

    import app.api as api_module

    commit = "b" * 40
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_GIT_COMMIT", commit)
    def fail_bootstrap(*args, **kwargs):
        raise AssertionError("liveness must not bootstrap the database or cohort")

    monkeypatch.setattr(api_module, "bootstrap", fail_bootstrap)
    response = TestClient(api_module.create_app()).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "deployment": {"platform": "render", "git_commit": commit},
    }


def test_health_omits_invalid_render_commit(monkeypatch):
    from starlette.testclient import TestClient

    import app.api as api_module

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "not-a-commit")
    service, _ = make_client()
    body = TestClient(api_module.create_app(service)).get("/health").json()
    assert body["deployment"] == {"platform": "render", "git_commit": None}


def test_readiness_distinguishes_demo_liveness_from_production_readiness():
    svc, c = make_client()
    live = c.get("/health")
    assert live.status_code == 200 and live.json()["status"] == "ok"
    ready = c.get("/health/ready")
    assert ready.status_code == 503
    body = ready.json()
    assert body["status"] == "not_ready" and body["ready"] is False
    assert live.json()["readiness"]["ready"] is False
    assert live.json()["readiness"]["checks"] == body["checks"]
    assert body["checks"]["demo_mode_disabled"] is False
    assert body["checks"]["participant_consent_records_verified"] is False
    assert body["checks"]["durable_storage_verified"] is False
    assert body["checks"]["external_audit_anchor_verified"] is False
    assert body["checks"]["institutional_identity_provider_verified"] is False


def test_auth_required():
    svc, c = make_client()
    assert c.post("/requests", json=DEMO_REQ).status_code == 401
    assert c.post("/requests", json=DEMO_REQ, headers=H("nope")).status_code == 401
    assert c.get("/audit").status_code == 401
    assert c.get("/audit", headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert c.get("/anomalies").status_code == 401


def test_submit_and_read_back_own_request_only():
    svc, c = make_client()
    r = c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER))
    assert r.status_code == 201 and r.json()["outcome"] == "permit_with_transform"
    rid = r.json()["id"]
    assert c.get(f"/requests/{rid}", headers=H(RESEARCHER)).json()["id"] == rid
    assert c.get(f"/requests/{rid}", headers=H(ATTACKER)).status_code == 404
    assert c.get("/requests/999999", headers=H(ATTACKER)).status_code == 404
    assert c.get("/requests/999999").status_code == 401
    assert c.get(f"/requests/{rid}", headers=ADMIN).status_code == 200
    mine = c.get("/requests", headers=H(RESEARCHER)).json()["requests"]
    assert len(mine) == 1 and "release" not in mine[0]
    assert c.get("/requests", headers=H(ATTACKER)).json()["requests"] == []
    assert len(c.get("/requests", headers=ADMIN).json()["requests"]) == 1


def test_bad_inputs_are_422_or_400():
    svc, c = make_client()
    assert c.post("/requests", json={"purpose": "x"}, headers=H(RESEARCHER)).status_code == 422
    r = c.post("/requests", content=b"not json", headers=H(RESEARCHER))
    assert r.status_code == 400
    assert c.post("/requests", json=[1], headers=H(RESEARCHER)).status_code == 400


def test_consent_summary_returns_counts_only():
    svc, c = make_client()
    j = c.get("/consent/summary?purpose=disease_research&disease=diabetes",
              headers=H(RESEARCHER)).json()
    assert set(j) == {"eligible", "considered", "excluded_by_reason"} and j["eligible"] > 0


def test_frozen_account_gets_403_with_reason_and_admin_can_unfreeze():
    svc, c = make_client()
    codes = [c.post("/requests", json=q, headers=H(ATTACKER)).status_code
             for q in attack_queries(5)]
    assert codes[:4] == [201, 201, 201, 201] and codes[4] == 403
    r = c.post("/requests", json=attack_queries(1)[0], headers=H(ATTACKER))
    assert r.json()["error"] == "requester_frozen"
    an = c.get("/anomalies", headers=ADMIN).json()
    att = next(x for x in an["requesters"] if x["name"] == "Probe Account")
    assert att["frozen"] and att["timeline"] and an["alerts"]
    uid = att["id"]
    assert c.post(f"/requesters/{uid}/unfreeze").status_code == 401
    assert c.post(f"/requesters/{uid}/unfreeze", headers=ADMIN).status_code == 200
    assert c.post("/requests", json=attack_queries(1)[0], headers=H(ATTACKER)).status_code == 201


def test_review_endpoint_requires_admin_and_works():
    svc, c = make_client()

    def assert_store_lock_released(stage):
        # TestClient dispatches sync handlers through AnyIO worker threads. A lock
        # accidentally retained by a completed request deadlocks the next admin call.
        assert not svc.store.lock._is_owned(), (
            f"test thread already owns store lock after {stage}: {svc.store.lock!r}"
        )
        acquired = svc.store.lock.acquire(blocking=False)
        assert acquired, f"store lock leaked after {stage}: {svc.store.lock!r}"
        svc.store.lock.release()

    req = {"purpose": "general_research", "data_level": "record",
           "variant_filter": {"min_maf": 0.2, "limit": 5}}
    d = c.post("/requests", json=req, headers=H("demo-controlled")).json()
    assert d["needs_human"]
    assert_store_lock_released("request submission")
    assert c.post(f"/requests/{d['id']}/review", json={"approve": True}).status_code == 401
    assert_store_lock_released("unauthorized review")
    # Strings such as "false" must never be coerced to truthy approval.
    invalid = c.post(f"/requests/{d['id']}/review", json={"approve": "false"}, headers=ADMIN)
    assert invalid.status_code == 422 and invalid.json()["error"] == "invalid_review"
    assert_store_lock_released("invalid review")
    out = c.post(f"/requests/{d['id']}/review", json={"approve": True, "reviewer": "carol"},
                 headers=ADMIN).json()
    assert out["status"] == "approved_pending_release" and out["reviewed_by"] == "carol"
    assert not out.get("release")
    assert c.post(f"/requests/{d['id']}/release", json={"reviewer": "carol"},
                  headers=ADMIN).status_code == 200
    released = c.get(f"/requests/{d['id']}", headers=ADMIN).json()
    assert released["status"] == "released" and released["release"]["level"] != "record"
    assert c.post(f"/requests/{d['id']}/review", json={"approve": True},
                  headers=ADMIN).status_code == 409


def test_steward_can_request_information_without_releasing():
    _, c = make_client()
    request = {"purpose": "general_research", "data_level": "record",
               "variant_filter": {"min_maf": 0.2, "limit": 5}}
    submitted = c.post("/requests", json=request, headers=H("demo-controlled")).json()
    response = c.post(
        f"/requests/{submitted['id']}/review",
        json={"action": "request_information", "reviewer": "steward"},
        headers=ADMIN,
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "needs_information"
    assert result["reviewed_by"] == "steward"
    assert result["needs_human"] is False
    assert not result.get("release")
    assert c.post(f"/requests/{submitted['id']}/release", json={}, headers=ADMIN).status_code == 409


def test_release_is_separately_gated_when_active_data_is_not_linked():
    svc, c = make_client()
    request = {"purpose": "general_research", "data_level": "record",
               "variant_filter": {"min_maf": 0.2, "limit": 5}}
    submitted = c.post("/requests", json=request, headers=H("demo-controlled")).json()
    approved = c.post(
        f"/requests/{submitted['id']}/review", json={"approve": True}, headers=ADMIN,
    )
    assert approved.json()["status"] == "approved_pending_release"
    svc.release_enabled = False
    released = c.post(
        f"/requests/{submitted['id']}/release", json={}, headers=ADMIN,
    )
    assert released.status_code == 503
    assert released.json()["error"] == "governed_release_unavailable"
    assert c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER)).status_code == 503


def test_audit_endpoints_and_tamper_demo_over_http():
    svc, c = make_client(allow_tamper_demo=True)
    c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER))
    head = c.get("/audit/head").json()
    assert len(head["head_hash"]) == 64 and head["length"] >= 8
    assert c.get("/audit/verify").json()["ok"] is True
    ok_anchor = c.get(f"/audit/verify?anchor_length={head['length']}&anchor_hash="
                      f"{head['head_hash']}").json()
    assert ok_anchor["ok"] is True
    view = c.get("/audit", headers=ADMIN).json()
    assert view["entries"][0]["idx"] == head["length"] and view["verify"]["ok"]
    checkpoint = c.get("/audit/checkpoint").json()
    assert c.post("/audit/verify-checkpoint", json=checkpoint).json()["valid"] is True
    assert c.post("/admin/tamper/4").status_code == 401
    bad = c.post("/admin/tamper/4", headers=ADMIN).json()
    assert bad["ok"] is False and bad["first_broken_index"] == 4
    assert c.get("/audit/verify").json()["first_broken_index"] == 4
    assert c.get(f"/audit/verify?anchor_length={head['length']}&anchor_hash={head['head_hash']}"
                 ).json()["ok"] is False
    assert c.get("/audit/verify?anchor_length=not-a-number&anchor_hash=" + "0" * 64).status_code == 400
    assert c.get("/audit/verify?anchor_length=0").status_code == 400
    assert c.get("/audit/verify?anchor_length=-1&anchor_hash=" + "0" * 64).status_code == 400
    assert c.get("/audit/verify?anchor_length=0&anchor_hash=bad").status_code == 400
    assert c.get("/audit/checkpoint?signer=" + "x" * 129).status_code == 400
    malformed = dict(checkpoint, length="not-an-integer")
    assert c.post("/audit/verify-checkpoint", json=malformed).json() == {
        "valid": False, "reason": "malformed_checkpoint"
    }


def test_tamper_endpoint_403_when_disabled():
    svc, c = make_client()
    c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER))
    assert c.post("/admin/tamper/1", headers=ADMIN).status_code == 403


def test_exposure_and_report_endpoints():
    svc, c = make_client()
    d = c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER)).json()
    g = c.get(f"/requests/{d['id']}/exposure", headers=ADMIN).json()
    assert "SIMULATED" in g["model"]
    # the exposure graph describes withheld variants and registry relatives: steward-only
    assert c.get(f"/requests/{d['id']}/exposure", headers=H(RESEARCHER)).status_code == 401
    rep = c.get("/reports/compliance", headers=ADMIN).json()
    assert rep["facts"]["requests"] == 1 and rep["report"]
    assert c.get("/reports/compliance").status_code == 401


def test_production_admin_provisions_a_one_time_requester_key(monkeypatch):
    from starlette.testclient import TestClient

    from app.api import create_app
    from tests.helpers import make_service

    admin_key = "production-admin-secret-that-is-long-enough-123456"
    master_key = base64.b64encode(b"m" * 32).decode()
    svc = make_service(admin_api_key=admin_key)
    monkeypatch.setenv("GG_DEMO_MODE", "false")
    monkeypatch.setenv("GG_DATABASE_URL", "postgresql://test.invalid/genomeguard")
    monkeypatch.setenv("GG_ALLOW_TAMPER_DEMO", "false")
    monkeypatch.setenv("GG_ADMIN_API_KEY", admin_key)
    monkeypatch.setenv("GG_MASTER_KEY", master_key)
    monkeypatch.setenv("GG_REAL_COHORT_FILE", "/secure/authorized-cohort.npz")
    monkeypatch.setenv("GG_DATASET_ID", "approved-cohort-2026-01")
    client = TestClient(create_app(svc))

    assert client.get("/demo/requesters").status_code == 404
    for path in ("/demo/donors", "/donor/1", "/federated/demo", "/federated/he",
                 "/eval/results", "/admin/tamper/1", "/admin/untamper"):
        if path in ("/admin/tamper/1", "/admin/untamper"):
            response = client.post(path, headers={"X-Admin-Key": admin_key})
        else:
            response = client.get(path)
        assert response.status_code == 404, path
    docs = client.get("/openapi.json").json()
    documented_paths = {item["path"] for item in docs["endpoints"]}
    assert not any(path.startswith(("/demo/", "/donor/", "/federated/")) for path in documented_paths)
    assert "/eval/results" not in documented_paths
    assert client.post("/admin/requesters", json={"name": "Researcher One",
                                                   "institution": "Research Institute"}).status_code == 401
    response = client.post("/admin/requesters", headers={"X-Admin-Key": admin_key},
                           json={"name": "Researcher One", "institution": "Research Institute",
                                 "credential_level": "registered"})
    assert response.status_code == 201
    payload = response.json()
    assert payload["shown_once"] is True and len(payload["api_key"]) >= 40
    assert svc.authenticate(payload["api_key"])["id"] == payload["id"]
    assert payload["api_key"] not in str(svc.audit.entries())
    bad = client.post("/admin/requesters", headers={"X-Admin-Key": admin_key},
                      json={"name": "Bad Level", "institution": "Research Institute",
                            "credential_level": "anonymous"})
    assert bad.status_code == 422


def test_demo_accounts_endpoint_only_in_demo_mode(monkeypatch):
    monkeypatch.setenv("GG_EXPOSE_DEMO_ADMIN_KEY", "true")
    svc, c = make_client()
    j = c.get("/demo/requesters").json()
    assert {r["tier"] for r in j["requesters"]} == {"registered", "anonymous", "controlled"}
    assert j["admin_key"] == "demo-admin-key"


def test_public_demo_accounts_never_disclose_custom_admin_credential(monkeypatch):
    secret = "staging-admin-secret-that-must-never-be-public-123456"
    monkeypatch.setenv("GG_ADMIN_API_KEY", secret)
    _, client = make_client()
    response = client.get("/demo/requesters")
    assert response.status_code == 200
    assert "admin_key" not in response.json()
    assert secret not in response.text


def test_public_demo_accounts_can_only_disclose_explicit_local_demo_key(monkeypatch):
    secret = "local-only-demo-secret-12345678901234567890"
    monkeypatch.setenv("GG_ADMIN_API_KEY", secret)
    monkeypatch.setenv("GG_EXPOSE_DEMO_ADMIN_KEY", "true")
    _, client = make_client()
    response = client.get("/demo/requesters")
    assert response.status_code == 200
    assert response.json()["admin_key"] == secret


def test_no_response_ever_leaks_genotype_like_data():
    svc, c = make_client()
    texts = [c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER)).text,
             c.get("/requests", headers=ADMIN).text, c.get("/audit", headers=ADMIN).text,
             c.get("/anomalies", headers=ADMIN).text, c.get("/me", headers=H(RESEARCHER)).text]
    for t in texts:
        assert "genotype_blob" not in t and "consent_json" not in t and "donor_ids" not in t


def test_researcher_never_sees_carrier_counts_relatives_or_detector_scores():
    svc, c = make_client()
    d = c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER)).json()
    admin_view = c.get(f"/requests/{d['id']}", headers=ADMIN).json()
    # sanity: the sensitive fields exist server-side and the admin can see them
    assert admin_view["risk"]["before"]["min_carriers"] is not None
    assert admin_view["risk"]["before"]["relatives_exposed"]["total"] > 0
    assert "anomaly" in admin_view["transform"]["agent_notes"]
    for body in (d, c.get(f"/requests/{d['id']}", headers=H(RESEARCHER)).json(),
                 c.get("/requests", headers=H(RESEARCHER)).json()["requests"][0]):
        text = json.dumps(body)
        for forbidden in ("min_carriers", "carrier_families", "relatives_exposed",
                          "relatives_exposed_total", "Simulated model", "Behaviour score"):
            assert forbidden not in text, forbidden
        assert body["risk"]["consent"]["eligible"] > 0  # what they may know is still there
        assert body["risk"]["before"]["band"] == "high"


def test_he_endpoint_public_and_correct():
    svc, c = make_client()
    r = c.get("/federated/he")
    assert r.status_code == 200 and r.json()["matches_plaintext"] is True
    assert r.json()["aggregator_saw"]["plaintexts"] == "none"


def test_untamper_repeats_the_demo_but_cannot_repair_real_edits():
    svc, c = make_client(allow_tamper_demo=True)
    c.post("/requests", json=DEMO_REQ, headers=H(RESEARCHER))
    assert c.post("/admin/untamper").status_code == 401
    c.post("/admin/tamper/2", headers=ADMIN)
    assert c.get("/audit/verify").json()["ok"] is False
    fixed = c.post("/admin/untamper", headers=ADMIN).json()
    assert fixed["ok"] is True and fixed["markers_removed"] == 1
    # a genuine edit (not our marker) must stay detected
    rows = svc.audit.store.all()
    svc.audit.store.replace_payload(3, {**rows[2]["payload"], "changed": 1})
    assert c.post("/admin/untamper", headers=ADMIN).json()["ok"] is False
    assert c.get("/audit/verify").json()["first_broken_index"] == 3


def test_untamper_403_when_disabled():
    svc, c = make_client()
    assert c.post("/admin/untamper", headers=ADMIN).status_code == 403


def test_checkpoint_and_compliance_export_endpoints():
    svc, c = make_client()
    cp_resp = c.get("/audit/checkpoint?signer=test-signer")
    assert cp_resp.status_code == 200
    cp = cp_resp.json()
    assert cp["signed_by"] == "test-signer"
    assert "checkpoint_digest" in cp

    verify_resp = c.post("/audit/verify-checkpoint", json=cp)
    assert verify_resp.status_code == 200
    assert verify_resp.json()["valid"] is True

    unauth = c.get("/reports/compliance/export")
    assert unauth.status_code == 401

    auth_resp = c.get("/reports/compliance/export", headers=ADMIN)
    assert auth_resp.status_code == 200
    pack = auth_resp.json()
    assert pack["evidence_package_version"] == "1.0"
    assert "dpdp_india" in pack["regulatory_evidence"]
    assert "gdpr_art9" in pack["regulatory_evidence"]
    assert "hipaa" in pack["regulatory_evidence"]
    assert pack["audit_checkpoint"]["length"] >= cp["length"]

def test_catalogue_endpoints():
    svc, c = make_client()
    resp = c.get("/catalogue/datasets")
    assert resp.status_code == 200
    data = resp.json()
    assert "datasets" in data
    assert "dataset_count" in data
    # Synthetic fixtures are not source-reviewed imports and must not be presented
    # as verified research datasets or measured imported individuals.
    assert data["dataset_count"] == 0
    assert data["datasets"] == []

    c_resp = c.get("/catalogue/chromosomes?assembly=GRCh38")
    assert c_resp.status_code == 200
    c_data = c_resp.json()
    assert c_data["reference_assembly"] == "GRCh38"
    assert c_data["chromosome_count"] == 25
    assert c_data["coverage_available"] is True
    chr22 = next(ch for ch in c_data["chromosomes"] if ch["chromosome"] == "22")
    assert chr22["data_coverage"]["variant_data_loaded"] is False
    assert chr22["data_coverage"]["variant_count"] == 0

    # In-memory cohort coordinates are not evidence of a normalized public import.
    svc.provenance["reference_assembly"] = "GRCh37"
    matching = c.get("/catalogue/chromosomes?assembly=GRCh37").json()
    chr22_matching = next(ch for ch in matching["chromosomes"] if ch["chromosome"] == "22")
    assert chr22_matching["data_coverage"]["variant_data_loaded"] is False
    assert chr22_matching["data_coverage"]["variant_count"] == 0
    mismatched = c.get("/catalogue/chromosomes?assembly=GRCh38").json()
    chr22_mismatched = next(ch for ch in mismatched["chromosomes"] if ch["chromosome"] == "22")
    assert chr22_mismatched["data_coverage"]["variant_data_loaded"] is False

    bad = c.get("/catalogue/chromosomes?assembly=invalid")
    assert bad.status_code == 400


def test_chromosome_reference_lengths_remain_available_when_coverage_query_fails(monkeypatch):
    from app.store import CatalogueUnavailableError

    svc, client = make_client()

    def unavailable(_assembly):
        raise CatalogueUnavailableError("simulated reference-store outage")

    monkeypatch.setattr(svc.store, "verified_public_chromosome_coverage", unavailable)
    response = client.get("/catalogue/chromosomes?assembly=GRCh38")
    assert response.status_code == 200
    data = response.json()
    assert data["chromosome_count"] == 25
    assert data["coverage_available"] is False
    assert "no dataset coverage is asserted" in data["provenance_note"]
    assert all(row["data_coverage"]["coverage_status"] == "unavailable"
               for row in data["chromosomes"])
    assert all(row["data_coverage"]["variant_data_loaded"] is False
               for row in data["chromosomes"])


def test_public_source_catalogue_is_discovery_only_and_keeps_review_boundaries():
    _, c = make_client()
    response = c.get("/catalogue/sources")
    assert response.status_code == 200
    data = response.json()
    assert data["discovery_only"] is True
    assert data["source_count"] == len(data["sources"]) == 3
    assert "do not establish reuse authorization" in data["provenance_note"]

    sources = {source["source_id"]: source for source in data["sources"]}
    assert set(sources) == {
        "igsr-1000-genomes-phase-3",
        "gnomad-v4-1-grch38",
        "ncbi-clinvar-variant-summary",
    }
    for source in sources.values():
        assert source["source_url"].startswith("https://")
        assert source["terms_url"].startswith("https://")
        assert source["terms_review_status"] == "pending_exact_artifact_review"
        assert source["import_status"] == "not_imported_by_catalogue"
        assert source["lifecycle_status"] == {
            "discovered": "complete",
            "metadata_registered": "complete",
            "downloaded": "not_started",
            "checksum_verified": "not_started",
            "qc_validated": "not_started",
            "steward_approved": "pending",
            "imported": "not_imported",
            "available_for_research": "not_available",
        }

    sources["igsr-1000-genomes-phase-3"]["lifecycle_status"]["downloaded"] = "complete"
    assert c.get("/catalogue/sources").json()["sources"][0]["lifecycle_status"]["downloaded"] == "not_started"

    assert "sample-level" in sources["igsr-1000-genomes-phase-3"]["data_type"].casefold()
    assert "Aggregate" in sources["gnomad-v4-1-grch38"]["data_type"]
    assert "participant genotype cohort" in sources["ncbi-clinvar-variant-summary"]["summary"]
    assert "GET /catalogue/sources" in {
        f"{endpoint['method']} {endpoint['path']}"
        for endpoint in c.get("/openapi.json").json()["endpoints"]
    }


def test_preview_is_non_consuming_and_returns_only_risk_utility_summary():
    svc, c = make_client()
    before_budget = svc.budget(svc.authenticate(RESEARCHER)["id"])
    before_audit = svc.audit.head()
    preview = c.post("/requests/preview", json=DEMO_REQ, headers=H(RESEARCHER))
    assert preview.status_code == 200
    data = preview.json()
    assert data["outcome"] in ("permit", "permit_with_transform", "deny", "escalate")
    assert data["variants_requested"] > 0
    assert "risk_before" in data and "risk_after" in data
    assert "release" not in data and "donor_ids" not in str(data)
    assert svc.budget(svc.authenticate(RESEARCHER)["id"]) == before_budget
    assert svc.audit.head() == before_audit
    assert c.get("/requests", headers=H(RESEARCHER)).json()["requests"] == []


def test_variant_inspector_and_steward_qc_are_metadata_only_and_authorized():
    svc, c = make_client()
    assert c.get("/admin/dataset-qc").status_code == 401
    qc = c.get("/admin/dataset-qc", headers=ADMIN)
    assert qc.status_code == 200
    q = qc.json()
    assert q["sample_count"] == svc.ds.n_donors
    assert q["variant_count"] == svc.ds.n_variants
    assert "genotypes" not in str(q).lower()
    variant = c.get("/variants/search?q=v1")
    assert variant.status_code == 200
    data = variant.json()
    assert len(data["matches"]) == 1
    assert data["matches"][0]["variant_id"] == 1
    assert "maf" not in str(data).lower()
    assert "donor" not in str(data).lower()


def test_steward_vcf_qc_upload_is_bounded_temporary_and_omits_sample_ids(monkeypatch, tmp_path):
    import hashlib

    import app.api as api_module

    _, client = make_client()
    content = (
        "##fileformat=VCFv4.2\n"
        "##reference=GRCh38\n"
        "##contig=<ID=1,length=248956422>\n"
        "##INFO=<ID=DP,Number=1,Type=Integer,Description=\"Read depth\">\n"
        "##FILTER=<ID=PASS,Description=\"All filters passed\">\n"
        "##FORMAT=<ID=GT,Number=1,Type=String,Description=\"Genotype\">\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tPRIVATE_SAMPLE\n"
        "1\t100\t.\tA\tG\t42\tPASS\t.\tGT\t0/1\n"
    )
    content_bytes = content.encode()
    headers = {
        **ADMIN,
        "Content-Type": "application/octet-stream",
        "X-Filename": "C:\\private\\PRIVATE_SAMPLE.vcf",
        "X-Reference-Assembly": "GRCh38",
        "X-Expected-Sha256": hashlib.sha256(content_bytes).hexdigest(),
    }

    assert client.post("/admin/vcf-qc", content=content, headers={
        key: value for key, value in headers.items() if key != "X-Admin-Key"
    }).status_code == 401
    response = client.post("/admin/vcf-qc", content=content, headers=headers)
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "PASSED"
    assert report["import_eligibility"] == "NOT_ESTABLISHED"
    assert report["file"]["name"] == "[uploaded VCF]"
    assert report["file"]["sha256"] == hashlib.sha256(content_bytes).hexdigest()
    assert report["statistics"]["split_variant_count"] == 1
    assert "PRIVATE_SAMPLE" not in json.dumps(report)

    monkeypatch.setattr(api_module, "MAX_UPLOAD_BYTES", 8)
    too_large = client.post("/admin/vcf-qc", content=b"x" * 9, headers={
        **ADMIN, "Content-Type": "application/octet-stream",
        "X-Filename": "large.vcf", "X-Reference-Assembly": "GRCh38",
    })
    assert too_large.status_code == 413
    assert too_large.json()["error"] == "file_too_large"

    wrong_type = client.post("/admin/vcf-qc", content=b"xx", headers={
        **ADMIN, "Content-Type": "application/octet-stream",
        "X-Filename": "sample.vcf.gz", "X-Reference-Assembly": "GRCh38",
    })
    assert wrong_type.status_code == 400
    assert wrong_type.json()["error"] == "file_type_mismatch"
