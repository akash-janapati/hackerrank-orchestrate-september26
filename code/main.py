"""Entry point: load dataset, predict every request, lint, write root output.csv.

Pipeline: messages (LLM facts) -> images (OCR + LLM) -> reconcile -> forecast ->
simulate -> capacity -> plans -> rank -> LLM explanation -> validate -> output.csv.
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import capacity  # noqa: E402
import config  # noqa: E402
import evidence  # noqa: E402
import explain  # noqa: E402
import forecast  # noqa: E402
import ingest  # noqa: E402
import llm  # noqa: E402
import messages  # noqa: E402
import plans as plans_mod  # noqa: E402
import rank  # noqa: E402
import reconcile  # noqa: E402
import usage  # noqa: E402
import validate  # noqa: E402
from domain import (  # noqa: E402
    OutputRow,
    PaymentOption,
    Plan,
    Profile,
    RawEvent,
    Request,
    fmt_amount,
)


def _plan_text(plan: Plan) -> str:
    if not plan.payments or plan.method == "not_recommended":
        return "none"
    return "|".join(
        f"{p.date.isoformat()}:{plans_mod.fmt_change_amount(p.amount)}" for p in plan.payments
    )


def _changes_text(plan: Plan) -> str:
    if not plan.spending_changes:
        return "none"
    parts = []
    for change in plan.spending_changes:
        if change.kind == "stop":
            parts.append(f"stop:{change.event_id}")
        else:
            parts.append(
                f"reduce_to:{change.event_id}:{plans_mod.fmt_change_amount(change.new_amount)}"
            )
    return "|".join(parts)


def _template_explanation(request: Request, profile: Profile, plan: Plan) -> str:
    currency = profile.currency
    amount = fmt_amount(request.requested_amount)
    minimum = fmt_amount(profile.minimum_balance)
    if plan.method == "full_payment" and plan.status == "affordable_now":
        return (f"Pay {currency} {amount} today. This keeps at least "
                f"{currency} {minimum} available through the 90-day forecast.")
    if plan.method == "full_payment":
        note = " after the recommended spending change" if plan.spending_changes else ""
        return (f"Pay {currency} {amount} today{note}. This keeps at least "
                f"{currency} {minimum} available.")
    if plan.method == "partial_payment" and len(plan.payments) == 2:
        first, second = plan.payments
        return (f"Pay {currency} {fmt_amount(first.amount)} today and the remaining "
                f"{currency} {fmt_amount(second.amount)} on {second.date.isoformat()}. "
                f"This completes the request and protects the {currency} {minimum} minimum.")
    if plan.method == "installments" and plan.payments:
        first = plan.payments[0]
        return (f"Use {len(plan.payments)} installments of {currency} "
                f"{fmt_amount(first.amount)}, starting {first.date.isoformat()}. "
                f"This keeps at least {currency} {minimum} available.")
    if plan.method == "wait" and plan.payments:
        day = plan.payments[0].date
        return (f"Wait until {day.isoformat()}, then pay {currency} {amount} in full. "
                f"Paying earlier would risk the {currency} {minimum} minimum.")
    return (f"Do not proceed with the {currency} {amount} request; it cannot be completed "
            f"safely within the forecast period.")


def predict_all(
    requests: list[Request],
    profiles: dict[str, Profile],
    events_by_user: dict[str, list[RawEvent]],
    options_by_request: dict[str, list[PaymentOption]],
    rates: dict,
    amount_overrides: dict | None = None,
) -> list[OutputRow]:
    overrides = amount_overrides or {}
    rows: list[OutputRow] = []
    explanation_items: list[tuple[dict, str]] = []
    for request in requests:
        profile = profiles[request.user_id]
        events = reconcile.reconcile(
            events_by_user.get(request.user_id, []), profile, rates,
            amount_overrides=overrides,
        )
        history = [e for e in events if e.date <= request.request_date]
        future = forecast.forecast_events(events, request.request_date)

        safe = capacity.amount_safe_to_pay(profile, future, request.requested_amount)
        earliest = capacity.earliest_full_date(
            profile, request.request_date, future, request.requested_amount
        )

        candidates = plans_mod.generate(
            request, profile, history, future,
            options_by_request.get(request.request_id, []),
            safe, earliest,
        )
        chosen = rank.choose(candidates) or rank.fallback()

        if chosen.status == "not_affordable":
            earliest_text = ""
        elif chosen.status == "affordable_now":
            earliest_text = request.request_date.isoformat()
        else:
            earliest_text = earliest.isoformat() if earliest else ""

        plan_text = _plan_text(chosen)
        changes_text = _changes_text(chosen)
        template = _template_explanation(request, profile, chosen)
        facts = {
            "request_id": request.request_id,
            "request_type": request.request_type,
            "currency": profile.currency,
            "requested_amount": round(request.requested_amount, 2),
            "amount_safe_to_pay": round(safe, 2),
            "affordability_status": chosen.status,
            "recommended_payment_method": chosen.method,
            "payment_plan": plan_text,
            "earliest_date_for_full_payment": earliest_text,
            "spending_changes_needed": changes_text,
            "minimum_balance": round(profile.minimum_balance, 2),
        }
        explanation_items.append((facts, template))

        rows.append(
            OutputRow(
                request_id=request.request_id,
                amount_safe_to_pay=safe,
                affordability_status=chosen.status,
                recommended_payment_method=chosen.method,
                payment_plan=plan_text,
                earliest_date_for_full_payment=earliest_text,
                spending_changes_needed=changes_text,
                decision_explanation=template,
            )
        )
    for row, text in zip(rows, explain.generate_many(explanation_items)):
        row.decision_explanation = text
    return rows


def write_output(path: str, rows: list[OutputRow]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(config.OUTPUT_COLUMNS)
        for row in rows:
            writer.writerow(row.as_csv_row())


def main() -> None:
    requests = ingest.load_requests(config.REQUESTS_CSV)
    profiles = ingest.load_profiles()
    events_by_user = ingest.load_events()
    options_by_request = ingest.load_options()
    rates = ingest.load_rates()

    # Messages: LLM structured facts (cached per message text, only on valid structure).
    messages_by_user = ingest.load_messages()
    events_amended = messages.load_amended_events(events_by_user, messages_by_user, profiles)

    # Images: OCR + LLM for blank amounts; only settled (historical) blanks applied.
    overrides, _records = evidence.load_amount_overrides(events_by_user)

    rows = predict_all(requests, profiles, events_amended, options_by_request, rates,
                       amount_overrides=overrides)

    request_index = {r.request_id: r for r in requests}
    validate.lint(rows, request_index, options_by_request, events_by_user, profiles)
    write_output(config.OUTPUT_PATH, rows)

    usage.write_report(config.USAGE_REPORT_PATH, len(requests),
                       config.MODEL_PROVIDER, config.MODEL_ID)
    llm.write_failures(config.LLM_FAILURES_PATH)

    print(f"wrote {len(rows)} rows to {config.OUTPUT_PATH}")
    print(f"model calls: {usage.USAGE.total_calls}; llm failures: {llm.failures_summary()}")
    print("lint: OK")


if __name__ == "__main__":
    main()
