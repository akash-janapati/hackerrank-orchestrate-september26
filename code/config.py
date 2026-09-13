"""Central configuration: paths, flags, and recurrence-policy defaults.

Phase 0: paths and flags are stable; recurrence policy constants are initial
defaults to be calibrated in Phase 1.
"""
from __future__ import annotations

import os

# --- Paths -----------------------------------------------------------------
CODE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CODE_DIR)
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")
MEDIA_DIR = os.path.join(DATASET_DIR, "media", "images")
CACHE_DIR = os.path.join(CODE_DIR, "cache")

OUTPUT_PATH = os.path.join(REPO_ROOT, "output.csv")

# Input files
PROFILES_CSV = os.path.join(DATASET_DIR, "financial_profiles.csv")
EVENTS_CSV = os.path.join(DATASET_DIR, "financial_events.csv")
RATES_CSV = os.path.join(DATASET_DIR, "exchange_rates.csv")
OPTIONS_CSV = os.path.join(DATASET_DIR, "request_payment_options.csv")
MESSAGES_CSV = os.path.join(DATASET_DIR, "messages.csv")
IMAGES_CSV = os.path.join(DATASET_DIR, "images.csv")
REQUESTS_CSV = os.path.join(DATASET_DIR, "requests.csv")
SAMPLE_REQUESTS_CSV = os.path.join(DATASET_DIR, "sample_requests.csv")

USAGE_REPORT_PATH = os.path.join(CODE_DIR, "evaluation", "usage_report.md")
LLM_FAILURES_PATH = os.path.join(CODE_DIR, "evaluation", "llm_failures.md")

# --- Pipeline --------------------------------------------------------------
HORIZON_DAYS = 90

# Standard LLM (all model jobs): DeepSeek via OpenRouter
MODEL_PROVIDER = "openrouter"
MODEL_ID = os.environ.get("ORCHESTRATE_MODEL_ID", "deepseek/deepseek-chat")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"

# --- Recurrence policy defaults (calibrated in Phase 1) --------------------
# Used only by code/evaluation/eda.py's exploratory diagnostics, not by the
# production forecast.py pipeline (which uses full history + MIN_OCCURRENCES
# instead of a trailing window -- a trailing window this short is incompatible
# with requiring multiple distinct months of history).
TRAILING_WINDOW = 30          # days of history anchoring the eda.py projection
MIN_OCCURRENCES = 3           # distinct months before a category is recurring
VARIABLE_AMOUNT = "conservative"  # "conservative" (max of recent) | "median"
# Fraction of median applied to recurring *variable* expense categories
# (calibrated on the 25 samples: preserves plan-field matches while halving MAE).
VARIABLE_EXPENSE_FRACTION = 0.25
ONE_TIME_TYPES = {"refund", "investment_purchase", "investment_sale"}
ONE_TIME_CATEGORIES = {"windfall"}  # category names that never recur (classify.is_recurring)
# Same-day ordering frozen from code/evaluation/eda.py on the 25 samples:
# debits-first beat credits-first (MAE 213,330 vs 307,533; closer on 6 rows vs 1)
# and is the financially safer ordering.
SAME_DAY_ORDER = "debits_first"  # frozen; "debits_first" | "credits_first"
# reserve_debits: keep pending debits in the forecast (money already committed).
# count_credits: do NOT count pending credits until they settle (problem_statement.md
# 90-Day Safety Check; AGENTS.md 6.3). Both read by classify.is_cash_eligible.
PENDING_POLICY = {"reserve_debits": True, "count_credits": False}

# Categories treated as monthly fixed when history supports them.
FIXED_CATEGORIES = {
    "rent", "utilities", "healthcare", "debt_repayment",
    "cloud_storage", "streaming", "music_subscription", "delivery_membership",
    "family_support", "salary", "education", "insurance", "housing", "gym",
    "entertainment",
}

# Output contract
OUTPUT_COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]

AFFORDABILITY_STATUSES = {
    "affordable_now", "affordable_with_plan", "affordable_later", "not_affordable",
}
PAYMENT_METHODS = {
    "full_payment", "partial_payment", "installments", "wait", "not_recommended",
}
