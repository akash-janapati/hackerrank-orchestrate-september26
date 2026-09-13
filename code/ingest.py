"""Dataset loading, indexing, and FX helpers.

All loaders are read-only with respect to dataset/.
"""
from __future__ import annotations

import csv
import os
from datetime import date
from typing import Optional

import config
from domain import OutputRow, PaymentOption, Profile, RawEvent, Request


# --- primitive parsers -----------------------------------------------------
def _rows(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _clean(value) -> str:
    return (value or "").strip()


def parse_date(value) -> Optional[date]:
    text = _clean(value)
    if not text:
        return None
    return date.fromisoformat(text[:10])


def parse_float(value) -> Optional[float]:
    text = _clean(value)
    if not text:
        return None
    return float(text.replace(",", ""))


def parse_int(value) -> Optional[int]:
    text = _clean(value)
    if not text:
        return None
    return int(float(text))


def parse_pipe_set(value) -> frozenset[str]:
    text = _clean(value)
    if not text:
        return frozenset()
    return frozenset(part.strip() for part in text.split("|") if part.strip())


def parse_bool(value) -> bool:
    return _clean(value).lower() == "true"


# --- entity loaders --------------------------------------------------------
def load_profiles() -> dict[str, Profile]:
    profiles: dict[str, Profile] = {}
    for row in _rows(config.PROFILES_CSV):
        profiles[row["user_id"]] = Profile(
            user_id=row["user_id"],
            currency=_clean(row["home_currency"]),
            balance=float(row["current_available_balance"]),
            minimum_balance=float(row["minimum_balance_to_keep"]),
            priorities=tuple(parse_pipe_set(row.get("financial_priorities", ""))),
            protected=parse_pipe_set(row.get("expense_categories_to_protect", "")),
            reducible=parse_pipe_set(row.get("expense_categories_user_is_willing_to_reduce", "")),
            stoppable=parse_pipe_set(row.get("expense_categories_user_is_willing_to_stop", "")),
            methods=parse_pipe_set(row.get("payment_methods_user_will_consider", "")),
            max_installment_months=parse_int(row.get("max_installment_months", "")),
        )
    return profiles


def load_events() -> dict[str, list[RawEvent]]:
    by_user: dict[str, list[RawEvent]] = {}
    for row in _rows(config.EVENTS_CSV):
        event = RawEvent(
            event_id=row["event_id"],
            user_id=row["user_id"],
            event_type=_clean(row["event_type"]),
            description=_clean(row.get("description", "")),
            category=_clean(row["category"]),
            direction=_clean(row["direction"]),
            amount=parse_float(row.get("amount", "")),
            currency=_clean(row["currency"]),
            event_date=parse_date(row["event_date"]),
            settlement_date=parse_date(row.get("settlement_date", "")),
            status=_clean(row["status"]),
            linked_event_id=_clean(row.get("linked_event_id", "")) or None,
            flexibility=_clean(row.get("flexibility", "fixed")),
            minimum_allowed_amount=parse_float(row.get("minimum_allowed_amount", "")),
        )
        by_user.setdefault(event.user_id, []).append(event)
    for events in by_user.values():
        events.sort(key=lambda e: (e.event_date, e.event_id))
    return by_user


def load_options() -> dict[str, list[PaymentOption]]:
    by_request: dict[str, list[PaymentOption]] = {}
    for row in _rows(config.OPTIONS_CSV):
        option = PaymentOption(
            option_id=row["payment_option_id"],
            request_id=row["request_id"],
            method=_clean(row["payment_method"]),
            payment_amount=float(row["payment_amount"]),
            number_of_payments=parse_int(row["number_of_payments"]) or 1,
            first_payment_date=parse_date(row["first_payment_date"]),
            frequency_days=parse_int(row.get("payment_frequency_days", "")),
            financing_fee=float(row.get("financing_fee") or 0),
            total_payable_amount=float(
                row.get("total_payable_amount") or row["payment_amount"]
            ),
        )
        by_request.setdefault(option.request_id, []).append(option)
    return by_request


def load_messages() -> dict[str, list[dict]]:
    by_user: dict[str, list[dict]] = {}
    for row in _rows(config.MESSAGES_CSV):
        by_user.setdefault(row["user_id"], []).append(row)
    return by_user


def load_images() -> tuple[dict[str, dict], list[dict]]:
    rows = _rows(config.IMAGES_CSV)
    by_event = {row["related_event_id"]: row for row in rows if _clean(row.get("related_event_id"))}
    return by_event, rows


def load_rates() -> dict[tuple[str, str], list[tuple[date, float]]]:
    rates: dict[tuple[str, str], list[tuple[date, float]]] = {}
    for row in _rows(config.RATES_CSV):
        key = (_clean(row["from_currency"]), _clean(row["to_currency"]))
        rates.setdefault(key, []).append((parse_date(row["rate_date"]), float(row["rate"])))
    for key in rates:
        rates[key].sort()
    return rates


def _expected_output(row: dict) -> Optional[OutputRow]:
    if "affordability_status" not in row or not _clean(row.get("affordability_status", "")):
        return None
    return OutputRow(
        request_id=row["request_id"],
        amount_safe_to_pay=float(row["amount_safe_to_pay"]),
        affordability_status=_clean(row["affordability_status"]),
        recommended_payment_method=_clean(row["recommended_payment_method"]),
        payment_plan=_clean(row["payment_plan"]),
        earliest_date_for_full_payment=_clean(row.get("earliest_date_for_full_payment", "")),
        spending_changes_needed=_clean(row.get("spending_changes_needed", "")),
        decision_explanation=_clean(row.get("decision_explanation", "")),
    )


def load_requests(path: str) -> list[Request]:
    requests: list[Request] = []
    for row in _rows(path):
        requests.append(
            Request(
                request_id=row["request_id"],
                user_id=row["user_id"],
                request_date=parse_date(row["request_date"]),
                request_type=_clean(row["request_type"]),
                requested_amount=float(row["requested_amount"]),
                desired_completion_date=parse_date(row["desired_completion_date"]),
                allows_partial_payment=parse_bool(row["allows_partial_payment"]),
                request_text=_clean(row.get("request_text", "")),
                expected=_expected_output(row),
            )
        )
    return requests


# --- FX --------------------------------------------------------------------
def to_home(
    amount: float,
    from_currency: str,
    home_currency: str,
    on_date: date,
    rates: dict[tuple[str, str], list[tuple[date, float]]],
) -> float:
    """Convert using the stated direction; exact date preferred, then nearest."""
    if from_currency == home_currency:
        return amount
    pair = rates.get((from_currency, home_currency))
    if pair:
        rate = _pick_rate(pair, on_date)
        if rate is not None:
            return amount * rate
    inverse = rates.get((home_currency, from_currency))
    if inverse:
        rate = _pick_rate(inverse, on_date)
        if rate:
            return amount / rate
    raise KeyError(f"no exchange rate {from_currency}->{home_currency} for {on_date}")


def _pick_rate(pair: list[tuple[date, float]], on_date: date) -> Optional[float]:
    exact = [rate for day, rate in pair if day == on_date]
    if exact:
        return exact[0]
    before = [rate for day, rate in pair if day <= on_date]
    if before:
        return before[-1]
    after = [rate for day, rate in pair if day >= on_date]
    if after:
        return after[0]
    return None


def image_path(image_id: str) -> str:
    return os.path.join(config.MEDIA_DIR, f"{image_id}.png")
