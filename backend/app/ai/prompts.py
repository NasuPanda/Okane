"""Prompt contract, figure slots and the deterministic fallback comment (A10, A29).

Decided in #28 / #45: the model never types a figure. It receives each figure already formatted
by code, under a name (``gap_eur``), and writes the name in braces (``{gap_eur}``); ``render``
fills in the exact value afterwards. The verifier still checks the rendered text, so a number
the model typed itself is caught.

The model sees a code-written sentence about the finding type (never the title, which carries
rounded amounts), the named figures with their meaning, masked context text and the check to
suggest. It never sees document numbers, user ids or raw lines.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from app.schemas import ExceptionRecord, ExceptionType

# v4 (A43): a gap is worded by its direction and the account's normal side; the check to
# suggest and the meaning sentence can come from the record's facts.
PROMPT_VERSION = "v4"
NAME_PLACEHOLDER = re.compile(r"\bNAME\d+\b", re.IGNORECASE)
# A slot (single or double braces), plus a currency code the model may have written before it
# ("EUR {gap_eur}") and a unit it may have repeated after it ("{multiple}x", "{gap_eur} euros").
SLOT = re.compile(
    r"(?P<lead>\b[A-Z]{3}\s?|€\s?)?\{\{?\s*(?P<name>[A-Za-z0-9_]+)\s*\}\}?"
    r"(?P<tail>\s?(?:in\s)?(?:[A-Za-z]+|%|×|€))?"
)
# Words that mean a unit a figure already carries.
UNIT_WORDS = {"×": "x", "times": "x", "percent": "%", "€": "eur", "euro": "eur", "euros": "eur"}
CURRENCY_UNIT = re.compile(r" ([A-Z]{3})$")
ISO_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
ISO_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TEMPLATE_LABEL = "Standard note (no AI was used):"

# Facts the model is never shown: lead-time bookkeeping (the badge text carries the meaning),
# and the Miner score, as the comment may not give a score (A10; entities and months are shown).
HIDDEN_FACTS = frozenset(
    {"today_detection_basis", "lead_days", "lead_days_daily", "lead_days_weekly",
     "okane_run_date", "lead_view", "miner_score"}
)  # fmt: skip

# What each figure means, in accountant language, so the model names it correctly (#45 cause 4).
FIGURE_LABELS: dict[str, str] = {
    "gap_eur": "the gap: month-end balance minus the expected balance",
    "balance_eur": "the month-end balance of the account (positive is a debit, negative a credit)",
    "balance_abs_eur": "the size of the month-end balance, on the side named in balance_side",
    "expected_eur": "the balance expected from the account's payment rhythm",
    "latest_month": "the latest month-end",
    "since_month": "the month-end since which the gap has been at or above materiality",
    "months_above_materiality": "number of month-ends with the gap at or above materiality",
    "lowest_gap_eur": "the smallest gap in that time",
    "lowest_gap_month": "the month-end of the smallest gap",
    "materiality_eur": "the materiality limit set by the controller",
    "unmatched_batches": "number of accrual batches without a matching payment",
    "batch_eur": "the accrual batch amount",
    "batch_period": "the month of the accrual batch",
    "batch_lines": "number of lines in the accrual batch",
    "accrual_date": "the date the accrual was booked",
    "expected_by": "the date the payment was expected by",
    "lag_p90_days": "the usual payment delay in days",
    "grace_days": "extra grace days allowed",
    "days_past_expected": "days since the payment was expected",
    "lookback_months": "number of months checked",
    "median_eur": "a normal month's batch (median)",
    "multiple": "how many times the normal amount",
    "posting_date": "the posting date",
    "missing_period": "the month with no accrual batch",
    "typical_batch_eur": "a typical accrual batch",
    "payment_eur": "the payment amount",
    "diff_pct": "difference between payment and batch, in percent",
    "label_period": "the month named in the payment text",
    "settles_period": "the month of the batch the payment actually settles",
    "amount_lc": "the amount in local currency (the value includes the currency code)",
    "median_abs_lc": "the usual amount on this account (the value includes the currency code)",
    "outlier_multiple": "the multiple of the usual amount at which lines are flagged",
    "amount_dc": "the amount in document currency (the value includes the currency code)",
    "min_amount": "the smallest amount checked",
    "lines": "number of lines",
    "euro_since": "the date from which the euro replaced this currency",
    "edits": "number of letters different",
    "occurrences": "times the word is written this way",
    "dictionary_count": "times the usual spelling is written",
    "found_period": "the month named on the line",
    "expected_period": "the month of the rest of the document",
    "months": "number of months the posting was seen",
    "entities": "number of company codes",
    "miner_score": "repeat strength: company codes times months",
    "first_month": "the first month seen",
    "last_month": "the last month seen",
    "documents": "number of documents",
    "people": "number of people involved",
    "total_abs_eur": "total amount posted by hand",
}

# Text facts used to build the prompt itself, not passed again as context.
PROMPT_FACTS = frozenset({"check", "gap_explained"})

# One sentence per type, written by code, in place of the title (#45 cause 2).
MEANING: dict[ExceptionType, str] = {
    "pulse_gap": "The account's month-end balance differs from what its own payment rhythm "
    "would leave.",
    "pulse_missing_payment": "An accrual batch has no matching payment and its expected-by date "
    "has passed.",
    "pulse_spike": "An accrual batch is much larger than a normal month.",
    "pulse_missing_batch": "A month has no accrual batch although the account accrues monthly.",
    "label_mismatch": "A payment's text names a different month than the accrual it pays.",
    "sentinel_outlier": "A line is far larger than the usual amount on this account.",
    "sentinel_two_currencies": "The same amount was posted in two currencies on one day.",
    "sentinel_currency_code": "The document currency is not a valid currency code, or the euro "
    "had replaced it.",
    "sentinel_reversal": "A reversal does not match the posting it reverses.",
    "typo": "A line's text may contain a mistake: a misspelt word or a wrong month.",
    "miner_cluster": "The same posting is typed by hand month after month.",
}

# The check to suggest, with no dates (#45 cause 3). Templates reuse it.
NEXT_CHECK: dict[ExceptionType, str] = {
    "pulse_gap": "the unmatched accrual batches listed as evidence",
    "pulse_missing_payment": "whether the batch was paid under another reference or is still owed",
    "pulse_spike": "that the batch is a genuine one-off",
    "pulse_missing_batch": "whether the accrual was booked elsewhere",
    "label_mismatch": "the payment text, and correct it if the label is wrong",
    "sentinel_outlier": "the source document and whether the amount was keyed correctly",
    "sentinel_two_currencies": "whether one of the two postings is a duplicate in the wrong "
    "currency",
    "sentinel_currency_code": "the currency on the source document",
    "sentinel_reversal": "the original posting and the reversal amount",
    "typo": "the line text, and correct it if it is wrong",
    "miner_cluster": "whether the automated posting or mapping can do this instead",
}

SYSTEM_PROMPT = """You draft short notes for accountants who reconcile balance sheet accounts.
You receive one finding as JSON: what it means, its figures, some context and the check to
suggest.
Rules you must follow:
- Never type a number or a date yourself. Write the figure's name in curly braces, for example
  {gap_eur}; the system fills in the exact value. Use only names listed under "figures".
- Call each figure what its "means" says. A gap is a gap, not the balance or the liability.
- At most 60 words: two or three plain sentences saying what was found, then the check.
- If you mention a cause, write "a possible cause is ..."; never state a cause as fact.
- No deadlines, due dates or time limits.
- Do not give a risk level, a score or a classification; the accountant decides.
- Plain accountant language: open item, accrual, payment, exposure, expected by.
- Say which way a gap goes in the finding's own words (for example "more paid than
  accrued"); never call a balance "owed" when the finding says it is a debit balance.
Example: {"comment": "The month-end balance for {latest_month} is {balance_eur}, {gap_eur} away
from the expected {expected_eur}. Check the evidence documents behind the gap."}
Answer with JSON only: {"comment": "<your note>"}"""

# Templates use the same slots as the model and the same renderer.
TEMPLATES: dict[ExceptionType, str] = {
    "pulse_gap": "The month-end balance for {latest_month} is {balance_eur} against an expected "
    "{expected_eur}, a gap of {gap_eur}. {explained} The gap has been at or above materiality "
    "since {since_month}; the lowest was {lowest_gap_eur} in {lowest_gap_month}.",
    "pulse_missing_payment": "The {batch_period} batch of {batch_eur} has no matching payment. "
    "It was expected by {expected_by}.",
    "pulse_spike": "The {batch_period} batch of {batch_eur} is {multiple} the usual size "
    "(median {median_eur}).",
    "pulse_missing_batch": "No batch was posted for {missing_period}; a typical batch is "
    "{typical_batch_eur}.",
    "label_mismatch": "The payment of {payment_eur} is labelled {label_period} but settles the "
    "{settles_period} batch.",
}


def next_check(record: ExceptionRecord) -> str:
    """The check to suggest: the record's own (a gap's depends on its direction, A43), else the
    type's."""
    own = record.facts.get("check")
    if isinstance(own, str) and own:
        return own
    return NEXT_CHECK.get(record.type, "the evidence documents")


def meaning(record: ExceptionRecord) -> str:
    """The code-written sentence the model gets instead of the title (with a gap's direction)."""
    base = MEANING.get(record.type, "A finding on this account.")
    explained = record.facts.get("gap_explained")
    return f"{base} {explained}" if isinstance(explained, str) and explained else base


def mask(text: str) -> str:
    """Replace name placeholders such as NAME122 before any model call."""
    return NAME_PLACEHOLDER.sub("[name]", text)


# ----- figures -------------------------------------------------------------------------------
def _plain_number(value: float) -> str:
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _date_text(value: str) -> str | None:
    """'2026-11-21' -> '21 Nov 2026'; '2025-05' -> 'May 2025'; anything else -> None."""
    day = ISO_DAY.match(value)
    if day:
        try:
            parsed = date(int(day[1]), int(day[2]), int(day[3]))
        except ValueError:
            return None
        return f"{parsed.day} {MONTH_NAMES[parsed.month - 1]} {parsed.year}"
    month = ISO_MONTH.match(value)
    if month and 1 <= int(month[2]) <= 12:
        return f"{MONTH_NAMES[int(month[2]) - 1]} {month[1]}"
    return None


def is_figure(value: float | str) -> bool:
    """Numbers, dates and months are figures; other text is context."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return True
    return _date_text(value) is not None


def display(key: str, value: float | str, facts: dict[str, float | str]) -> str:
    """A fact as the comment shows it. One formatter for the model's slots and the templates."""
    if isinstance(value, str):
        return _date_text(value) or mask(value)
    number = float(value)
    if key.endswith("_eur"):
        return f"{number:,.0f} EUR"
    for suffix, currency_key in (("_lc", "currency_lc"), ("_dc", "currency_dc")):
        if key.endswith(suffix):
            currency = facts.get(currency_key)
            unit = f" {currency}" if isinstance(currency, str) and currency else ""
            return f"{number:,.0f}{unit}"
    if key.endswith("_pct"):
        return f"{number:g}%"
    if key in {"multiple", "outlier_multiple"}:
        return f"{number:g}x"
    return _plain_number(number)


def figures(record: ExceptionRecord) -> dict[str, dict[str, str]]:
    """Every number and date fact as ``{name: {"value": shown text, "means": label}}``.

    The company code is a figure too, so the model can name it as ``{entity}``.
    """
    out = {"entity": {"value": record.entity, "means": "the company code"}}
    for key, value in record.facts.items():
        if key in HIDDEN_FACTS or not is_figure(value):
            continue
        out[key] = {
            "value": display(key, value, record.facts),
            "means": FIGURE_LABELS.get(key, key.replace("_", " ")),
        }
    return out


def context(record: ExceptionRecord) -> dict[str, str]:
    """Text facts (rule, prompt, currency, header pattern, lead-time badge), masked."""
    return {
        key: mask(value)
        for key, value in record.facts.items()
        if isinstance(value, str)
        and key not in HIDDEN_FACTS
        and key not in PROMPT_FACTS
        and not is_figure(value)
    }


def _unit(value: str) -> str | None:
    """The unit a displayed figure already carries: '%', 'x' or a currency code."""
    if value.endswith("%"):
        return "%"
    if re.search(r"\dx$", value):
        return "x"
    currency = CURRENCY_UNIT.search(value)
    return currency.group(1) if currency else None


def _repeats_unit(word: str | None, unit: str | None) -> bool:
    """Is the text next to a slot just its unit again ("x", " EUR", " in DEM", " euros")?"""
    if not word or not unit:
        return False
    word = word.strip().removeprefix("in ").strip().lower()
    return UNIT_WORDS.get(word, word) == unit.lower()


def render(text: str, figs: dict[str, dict[str, str]]) -> tuple[str, list[str]]:
    """Fill ``{name}`` slots with their values. Returns the text and any unknown names.

    A unit the model repeats before or after a slot is dropped, as the value already carries it
    ("{multiple}x" gives "4.1x", not "4.1xx"; "EUR {gap_eur}" gives "1,838,462 EUR"). Double
    braces are read as one slot.
    """
    unknown: list[str] = []

    def fill(match: re.Match[str]) -> str:
        name, lead, tail = match.group("name"), match.group("lead"), match.group("tail")
        if name not in figs:
            unknown.append(name)
            return match.group(0)
        value = figs[name]["value"]
        unit = _unit(value)
        before = "" if _repeats_unit(lead, unit) else (lead or "")
        after = "" if _repeats_unit(tail, unit) else (tail or "")
        return before + value + after

    return SLOT.sub(fill, text), unknown


def user_prompt(record: ExceptionRecord) -> str:
    """The user message: the finding's meaning, named figures, masked context, the check."""
    payload: dict[str, Any] = {
        "finding": meaning(record),
        "type": record.type,
        "workgroup": record.workgroup,
        "figures": figures(record),
        "context": context(record),
        "next_check": next_check(record),
    }
    return "FINDING:\n" + json.dumps(payload, ensure_ascii=False, indent=1)


# ----- deterministic template ----------------------------------------------------------------
def template_comment(record: ExceptionRecord) -> str:
    """A clearly labelled comment built only from the facts (used when no model draft is kept)."""
    figs = figures(record)
    template = TEMPLATES.get(record.type)
    if template is not None:
        explained = record.facts.get("gap_explained")
        sentence = explained if isinstance(explained, str) else ""
        held, normal = record.facts.get("balance_side"), record.facts.get("normal_side")
        if record.facts.get("wrong_side_balance") == "yes":
            # The figure goes in a slot, so the note states it exactly.
            sentence = sentence.split(" The account has a ")[0] + (
                f" The account has a {held} balance of {{balance_abs_eur}}, the wrong side for "
                f"a {normal} account."
            )
        template = template.replace("{explained}", sentence).replace("  ", " ")
        body, unknown = render(template, figs)
        for name in unknown:
            body = body.replace("{" + name + "}", "n/a")
    elif "prompt" in record.facts:
        body = str(record.facts["prompt"])
    else:
        body = f"{record.title}. Rule: {record.facts.get('rule', 'n/a')}."
    return f"{TEMPLATE_LABEL} {mask(body)} Check {next_check(record)}."
