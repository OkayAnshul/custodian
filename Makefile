# Entry points. Everything below runs from a clean checkout with no arguments.

VENV := .venv
PY   := $(VENV)/bin/python

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "  make install    virtualenv and dependencies"
	@echo "  make test       the full suite (12 extra tests if .env has Razorpay keys)"
	@echo "  make demo       all six demo scenarios"
	@echo "  make eval       the corpus, DEV and TEST"
	@echo "  make sweep      the threshold curve"
	@echo "  make serve      the API and decision viewer on :8000"
	@echo "  make review     lay out the 30 drafted labels for human review"
	@echo "  make check      what CI runs"

$(VENV):
	python3 -m venv $(VENV)

.PHONY: install
install: $(VENV)
	$(VENV)/bin/pip install -q -e ".[dev]"

.PHONY: test
test:
	@set -a; [ -f .env ] && . ./.env; set +a; $(VENV)/bin/pytest -q --cov=custodian --cov-report=term

.PHONY: demo
demo:
	@set -a; [ -f .env ] && . ./.env; set +a; $(PY) scripts/demo.py

.PHONY: eval
eval:
	@$(PY) -m eval.harness --split DEV
	@$(PY) -m eval.harness --split TEST

.PHONY: sweep
sweep:
	@$(PY) -m eval.sweep --split ALL --csv docs/sweep.csv

.PHONY: serve
serve:
	@echo "http://127.0.0.1:8000  ·  /docs for the API  ·  / for decisions"
	@$(VENV)/bin/uvicorn custodian.api.app:app --reload

.PHONY: review
review:
	@$(PY) -m eval.corpus.review --sheet
	@echo "read eval/corpus/REVIEW.md, then:"
	@echo "  $(PY) -m eval.corpus.review --apply --as you@example.com"

.PHONY: corpus
corpus:
	@$(PY) -m eval.corpus.build

.PHONY: check
check: test
	@$(PY) -m eval.harness --all
	@$(PY) scripts/demo.py > /dev/null && echo "demo: runs clean"
