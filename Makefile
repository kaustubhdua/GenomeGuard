PY ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: setup seed run test eval eval-smoke demo lint fetch-real real-trios eval-real fetch-duo federated bench ui-smoke deploy-smoke

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

seed:
	PYTHONPATH=backend $(PY) -m app.data.seed

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

# --- real open data (run on YOUR machine; needs internet). See backend/app/data/real.py ---
fetch-real:
	PYTHONPATH=backend $(PY) -m app.data.real build --out data_real/1000g_chr22.npz
	@echo "now: GG_REAL_COHORT_FILE=data_real/1000g_chr22.npz make seed && make run"

# Real FAMILIES: build from the high-coverage 1000 Genomes release (602 trios). Download one
# chromosome's phased VCF and the 3,202-sample pedigree yourself (see docs/real-data.md), then:
#   make real-trios VCF=path/to/chr22.vcf.gz PED=path/to/pedigree.txt
real-trios:
	@test -n "$(VCF)" -a -n "$(PED)" || (echo "usage: make real-trios VCF=<vcf.gz> PED=<pedigree>"; exit 2)
	PYTHONPATH=backend $(PY) -m app.data.real build --vcf $(VCF) --ped $(PED) --out data_real/1000g_trios.npz
	@echo "now: GG_REAL_COHORT_FILE=data_real/1000g_trios.npz GG_DB_PATH=data_real/gg.sqlite3 make run"

# Red-team evaluation on a real cohort file: make eval-real COHORT=data_real/1000g_trios.npz
eval-real:
	@test -n "$(COHORT)" || (echo "usage: make eval-real COHORT=<cohort.npz>"; exit 2)
	PYTHONPATH=backend $(PY) -m redteam.run_eval --cohort $(COHORT)

bench:
	PYTHONPATH=backend $(PY) scripts/bench.py

fetch-duo:
	PYTHONPATH=backend $(PY) -m app.data.duo

federated:
	PYTHONPATH=backend $(PY) -m app.core.federated

# Read-only checks against an already deployed synthetic demo; never prints demo keys.
deploy-smoke:
	@test -n "$(URL)" || (echo "usage: make deploy-smoke URL=https://your-service.onrender.com"; exit 2)
	$(PY) scripts/deploy_smoke.py --base $(URL)

# Drives the real UI in a headless browser (needs: pip install playwright && playwright install chromium)
ui-smoke:
	rm -f /tmp/gg-ui-smoke.sqlite3
	GG_DB_PATH=/tmp/gg-ui-smoke.sqlite3 GG_ALLOW_TAMPER_DEMO=true PYTHONPATH=backend \
		$(PY) -m uvicorn app.main:app --port 8767 > /tmp/gg-ui-smoke.log 2>&1 & echo $$! > /tmp/gg-ui-smoke.pid
	sleep 8
	@set -e; trap 'kill `cat /tmp/gg-ui-smoke.pid`' EXIT; \
		$(PY) scripts/deploy_smoke.py --base http://127.0.0.1:8767; \
		$(PY) scripts/ui_smoke.py --base http://127.0.0.1:8767
