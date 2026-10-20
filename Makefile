PY ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: setup seed run test eval demo lint

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

seed:
	@echo "seed: implemented in step 2 (synthetic data + pedigree)"

run:
	$(PY) -m uvicorn app.main:app --app-dir backend --reload --port 8000

test:
	$(PY) -m pytest -q

lint:
	.venv/bin/ruff check backend

eval:
	@echo "eval: implemented in step 10 (red-team harness)"

demo:
	@echo "demo: implemented in step 12 (scripted demo scenario)"
