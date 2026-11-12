from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


def test_frontend_runtime_has_no_supabase_dependency():
    """Browser runtime must call only the first-party GenomeGuard API."""
    runtime_files = [
        *sorted((FRONTEND / "src").rglob("*.js")),
        FRONTEND / "index.html",
        FRONTEND / "vercel.json",
    ]
    forbidden = ("supabase.co", "SUPABASE_", "supabase-auth", "supabase-config",
                 "/functions/v1/", "/auth/v1/")
    violations = []
    for path in runtime_files:
        source = path.read_text(encoding="utf-8").lower()
        for marker in forbidden:
            if marker.lower() in source:
                violations.append(f"{path.relative_to(ROOT)} contains {marker}")
    assert not violations, "\n".join(violations)


def test_public_catalogue_uses_same_origin_api():
    source = (FRONTEND / "src" / "catalogue-api.js").read_text(encoding="utf-8")
    assert 'const path = `/catalogue/${resource}${query}`' in source
    assert 'fetch(path,' in source
    assert "https://" not in source
