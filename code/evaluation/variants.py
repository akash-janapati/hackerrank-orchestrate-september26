"""Variant comparison on the 25 samples.

Variants:
  full          - original full recurrence expansion
  stable        - stable-only expansion (sigma(day)==0, amount CV<0.05)
  capped        - full expansion only up to next salary, then given rows
  contractual   - only rent/debt/insurance/subscription/salary projected
  given         - only given pending/scheduled rows (no recurrence)

Reports amount_safe MAE/exact and status/earliest match counts.

Run: python3 code/evaluation/variants.py
"""
from __future__ import annotations

import os
import statistics
import sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
sys.path.insert(0, CODE_DIR)

import capacity  # noqa: E402
import classify  # noqa: E402
import config  # noqa: E402
import forecast as forecast_mod  # noqa: E402
import ingest  # noqa: E402
import reconcile  # noqa: E402
import simulate as simulate_mod  # noqa: E402

SAMPLES = ingest.load_requests(config.SAMPLE_REQUESTS_CSV)
PROFILES = ingest.load_profiles()
EVENTS = ingest.load_events()
RATES = ingest.load_rates()

CONTRACTUAL = {
    "rent", "debt_repayment", "insurance", "streaming",
    "music_subscription", "delivery_membership", "cloud_storage", "salary",
}
EPS = 0.01


def build(uid, rd):
    profile = PROFILES[uid]
    events = reconcile.reconcile(EVENTS.get(uid, []), profile, RATES)
    return profile, events


def full_future(events, rd):
    original = forecast_mod._is_stable
    forecast_mod._is_stable = lambda bucket: True
    try:
        return forecast_mod.forecast_events(events, rd)
    finally:
        forecast_mod._is_stable = original


def stable_future(events, rd):
    return forecast_mod.forecast_events(events, rd)


def capped_future(events, rd):
    future = full_future(events, rd)
    explicit = [e for e in future if e.source == "event"]
    projected = [e for e in future if e.source == "forecast"]
    salary_days = [e.date for e in explicit
                   if e.direction == "credit" and e.category == "salary"]
    if not salary_days:
        salary_days = [e.date for e in projected
                       if e.direction == "credit" and e.category == "salary"]
    cutoff = min(salary_days) if salary_days else rd
    return explicit + [e for e in projected if e.date <= cutoff]


def contractual_future(events, rd):
    future = full_future(events, rd)
    return [
        e for e in future
        if e.source == "event" or (e.source == "forecast" and e.category in CONTRACTUAL)
    ]


def given_future(events, rd, horizon):
    return [
        e for e in events
        if e.status in ("pending", "scheduled") and rd < e.date <= horizon
    ]


def provisional(profile, request, safe, earliest):
    if safe >= request.requested_amount - EPS and "full_payment" in profile.methods:
        return "affordable_now", request.request_date.isoformat()
    if earliest is not None and earliest <= request.desired_completion_date \
            and "full_payment" in profile.methods:
        return "affordable_later", earliest.isoformat()
    return "not_affordable", ""


def evaluate(label, future_fn, subset=None, horizon_offset=0, given_only=False):
    exact = 0
    mae = 0.0
    status_ok = 0
    earliest_ok = 0
    n = 0
    for sample in SAMPLES:
        if subset is not None and sample.request_id not in subset:
            continue
        profile, events = build(sample.user_id, sample.request_date)
        if given_only:
            future = future_fn(events, sample.request_date,
                               sample.request_date + timedelta(days=config.HORIZON_DAYS))
        else:
            future = future_fn(events, sample.request_date)
        gt = float(sample.expected.amount_safe_to_pay)
        safe = capacity.amount_safe_to_pay(profile, future, sample.requested_amount)
        earliest = capacity.earliest_full_date(
            profile, sample.request_date, future, sample.requested_amount
        )
        status, earliest_text = provisional(profile, sample, safe, earliest)
        n += 1
        mae += abs(safe - gt)
        exact += abs(safe - gt) < 0.01
        status_ok += status == sample.expected.affordability_status
        earliest_ok += earliest_text == sample.expected.earliest_date_for_full_payment
    print(f"{label:<26}{n:>4}{exact:>7}{mae / n:>16,.0f}{status_ok:>9}/{n}{earliest_ok:>9}/{n}")


def main():
    print(f"{'variant':<26}{'n':>4}{'exact':>7}{'MAE':>16}{'status':>10}{'earliest':>10}")
    print("-" * 73)
    evaluate("full expansion", full_future)
    evaluate("stable-only", stable_future)
    evaluate("capped horizon", capped_future)
    evaluate("contractual-only", contractual_future)

    given_ids = {
        s.request_id for s in SAMPLES
        if given_future(
            build(s.user_id, s.request_date)[1], s.request_date,
            s.request_date + timedelta(days=config.HORIZON_DAYS)
        )
    }
    print("-" * 73)
    evaluate("given-rows-only (subset)", given_future, subset=given_ids, given_only=True)


if __name__ == "__main__":
    main()
