"""Day-by-day cash-flow simulator: the single source of numeric truth."""
from __future__ import annotations

from datetime import date
from typing import Optional

import config
from domain import Event, Payment, SimulationResult, SpendingChange


def _signed(event: Event) -> float:
    return event.amount if event.direction == "credit" else -event.amount


def simulate(
    balance: float,
    min_balance: float,
    future_events: list[Event],
    payments: Optional[list[Payment]] = None,
    changes: Optional[list[SpendingChange]] = None,
) -> SimulationResult:
    payments = payments or []
    changes = changes or []

    stopped_ids = {c.event_id for c in changes if c.kind == "stop"}
    stopped_categories = {c.category for c in changes
                          if c.kind == "stop" and c.category}
    reduce_by_id = {c.event_id: c.new_amount for c in changes
                    if c.kind == "reduce_to" and c.new_amount is not None}
    reduce_by_category = {c.category: c.new_amount for c in changes
                          if c.kind == "reduce_to" and c.category and c.new_amount is not None}

    by_day: dict[date, list[float]] = {}
    for event in future_events:
        if event.event_id in stopped_ids:
            continue
        if event.source == "forecast" and event.category in stopped_categories:
            continue
        amount = event.amount
        if event.event_id in reduce_by_id:
            amount = min(amount, reduce_by_id[event.event_id])
        elif event.source == "forecast" and event.category in reduce_by_category:
            amount = min(amount, reduce_by_category[event.category])
        delta = amount if event.direction == "credit" else -amount
        by_day.setdefault(event.date, []).append(delta)

    for payment in payments:
        by_day.setdefault(payment.date, []).append(-payment.amount)

    running = balance
    minimum = balance
    breach: Optional[date] = None
    daily: dict[date, float] = {}

    for day in sorted(by_day):
        entries = by_day[day]
        if config.SAME_DAY_ORDER == "debits_first":
            entries.sort()
        else:
            entries.sort(reverse=True)
        for delta in entries:
            running += delta
            if running < minimum:
                minimum = running
                breach = day
        daily[day] = running

    return SimulationResult(
        daily_balances=daily,
        minimum=minimum,
        safe=minimum >= min_balance - 1e-6,
        breach_date=breach,
    )
