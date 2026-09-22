.PHONY: help install test lint typecheck check parity record-golden neo4j-up neo4j-down neo4j-test clean

help:
	@echo "install       Create the virtualenv and install both packages"
	@echo "test          Run the test suite"
	@echo "lint          ruff check + format check"
	@echo "typecheck     mypy"
	@echo "check         lint + typecheck + test  (what CI runs)"
	@echo "parity        Compare PIL's translators against AXO's, over every fixture"
	@echo "record-golden Save AXO's current output as the specification (review the diff)"
	@echo "neo4j-up      Start a throwaway local Neo4j (docker-compose.neo4j.yml)"
	@echo "neo4j-down    Stop it and discard its data"
	@echo "neo4j-test    Run pil_graph's real-Neo4j integration tests against it"

install:
	uv sync --python 3.12

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy

check: lint typecheck test

# Proves the migration (§5 Step 3). Byte-identical or it fails.
# AXO_PATH must point at an AXO checkout; CI pins it to a known SHA.
AXO_PATH ?= ../axo

parity:
	uv run python scripts/parity.py --axo-path $(AXO_PATH)

# Defines the specification (§D6 step 2). Review the diff before committing: a change to
# a file that already existed means AXO's behaviour moved, which is a finding.
record-golden:
	uv run python scripts/parity.py --axo-path $(AXO_PATH) --record-golden

# A throwaway Neo4j for local dev/test only -- see docker-compose.neo4j.yml's own header
# for why (I-1: PIL is never deployed, this deploys nothing). Not wired into CI, which
# has no Neo4j; these targets are for a developer's laptop.
NEO4J_TEST_URI ?= bolt://localhost:7687
NEO4J_TEST_USER ?= neo4j
NEO4J_TEST_PASSWORD ?= testpassword

neo4j-up:
	docker compose -f docker-compose.neo4j.yml up -d --wait

neo4j-down:
	docker compose -f docker-compose.neo4j.yml down -v

neo4j-test:
	NEO4J_TEST_URI=$(NEO4J_TEST_URI) NEO4J_TEST_USER=$(NEO4J_TEST_USER) \
		NEO4J_TEST_PASSWORD=$(NEO4J_TEST_PASSWORD) \
		uv run --group graph-integration pytest tests/test_graph_neo4j_integration.py -v

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
