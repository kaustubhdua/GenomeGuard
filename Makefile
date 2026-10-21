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

# Scripted 3-minute scenario. Starts a throwaway server on a fresh database, runs the checks.
demo:
	rm -f /tmp/gg-demo.sqlite3
	GG_DB_PATH=/tmp/gg-demo.sqlite3 GG_ALLOW_TAMPER_DEMO=true PYTHONPATH=backend \
		$(PY) -m uvicorn app.main:app --port 8765 > /tmp/gg-demo.log 2>&1 & echo $$! > /tmp/gg-demo.pid
	sleep 8
	$(PY) scripts/demo.py --base http://127.0.0.1:8765; code=$$?; kill `cat /tmp/gg-demo.pid`; exit $$code
