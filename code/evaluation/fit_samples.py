"""Scorecard: run the current pipeline on the 25 solved samples.

Usage:
    python3 code/evaluation/fit_samples.py

Prints per-field match counts and amount error statistics. Used in Phase 1 to
calibrate the recurrence policy against the only labeled data available.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
sys.path.insert(0, CODE_DIR)

import config  # noqa: E402
import ingest  # noqa: E402
import main as pipeline  # noqa: E402
import validate  # noqa: E402


def _norm_plan(plan: str) -> str:
    return (plan or "").strip()


def _norm_changes(changes: str) -> str:
    return (changes or "").strip()


def score(samples, predicted_by_id) -> None:
    total = len(samples)
    with_expected = [s for s in samples if s.expected is not None]
    matches = {"amount": 0, "amount<=1": 0, "status": 0, "method": 0,
               "plan": 0, "earliest": 0, "changes": 0}
    abs_errors: list[float] = []
    worst: list[tuple[float, str, float, float]] = []

    for sample in with_expected:
        expected = sample.expected
        predicted = predicted_by_id[sample.request_id]

        err = abs(predicted.amount_safe_to_pay - expected.amount_safe_to_pay)
        abs_errors.append(err)
        worst.append((err, sample.request_id,
                      predicted.amount_safe_to_pay, expected.amount_safe_to_pay))

        if err <= 0.01:
            matches["amount"] += 1
        if err <= 1.0:
            matches["amount<=1"] += 1
        if predicted.affordability_status == expected.affordability_status:
            matches["status"] += 1
        if predicted.recommended_payment_method == expected.recommended_payment_method:
            matches["method"] += 1
        if _norm_plan(predicted.payment_plan) == _norm_plan(expected.payment_plan):
            matches["plan"] += 1
        if (predicted.earliest_date_for_full_payment
                == expected.earliest_date_for_full_payment):
            matches["earliest"] += 1
        if _norm_changes(predicted.spending_changes_needed) == _norm_changes(
            expected.spending_changes_needed
        ):
            matches["changes"] += 1

    n = max(1, len(with_expected))
    mae = sum(abs_errors) / max(1, len(abs_errors))
    median = sorted(abs_errors)[len(abs_errors) // 2] if abs_errors else 0.0

    print(f"samples: {total} total, {len(with_expected)} with expected output")
    print("-" * 64)
    for key in ("amount", "amount<=1", "status", "method", "plan", "earliest", "changes"):
        print(f"  {key:<12} {matches[key]:>3}/{n:<3}  ({100.0 * matches[key] / n:5.1f}%)")
    print("-" * 64)
    print(f"  amount abs error: MAE={mae:,.2f}  median={median:,.2f}")
    print("  largest amount errors (error, request, predicted, expected):")
    for err, rid, pred, exp in sorted(worst, reverse=True)[:5]:
        print(f"    {err:>14,.2f}  {rid}  predicted={pred:,.2f}  expected={exp:,.2f}")


if __name__ == "__main__":
    samples = ingest.load_requests(config.SAMPLE_REQUESTS_CSV)
    profiles = ingest.load_profiles()
    events_by_user = ingest.load_events()
    options_by_request = ingest.load_options()
    rates = ingest.load_rates()

    import evidence  # noqa: E402
    import messages  # noqa: E402
    messages_by_user = ingest.load_messages()
    events_amended = messages.load_amended_events(events_by_user, messages_by_user, profiles)
    overrides, _records = evidence.load_amount_overrides(events_by_user)
    predicted_rows = pipeline.predict_all(
        samples, profiles, events_amended, options_by_request, rates,
        amount_overrides=overrides,
    )
    predicted_by_id = {row.request_id: row for row in predicted_rows}

    request_index = {r.request_id: r for r in samples}
    try:
        validate.lint(predicted_rows, request_index, options_by_request,
                      events_by_user, profiles)
        print("lint: OK")
    except ValueError as exc:
        print("lint: FAILED")
        print(exc)
    score(samples, predicted_by_id)
