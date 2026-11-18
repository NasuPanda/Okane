"""Mistake prompts: "you may have made a mistake" (brief section 1 baselines; section 9).

ASSUMPTION (the brief gives no spec beyond "spelling or period-label errors" and rapidfuzz):

1. Spelling: within one account, words used at least ``typo_dictionary_min_count`` times form
   the account's own dictionary. A word that is at least ``typo_min_similarity`` similar to a
   dictionary word used ``typo_rarity_ratio`` times as often is flagged, e.g. "Auzahl" (4) for
   "Auszahl" (11), "URSAAF" (2) for "URSSAF" (80). Prefix pairs (plurals, longer forms) are
   not flagged. Words shorter than five letters and name placeholders
   (NAME###) are ignored.
2. Period label: inside one document, a line whose text names a different period than the
   rest of the document's lines is flagged.

Wrong period labels on payments are handled by Pulse (label_mismatch).
"""

from __future__ import annotations

import re
from collections import Counter

import pandas as pd
from rapidfuzz import fuzz, process

from app.engines import doc_ref, doc_refs, make_record, period_label
from app.engines.pulse import parse_period
from app.schemas import ExceptionRecord, Rules

WORD = re.compile(r"[A-Za-zÀ-ÿ]{5,}")
NAME_PLACEHOLDER = re.compile(r"NAME\d+", re.IGNORECASE)


def words(text: object) -> list[str]:
    """Words of five letters or more, name placeholders removed."""
    if not isinstance(text, str):
        return []
    return WORD.findall(NAME_PLACEHOLDER.sub(" ", text))


def spelling_alerts(lines: pd.DataFrame, rules: Rules) -> list[ExceptionRecord]:
    """Rare words that look like a frequent word of the same account."""
    records = []
    for (_, _, _), acct in lines.groupby(["erp", "entity", "account"], sort=False):
        tokens = acct["text"].map(words)
        counts = Counter(w.lower() for ws in tokens for w in ws)
        spelling = Counter(w for ws in tokens for w in ws)
        display = {}
        for original, _ in spelling.most_common():
            display.setdefault(original.lower(), original)
        dictionary = [w for w, c in counts.items() if c >= rules.typo_dictionary_min_count]
        if not dictionary:
            continue
        for word, count in counts.items():
            # a prefix pair is a plural or a longer form ("deduction"/"deductions"), not a typo
            common = [
                w for w in dictionary
                if counts[w] >= rules.typo_rarity_ratio * count
                and not (w.startswith(word) or word.startswith(w))
            ]  # fmt: skip
            best = process.extractOne(word, common, scorer=fuzz.ratio) if common else None
            if best is None or best[1] < rules.typo_min_similarity:
                continue
            suggestion, similarity = display.get(best[0], best[0]), best[1]
            hit_mask = tokens.map(lambda ws, w=word: w in (x.lower() for x in ws))
            hit = acct[hit_mask]
            shown = next(x for ws in tokens[hit_mask] for x in ws if x.lower() == word)
            refs = doc_refs(hit)
            first = min(hit["posting_date"])
            records.append(
                make_record(
                    type_="typo",
                    lines=hit,
                    title=f"You may have made a mistake: '{shown}' looks like '{suggestion}'",
                    exposure_eur=float(hit["amount_eur"].sum()),
                    facts={
                        "rule": "Rare word close to a word this account uses often",
                        "found": shown,
                        "suggestion": suggestion,
                        "similarity_pct": round(similarity, 1),
                        "occurrences": count,
                        "dictionary_count": counts[best[0]],
                        "posting_date": first,
                        "prompt": f"You may have made a mistake: '{shown}' looks like "
                        f"'{suggestion}', which this account uses {counts[best[0]]} times.",
                    },
                    evidence=refs,
                    first_signal=first,
                    id_keys=[word, *refs],
                )
            )
    return records


def period_label_alerts(lines: pd.DataFrame) -> list[ExceptionRecord]:
    """A line whose text names a different period than the rest of its document."""
    work = lines.assign(text_period=lines["text"].map(parse_period))
    work = work[work["text_period"].notna()]
    records = []
    for (_, _, _, year, number), doc in work.groupby(
        ["erp", "entity", "account", "year", "document_no"], sort=False
    ):
        if len(doc) < 3:
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
    return spelling_alerts(lines, rules) + period_label_alerts(lines)
