"""Diagnostic traces for the Phase 1 forecast.

Answers four questions:
  1. Projection trace for 3 samples with different residual signs.
  2. Exact-match counts for additional candidate rules.
  3. Is the ground truth inferrable from the given pending/scheduled rows alone?
  4. How much does recurrence add on top of the given rows, for one traced case?

Run: python3 code/evaluation/trace_samples.py
Read-only with respect to dataset/ and the pipeline.
"""
from __future__ import annotations

import calendar
import collections
import os
import statistics
import sys
from datetime import date, timedelta

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
OPTIONS = ingest.load_options()
RATES = ingest.load_rates()


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def reconciled(uid: str):
    return reconcile.reconcile(EVENTS.get(uid, []), PROFILES[uid], RATES)


def target(sample) -> float:
    profile = PROFILES[sample.user_id]
    return float(sample.expected.amount_safe_to_pay) - (
        profile.balance - profile.minimum_balance
    )


def sign(event) -> float:
    return event.amount if event.direction == "credit" else -event.amount


def explicit_future(events, rd, horizon):
    return [e for e in events if rd < e.date <= horizon and classify.is_cash_eligible(e)]


def history(events, rd):
    return [e for e in events if e.date <= rd and classify.is_cash_eligible(e)]


def min_cum_from(entries) -> tuple[float, dict]:
    """entries: list of (date, signed). debits-first per day."""
    by_day = collections.defaultdict(list)
    for day, value in entries:
        by_day[day].append(value)
    cumulative = 0.0
    minimum = 0.0
    at = None
    for day in sorted(by_day):
        for value in sorted(by_day[day]):
            cumulative += value
            if cumulative < minimum:
                minimum = cumulative
                at = day
    return minimum, at


def safe_from_min(minimum, profile, requested):
    return max(0.0, min(profile.balance - profile.minimum_balance + minimum, requested))


# ---------------------------------------------------------------------------
# Rule-based projections (return list of (date, signed))
# ---------------------------------------------------------------------------
def _series(events):
    groups = collections.defaultdict(list)
    for e in events:
        groups[(e.category, e.direction)].append(e)
    for key in groups:
        groups[key].sort(key=lambda e: e.date)
    return groups


def rule_last_dom(events, rd, horizon):
    out = [(e.date, sign(e)) for e in explicit_future(events, rd, horizon)]
    for (cat, dirn), evs in _series(history(events, rd)).items():
        coverage = {(e.category, e.direction, (e.date.year, e.date.month))
                    for e in explicit_future(events, rd, horizon)}
        dom = int(round(statistics.median([e.date.day for e in evs])))
        amount = evs[-1].amount
        for k in range(1, 4):
            day = add_months(date(rd.year, rd.month, min(dom, 28)), k)
            if day > horizon:
                break
            if day > rd and (cat, dirn, (day.year, day.month)) not in coverage:
                out.append((day, amount if dirn == "credit" else -amount))
    return out


def rule_last_resampled(events, rd, horizon):
    out = [(e.date, sign(e)) for e in explicit_future(events, rd, horizon)]
    for (cat, dirn), evs in _series(history(events, rd)).items():
        if len(evs) < 2:
            continue
        gaps = [(evs[i + 1].date - evs[i].date).days for i in range(len(evs) - 1)]
        interval = max(1, int(round(statistics.median(gaps))))
        amount = evs[-1].amount
        day = evs[-1].date + timedelta(days=interval)
        while day <= horizon:
            if day > rd:
                out.append((day, amount if dirn == "credit" else -amount))
            day += timedelta(days=interval)
    return out


def rule_months_back(events, rd, horizon, back):
    out = [(e.date, sign(e)) for e in explicit_future(events, rd, horizon)]
    for (cat, dirn), evs in _series(history(events, rd)).items():
        month_amount = {}
        for e in evs:
            month_amount[(e.date.year, e.date.month)] = e.amount
        dom = int(round(statistics.median([e.date.day for e in evs])))
        for k in range(1, 4):
            target_month = add_months(date(rd.year, rd.month, 1), k)
            source = add_months(target_month, -back)
            amount = month_amount.get((source.year, source.month))
            if amount is None:
                continue
            day = date(target_month.year, target_month.month,
                       min(dom, calendar.monthrange(target_month.year, target_month.month)[1]))
            if day > horizon:
                break
            if day > rd:
                out.append((day, amount if dirn == "credit" else -amount))
    return out


def rule_rounded_last(events, rd, horizon, step):
    out = rule_last_dom(events, rd, horizon)
    explicit_days = {(e.date) for e in explicit_future(events, rd, horizon)}
    result = []
    for day, value in out:
        if day in explicit_days:
            result.append((day, value))
        else:
            rounded = round(abs(value) / step) * step
            result.append((day, rounded if value > 0 else -rounded))
    return result


def rule_trailing_sum(events, rd, horizon):
    hist = [e for e in history(events, rd) if e.direction == "debit"]
    window = [e for e in hist if e.date > rd - timedelta(days=30)]
    total = sum(e.amount for e in window)
    out = [(e.date, sign(e)) for e in explicit_future(events, rd, horizon)]
    for k in range(1, 4):
        day = rd + timedelta(days=30 * k)
        if day <= horizon:
            out.append((day, -total))
    return out


# ---------------------------------------------------------------------------
# Section 1
# ---------------------------------------------------------------------------
def section_1():
    print("=" * 78)
    print("SECTION 1 - PROJECTION TRACES (3 samples, different residual signs)")
    print("=" * 78)

    records = []
    for sample in SAMPLES:
        profile = PROFILES[sample.user_id]
        events = reconciled(sample.user_id)
        future = forecast_mod.forecast_events(events, sample.request_date)
        result = simulate_mod.simulate(profile.balance, profile.minimum_balance, future)
        minimum = result.minimum - profile.balance
        computed = safe_from_min(minimum, profile, sample.requested_amount)
        residual = float(sample.expected.amount_safe_to_pay) - computed
        records.append((residual, sample, profile, future, minimum, computed, result))

    records.sort(key=lambda r: r[0])
    chosen = [records[0], records[len(records) // 2], records[-1]]
    seen = set()
    for residual, sample, profile, future, minimum, computed, result in chosen:
        if sample.request_id in seen:
            continue
        seen.add(sample.request_id)
        print(f"\n----- {sample.request_id} ({sample.user_id}) -----")
        print(f"request_date={sample.request_date}  desired={sample.desired_completion_date}  "
              f"requested={sample.requested_amount:,.2f}")
        print(f"GT amount_safe={float(sample.expected.amount_safe_to_pay):,.2f}  "
              f"GT earliest={sample.expected.earliest_date_for_full_payment or '-'}")
        print(f"balance={profile.balance:,.2f}  minimum={profile.minimum_balance:,.2f}  "
              f"cur={profile.currency}")
        print("projected 90-day timeline:")
        for e in sorted(future, key=lambda e: (e.date, e.category)):
            print(f"   {e.date}  {e.category:<18} {e.direction:<7} "
                  f"{e.amount:>14,.2f}  source={e.source}")
        print(f"derived min_cumulative_net={minimum:,.2f}  min_at={result.breach_date}")
        print(f"computed amount_safe={computed:,.2f}")
        print(f"residual (GT - computed)={float(sample.expected.amount_safe_to_pay) - computed:,.2f}")


# ---------------------------------------------------------------------------
# Section 2
# ---------------------------------------------------------------------------
def section_2():
    print("\n" + "=" * 78)
    print("SECTION 2 - CANDIDATE RULES: exact-match count on amount_safe (25 samples)")
    print("=" * 78)

    rules = {
        "last_dom (last amount, day-of-month)": lambda e, r, h: rule_last_dom(e, r, h),
        "last_resampled (last amount, interval)": lambda e, r, h: rule_last_resampled(e, r, h),
        "months_back_1": lambda e, r, h: rule_months_back(e, r, h, 1),
        "months_back_2": lambda e, r, h: rule_months_back(e, r, h, 2),
        "months_back_3": lambda e, r, h: rule_months_back(e, r, h, 3),
        "rounded_last_10": lambda e, r, h: rule_rounded_last(e, r, h, 10),
        "rounded_last_100": lambda e, r, h: rule_rounded_last(e, r, h, 100),
        "rounded_last_1000": lambda e, r, h: rule_rounded_last(e, r, h, 1000),
        "rounded_last_10000": lambda e, r, h: rule_rounded_last(e, r, h, 10000),
        "trailing_sum_30d": lambda e, r, h: rule_trailing_sum(e, r, h),
    }

    print(f"{'rule':<42}{'exact':>7}{'closest_err':>16}")
    print("-" * 65)
    for label, fn in rules.items():
        exact = 0
        best = None
        for sample in SAMPLES:
            profile = PROFILES[sample.user_id]
            events = reconciled(sample.user_id)
            horizon = sample.request_date + timedelta(days=config.HORIZON_DAYS)
            minimum, _ = min_cum_from(fn(events, sample.request_date, horizon))
            safe = safe_from_min(minimum, profile, sample.requested_amount)
            diff = abs(safe - float(sample.expected.amount_safe_to_pay))
            if diff < 0.01:
                exact += 1
            if best is None or diff < best:
                best = diff
        print(f"{label:<42}{exact:>5}/25{best:>16,.2f}")


# ---------------------------------------------------------------------------
# Section 3
# ---------------------------------------------------------------------------
def section_3():
    print("\n" + "=" * 78)
    print("SECTION 3 - GROUND TRUTH FROM GIVEN ROWS ONLY (no recurrence)")
    print("=" * 78)

    subset = []
    for sample in SAMPLES:
        events = reconciled(sample.user_id)
        horizon = sample.request_date + timedelta(days=config.HORIZON_DAYS)
        given = [e for e in events if e.status in ("pending", "scheduled")
                 and sample.request_date < e.date <= horizon]
        if given:
            subset.append((sample, given))

    print(f"samples with >=1 given future row in window: {len(subset)}")
    if not subset:
        return

    given_exact = given_mae = full_exact = full_mae = 0.0
    given_exact = 0
    full_exact = 0
    for sample, given in subset:
        profile = PROFILES[sample.user_id]
        horizon = sample.request_date + timedelta(days=config.HORIZON_DAYS)
        gt = float(sample.expected.amount_safe_to_pay)

        minimum, _ = min_cum_from([(e.date, sign(e)) for e in given])
        given_safe = safe_from_min(minimum, profile, sample.requested_amount)

        events = reconciled(sample.user_id)
        future = forecast_mod.forecast_events(events, sample.request_date)
        result = simulate_mod.simulate(profile.balance, profile.minimum_balance, future)
        full_safe = safe_from_min(result.minimum - profile.balance, profile, sample.requested_amount)

        given_exact += abs(given_safe - gt) < 0.01
        full_exact += abs(full_safe - gt) < 0.01
        given_mae += abs(given_safe - gt)
        full_mae += abs(full_safe - gt)

    n = len(subset)
    print(f"  given-rows-only : exact={given_exact}/{n}  MAE={given_mae / n:,.2f}")
    print(f"  full expansion  : exact={full_exact}/{n}  MAE={full_mae / n:,.2f}")


# ---------------------------------------------------------------------------
# Section 4
# ---------------------------------------------------------------------------
def section_4():
    print("\n" + "=" * 78)
    print("SECTION 4 - CASE WHERE THE FUTURE IS PARTIALLY GIVEN")
    print("=" * 78)

    best = None
    for sample in SAMPLES:
        events = reconciled(sample.user_id)
        horizon = sample.request_date + timedelta(days=config.HORIZON_DAYS)
        given = [e for e in events if e.status in ("pending", "scheduled")
                 and sample.request_date < e.date <= horizon]
        if not given:
            continue
        profile = PROFILES[sample.user_id]
        gt = float(sample.expected.amount_safe_to_pay)
        minimum, _ = min_cum_from([(e.date, sign(e)) for e in given])
        given_safe = safe_from_min(minimum, profile, sample.requested_amount)
        delta = abs(gt - given_safe)
        if best is None or delta > best[0]:
            best = (delta, sample, profile, given, gt, given_safe, events)

    if best is None:
        print("no sample with a given future row")
        return

    _, sample, profile, given, gt, given_safe, events = best
    horizon = sample.request_date + timedelta(days=config.HORIZON_DAYS)
    future = forecast_mod.forecast_events(events, sample.request_date)
    result = simulate_mod.simulate(profile.balance, profile.minimum_balance, future)
    full_safe = safe_from_min(result.minimum - profile.balance, profile, sample.requested_amount)
    projected = [e for e in future if e.source == "forecast"]

    print(f"{sample.request_id} ({sample.user_id})  rd={sample.request_date}  "
          f"requested={sample.requested_amount:,.2f}")
    print(f"balance={profile.balance:,.2f}  minimum={profile.minimum_balance:,.2f}")
    print("given future rows:")
    for e in sorted(given, key=lambda e: e.date):
        print(f"   {e.date}  {e.status:<9} {e.category:<16} {e.direction:<7} {e.amount:>12,.2f}")
    print(f"GT amount_safe={gt:,.2f}   given-rows-only={given_safe:,.2f}   "
          f"full expansion={full_safe:,.2f}")
    print(f"recurrence rows added={len(projected)}; "
          f"recurrence net contribution={sum(sign(e) for e in projected):,.2f}")


if __name__ == "__main__":
    section_1()
    section_2()
    section_3()
    section_4()
