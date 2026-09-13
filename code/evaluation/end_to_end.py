"""End-to-end trace for a single request, written to examples/<request_id>.md.

Usage: python3 code/evaluation/end_to_end.py [request_id]

Documents the full pipeline: inputs, message facts, image extraction, reconciliation,
forecast, simulation, capacity, candidate plans, ranking, explanation, and output.
"""
from __future__ import annotations

import os
import sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
sys.path.insert(0, CODE_DIR)

import capacity  # noqa: E402
import config  # noqa: E402
import evidence  # noqa: E402
import explain  # noqa: E402
import forecast  # noqa: E402
import ingest  # noqa: E402
import main as pipeline  # noqa: E402
import messages as messages_mod  # noqa: E402
import plans as plans_mod  # noqa: E402
import rank  # noqa: E402
import reconcile  # noqa: E402
import simulate as simulate_mod  # noqa: E402

DEFAULT_REQUEST = "request_03"


def _find_request(request_id):
    for path in (config.SAMPLE_REQUESTS_CSV, config.REQUESTS_CSV):
        for request in ingest.load_requests(path):
            if request.request_id == request_id:
                return request
    raise SystemExit(f"request {request_id} not found")


def _event_line(e):
    amount = f"{e.amount:,.2f}" if e.amount is not None else "None"
    return (f"| {e.event_id} | {e.category} | {e.direction} | {amount} | {e.event_date} | "
            f"{e.settlement_date} | {e.status} | {e.flexibility} | {e.linked_event_id or '-'} |")


def main():
    request_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REQUEST
    request = _find_request(request_id)
    uid = request.user_id
    profiles = ingest.load_profiles()
    profile = profiles[uid]
    events_by_user = ingest.load_events()
    options_by_request = ingest.load_options()
    rates = ingest.load_rates()
    messages_by_user = ingest.load_messages()

    messages = messages_by_user.get(uid, [])
    facts_by_user = messages_mod.load_facts({uid: messages}) if messages else {}
    amended = messages_mod.load_amended_events(events_by_user, messages_by_user, profiles)
    overrides, records = evidence.load_amount_overrides(events_by_user)

    lines: list[str] = []
    add = lines.append
    add(f"# End-to-end trace: `{request_id}` ({uid})")
    add("")
    add("This documents one full pipeline run: inputs → message facts → image extraction → "
        "reconciliation → forecast → simulation → capacity → candidate plans → ranking → "
        "explanation → output.")
    add("")

    add("## 1. Request input (`dataset/requests.csv` or `sample_requests.csv`)")
    add("")
    add("| field | value |")
    add("|---|---|")
    for field in ("request_id", "user_id", "request_date", "request_type", "requested_amount",
                  "desired_completion_date", "allows_partial_payment"):
        add(f"| {field} | {getattr(request, field)} |")
    add(f"| request_text | {request.request_text} |")
    add("")

    add("## 2. Profile (`dataset/financial_profiles.csv`)")
    add("")
    add("| field | value |")
    add("|---|---|")
    add(f"| home_currency | {profile.currency} |")
    add(f"| current_available_balance | {profile.balance:,.2f} |")
    add(f"| minimum_balance_to_keep | {profile.minimum_balance:,.2f} |")
    add(f"| protected | {sorted(profile.protected)} |")
    add(f"| reducible | {sorted(profile.reducible)} |")
    add(f"| stoppable | {sorted(profile.stoppable)} |")
    add(f"| payment_methods_user_will_consider | {sorted(profile.methods)} |")
    add(f"| max_installment_months | {profile.max_installment_months} |")
    add("")

    add("## 3. Financial events for this user (`dataset/financial_events.csv`)")
    add("")
    add("| event_id | category | direction | amount | event_date | settlement_date | status | "
        "flexibility | linked_event_id |")
    add("|---|---|---|---|---|---|---|---|---|")
    for e in sorted(events_by_user.get(uid, []), key=lambda e: e.event_date):
        add(_event_line(e))
    add("")

    add("## 4. Messages (`dataset/messages.csv`) and LLM-extracted facts")
    add("")
    if not messages:
        add("_no message for this user_")
    for message in messages:
        add(f"**{message['message_id']}** (source={message['source_type']}, "
            f"request={message['request_id'] or '-'}, related_event={message['related_event_id'] or '-'})")
        add("")
        add(f"> {message['message_text']}")
        add("")
    entry = facts_by_user.get(uid)
    if entry:
        add(f"Extracted facts (LLM, cached): `{entry.get('facts')}`")
        add("")
        add(f"Summary: {entry.get('summary')}")
        add("")

    add("## 5. Images (`dataset/images.csv`) and extraction")
    add("")
    _, image_rows = ingest.load_images()
    user_images = [r for r in image_rows if r.get("user_id") == uid]
    applied = {r["event_id"]: r for r in records}
    if not user_images:
        add("_no image for this user_")
    for row in user_images:
        event_id = row["related_event_id"]
        record = applied.get(event_id, {})
        add(f"**{row['image_id']}** → event `{event_id}` "
            f"(`dataset/media/images/{row['image_id']}.png`)")
        add("")
        add(f"- extracted_amount: {record.get('extracted_amount')} "
            f"({record.get('currency')}, method={record.get('method')})")
        add(f"- evidence_line: {record.get('evidence_line')}")
        add(f"- applied to forecast: {record.get('applied_to_forecast')}")
        add("")

    add("## 6. Candidate plans and the ranking")
    add("")
    profile_events = reconcile.reconcile(amended.get(uid, []), profile, rates,
                                         amount_overrides=overrides)
    history = [e for e in profile_events if e.date <= request.request_date]
    future = forecast.forecast_events(profile_events, request.request_date)
    safe = capacity.amount_safe_to_pay(profile, future, request.requested_amount)
    earliest = capacity.earliest_full_date(profile, request.request_date, future,
                                           request.requested_amount)
    sim = simulate_mod.simulate(profile.balance, profile.minimum_balance, future)
    candidates = plans_mod.generate(request, profile, history, future,
                                    options_by_request.get(request_id, []), safe, earliest)
    chosen = rank.choose(candidates) or rank.fallback()

    add("### Payment options (`dataset/request_payment_options.csv`)")
    add("")
    add("| option_id | method | payment_amount | n | first_date | frequency | fee | total |")
    add("|---|---|---|---|---|---|---|---|")
    for option in options_by_request.get(request_id, []):
        add(f"| {option.option_id} | {option.method} | {option.payment_amount:,.2f} | "
            f"{option.number_of_payments} | {option.first_payment_date} | "
            f"{option.frequency_days} | {option.financing_fee:,.2f} | "
            f"{option.total_payable_amount:,.2f} |")
    add("")

    add("### Forecast and simulation")
    add("")
    add(f"- projected future events: {len(future)} "
        f"(forecast rows: {sum(1 for e in future if e.source == 'forecast')})")
    add(f"- simulated minimum balance: {sim.minimum:,.2f} "
        f"(safe={sim.safe}, breach_date={sim.breach_date})")
    add(f"- `amount_safe_to_pay` = {safe:,.2f} "
        f"(= min_balance_after_forecast − minimum_balance, capped at requested)")
    add(f"- `earliest_date_for_full_payment` = {earliest} "
        f"(without spending changes, preference-independent)")
    add("")

    add("### Candidate plans (each re-simulated for safety)")
    add("")
    add("| method | status | payments | total_paid | changes | option | rank_key |")
    add("|---|---|---|---|---|---|---|")
    for plan in candidates:
        payments = "|".join(f"{p.date}:{plans_mod.fmt_change_amount(p.amount)}"
                            for p in plan.payments) or "none"
        changes = "|".join(f"{c.kind}:{c.event_id}" for c in plan.spending_changes) or "none"
        add(f"| {plan.method} | {plan.status} | {payments} | {plan.total_paid:,.2f} | "
            f"{changes} | {plan.option_id or '-'} | {rank.rank_key(plan)} |")
    if not candidates:
        add("| _none_ | | | | | | |")
    add("")
    add(f"**Chosen (rank.choose): `{chosen.method}` / `{chosen.status}`**")
    add("")

    add("## 7. Final output row (`output.csv`)")
    add("")
    rows = pipeline.predict_all([request], profiles, amended, options_by_request, rates,
                                amount_overrides=overrides)
    row = rows[0]
    add("| column | value |")
    add("|---|---|")
    for column in config.OUTPUT_COLUMNS:
        add(f"| {column} | {getattr(row, column)} |")
    add("")

    if request.expected is not None:
        add("## 8. Ground truth (this is a solved sample)")
        add("")
        add("| field | ground truth | predicted |")
        add("|---|---|---|")
        for field in ("amount_safe_to_pay", "affordability_status",
                      "recommended_payment_method", "payment_plan",
                      "earliest_date_for_full_payment", "spending_changes_needed"):
            gt = getattr(request.expected, field)
            add(f"| {field} | {gt} | {getattr(row, field)} |")
        add("")

    out_path = os.path.join(config.REPO_ROOT, "examples", f"{request_id}.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {out_path}")
    print(f"chosen: {chosen.method} / {chosen.status}; safe={safe:,.2f}; earliest={earliest}")


if __name__ == "__main__":
    main()
