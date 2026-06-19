# openclaw-pipeline-bench Makefile
# Targets are designed so a fresh M5 Pro Claude session can run them in order.

SHELL := /bin/bash
TIMESTAMP := $(shell date -u +%Y%m%dT%H%M%SZ)
RESULTS_DIR := bench/results/$(TIMESTAMP)
VARIANTS := baseline sqlite-flat pipeline-noop pipeline-fullcopy pipeline-1-analyst pipeline-blocking

.PHONY: help install build bench-all clean smoke $(addprefix bench-,$(VARIANTS))

help:
	@echo "Targets:"
	@echo "  install              Verify OrbStack + Python + uv are present"
	@echo "  build                Build all 6 variant container images"
	@echo "  smoke                Run harness against in-memory SQLite for 10s (no docker)"
	@echo "  bench-<variant>      Run a single variant 3x, write to bench/results/<ts>/<variant>/"
	@echo "  bench-all            Run all 6 variants back-to-back + generate REPORT.md"
	@echo "  clean                Tear down docker compose + remove bench/results/"

install:
	@command -v orb >/dev/null  || (echo "OrbStack missing: brew install --cask orbstack" && exit 1)
	@command -v docker >/dev/null || (echo "Docker missing — start OrbStack first" && exit 1)
	@command -v python3.13 >/dev/null || (echo "Python 3.13 missing: brew install python@3.13" && exit 1)
	@command -v uv >/dev/null || (echo "uv missing: brew install uv" && exit 1)
	@echo "All required tools present."

build:
	docker compose build

smoke:
	cd bench && uv run --with psutil --with pyyaml python -m harness.runner --variant pipeline-noop --duration 10 --in-memory --manifest ../manifest/manifest.yaml

bench-baseline:
	@mkdir -p $(RESULTS_DIR)/baseline
	docker compose run --rm baseline --duration 360 --output $(RESULTS_DIR)/baseline/run-1.json
	docker compose run --rm baseline --duration 360 --output $(RESULTS_DIR)/baseline/run-2.json
	docker compose run --rm baseline --duration 360 --output $(RESULTS_DIR)/baseline/run-3.json

bench-sqlite-flat:
	@mkdir -p $(RESULTS_DIR)/sqlite-flat
	docker compose run --rm sqlite-flat --duration 360 --output $(RESULTS_DIR)/sqlite-flat/run-1.json
	docker compose run --rm sqlite-flat --duration 360 --output $(RESULTS_DIR)/sqlite-flat/run-2.json
	docker compose run --rm sqlite-flat --duration 360 --output $(RESULTS_DIR)/sqlite-flat/run-3.json

bench-pipeline-noop:
	@mkdir -p $(RESULTS_DIR)/pipeline-noop
	docker compose run --rm pipeline-noop --duration 360 --output $(RESULTS_DIR)/pipeline-noop/run-1.json
	docker compose run --rm pipeline-noop --duration 360 --output $(RESULTS_DIR)/pipeline-noop/run-2.json
	docker compose run --rm pipeline-noop --duration 360 --output $(RESULTS_DIR)/pipeline-noop/run-3.json

bench-pipeline-fullcopy:
	@mkdir -p $(RESULTS_DIR)/pipeline-fullcopy
	docker compose run --rm pipeline-fullcopy --duration 360 --output $(RESULTS_DIR)/pipeline-fullcopy/run-1.json
	docker compose run --rm pipeline-fullcopy --duration 360 --output $(RESULTS_DIR)/pipeline-fullcopy/run-2.json
	docker compose run --rm pipeline-fullcopy --duration 360 --output $(RESULTS_DIR)/pipeline-fullcopy/run-3.json

bench-pipeline-1-analyst:
	@mkdir -p $(RESULTS_DIR)/pipeline-1-analyst
	docker compose run --rm pipeline-1-analyst --duration 360 --output $(RESULTS_DIR)/pipeline-1-analyst/run-1.json
	docker compose run --rm pipeline-1-analyst --duration 360 --output $(RESULTS_DIR)/pipeline-1-analyst/run-2.json
	docker compose run --rm pipeline-1-analyst --duration 360 --output $(RESULTS_DIR)/pipeline-1-analyst/run-3.json

bench-pipeline-blocking:
	@mkdir -p $(RESULTS_DIR)/pipeline-blocking
	docker compose run --rm pipeline-blocking --duration 360 --output $(RESULTS_DIR)/pipeline-blocking/run-1.json
	docker compose run --rm pipeline-blocking --duration 360 --output $(RESULTS_DIR)/pipeline-blocking/run-2.json
	docker compose run --rm pipeline-blocking --duration 360 --output $(RESULTS_DIR)/pipeline-blocking/run-3.json

bench-all: build $(addprefix bench-,$(VARIANTS))
	uv run --with psutil --with pyyaml python scripts/generate_report.py $(RESULTS_DIR) > $(RESULTS_DIR)/REPORT.md
	@echo ""
	@echo "==============================================="
	@echo "Bench complete. Report: $(RESULTS_DIR)/REPORT.md"
	@echo "Write the headline paragraph by hand before sharing."
	@echo "==============================================="

clean:
	docker compose down -v 2>/dev/null || true
	rm -rf bench/results/*
	@echo "Cleaned."
