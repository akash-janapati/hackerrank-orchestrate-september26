"""Step A - message reconnaissance and amendment impact on the 25 samples.

Prints each sample user's message, linkage, and a hand-authored interpretation,
then applies the financial amendments to history/future and re-runs plan
generation, reporting raw vs with-message plan-field match.

Run: python3 code/evaluation/message_recon.py
"""
from __future__ import annotations

import os
import sys
from dataclasses import replace
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
sys.path.insert(0, CODE_DIR)

import config  # noqa: E402
import ingest  # noqa: E402
import main as pipeline  # noqa: E402
from domain import RawEvent  # noqa: E402

SAMPLES = ingest.load_requests(config.SAMPLE_REQUESTS_CSV)
PROFILES = ingest.load_profiles()
EVENTS = ingest.load_events()
OPTIONS = ingest.load_options()
RATES = ingest.load_rates()

FIELDS = ["affordability_status", "recommended_payment_method", "payment_plan",
          "spending_changes_needed"]

INTERPRETATION = {
    "request_02": "amend income: recurring salary raised to IDR 42,750,000 from 2025-08-15",
    "request_03": "confirm scheduled salary; one-time adjustment noted separately (no amount)",
    "request_04": "no financial content: bonus still pending and unapproved -> ignore",
    "request_06": "amend income: next payroll reduced to EUR 1037.52",
    "request_07": "amend date: confirmed salary moves to 2024-09-23",
    "request_08": "amend income: next salary reduced to EUR 1422.85 (unpaid leave)",
    "request_10": "no change: payout still pending -> ignore (pending credit)",
    "request_11": "amend income: base salary IDR 38,760,000; drop unapproved commission",
    "request_12": "amend income: seasonal contract ended -> remove recurring salary",
    "request_14": "add income EUR 2717 from 2025-08-15 and new recurring childcare expense",
    "request_15": "add income: first salary EUR 1661 on 2026-01-15",
    "request_16": "amend expense: monthly rent +12%",
    "request_18": "no financial content: debit+credit are an internal transfer -> no net cash",
    "request_20": "no change: refund initiated but not credited -> ignore (pending credit)",
    "request_22": "no change: portfolio value only, no cash -> ignore (non-cash)",
    "request_23": "no change: prize still processing -> ignore (pending credit)",
    "request_24": "no change: prize already credited/settled -> no forecast change",
}


def amend(uid: str, rows: list[RawEvent]) -> list[RawEvent]:
    rows = list(rows)
    if uid == "user_02":
        salaries = [i for i, e in enumerate(rows)
                    if e.category == "salary" and e.direction == "credit"]
        if salaries:
            i = max(salaries, key=lambda k: rows[k].event_date)
            rows[i] = replace(rows[i], amount=42750000.0)
    elif uid == "user_07":
        for i, e in enumerate(rows):
            if e.category == "salary" and e.status == "scheduled":
                rows[i] = replace(e, event_date=date(2024, 9, 23),
                                  settlement_date=date(2024, 9, 23))
    elif uid == "user_11":
        rows = [e for e in rows
                if not (e.category == "salary" and e.direction == "credit"
                        and e.event_date.day != 15)]
        for i, e in enumerate(rows):
            if e.category == "salary" and e.direction == "credit":
                rows[i] = replace(e, amount=38760000.0)
    elif uid == "user_12":
        rows = [e for e in rows if not (e.category == "salary" and e.direction == "credit")]
    elif uid == "user_14":
        rows.append(RawEvent(
            event_id="msg14_salary", user_id=uid, event_type="income",
            description="Regular salary", category="salary", direction="credit",
            amount=2717.0, currency="EUR", event_date=date(2025, 7, 15),
            settlement_date=date(2025, 7, 15), status="settled",
            linked_event_id=None, flexibility="fixed", minimum_allowed_amount=None))
        rows.append(RawEvent(
            event_id="msg14_childcare", user_id=uid, event_type="expense",
            description="Childcare", category="childcare", direction="debit",
            amount=180.0, currency="EUR", event_date=date(2025, 7, 20),
            settlement_date=date(2025, 7, 20), status="settled",
            linked_event_id=None, flexibility="fixed", minimum_allowed_amount=None))
    elif uid == "user_15":
        rows.append(RawEvent(
            event_id="msg15_salary", user_id=uid, event_type="income",
            description="First salary", category="salary", direction="credit",
            amount=1661.0, currency="EUR", event_date=date(2026, 1, 15),
            settlement_date=date(2026, 1, 15), status="scheduled",
            linked_event_id=None, flexibility="fixed", minimum_allowed_amount=None))
    elif uid == "user_16":
        for i, e in enumerate(rows):
            if e.category == "rent" and e.amount is not None:
                rows[i] = replace(e, amount=e.amount * 1.12)
    return rows


def matches(row, expected):
    return sum(getattr(row, f) == getattr(expected, f) for f in FIELDS)


def main():
    print("=" * 84)
    print("STEP A - MESSAGE RECONNAISSANCE (25 samples)")
    print("=" * 84)
    messages = {m["user_id"]: m for m in
                [r for r in __import__("csv").DictReader(open(config.MESSAGES_CSV))]}
    for sample in SAMPLES:
        message = messages.get(sample.user_id)
        if message is None:
            continue
        link = f"request={message['request_id'] or '-'} event={message['related_event_id'] or '-'}"
        print(f"\n{sample.request_id} {sample.user_id} [{message['message_id']}] "
              f"src={message['source_type']} {link}")
        print(f"  text: {message['message_text']}")
        print(f"  interpretation: {INTERPRETATION.get(sample.request_id, 'unclassified')}")

    amended_events = {
        uid: amend(uid, rows) for uid, rows in EVENTS.items()
    }

    raw_rows = {r.request_id: r for r in pipeline.predict_all(
        SAMPLES, PROFILES, EVENTS, OPTIONS, RATES)}
    amended_rows = {r.request_id: r for r in pipeline.predict_all(
        SAMPLES, PROFILES, amended_events, OPTIONS, RATES)}

    print("\n" + "=" * 84)
    print("AMENDMENT IMPACT (plan-field match of 4: status/method/plan/changes)")
    print("=" * 84)
    print(f"{'sample':<12}{'raw':>6}{'with-msg':>10}{'delta':>7}")
    print("-" * 36)
    financial = [s for s in SAMPLES if s.request_id in INTERPRETATION]
    total_raw = total_new = 0
    for sample in financial:
        raw = matches(raw_rows[sample.request_id], sample.expected)
        new = matches(amended_rows[sample.request_id], sample.expected)
        total_raw += raw
        total_new += new
        flag = "  <-- improves" if new > raw else ("  (worse)" if new < raw else "")
        print(f"{sample.request_id:<12}{raw:>6}{new:>10}{new - raw:>7}{flag}")
    print("-" * 36)
    print(f"{'TOTAL':<12}{total_raw:>6}{total_new:>10}{total_new - total_raw:>7} "
          f"(of {4 * len(financial)})")


if __name__ == "__main__":
    main()
