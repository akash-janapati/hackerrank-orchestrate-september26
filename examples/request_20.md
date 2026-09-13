# End-to-end trace: `request_20` (user_20)

This documents one full pipeline run: inputs → message facts → image extraction → reconciliation → forecast → simulation → capacity → candidate plans → ranking → explanation → output.

## 1. Request input (`dataset/requests.csv` or `sample_requests.csv`)

| field | value |
|---|---|
| request_id | request_20 |
| user_id | user_20 |
| request_date | 2026-02-07 |
| request_type | travel |
| requested_amount | 303700.0 |
| desired_completion_date | 2026-02-22 |
| allows_partial_payment | False |
| request_text | I can book the family trip for INR 303,700. Would it be safer to book the trip now or wait until more money comes in? |

## 2. Profile (`dataset/financial_profiles.csv`)

| field | value |
|---|---|
| home_currency | INR |
| current_available_balance | 102,609.05 |
| minimum_balance_to_keep | 64,500.00 |
| protected | ['education', 'housing', 'utilities'] |
| reducible | ['dining', 'entertainment'] |
| stoppable | ['cloud_storage'] |
| payment_methods_user_will_consider | ['full_payment', 'installments', 'partial_payment'] |
| max_installment_months | 11 |

## 3. Financial events for this user (`dataset/financial_events.csv`)

| event_id | category | direction | amount | event_date | settlement_date | status | flexibility | linked_event_id |
|---|---|---|---|---|---|---|---|---|
| event_1744 | groceries | debit | 3,866.50 | 2025-08-13 | 2025-08-13 | settled | fixed | - |
| event_1762 | transport | debit | 2,046.25 | 2025-08-14 | 2025-08-14 | settled | fixed | - |
| event_1775 | dining | debit | 3,150.77 | 2025-08-15 | 2025-08-15 | settled | reducible | - |
| event_1745 | groceries | debit | 3,724.49 | 2025-08-23 | 2025-08-23 | settled | fixed | - |
| event_1763 | transport | debit | 2,060.70 | 2025-08-28 | 2025-08-28 | settled | fixed | - |
| event_1702 | housing | debit | 7,950.00 | 2025-09-02 | 2025-09-02 | settled | fixed | - |
| event_1746 | groceries | debit | 3,127.16 | 2025-09-02 | 2025-09-02 | settled | fixed | - |
| event_1703 | utilities | debit | 7,784.29 | 2025-09-05 | 2025-09-05 | settled | fixed | - |
| event_1776 | dining | debit | 3,075.11 | 2025-09-05 | 2025-09-05 | settled | reducible | - |
| event_1704 | insurance | debit | 3,290.00 | 2025-09-06 | 2025-09-06 | settled | fixed | - |
| event_1705 | education | debit | 8,740.00 | 2025-09-07 | 2025-09-07 | settled | fixed | - |
| event_1706 | healthcare | debit | 5,968.18 | 2025-09-09 | 2025-09-09 | settled | fixed | - |
| event_1708 | cloud_storage | debit | 365.00 | 2025-09-11 | 2025-09-11 | settled | stoppable | - |
| event_1764 | transport | debit | 2,195.41 | 2025-09-11 | 2025-09-11 | settled | fixed | - |
| event_1747 | groceries | debit | 4,104.17 | 2025-09-12 | 2025-09-12 | settled | fixed | - |
| event_1707 | entertainment | debit | 2,298.76 | 2025-09-13 | 2025-09-13 | settled | reducible | - |
| event_1701 | salary | credit | 108,000.00 | 2025-09-15 | 2025-09-15 | settled | fixed | - |
| event_1748 | groceries | debit | 2,968.61 | 2025-09-22 | 2025-09-22 | settled | fixed | - |
| event_1765 | transport | debit | 2,632.00 | 2025-09-25 | 2025-09-25 | settled | fixed | - |
| event_1777 | dining | debit | 3,365.58 | 2025-09-26 | 2025-09-26 | settled | reducible | - |
| event_1710 | housing | debit | 7,950.00 | 2025-10-02 | 2025-10-02 | settled | fixed | - |
| event_1749 | groceries | debit | 4,660.33 | 2025-10-02 | 2025-10-02 | settled | fixed | - |
| event_1711 | utilities | debit | 7,977.68 | 2025-10-05 | 2025-10-05 | settled | fixed | - |
| event_1712 | insurance | debit | 3,290.00 | 2025-10-06 | 2025-10-06 | settled | fixed | - |
| event_1713 | education | debit | 8,740.00 | 2025-10-07 | 2025-10-07 | settled | fixed | - |
| event_1714 | healthcare | debit | 6,648.50 | 2025-10-09 | 2025-10-09 | settled | fixed | - |
| event_1766 | transport | debit | 3,063.34 | 2025-10-09 | 2025-10-09 | settled | fixed | - |
| event_1716 | cloud_storage | debit | 365.00 | 2025-10-11 | 2025-10-11 | settled | stoppable | - |
| event_1750 | groceries | debit | 4,109.13 | 2025-10-12 | 2025-10-12 | settled | fixed | - |
| event_1715 | entertainment | debit | 2,279.67 | 2025-10-13 | 2025-10-13 | settled | reducible | - |
| event_1709 | salary | credit | 108,000.00 | 2025-10-15 | 2025-10-15 | settled | fixed | - |
| event_1778 | dining | debit | 4,270.04 | 2025-10-17 | 2025-10-17 | settled | reducible | - |
| event_1751 | groceries | debit | 2,812.26 | 2025-10-22 | 2025-10-22 | settled | fixed | - |
| event_1767 | transport | debit | 2,359.03 | 2025-10-23 | 2025-10-23 | settled | fixed | - |
| event_1752 | groceries | debit | 3,525.04 | 2025-11-01 | 2025-11-01 | settled | fixed | - |
| event_1718 | housing | debit | 7,950.00 | 2025-11-02 | 2025-11-02 | settled | fixed | - |
| event_1719 | utilities | debit | 8,058.75 | 2025-11-05 | 2025-11-05 | settled | fixed | - |
| event_1720 | insurance | debit | 3,290.00 | 2025-11-06 | 2025-11-06 | settled | fixed | - |
| event_1768 | transport | debit | 2,628.75 | 2025-11-06 | 2025-11-06 | settled | fixed | - |
| event_1721 | education | debit | 8,740.00 | 2025-11-07 | 2025-11-07 | settled | fixed | - |
| event_1779 | dining | debit | 2,857.78 | 2025-11-07 | 2025-11-07 | settled | reducible | - |
| event_1722 | healthcare | debit | 5,907.73 | 2025-11-09 | 2025-11-09 | settled | fixed | - |
| event_1724 | cloud_storage | debit | 365.00 | 2025-11-11 | 2025-11-11 | settled | stoppable | - |
| event_1753 | groceries | debit | 3,386.09 | 2025-11-11 | 2025-11-11 | settled | fixed | - |
| event_1723 | entertainment | debit | 2,115.92 | 2025-11-13 | 2025-11-13 | settled | reducible | - |
| event_1717 | salary | credit | 108,000.00 | 2025-11-15 | 2025-11-15 | settled | fixed | - |
| event_1769 | transport | debit | 2,836.95 | 2025-11-20 | 2025-11-20 | settled | fixed | - |
| event_1754 | groceries | debit | 3,796.24 | 2025-11-21 | 2025-11-21 | settled | fixed | - |
| event_1780 | dining | debit | 4,308.23 | 2025-11-28 | 2025-11-28 | settled | reducible | - |
| event_1755 | groceries | debit | 3,016.03 | 2025-12-01 | 2025-12-01 | settled | fixed | - |
| event_1726 | housing | debit | 7,950.00 | 2025-12-02 | 2025-12-02 | settled | fixed | - |
| event_1770 | transport | debit | 2,570.15 | 2025-12-04 | 2025-12-04 | settled | fixed | - |
| event_1727 | utilities | debit | 6,848.62 | 2025-12-05 | 2025-12-05 | settled | fixed | - |
| event_1728 | insurance | debit | 3,290.00 | 2025-12-06 | 2025-12-06 | settled | fixed | - |
| event_1729 | education | debit | 8,740.00 | 2025-12-07 | 2025-12-07 | settled | fixed | - |
| event_1730 | healthcare | debit | 6,505.49 | 2025-12-09 | 2025-12-09 | settled | fixed | - |
| event_1732 | cloud_storage | debit | 365.00 | 2025-12-11 | 2025-12-11 | settled | stoppable | - |
| event_1756 | groceries | debit | 4,683.37 | 2025-12-11 | 2025-12-11 | settled | fixed | - |
| event_1731 | entertainment | debit | 1,949.86 | 2025-12-13 | 2025-12-13 | settled | reducible | - |
| event_1725 | salary | credit | 108,000.00 | 2025-12-15 | 2025-12-15 | settled | fixed | - |
| event_1771 | transport | debit | 3,145.95 | 2025-12-18 | 2025-12-18 | settled | fixed | - |
| event_1781 | dining | debit | 2,629.91 | 2025-12-19 | 2025-12-19 | settled | reducible | - |
| event_1757 | groceries | debit | 3,067.82 | 2025-12-21 | 2025-12-21 | settled | fixed | - |
| event_1758 | groceries | debit | 3,588.10 | 2025-12-31 | 2025-12-31 | settled | fixed | - |
| event_1772 | transport | debit | 2,838.14 | 2026-01-01 | 2026-01-01 | settled | fixed | - |
| event_1734 | housing | debit | 7,950.00 | 2026-01-02 | 2026-01-02 | settled | fixed | - |
| event_1735 | utilities | debit | 7,551.74 | 2026-01-05 | 2026-01-05 | settled | fixed | - |
| event_1736 | insurance | debit | 3,290.00 | 2026-01-06 | 2026-01-06 | settled | fixed | - |
| event_1737 | education | debit | 8,740.00 | 2026-01-07 | 2026-01-07 | settled | fixed | - |
| event_1738 | healthcare | debit | 6,654.33 | 2026-01-09 | 2026-01-09 | settled | fixed | - |
| event_1782 | dining | debit | 3,352.75 | 2026-01-09 | 2026-01-09 | settled | reducible | - |
| event_1759 | groceries | debit | 3,752.77 | 2026-01-10 | 2026-01-10 | settled | fixed | - |
| event_1740 | cloud_storage | debit | 365.00 | 2026-01-11 | 2026-01-11 | settled | stoppable | - |
| event_1739 | entertainment | debit | 2,097.15 | 2026-01-13 | 2026-01-13 | settled | reducible | - |
| event_1784 | shopping | debit | 8,640.00 | 2026-01-14 | 2026-01-15 | settled | fixed | - |
| event_1733 | salary | credit | 108,000.00 | 2026-01-15 | 2026-01-15 | settled | fixed | - |
| event_1773 | transport | debit | 3,150.25 | 2026-01-15 | 2026-01-15 | settled | fixed | - |
| event_1760 | groceries | debit | 3,702.16 | 2026-01-20 | 2026-01-20 | settled | fixed | - |
| event_1774 | transport | debit | 3,243.84 | 2026-01-29 | 2026-01-29 | settled | fixed | - |
| event_1761 | groceries | debit | 4,719.22 | 2026-01-30 | 2026-01-30 | settled | fixed | - |
| event_1783 | dining | debit | 3,803.95 | 2026-01-30 | 2026-01-30 | settled | reducible | - |
| event_1741 | housing | debit | 7,950.00 | 2026-02-02 | 2026-02-02 | settled | fixed | - |
| event_1785 | shopping | credit | 8,640.00 | 2026-02-04 | 2026-02-14 | pending | fixed | event_1784 |
| event_1742 | utilities | debit | 7,769.87 | 2026-02-05 | 2026-02-05 | settled | fixed | - |
| event_1743 | insurance | debit | 3,290.00 | 2026-02-06 | 2026-02-06 | settled | fixed | - |
| event_1786 | utilities | debit | None | 2026-02-06 | 2026-02-09 | pending | fixed | - |
| event_1787 | shopping | debit | 4,470.00 | 2026-02-06 | 2026-02-08 | pending | fixed | - |

## 4. Messages (`dataset/messages.csv`) and LLM-extracted facts

**message_14** (source=merchant, request=request_20, related_event=event_1785)

> CartLane has new information about your payment or refund. Your refund has been initiated but has not reached your account yet. We’ll send another update when the credit is completed. Order ref MER-0014.

Extracted facts (LLM, cached): `[{'action': 'ignore', 'category': None, 'direction': None, 'amount': None, 'currency': None, 'date': None, 'factor': None, 'recurrence': None, 'reason': 'pending refund'}]`

Summary: Pending refund, not yet credited

## 5. Images (`dataset/images.csv`) and extraction

**image_05** → event `event_1786` (`dataset/media/images/image_05.png`)

- extracted_amount: 704.05 (INR, method=llm)
- evidence_line: Total @ 704.05
- applied to forecast: False

## 6. Candidate plans and the ranking

### Payment options (`dataset/request_payment_options.csv`)

| option_id | method | payment_amount | n | first_date | frequency | fee | total |
|---|---|---|---|---|---|---|---|
| payment_option_55 | full_payment | 303,700.00 | 1 | 2026-02-07 | None | 0.00 | 303,700.00 |
| payment_option_56 | installments | 19,234.33 | 18 | 2026-02-07 | 31 | 42,517.94 | 346,217.94 |

### Forecast and simulation

- projected future events: 45 (forecast rows: 44)
- simulated minimum balance: 87,472.76 (safe=True, breach_date=2026-02-13)
- `amount_safe_to_pay` = 22,972.76 (= min_balance_after_forecast − minimum_balance, capped at requested)
- `earliest_date_for_full_payment` = None (without spending changes, preference-independent)

### Candidate plans (each re-simulated for safety)

| method | status | payments | total_paid | changes | option | rank_key |
|---|---|---|---|---|---|---|
| _none_ | | | | | | |

**Chosen (rank.choose): `not_recommended` / `not_affordable`**

## 7. Final output row (`output.csv`)

| column | value |
|---|---|
| request_id | request_20 |
| amount_safe_to_pay | 22972.762499999997 |
| affordability_status | not_affordable |
| recommended_payment_method | not_recommended |
| payment_plan | none |
| earliest_date_for_full_payment |  |
| spending_changes_needed | none |
| decision_explanation | Do not proceed with the INR 303700 request; it cannot be completed safely within the forecast period. |

## 8. Ground truth (this is a solved sample)

| field | ground truth | predicted |
|---|---|---|
| amount_safe_to_pay | 5400.0 | 22972.762499999997 |
| affordability_status | not_affordable | not_affordable |
| recommended_payment_method | not_recommended | not_recommended |
| payment_plan | none | none |
| earliest_date_for_full_payment |  |  |
| spending_changes_needed | none | none |

