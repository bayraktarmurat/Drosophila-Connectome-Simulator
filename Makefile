# Connectome Circuit Explorer: common tasks. Run `make help`.

PYTHON ?= python3.14
VENV := .venv
PY := $(VENV)/bin/python
CONFIG ?= giant_fiber

.PHONY: help install fetch layout dev test lint format sanity

help:
	@echo "make install          create .venv (Python 3.14) and install backend + frontend deps"
	@echo "make fetch CONFIG=x   fetch circuit x from neuPrint (needs the token) and compute its layout"
	@echo "make layout CONFIG=x  recompute the cached graph layout only"
	@echo "make dev              run backend (:8000) and frontend (:5173) together"
	@echo "make test             run the backend test suite"
	@echo "make lint             ruff + oxlint + prettier/tsc checks"
	@echo "make format           auto-format Python and TypeScript"
	@echo "make sanity           re-run the Phase 5 science checks (a few minutes)"

$(PY):
	$(PYTHON) -m venv $(VENV)

install: $(PY)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev,fetch]"
	npm --prefix frontend install

fetch: $(PY)
	$(PY) scripts/fetch_circuit.py --config $(CONFIG)
	$(PY) scripts/compute_layout.py --config $(CONFIG)

layout: $(PY)
	$(PY) scripts/compute_layout.py --config $(CONFIG)

dev:
	./scripts/dev.sh

test: $(PY)
	$(PY) -m pytest

lint: $(PY)
	$(VENV)/bin/ruff check backend scripts
	$(VENV)/bin/ruff format --check backend scripts
	npm --prefix frontend run lint
	npm --prefix frontend run format:check
	cd frontend && npx tsc -b

format: $(PY)
	$(VENV)/bin/ruff format backend scripts
	$(VENV)/bin/ruff check --fix backend scripts
	npm --prefix frontend run format

sanity: $(PY)
	$(PY) scripts/sanity_checks.py
