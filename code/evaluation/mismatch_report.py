"""Phase 2 acceptance: per-sample plan-field match + mismatch classification.

Classification:
  forecast-driven - the expected plan exists and is eligible, but is deemed
                    unsafe under our projected timeline (our amount/forecast is
                    the cause); or the expected verdict is not_affordable while
                    our forecast says otherwise.
  rule-driven     - the expected plan is safe under our forecast but we failed to
                    generate/choose it, or eligibility/option matching disagrees.

Run: python3 code/evaluation/mismatch_report.py
"""
from __future__ import annotations

import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
sys.path.insert(0, CODE_DIR)

import config  # noqa: E402
import forecast  # noqa: E402
import ingest  # noqa: E402
import main as pipeline  # noqa: E402
import reconcile  # noqa: E402
import validate  # noqa: E402
from domain import Payment, SpendingChange  # noqa: E402
from simulate import simulate  # noqa: E402

SAMPLES = ingest.load_requests(config.SAMPLE_REQUESTS_CSV)
PROFILES = ingest.load_profiles()
EVENTS = ingest.load_events()
OPTIONS = ingest.load_options()
RATES = ingest.load_rates()

FIELDS = ["affordability_status", "recommended_payment_method", "payment_plan",
          "spending_changes_needed"]


def _parse_plan(text):
    if not text or text == "none":
        return []
    payments = []
    for part in text.split("|"):
        day, amount = part.split(":")
        payments.append(Payment(date.fromisoformat(day), float(amount)))
    return payments


def _parse_changes(text, history_by_id):
    if not text or text == "none":
        return []
    changes = []
    for part in text.split("|"):
        chunks = part.split(":")
        if chunks[0] == "stop":
            event = history_by_id.get(chunks[1])
            changes.append(SpendingChange("stop", chunks[1], None, event.category if event else None))
        else:
            event = history_by_id.get(chunks[1])
            changes.append(SpendingChange("reduce_to", chunks[1], float(chunks[2]),
                                          event.category if event else None))
    return changes


def _option_matches(option, payments):
    freq = option.frequency_days or 0
    schedule = [(option.first_payment_date, option.payment_amount)] * 0
    from datetime import timedelta
    schedule = [
        (option.first_payment_date + timedelta(days=freq * i), option.payment_amount)
        for i in range(option.number_of_payments)
    ]
    if len(schedule) != len(payments):
        return False
    return all(a == p.date and abs(b - p.amount) <= 0.011
               for (a, b), p in zip(schedule, payments))


def classify(sample, profile, history, future, options):
    expected = sample.expected
    method = expected.recommended_payment_method

    if method == "not_recommended":
        return "forecast-driven: expected not_affordable but our forecast is more optimistic"

    required = {
        "wait": "full_payment",
        "full_payment": "full_payment",
        "partial_payment": "partial_payment",
        "installments": "installments",
    }[method]
    if required not in profile.methods:
        return f"rule-driven: {required} not in payment_methods_user_will_consider"
    if method == "partial_payment" and not sample.allows_partial_payment:
        return "rule-driven: partial not allowed by request"
    if method == "installments":
        payments = _parse_plan(expected.payment_plan)
        if not any(_option_matches(o, payments) for o in options):
            return "rule-driven: expected plan matches no supplied option"
        if (profile.max_installment_months is not None
                and payments and len(payments) > profile.max_installment_months):
            return "rule-driven: exceeds max_installment_months"

    if expected.spending_changes_needed not in ("", "none"):
        return "forecast-driven: expected needs spending changes but our forecast is optimistic"

    payments = _parse_plan(expected.payment_plan)
    history_by_id = {e.event_id: e for e in history}
    changes = _parse_changes(expected.spending_changes_needed, history_by_id)
    result = simulate(profile.balance, profile.minimum_balance, future,
                      payments=payments, changes=changes)
    if not result.safe:
        return "forecast-driven: expected plan unsafe under our projection"
    return "rule-driven: expected plan safe but not generated/chosen"


def main():
    predicted = {r.request_id: r for r in pipeline.predict_all(
        SAMPLES, PROFILES, EVENTS, OPTIONS, RATES)}

    match = 0
    details = []
    for sample in SAMPLES:
        expected = sample.expected
        row = predicted[sample.request_id]
        mismatch = [f for f in FIELDS if getattr(row, f) != getattr(expected, f)]
        if not mismatch:
            match += 1
            continue
        profile = PROFILES[sample.user_id]
        events = reconcile.reconcile(EVENTS.get(sample.user_id, []), profile, RATES)
        history = [e for e in events if e.date <= sample.request_date]
        future = forecast.forecast_events(events, sample.request_date)
        label = classify(sample, profile, history, future, OPTIONS.get(sample.request_id, []))
        gt_safe = float(expected.amount_safe_to_pay)
        pred_safe = row.amount_safe_to_pay
        if pred_safe > gt_safe + 0.01:
            direction = "amount too high (under-reserved)"
        elif pred_safe < gt_safe - 0.01:
            direction = "amount too low (over-reserved)"
        else:
            direction = "amount equal"
        details.append((sample.request_id, mismatch, label, direction, row, expected))

    print(f"RAW plan-field match: {match}/25   (mismatches: {len(details)})")
    direction_counts: dict[str, int] = {}
    for _rid, _f, _l, direction, _r, _e in details:
        direction_counts[direction] = direction_counts.get(direction, 0) + 1
    print("mismatch attribution:")
    for label, count in sorted(direction_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>2}  {label}")
    print(f"  {sum(1 for d in details if d[5].spending_changes_needed not in ('', 'none')):>2}  "
          f"expected a spending change we did not emit")
    print("\nper-sample mismatch detail:")
    for rid, fields, label, direction, row, expected in details:
        print(f"  {rid:<12} [{direction}] {label}")
        print(f"      differing fields: {fields}")
        print(f"      pred: {row.affordability_status} / {row.recommended_payment_method} / "
              f"{row.payment_plan} / {row.spending_changes_needed}")
        print(f"      exp : {expected.affordability_status} / {expected.recommended_payment_method} / "
              f"{expected.payment_plan} / {expected.spending_changes_needed}")


if __name__ == "__main__":
    main()
