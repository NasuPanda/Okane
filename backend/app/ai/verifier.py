"""Verify every figure in an AI comment against the exception's facts (brief sections 1, 5).

Code computes every number; the model may only repeat them. This module extracts every
number and date from a comment and checks each one against ``ExceptionRecord.facts``.

Matching rule for a number shown with ``d`` decimals and a unit (none, K, M, bn, %, x):
it passes when some fact value ``f`` satisfies ``round(|f| / unit, d) == shown``. So
1,838,461.53 may be written "1,838,462", "1.84M" or "1.8M", but "1.85M" or "1,838,460" fail.
Percentages also accept a fraction fact times 100. Dates must equal a date in the facts
(day precision when the comment gives a day, month precision otherwise). Signs are ignored:
the comment says "credit" or "debit" in words.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
MONTH_WORD = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)
DATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"), "ymd"),
    (
        re.compile(
            r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+" + MONTH_WORD + r",?\s+(\d{4})(?!\d)",
            re.IGNORECASE,
        ),
        "dmy",
    ),
    (re.compile(MONTH_WORD + r"\s+(\d{1,2}),?\s+(\d{4})(?!\d)", re.IGNORECASE), "mdy"),
    (re.compile(r"(?<!\d)(\d{4})-(\d{2})(?![\d-])"), "ym"),
    (re.compile(MONTH_WORD + r"[\s']*(\d{4})(?!\d)", re.IGNORECASE), "my"),
]
NUMBER = re.compile(
    r"(?<![\w.,])[-+−]?(?:EUR\s?|€\s?)?"
    r"(?P<int>\d{1,3}(?:[,  ]\d{3})+|\d+)(?:\.(?P<dec>\d+))?"
    r"(?:\s?(?P<unit>%|percent\b|million\b|thousand\b|billion\b|bn\b|[kKmM](?![a-zA-Z])|x(?![a-zA-Z])|×))?"
)
UNIT_SCALE = {"": 1.0, "k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "bn": 1e9,
              "billion": 1e9}  # fmt: skip
EPSILON = 1e-9


@dataclass
class Figure:
    text: str
    value: float
    decimals: int
    unit: str  # "", "k", "m", "bn", "%", "x" (normalised)


@dataclass
class VerifierOutput:
    result: Literal["passed", "failed"]
    checked: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def _normal_unit(raw: str | None) -> str:
    if not raw:
        return ""
    raw = raw.lower()
    if raw in {"%", "percent"}:
        return "%"
    if raw in {"x", "×"}:
        return "x"
    return {"thousand": "k", "million": "m", "billion": "bn"}.get(raw, raw)


def extract_figures(text: str) -> list[Figure]:
    """Every number in ``text`` (dates must be removed first)."""
    figures = []
    for match in NUMBER.finditer(text):
        integer = re.sub(r"[,  ]", "", match.group("int"))
        decimals = match.group("dec") or ""
        value = float(f"{integer}.{decimals}" if decimals else integer)
        figures.append(
            Figure(match.group(0).strip(), value, len(decimals), _normal_unit(match.group("unit")))
        )
    return figures


def _date_token(match: re.Match[str], kind: str) -> tuple[int, int, int | None] | None:
    g = match.groups()
    try:
        if kind == "ymd":
            return int(g[0]), int(g[1]), int(g[2])
        if kind == "dmy":
            return int(g[2]), MONTHS[g[1][:3].lower()], int(g[0])
        if kind == "mdy":
            return int(g[2]), MONTHS[g[0][:3].lower()], int(g[1])
        if kind == "ym":
            return int(g[0]), int(g[1]), None
        return int(g[1]), MONTHS[g[0][:3].lower()], None
    except (KeyError, ValueError):
        return None


def extract_dates(text: str) -> tuple[list[tuple[str, tuple[int, int, int | None]]], str]:
    """Dates and month labels in ``text``, and the text with them blanked out."""
    found = []
    for pattern, kind in DATE_PATTERNS:
        for match in pattern.finditer(text):
            token = _date_token(match, kind)
            if token is None or not 1 <= token[1] <= 12:
                continue
            found.append((match.group(0), token))
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    return found, text


def fact_dates(
    values: Iterable[float | str],
) -> tuple[set[tuple[int, int, int]], set[tuple[int, int]]]:
    """Days and months mentioned in the facts (ISO dates and YYYY-MM labels)."""
    days: set[tuple[int, int, int]] = set()
    months: set[tuple[int, int]] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        for y, m, d in re.findall(r"(\d{4})-(\d{2})-(\d{2})", value):
            try:
                day = date(int(y), int(m), int(d))
            except ValueError:
                continue
            days.add((day.year, day.month, day.day))
            months.add((day.year, day.month))
        for y, m in re.findall(r"(?<!\d)(\d{4})-(\d{2})(?![\d-])", value):
            months.add((int(y), int(m)))
    return days, months


def fact_numbers(values: Iterable[float | str]) -> list[float]:
    """Numeric facts plus numbers written inside text facts (e.g. '3x', '12-month')."""
    numbers: list[float] = []
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            numbers.append(abs(float(value)))
            continue
        _, without_dates = extract_dates(value)
        numbers += [f.value for f in extract_figures(without_dates)]
        for y, m, d in re.findall(r"(\d{4})-(\d{2})(?:-(\d{2}))?", value):
            numbers += [float(y), float(m)] + ([float(d)] if d else [])
    return numbers


def matches(figure: Figure, candidates: list[float]) -> bool:
    """Does the shown figure equal some fact at the precision it is shown?"""
    for fact in candidates:
        if figure.unit == "%":
            options = [fact, fact * 100]
        elif figure.unit == "x":
            options = [fact]
        else:
            options = [fact / UNIT_SCALE.get(figure.unit, 1.0)]
        if any(abs(round(o, figure.decimals) - figure.value) < EPSILON for o in options):
            return True
    return False


def verify(
    comment: str, facts: dict[str, float | str], extra: Iterable[str] = ()
) -> VerifierOutput:
    """Check every figure and date in ``comment`` against ``facts``.

    ``extra`` holds identifiers the model was shown outside the facts (entity, account).
    """
    values = list(facts.values()) + list(extra)
    days, months = fact_dates(values)
    candidates = fact_numbers(values)
    dates, remainder = extract_dates(comment)
    checked: list[str] = []
    failed: list[str] = []
    for text, (y, m, d) in dates:
        ok = (y, m, d) in days if d is not None else (y, m) in months
        (checked if ok else failed).append(text)
    for figure in extract_figures(remainder):
        (checked if matches(figure, candidates) else failed).append(figure.text)
    return VerifierOutput("failed" if failed else "passed", checked, failed)


# ----- wording check (#29, #45) ------------------------------------------------------------
MAX_WORDS = 60
SENTENCE = re.compile(r"[^.!?]+")
CLASS_NAMES = re.compile(r"\b(list component|timing item|required adjustment)", re.IGNORECASE)
RISK_WORDS = re.compile(
    r"\b(risk level|(?:high|medium|low)[- ]risk|risk score|score)\b", re.IGNORECASE
)
DEADLINE_WORDS = re.compile(r"\b(deadline|due date|no later than)\b", re.IGNORECASE)
CAUSE_WORDS = re.compile(
    r"\b(because|caused by|the cause|the reason|(?:is|are|was|were) (?:likely )?due to)\b",
    re.IGNORECASE,
)
HEDGE_WORDS = re.compile(r"\b(possible|possibly|may|might|could|perhaps)\b", re.IGNORECASE)


def wording_issues(text: str) -> list[str]:
    """What the comment says that the prompt contract forbids, in plain language.

    Run on the model's own text (slots count as one word each). Figures are checked by
    ``verify``; this covers length, causes stated as fact, classes, risk levels and deadlines.
    """
    issues = []
    words = len(text.split())
    if words > MAX_WORDS:
        issues.append(f"Longer than {MAX_WORDS} words ({words})")
    if any(CAUSE_WORDS.search(s) and not HEDGE_WORDS.search(s) for s in SENTENCE.findall(text)):
        issues.append("States a cause as fact instead of 'a possible cause'")
    if CLASS_NAMES.search(text):
        issues.append("Names a classification; the accountant decides the class")
    if RISK_WORDS.search(text):
        issues.append("Gives a risk level or score")
    if DEADLINE_WORDS.search(text):
        issues.append("Sets a deadline or due date")
    return issues
