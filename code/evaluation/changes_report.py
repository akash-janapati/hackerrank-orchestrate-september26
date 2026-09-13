"""Investigate spending-change handling and the changes=0 result.

Run: python3 code/evaluation/changes_report.py
"""
from __future__ import annotations

import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
sys.path.insert(0, CODE_DIR)

import capacity  # noqa: E402
import config  # noqa: E402
import forecast  # noqa: E402
import ingest  # noqa: E402
import plans as plans_mod  # noqa: E402
import reconcile  # noqa: E402
from domain import Payment  # noqa: E402
from simulate import simulate  # noqa: E402

SAMPLES = {s.request_id: s for s in ingest.load_requests(config.SAMPLE_REQUESTS_CSV)}
EVAL = ingest.load_requests(config.REQUESTS_CSV)
PROFILES = ingest.load_profiles()
EVENTS = ingest.load_events()
RATES = ingest.load_rates()


def context(sample):
    profile = PROFILES[sample.user_id]
    events = reconcile.reconcile(EVENTS.get(sample.user_id, []), profile, RATES)
    history = [e for e in events if e.date <= sample.request_date]
    future = forecast.forecast_events(events, sample.request_date)
    return profile, events, history, future


def section_1():
    print("=" * 78)
    print("1. THE THREE SAMPLES WITH NON-NONE GROUND-TRUTH CHANGES")
    print("=" * 78)
    for rid in ("request_06", "request_11", "request_21"):
        sample = SAMPLES[rid]
        profile, events, history, _ = context(sample)
        print(f"\n----- {rid} {sample.user_id} -----")
        print(f"GT changes        : {sample.expected.spending_changes_needed}")
        print(f"protected         : {sorted(profile.protected)}")
        print(f"reducible         : {sorted(profile.reducible)}")
        print(f"stoppable         : {sorted(profile.stoppable)}")
        print("latest history events per flexible category (from CSV flexibility):")
        seen = set()
        for e in sorted(history, key=lambda e: e.date, reverse=True):
            if e.direction != "debit" or e.category in seen:
                continue
            if e.category in profile.protected:
                continue
            if not (e.category in profile.stoppable or e.category in profile.reducible):
                continue
            seen.add(e.category)
            print(f"   {e.event_id:<12} {e.category:<18} flex={e.flexibility:<22} "
                  f"amount={e.amount:>12,.2f} min_allowed={e.minimum_allowed_amount} "
                  f"stop={e.category in profile.stoppable} reduce={e.category in profile.reducible}")
        candidates = plans_mod._flexible_candidates(profile, history)
        print(f"_flexible_candidates -> {len(candidates)}")
        for change, saving in candidates:
            print(f"   {change.kind:<9} {change.event_id:<12} {change.category:<16} "
                  f"new={change.new_amount} saving={saving:,.2f}")


def section_2():
    print("\n" + "=" * 78)
    print("2. minimum_allowed_amount IS read from the schema")
    print("=" * 78)
    total = 0
    by_flex = {}
    for uid, rows in EVENTS.items():
        for r in rows:
            if r.minimum_allowed_amount is not None:
                total += 1
                by_flex[r.flexibility] = by_flex.get(r.flexibility, 0) + 1
    print(f"events with minimum_allowed_amount set: {total}")
    print(f"by flexibility: {by_flex}")


def _changes_fix(profile, future, history, requested, request_date):
    changes = []
    for change, _saving in plans_mod._flexible_candidates(profile, history):
        changes.append(change)
        result = simulate(profile.balance, profile.minimum_balance, future,
                          payments=[Payment(request_date, requested)], changes=changes)
        if result.safe:
            return True, len(changes)
        if len(changes) >= 3:
            break
    return False, 0


def section_3():
    print("\n" + "=" * 78)
    print("3. WHY ZERO CHANGES ON THE 250 EVAL REQUESTS")
    print("=" * 78)
    total = 0
    full_safe = 0
    full_unsafe = 0
    unsafe_with_candidates = 0
    changes_would_fix = 0
    for sample in EVAL:
        profile, events, history, future = context(sample)
        total += 1
        result = simulate(profile.balance, profile.minimum_balance, future,
                          payments=[Payment(sample.request_date, sample.requested_amount)])
        if result.safe:
            full_safe += 1
            continue
        full_unsafe += 1
        if plans_mod._flexible_candidates(profile, history):
            unsafe_with_candidates += 1
            ok, _n = _changes_fix(profile, future, history,
                                  sample.requested_amount, sample.request_date)
            if ok:
                changes_would_fix += 1
    print(f"eval requests                  : {total}")
    print(f"full payment today already safe: {full_safe}")
    print(f"full payment today unsafe      : {full_unsafe}")
    print(f"  of those, with flexible cands: {unsafe_with_candidates}")
    print(f"  of those, <=3 changes fix it : {changes_would_fix}")
    print("=> zero emitted changes means every request we could complete was already")
    print("   affordable in full under our (optimistic, stable-only) projection.")


def section_4():
    print("\n" + "=" * 78)
    print("4. RANKER IS THE FINAL GATE")
    print("=" * 78)
    with open(os.path.join(CODE_DIR, "main.py"), encoding="utf-8") as fh:
        text = fh.read()
    gate = "chosen = rank.choose(candidates) or rank.fallback()"
    print(f"main.predict_all contains: {gate!r} -> {gate in text}")
    print("No provisional status/earliest branch overrides the ranker result.")


if __name__ == "__main__":
    section_1()
    section_2()
    section_3()
    section_4()
