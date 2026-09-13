"""Step C - how many users' messages would actually change their forecast.

Applies a mechanical, template-based amendment derived from each message to the
user's events, then re-runs the pipeline and counts forecast changes.

Run: python3 code/evaluation/message_value.py
"""
from __future__ import annotations

import csv
import os
import re
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

ALL_REQUESTS = ingest.load_requests(config.REQUESTS_CSV) + \
    ingest.load_requests(config.SAMPLE_REQUESTS_CSV)
PROFILES = ingest.load_profiles()
EVENTS = ingest.load_events()
OPTIONS = ingest.load_options()
RATES = ingest.load_rates()

AMOUNT_RE = re.compile(r"(IDR|USD|EUR|ZAR|INR)\s*([0-9][0-9,]*(?:\.[0-9]+)?)")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
CHILDCARE = ("childcare payment begins", "pembayaran penitipan anak", "childcare")
SALARY = ("salary", "gaji", "pay", "upah")


def parse_amount(text):
    m = AMOUNT_RE.search(text)
    if not m:
        return None, None
    return m.group(1), float(m.group(2).replace(",", ""))


def classify(text):
    low = text.lower()
    if "contract has ended" in low or "kontrak musiman" in low and "berakhir" in low:
        return "remove_income"
    if "first salary" in low or "gaji pertama" in low:
        return "add_income"
    if "salary of" in low and "confirmed for" in low:
        return "add_income"
    if "resumes on" in low:
        return "amend_income"
    if "expected on" in low or "diperkirakan masuk pada" in low:
        return "amend_date"
    if "increased to" in low or "naik menjadi" in low or "base salary" in low \
            or "gaji pokok yang dikonfirmasi" in low:
        return "amend_income"
    if "reduced to" in low or "temporary monthly pay" in low:
        return "amend_income"
    if "increases monthly rent by" in low:
        return "amend_rent"
    if "another debit will be attempted" in low:
        return "add_debit"
    return "no_change"


def latest_salary(rows):
    idx = [i for i, e in enumerate(rows)
           if e.category == "salary" and e.direction == "credit"]
    return max(idx, key=lambda i: rows[i].event_date) if idx else None


def apply(uid, text, rows):
    kind = classify(text)
    rows = list(rows)
    currency, amount = parse_amount(text)
    dates = DATE_RE.findall(text)
    if kind == "no_change":
        return rows
    if kind == "remove_income":
        return [e for e in rows if not (e.category == "salary" and e.direction == "credit")]
    if kind == "amend_rent":
        for i, e in enumerate(rows):
            if e.category == "rent" and e.amount is not None:
                rows[i] = replace(e, amount=e.amount * 1.12)
        return rows
    if kind == "amend_date":
        target = date.fromisoformat(dates[0]) if dates else None
        idx = [i for i, e in enumerate(rows)
               if e.category == "salary" and e.direction == "credit" and e.status == "scheduled"]
        if idx and target:
            i = idx[-1]
            rows[i] = replace(rows[i], event_date=target, settlement_date=target)
        elif target:
            base = latest_salary(rows)
            amt = rows[base].amount if base is not None else 0.0
            cur = rows[base].currency if base is not None else "USD"
            rows.append(RawEvent(event_id=f"msg_{uid}_sal", user_id=uid,
                                 event_type="income", description="salary",
                                 category="salary", direction="credit", amount=amt,
                                 currency=cur, event_date=target, settlement_date=target,
                                 status="scheduled", linked_event_id=None,
                                 flexibility="fixed", minimum_allowed_amount=None))
        return rows
    if kind == "amend_income":
        base = latest_salary(rows)
        if base is not None and amount is not None:
            rows[base] = replace(rows[base], amount=amount,
                                 currency=currency or rows[base].currency)
        elif amount is not None:
            target = date.fromisoformat(dates[0]) if dates else None
            rows.append(RawEvent(event_id=f"msg_{uid}_sal", user_id=uid,
                                 event_type="income", description="salary",
                                 category="salary", direction="credit", amount=amount,
                                 currency=currency or "USD",
                                 event_date=target or date(2000, 1, 15),
                                 settlement_date=target,
                                 status="scheduled" if target else "settled",
                                 linked_event_id=None, flexibility="fixed",
                                 minimum_allowed_amount=None))
        return rows
    if kind == "add_income":
        target = date.fromisoformat(dates[0]) if dates else None
        rows.append(RawEvent(event_id=f"msg_{uid}_sal", user_id=uid,
                             event_type="income", description="salary",
                             category="salary", direction="credit", amount=amount or 0.0,
                             currency=currency or "USD",
                             event_date=target or date(2000, 1, 15),
                             settlement_date=target,
                             status="scheduled",
                             linked_event_id=None, flexibility="fixed",
                             minimum_allowed_amount=None))
        return rows
    return rows


def main():
    messages = list(csv.DictReader(open(config.MESSAGES_CSV)))
    per_user = {m["user_id"]: m for m in messages}

    baseline = {r.request_id: r for r in pipeline.predict_all(
        ALL_REQUESTS, PROFILES, EVENTS, OPTIONS, RATES)}

    amended_events = {}
    kinds = {}
    for uid, rows in EVENTS.items():
        msg = per_user.get(uid)
        if msg is None:
            amended_events[uid] = rows
            continue
        kind = classify(msg["message_text"])
        kinds[uid] = kind
        amended_events[uid] = apply(uid, msg["message_text"], rows)

    amended = {r.request_id: r for r in pipeline.predict_all(
        ALL_REQUESTS, PROFILES, amended_events, OPTIONS, RATES)}

    changed = []
    for request in ALL_REQUESTS:
        before, after = baseline[request.request_id], amended[request.request_id]
        if (abs(before.amount_safe_to_pay - after.amount_safe_to_pay) > 0.01
                or before.recommended_payment_method != after.recommended_payment_method):
            changed.append((request, before, after, kinds.get(request.user_id, "no_message")))

    from collections import Counter
    print(f"messages total                : {len(messages)}")
    print(f"users with a change template  : {sum(1 for k in kinds.values() if k != 'no_change')}")
    print(f"requests whose forecast CHANGED: {len(changed)}")
    print("changed by template kind:")
    for kind, count in Counter(k for _r, _b, _a, k in changed).most_common():
        print(f"   {count:>3}  {kind}")
    print("\nexamples:")
    for request, before, after, kind in changed[:3]:
        print(f"   {request.request_id} {request.user_id} [{kind}]")
        print(f"      safe {before.amount_safe_to_pay:,.2f} -> {after.amount_safe_to_pay:,.2f}   "
              f"method {before.recommended_payment_method} -> {after.recommended_payment_method}")


if __name__ == "__main__":
    main()
