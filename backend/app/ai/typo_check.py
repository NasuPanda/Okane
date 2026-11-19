"""Model-assisted typo check (#30; docs/ASSUMPTIONS.md A6).

The typo rule (``engines/typos.py``) flags a rare word one letter away from a common one. The
model reads the flagged word, the common word, how often each is written and up to three masked
line texts, and says whether it is a misspelling or a real word (an abbreviation, a foreign
word, a name).

- Advisory only: the verdict is stored as ``ExceptionRecord.ai_check``. It never removes the
  prompt or changes its id, score, status or class; the controller allow-lists real words.
- A suggestion is kept only if it is a word of the run's own dictionary, at most
  ``Rules.typo_max_edits`` letters from the flagged word and at least ``Rules.typo_common_ratio``
  times as common (the rule's own idea of a common word). Otherwise the rule's suggestion
  stands.
- Without a model nothing is added, and the edit-distance result stands as before.
- The model's raw answer is cached by task, model and a hash of the prompt version, system
  prompt, output schema and prompt. The suggestion rule above is applied each time it is read,
  so a Rules change takes effect without asking the model again.
- Line texts are masked (names, and numbers of 6 digits or more such as references) before the
  model sees them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter

import httpx
import pandas as pd
from pydantic import BaseModel
from rapidfuzz.distance import Levenshtein

from app.ai.client import ModelUnavailableError, chat
from app.ai.prompts import mask
from app.config import Settings
from app.database import Database
from app.engines.typos import typo_samples, word_counts
from app.schemas import ExceptionRecord, Rules, TypoCheck

log = logging.getLogger("okane.ai")
TASK = "typo"
TYPO_PROMPT_VERSION = "v3"
LONG_NUMBER = re.compile(r"\d{6,}")  # document numbers and references add nothing to spelling

TYPO_SYSTEM_PROMPT = """You check possible spelling mistakes in the text of accounting lines.
A simple rule flagged a word because it is rare in this data and one letter away from a word
that is written much more often. The rule is often wrong, so judge for yourself.
Not typos: abbreviations, which accountants use a lot (for example "Accr" for accrual, "Prov"
for provision, "Reclas" for reclassification); words in another language (French, German,
Spanish ...); names, codes and references. A typo is a word with a letter accidentally missing,
added, doubled or wrong, where the writer clearly meant the common word.
Read the line texts first and ask: given these texts, did the writer mean the common word?
- is_typo: true only if the writer clearly meant the common word.
- suggestion: the correct spelling when is_typo is true, otherwise null.
Answer with JSON only:
{"is_typo": true or false, "suggestion": "<word>" or null}"""


class TypoVerdict(BaseModel):
    """The only shape accepted from the model for this task.

    Both keys are required: Ollama writes required keys first and may skip an optional one.
    No reason is asked for (#62 review): an optional one was always skipped, and a required
    one, written first, gave worse verdicts on real data with the 7B model (A6).
    """

    is_typo: bool
    suggestion: str | None


def spelling_prompts(records: list[ExceptionRecord]) -> list[ExceptionRecord]:
    """Spelling prompts only; period-label prompts are structural and not checked."""
    return [r for r in records if r.type == "typo" and isinstance(r.facts.get("found"), str)]


def mask_text(text: str) -> str:
    """Names and long numbers (references, document numbers) masked."""
    return LONG_NUMBER.sub("[number]", mask(text))


def typo_prompt(record: ExceptionRecord, samples: list[str]) -> str:
    payload = {
        "line_texts": [mask_text(s) for s in samples],
        "rare_word": mask(str(record.facts["found"])),
        "rare_word_times": record.facts.get("occurrences"),
        "common_word": mask(str(record.facts.get("suggestion", ""))),
        "common_word_times": record.facts.get("dictionary_count"),
    }
    return "WORD:\n" + json.dumps(payload, ensure_ascii=False, indent=1)


def cache_key(prompt: str, settings: Settings) -> str:
    """Everything the model is given, so any change to it asks again."""
    raw = json.dumps(
        {"v": TYPO_PROMPT_VERSION, "system": TYPO_SYSTEM_PROMPT,
         "schema": TypoVerdict.model_json_schema(), "prompt": prompt},
        sort_keys=True,
    )  # fmt: skip
    return f"{TASK}:{settings.ollama_model}:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def accepted_suggestion(
    verdict: TypoVerdict, record: ExceptionRecord, vocabulary: Counter[str], rules: Rules
) -> str | None:
    """The model's suggestion if it is a common word of the run's dictionary, else the rule's."""
    if not verdict.is_typo:
        return None
    found = str(record.facts["found"])
    rule_suggestion = str(record.facts.get("suggestion", "")) or None
    word = (verdict.suggestion or "").strip()
    if not word or word.lower() == found.lower():
        return rule_suggestion
    if rule_suggestion and word.lower() == rule_suggestion.lower():
        return rule_suggestion  # keep the rule's casing
    common = vocabulary[word.lower()] >= rules.typo_common_ratio * max(vocabulary[found.lower()], 1)
    close = Levenshtein.distance(word.lower(), found.lower()) <= rules.typo_max_edits
    return word if common and close else rule_suggestion


def check_typo(
    record: ExceptionRecord,
    samples: list[str],
    vocabulary: Counter[str],
    rules: Rules,
    db: Database,
    settings: Settings,
    http: httpx.Client | None,
) -> TypoCheck | None:
    """Cached verdict, or a fresh one when ``http`` is given. Raises if the model fails.

    The cache holds the model's own answer; the suggestion rule uses today's Rules and words.
    """
    prompt = typo_prompt(record, samples)
    key = cache_key(prompt, settings)
    hit = db.cache_get(key)
    if hit is not None:
        verdict = TypoVerdict.model_validate(hit)
    elif http is None:
        return None
    else:
        messages = [
            {"role": "system", "content": TYPO_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        verdict = chat(messages, TypoVerdict, settings, http)
        db.cache_put(key, verdict.model_dump())
    return TypoCheck(
        verdict="typo" if verdict.is_typo else "not_a_typo",
        suggestion=accepted_suggestion(verdict, record, vocabulary, rules),
    )


def annotate_typos(
    records: list[ExceptionRecord],
    lines: pd.DataFrame,
    rules: Rules,
    db: Database,
    settings: Settings,
    use_model: bool,
    http: httpx.Client | None = None,
) -> list[ExceptionRecord]:
    """Attach the assistant's check to each spelling prompt; every other field is unchanged.

    Cached verdicts are always attached; new ones are asked for only when ``use_model``.
    """
    targets = spelling_prompts(records)
    if not targets:
        return records
    vocabulary = word_counts(lines, rules)
    client = (http or httpx.Client(timeout=settings.ollama_timeout_s)) if use_model else None
    checks: dict[str, TypoCheck] = {}
    try:
        for record in targets:
            samples = typo_samples(lines, record)
            try:
                check = check_typo(record, samples, vocabulary, rules, db, settings, client)
            except ModelUnavailableError as exc:
                log.info("model unavailable for the typo check (%s); cached verdicts only", exc)
                if client is not None and http is None:
                    client.close()
                client = None
                check = check_typo(record, samples, vocabulary, rules, db, settings, None)
            if check is not None:
                checks[record.id] = check
    finally:
        if client is not None and http is None:
            client.close()
    return [
        r.model_copy(update={"ai_check": checks[r.id]}) if r.id in checks else r for r in records
    ]
