"""Domain objects shared across the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


def fmt_amount(value: float) -> str:
    """Format an amount without trailing zeros, keeping cents when present."""
    if value is None:
        return "0"
    text = f"{float(value):.2f}"
    text = text.rstrip("0").rstrip(".")
    return text or "0"


@dataclass(frozen=True)
class Profile:
    user_id: str
    currency: str
    balance: float
    minimum_balance: float
    priorities: tuple[str, ...] = ()
    protected: frozenset[str] = frozenset()
    reducible: frozenset[str] = frozenset()
    stoppable: frozenset[str] = frozenset()
    methods: frozenset[str] = frozenset()
    max_installment_months: Optional[int] = None


@dataclass(frozen=True)
class Request:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: float
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str
    # Optional solved-output fields, present only for sample_requests.csv
    expected: Optional["OutputRow"] = None


@dataclass(frozen=True)
class RawEvent:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: Optional[float]
    currency: str
    event_date: date
    settlement_date: Optional[date]
    status: str
    linked_event_id: Optional[str]
    flexibility: str
    minimum_allowed_amount: Optional[float]

    def cash_date(self) -> date:
        return self.settlement_date or self.event_date


@dataclass(frozen=True)
class Event:
    """Canonical cash event after reconciliation + forecast expansion."""

    event_id: str
    user_id: str
    source: str            # "event" | "message_fact" | "forecast"
    event_type: str
    category: str
    direction: str         # debit | credit
    amount: float
    currency: str
    date: date
    status: str
    flexibility: str
    minimum_allowed_amount: Optional[float] = None
    linked_event_id: Optional[str] = None
    recurrence: str = "one_time"
    description: str = ""


@dataclass(frozen=True)
class PaymentOption:
    option_id: str
    request_id: str
    method: str
    payment_amount: float
    number_of_payments: int
    first_payment_date: date
    frequency_days: Optional[int]
    financing_fee: float
    total_payable_amount: float


@dataclass(frozen=True)
class FactChange:
    target: str
    field: str
    new_value: object
    effective_date: Optional[date]
    action: str
    confidence: float
    source_message_id: str
    rationale: str = ""


@dataclass(frozen=True)
class Payment:
    date: date
    amount: float


@dataclass(frozen=True)
class SpendingChange:
    kind: str              # "stop" | "reduce_to"
    event_id: str
    new_amount: Optional[float] = None
    category: Optional[str] = None


@dataclass
class Plan:
    method: str
    payments: list[Payment] = field(default_factory=list)
    spending_changes: list[SpendingChange] = field(default_factory=list)
    status: str = "not_affordable"
    earliest_full: Optional[date] = None
    total_paid: float = 0.0
    option_id: Optional[str] = None
    rank_key: tuple = ()


@dataclass
class SimulationResult:
    daily_balances: dict[date, float]
    minimum: float
    safe: bool
    breach_date: Optional[date] = None


@dataclass
class RequestContext:
    request: Request
    profile: Profile
    events: list[RawEvent] = field(default_factory=list)
    options: list[PaymentOption] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)


@dataclass
class OutputRow:
    request_id: str
    amount_safe_to_pay: float
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: str
    spending_changes_needed: str
    decision_explanation: str

    def as_csv_row(self) -> list[str]:
        return [
            self.request_id,
            fmt_amount(self.amount_safe_to_pay),
            self.affordability_status,
            self.recommended_payment_method,
            self.payment_plan,
            self.earliest_date_for_full_payment,
            self.spending_changes_needed,
            self.decision_explanation,
        ]
