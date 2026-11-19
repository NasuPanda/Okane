"""Mistake prompts: "you may have made a mistake" (brief section 1 baselines; section 9).

Decided in #12 (docs/ASSUMPTIONS.md A6):

1. Spelling: words of at least ``typo_min_word_length`` (5) letters are counted over the Text
   and Doc.Header Text of every line in the run (both workbooks, case ignored, name
   placeholders NAME### removed). A word seen at most ``typo_max_rare_count`` times that is
   ``typo_max_edits`` letter(s) away (Levenshtein: one letter added, removed or replaced)
   from a word seen at least ``typo_common_ratio`` times as often is flagged, e.g. "URSAAF"
   for "URSSAF". Plurals and shortened forms (one word starts with the other) are skipped, as
   are the words on ``typo_allow_list`` (abbreviations such as "Alloc"). Two swapped letters
   count as two edits.
2. Period label: inside one document with at least ``period_label_min_lines`` (3) lines that
   name a period, a line whose text names a different period than most of them is flagged.

Every threshold comes from ``Rules`` (built in #13) and is shown on the Rules page.

Wrong period labels on payments are handled by Pulse (label_mismatch).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

import pandas as pd
from rapidfuzz.distance import Levenshtein

from app.engines import doc_ref, doc_refs, make_record, period_label
from app.engines.pulse import parse_period
from app.schemas import ExceptionRecord, Rules

WORD = re.compile(r"[A-Za-zÀ-ÿ]+")
NAME_PLACEHOLDER = re.compile(r"NAME\d+", re.IGNORECASE)
TEXT_FIELDS = ("text", "header_text")


def words(text: object, min_length: int) -> list[str]:
    """Words of at least ``min_length`` letters, name placeholders removed."""
    if not isinstance(text, str):
        return []
    return [w for w in WORD.findall(NAME_PLACEHOLDER.sub(" ", text)) if len(w) >= min_length]


def line_words(lines: pd.DataFrame, min_length: int) -> pd.Series:
    """The words of each line's Text and Doc.Header Text, as written."""
    fields = [f for f in TEXT_FIELDS if f in lines.columns]
    return lines[fields].apply(
        lambda row: [w for f in fields for w in words(row[f], min_length)], axis=1
    )


def typo_candidates(counts: Counter[str], rules: Rules) -> dict[str, str]:
    """Rare word -> the frequent word it is a slip of (both lower-case)."""
    allowed = {w.strip().lower() for w in rules.typo_allow_list}
    edits = rules.typo_max_edits
    by_length: dict[int, list[str]] = defaultdict(list)
    for word in counts:
        by_length[len(word)].append(word)
    found = {}
    for word, count in counts.items():
        if count > rules.typo_max_rare_count or word in allowed:
            continue
        best = None
        for length in range(len(word) - edits, len(word) + edits + 1):
            for other in by_length.get(length, []):
                if counts[other] < rules.typo_common_ratio * count:
                    continue
                # a plural or a shortened form ("deduction"/"deductions"), not a typo
                if other.startswith(word) or word.startswith(other):
                    continue
                if Levenshtein.distance(word, other, score_cutoff=edits) > edits:
                    continue
                if best is None or counts[other] > counts[best]:
                    best = other
        if best is not None:
            found[word] = best
    return found


def spelling_alerts(lines: pd.DataFrame, rules: Rules) -> list[ExceptionRecord]:
    """Rare words one letter away from a word used often in the run."""
    if lines.empty:
        return []
    tokens = line_words(lines, rules.typo_min_word_length)
    lowered = tokens.map(lambda ws: {w.lower() for w in ws})
    counts = Counter(w.lower() for ws in tokens for w in ws)
    display: dict[str, str] = {}
    for original, _ in Counter(w for ws in tokens for w in ws).most_common():
        display.setdefault(original.lower(), original)
    records = []
    for word, common in sorted(typo_candidates(counts, rules).items()):
        hit_mask = lowered.map(lambda ws, w=word: w in ws)
        suggestion = display[common]
        for _, hit in lines[hit_mask].groupby(["erp", "entity", "account"], sort=False):
            shown = next(x for ws in tokens[hit.index] for x in ws if x.lower() == word)
            refs = doc_refs(hit)
            first = min(hit["posting_date"])
            records.append(
                make_record(
                    type_="typo",
                    lines=hit,
                    title=f"You may have made a mistake: '{shown}' looks like '{suggestion}'",
                    exposure_eur=float(hit["amount_eur"].sum()),
                    facts={
                        "rule": "Rare word one letter away from a word used often",
                        "found": shown,
                        "suggestion": suggestion,
                        "edits": Levenshtein.distance(word, common),
                        "occurrences": counts[word],
                        "dictionary_count": counts[common],
                        "min_word_length": rules.typo_min_word_length,
                        "max_rare_count": rules.typo_max_rare_count,
                        "common_ratio": rules.typo_common_ratio,
                        "posting_date": first,
                        "prompt": f"You may have made a mistake: '{shown}' looks like "
                        f"'{suggestion}', which is used {counts[common]} times.",
                    },
                    evidence=refs,
                    first_signal=first,
                    id_keys=[word, *refs],
                )
            )
    return records


def period_label_alerts(lines: pd.DataFrame, rules: Rules) -> list[ExceptionRecord]:
    """A line whose text names a different period than the rest of its document."""
    work = lines.assign(text_period=lines["text"].map(parse_period))
    work = work[work["text_period"].notna()]
    records = []
    for (_, _, _, year, number), doc in work.groupby(
        ["erp", "entity", "account", "year", "document_no"], sort=False
    ):
        if len(doc) < rules.period_label_min_lines:
            continue
        majority, majority_count = Counter(doc["text_period"]).most_common(1)[0]
        if majority_count < len(doc) / 2:
            continue
        odd = doc[doc["text_period"] != majority]
        if odd.empty:
            continue
        found = odd["text_period"].iloc[0]
        ref = doc_ref(year, number)
        first = min(odd["posting_date"])
        records.append(
            make_record(
                type_="typo",
                lines=odd,
                title=f"You may have made a mistake: period {period_label(*found)} in a "
                f"{period_label(*majority)} document",
                exposure_eur=float(odd["amount_eur"].sum()),
                facts={
                    "rule": "Line text names a different period than the rest of its document",
                    "found_period": period_label(*found),
                    "expected_period": period_label(*majority),
                    "lines": len(odd),
                    "min_lines": rules.period_label_min_lines,
                    "posting_date": first,
                    "prompt": f"You may have made a mistake: {len(odd)} line(s) say "
                    f"{period_label(*found)} but the document is for {period_label(*majority)}.",
                },
                evidence=[ref],
                first_signal=first,
                id_keys=[ref, "period"],
            )
        )
    return records


def run_typos(lines: pd.DataFrame, rules: Rules) -> list[ExceptionRecord]:
    return spelling_alerts(lines, rules) + period_label_alerts(lines, rules)
