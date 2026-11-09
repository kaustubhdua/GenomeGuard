from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_staging_image_is_synthetic_only_and_does_not_embed_real_cohort():
    dockerfile = (ROOT / "Dockerfile.staging").read_text(encoding="utf-8")
    lowered = dockerfile.lower()

    assert "app.data.real build" not in lowered
    assert "data_real" not in lowered
    assert "1000g" not in lowered
    assert "gg_dataset_id=synthetic-cohort-1" in lowered
    assert "gg_real_cohort_file" not in lowered
    assert "useradd -m app" in lowered


def test_render_staging_blueprint_uses_synthetic_only_image():
    blueprint = (ROOT / "render.staging.yaml").read_text(encoding="utf-8")
    assert "dockerfilePath: ./Dockerfile.staging" in blueprint
    assert 'value: "true"' in blueprint
    assert "GG_DEMO_MODE" in blueprint
