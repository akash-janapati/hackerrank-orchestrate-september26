# OpenCode Session Handoff — Buy or Wait? (HackerRank Orchestrate, Sept 2026)

This file summarizes the approach, decisions, findings, current state, and open items so a
different coding agent can continue without re-deriving everything. Read `AGENTS.md` first
(it mandates conversation logging to `log.txt` and the submission rules), then this file,
then `architecture.md` and `implementation.md`.

---

## 0. TL;DR / status

- Working end-to-end solution in `code/`, writes a valid root `output.csv` (250 rows, lint OK).
- Deterministic financial core + LLM evidence (messages, images) + LLM explanations.
- Current sample scorecard (25 solved samples): **amount MAE 471,047 · median error 597.74 ·
  status 18/25 · method 20/25 · plan 17/25 · earliest 10/25 · changes 22/25 · plan-field rows 14/25**.
- The `amount_safe_to_pay` field is **information-bounded** (see §6); exact reproduction is
  impossible from the released data. All remaining effort is incremental accuracy.
- **BLOCKER:** OpenRouter account returned `HTTP 402 Payment Required` (out of credits). All
  recent LLM calls fail and explanations fall back to templates. Top up to resume LLM features.
  Failures are reported in `code/evaluation/llm_failures.md`.

---

## 1. The challenge

For each row of `dataset/requests.csv` (250 requests), decide whether the user can pay in full,
pay partially, use installments, wait, or not proceed. Required `output.csv` columns:

```
request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation
```

Full spec: `problem_statement.md`. Starter context: `README.md` (overwritten with solution docs).

---

## 2. Important files

### Deliverables / docs
- `output.csv` (root) — final predictions, 250 rows + header.
- `code.zip` — submission package (code, README, examples, architecture.md, implementation.md,
  report.md; excludes log.txt/cache/secrets).
- `log.txt` — **chat transcript, gitignored, submitted separately** (AGENTS.md requires
  append-only logging every turn).
- `architecture.md` — design authority (pipeline, modules, rules).
- `implementation.md` — build plan, validation vs checklist, decisions, and later sections
  (§14–16) documenting forecast fixes.
- `report.md` — detailed 25-sample comparison vs ground truth (generated).
- `examples/request_03.md` — end-to-end trace of one request.
- `README.md` — setup/run/env docs.

### Core pipeline (`code/`)
| File | Role |
|---|---|
| `config.py` | paths, `HORIZON_DAYS=90`, `MODEL_ID`, recurrence/policy constants, output columns |
| `domain.py` | dataclasses: `Profile, Request, RawEvent, Event, PaymentOption, FactChange, Payment, SpendingChange, Plan, SimulationResult, OutputRow` |
| `ingest.py` | CSV loaders/indexes, `to_home` FX (exact→nearest→inverse), `cash_date`, `image_path` |
| `classify.py` | `Series` stats (median interval, day-of-month, months), `is_non_cash`, `is_cash_eligible`, `build_series`, `is_recurring` |
| `reconcile.py` | filters (drop cancelled/failed/non_cash/unrealized), key dedupe, FX to home, `amount_overrides` for blank events |
| `forecast.py` | 90-day recurrence expansion: **income cadence + median**, **fixed expenses at median**, **variable expenses at `VARIABLE_EXPENSE_FRACTION*median`**, monthly from request month, explicit pending/scheduled kept, dedupe by (category,direction,month) |
| `simulate.py` | day-by-day balances, debits-first, applies payments/`stop`/`reduce_to` (by id and category) |
| `capacity.py` | `amount_safe_to_pay`, `earliest_full_date` (no changes, preference-independent) |
| `plans.py` | candidate plans (full, full+changes, partial, installments matched to options, wait); spending-change optimizer |
| `rank.py` | eligibility gate + 6-level rank key; `fallback()` |
| `validate.py` | spec linter (bounds, status↔method, partial/installments/wait rules, flexible-only changes) |
| `messages.py` | **LLM** structured fact extraction per message, cache only on valid extraction, deterministic apply (end_income > amend > add) |
| `evidence.py` | image: `pytesseract` OCR (PSM 3/6/4) → `llm.chat_json` → amount; per-image JSON cache; label fallback; settled-only overrides |
| `explain.py` | LLM `decision_explanation` from computed facts, grounding check, template fallback, parallel |
| `llm.py` | single OpenRouter/DeepSeek client, retries, usage accounting, failure list, `write_failures` |
| `usage.py` | token/cost accounting + `usage_report.md` writer |
| `main.py` | orchestrates everything, writes `output.csv`, `usage_report.md`, `llm_failures.md` |

### Diagnostics (`code/evaluation/`)
`eda.py`, `fit_samples.py`, `variants.py`, `mismatch_report.py`, `changes_report.py`,
`message_recon.py`, `message_value.py`, `trace_samples.py`, `images_report.py`,
`sample_report.py` (writes `report.md`), `end_to_end.py` (writes `examples/<id>.md`).

### Caches (`code/cache/`, gitignored)
`messages.json` (LLM facts by text hash), `explanations.json`, `ocr/<image_id>.json`,
plus a stale `ocr_cache.json` from an earlier attempt (unused).

---

## 3. How to run

```bash
pip install pytesseract           # plus system tesseract binary
export OPENROUTER_API_KEY=...     # required for messages/images/explanations
python3 code/main.py              # writes root output.csv (+ reports)
```

Env: `OPENROUTER_API_KEY` (required), `ORCHESTRATE_MODEL_ID` (default `deepseek/deepseek-chat`).
There are **no** live/cache flags — the pipeline always uses the LLM with on-disk caching.

Evaluation:
```bash
python3 code/evaluation/fit_samples.py
python3 code/evaluation/sample_report.py     # -> report.md
python3 code/evaluation/end_to_end.py request_03
python3 code/evaluation/mismatch_report.py
```

---

## 4. Pipeline (data flow)

```
requests -> ingest -> messages(LLM facts) -> evidence(OCR+LLM amounts) -> reconcile
  -> forecast(90d recurrence) -> simulate -> capacity -> plans -> rank -> explain(LLM)
  -> validate(lint) -> output.csv
```

Model calls only in: message facts, image amounts, explanations. All money decisions are
deterministic Python.

---

## 5. Dataset facts established (verified)

- 250 eval requests (`request_26`+), 25 solved samples (`request_01`–25), 275 users (1 request/user).
- `financial_events.csv`: 25,342 rows; statuses settled 25,148, pending 71, scheduled 70,
  cancelled 22, failed 21, unrealized 10; flexibility fixed 21,138, reducible 2,682,
  stoppable 1,297, reducible_or_stoppable 225. `amount` blank in 16 rows; `linked_event_id` in 58.
- **The next 90 days are NOT in the file**: 228/275 requests have zero events after `request_date`;
  the rest cover 8–20 days; 0/275 reach 90 days. So recurrence must be projected.
- **16 images** map 1:1 to the 16 blank-amount events.
- **215 messages**, one per messaging user (215 users); 128 request-linked, 39 event-linked,
  76 user-only; all request-linked messages dated before `request_date`.
- Sample ground-truth distribution: status (with_plan 9, not_affordable 7, later 6, now 3);
  method (not_recommended 7, full 6, wait 6, installments 5, partial 1); changes non-none in 3.
- Exchange rates are fixed/dated; only certain pairs exist (USD→{INR,IDR}, USD→EUR, EUR→{USD,ZAR}).
  A message-added event once produced USD→ZAR and crashed; added events are now home-currency.

---

## 6. The core limitation (important)

`amount_safe_to_pay` cannot be reproduced exactly because the ground truth was computed from the
generator's **hidden per-occurrence future events**, which are not released. Evidence:
- Only 8–20 days of future coverage, 0/275 reach 90 days.
- Every sample user has variable-amount categories; no deterministic rule matched all 25 targets.
- ~15 projection rules tested (last/mean/median/max, copy windows, N-months-back, trailing-min,
  next-occurrence reserves, all/stable/protected expense policies); none reached exact.
- Errors are both-directional; median error is now small (597.74) while MAE is tail-driven.

Current residual concentrates in a few large-currency users (`request_25`, `request_04`,
`request_02`). Treat further amount work as incremental, not solvable.

---

## 7. Key decisions (frozen)

1. Deterministic core; LLMs only for message facts, image amounts, explanations.
2. `SAME_DAY_ORDER = "debits_first"` (adopted from eda.py; safer and better fit).
3. Forecast policy: **income by cadence** (≥3 months, 5–40 day median interval, amount = median);
   **expenses**: recurring (≥3 months); fixed categories (`config.FIXED_CATEGORIES`) at median;
   variable categories (groceries/transport/dining) at `VARIABLE_EXPENSE_FRACTION = 0.25` × median.
   Monthly projections iterate from the **request month** (not next month).
4. Image overrides apply only to **settled** blank events (pending/scheduled blanks cached but
   not applied — see request_16).
5. Output at repo root; `dataset/` never modified.
6. Exact column order; linter must pass before writing.

---

## 8. Evolution of the forecast (what changed and why)

- Started stable-only (day-of-month σ=0 AND amount CV<0.05) → dropped salary whenever a one-off
  pay adjustment raised variance, so `wait`/`installments` cases were mislabelled `not_affordable`.
- Income moved to cadence-based + median amount.
- Trace of `request_03` exposed that monthly projection **skipped occurrences in the request
  month** (salary 2019-09-15 missing) → fixed to start at month 0 (status 11→19).
- Variable expenses were entirely dropped → large optimistic bias (+672k). Introduced calibrated
  variable projection (α=0.25) → MAE 671k→471k, median 9,152→597.74, status 18, method 20, plan 17.
- Pure all-median expenses reaches MAE 105k but breaks 8 plan-field samples; α=0.25 keeps plan
  matches. All-Median is a possible alternative if the scoring weights amount heavily.

---

## 9. Known limitations / gaps to consider

- `linked_event_id` lifecycles are not netted (dedupe only by identical fields).
- `financial_priorities` unused in simulation.
- Spending-change optimizer selection is greedy; the generator's exact change set for
  `request_21` (cloud stop + streaming reduce) is not reproduced by any tested order.
- `earliest_date_for_full_payment` match is low (10/25) — sensitive to the forecast minimum.
- `messages.py` LLM facts are strong but a few grounding/JSON failures remain (reported).
- OpenRouter credits exhausted → LLM explanation failures (templates used).

---

## 10. Sample scorecard history

| stage | amount exact | MAE | median | status | method | plan | earliest | changes |
|---|---|---|---|---|---|---|---|---|
| Phase 0 stub | 0/25 | 1,642,336 | — | 7 | 7 | 7 | 7 | 22 |
| stable-only | 4/25 | 733,545 | 9,152 | 9 | 11 | 10 | 9 | 22 |
| + messages (regex) | 4/25 | 733,545 | 9,152 | 9 | 11 | 10 | 9 | 22 |
| + income cadence | 4/25 | 601,992 | 9,152 | 12 | 15 | 15 | 10 | 22 |
| + request-month fix | 4/25 | 671,666 | 2,438 | 19 | 21 | 17 | 10 | 22 |
| + α=0.25 variable expenses | **4/25** | **471,047** | **597.74** | **18** | **20** | **17** | 10 | 22 |

Full-set status distribution now: `affordable_now` 67, `affordable_with_plan` 68,
`affordable_later` 42, `not_affordable` 73.

---

## 11. Submission checklist (per `problem_statement.md` / `README.md`)

- `code.zip` — code, README, `evaluation/` (includes `usage_report.md`), architecture.md,
  implementation.md, report.md, examples/. Excludes log.txt/cache/secrets. ✅ built.
- `output.csv` — 250 rows, exact columns. ✅
- `chat_transcript` = `log.txt`. ✅ present (gitignored; submit separately).
- `code/evaluation/usage_report.md` — generated from a run; **currently reflects 0 successful
  calls due to the 402**; regenerate after topping up credits.

---

## 12. Working with the logging contract

`AGENTS.md` requires appending a `SESSION START` entry and a per-turn entry to `log.txt`
(same directory as AGENTS.md), with a non-empty `tool=<harness name>` line, append-only,
no secrets. `log.txt` is gitignored and is the submitted chat transcript.

---

## 13. Suggested next steps

1. **Top up OpenRouter credits**, re-run `python3 code/main.py` to regenerate `usage_report.md`
   and LLM explanations; verify `llm_failures.md`.
2. If amount accuracy is weighted heavily, evaluate `VARIABLE_EXPENSE_FRACTION` ∈ {0.25, 0.5}
   against the plan-field trade-off (α=0.5: MAE ~347k, plan-row 13; α=0.25: MAE 471k, plan-row 14).
3. Implement `linked_event_id` lifecycle netting and use `financial_priorities`.
4. Improve `earliest_date_for_full_payment` (it lags at 10/25) — likely the highest-value
   remaining plan-field lever.
5. Re-run `report.md`, `examples/request_03.md`, and rebuild `code.zip` after any change.

---

## 14. Gotchas

- Do **not** treat blank amounts as zero; resolve via image or drop, never zero.
- Added events must use the user's home currency (FX pairs are limited).
- `explain.generate_many` is parallel (4 workers); higher concurrency triggered 429s.
- 4xx auth/payment errors are not retried; transient 429/504 are retried.
- Linter (`validate.py`) enforces: `affordable_now ⇔ earliest == request_date`, `not_affordable ⇒
  plan none & empty earliest`, partial = exactly 2 payments summing to requested, installments
  exactly match an option, changes flexible/non-protected/≤3.
- The forecast's monthly loop must start at month 0 or request-month items are skipped.
