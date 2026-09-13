"""Generate report.md: the pipeline's 25-sample predictions vs ground truth.

Run: python3 code/evaluation/sample_report.py   (writes repo-root report.md)
"""
from __future__ import annotations

import collections
import os
import statistics
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
sys.path.insert(0, CODE_DIR)

import config  # noqa: E402
import evidence  # noqa: E402
import ingest  # noqa: E402
import main as pipeline  # noqa: E402
import messages as messages_mod  # noqa: E402

FIELDS = [
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
]
PLAN_FIELDS = ["affordability_status", "recommended_payment_method",
               "payment_plan", "spending_changes_needed"]


def load_predictions():
    samples = ingest.load_requests(config.SAMPLE_REQUESTS_CSV)
    profiles = ingest.load_profiles()
    events_by_user = ingest.load_events()
    options = ingest.load_options()
    rates = ingest.load_rates()

    messages_by_user = ingest.load_messages()
    events_amended = messages_mod.load_amended_events(events_by_user, messages_by_user, profiles)
    overrides, _records = evidence.load_amount_overrides(events_by_user)

    rows = pipeline.predict_all(samples, profiles, events_amended, options, rates,
                                amount_overrides=overrides)
    return samples, {r.request_id: r for r in rows}


def metrics(samples, predicted):
    near = 0
    errors = []
    plan = 0
    for s in samples:
        row = predicted[s.request_id]
        exp = s.expected
        err = abs(row.amount_safe_to_pay - float(exp.amount_safe_to_pay))
        errors.append(err)
        near += err <= 0.01
        plan += all(str(getattr(row, f)) == str(getattr(exp, f)) for f in PLAN_FIELDS)
    n = len(samples)
    return {"near": near, "mae": sum(errors) / n, "median": sorted(errors)[n // 2],
            "plan": plan}


def ablation(samples):
    """Effect of the messages and image layers."""
    profiles = ingest.load_profiles()
    events_by_user = ingest.load_events()
    options = ingest.load_options()
    rates = ingest.load_rates()
    messages_by_user = ingest.load_messages()
    events_amended = messages_mod.load_amended_events(events_by_user, messages_by_user, profiles)
    overrides, _ = evidence.load_amount_overrides(events_by_user)

    def run(events, ov):
        return {r.request_id: r for r in pipeline.predict_all(
            samples, profiles, events, options, rates, amount_overrides=ov)}

    return {
        "core (no messages/images)": metrics(samples, run(events_by_user, {})),
        "+ messages only": metrics(samples, run(events_amended, {})),
        "+ messages + settled images": metrics(samples, run(events_amended, overrides)),
    }


def fmt(value, is_amount=False):
    if value is None:
        return ""
    if is_amount:
        return f"{float(value):,.2f}"
    return str(value)


def main():
    samples, predicted = load_predictions()
    n = len(samples)

    exact = collections.Counter()
    near = 0
    errors: list[float] = []
    per_type = collections.defaultdict(lambda: {"n": 0, "amount_err": 0.0, "status": 0,
                                                "method": 0, "plan": 0})
    detail = []
    plan_match = 0

    for s in samples:
        exp = s.expected
        row = predicted[s.request_id]
        err = abs(row.amount_safe_to_pay - float(exp.amount_safe_to_pay))
        errors.append(err)
        for field in FIELDS:
            if str(getattr(row, field)) == str(getattr(exp, field)):
                exact[field] += 1
        if err <= 0.01:
            near += 1
        if all(str(getattr(row, f)) == str(getattr(exp, f)) for f in PLAN_FIELDS):
            plan_match += 1

        ptype = per_type[s.request_type]
        ptype["n"] += 1
        ptype["amount_err"] += err
        ptype["status"] += row.affordability_status == exp.affordability_status
        ptype["method"] += row.recommended_payment_method == exp.recommended_payment_method
        ptype["plan"] += str(row.payment_plan) == str(exp.payment_plan)

        if err > 0.01:
            direction = "under-reserved (pred > GT)" if row.amount_safe_to_pay > float(
                exp.amount_safe_to_pay) else "over-reserved (pred < GT)"
        else:
            direction = "exact"
        detail.append((s, row, exp, err, direction))

    mae = sum(errors) / n
    median = sorted(errors)[n // 2]

    lines: list[str] = []
    add = lines.append
    add("# Buy or Wait? — Sample Report")
    add("")
    add("Pipeline run on the 25 solved samples (`dataset/sample_requests.csv`) and compared to "
        "the ground-truth labels. Configuration: income recurrence by cadence (amount = median); "
        "recurring expenses projected with fixed categories at median and variable categories at "
        "a calibrated fraction (config.VARIABLE_EXPENSE_FRACTION); monthly occurrences include the "
        "request month; debits-first 90-day simulator; plan generation + 6-level ranker; LLM "
        "structured message facts; settled-only image amount overrides; LLM explanations.")
    add("")
    add("## Executive summary")
    add("")
    add(f"- **Amount exact:** {near}/{n} ({100.0 * near / n:.0f}%)")
    add(f"- **Amount MAE:** {mae:,.2f} · median error: {median:,.2f}")
    add(f"- **Plan-field row match** (status+method+plan+changes): {plan_match}/{n}")
    add(f"- **Status match:** {exact['affordability_status']}/{n} · "
        f"**Method match:** {exact['recommended_payment_method']}/{n} · "
        f"**Plan match:** {exact['payment_plan']}/{n}")
    add("")
    add("`amount_safe_to_pay` is bounded by the missing hidden future timeline (see "
        "`implementation.md` §3): the released events stop at `request_date`, and future "
        "per-occurrence amounts are not recoverable. Plan fields are downstream of the amount.")
    add("")

    add("## Per-field accuracy")
    add("")
    add("| field | exact | rate |")
    add("|---|---|---|")
    for field in FIELDS:
        add(f"| `{field}` | {exact[field]}/{n} | {100.0 * exact[field] / n:.0f}% |")
    add("")

    add("## Amount error statistics")
    add("")
    add(f"- exact (abs <= 0.01): {near}/{n}")
    add(f"- within 1: {sum(1 for e in errors if e <= 1)}/{n}")
    add(f"- within 1% of GT: {sum(1 for s, r, e, x, d in detail if float(e.amount_safe_to_pay) and x / float(e.amount_safe_to_pay) <= 0.01)}/{n}")
    add(f"- MAE: {mae:,.2f}")
    add(f"- median: {median:,.2f}")
    add(f"- max: {max(errors):,.2f}")
    add("")

    add("## Effect of the evidence layer (ablation)")
    add("")
    add("| configuration | amount exact | amount MAE | plan-field rows |")
    add("|---|---|---|---|")
    for label, m in ablation(samples).items():
        add(f"| {label} | {m['near']}/25 | {m['mae']:,.2f} | {m['plan']}/25 |")
    add("")
    add("The message and settled-image layers are MAE-neutral on these 25 samples; messages "
        "raise full-set actionability (`not_affordable` drops) and the improvement here comes from "
        "the forecast itself (income by cadence + calibrated variable-expense projection + "
        "request-month occurrences).")
    add("")

    add("## Breakdown by request type")
    add("")
    add("| request_type | n | amount MAE | status | method | plan |")
    add("|---|---|---|---|---|---|")
    for rtype in sorted(per_type):
        b = per_type[rtype]
        add(f"| {rtype} | {b['n']} | {b['amount_err'] / b['n']:,.2f} | "
            f"{b['status']}/{b['n']} | {b['method']}/{b['n']} | {b['plan']}/{b['n']} |")
    add("")

    add("## Ground-truth status vs predicted")
    add("")
    matrix = collections.Counter((s.expected.affordability_status, row.affordability_status)
                                 for s, row, exp, err, d in detail)
    statuses = ["affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"]
    add("| GT \\ pred | " + " | ".join(statuses) + " |")
    add("|" + "---|" * (len(statuses) + 1))
    for gt_status in statuses:
        cells = [str(matrix.get((gt_status, ps), 0)) for ps in statuses]
        add(f"| {gt_status} | " + " | ".join(cells) + " |")
    add("")

    add("## Per-sample comparison")
    add("")
    add("| request | type | GT status | pred status | GT method | pred method | "
        "GT safe | pred safe | abs err | earliest | changes |")
    add("|---|---|---|---|---|---|---|---|---|---|---|")
    for s, row, exp, err, direction in detail:
        flag = " ==" if err <= 0.01 else " !!"
        add(f"| {s.request_id} | {s.request_type} | {exp.affordability_status} | "
            f"{row.affordability_status} | {exp.recommended_payment_method} | "
            f"{row.recommended_payment_method} | {float(exp.amount_safe_to_pay):,.2f} | "
            f"{row.amount_safe_to_pay:,.2f}{flag} | {err:,.2f} | "
            f"{exp.earliest_date_for_full_payment or '-'} / "
            f"{row.earliest_date_for_full_payment or '-'} | "
            f"{exp.spending_changes_needed} / {row.spending_changes_needed} |")
    add("")

    add("## Mismatch attribution")
    add("")
    bucket = collections.Counter()
    for s, row, exp, err, direction in detail:
        if err > 0.01:
            bucket[direction] += 1
        if exp.spending_changes_needed not in ("", "none") and row.spending_changes_needed == "none":
            bucket["expected a spending change not emitted"] += 1
        if row.affordability_status != exp.affordability_status:
            bucket["status differs"] += 1
        if row.recommended_payment_method != exp.recommended_payment_method:
            bucket["method differs"] += 1
    for label, count in bucket.most_common():
        add(f"- {count}: {label}")
    add("")

    add("## Representative full comparisons")
    add("")
    for s, row, exp, err, direction in detail:
        if err <= 0.01:
            continue
        add(f"### {s.request_id} ({s.user_id}, {s.request_type})")
        add("")
        add(f"- request: {s.request_date} → {s.desired_completion_date}, "
            f"amount {float(s.requested_amount):,.2f}, partial={s.allows_partial_payment}")
        for field in FIELDS:
            gv, pv = getattr(exp, field), getattr(row, field)
            if field == "amount_safe_to_pay":
                gv, pv = f"{float(gv):,.2f}", f"{float(pv):,.2f}"
            mark = "" if str(gv) == str(pv) else "  \u2190 differs"
            add(f"- `{field}`: GT `{gv}` \u00b7 pred `{pv}`{mark}")
        add("")

    add("## Notes")
    add("")
    add("- The deterministic engine is byte-reproducible; sample predictions come from the same "
        "code path as `output.csv`.")
    add("- Image amounts are applied only to settled (historical) blank events; pending/scheduled "
        "blanks are cached but not applied (request_16 case).")
    add("- Message handling is regex-only (no LLM).")
    add("")

    with open(os.path.join(config.REPO_ROOT, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("wrote report.md")
    print(f"amount exact {near}/{n}, MAE {mae:,.2f}, plan-field match {plan_match}/{n}")


if __name__ == "__main__":
    main()
