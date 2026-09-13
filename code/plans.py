"""Candidate plan generation.

Produces safe, method-eligible plans; ranking lives in rank.py.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import config
from domain import (
    Event,
    Payment,
    PaymentOption,
    Plan,
    Profile,
    Request,
    SpendingChange,
)
from simulate import simulate

EPS = 0.01


def _sim_safe(profile: Profile, future: list[Event], payments, changes) -> bool:
    return simulate(profile.balance, profile.minimum_balance, future,
                    payments=payments, changes=changes).safe


def fmt_change_amount(value: float) -> str:
    if float(value) == int(value):
        return str(int(value))
    return f"{value:.2f}"


def _flexible_candidates(profile: Profile, history: list[Event]):
    """One candidate per flexible, non-protected category, using its most recent
    occurrence. Kind priority: reduce_to over stop. Ordering (sample-observed):
    most recent occurrence first; among equal dates, larger saving first.

    request_06 -> stop event_476 (streaming only)
    request_11 -> reduce_to event_989 (dining, 2025-04-23) before entertainment (2025-04-16)
    request_21 -> stop event_1815 / reduce_to event_1816 (most recent eligible events)
    """
    latest: dict[str, tuple[SpendingChange, float, date]] = {}
    for event in history:
        if event.direction != "debit" or event.amount is None:
            continue
        if event.category in profile.protected:
            continue
        can_reduce = (event.flexibility in ("reducible", "reducible_or_stoppable")
                      and event.category in profile.reducible)
        can_stop = (event.flexibility in ("stoppable", "reducible_or_stoppable")
                    and event.category in profile.stoppable)
        candidate: Optional[SpendingChange] = None
        saving = 0.0
        if can_reduce:
            cap = event.minimum_allowed_amount if event.minimum_allowed_amount is not None else 0.0
            candidate = SpendingChange("reduce_to", event.event_id, cap, event.category)
            saving = max(0.0, event.amount - cap)
        elif can_stop:
            candidate = SpendingChange("stop", event.event_id, None, event.category)
            saving = event.amount
        if candidate is not None:
            latest[event.category] = (candidate, saving, event.date)
    ordered = sorted(latest.values(), key=lambda item: (-item[2].toordinal(), -item[1]))
    return [(candidate, saving) for candidate, saving, _date in ordered]


def _full_with_changes(profile, future, history, requested, request_date):
    """Greedy <=3 changes making an immediate full payment safe; pruned to minimal."""
    payment = [Payment(request_date, requested)]
    if _sim_safe(profile, future, payment, []):
        return None
    chosen: list[SpendingChange] = []
    for change, _saving in _flexible_candidates(profile, history):
        if len(chosen) >= 3:
            break
        chosen.append(change)
        if _sim_safe(profile, future, payment, chosen):
            for candidate in list(chosen):
                trial = [c for c in chosen if c is not candidate]
                if _sim_safe(profile, future, payment, trial):
                    chosen = trial
            return chosen
    return None


def _option_schedule(option: PaymentOption) -> list[Payment]:
    frequency = option.frequency_days or 0
    return [
        Payment(option.first_payment_date + timedelta(days=frequency * i),
                option.payment_amount)
        for i in range(option.number_of_payments)
    ]


def generate(
    request: Request,
    profile: Profile,
    history: list[Event],
    future: list[Event],
    options: list[PaymentOption],
    amount_safe: float,
    earliest_full: Optional[date],
) -> list[Plan]:
    plans: list[Plan] = []
    accepted = profile.methods
    deadline = request.desired_completion_date
    today = request.request_date

    if "full_payment" in accepted:
        payment = [Payment(today, request.requested_amount)]
        if _sim_safe(profile, future, payment, []):
            plans.append(Plan(method="full_payment", payments=payment,
                              status="affordable_now", earliest_full=today,
                              total_paid=request.requested_amount))
        else:
            changes = _full_with_changes(profile, future, history,
                                         request.requested_amount, today)
            if changes is not None:
                plans.append(Plan(method="full_payment", payments=payment,
                                  spending_changes=changes,
                                  status="affordable_with_plan",
                                  earliest_full=earliest_full,
                                  total_paid=request.requested_amount))

    if (request.allows_partial_payment and "partial_payment" in accepted
            and 0 < amount_safe < request.requested_amount - EPS
            and earliest_full is not None and earliest_full <= deadline):
        payments = [Payment(today, amount_safe),
                    Payment(earliest_full, request.requested_amount - amount_safe)]
        if _sim_safe(profile, future, payments, []):
            plans.append(Plan(method="partial_payment", payments=payments,
                              status="affordable_with_plan",
                              earliest_full=earliest_full,
                              total_paid=request.requested_amount))

    if "installments" in accepted:
        for option in options:
            if option.method != "installments":
                continue
            if (profile.max_installment_months is not None
                    and option.number_of_payments > profile.max_installment_months):
                continue
            schedule = _option_schedule(option)
            if not schedule or schedule[-1].date > deadline:
                continue
            if _sim_safe(profile, future, schedule, []):
                plans.append(Plan(method="installments", payments=schedule,
                                  status="affordable_with_plan",
                                  earliest_full=earliest_full,
                                  total_paid=option.total_payable_amount,
                                  option_id=option.option_id))

    if ("full_payment" in accepted and earliest_full is not None
            and today < earliest_full <= deadline):
        payment = [Payment(earliest_full, request.requested_amount)]
        if _sim_safe(profile, future, payment, []):
            plans.append(Plan(method="wait", payments=payment,
                              status="affordable_later",
                              earliest_full=earliest_full,
                              total_paid=request.requested_amount))

    return plans
