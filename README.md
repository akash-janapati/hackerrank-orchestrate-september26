# Buy or Wait? — Solution

AI-powered financial decision agent for the HackerRank Orchestrate "Buy or Wait?" challenge.
For every request in `dataset/requests.csv` it decides whether the user can pay in full, pay
partially, use installments, wait, or not proceed, and writes `output.csv` at the repository root.

See `architecture.md` (design), `implementation.md` (build plan + validation), and `report.md`
(sample comparison).

## Requirements

- Python 3.11+
- `pytesseract` (Python package) and the system `tesseract` binary
- An OpenRouter API key

```bash
pip install pytesseract
# system tesseract, e.g.: apt-get install tesseract-ocr  (or brew install tesseract)
```

## Environment variables (never hardcode secrets)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENROUTER_API_KEY` | yes | — | DeepSeek via OpenRouter |
| `ORCHESTRATE_MODEL_ID` | no | `deepseek/deepseek-chat` | model id |

## Run

```bash
python3 code/main.py            # writes output.csv at the repository root
```

The pipeline always uses the LLM with on-disk caching:
- **Messages**: DeepSeek extracts structured financial facts per message (retried until the
  structure validates; cached only on valid extraction).
- **Images**: `pytesseract` OCR → DeepSeek returns the final amount (cached per image by file
  hash; deterministic label fallback).
- **Explanation**: DeepSeek writes `decision_explanation` from computed facts only (rejects
  invented numbers; template fallback).

Re-running reuses caches by content hash. Model-call failures are always reported in
`code/evaluation/llm_failures.md`; token/cost accounting is in `code/evaluation/usage_report.md`.

## What it does

- **Deterministic core**: reconstructs each user's cash position, expands recurring income
  (cadence-based) and expenses (stable-only), and simulates day-by-day balances (debits before
  credits) over a 90-day horizon. A plan is safe only if the balance never drops below
  `minimum_balance_to_keep`.
- **Capacity**: `amount_safe_to_pay` and `earliest_date_for_full_payment`.
- **Plans**: full / partial / installments (matched to `request_payment_options.csv`) / wait,
  plus a spending-change optimizer over flexible, non-protected categories, ranked by the
  six-level rule.
- **Validator**: a spec linter checks every invariant before writing `output.csv`.

## Output

Root `output.csv`, exact columns in order:

```
request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation
```

## Evaluation utilities

```bash
python3 code/evaluation/fit_samples.py       # scorecard vs the 25 solved samples
python3 code/evaluation/sample_report.py     # writes report.md (detailed comparison)
python3 code/evaluation/variants.py          # forecast-policy comparison
python3 code/evaluation/mismatch_report.py   # plan-field mismatch attribution
python3 code/evaluation/images_report.py     # 16-image resolution table
python3 code/evaluation/trace_samples.py     # projection traces
```

## Layout

```text
code/            solution modules (config, ingest, domain, classify, reconcile, forecast,
                 simulate, capacity, plans, rank, messages, evidence, explain, llm, usage,
                 validate)
code/evaluation/ diagnostics, usage_report.md, llm_failures.md
code/cache/      gitignored caches (ocr/<image_id>.json, messages.json, explanations.json)
architecture.md  design
implementation.md build plan and validation
report.md        sample comparison report
output.csv       predictions (repository root)
log.txt          chat transcript (gitignored; submit separately)
```
