# Entry points. Everything below runs from a clean checkout with no arguments.

VENV := .venv
PY   := $(VENV)/bin/python

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "  make install    virtualenv and dependencies"
	@echo "  make test       the full suite (14 extra tests if .env has Razorpay keys)"
	@echo "  make demo       all six demo scenarios"
	@echo "  make demo-groq  the same demo, with Groq breaking the substitution tie"
	@echo "  make eval       the corpus, DEV and TEST"
	@echo "  make money      what Custodian saves, and what it costs"
	@echo "  make sweep      the threshold curve"
	@echo "  make pitch      preflight for recording: server, live order, both pages"
	@echo "  make serve      the API and decision viewer on :8000"
	@echo "  make review     lay out the 30 drafted labels for human review"
	@echo "  make record     record real model responses (needs GROQ_API_KEY)"
	@echo "  make check      what CI runs"

$(VENV):
	python3 -m venv $(VENV)

.PHONY: install
install: $(VENV)
	$(VENV)/bin/pip install -q -e ".[dev]"

.PHONY: test
test:
	@# No -q here: pyproject's addopts already carries one, and a second makes
	@# pytest quiet enough to swallow the "N passed" line — so `make test`
	@# printed a coverage table and never said how many tests ran.
	@set -a; [ -f .env ] && . ./.env; set +a; $(VENV)/bin/pytest --cov=custodian --cov-report=term

.PHONY: demo
demo:
	@set -a; [ -f .env ] && . ./.env; set +a; $(PY) scripts/demo.py

.PHONY: demo-groq
demo-groq:
	@set -a; [ -f .env ] && . ./.env; set +a; $(PY) scripts/demo.py --scorer groq

.PHONY: eval
eval:
	@$(PY) -m eval.harness --split DEV
	@$(PY) -m eval.harness --split TEST
	@$(PY) -m eval.counterfactual

.PHONY: money
money:
	@$(PY) -m eval.counterfactual

.PHONY: sweep
sweep:
	@$(PY) -m eval.sweep --split ALL --csv docs/sweep.csv

# Everything between a cold machine and "press record": server on the live
# gateway, a real order so the checkout page and payable link work, both
# surfaces open, and the run sheet printed.
.PHONY: pitch
pitch:
	@bash scripts/pitch.sh

.PHONY: serve
serve:
	@echo "http://127.0.0.1:8000  ·  /docs for the API  ·  / for decisions"
	@$(VENV)/bin/uvicorn custodian.api.app:app --reload

.PHONY: review
review:
	@$(PY) -m eval.corpus.review --sheet
	@echo "read eval/corpus/REVIEW.md, then:"
	@echo "  $(PY) -m eval.corpus.review --apply --as you@example.com"

.PHONY: record
record:
	@set -a; [ -f .env ] && . ./.env; set +a; $(PY) scripts/record_fixtures.py --provider groq

.PHONY: record-dry
record-dry:
	@$(PY) scripts/record_fixtures.py --dry-run

.PHONY: corpus
corpus:
	@$(PY) -m eval.corpus.build

# Everything CI runs, in the order CI runs it. If this passes and the build is
# red, one of the two is lying — which is exactly how BROKE.md 014 happened.
.PHONY: check
check: test
	@$(PY) -m eval.harness --all
	@$(PY) -m eval.sweep --split ALL > /dev/null && echo "sweep: runs clean"
	@$(PY) -m eval.counterfactual > /dev/null && echo "counterfactual: runs clean"
	@$(PY) scripts/demo.py > /dev/null && echo "demo: runs clean"
	@$(PY) -m eval.corpus.build --check
