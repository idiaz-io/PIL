.PHONY: help install test lint typecheck check parity record-golden clean

help:
	@echo "install       Create the virtualenv and install both packages"
	@echo "test          Run the test suite"
	@echo "lint          ruff check + format check"
	@echo "typecheck     mypy"
	@echo "check         lint + typecheck + test  (what CI runs)"
	@echo "parity        Compare PIL's translators against AXO's, over every fixture"
	@echo "record-golden Save AXO's current output as the specification (review the diff)"

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

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
