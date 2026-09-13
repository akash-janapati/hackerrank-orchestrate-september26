# End-to-end trace: `request_03` (user_03)

This documents one full pipeline run: inputs → message facts → image extraction → reconciliation → forecast → simulation → capacity → candidate plans → ranking → explanation → output.

## 1. Request input (`dataset/requests.csv` or `sample_requests.csv`)

| field | value |
|---|---|
| request_id | request_03 |
| user_id | user_03 |
| request_date | 2019-09-03 |
| request_type | education |
| requested_amount | 5491000.0 |
| desired_completion_date | 2019-11-15 |
| allows_partial_payment | False |
| request_text | Should I pay for the course now, use installments, or wait? I need to decide by 15 November 2019. The course I want to take is IDR 5,491,000. |

## 2. Profile (`dataset/financial_profiles.csv`)

| field | value |
|---|---|
| home_currency | IDR |
| current_available_balance | 5,810,300.00 |
| minimum_balance_to_keep | 2,668,700.00 |
| protected | ['groceries', 'rent', 'utilities'] |
| reducible | ['shopping', 'streaming'] |
| stoppable | ['cloud_storage', 'streaming'] |
| payment_methods_user_will_consider | ['full_payment', 'installments', 'partial_payment'] |
| max_installment_months | 2 |

## 3. Financial events for this user (`dataset/financial_events.csv`)

| event_id | category | direction | amount | event_date | settlement_date | status | flexibility | linked_event_id |
|---|---|---|---|---|---|---|---|---|
| event_244 | dining | debit | 117,456.78 | 2019-03-09 | 2019-03-09 | settled | fixed | - |
| event_217 | groceries | debit | 159,576.52 | 2019-03-12 | 2019-03-12 | settled | fixed | - |
| event_235 | transport | debit | 81,510.25 | 2019-03-13 | 2019-03-13 | settled | fixed | - |
| event_218 | groceries | debit | 234,390.87 | 2019-03-22 | 2019-03-22 | settled | fixed | - |
| event_245 | dining | debit | 141,412.46 | 2019-03-30 | 2019-03-30 | settled | fixed | - |
| event_219 | groceries | debit | 230,312.98 | 2019-04-01 | 2019-04-01 | settled | fixed | - |
| event_236 | transport | debit | 116,319.21 | 2019-04-03 | 2019-04-03 | settled | fixed | - |
| event_187 | rent | debit | 1,140,000.00 | 2019-04-04 | 2019-04-04 | settled | fixed | - |
| event_188 | utilities | debit | 295,330.29 | 2019-04-08 | 2019-04-08 | settled | fixed | - |
| event_190 | streaming | debit | 117,800.00 | 2019-04-11 | 2019-04-11 | settled | reducible_or_stoppable | - |
| event_220 | groceries | debit | 234,602.65 | 2019-04-11 | 2019-04-11 | settled | fixed | - |
| event_189 | cloud_storage | debit | 20,900.00 | 2019-04-14 | 2019-04-14 | settled | stoppable | - |
| event_191 | shopping | debit | 151,493.37 | 2019-04-14 | 2019-04-14 | settled | reducible | - |
| event_186 | salary | credit | 4,365,000.00 | 2019-04-15 | 2019-04-15 | settled | fixed | - |
| event_246 | dining | debit | 146,236.28 | 2019-04-20 | 2019-04-20 | settled | fixed | - |
| event_221 | groceries | debit | 209,875.85 | 2019-04-21 | 2019-04-21 | settled | fixed | - |
| event_237 | transport | debit | 71,790.29 | 2019-04-24 | 2019-04-24 | settled | fixed | - |
| event_222 | groceries | debit | 178,469.49 | 2019-05-01 | 2019-05-01 | settled | fixed | - |
| event_193 | rent | debit | 1,140,000.00 | 2019-05-04 | 2019-05-04 | settled | fixed | - |
| event_194 | utilities | debit | 290,684.15 | 2019-05-08 | 2019-05-08 | settled | fixed | - |
| event_196 | streaming | debit | 117,800.00 | 2019-05-11 | 2019-05-11 | settled | reducible_or_stoppable | - |
| event_223 | groceries | debit | 180,577.99 | 2019-05-11 | 2019-05-11 | settled | fixed | - |
| event_247 | dining | debit | 132,247.64 | 2019-05-11 | 2019-05-11 | settled | fixed | - |
| event_195 | cloud_storage | debit | 20,900.00 | 2019-05-14 | 2019-05-14 | settled | stoppable | - |
| event_197 | shopping | debit | 184,274.02 | 2019-05-14 | 2019-05-14 | settled | reducible | - |
| event_192 | salary | credit | 4,365,000.00 | 2019-05-15 | 2019-05-15 | settled | fixed | - |
| event_238 | transport | debit | 73,531.06 | 2019-05-15 | 2019-05-15 | settled | fixed | - |
| event_224 | groceries | debit | 155,851.46 | 2019-05-21 | 2019-05-21 | settled | fixed | - |
| event_225 | groceries | debit | 188,355.72 | 2019-05-31 | 2019-05-31 | settled | fixed | - |
| event_248 | dining | debit | 158,476.50 | 2019-06-01 | 2019-06-01 | settled | fixed | - |
| event_199 | rent | debit | 1,140,000.00 | 2019-06-04 | 2019-06-04 | settled | fixed | - |
| event_239 | transport | debit | 106,806.88 | 2019-06-05 | 2019-06-05 | settled | fixed | - |
| event_200 | utilities | debit | 270,537.63 | 2019-06-08 | 2019-06-08 | settled | fixed | - |
| event_226 | groceries | debit | 166,710.61 | 2019-06-10 | 2019-06-10 | settled | fixed | - |
| event_202 | streaming | debit | 117,800.00 | 2019-06-11 | 2019-06-11 | settled | reducible_or_stoppable | - |
| event_201 | cloud_storage | debit | 20,900.00 | 2019-06-14 | 2019-06-14 | settled | stoppable | - |
| event_203 | shopping | debit | 153,395.26 | 2019-06-14 | 2019-06-14 | settled | reducible | - |
| event_198 | salary | credit | 4,365,000.00 | 2019-06-15 | 2019-06-15 | settled | fixed | - |
| event_227 | groceries | debit | 171,495.67 | 2019-06-20 | 2019-06-20 | settled | fixed | - |
| event_249 | dining | debit | 175,170.67 | 2019-06-22 | 2019-06-22 | settled | fixed | - |
| event_240 | transport | debit | 79,693.97 | 2019-06-26 | 2019-06-26 | settled | fixed | - |
| event_228 | groceries | debit | 145,691.38 | 2019-06-30 | 2019-06-30 | settled | fixed | - |
| event_205 | rent | debit | 1,140,000.00 | 2019-07-04 | 2019-07-04 | settled | fixed | - |
| event_206 | utilities | debit | 303,042.45 | 2019-07-08 | 2019-07-08 | settled | fixed | - |
| event_229 | groceries | debit | 171,259.18 | 2019-07-10 | 2019-07-10 | settled | fixed | - |
| event_208 | streaming | debit | 117,800.00 | 2019-07-11 | 2019-07-11 | settled | reducible_or_stoppable | - |
| event_250 | dining | debit | 171,303.21 | 2019-07-13 | 2019-07-13 | settled | fixed | - |
| event_207 | cloud_storage | debit | 20,900.00 | 2019-07-14 | 2019-07-14 | settled | stoppable | - |
| event_209 | shopping | debit | 173,930.81 | 2019-07-14 | 2019-07-14 | settled | reducible | - |
| event_204 | salary | credit | 4,365,000.00 | 2019-07-15 | 2019-07-15 | settled | fixed | - |
| event_241 | transport | debit | 83,523.33 | 2019-07-17 | 2019-07-17 | settled | fixed | - |
| event_230 | groceries | debit | 173,004.74 | 2019-07-20 | 2019-07-20 | settled | fixed | - |
| event_231 | groceries | debit | 214,266.98 | 2019-07-30 | 2019-07-30 | settled | fixed | - |
| event_251 | dining | debit | 171,191.99 | 2019-08-03 | 2019-08-03 | settled | fixed | - |
| event_212 | rent | debit | 1,140,000.00 | 2019-08-04 | 2019-08-04 | settled | fixed | - |
| event_242 | transport | debit | 99,961.13 | 2019-08-07 | 2019-08-07 | settled | fixed | - |
| event_213 | utilities | debit | 262,344.55 | 2019-08-08 | 2019-08-08 | settled | fixed | - |
| event_232 | groceries | debit | 221,578.88 | 2019-08-09 | 2019-08-09 | settled | fixed | - |
| event_215 | streaming | debit | 117,800.00 | 2019-08-11 | 2019-08-11 | settled | reducible_or_stoppable | - |
| event_214 | cloud_storage | debit | 20,900.00 | 2019-08-14 | 2019-08-14 | settled | stoppable | - |
| event_216 | shopping | debit | 180,395.29 | 2019-08-14 | 2019-08-14 | settled | reducible | - |
| event_210 | salary | credit | 4,365,000.00 | 2019-08-15 | 2019-08-15 | settled | fixed | - |
| event_233 | groceries | debit | 240,706.45 | 2019-08-19 | 2019-08-19 | settled | fixed | - |
| event_211 | salary | credit | 1,964,250.00 | 2019-08-20 | 2019-08-20 | settled | fixed | - |
| event_252 | dining | debit | 135,718.35 | 2019-08-24 | 2019-08-24 | settled | fixed | - |
| event_243 | transport | debit | 106,233.46 | 2019-08-28 | 2019-08-28 | settled | fixed | - |
| event_234 | groceries | debit | 200,238.72 | 2019-08-29 | 2019-08-29 | settled | fixed | - |
| event_253 | salary | credit | None | 2019-08-31 | 2019-08-31 | settled | fixed | - |
| event_254 | healthcare | debit | 95,000.00 | 2019-09-02 | 2019-09-07 | pending | fixed | - |

## 4. Messages (`dataset/messages.csv`) and LLM-extracted facts

**message_02** (source=employer, request=request_03, related_event=-)

> Tim payroll BrightPath Media telah mengirim pembaruan. Gaji rutin untuk penggajian berikutnya sudah dikonfirmasi. Slip gaji berikutnya akan menampilkan gaji rutin dan penyesuaian satu kali secara terpisah. Ref payroll EMP-0002.

Extracted facts (LLM, cached): `[{'action': 'set_income_amount', 'category': 'salary', 'direction': 'credit', 'amount': None, 'currency': None, 'date': None, 'factor': None, 'recurrence': 'monthly', 'reason': None}]`

Summary: Salary update confirmed for next payroll with one-time adjustment.

## 5. Images (`dataset/images.csv`) and extraction

**image_01** → event `event_253` (`dataset/media/images/image_01.png`)

- extracted_amount: 4365000 (IDR, method=llm)
- evidence_line: Net Pay : IDR 4,365,000
- applied to forecast: True

## 6. Candidate plans and the ranking

### Payment options (`dataset/request_payment_options.csv`)

| option_id | method | payment_amount | n | first_date | frequency | fee | total |
|---|---|---|---|---|---|---|---|
| payment_option_08 | full_payment | 5,491,000.00 | 1 | 2019-09-03 | None | 0.00 | 5,491,000.00 |
| payment_option_09 | installments | 308,541.90 | 21 | 2019-09-17 | 28 | 988,379.90 | 6,479,379.90 |
| payment_option_10 | installments | 279,125.83 | 24 | 2019-09-06 | 31 | 1,208,019.92 | 6,699,019.92 |

### Forecast and simulation

- projected future events: 9 (forecast rows: 8)
- simulated minimum balance: 4,436,600.00 (safe=True, breach_date=2019-10-14)
- `amount_safe_to_pay` = 1,767,900.00 (= min_balance_after_forecast − minimum_balance, capped at requested)
- `earliest_date_for_full_payment` = 2019-11-16 (without spending changes, preference-independent)

### Candidate plans (each re-simulated for safety)

| method | status | payments | total_paid | changes | option | rank_key |
|---|---|---|---|---|---|---|
| _none_ | | | | | | |

**Chosen (rank.choose): `not_recommended` / `not_affordable`**

## 7. Final output row (`output.csv`)

| column | value |
|---|---|
| request_id | request_03 |
| amount_safe_to_pay | 1767900.0 |
| affordability_status | not_affordable |
| recommended_payment_method | not_recommended |
| payment_plan | none |
| earliest_date_for_full_payment |  |
| spending_changes_needed | none |
| decision_explanation | The requested amount of IDR 5,491,000 for education is not affordable, as the safe amount to pay is only IDR 1,767,900, and no payment plan or spending changes are recommended. |

## 8. Ground truth (this is a solved sample)

| field | ground truth | predicted |
|---|---|---|
| amount_safe_to_pay | 873000.0 | 1767900.0 |
| affordability_status | affordable_later | not_affordable |
| recommended_payment_method | wait | not_recommended |
| payment_plan | 2019-11-15:5491000 | none |
| earliest_date_for_full_payment | 2019-11-15 |  |
| spending_changes_needed | none | none |

