# Okane developer commands. Works with GNU make on macOS/Linux and in Git Bash on Windows
# (use `mingw32-make` or `make` from Git for Windows / MSYS2).

PYTHON ?= python
VENV := backend/.venv
ifeq ($(OS),Windows_NT)
  BIN := $(VENV)/Scripts
else
  BIN := $(VENV)/bin
endif
PY := $(BIN)/python
NPM ?= npm

.PHONY: help setup dev dev-api dev-web ollama-check test lint fixtures generate-sample-data \
        types build serve clean

help:
	@echo "setup                 create backend venv, install deps, copy sample rates, npm install"
	@echo "generate-sample-data  write synthetic workbooks to data/sample/"
	@echo "dev                   API on :8000 + Vite on :5173 (checks Ollama on :11434)"
	@echo "test | lint           pytest + ruff | ruff + frontend typecheck"
	@echo "fixtures              export synthetic JSON fixtures to fixtures/"
	@echo "types                 regenerate frontend API types from the OpenAPI schema"
	@echo "build | serve         build frontend | serve API + built frontend on :8000"

setup:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e "backend[dev]"
	@test -f data/rates.csv || (cp backend/tests/data/rates.sample.csv data/rates.csv && echo "copied sample rates to data/rates.csv")
	cd frontend && $(NPM) install

generate-sample-data:
	$(PY) scripts/generate_sample_data.py --out data/sample

ollama-check:
	@curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1 \
	  && echo "Ollama is running on :11434" \
	  || echo "WARNING: Ollama not reachable on :11434; AI comments fall back to the labelled template."

dev-api:
	cd backend && ../$(PY) -m uvicorn app.main:app --reload --port 8000

dev-web:
	cd frontend && $(NPM) run dev

dev: ollama-check
	$(MAKE) -j2 dev-api dev-web

test:
	cd backend && ../$(PY) -m pytest

lint:
	cd backend && ../$(PY) -m ruff check . && ../$(PY) -m ruff format --check .
	cd frontend && $(NPM) run typecheck

fixtures:
	cd backend && ../$(PY) -m app.services.fixtures

types:
	cd backend && ../$(PY) -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))" > ../frontend/src/api/openapi.json
	cd frontend && npx openapi-typescript src/api/openapi.json -o src/api/schema.d.ts

build:
	cd frontend && $(NPM) run build

serve: build
	cd backend && OKANE_ENABLE_WATCHER=true ../$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000

clean:
	rm -rf frontend/dist backend/.pytest_cache backend/.ruff_cache
