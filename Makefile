.PHONY: help install test lint typecheck check parity clean

help:
	@echo "install    Create the virtualenv and install both packages"
	@echo "test       Run the test suite"
	@echo "lint       ruff check + format check"
	@echo "typecheck  mypy"
	@echo "check      lint + typecheck + test  (what CI runs)"
	@echo "parity     Compare PIL's translators against AXO's, over every fixture"

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

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
