"""Deterministic recurrence expansion over the 90-day horizon.

Policy derived from code/evaluation/eda.py:
  - monthly categories -> project on their median day-of-month
  - weekly/biweekly variable categories -> project at their median interval
  - one-time types are never projected
Representative amounts: median for fixed-amount series, and (per the spec's
"forecast essential variable spending conservatively") the recent maximum for
variable series when VARIABLE_AMOUNT == "conservative".
"""
from __future__ import annotations

import calendar
import statistics
from datetime import date, timedelta

import config
from classify import (
    Series,
    build_series,
    is_cash_eligible,
    is_monthly,
    is_recurring,
    is_variable_amount,
)
from domain import Event

ONE_TIME_SOURCES = {"refund", "investment_purchase", "investment_sale"}


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _representative_amount(bucket: Series, mode: str) -> float:
    recent = bucket.amounts[-6:]
    median = statistics.median(recent)
    if bucket.direction == "credit":
        return statistics.median(bucket.amounts)
    # Fixed categories (rent, utilities, healthcare, shopping, subscriptions, ...)
    # project at their median; purely variable categories (groceries, transport,
    # dining) project at a calibrated fraction of their median.
    if bucket.category in config.FIXED_CATEGORIES:
        return median
    return config.VARIABLE_EXPENSE_FRACTION * median


def _month_key(day: date) -> tuple[int, int]:
    return (day.year, day.month)


def _is_stable(bucket: Series) -> bool:
    """Recurrence policy.

    Income (credits): cadence-based (>= MIN_OCCURRENCES months, 5-40 day median
    interval), amount = median.
    Expenses (debits): any category recurring over >= MIN_OCCURRENCES months is
    projected; fixed categories at median, variable categories at a calibrated
    fraction of median (config.VARIABLE_EXPENSE_FRACTION).
    """
    if len(bucket.amounts) < 2:
        return False
    interval = bucket.median_interval
    if interval is None:
        return False
    if bucket.direction == "credit":
        return bucket.months >= config.MIN_OCCURRENCES and 5 <= interval <= 40
    return bucket.months >= config.MIN_OCCURRENCES


# How close a projected occurrence must fall to an explicit (pending/scheduled)
# row of the same category/direction before it's treated as already covered.
# Only used for non-monthly (multiple-times-a-month) categories; monthly
# categories are deduped at month granularity since they have exactly one
# expected occurrence per month.
EXPLICIT_MATCH_WINDOW_DAYS = 3


def _month_day(year: int, month: int, day_of_month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day_of_month, last_day))


def forecast_events(
    events: list[Event],
    request_date: date,
    horizon_days: int = config.HORIZON_DAYS,
) -> list[Event]:
    horizon = request_date + timedelta(days=horizon_days)
    history = [e for e in events if e.date <= request_date and is_cash_eligible(e)]
    explicit_future = [
        e for e in events if request_date < e.date <= horizon and is_cash_eligible(e)
    ]

    series = build_series(history)
    # Monthly categories: one occurrence per month, so month-level coverage
    # correctly prevents double-counting an explicit row against the
    # projection for that same month.
    covered_months = {(e.category, e.direction, _month_key(e.date)) for e in explicit_future}
    # Multi-times-per-month categories (groceries/transport/...): an explicit
    # row only covers its own specific occurrence, not the whole month.
    explicit_dates: dict[tuple[str, str], list[date]] = {}
    for e in explicit_future:
        explicit_dates.setdefault((e.category, e.direction), []).append(e.date)

    def _near_explicit(category: str, direction: str, candidate: date) -> bool:
        return any(
            abs((candidate - d).days) <= EXPLICIT_MATCH_WINDOW_DAYS
            for d in explicit_dates.get((category, direction), [])
        )

    projected: list[Event] = []
    for (category, direction), bucket in series.items():
        if bucket.direction not in ("debit", "credit"):
            continue
        if not is_recurring(bucket, config.MIN_OCCURRENCES):
            continue
        if not _is_stable(bucket):
            continue

        amount = _representative_amount(bucket, config.VARIABLE_AMOUNT)

        if is_monthly(bucket):
            day_of_month = bucket.median_day_of_month
            month = 0
            while True:
                month_anchor = _add_months(
                    date(request_date.year, request_date.month, 1), month
                )
                candidate = _month_day(month_anchor.year, month_anchor.month, day_of_month)
                if candidate > horizon:
                    break
                if candidate > request_date:
                    key = (category, direction, _month_key(candidate))
                    if key not in covered_months:
                        projected.append(_make(bucket, candidate, amount))
                month += 1
        else:
            interval = bucket.median_interval or 30
            if interval <= 0:
                continue
            candidate = bucket.last_date + timedelta(days=interval)
            while candidate <= horizon:
                if candidate > request_date and not _near_explicit(category, direction, candidate):
                    projected.append(_make(bucket, candidate, amount))
                candidate += timedelta(days=interval)

    combined = explicit_future + projected
    return sorted(combined, key=lambda e: (e.date, e.event_id))


def _make(bucket: Series, day: date, amount: float) -> Event:
    from classify import is_monthly, is_variable_amount

    recurrence = "fixed" if (is_monthly(bucket) and bucket.is_fixed_amount()) else "variable"
    return Event(
        event_id=f"forecast_{bucket.category}_{bucket.direction}_{day.isoformat()}",
        user_id="",
        source="forecast",
        event_type="expense" if bucket.direction == "debit" else "income",
        category=bucket.category,
        direction=bucket.direction,
        amount=amount,
        currency="",
        date=day,
        status="forecast",
        flexibility="fixed",
        recurrence=recurrence,
        description="projected",
    )
