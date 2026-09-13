"""Deterministic 6-level plan ranking.

Eligibility (which methods the user will consider) and the safety filter
(re-simulating each candidate) both happen in plans.py, at generation time --
this module only orders the candidates that already survived both.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from domain import Plan


def rank_key(plan: Plan) -> tuple:
    completes = 0 if plan.status != "not_affordable" else 1
    changes = 0 if not plan.spending_changes else 1
    total_paid = plan.total_paid
    first_payment = plan.payments[0].date if plan.payments else date.max
    payment_count = len(plan.payments)
    option_id = plan.option_id or ""
    return (completes, changes, total_paid, first_payment, payment_count, option_id)


def choose(plans: list[Plan]) -> Optional[Plan]:
    if not plans:
        return None
    return min(plans, key=rank_key)


def fallback() -> Plan:
    return Plan(method="not_recommended", status="not_affordable")
