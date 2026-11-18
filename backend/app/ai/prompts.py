"""Prompt templates and the deterministic fallback comment.

The model sees only the exception title, its type, the rule and the ``facts`` dict, with name
placeholders masked. It never sees document numbers, user ids or raw lines.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.schemas import ExceptionRecord

PROMPT_VERSION = "v1"
NAME_PLACEHOLDER = re.compile(r"\bNAME\d+\b", re.IGNORECASE)
TEMPLATE_LABEL = "Template comment (no AI model was used):"

SYSTEM_PROMPT = """You draft short reconciliation comments for accountants at a finance team.
Write two or three plain sentences explaining the finding and what to check next.
Rules you must follow:
- Use ONLY numbers that appear in FACTS. Copy them as given, or round them consistently
  (for example 1838461.53 may be written as 1,838,462 or 1.84M). Never compute new numbers.
- Do not invent dates, amounts, percentages, document numbers or names.
- Do not assign a risk level, score or classification; the accountant decides.
- Plain accountant language: open item, accrual, payment, exposure, expected by.
Answer with JSON only: {"comment": "<your comment>"}"""


def mask(text: str) -> str:
    """Replace name placeholders such as NAME122 before any model call."""
    return NAME_PLACEHOLDER.sub("[name]", text)


def masked_facts(record: ExceptionRecord) -> dict[str, float | str]:
    return {k: mask(v) if isinstance(v, str) else v for k, v in record.facts.items()}


def user_prompt(record: ExceptionRecord) -> str:
    """The user message: masked title, type and facts as JSON."""
    payload: dict[str, Any] = {
        "finding": mask(record.title),
        "type": record.type,
        "workgroup": record.workgroup,
        "entity": record.entity,
        "facts": masked_facts(record),
    }
    return "FACTS:\n" + json.dumps(payload, ensure_ascii=False, indent=1)


# ----- deterministic template ----------------------------------------------------------------
def eur(value: object) -> str:
    """A figure as the template writes it: thousands separators, no decimals, EUR."""
    return f"{float(value):,.0f} EUR"  # type: ignore[arg-type]


def _f(record: ExceptionRecord, key: str) -> Any:
    return record.facts.get(key, "n/a")


def template_comment(record: ExceptionRecord) -> str:
    """A clearly labelled comment built only from the facts (used when no model runs)."""
    f = lambda key: _f(record, key)  # noqa: E731
    by_type = {
        "pulse_gap": lambda: (
            f"The month-end balance for {f('latest_month')} is {eur(f('balance_eur'))} against "
            f"an expected {eur(f('expected_eur'))}, a gap of {eur(f('gap_eur'))}. The gap has "
            f"been at or above materiality since {f('since_month')}; the lowest was "
            f"{eur(f('lowest_gap_eur'))} in {f('lowest_gap_month')}. Check the unmatched "
            "batches listed as evidence."
        ),
        "pulse_missing_payment": lambda: (
            f"The {f('batch_period')} batch of {eur(f('batch_eur'))} has no matching payment. "
            f"It was expected by {f('expected_by')}. Confirm whether it was paid under another "
            "reference or is still owed."
        ),
        "pulse_spike": lambda: (
            f"The {f('batch_period')} batch of {eur(f('batch_eur'))} is {f('multiple')}x the "
            f"usual size (median {eur(f('median_eur'))}). Confirm it is a genuine one-off."
        ),
        "pulse_missing_batch": lambda: (
            f"No batch was posted for {f('missing_period')}; a typical batch is "
            f"{eur(f('typical_batch_eur'))}. Confirm whether the accrual was booked elsewhere."
        ),
        "label_mismatch": lambda: (
            f"The payment of {eur(f('payment_eur'))} is labelled {f('label_period')} but settles "
            f"the {f('settles_period')} batch. Correct the payment text if the label is wrong."
        ),
    }
    builder = by_type.get(record.type)
    if builder is not None:
        body = builder()
    elif "prompt" in record.facts:
        body = str(record.facts["prompt"])
    else:
        body = f"{record.title}. Rule: {f('rule')}. Review the evidence documents."
    return f"{TEMPLATE_LABEL} {mask(body)}"
