# GroundLedger / SFA-Bench - one obvious entry path for a clean machine.
# Everything is stdlib-only: the targets work with no network and no install.
# `make setup` adds the optional `groundledger` CLI but is not required.

PY ?= python3

.PHONY: help setup test test-core demo verify verify-update verify-core preview clean

help:
	@echo "Targets:"
	@echo "  make setup        # optional: pip install -e . (adds the 'groundledger' CLI; stdlib-only, no deps)"
	@echo "  make test         # run the product test suite (unittest, no deps)"
	@echo "  make demo         # run the end-to-end product demo"
	@echo "  make verify       # reproducibility + tamper verification (the trust check)"
	@echo "  make test-core    # run the SFA-Bench research-core offline suite"
	@echo "  make verify-core  # research-core verify_all + release gate"
	@echo "  make preview      # open the sales landing page + one-pager"

setup:
	@$(PY) --version
	@$(PY) -m pip install -e . --no-build-isolation \
		&& echo "Installed. The 'groundledger' CLI is now on your PATH." \
		|| echo "Optional install skipped (no network / no pip). Everything still runs via 'python -m ...' and the make targets."

test:
	$(PY) -m unittest discover -s product -t . -p 'test_*.py'

test-core:
	$(PY) verify_all.py

demo:
	$(PY) -m product.demo

verify:
	$(PY) -m product.groundledger.verification

verify-update:
	$(PY) -m product.groundledger.verification --update

verify-core:
	$(PY) verify_all.py && $(PY) release_gate.py --ci

preview:
	./scripts/sales-preview.sh

clean:
	rm -rf product/data .verify-all-* **/__pycache__ */__pycache__ __pycache__
