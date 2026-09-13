# Buy or Wait? — Implementation Plan

Companion to `architecture.md`. This file is the executable plan: ordered phases, module
contracts, algorithms, acceptance criteria, and commands. `architecture.md` remains the design
authority; where this file adds precision (caching, lifecycle semantics, recurrence-vs-explicit
de-duplication) it is authoritative for the build.

Owner: solo participant · Language: Python 3 (stdlib-first) · Deadline: 2026-09-13 18:00 IST.

---

## 0. Objective and hard constraints

Produce root `output.csv` with one row per `dataset/requests.csv` (`request_id`): the max safe
amount today, affordability status, recommended method/plan, earliest full-payment date,
permitted spending changes, and a grounded explanation.

Hard constraints:

- Run from terminal: `python3 code/main.py` → root `output.csv`.
- Read only `dataset/`; never modify it; never use organizer-only files.
- Exact column order per spec.
- Deterministic core; models only for (a) message→`FactChange`, (b) OCR text→image amount,
  (c) `decision_explanation` text.
- `0 <= amount_safe_to_pay <= requested_amount` always.
- Minimal dependencies: stdlib core; `pytesseract` (+ system `tesseract`) for OCR; `urllib`
  for HTTP. No agent framework.
- Secrets from environment only (`OPENROUTER_API_KEY`, optional model-id overrides).

Deliverables: root `output.csv`, `code.zip` (code + README + `evaluation/`), `chat_transcript`
(`log.txt`), `evaluation/usage_report.md` from the final full-dataset run.

---

## 1. Target repository layout

```text
.
├── architecture.md
├── implementation.md
├── output.csv                      # generated, repo root
├── code.zip                        # generated at the end
├── code/
│   ├── main.py                     # entrypoint
│   ├── config.py                   # paths, horizon, flags, recurrence policy
│   ├── ingest.py                   # loaders + indexes + FX
│   ├── domain.py                   # dataclasses
│   ├── classify.py                 # event classification
│   ├── reconcile.py                # FactChange apply, lifecycle, precedence, FX
│   ├── forecast.py                 # recurrence expansion
│   ├── simulate.py                 # day-by-day balance predicat
│   ├── capacity.py                 # amount_safe_to_pay, earliest_full
│   ├── plans.py                    # candidate generation + spending changes
│   ├── rank.py                     # PreferenceGate, OptionMatcher, ranker
│   ├── explain.py                  # LLM explanation + template fallback
│   ├── evidence.py                 # OCR + DeepSeek client + cache + fallback parser
│   ├── usage.py                    # model/token accounting
│   ├── validate.py                 # spec linter + re-simulation
│   ├── cache/                      # gitignored: ocr/<image_id>.json (one per image), llm_cache.json
│   └── evaluation/
│       ├── fit_samples.py          # scorecard vs 25 samples
│       └── usage_report.md         # written only by final run
└── dataset/ ...                    # read-only
```

---

## 2. Phase 0 — Scaffold, ingestion, linter (target: ~1.5 h) — ✅ DONE

Status: implemented and validated. Files: `code/config.py`, `code/domain.py`,
`code/ingest.py`, `code/validate.py`, `code/main.py`, `code/evaluation/fit_samples.py`.

### Tasks

- [x] `config.py`: `DATASET_DIR`, `OUTPUT_PATH` (root), `HORIZON_DAYS = 90`,
      `CACHE_ENABLED`, `LIVE_MODELS`, `MODEL_ID` (default DeepSeek via OpenRouter),
      recurrence-policy constants (see §7).
- [x] `domain.py`: frozen dataclasses `Profile`, `RawEvent`, `Event`, `FactChange`,
      `Payment`, `SpendingChange`, `Plan`, `SimulationResult`, `RequestContext`,
      `PaymentOption`, `Request`, `OutputRow`.
- [x] `ingest.py`:
  - [x] loaders + indexes: `profiles[user_id]`, `events_by_user[user_id]`,
        `options_by_request[request_id]`, `message_by_user[user_id]`,
        `image_by_event[event_id]`, `rates[(from,to)]` (dated).
  - [x] `to_home(...)` with exact-date preference, nearest fallback, and inverse-pair fallback.
  - [x] `RawEvent.cash_date()` = `settlement_date` if present else `event_date`.
- [x] `validate.py` with the full §8 linter check set; `lint(...)` raises on violation.
- [x] `main.py`: load → deterministic stub pipeline → lint → write root `output.csv`.
- [x] `evaluation/fit_samples.py`: runs the pipeline on the 25 samples and prints a scorecard.

### Acceptance
- [x] `python3 code/main.py` writes a 251-line root `output.csv` (header + 250), exact header,
      lint OK.
- [x] `fit_samples.py` runs and prints a per-field scorecard (Phase 0 stub baseline).
- [x] Determinism: two runs produce byte-identical `output.csv`.
- [x] Linter rejects negative/over-cap safe amounts, wrong `affordable_now` earliest,
      `not_recommended` with a plan, and non-matching installment plans.

### Validation vs checklist (re-verified)

- `config.py`: all required keys present (`DATASET_DIR`, `OUTPUT_PATH`, `HORIZON_DAYS`,
  `CACHE_ENABLED`, `LIVE_MODELS`, `MODEL_ID`, recurrence constants). ✅
- `domain.py`: all listed dataclasses present. ✅
- `ingest.py`: `load_profiles`, `load_events`, `load_options`, `load_messages`, `load_images`,
  `load_rates`; `to_home` exact→nearest→inverse; `RawEvent.cash_date()`. ✅
- `validate.py`: full linter; rejects negative/over-cap safe, `not_recommended` with a plan,
  non-matching installments (re-tested). ✅
- `python3 code/main.py`: 250 rows, exact header, lint OK; two runs byte-identical. ✅
- `fit_samples.py` prints the scorecard. ✅
- Deviation: the Phase-0 "stub pipeline" was superseded by the real pipeline in Phase 1;
  `main.py` no longer emits stub rows.

### Phase 0 measured baseline (stub)
- `amount` 0/25, `status` 7/25, `method` 7/25, `plan` 7/25, `earliest` 7/25, `changes` 22/25.
- This is the floor; Phase 1 must drive `amount`/`earliest`/`status` up.

### Note
- A prior/parallel attempt left `code/cache/ocr_cache.json` (old single-file format) and stale
  `code/__pycache__` entries for modules that do not exist. Both are gitignored and ignored by
  the current code; the live image cache will be per-image at `code/cache/ocr/<image_id>.json`.

---

## 3. Phase 1 — Canonical state, forecast, simulator, capacity (target: ~6 h)

This is the scoring crux.

### Status: implemented; exact-match acceptance NOT met — cause documented

Files: `code/classify.py`, `code/reconcile.py`, `code/forecast.py`,
`code/simulate.py`, `code/capacity.py`; wired into `code/main.py`.

Policy used (derived, not swept): recurrence only when history shows
`>= MIN_OCCURRENCES` distinct months; **stable-only expansion** (adopted from
`code/evaluation/variants.py`) — project only categories whose day-of-month is constant
(sigma == 0) and whose amount coefficient of variation is < 0.05; one-time types never
projected; debits-first same-day ordering; explicit `pending`/`scheduled` rows always
included; FX by settlement-date rate.
`amount_safe_to_pay = clamp(min_balance_after_forecast - minimum_balance, 0, requested)`.
`earliest_full_date` scans the horizon for the first day a single full payment stays safe.

**Variant comparison on the 25 samples (before adoption):**

| variant | exact | MAE | signed mean (pred-GT) |
|---|---|---|---|
| full expansion | 2/25 | 1,218,999 | -900,927 |
| A capped horizon | 3/25 | 1,218,530 | -900,411 |
| B stable-only expansion | 4/25 | **733,545** | **+22,093** |

A alone was negligible; **B materially improved MAE (~40%) and removed the pessimistic
bias**, so it was adopted. With B in place, A stacks to MAE 638,796 (deferred).

**Scorecard (Phase 0 stub -> Phase 1, stable-only):** amount exact 0/25 -> 4/25;
status 7/25 -> 9/25; method 7/25 -> 11/25; plan 7/25 -> 10/25; earliest 7/25 -> 9/25;
changes 22/25 -> 22/25; amount MAE 1,642,336 -> 733,545 (median 9,152).

**Root cause of the mismatches (specific rule):** the ground truth was computed from the
generator's **hidden per-occurrence future events**, which are not present in the released
`financial_events.csv`. The released file stops at/near `request_date`, and the hidden future
amounts are drawn per occurrence (they vary month to month even for a fixed category/day), so
no deterministic projection can reproduce them. Evidence:

- 228/275 requests have zero events after `request_date`; the rest cover 8-20 days; 0/275
  reach 90 days (see `architecture.md` §7).
- Every sample user has multiple variable-amount categories; amounts for the same
  category/day-of-month differ across months (e.g. user_19 utilities 5525.82-6141.28).
- Every plausible deterministic rule was tested against the 25 targets and matches **none**
  exactly: last-amount day-of-month; all-days-of-month; copy trailing 30/60/90 days; tile by
  30/45 days; per-category mean/median/max; next-occurrence reserves; monthly-fixed-only.
  Errors go both directions, which excludes a single missing inclusion/exclusion rule.
- The chosen per-category amount estimate (median, mean, or conservative max) changes MAE by
  only ~8% and never the exact-match count, confirming the error is information-theoretic,
  not a tuning gap.

**Consequence:** `amount_safe_to_pay`, `earliest_date_for_full_payment`, and the
capacity-derived parts of `affordability_status` are bounded by this information limit and
cannot be exact on this dataset. The deterministic engine is otherwise correct and lints
clean. This needs a decision before Phase 2: accept a principled approximation, or attempt to
recover the generator's hidden future (not possible from the released files alone).

### Validation vs checklist (re-verified against code)

| checklist item | status |
|---|---|
| 3.1 five-way classification (`fixed/variable/one_time/lifecycle/non_cash`) | ⚠️ partial: `is_non_cash`, `is_cash_eligible`, series stats, fixed/variable via `is_monthly`/`is_fixed_amount`; history events keep `recurrence="unknown"`; no explicit `lifecycle` label |
| 3.1 `non_cash` rule | ✅ direction `non_cash` / status `unrealized` / event_type `investment_valuation` |
| 3.1 `lifecycle` rule | ❌ not implemented as stated: `reconcile` does not branch on `linked_event_id`; no failed→pending retry conversion |
| 3.1 `fixed`/`variable` rules | ⚠️ partial (`is_monthly`, `is_fixed_amount`, `forecast._is_stable`) |
| 3.1 `one_time` rule | ⚠️ effectively via recurrence thresholds; the guard at `forecast.py:89` compares a category to event_type names and is dead code |
| 3.1 recurrence `>= MIN_OCCURRENCES` | ✅ |
| 3.2 `apply_facts` + precedence | ❌ not implemented (`facts` argument accepted but ignored) |
| 3.2 lifecycle semantics | ⚠️ partial: cancelled/failed dropped, `investment_valuation` excluded, `refund` credit retained, key-based dedupe; missing retry conversion and linked netting |
| 3.2 `dedupe_explicit_vs_recurrence` | ✅ via `forecast` `covered` set (category, direction, month) |
| 3.2 FX by settlement date | ✅ |
| 3.3 `expand` over 90-day horizon | ✅ |
| 3.3 fixed-monthly median projection | ✅ |
| 3.3 variable median-interval conservative | ❌ not active: stable-only drops variable categories; `is_variable_amount` imported but unused, conservative branch unreachable |
| 3.3 recurring income / scheduled salary | ⚠️ partial; salary is dropped if its amount varies (stability filter) |
| 3.3 exclude one_time/non_cash/cancelled/failed | ⚠️ mixed (see above) |
| 3.3 `INCLUDE_SAME_DAY` / `SAME_DAY_ORDER` | ⚠️ `SAME_DAY_ORDER` used in `simulate`; `INCLUDE_SAME_DAY` unused (strict `>`) |
| 3.4 `simulate(state, payments, changes)` | ❌ actual signature `simulate(balance, min_balance, future_events, payments, changes)` |
| 3.4 start/day order/changes/payments/running-min | ✅ |
| 3.5 `min_cumulative_net` | ⚠️ computed inline in `capacity.amount_safe_to_pay`, not a named function |
| 3.5 `amount_safe_to_pay` formula | ✅ (equivalent form `min_after − minimum_balance`) |
| 3.5 `earliest_full_date` | ✅ |
| 3.5 `affordable_now ⇔ earliest == request_date` | ✅ |
| Acceptance: exact `amount_safe`/`earliest`/`status` | ❌ not met — information-bounded (documented above); amount 4/25 |

### 3.1 `classify.py`
- [ ] Classify each cash event into `fixed | variable | one_time | lifecycle | non_cash`.
- [ ] Rules (configurable):
  - `non_cash`: `direction == non_cash` or status `unrealized` or event_type
    `investment_valuation`.
  - `lifecycle`: has `linked_event_id` (handled by reconciler, never simply dropped).
  - `fixed`: category recurring monthly with stable amount (rent, utilities, healthcare,
    debt_repayment, subscriptions, family_support, salary).
  - `variable`: recurring with variable amount/cadence (groceries weekly, transport ~2x/mo,
    dining, shopping).
  - `one_time`: appears once, or description/type indicates one-off (travel, refund,
    windfall, windfall-like, investment_purchase/sale).
- [ ] Detect recurrence only when history supports it: a `(category, direction)` is recurring
      if it appears in `MIN_OCCURRENCES` distinct months (default 3). Otherwise `one_time`.

### 3.2 `reconcile.py` (pure Python; apply evidence if present)
- [ ] `apply_facts(events, facts)`: precedence order (explicit cancel/settle/amend > newer
      same-source > settled > safer). Facts with `effective_date` only affect
      dates ≥ effective.
- [ ] **Lifecycle semantics (spec-critical).** `linked_event_id` is not a blanket duplicate
      flag:
  - failed/cancelled rows are removed from cash flow (a "will retry" message converts the
    failed debit back to a pending debit);
  - `refund` (credit) linked to an expense is a real cash credit, not a duplicate;
  - `investment_purchase`/`investment_sale` are cash; their linked
    `investment_valuation` is `non_cash` and excluded;
  - true duplicate representations of the same cash movement are de-duplicated.
- [ ] `dedupe_explicit_vs_recurrence(...)`: an explicit `pending`/`scheduled` row for a
      category/date supersedes the projected recurring occurrence for that date; projected
      occurrences must not duplicate a supplied row.
- [ ] FX-normalize every retained cash event to the user's home currency using the
      settlement-date rate; keep original amount/currency for provenance.

### 3.3 `forecast.py`
- [ ] `expand(state) -> list[Event]` over `[request_date, request_date + 90d]`.
- [ ] Fixed-monthly: project on the category's median day-of-month with its median (or last)
      amount. Variable: project at the category's median interval with a conservative amount
      (e.g. max of recent occurrences). Income: project recurring salary only when
      history supports it; always include the confirmed scheduled salary on its settlement
      date.
- [ ] Exclude `one_time`, `non_cash`, cancelled, failed.
- [ ] Apply `INCLUDE_SAME_DAY` / `SAME_DAY_ORDER` from config.
- [ ] Policy knobs live in `config.py`; keep functions pure and parameterized so the
      scorecard can sweep them.

### 3.4 `simulate.py`
- [ ] `simulate(state, payments, changes) -> SimulationResult`.
- [ ] Start at `profile.balance` on `request_date`; for each day apply debits then credits;
      apply spending changes (`stop` removes future occurrences; `reduce_to` caps future
      amounts at `new_amount`); apply requested payments; track running min.
- [ ] `safe = running_min >= profile.minimum_balance`.
- [ ] Return daily balances, min, and breach date for explanations.

### 3.5 `capacity.py`
- [ ] `min_cumulative_net(state)` via simulation with no request payment and no changes.
- [ ] `amount_safe_to_pay = clamp(balance − minimum + min_cum, 0, requested)`.
- [ ] `earliest_full_date`: smallest `d` in horizon such that paying `requested_amount` on `d`
      is safe for the remainder (no changes, preference-independent). Empty if none.
- [ ] `affordable_now ⇔ earliest_full == request_date`.

### Acceptance
- Scorecard: `amount_safe` median abs error trending to ~0; `earliest` exact on most samples.
- Every sample's `amount_safe`, `earliest`, `status` reproduced or within a documented
  tolerance; record baseline vs naive tile in `architecture.md`/notes.

---

## 4. Phase 2 — Plans, eligibility, ranking (target: ~3 h) — ✅ DONE

Status: implemented (`code/plans.py`, `code/rank.py`, wired into `code/main.py`).
`plans.generate` produces full (with/without changes), partial, installments (matched to
options, respecting `max_installment_months` and the completion deadline), and wait plans;
`rank.choose` applies the 6-level key (completes, changes, total paid, earlier start, fewer
payments, lowest option id). `simulate` now applies spending changes by category to projected
occurrences.

**Sample scorecard (Phase 0 -> Phase 1 -> Phase 2):**

| field | Phase 0 | Phase 1 | Phase 2 |
|---|---|---|---|
| `amount_safe` exact | 0/25 | 4/25 | 4/25 |
| `status` | 7/25 | 9/25 | **11/25** |
| `method` | 7/25 | 11/25 | **13/25** |
| `plan` | 7/25 | 10/25 | **12/25** |
| `earliest` | 7/25 | 9/25 | **10/25** |
| `changes` | 22/25 | 22/25 | 22/25 |

**Mismatch reality check** (`code/evaluation/mismatch_report.py`, honest metric): **raw
plan-field match is 11/25**. The 14 mismatches break down as: 7 where our `amount_safe` is too
high (under-reserved, we recommend something the truth rejects), 7 where it is too low
(over-reserved, e.g. expected `wait`/`installments` our projection deems unsafe), and 3 where the
truth needs a spending change we did not emit. No single "forecast-driven" label is used; each
mismatch is attributed by the sign of the `amount_safe` residual.

**Spending-change investigation** (`code/evaluation/changes_report.py`):
- `_flexible_candidates` had a real bug: it kept the max-saving event and preferred `stop`. The
  solved samples use the **most recent** event per category and prefer `reduce_to`. Fixed in
  `plans.py`; candidates now reproduce the ground-truth ids exactly (request_06 `event_476`;
  request_11 `event_989:665950`; request_21 `event_1815` + `event_1816:23.50`).
- `minimum_allowed_amount` is read from the schema (2,907 events populated).
- Zero changes are emitted on the 250 eval rows because, under the stable-only projection, of
  174 requests where an immediate full payment is unsafe, 171 have flexible candidates but **none
  is fixed by <=3 changes** (the shortfall exceeds the available flexible savings); the other 76
  are already full-payment safe. So changes=0 is legitimate for our projection, not a lookup bug.
- The ranker is the final gate: `main.predict_all` emits `rank.choose(candidates) or
  rank.fallback()` with no overriding branch.

Full run: 250 rows, lint OK; statuses `affordable_now` 51, `affordable_with_plan` 42,
`affordable_later` 13, `not_affordable` 144; methods include `installments` 34, `partial_payment` 8.

### Pre-Phase-3 investigation (Steps A/B/C)

**Step B — change-selection order (fixed).** `_flexible_candidates` now uses one candidate per
flexible category (its most recent occurrence), prefers `reduce_to` over `stop`, and orders by
most-recent occurrence date then larger saving. This reproduces request_06 (`stop event_476`) and
request_11 (`reduce_to event_989` before entertainment); request_21's exact set (cloud stop +
streaming reduce) is not reproduced by any greedy order tested, but no change is emitted under our
projection so output is unaffected.

**Step A — message recon (`code/evaluation/message_recon.py`).** For the 25 samples: each message
dumped with linkage and a hand-authored interpretation. Applying the financial amendments and
re-running plan generation changed `amount_safe` for only 2 samples (user_02, user_15) and improved
plan-field match for **0 samples (delta 0 across all 17 financial messages)**.

**Step C — how many messages actually change a forecast (`code/evaluation/message_value.py`).**
Mechanical template application over all 215 messages: 114 users have a change-type template, but
only **58 of 275 requests' forecasts actually changed** (30 add_income, 17 amend_income, 7
amend_date, 4 amend_rent). The rest are pending credits, non-cash, or no-content. So "198 users have
messages" is not "198 change the forecast".

**Evidence verdict:** on the 25 samples, Phase 3 message work yields no plan-field improvement; on
the full set it changes 58 requests. Blank-amount images (16 events) are a separate, concrete gap:
those events are currently dropped from cash flow entirely (never treated as zero, but not
projected), including user_03's salary. Decision deferred to the user.

### Validation vs checklist (re-verified against code)

| checklist item | status |
|---|---|
| 4.1 `full_payment` (no changes) | ✅ |
| 4.1 `full_payment + changes` | ✅ one candidate per category (stop/reduce mutually exclusive), `reduce_to` at `minimum_allowed_amount`, ≤3, pruned to minimal |
| 4.1 `partial_payment` | ✅ allows/accepted/`0<safe<requested`/earliest ≤ desired, exactly two payments summing to requested |
| 4.1 `installments` | ✅ exact option schedule, `max_installment_months`, last payment ≤ deadline |
| 4.1 `wait` | ✅ later safe date ≤ deadline |
| 4.1 `not_recommended` | ✅ `rank.fallback` |
| 4.2 `PreferenceGate` | ⚠️ enforced in `plans.generate` (`profile.methods`); `rank.eligible_methods` exists but is unused |
| 4.2 `OptionMatcher` | ⚠️ implemented in `plans._option_schedule`, not in `rank.py` |
| 4.2 safety filter (re-simulate) | ✅ in `plans._sim_safe`; not a separate rank pass |
| 4.2 6-level rank key | ✅ |
| 4.2 map winner → `affordability_status` | ✅ `Plan.status` |
| Acceptance: method/plan/status match samples | ⚠️ partial: raw 11/25; 14 mismatches attributed (7 under-reserved, 7 over-reserved, 3 missing change) — all amount-driven |

### 4.1 `plans.py`
- [ ] `full_payment`: pay `requested_amount` on `request_date` (no changes) if safe.
- [ ] `full_payment + changes`: pick ≤3 flexible, non-protected events; `stop` stoppable,
      `reduce_to` reducible at `minimum_allowed_amount` (or the minimal reduction that makes it
      safe). `stop`/`reduce_to` on the same event are mutually exclusive; different events if
      both kinds used. Minimize count and prefer zero changes.
- [ ] `partial_payment`: only if `allows_partial_payment` and user accepts it and
      `0 < amount_safe < requested` and `earliest_full <= desired_completion_date`; exactly two
      payments summing to `requested_amount`.
- [ ] `installments`: for each supplied option (matched exactly: dates, amounts, fees) that
      respects `max_installment_months` and whose last payment ≤ `desired_completion_date`.
- [ ] `wait`: full payment on a later safe date ≤ `desired_completion_date`.
- [ ] `not_recommended`: fallback with `plan = none`.

### 4.2 `rank.py`
- [ ] `PreferenceGate`: immediate methods require membership in
      `payment_methods_user_will_consider`; `wait` requires `full_payment` accepted.
- [ ] `OptionMatcher`: exact option schedule + `max_installment_months`.
- [ ] Safety filter: re-simulate each candidate; keep only safe ones.
- [ ] Rank key: (1) completes by `desired_completion_date`, (2) no spending changes,
      (3) minimize `total_paid` (incl. fees), (4) earlier first payment, (5) fewer payments,
      (6) lowest `payment_option_id`.
- [ ] Map winner → `affordability_status` (`affordable_now` / `affordable_with_plan` /
      `affordable_later` / `not_affordable`).

### Acceptance
- `recommended_payment_method`, `payment_plan`, `affordability_status` match samples.
- `spending_changes_needed` matches sample cases (e.g. `stop:event_476`, event_989→665,950,
  event_1816→23.5).

---

## 5. Phase 3 — Evidence layer (target: ~4 h)

### Status: narrow Phase 3 done (Steps 1-3); full layer intentionally skipped

**Step 1 — stability-filter fix: attempted, reverted.** Cadence-based recurrence with
last-amount projection regressed: stable-only MAE 733,545 → 1,593,232 (cadence for all),
or 738,264 (monthly σ≤1 hybrid). Per the revert-on-regression rule the previous
stable-only filter (σ(day)==0 and amount CV<0.05, median/conservative amount) was restored.
Baseline reconfirmed: MAE 733,545, amount 4/25, status 9/25.

**Step 2 — images: implemented, reverted from the pipeline.** `code/evidence.py` does
`pytesseract` OCR (PSM 3/6/4) → DeepSeek (`deepseek/deepseek-chat` via OpenRouter) →
`{amount, currency, confidence, evidence_line}`, with a deterministic label-priority fallback
(`Net Pay > Grand Total > Total Amount Received > Amount Payable/Balance Due > Total > Item Bill`)
and one JSON cache per image at `code/cache/ocr/<image_id>.json` keyed by file hash. All
**16/16 blank events resolved** (`code/evaluation/images_report.py`), e.g. request_03 salary
IDR 4,365,000, image_16 INR 393.22. However wiring the overrides into the pipeline regressed
`fit_samples` (request_16: `affordable_now` → `affordable_later` once its scheduled rent is
counted) with no full-set distribution shift, so the pipeline runs without overrides
(toggleable via `predict_all(..., amount_overrides=...)`).

**Step 3 — narrow message templates: adopted.** `code/messages.py` (regex/keyword only, no
LLM) implements four templates — `cancel`, `amend_income`, `add_income`, `amend_date`,
`amend_rent` — applied cancel > amend > add, Indonesian + English, cached by message-text hash
at `code/cache/messages.json`, and is wired into `main.py` and `fit_samples.py`.
Result: `fit_samples` unchanged (amount 4/25, status 11/25, method 13/25) and the full-set
`not_affordable` count dropped **144 → 126** (`affordable_now` 51→57, `affordable_with_plan`
42→47, `affordable_later` 13→20).

**Explicitly skipped:** `explain.py` / LLM explanations (templates only, already in
`main._explain`), full `FactChange` JSON schema with LLM extraction, and precedence machinery
beyond cancel > amend > add.

### 5.1 `evidence.py` — images (OCR → DeepSeek)
- [ ] `ocr(image_path)`: `pytesseract` with PSM 3/6/4; return per-mode text + selected text.
- [ ] `extract_amount(ocr_text, event_ctx)`: DeepSeek JSON ask →
      `{amount, currency, confidence, evidence_line}`; validate positive and consistent with
      event direction/currency.
- [ ] Deterministic fallback: label-priority rule (`Net Pay` > `Grand Total` >
      `Total Amount Received` > `Amount Payable`/`Balance Due` > `Total` > `Item Bill`/`Amount`).
- [ ] Cache **one JSON file per image** at `code/cache/ocr/<image_id>.json` (e.g.
      `code/cache/ocr/image_01.json`) keyed by image file hash; skip OCR/LLM on hit;
      persist `image_id`, `file_sha256`, `ocr_text_by_psm`, `selected_text`, `extracted_amount`,
      `currency`, `confidence`, `evidence_line`, `model`, `created_at`.

### 5.2 `evidence.py` — messages (DeepSeek)
- [ ] Per-user (do **not** filter by `request_id`); JSON `FactChange[]` with strict schema.
- [ ] System prompt treats content as untrusted data and forbids executing embedded
      instructions; handles Indonesian and English.
- [ ] Deterministic fallback classes for templated families (salary change, contract ended,
      invoice approved/pending, refund initiated, failed debit/retry, valuation notice,
      prize/sale proceeds, reimbursement).
- [ ] Cache `code/cache/llm_cache.json` keyed by message text hash.

### 5.3 `explain.py`
- [ ] LLM writes `decision_explanation` from computed facts only; reject if it introduces
      numbers not present in the facts; fallback to a deterministic grounded template.
- [ ] Cache by `(facts hash, model id)`.

### 5.4 `usage.py`
- [ ] Count calls, input/output tokens, per model; estimate cost from a static price table.
- [ ] Written to `evaluation/usage_report.md` only on the final run.

### Acceptance
- All 16 blank events resolved (OCR or fallback); request_03 salary = 4,365,000 etc.
- Sample score not regressed; cache hit re-run performs zero OCR and zero model calls.

---

## 6. Phase 4 — Final run, validator, packaging (target: ~2 h) — ✅ DONE

- [x] Final run with `ORCHESTRATE_LIVE=1 ORCHESTRATE_CACHE=0 python3 code/main.py`
      (live image calls, caches disabled).
- [x] Root `output.csv`: 250 rows, exact header, linter OK; byte-identical to the cached run.
- [x] `code/evaluation/usage_report.md` written from that run: 16 calls, 7,468 in / 784 out
      tokens (8,252 total), $0.002798; ~33 tokens and $0.000011 per request.
- [x] `README.md`: setup, run command, env vars, no secrets.
- [x] `code.zip`: `code/`, `README.md`, `evaluation/`, `architecture.md`, `implementation.md`;
      excludes `log.txt`, `cache/`, `__pycache__`, secrets (verified).
- [x] `chat_transcript` (`log.txt`) present at repo root.
- [x] Every installment plan matches an option; changes target flexible non-protected events.

**Step A/B/C outcome:** request_16 was diagnosed as **Legitimate** (not a duplicate; correct
direction). The principled cash-date-vs-history rule (apply image overrides only to **settled**
blank events) satisfied both acceptance conditions — `fit_samples` at baseline (amount 4/25,
status 11/25, method 13/25) and full-set `not_affordable` 126 / `affordable_now` 57 — so the
settled-only image overrides were adopted. The final pipeline therefore makes 16 genuine image
model calls; no fabricated usage.


- [ ] Run full 250 with `LIVE_MODELS=true`, `CACHE_ENABLED=false` (genuine usage report;
      cache still written for reproducibility).
- [ ] `lint()` on all rows; `validate.py` re-simulates each chosen plan.
- [ ] Write root `output.csv`.
- [ ] Generate `evaluation/usage_report.md` from that run only.
- [ ] README: setup (`pip install pytesseract`, system `tesseract`, env vars), run command.
- [ ] Build `code.zip` (code + README + `evaluation/`); ensure no secrets, no `log.txt`.
- [ ] Confirm header/order/count and all invariants in README checklist.

### Acceptance (submission gate)
- 250 rows + header, exact columns.
- No linter violations; every installment plan matches an option; every change targets a
  flexible non-protected event.
- `evaluation/usage_report.md` present and consistent with the final run.

---

## 7. Recurrence policy (initial defaults, to be calibrated)

```python
HORIZON_DAYS = 90
TRAILING_WINDOW = 30          # days of history anchoring the projection
MIN_OCCURRENCES = 3           # distinct months before a category is recurring
CADENCE_MODE = "day_of_month" # or "median_interval"
VARIABLE_CATEGORIES = {"groceries": 7, "transport": 14, "dining": 30, "shopping": 30}
VARIABLE_AMOUNT = "conservative"   # e.g. max of recent occurrences
ONE_TIME_TYPES = {"refund", "investment_purchase", "investment_sale"}
ONE_TIME_CATEGORIES = {"windfall"}
INCLUDE_SAME_DAY = True
SAME_DAY_ORDER = "debits_first"
PENDING_POLICY = {"reserve_debits": True, "count_credits": False}
```

Calibration: sweep these against the 25 samples with leave-one-out; freeze the winning set in
`config.py`; record the scorecard delta in notes and `architecture.md`.

---

## 8. Output writer and invariants

Field formatting:
- amounts: trim trailing zeros but keep cents where present (e.g. `15595206.67`);
- `payment_plan`: chronological `YYYY-MM-DD:amount` joined by `|`, or `none`;
- `earliest_date_for_full_payment`: `YYYY-MM-DD` or empty;
- `spending_changes_needed`: `stop:<id>` / `reduce_to:<id>:<amt>` joined by `|`, or `none`;
- `decision_explanation`: ≤ ~2 sentences, grounded.

Linter (fail the run):
- header exact; one row per request; `0 <= safe <= requested`;
- `affordable_now ⇔ earliest == request_date`; earliest empty otherwise if never safe;
- partial rule (allows, accepted, 2 payments sum to requested, 2nd ≤ desired);
- installments exactly match a supplied option and `max_installment_months`;
- `not_recommended`/`wait` plan rules;
- ≤3 changes, flexible non-protected only, stop/reduce mutually exclusive,
  `reduce_to >= minimum_allowed_amount`;
- re-simulated chosen plan is safe.

---

## 9. Verification commands

```bash
python3 code/main.py                    # writes root output.csv
python3 code/evaluation/fit_samples.py  # scorecard vs 25 samples
python3 -m py_compile code/*.py         # syntax check
```

Determinism check: run twice with `CACHE_ENABLED=true` and `diff output.csv` → identical.

---

## 10. Evidence caching contract

- **Images: one JSON file per image**, `code/cache/ocr/<image_id>.json` (e.g.
  `code/cache/ocr/image_01.json`), containing a single record:
  `{image_id, file_sha256, ocr_text_by_psm, selected_text, extracted_amount, currency,
  confidence, evidence_line, model, created_at}`. Missing file → run OCR + LLM and write it.
- `code/cache/llm_cache.json`: a single shared file, `sha256(message_text) -> {facts, model,
  created_at}` and `sha256(facts+model) -> {explanation}`.
- Cache read before any model/OCR call; write after. `CACHE_ENABLED=false` ignores reads but
  still writes (so the final run's cache can back later reproductions).

---

## 11. Time budget (≈20 h remaining)

| Phase | Target |
|---|---|
| 0 Scaffold | 1.5 h |
| 1 Forecast/simulate/capacity | 6 h |
| 2 Plans/rank | 3 h |
| 3 Evidence | 4 h |
| 4 Final run/packaging | 2 h |
| Buffer | 3.5 h |

---

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Recurrence policy mismatch | sample scorecard + leave-one-out; documented baseline |
| `linked_event_id` mishandled | lifecycle semantics, never blanket-exclude linked rows |
| explicit vs projected double count | reconciler de-dup rule |
| OCR misread / ambiguous layout | LLM over OCR text + deterministic label fallback + validation |
| Model JSON invalid | strict schema, discard, deterministic fallback |
| Output format violation | linter fails run before writing |
| Non-determinism | content-hash caches; `diff` re-run check |
| Time overrun | deterministic core first; evidence and explanations last |

---

## 13. Assumptions and open items

- 90-day horizon; `earliest_full` empty when not safe within it.
- Recurring salary projected from history is supported (validated on `user_03`).
- Final run uses live calls with cache disabled to produce a genuine usage report; cache still
  written. (Flip `CACHE_ENABLED=true` if a zero-call reproducible run is preferred.)
- Output at repo root; `dataset/` untouched.

---

## 14. Post-submission forecast improvement

The amount/logic lever is income recurrence. The original stable-only filter dropped income
series whenever a one-off pay adjustment raised amount variance (e.g. user_03's extra pay,
user_02's amended raise), so the simulator saw no income and mislabelled `wait`/`installments`
cases as `not_affordable`.

Change (`code/forecast.py`): **income recurrence by cadence** — a credit `(category,direction)`
is recurring when it appears in >= `MIN_OCCURRENCES` months with a 5–40 day median interval,
and its projected amount is the **median** of occurrences (robust to one-offs). Expenses keep
the stable-only filter (day-of-month sigma == 0 and amount CV < 0.05), which remains best.

Measured on the 25 samples (full pipeline: messages + settled images):

| metric | before | after |
|---|---|---|
| amount MAE | 1,074,237 | **601,992** |
| status | 11/25 | **12/25** |
| method | 13/25 | **15/25** |
| plan | 13/25 | **15/25** |
| earliest | 10/25 | 10/25 |
| changes | 22/25 | 22/25 |
| full-set `not_affordable` | 126 | **98** |
| full-set `affordable_now` | 57 | **71** |

Alternatives tested and rejected (worse): trailing-window-minimum forecast (MAE 860k);
all-recurring expense projection at max/mean/p75/median (status 9–11); protected-category
conservative projection (status 9). The residual amount error remains the hidden-future
information bound; errors are now both-directional rather than systematically pessimistic.

---

## 15. LLM message extraction, LLM explanations, failure reporting

Requested: replace the regex-based message layer with LLM structured extraction;
remove the live/cache gating flags; use the LLM to write `decision_explanation`;
report every LLM call failure.

Changes:
- **`code/llm.py`** (new): single DeepSeek/OpenRouter client. `chat()` retries transient
  HTTP/429/504/provider errors; `chat_json()` retries until valid JSON; records tokens/cost in
  `usage.USAGE`; appends failures to `llm.FAILURES`; `write_failures()` emits
  `evaluation/llm_failures.md`.
- **`code/messages.py`**: rewritten to ask DeepSeek for structured facts per message
  (`{action, category, direction, amount, currency, date, factor, recurrence, reason}`),
  validated and cached per message-text hash **only on a valid extraction**; facts applied
  deterministically (end_income > amendments > additions). Added events use the user's home
  currency to avoid unconvertible FX.
- **`code/explain.py`** (new): DeepSeek writes `decision_explanation` from computed facts only;
  rejects explanations that introduce monetary numbers absent from the facts; template fallback;
  cached only on success; parallelised (`explain.generate_many`, 4 workers).
- **`code/evidence.py`**: image extraction now goes through `llm.chat_json`; per-image cache by
  file hash; deterministic label fallback; failures reported.
- **Flags removed**: `LIVE_MODELS` / `CACHE_ENABLED` (and their env vars) are gone; the pipeline
  always uses the LLM with on-disk caching.
- **`main.py`**: runs messages → images → forecast → plans → rank → LLM explanation → lint, and
  writes both `evaluation/usage_report.md` and `evaluation/llm_failures.md`.

Final full run: 250 rows, lint OK; 241–248 model calls; token/cost in `usage_report.md`;
failures reported in `llm_failures.md` (mostly grounding fallbacks plus a few transient
429/504, all retried). Sample scorecard with LLM messages/explanations: amount 4/25, status
11/25, method 14/25, plan 14/25, earliest 10/25, changes 22/25, MAE 600,924.

---

## 16. Forecast fixes and calibration (request_03 deep-dive)

Tracing `request_03` (see `examples/request_03.md`) exposed two forecast issues:

1. **Request-month occurrences were skipped.** Monthly projection started at `+1`
   calendar month, so a salary/rent due later in the request month (e.g. salary 2019-09-15)
   was never projected, inflating the pre-income dip. Fixed: iterate months from `0`, keeping
   occurrences strictly after `request_date`.
2. **Variable expenses were dropped entirely** (stable-only filter), producing a large
   optimistic bias (mean pred−GT ≈ +672k on the samples). Fixed with a calibrated projection:
   recurring expenses are projected (≥ `MIN_OCCURRENCES` months); fixed categories
   (`config.FIXED_CATEGORIES`) at their median, purely variable categories (groceries,
   transport, dining) at `config.VARIABLE_EXPENSE_FRACTION` × median = **0.25**. Income keeps
   the cadence rule and median amount.

Measured on the 25 samples:

| metric | before | after |
|---|---|---|
| amount MAE | 671,666 | **471,047** |
| amount median error | 9,152 | **597.74** |
| status | 19/25 | **18/25** |
| method | 21/25 | **20/25** |
| plan | 17/25 | **17/25** |
| plan-field rows | 14/25 | **14/25** |

(A pure all-expenses median projection reaches MAE 105k but breaks 8 plan-field samples; the
0.25 fraction retains the plan matches while roughly halving the amount error.)
