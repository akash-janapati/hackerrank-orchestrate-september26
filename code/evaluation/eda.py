"""Exploratory data analysis used to calibrate the pipeline.

Sections:
  1. Ground-truth distribution across the 25 solved samples.
  2. financial_events.csv schema.
  3. Category-level regularity across all 275 users.
  4. Same-day ordering evidence (debit-first vs credit-first).

Run: python3 code/evaluation/eda.py
"""
from __future__ import annotations

import calendar
import collections
import csv
import os
import statistics
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
sys.path.insert(0, CODE_DIR)

import config  # noqa: E402
import ingest  # noqa: E402


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def section_header(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ---------------------------------------------------------------------------
# 1. Ground-truth distribution
# ---------------------------------------------------------------------------
def section_1() -> None:
    section_header("1. GROUND-TRUTH DISTRIBUTION (25 samples)")
    samples = ingest.load_requests(config.SAMPLE_REQUESTS_CSV)
    expected = [s.expected for s in samples if s.expected is not None]
    n = len(expected)

    for field in ("affordability_status", "recommended_payment_method",
                  "spending_changes_needed"):
        counts = collections.Counter(getattr(e, field) for e in expected)
        print(f"\n{field} ({n} rows):")
        for value, count in counts.most_common():
            print(f"  {count:>3}  {value}")

    amounts = [e.amount_safe_to_pay for e in expected]
    zeros = sum(1 for a in amounts if a == 0)
    print("\namount_safe_to_pay:")
    print(f"  min={min(amounts):,.2f}  median={statistics.median(amounts):,.2f}  "
          f"max={max(amounts):,.2f}")
    print(f"  zeros={zeros}  empty=0")

    earliest = [e.earliest_date_for_full_payment for e in expected]
    empty = sum(1 for e in earliest if not e)
    non_empty = sorted(e for e in earliest if e)
    print("\nearliest_date_for_full_payment:")
    print(f"  empty={empty}/{n}")
    if non_empty:
        print(f"  min={non_empty[0]}  median={non_empty[len(non_empty) // 2]}  "
              f"max={non_empty[-1]}")


# ---------------------------------------------------------------------------
# 2. Schema
# ---------------------------------------------------------------------------
def section_2() -> None:
    section_header("2. SCHEMA: financial_events.csv")
    with open(config.EVENTS_CSV, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    columns = list(rows[0].keys())
    print(f"rows={len(rows)}  columns={len(columns)}\n")
    print(f"{'column':<26}{'inferred':<10}{'empty':>8}{'unique':>9}")
    print("-" * 53)
    for col in columns:
        values = [r[col] for r in rows]
        non_empty = [v for v in values if v.strip()]
        empty = len(values) - len(non_empty)

        # infer type
        inferred = "str"
        def parses(fn):
            try:
                for v in non_empty[:200]:
                    fn(v)
                return True
            except ValueError:
                return False
        if non_empty and parses(int):
            inferred = "int"
        elif non_empty and parses(float):
            inferred = "float"
        elif non_empty and parses(date.fromisoformat):
            inferred = "date"

        print(f"{col:<26}{inferred:<10}{empty:>8}{len(set(non_empty)):>9}")

    print("\nvalue counts for low-cardinality columns:")
    for col in columns:
        values = [r[col] for r in rows if r[col].strip()]
        uniques = sorted(set(values))
        if 0 < len(uniques) < 15:
            print(f"\n  {col} ({len(uniques)}):")
            for value, count in collections.Counter(values).most_common():
                print(f"    {count:>6}  {value}")

    print("\nnote: no frequency/recurrence columns exist; recurrence must be inferred.")


# ---------------------------------------------------------------------------
# 3. Category-level regularity
# ---------------------------------------------------------------------------
def section_3() -> None:
    section_header("3. CATEGORY-LEVEL REGULARITY (all users)")
    events = ingest.load_events()
    grouped: dict[tuple[str, str], dict[str, list[date]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    for user_events in events.values():
        for event in user_events:
            if event.status != "settled" or event.direction not in ("debit", "credit"):
                continue
            grouped[(event.category, event.direction)][event.user_id].append(event.event_date)

    print(f"{'category':<20}{'dir':<8}{'users':>6}{'>=3occ':>7}{'medMon':>7}"
          f"{'medDOMsd':>9}  top intervals")
    print("-" * 100)
    ranked = sorted(grouped.items(), key=lambda kv: -len(kv[1]))
    for (category, direction), users in ranked:
        n_users = len(users)
        ge3 = sum(1 for dates in users.values() if len(dates) >= 3)
        months = [len({(d.year, d.month) for d in dates}) for dates in users.values()]
        dom_stds = [
            statistics.pstdev([d.day for d in dates])
            for dates in users.values() if len(dates) >= 2
        ]
        intervals: list[int] = []
        for dates in users.values():
            dates = sorted(dates)
            intervals += [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        top = ", ".join(
            f"{iv}d:{c}" for iv, c in collections.Counter(intervals).most_common(3)
        )
        med_dom = statistics.median(dom_stds) if dom_stds else 0.0
        print(f"{category:<20}{direction:<8}{n_users:>6}{ge3:>7}"
              f"{statistics.median(months):>7.0f}"
              f"{med_dom:>9.1f}  {top}")


# ---------------------------------------------------------------------------
# 4. Same-day ordering evidence
# ---------------------------------------------------------------------------
def _signed(event) -> float:
    return event.amount if event.direction == "credit" else -event.amount


def _min_cumulative(user_id, request_date, order, events_by_user):
    """Naive tiling forecast; returns (min_cum_net, same_day_pairs)."""
    horizon = request_date + timedelta(days=config.HORIZON_DAYS)
    by_day: dict[date, list[float]] = collections.defaultdict(list)
    same_day: list[date] = []

    for event in events_by_user.get(user_id, []):
        if event.amount is None:
            continue
        if event.status not in ("settled", "pending", "scheduled"):
            continue
        if event.direction not in ("debit", "credit"):
            continue
        signed = _signed(event)
        if request_date - timedelta(days=config.TRAILING_WINDOW) <= event.event_date <= request_date:
            step = 1
            while True:
                shifted = add_months(event.event_date, step)
                if shifted > horizon:
                    break
                if shifted > request_date:
                    by_day[shifted].append(signed)
                step += 1
        elif request_date < event.event_date <= horizon:
            by_day[event.event_date].append(signed)

    cumulative = 0.0
    minimum = 0.0
    for day in sorted(by_day):
        entries = by_day[day]
        if order == "debits_first":
            entries = sorted(entries, key=lambda v: v > 0)
        else:
            entries = sorted(entries, key=lambda v: v < 0)
        if any(v < 0 for v in entries) and any(v > 0 for v in entries):
            same_day.append(day)
        for value in entries:
            cumulative += value
            minimum = min(minimum, cumulative)
    return minimum, same_day


def section_4() -> None:
    section_header("4. SAME-DAY ORDERING EVIDENCE")
    samples = ingest.load_requests(config.SAMPLE_REQUESTS_CSV)
    events_by_user = ingest.load_events()
    profiles = ingest.load_profiles()

    rows = []
    for sample in samples:
        if sample.expected is None:
            continue
        profile = profiles[sample.user_id]
        safe = {}
        pairs = {}
        for order in ("debits_first", "credits_first"):
            minimum, same_day = _min_cumulative(
                sample.user_id, sample.request_date, order, events_by_user
            )
            uncapped = profile.balance - profile.minimum_balance + minimum
            safe[order] = max(0.0, min(uncapped, sample.requested_amount))
            pairs[order] = same_day
        rows.append((sample, safe, pairs))

    any_pairs = [(s, pairs) for s, _, pairs in rows if pairs["debits_first"]]
    print(f"sample users with same-day debit+credit in window: {len(any_pairs)}")
    for sample, pairs in any_pairs:
        print(f"  {sample.request_id} {sample.user_id}: days={[d.isoformat() for d in pairs['debits_first']]}")

    print(f"\n{'request':<12}{'expected':>14}{'debit-first':>14}{'credit-first':>14}  match")
    print("-" * 66)
    deb_err = cre_err = 0.0
    deb_match = cre_match = 0
    for sample, safe, _ in rows:
        expected = sample.expected.amount_safe_to_pay
        d, c = safe["debits_first"], safe["credits_first"]
        match = ""
        if abs(d - expected) <= 1e-6 and abs(c - expected) > 1e-6:
            match = "debit"
        elif abs(c - expected) <= 1e-6 and abs(d - expected) > 1e-6:
            match = "credit"
        elif abs(d - expected) <= 1e-6 and abs(c - expected) <= 1e-6:
            match = "both"
        deb_err += abs(d - expected)
        cre_err += abs(c - expected)
        if abs(d - expected) < abs(c - expected):
            deb_match += 1
        elif abs(c - expected) < abs(d - expected):
            cre_match += 1
        print(f"{sample.request_id:<12}{expected:>14,.2f}{d:>14,.2f}{c:>14,.2f}  {match}")

    print("-" * 66)
    print(f"MAE debits_first ={deb_err / len(rows):>14,.2f}  closer on {deb_match} rows")
    print(f"MAE credits_first={cre_err / len(rows):>14,.2f}  closer on {cre_match} rows")


if __name__ == "__main__":
    section_1()
    section_2()
    section_3()
    section_4()
