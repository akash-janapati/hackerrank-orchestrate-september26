"""Capacity: the most that can be paid today and the earliest safe full payment.

Both are computed WITHOUT optional spending changes and independently of the
user's payment-method preferences.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import config
from domain import Event, Payment, Profile
from simulate import simulate


def amount_safe_to_pay(
    profile: Profile, future_events: list[Event], requested_amount: float
) -> float:
    result = simulate(profile.balance, profile.minimum_balance, future_events)
    safe = result.minimum - profile.minimum_balance
    return max(0.0, min(safe, requested_amount))


def earliest_full_date(
    profile: Profile,
    request_date: date,
    future_events: list[Event],
    requested_amount: float,
    horizon_days: int = config.HORIZON_DAYS,
) -> Optional[date]:
    for offset in range(horizon_days + 1):
        candidate = request_date + timedelta(days=offset)
        result = simulate(
            profile.balance,
            profile.minimum_balance,
            future_events,
            payments=[Payment(candidate, requested_amount)],
        )
        if result.safe:
            return candidate
    return None
