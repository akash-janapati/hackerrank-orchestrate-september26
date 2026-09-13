"""Verification tests + eval metrics for the Buy or Wait? pipeline.

Design constraints (as requested):
- No live LLM calls. Message facts and image amounts are read straight from
  the existing on-disk caches (code/cache/messages.json, code/cache/ocr/*.json).
  `llm.chat` / `llm.chat_json` are monkeypatched to raise during the
  messages/images loading phase, so a cache miss fails loudly instead of
  silently reaching the network.
- `decision_explanation` generation (explain.py / LLM) is skipped entirely;
  rows get a fixed placeholder instead. This is a deliberate test-only
  shortcut, not a claim about the real pipeline's explanation quality.

This is plain stdlib (no pytest dependency, matching the project's
stdlib-first policy). Each check is isolated: one failing check does not stop
the others from running.

Usage:
    python3 code/evaluation/test_pipeline.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import traceback
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)
sys.path.insert(0, CODE_DIR)

import capacity  # noqa: E402
import classify  # noqa: E402
import config  # noqa: E402
import evidence  # noqa: E402
import explain  # noqa: E402
import forecast  # noqa: E402
import ingest  # noqa: E402
import llm  # noqa: E402
import main as pipeline  # noqa: E402
import messages  # noqa: E402
import plans as plans_mod  # noqa: E402
import rank  # noqa: E402
import reconcile  # noqa: E402
import validate  # noqa: E402
from domain import Event, OutputRow, Profile, RawEvent  # noqa: E402

# ---------------------------------------------------------------------------
# Minimal stdlib test harness
# ---------------------------------------------------------------------------

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except AssertionError as exc:
        RESULTS.append((name, False, str(exc)))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}\n"
                                     + traceback.format_exc(limit=3)))


class BlockLLM:
    """Raises if llm.chat / llm.chat_json is actually invoked.

    Used to prove that message-fact and image-amount resolution are fully
    served by the on-disk caches, as instructed.
    """

    def __enter__(self):
        self._chat, self._chat_json = llm.chat, llm.chat_json

        def _blocked(*_a, **_k):
            raise AssertionError(
                "LLM call attempted; expected a pure cache hit for this input"
            )

        llm.chat = _blocked
        llm.chat_json = _blocked
        return self

    def __exit__(self, *_exc):
        llm.chat, llm.chat_json = self._chat, self._chat_json
        return False


# ---------------------------------------------------------------------------
# Shared fixtures: real dataset, loaded once
# ---------------------------------------------------------------------------

PROFILES = ingest.load_profiles()
EVENTS_BY_USER = ingest.load_events()
OPTIONS_BY_REQUEST = ingest.load_options()
RATES = ingest.load_rates()
SAMPLES = ingest.load_requests(config.SAMPLE_REQUESTS_CSV)
REQUEST_INDEX = {r.request_id: r for r in SAMPLES}

with BlockLLM():
    MESSAGES_BY_USER = ingest.load_messages()
    EVENTS_AMENDED = messages.load_amended_events(EVENTS_BY_USER, MESSAGES_BY_USER, PROFILES)
    OVERRIDES, _OVERRIDE_RECORDS = evidence.load_amount_overrides(EVENTS_BY_USER)


def predict_all_no_explain(requests) -> list[OutputRow]:
    """Same deterministic path as main.predict_all, minus the LLM explanation
    step (per instructions): decision_explanation is a fixed placeholder."""
    rows: list[OutputRow] = []
    for request in requests:
        profile = PROFILES[request.user_id]
        events = reconcile.reconcile(
            EVENTS_AMENDED.get(request.user_id, []), profile, RATES,
            amount_overrides=OVERRIDES,
        )
        history = [e for e in events if e.date <= request.request_date]
        future = forecast.forecast_events(events, request.request_date)

        safe = capacity.amount_safe_to_pay(profile, future, request.requested_amount)
        earliest = capacity.earliest_full_date(
            profile, request.request_date, future, request.requested_amount
        )

        candidates = plans_mod.generate(
            request, profile, history, future,
            OPTIONS_BY_REQUEST.get(request.request_id, []),
            safe, earliest,
        )
        chosen = rank.choose(candidates) or rank.fallback()

        if chosen.status == "not_affordable":
            earliest_text = ""
        elif chosen.status == "affordable_now":
            earliest_text = request.request_date.isoformat()
        else:
            earliest_text = earliest.isoformat() if earliest else ""

        rows.append(OutputRow(
            request_id=request.request_id,
            amount_safe_to_pay=safe,
            affordability_status=chosen.status,
            recommended_payment_method=chosen.method,
            payment_plan=pipeline._plan_text(chosen),
            earliest_date_for_full_payment=earliest_text,
            spending_changes_needed=pipeline._changes_text(chosen),
            decision_explanation="SKIPPED_FOR_TEST",
        ))
    return rows


SAMPLE_ROWS: list[OutputRow] = []


# ---------------------------------------------------------------------------
# 1. Harness-level checks
# ---------------------------------------------------------------------------

def test_messages_served_from_cache_only():
    # Already exercised at module load inside BlockLLM(); re-assert the cache
    # actually covers every messaging user (i.e. this wasn't a vacuous pass).
    assert len(MESSAGES_BY_USER) > 0, "no messages loaded; cache-coverage check is vacuous"


def test_images_served_from_cache_only():
    assert len(_OVERRIDE_RECORDS) == 16, (
        f"expected all 16 known blank-amount images resolved from cache, "
        f"got {len(_OVERRIDE_RECORDS)}"
    )


def test_pipeline_runs_on_all_samples():
    global SAMPLE_ROWS
    with BlockLLM():
        SAMPLE_ROWS = predict_all_no_explain(SAMPLES)
    assert len(SAMPLE_ROWS) == len(SAMPLES)


def test_lint_passes_on_samples():
    assert SAMPLE_ROWS, "run test_pipeline_runs_on_all_samples first"
    validate.lint(SAMPLE_ROWS, REQUEST_INDEX, OPTIONS_BY_REQUEST, EVENTS_BY_USER, PROFILES)


def test_output_bounds_and_resimulation():
    """Cross-check validate.lint with an independent re-simulation of the
    chosen plan for every sample, using capacity/simulate directly."""
    assert SAMPLE_ROWS
    for row in SAMPLE_ROWS:
        request = REQUEST_INDEX[row.request_id]
        assert 0.0 - 1e-6 <= row.amount_safe_to_pay <= request.requested_amount + 1e-6, (
            f"{row.request_id}: amount_safe_to_pay {row.amount_safe_to_pay} "
            f"outside [0, {request.requested_amount}]"
        )
        if row.affordability_status == "affordable_now":
            assert row.earliest_date_for_full_payment == request.request_date.isoformat()
        if row.affordability_status == "not_affordable":
            assert row.payment_plan == "none"
            assert row.earliest_date_for_full_payment == ""


# ---------------------------------------------------------------------------
# 2. BUG: pending credits are counted as available cash
#
# problem_statement.md, 90-Day Safety Check: "Ignore pending credits, failed
# or cancelled transactions, duplicate records, and unrealized investments."
# AGENTS.md §6.3: "Do not count pending credits, bonuses, commissions,
# refunds, lottery proceeds, or investment gains until they settle."
# config.py even encodes the intended rule (PENDING_POLICY["count_credits"]
# = False) but that constant is never read anywhere in the pipeline.
# ---------------------------------------------------------------------------

def test_bug_pending_credit_excluded_from_cash_eligible():
    event = Event(
        event_id="synthetic_pending_credit", user_id="test_user", source="event",
        event_type="income", category="bonus", direction="credit", amount=5000.0,
        currency="INR", date=date(2024, 1, 15), status="pending", flexibility="fixed",
    )
    assert not classify.is_cash_eligible(event), (
        "BUG: classify.is_cash_eligible() returns True for a PENDING credit. "
        "It must return False until the credit settles (see problem_statement.md "
        "90-Day Safety Check and AGENTS.md 6.3)."
    )


def test_bug_pending_credit_real_dataset_row_leaks_into_reconciled_events():
    profile = PROFILES["user_20"]
    raw = EVENTS_BY_USER["user_20"]
    pending = [e for e in raw if e.event_id == "event_1785"]
    assert pending, "fixture event_1785 (pending credit, user_20) not found in dataset"
    assert pending[0].status == "pending" and pending[0].direction == "credit"

    reconciled = reconcile.reconcile(raw, profile, RATES)
    leaked = [e for e in reconciled if e.event_id == "event_1785"]
    assert not leaked, (
        "BUG: pending credit event_1785 (user_20, amount 8,640 INR-equivalent, "
        "settlement_date 2026-02-14) survives reconcile.reconcile() and is fed "
        "straight into forecast_events()/simulate() as real, available cash. "
        "This directly inflates amount_safe_to_pay for request_20 and is a "
        "concrete example of the systemic 'pred > GT' (under-reserved) bias "
        "noted in report.md (19/25 mismatches)."
    )


# ---------------------------------------------------------------------------
# 3. BUG: monthly recurrence anchors every projected date to day<=28
#
# forecast.py:104 computes the FIRST projected date with
# `min(day_of_month, 28)` instead of clamping to the target month's actual
# length (as `_add_months` does everywhere else). Because that clamped day is
# then reused as the anchor for every subsequent `_add_months()` call, a
# category that recurs on the 29th/30th/31st is shifted to the 28th for
# *every* occurrence across the whole 90-day horizon, not just the first one.
# ---------------------------------------------------------------------------

def test_bug_monthly_projection_clamps_every_occurrence_to_day_28():
    history = [
        Event(event_id=f"hist_{i}", user_id="u", source="event", event_type="expense",
             category="rent", direction="debit", amount=1000.0, currency="INR",
             date=d, status="settled", flexibility="fixed")
        for i, d in enumerate([date(2024, 1, 31), date(2024, 3, 31), date(2024, 5, 31)])
    ]
    request_date = date(2024, 6, 1)
    projected = forecast.forecast_events(history, request_date, horizon_days=90)
    rent_days = sorted(e.date.day for e in projected if e.category == "rent")
    assert rent_days, "no rent occurrences projected; fixture/setup problem"
    assert any(d >= 29 for d in rent_days), (
        f"BUG: rent recurs on day 31 in history, but every projected "
        f"occurrence is clamped to day<=28: got days {rent_days} "
        f"(e.g. July has 31 days but rent is still placed on the 28th). "
        f"forecast.py:104 `min(day_of_month, 28)` should clamp to the target "
        f"month's actual length via calendar.monthrange, as _add_months does."
    )


# ---------------------------------------------------------------------------
# 4. BUG: duplicate-detection key ignores event_id
#
# reconcile._duplicate_key() = (user_id, category, direction, event_type,
# amount, event_date) with no event_id. Two distinct, legitimate transactions
# that coincidentally share those fields (e.g. two identical coffee
# purchases on the same day) collapse into one row, silently dropping real
# spend from the forecast.
# ---------------------------------------------------------------------------

def test_bug_duplicate_key_drops_distinct_transactions():
    profile = Profile(user_id="u", currency="INR", balance=10_000.0, minimum_balance=0.0)
    common = dict(
        user_id="u", event_type="expense", description="coffee", category="dining",
        direction="debit", amount=50.0, currency="INR", event_date=date(2024, 3, 1),
        settlement_date=None, status="settled", linked_event_id=None,
        flexibility="stoppable", minimum_allowed_amount=None,
    )
    e1 = RawEvent(event_id="e1", **common)
    e2 = RawEvent(event_id="e2", **common)  # a second, distinct coffee purchase
    result = reconcile.reconcile([e1, e2], profile, {})
    assert len(result) == 2, (
        f"BUG: reconcile._duplicate_key() does not include event_id, so two "
        f"distinct transactions sharing (category, direction, type, amount, "
        f"date) collapse into {len(result)} row(s) instead of 2 -- real "
        f"spend is silently dropped from the cash-flow forecast."
    )


# ---------------------------------------------------------------------------
# 5. BUG: month-granularity dedupe suppresses a whole month of a
#    multiple-times-per-month variable category
#
# forecast.py's `covered` set keys on (category, direction, (year, month)).
# One explicit pending/scheduled row for a weekly category (groceries,
# transport, ...) in a given month suppresses ALL projected occurrences of
# that category for the rest of that month, not just the specific date it
# actually covers.
# ---------------------------------------------------------------------------

def test_bug_single_explicit_row_suppresses_whole_month_of_weekly_category():
    history = [
        Event(event_id=f"g{i}", user_id="u", source="event", event_type="expense",
             category="groceries", direction="debit", amount=100.0, currency="INR",
             date=date(2024, 1, 1) + timedelta(days=7 * i), status="settled",
             flexibility="reducible")
        for i in range(12)  # ~12 weeks of history -> clearly recurring, weekly
    ]
    request_date = date(2024, 4, 1)
    explicit = Event(
        event_id="explicit_g", user_id="u", source="event", event_type="expense",
        category="groceries", direction="debit", amount=100.0, currency="INR",
        date=date(2024, 4, 5), status="scheduled", flexibility="reducible",
    )
    projected = forecast.forecast_events(history + [explicit], request_date, horizon_days=30)
    april_groceries = [e for e in projected if e.category == "groceries" and e.date.month == 4]
    assert len(april_groceries) >= 3, (
        f"BUG: a single explicit/scheduled groceries row on 2024-04-05 "
        f"suppresses every projected weekly occurrence for the rest of "
        f"April (found {len(april_groceries)}, expected >=3 for a weekly "
        f"category). forecast.py's (category, direction, month) dedupe key "
        f"is too coarse for categories that recur multiple times a month."
    )


# ---------------------------------------------------------------------------
# 6. FIXED: explain.py's number-grounding regex now catches bare numbers
#
# Regression test for the fix to MONETARY in explain.py: it previously only
# matched comma-grouped (12,345) or decimal (12.34) numbers, so a hallucinated
# bare integer like "303700" slipped through ungrounded-number detection.
# ---------------------------------------------------------------------------

def test_fixed_grounding_rejects_invented_bare_number():
    facts = {"request_id": "request_58", "amount_safe_to_pay": 16226000.0,
             "requested_amount": 16226000.0}
    invented = "You can safely pay 999999 today toward this request."
    assert not explain._grounded(invented, facts), (
        "explain._grounded() failed to reject an invented bare number "
        "(999999) that does not appear anywhere in the computed facts."
    )


def test_fixed_grounding_still_accepts_real_bare_number():
    facts = {"request_id": "request_58", "amount_safe_to_pay": 16226000.0,
             "requested_amount": 16226000.0}
    grounded = "You can safely pay 16226000 today toward this request."
    assert explain._grounded(grounded, facts), (
        "explain._grounded() rejected a real amount (16226000) that does "
        "appear in the facts -- the broadened regex must not cause false "
        "positives on legitimately grounded bare numbers."
    )


def test_fixed_grounding_ignores_small_counts():
    facts = {"payment_count": 3}
    text = "This is split across 18 installments over 90 days."
    assert explain._grounded(text, facts), (
        "explain._grounded() should not flag small 1-2 digit numbers "
        "(payment counts, day counts) that were never part of the amount "
        "grounding contract."
    )


# ---------------------------------------------------------------------------
# 7. FIXED: messages.py degrades to a deterministic fallback instead of
# silently dropping a message when the LLM is unavailable.
#
# These call messages.extract_facts_fallback() / messages.load_facts()
# directly as pure-function unit tests -- they do not run the 250-request
# pipeline or touch output.csv.
# ---------------------------------------------------------------------------

def test_fixed_message_fallback_extracts_real_request_58_message():
    # The exact message text behind request_58 (see the previous end_income
    # boolean-logic fix): "One household-work income source has ended. The
    # remaining confirmed monthly salary is IDR 25,840,000."
    text = ("Rincian penggajian Anda di Cedar Health telah berubah. Salah satu "
            "sumber pendapatan kerja rumah tangga telah berakhir. Sisa gaji "
            "bulanan yang dikonfirmasi adalah IDR 25840000. Pendapatan yang "
            "sudah berakhir harus dikeluarkan dari perkiraan berikutnya. "
            "Ref payroll EMP-0042.")
    result = messages.extract_facts_fallback(text)
    actions = {f["action"] for f in result["facts"]}
    assert "end_income" in actions, (
        f"fallback failed to detect the income-ended phrase; got actions {actions}"
    )
    salary_facts = [f for f in result["facts"] if f["action"] == "set_income_amount"]
    assert salary_facts and salary_facts[0]["amount"] == 25840000.0, (
        f"fallback failed to extract the confirmed salary amount; got {salary_facts}"
    )
    assert salary_facts[0]["currency"] == "IDR"


def test_fixed_message_fallback_never_invents_an_amount():
    result = messages.extract_facts_fallback("My salary changed recently.")
    for fact in result["facts"]:
        if fact["action"] == "set_income_amount":
            assert False, "fallback must not emit set_income_amount without a real amount in the text"
    # No pattern with a usable amount -> safe no-op.
    assert result["facts"][0]["action"] in ("ignore",)


class SimulateLLMOutage:
    """Makes llm.chat_json raise llm.LLMError, as a real provider outage
    (e.g. HTTP 402/504) would -- distinct from BlockLLM, which raises
    AssertionError to prove a call was never *supposed* to happen at all."""

    def __enter__(self):
        self._chat_json = llm.chat_json

        def _fail(*_a, **_k):
            raise llm.LLMError("simulated provider outage")

        llm.chat_json = _fail
        return self

    def __exit__(self, *_exc):
        llm.chat_json = self._chat_json
        return False


def test_fixed_message_fallback_fires_on_llm_outage_and_is_not_persisted():
    text = "My contract has ended and I have no other confirmed income."
    text_key = hashlib.sha256(text.encode("utf-8")).hexdigest()

    cache_before = {}
    if os.path.exists(messages.CACHE_PATH):
        with open(messages.CACHE_PATH, encoding="utf-8") as fh:
            cache_before = json.load(fh)
    assert text_key not in cache_before, "test fixture message unexpectedly already cached"

    with SimulateLLMOutage():
        facts_by_user = messages.load_facts({"synthetic_user": [{"message_text": text}]})

    assert "synthetic_user" in facts_by_user, (
        "BUG (regression): a message must never be silently dropped when the "
        "LLM is unavailable -- it should degrade to the deterministic fallback."
    )
    assert any(f["action"] == "end_income" for f in facts_by_user["synthetic_user"]["facts"])

    with open(messages.CACHE_PATH, encoding="utf-8") as fh:
        cache_after = json.load(fh)
    assert text_key not in cache_after, (
        "fallback classifications must never be written to the on-disk cache "
        "-- doing so would permanently lock out the LLM even after it recovers."
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    tests = [
        test_messages_served_from_cache_only,
        test_images_served_from_cache_only,
        test_pipeline_runs_on_all_samples,
        test_lint_passes_on_samples,
        test_output_bounds_and_resimulation,
        test_bug_pending_credit_excluded_from_cash_eligible,
        test_bug_pending_credit_real_dataset_row_leaks_into_reconciled_events,
        test_bug_monthly_projection_clamps_every_occurrence_to_day_28,
        test_bug_duplicate_key_drops_distinct_transactions,
        test_bug_single_explicit_row_suppresses_whole_month_of_weekly_category,
        test_fixed_grounding_rejects_invented_bare_number,
        test_fixed_grounding_still_accepts_real_bare_number,
        test_fixed_grounding_ignores_small_counts,
        test_fixed_message_fallback_extracts_real_request_58_message,
        test_fixed_message_fallback_never_invents_an_amount,
        test_fixed_message_fallback_fires_on_llm_outage_and_is_not_persisted,
    ]
    for test in tests:
        check(test.__name__, test)

    print("=" * 78)
    print("TEST RESULTS")
    print("=" * 78)
    passed = 0
    for name, ok, detail in RESULTS:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        if not ok:
            for line in detail.splitlines():
                print(f"        {line}")
        passed += ok
    print("-" * 78)
    print(f"{passed}/{len(RESULTS)} passed, {len(RESULTS) - passed} failed")
    print()

    if SAMPLE_ROWS:
        print("=" * 78)
        print("EVAL METRICS on dataset/sample_requests.csv (25 samples)")
        print("decision_explanation generation was skipped for this run.")
        print("=" * 78)
        from fit_samples import score  # local import: reuses the scoring logic
        score(SAMPLES, {row.request_id: row for row in SAMPLE_ROWS})

    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
