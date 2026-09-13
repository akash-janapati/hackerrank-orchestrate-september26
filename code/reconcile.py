"""Reconciliation: filter, lifecycle handling, de-duplication, FX normalization.

Phase 1 has no message/image facts yet; the function accepts an (empty) fact
list so the reconciler contract is stable for Phase 3.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

import config
import ingest
from domain import Event, FactChange, Profile, RawEvent

TERMINAL_STATUSES = {"cancelled", "failed"}


def _duplicate_key(event: RawEvent) -> str:
    # event_id is the dataset's real primary key. Keying on it (rather than a
    # coincidental combination of category/direction/type/amount/date) means
    # this only ever collapses a literal repeated row, never two distinct
    # transactions that happen to share those fields.
    return event.event_id


def reconcile(
    raw_events: Iterable[RawEvent],
    profile: Profile,
    rates: dict,
    facts: Optional[list[FactChange]] = None,
    amount_overrides: Optional[dict] = None,
) -> list[Event]:
    facts = facts or []
    amount_overrides = amount_overrides or {}
    events: list[Event] = []
    seen: set[tuple] = set()

    for raw in raw_events:
        if raw.status in TERMINAL_STATUSES:
            continue
        if raw.direction == "non_cash" or raw.event_type == "investment_valuation":
            continue
        if raw.status == "unrealized":
            continue
        if raw.direction not in ("debit", "credit"):
            continue
        # Mirror classify.is_cash_eligible's pending-cash policy here too, so
        # reconcile.reconcile()'s own output is already correctly filtered
        # for any caller -- not just forecast.forecast_events(), which
        # applies the same policy a second time.
        if (raw.direction == "credit" and raw.status == "pending"
                and not config.PENDING_POLICY.get("count_credits", False)):
            continue
        if (raw.direction == "debit" and raw.status == "pending"
                and not config.PENDING_POLICY.get("reserve_debits", True)):
            continue

        amount = raw.amount if raw.amount is not None else amount_overrides.get(raw.event_id)
        if amount is None:
            # No amount from the row or a linked image; cannot enter cash flow
            # (never treat a blank amount as zero).
            continue

        key = _duplicate_key(raw)
        if key in seen:
            continue
        seen.add(key)

        home_amount = ingest.to_home(
            amount, raw.currency, profile.currency, raw.cash_date(), rates
        )

        events.append(
            Event(
                event_id=raw.event_id,
                user_id=raw.user_id,
                source="event",
                event_type=raw.event_type,
                category=raw.category,
                direction=raw.direction,
                amount=home_amount,
                currency=profile.currency,
                date=raw.cash_date(),
                status=raw.status,
                flexibility=raw.flexibility,
                minimum_allowed_amount=raw.minimum_allowed_amount,
                linked_event_id=raw.linked_event_id,
                recurrence="unknown",
                description=raw.description,
            )
        )

    return sorted(events, key=lambda e: (e.date, e.event_id))
