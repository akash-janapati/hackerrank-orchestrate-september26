# Buy or Wait? — Sample Report

Pipeline run on the 25 solved samples (`dataset/sample_requests.csv`) and compared to the ground-truth labels. Configuration: income recurrence by cadence (amount = median); recurring expenses projected with fixed categories at median and variable categories at a calibrated fraction (config.VARIABLE_EXPENSE_FRACTION); monthly occurrences include the request month; debits-first 90-day simulator; plan generation + 6-level ranker; LLM structured message facts; settled-only image amount overrides; LLM explanations.

## Executive summary

- **Amount exact:** 4/25 (16%)
- **Amount MAE:** 471,047.46 · median error: 597.74
- **Plan-field row match** (status+method+plan+changes): 14/25
- **Status match:** 18/25 · **Method match:** 20/25 · **Plan match:** 17/25

`amount_safe_to_pay` is bounded by the missing hidden future timeline (see `implementation.md` §3): the released events stop at `request_date`, and future per-occurrence amounts are not recoverable. Plan fields are downstream of the amount.

## Per-field accuracy

| field | exact | rate |
|---|---|---|
| `amount_safe_to_pay` | 4/25 | 16% |
| `affordability_status` | 18/25 | 72% |
| `recommended_payment_method` | 20/25 | 80% |
| `payment_plan` | 17/25 | 68% |
| `earliest_date_for_full_payment` | 10/25 | 40% |
| `spending_changes_needed` | 22/25 | 88% |

## Amount error statistics

- exact (abs <= 0.01): 4/25
- within 1: 4/25
- within 1% of GT: 5/25
- MAE: 471,047.46
- median: 597.74
- max: 4,291,200.00

## Effect of the evidence layer (ablation)

| configuration | amount exact | amount MAE | plan-field rows |
|---|---|---|---|
| core (no messages/images) | 4/25 | 471,069.81 | 14/25 |
| + messages only | 4/25 | 471,069.81 | 14/25 |
| + messages + settled images | 4/25 | 471,047.46 | 14/25 |

The message and settled-image layers are MAE-neutral on these 25 samples; messages raise full-set actionability (`not_affordable` drops) and the improvement here comes from the forecast itself (income by cadence + calibrated variable-expense projection + request-month occurrences).

## Breakdown by request type

| request_type | n | amount MAE | status | method | plan |
|---|---|---|---|---|---|
| debt_repayment | 3 | 5,142.06 | 1/3 | 1/3 | 1/3 |
| education | 3 | 155,914.14 | 2/3 | 3/3 | 2/3 |
| emergency_expense | 2 | 12,333.77 | 2/2 | 2/2 | 1/2 |
| family_transfer | 3 | 1,430,576.27 | 1/3 | 1/3 | 1/3 |
| housing | 3 | 1,355,885.71 | 3/3 | 3/3 | 3/3 |
| investment | 3 | 3,253.12 | 2/3 | 3/3 | 3/3 |
| other | 2 | 139.43 | 2/2 | 2/2 | 1/2 |
| purchase | 3 | 88,280.00 | 3/3 | 2/3 | 2/3 |
| travel | 3 | 878,028.72 | 2/3 | 3/3 | 3/3 |

## Ground-truth status vs predicted

| GT \ pred | affordable_now | affordable_with_plan | affordable_later | not_affordable |
|---|---|---|---|---|
| affordable_now | 3 | 0 | 0 | 0 |
| affordable_with_plan | 3 | 6 | 0 | 0 |
| affordable_later | 2 | 0 | 3 | 1 |
| not_affordable | 1 | 0 | 0 | 6 |

## Per-sample comparison

| request | type | GT status | pred status | GT method | pred method | GT safe | pred safe | abs err | earliest | changes |
|---|---|---|---|---|---|---|---|---|---|---|
| request_01 | purchase | affordable_now | affordable_now | full_payment | full_payment | 25,256.00 | 25,256.00 == | 0.00 | 2024-03-03 / 2024-03-03 | none / none |
| request_02 | travel | affordable_with_plan | affordable_with_plan | installments | installments | 17,229,139.20 | 19,246,297.61 !! | 2,017,158.41 | 2025-09-15 / 2025-09-16 | none / none |
| request_03 | education | affordable_later | affordable_later | wait | wait | 873,000.00 | 1,340,711.37 !! | 467,711.37 | 2019-11-15 / 2019-10-16 | none / none |
| request_04 | family_transfer | affordable_later | affordable_now | wait | full_payment | 8,401,800.00 | 12,693,000.00 !! | 4,291,200.00 | 2024-06-15 / 2024-06-04 | none / none |
| request_05 | debt_repayment | not_affordable | affordable_now | not_recommended | full_payment | 737.00 | 15,488.00 !! | 14,751.00 | - / 2025-11-06 | none / none |
| request_06 | investment | affordable_with_plan | affordable_now | full_payment | full_payment | 603.30 | 620.40 !! | 17.10 | 2026-01-15 / 2026-01-03 | stop:event_476 / none |
| request_07 | housing | affordable_with_plan | affordable_with_plan | installments | installments | 87,170.56 | 100,469.62 !! | 13,299.06 | 2024-10-23 / 2024-10-16 | none / none |
| request_08 | emergency_expense | affordable_later | affordable_later | wait | wait | 284.57 | 488.24 !! | 203.67 | 2025-04-15 / 2025-03-16 | none / none |
| request_09 | other | affordable_now | affordable_now | full_payment | full_payment | 166.61 | 166.61 == | 0.00 | 2026-07-04 / 2026-07-04 | none / none |
| request_10 | purchase | not_affordable | not_affordable | not_recommended | not_recommended | 12,700.00 | 266,700.00 !! | 254,000.00 | - / - | none / none |
| request_11 | travel | affordable_with_plan | affordable_now | full_payment | full_payment | 12,510,645.00 | 13,110,000.00 !! | 599,355.00 | 2025-07-15 / 2025-05-03 | reduce_to:event_989:665950 / none |
| request_12 | education | affordable_with_plan | affordable_with_plan | installments | installments | 65,164.00 | 65,164.00 == | 0.00 | 2026-04-05 / 2026-04-05 | none / none |
| request_13 | family_transfer | affordable_later | affordable_now | wait | full_payment | 433.40 | 941.60 !! | 508.20 | 2024-05-15 / 2024-03-07 | none / none |
| request_14 | debt_repayment | not_affordable | not_affordable | not_recommended | not_recommended | 597.74 | 0.00 !! | 597.74 | - / - | none / none |
| request_15 | investment | not_affordable | not_affordable | not_recommended | not_recommended | 83.05 | 0.00 !! | 83.05 | - / - | none / none |
| request_16 | housing | affordable_now | affordable_now | full_payment | full_payment | 122,500.00 | 122,500.00 == | 0.00 | 2023-08-12 / 2023-08-12 | none / none |
| request_17 | emergency_expense | affordable_with_plan | affordable_with_plan | installments | installments | 243,849.58 | 268,313.45 !! | 24,463.87 | 2026-03-15 / 2026-03-16 | none / none |
| request_18 | other | affordable_later | affordable_later | wait | wait | 462.00 | 740.87 !! | 278.87 | 2026-09-15 / 2026-08-16 | none / none |
| request_19 | purchase | affordable_with_plan | affordable_with_plan | partial_payment | installments | 28,820.00 | 39,660.00 !! | 10,840.00 | 2024-09-15 / 2024-09-04 | none / none |
| request_20 | travel | not_affordable | not_affordable | not_recommended | not_recommended | 5,400.00 | 22,972.76 !! | 17,572.76 | - / - | none / none |
| request_21 | education | affordable_with_plan | affordable_now | full_payment | full_payment | 1,543.35 | 1,574.40 !! | 31.05 | 2026-04-15 / 2026-04-03 | stop:event_1815|reduce_to:event_1816:23.50 / none |
| request_22 | family_transfer | affordable_with_plan | affordable_with_plan | installments | installments | 475.46 | 496.07 !! | 20.61 | 2025-01-15 / 2024-12-16 | none / none |
| request_23 | debt_repayment | affordable_later | not_affordable | wait | not_recommended | 9,152.00 | 9,229.43 !! | 77.43 | 2025-07-15 / - | none / none |
| request_24 | investment | not_affordable | not_affordable | not_recommended | not_recommended | 13,420.00 | 23,079.21 !! | 9,659.21 | - / - | none / none |
| request_25 | housing | not_affordable | not_affordable | not_recommended | not_recommended | 1,425,000.00 | 5,479,358.08 !! | 4,054,358.08 | - / - | none / none |

## Mismatch attribution

- 19: under-reserved (pred > GT)
- 7: status differs
- 5: method differs
- 3: expected a spending change not emitted
- 2: over-reserved (pred < GT)

## Representative full comparisons

### request_02 (user_02, travel)

- request: 2025-08-05 → 2025-10-10, amount 46,018,000.00, partial=False
- `amount_safe_to_pay`: GT `17,229,139.20` · pred `19,246,297.61`  ← differs
- `affordability_status`: GT `affordable_with_plan` · pred `affordable_with_plan`
- `recommended_payment_method`: GT `installments` · pred `installments`
- `payment_plan`: GT `2025-08-08:15952906.67|2025-09-07:15952906.67|2025-10-07:15952906.67` · pred `2025-08-08:15952906.67|2025-09-07:15952906.67|2025-10-07:15952906.67`
- `earliest_date_for_full_payment`: GT `2025-09-15` · pred `2025-09-16`  ← differs
- `spending_changes_needed`: GT `none` · pred `none`

### request_03 (user_03, education)

- request: 2019-09-03 → 2019-11-15, amount 5,491,000.00, partial=False
- `amount_safe_to_pay`: GT `873,000.00` · pred `1,340,711.37`  ← differs
- `affordability_status`: GT `affordable_later` · pred `affordable_later`
- `recommended_payment_method`: GT `wait` · pred `wait`
- `payment_plan`: GT `2019-11-15:5491000` · pred `2019-10-16:5491000`  ← differs
- `earliest_date_for_full_payment`: GT `2019-11-15` · pred `2019-10-16`  ← differs
- `spending_changes_needed`: GT `none` · pred `none`

### request_04 (user_04, family_transfer)

- request: 2024-06-04 → 2024-06-19, amount 12,693,000.00, partial=True
- `amount_safe_to_pay`: GT `8,401,800.00` · pred `12,693,000.00`  ← differs
- `affordability_status`: GT `affordable_later` · pred `affordable_now`  ← differs
- `recommended_payment_method`: GT `wait` · pred `full_payment`  ← differs
- `payment_plan`: GT `2024-06-15:12693000` · pred `2024-06-04:12693000`  ← differs
- `earliest_date_for_full_payment`: GT `2024-06-15` · pred `2024-06-04`  ← differs
- `spending_changes_needed`: GT `none` · pred `none`

### request_05 (user_05, debt_repayment)

- request: 2025-11-06 → 2026-01-12, amount 15,488.00, partial=False
- `amount_safe_to_pay`: GT `737.00` · pred `15,488.00`  ← differs
- `affordability_status`: GT `not_affordable` · pred `affordable_now`  ← differs
- `recommended_payment_method`: GT `not_recommended` · pred `full_payment`  ← differs
- `payment_plan`: GT `none` · pred `2025-11-06:15488`  ← differs
- `earliest_date_for_full_payment`: GT `` · pred `2025-11-06`  ← differs
- `spending_changes_needed`: GT `none` · pred `none`

### request_06 (user_06, investment)

- request: 2026-01-03 → 2026-01-14, amount 620.40, partial=False
- `amount_safe_to_pay`: GT `603.30` · pred `620.40`  ← differs
- `affordability_status`: GT `affordable_with_plan` · pred `affordable_now`  ← differs
- `recommended_payment_method`: GT `full_payment` · pred `full_payment`
- `payment_plan`: GT `2026-01-03:620.40` · pred `2026-01-03:620.40`
- `earliest_date_for_full_payment`: GT `2026-01-15` · pred `2026-01-03`  ← differs
- `spending_changes_needed`: GT `stop:event_476` · pred `none`  ← differs

### request_07 (user_07, housing)

- request: 2024-09-05 → 2024-11-14, amount 197,400.00, partial=True
- `amount_safe_to_pay`: GT `87,170.56` · pred `100,469.62`  ← differs
- `affordability_status`: GT `affordable_with_plan` · pred `affordable_with_plan`
- `recommended_payment_method`: GT `installments` · pred `installments`
- `payment_plan`: GT `2024-09-12:68432|2024-10-10:68432|2024-11-07:68432` · pred `2024-09-12:68432|2024-10-10:68432|2024-11-07:68432`
- `earliest_date_for_full_payment`: GT `2024-10-23` · pred `2024-10-16`  ← differs
- `spending_changes_needed`: GT `none` · pred `none`

### request_08 (user_08, emergency_expense)

- request: 2025-02-07 → 2025-04-15, amount 996.60, partial=False
- `amount_safe_to_pay`: GT `284.57` · pred `488.24`  ← differs
- `affordability_status`: GT `affordable_later` · pred `affordable_later`
- `recommended_payment_method`: GT `wait` · pred `wait`
- `payment_plan`: GT `2025-04-15:996.60` · pred `2025-03-16:996.60`  ← differs
- `earliest_date_for_full_payment`: GT `2025-04-15` · pred `2025-03-16`  ← differs
- `spending_changes_needed`: GT `none` · pred `none`

### request_10 (user_10, purchase)

- request: 2024-12-06 → 2025-02-10, amount 266,700.00, partial=True
- `amount_safe_to_pay`: GT `12,700.00` · pred `266,700.00`  ← differs
- `affordability_status`: GT `not_affordable` · pred `not_affordable`
- `recommended_payment_method`: GT `not_recommended` · pred `not_recommended`
- `payment_plan`: GT `none` · pred `none`
- `earliest_date_for_full_payment`: GT `` · pred ``
- `spending_changes_needed`: GT `none` · pred `none`

### request_11 (user_11, travel)

- request: 2025-05-03 → 2025-06-12, amount 13,110,000.00, partial=False
- `amount_safe_to_pay`: GT `12,510,645.00` · pred `13,110,000.00`  ← differs
- `affordability_status`: GT `affordable_with_plan` · pred `affordable_now`  ← differs
- `recommended_payment_method`: GT `full_payment` · pred `full_payment`
- `payment_plan`: GT `2025-05-03:13110000` · pred `2025-05-03:13110000`
- `earliest_date_for_full_payment`: GT `2025-07-15` · pred `2025-05-03`  ← differs
- `spending_changes_needed`: GT `reduce_to:event_989:665950` · pred `none`  ← differs

### request_13 (user_13, family_transfer)

- request: 2024-03-07 → 2024-05-15, amount 941.60, partial=True
- `amount_safe_to_pay`: GT `433.40` · pred `941.60`  ← differs
- `affordability_status`: GT `affordable_later` · pred `affordable_now`  ← differs
- `recommended_payment_method`: GT `wait` · pred `full_payment`  ← differs
- `payment_plan`: GT `2024-05-15:941.60` · pred `2024-03-07:941.60`  ← differs
- `earliest_date_for_full_payment`: GT `2024-05-15` · pred `2024-03-07`  ← differs
- `spending_changes_needed`: GT `none` · pred `none`

### request_14 (user_14, debt_repayment)

- request: 2025-08-04 → 2025-10-04, amount 5,414.20, partial=True
- `amount_safe_to_pay`: GT `597.74` · pred `0.00`  ← differs
- `affordability_status`: GT `not_affordable` · pred `not_affordable`
- `recommended_payment_method`: GT `not_recommended` · pred `not_recommended`
- `payment_plan`: GT `none` · pred `none`
- `earliest_date_for_full_payment`: GT `` · pred ``
- `spending_changes_needed`: GT `none` · pred `none`

### request_15 (user_15, investment)

- request: 2026-01-06 → 2026-02-01, amount 3,685.00, partial=False
- `amount_safe_to_pay`: GT `83.05` · pred `0.00`  ← differs
- `affordability_status`: GT `not_affordable` · pred `not_affordable`
- `recommended_payment_method`: GT `not_recommended` · pred `not_recommended`
- `payment_plan`: GT `none` · pred `none`
- `earliest_date_for_full_payment`: GT `` · pred ``
- `spending_changes_needed`: GT `none` · pred `none`

### request_17 (user_17, emergency_expense)

- request: 2026-03-01 → 2026-05-04, amount 274,600.00, partial=False
- `amount_safe_to_pay`: GT `243,849.58` · pred `268,313.45`  ← differs
- `affordability_status`: GT `affordable_with_plan` · pred `affordable_with_plan`
- `recommended_payment_method`: GT `installments` · pred `installments`
- `payment_plan`: GT `2026-03-01:95194.67|2026-03-31:95194.67|2026-04-30:95194.67` · pred `2026-03-01:95194.67|2026-03-31:95194.67|2026-04-30:95194.67`
- `earliest_date_for_full_payment`: GT `2026-03-15` · pred `2026-03-16`  ← differs
- `spending_changes_needed`: GT `none` · pred `none`

### request_18 (user_18, other)

- request: 2026-07-07 → 2026-09-15, amount 3,246.10, partial=False
- `amount_safe_to_pay`: GT `462.00` · pred `740.87`  ← differs
- `affordability_status`: GT `affordable_later` · pred `affordable_later`
- `recommended_payment_method`: GT `wait` · pred `wait`
- `payment_plan`: GT `2026-09-15:3246.10` · pred `2026-08-16:3246.10`  ← differs
- `earliest_date_for_full_payment`: GT `2026-09-15` · pred `2026-08-16`  ← differs
- `spending_changes_needed`: GT `none` · pred `none`

### request_19 (user_19, purchase)

- request: 2024-09-04 → 2024-10-04, amount 39,660.00, partial=True
- `amount_safe_to_pay`: GT `28,820.00` · pred `39,660.00`  ← differs
- `affordability_status`: GT `affordable_with_plan` · pred `affordable_with_plan`
- `recommended_payment_method`: GT `partial_payment` · pred `installments`  ← differs
- `payment_plan`: GT `2024-09-04:28820|2024-09-15:10840` · pred `2024-09-04:20623.20|2024-10-02:20623.20`  ← differs
- `earliest_date_for_full_payment`: GT `2024-09-15` · pred `2024-09-04`  ← differs
- `spending_changes_needed`: GT `none` · pred `none`

### request_20 (user_20, travel)

- request: 2026-02-07 → 2026-02-22, amount 303,700.00, partial=False
- `amount_safe_to_pay`: GT `5,400.00` · pred `22,972.76`  ← differs
- `affordability_status`: GT `not_affordable` · pred `not_affordable`
- `recommended_payment_method`: GT `not_recommended` · pred `not_recommended`
- `payment_plan`: GT `none` · pred `none`
- `earliest_date_for_full_payment`: GT `` · pred ``
- `spending_changes_needed`: GT `none` · pred `none`

### request_21 (user_21, education)

- request: 2026-04-03 → 2026-04-14, amount 1,574.40, partial=False
- `amount_safe_to_pay`: GT `1,543.35` · pred `1,574.40`  ← differs
- `affordability_status`: GT `affordable_with_plan` · pred `affordable_now`  ← differs
- `recommended_payment_method`: GT `full_payment` · pred `full_payment`
- `payment_plan`: GT `2026-04-03:1574.40` · pred `2026-04-03:1574.40`
- `earliest_date_for_full_payment`: GT `2026-04-15` · pred `2026-04-03`  ← differs
- `spending_changes_needed`: GT `stop:event_1815|reduce_to:event_1816:23.50` · pred `none`  ← differs

### request_22 (user_22, family_transfer)

- request: 2024-12-05 → 2025-02-10, amount 731.50, partial=True
- `amount_safe_to_pay`: GT `475.46` · pred `496.07`  ← differs
- `affordability_status`: GT `affordable_with_plan` · pred `affordable_with_plan`
- `recommended_payment_method`: GT `installments` · pred `installments`
- `payment_plan`: GT `2024-12-08:253.59|2025-01-05:253.59|2025-02-02:253.59` · pred `2024-12-08:253.59|2025-01-05:253.59|2025-02-02:253.59`
- `earliest_date_for_full_payment`: GT `2025-01-15` · pred `2024-12-16`  ← differs
- `spending_changes_needed`: GT `none` · pred `none`

### request_23 (user_23, debt_repayment)

- request: 2025-05-07 → 2025-07-15, amount 38,016.00, partial=False
- `amount_safe_to_pay`: GT `9,152.00` · pred `9,229.43`  ← differs
- `affordability_status`: GT `affordable_later` · pred `not_affordable`  ← differs
- `recommended_payment_method`: GT `wait` · pred `not_recommended`  ← differs
- `payment_plan`: GT `2025-07-15:38016` · pred `none`  ← differs
- `earliest_date_for_full_payment`: GT `2025-07-15` · pred ``  ← differs
- `spending_changes_needed`: GT `none` · pred `none`

### request_24 (user_24, investment)

- request: 2026-01-04 → 2026-02-08, amount 109,600.00, partial=True
- `amount_safe_to_pay`: GT `13,420.00` · pred `23,079.21`  ← differs
- `affordability_status`: GT `not_affordable` · pred `not_affordable`
- `recommended_payment_method`: GT `not_recommended` · pred `not_recommended`
- `payment_plan`: GT `none` · pred `none`
- `earliest_date_for_full_payment`: GT `` · pred ``
- `spending_changes_needed`: GT `none` · pred `none`

### request_25 (user_25, housing)

- request: 2024-03-06 → 2024-04-17, amount 60,496,000.00, partial=True
- `amount_safe_to_pay`: GT `1,425,000.00` · pred `5,479,358.08`  ← differs
- `affordability_status`: GT `not_affordable` · pred `not_affordable`
- `recommended_payment_method`: GT `not_recommended` · pred `not_recommended`
- `payment_plan`: GT `none` · pred `none`
- `earliest_date_for_full_payment`: GT `` · pred ``
- `spending_changes_needed`: GT `none` · pred `none`

## Notes

- The deterministic engine is byte-reproducible; sample predictions come from the same code path as `output.csv`.
- Image amounts are applied only to settled (historical) blank events; pending/scheduled blanks are cached but not applied (request_16 case).
- Message handling is regex-only (no LLM).

