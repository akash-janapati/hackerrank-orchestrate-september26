"""Event classification and recurrence detection.

Policy is derived from the release diagnostics (code/evaluation/eda.py):
monthly categories have a stable day-of-month (pstdev 0.0) and ~30-31 day
intervals; variable categories (groceries/transport/dining) recur weekly or
biweekly. Recurrence is only detected when history supports it.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import config
from domain import Event

NON_CASH_TYPES = {"investment_valuation"}
NON_CASH_DIRECTIONS = {"non_cash"}
TERMINAL_STATUSES = {"cancelled", "failed"}


@dataclass
class Series:
    category: str
    direction: str
    dates: list[date] = field(default_factory=list)
    amounts: list[float] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.dates)

    @property
    def months(self) -> int:
        return len({(d.year, d.month) for d in self.dates})

    @property
    def last_date(self) -> date:
        return max(self.dates)

    @property
    def last_amount(self) -> float:
        index = max(range(len(self.dates)), key=lambda i: self.dates[i])
        return self.amounts[index]

    @property
    def median_day_of_month(self) -> int:
        return int(round(statistics.median(d.day for d in self.dates)))

    @property
    def median_interval(self) -> Optional[int]:
        ordered = sorted(self.dates)
        if len(ordered) < 2:
            return None
        gaps = [(ordered[i + 1] - ordered[i]).days for i in range(len(ordered) - 1)]
        return int(round(statistics.median(gaps)))

    def is_fixed_amount(self, tol: float = 0.005) -> bool:
        if len(self.amounts) < 2:
            return True
        return statistics.pstdev(self.amounts) <= tol


def is_non_cash(event: Event) -> bool:
    return (
        event.direction in NON_CASH_DIRECTIONS
        or event.event_type in NON_CASH_TYPES
        or event.status == "unrealized"
    )


def is_cash_eligible(event: Event) -> bool:
    """Retained for cash-flow forecasting (settled/pending/scheduled, not terminal).

    Pending debits are reserved (kept); pending credits are not counted until
    they settle (problem_statement.md 90-Day Safety Check; AGENTS.md 6.3).
    """
    if event.status in TERMINAL_STATUSES:
        return False
    if is_non_cash(event):
        return False
    if event.direction not in ("debit", "credit"):
        return False
    if (event.direction == "credit" and event.status == "pending"
            and not config.PENDING_POLICY.get("count_credits", False)):
        return False
    if (event.direction == "debit" and event.status == "pending"
            and not config.PENDING_POLICY.get("reserve_debits", True)):
        return False
    return event.amount is not None


def build_series(events: list[Event]) -> dict[tuple[str, str], Series]:
    series: dict[tuple[str, str], Series] = {}
    for event in events:
        if not is_cash_eligible(event):
            continue
        key = (event.category, event.direction)
        bucket = series.setdefault(key, Series(category=event.category, direction=event.direction))
        bucket.dates.append(event.date)
        bucket.amounts.append(event.amount)
    return series


def is_recurring(bucket: Series, min_occurrences: int) -> bool:
    if bucket.months < min_occurrences:
        return False
    if bucket.category in config.ONE_TIME_CATEGORIES:
        return False
    return True


def is_monthly(bucket: Series) -> bool:
    interval = bucket.median_interval
    return interval is not None and interval >= 25


def is_variable_amount(bucket: Series, variable_categories: set[str]) -> bool:
    return bucket.category in variable_categories or not bucket.is_fixed_amount()
