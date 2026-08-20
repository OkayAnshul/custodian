# Custodian

**The purpose layer for agentic commerce.** Make an Indian merchant transactable by an AI buyer end to end — then verify the agent bought what the human actually asked for.

> The agentic commerce stack proves an agent was *permitted* to spend — AP2, and UAP in India. No layer checks whether it bought the right thing. That gap lands on the merchant.

A guardrail inspects text and guesses. Custodian re-derives price, purpose and mandate fit against a catalog it controls and a mandate with hard numbers, gates three ways with calibrated abstention, and writes a hash-chained trail a dispute can be resolved from. Different mechanism, different failure surface.

**Status: day 1 of 15.** This README is written in full on day 13. Until then the live documents are the ones below.

| Document | What it holds |
|---|---|
| [`DECISIONS.md`](DECISIONS.md) | Every engineering decision, with the alternatives that were rejected |
| [`ENGINEERING_LOG.md`](ENGINEERING_LOG.md) | Session-by-session record |
| [`BROKE.md`](BROKE.md) | What broke and how we got out |

## Running the tests

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest --cov=custodian
```

## Built so far

| Module | Guarantee |
|---|---|
| `money.py` | Amounts are integer paise. No float path exists. |
| `bp.py` | Scores are integer basis points. All aggregation is integer arithmetic. |
| `canonical.py` | One logical value, one byte sequence. Floats are refused, not rounded. |
| `ledger/` | Append-only, hash-chained, tamper-evident. `observed` and `inferred` never blur. |
| `payments/` | One Protocol; fake and real implementations pass one contract suite. |
