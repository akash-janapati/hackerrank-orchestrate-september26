"""Step 2 report: resolve the 16 blank-amount images and measure impact.

Run: python3 code/evaluation/images_report.py
"""
from __future__ import annotations

import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
sys.path.insert(0, CODE_DIR)

import config  # noqa: E402
import evidence  # noqa: E402
import ingest  # noqa: E402
import main as pipeline  # noqa: E402


def distribution(rows):
    return collections.Counter(r.affordability_status for r in rows)


def main():
    events = ingest.load_events()
    profiles = ingest.load_profiles()
    options = ingest.load_options()
    rates = ingest.load_rates()
    samples = ingest.load_requests(config.SAMPLE_REQUESTS_CSV)
    eval_requests = ingest.load_requests(config.REQUESTS_CSV)

    # Live resolution (ignores cache, rewrites it).
    overrides, records = evidence.load_amount_overrides(events)

    print("=" * 92)
    print("STEP 2 - IMAGE RESOLUTION (16 blank-amount events)")
    print("=" * 92)
    print(f"{'image':<10}{'event':<12}{'category':<14}{'dir':<7}{'amount':>14}  "
          f"{'cur':<4}{'method':<9} enters")
    print("-" * 92)
    for record in sorted(records, key=lambda r: r["image_id"]):
        event = next((e for rows in events.values() for e in rows
                      if e.event_id == record.get("event_id")), None)
        amount = record.get("extracted_amount")
        enters = "yes" if record.get("event_id") in overrides else "NO"
        print(f"{record['image_id']:<10}{record.get('event_id',''):<12}"
              f"{event.category if event else '':<14}{event.direction if event else '':<7}"
              f"{(f'{amount:,.2f}' if amount else '-'):>14}  "
              f"{(record.get('currency') or '-'):<4}{str(record.get('method')):<9}{enters}")
    print("-" * 92)
    print(f"resolved into cash flow: {len(overrides)}/16")

    # Sample scorecard impact.
    def sample_score(ov):
        rows = {r.request_id: r for r in pipeline.predict_all(
            samples, profiles, events, options, rates, amount_overrides=ov)}
        exact = status = method = 0
        for s in samples:
            r = rows[s.request_id]
            exact += abs(r.amount_safe_to_pay - float(s.expected.amount_safe_to_pay)) < 0.01
            status += r.affordability_status == s.expected.affordability_status
            method += r.recommended_payment_method == s.expected.recommended_payment_method
        return exact, status, method

    before = sample_score({})
    after = sample_score(overrides)
    print(f"\nfit_samples (amount exact / status / method): "
          f"{before[0]}/25 {before[1]}/25 {before[2]}/25  ->  "
          f"{after[0]}/25 {after[1]}/25 {after[2]}/25")

    eval_before = distribution(pipeline.predict_all(eval_requests, profiles, events, options, rates))
    eval_after = distribution(pipeline.predict_all(eval_requests, profiles, events, options, rates,
                                                   amount_overrides=overrides))
    print("\nfull-set (250) status distribution:")
    print(f"  before: {dict(eval_before)}")
    print(f"  after : {dict(eval_after)}")


if __name__ == "__main__":
    main()
