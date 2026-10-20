PY ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: setup seed run test eval eval-smoke demo lint

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

seed:
	$(PY) -m app.data.seed

run:
	$(PY) -m uvicorn app.main:app --app-dir backend --reload --port 8000

test:
	$(PY) -m pytest -q

lint:
	.venv/bin/ruff check backend

eval:
	PYTHONPATH=backend $(PY) -m redteam.run_eval

eval-smoke:
	PYTHONPATH=backend $(PY) -m redteam.run_eval --quick

demo:
	@echo "demo: implemented in step 12 (scripted demo scenario)"
