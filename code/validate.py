"""Deterministic spec linter.

Raises ValueError listing every violation. Intended to run before writing
output.csv so an invalid submission can never ship.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from domain import OutputRow, PaymentOption, Profile, RawEvent, Request


def parse_plan(plan: str) -> list[tuple[date, float]]:
    text = (plan or "").strip()
    if text in ("", "none"):
        return []
    payments: list[tuple[date, float]] = []
    for part in text.split("|"):
        day_text, _, amount_text = part.partition(":")
        payments.append((date.fromisoformat(day_text.strip()), float(amount_text)))
    return payments


def parse_changes(changes: str) -> list[tuple[str, str, Optional[float]]]:
    text = (changes or "").strip()
    if text in ("", "none"):
        return []
    result: list[tuple[str, str, Optional[float]]] = []
    for part in text.split("|"):
        chunks = part.split(":")
        if chunks[0] == "stop" and len(chunks) == 2:
            result.append(("stop", chunks[1], None))
        elif chunks[0] == "reduce_to" and len(chunks) == 3:
            result.append(("reduce_to", chunks[1], float(chunks[2])))
        else:
            raise ValueError(f"malformed spending change: {part!r}")
    return result


def _option_schedule(option: PaymentOption) -> list[tuple[date, float]]:
    from datetime import timedelta

    freq = option.frequency_days or 0
    return [
        (option.first_payment_date + timedelta(days=freq * i), option.payment_amount)
        for i in range(option.number_of_payments)
    ]


def _same_schedule(a: list[tuple[date, float]], b: list[tuple[date, float]]) -> bool:
    if len(a) != len(b):
        return False
    return all(da == db and abs(va - vb) <= 0.011 for (da, va), (db, vb) in zip(a, b))


def lint(
    rows: Iterable[OutputRow],
    requests: dict[str, Request],
    options_by_request: dict[str, list[PaymentOption]],
    events_by_user: dict[str, list[RawEvent]] | None = None,
    profiles: dict[str, Profile] | None = None,
) -> None:
    rows = list(rows)
    errors: list[str] = []

    seen = [row.request_id for row in rows]
    if len(seen) != len(set(seen)):
        errors.append("duplicate request_id rows")
    missing = set(requests) - set(seen)
    extra = set(seen) - set(requests)
    if missing:
        errors.append(f"missing rows for {len(missing)} request(s): {sorted(missing)[:5]}")
    if extra:
        errors.append(f"unknown request_id rows: {sorted(extra)[:5]}")

    for row in rows:
        req = requests.get(row.request_id)
        if req is None:
            continue
        prefix = f"[{row.request_id}]"

        if row.affordability_status not in {
            "affordable_now", "affordable_with_plan", "affordable_later", "not_affordable",
        }:
            errors.append(f"{prefix} bad affordability_status={row.affordability_status!r}")
        if row.recommended_payment_method not in {
            "full_payment", "partial_payment", "installments", "wait", "not_recommended",
        }:
            errors.append(f"{prefix} bad method={row.recommended_payment_method!r}")

        if not (0 <= row.amount_safe_to_pay <= req.requested_amount + 1e-6):
            errors.append(
                f"{prefix} amount_safe_to_pay={row.amount_safe_to_pay} out of [0, "
                f"{req.requested_amount}]"
            )

        try:
            payments = parse_plan(row.payment_plan)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{prefix} malformed payment_plan: {exc}")
            payments = []
        try:
            changes = parse_changes(row.spending_changes_needed)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{prefix} malformed spending_changes_needed: {exc}")
            changes = []

        # status <-> method consistency
        status, method = row.affordability_status, row.recommended_payment_method
        if status == "affordable_now":
            if method != "full_payment":
                errors.append(f"{prefix} affordable_now requires full_payment")
            if row.earliest_date_for_full_payment != req.request_date.isoformat():
                errors.append(f"{prefix} affordable_now requires earliest == request_date")
        elif status == "affordable_with_plan":
            if method not in {"full_payment", "partial_payment", "installments"}:
                errors.append(f"{prefix} affordable_with_plan requires full/partial/installments")
        elif status == "affordable_later":
            if method != "wait":
                errors.append(f"{prefix} affordable_later requires wait")
            if not row.earliest_date_for_full_payment:
                errors.append(f"{prefix} affordable_later requires a non-empty earliest date")
        elif status == "not_affordable":
            if method != "not_recommended":
                errors.append(f"{prefix} not_affordable requires not_recommended")
            if row.earliest_date_for_full_payment:
                errors.append(f"{prefix} not_affordable requires empty earliest date")

        if row.earliest_date_for_full_payment:
            try:
                date.fromisoformat(row.earliest_date_for_full_payment)
            except ValueError:
                errors.append(f"{prefix} earliest date not ISO: {row.earliest_date_for_full_payment!r}")

        if method == "not_recommended" and row.payment_plan.strip() != "none":
            errors.append(f"{prefix} not_recommended requires plan=none")
        if method in {"full_payment", "partial_payment", "installments", "wait"} and not payments:
            errors.append(f"{prefix} method={method} requires a non-empty plan")

        if method == "full_payment":
            expected = [(req.request_date, req.requested_amount)]
            if not _same_schedule(payments, expected):
                errors.append(
                    f"{prefix} full_payment plan must be request_date:requested_amount"
                )

        if method == "wait":
            if row.earliest_date_for_full_payment:
                earliest = date.fromisoformat(row.earliest_date_for_full_payment)
                expected = [(earliest, req.requested_amount)]
                if not _same_schedule(payments, expected):
                    errors.append(f"{prefix} wait plan must be earliest_date:requested_amount")
                if earliest > req.desired_completion_date:
                    errors.append(f"{prefix} wait completes after desired_completion_date")

        if method == "partial_payment":
            if status != "affordable_with_plan":
                errors.append(f"{prefix} partial_payment requires affordable_with_plan")
            if not req.allows_partial_payment:
                errors.append(f"{prefix} partial_payment but request does not allow it")
            if len(payments) != 2:
                errors.append(f"{prefix} partial_payment requires exactly 2 payments")
            else:
                if payments[0][0] != req.request_date:
                    errors.append(f"{prefix} partial_payment first payment must be request_date")
                if abs(sum(v for _, v in payments) - req.requested_amount) > 0.011:
                    errors.append(f"{prefix} partial_payment total must equal requested_amount")
                if not (0 < row.amount_safe_to_pay < req.requested_amount):
                    errors.append(f"{prefix} partial_payment requires 0 < safe < requested")
                if row.earliest_date_for_full_payment:
                    earliest = date.fromisoformat(row.earliest_date_for_full_payment)
                    if payments[1][0] != earliest:
                        errors.append(f"{prefix} partial_payment second date must equal earliest")
                    if earliest > req.desired_completion_date:
                        errors.append(f"{prefix} partial_payment completes after deadline")

        if method == "installments":
            options = options_by_request.get(row.request_id, [])
            if not any(_same_schedule(payments, _option_schedule(o)) for o in options):
                errors.append(f"{prefix} installments plan does not match any supplied option")

        # spending changes
        if len(changes) > 3:
            errors.append(f"{prefix} more than 3 spending changes")
        change_events = [event_id for _, event_id, _ in changes]
        if len(change_events) != len(set(change_events)):
            errors.append(f"{prefix} spending changes reference the same event twice")
        stop_events = {e for kind, e, _ in changes if kind == "stop"}
        reduce_events = {e for kind, e, _ in changes if kind == "reduce_to"}
        if stop_events & reduce_events:
            errors.append(f"{prefix} stop and reduce_to on the same event")

        if changes and (events_by_user is None or profiles is None):
            errors.append(f"{prefix} cannot validate spending changes without events/profiles")
        elif changes:
            user_events = {e.event_id: e for e in events_by_user.get(req.user_id, [])}
            profile = profiles.get(req.user_id)
            for kind, event_id, new_amount in changes:
                event = user_events.get(event_id)
                if event is None:
                    errors.append(f"{prefix} spending change references unknown event {event_id}")
                    continue
                if profile and event.category in profile.protected:
                    errors.append(f"{prefix} spending change on protected category {event.category}")
                if kind == "stop":
                    if event.flexibility not in {"stoppable", "reducible_or_stoppable"}:
                        errors.append(f"{prefix} cannot stop non-stoppable event {event_id}")
                else:
                    if event.flexibility not in {"reducible", "reducible_or_stoppable"}:
                        errors.append(f"{prefix} cannot reduce non-reducible event {event_id}")
                    if event.minimum_allowed_amount is not None and new_amount is not None:
                        if new_amount < event.minimum_allowed_amount - 1e-6:
                            errors.append(
                                f"{prefix} {event_id} reduce_to below minimum_allowed_amount"
                            )
                    if event.amount is not None and new_amount is not None:
                        if new_amount >= event.amount:
                            errors.append(f"{prefix} {event_id} reduce_to is not a reduction")

    if errors:
        raise ValueError("output lint failed:\n  - " + "\n  - ".join(errors))
