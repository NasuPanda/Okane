"""Ollama client and comment cache (brief sections 5 and 9, "AI layer").

- The model writes a comment for one exception from masked text and the ``facts`` dict only.
- Output must be JSON ``{"comment": "..."}``, validated with pydantic.
- ``verifier.verify`` checks every figure; a failed draft is retried once.
- Model drafts are cached in DuckDB by exception id plus a hash of what the model saw.
- If Ollama is unreachable or disabled, a clearly labelled deterministic template comment is
  returned with ``verifier = "not_run"``; the app keeps working.
"""

from __future__ import annotations

import hashlib
import json
import logging

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.ai.prompts import PROMPT_VERSION, SYSTEM_PROMPT, template_comment, user_prompt
from app.ai.verifier import verify
from app.config import Settings
from app.database import Database
from app.schemas import Comment, ExceptionRecord

log = logging.getLogger("okane.ai")
MAX_ATTEMPTS = 2


class ModelOutput(BaseModel):
    """The prompt contract: the only shape accepted from the model."""

    comment: str = Field(min_length=10, max_length=1200)


class ModelUnavailableError(RuntimeError):
    """Ollama is not reachable or returned something unusable."""


def facts_hash(record: ExceptionRecord) -> str:
    """Hash of everything the model sees, so a changed finding gets a fresh comment."""
    raw = json.dumps(
        {"v": PROMPT_VERSION, "title": record.title, "facts": record.facts}, sort_keys=True
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cache_key(record: ExceptionRecord) -> str:
    return f"{record.id}:{facts_hash(record)}"


def cached_comment(record: ExceptionRecord, db: Database) -> Comment | None:
    payload = db.cache_get(cache_key(record))
    if payload is None:
        return None
    return Comment.model_validate({**payload, "cached": True})


def template(record: ExceptionRecord) -> Comment:
    return Comment(
        exception_id=record.id,
        comment=template_comment(record),
        source="template",
        verifier="not_run",
        checked_figures=[],
        failed_figures=[],
        cached=False,
    )


def ollama_available(settings: Settings, http: httpx.Client | None = None) -> bool:
    """Quick reachability check (``GET /api/tags``)."""
    client = http or httpx.Client(timeout=2.0)
    try:
        return client.get(f"{settings.ollama_url}/api/tags").status_code == 200
    except httpx.HTTPError:
        return False
    finally:
        if http is None:
            client.close()


def call_model(record: ExceptionRecord, settings: Settings, http: httpx.Client) -> str:
    """One chat call. Returns the validated comment text."""
    body = {
        "model": settings.ollama_model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(record)},
        ],
    }
    try:
        response = http.post(f"{settings.ollama_url}/api/chat", json=body)
        response.raise_for_status()
        content = response.json()["message"]["content"]
        return ModelOutput.model_validate_json(content).comment.strip()
    except (httpx.HTTPError, KeyError, ValueError, ValidationError) as exc:
        raise ModelUnavailableError(str(exc)) from exc


def model_comment(record: ExceptionRecord, settings: Settings, http: httpx.Client) -> Comment:
    """Draft, verify, retry once if a figure fails; return the best attempt."""
    extra = [record.entity, record.account]
    best: Comment | None = None
    for _ in range(MAX_ATTEMPTS):
        text = call_model(record, settings, http)
        outcome = verify(text, record.facts, extra)
        best = Comment(
            exception_id=record.id,
            comment=text,
            source="model",
            verifier=outcome.result,
            checked_figures=outcome.checked,
            failed_figures=outcome.failed,
            cached=False,
        )
        if outcome.result == "passed":
            break
        log.warning("comment for %s failed verification; retrying", record.id)
    assert best is not None
    return best


def draft_comment(
    record: ExceptionRecord,
    db: Database,
    settings: Settings,
    refresh: bool = False,
    http: httpx.Client | None = None,
) -> Comment:
    """Cached model comment, a fresh model comment, or the labelled template."""
    if not refresh:
        hit = cached_comment(record, db)
        if hit is not None:
            return hit
    if not settings.ai_enabled:
        return template(record)
    client = http or httpx.Client(timeout=settings.ollama_timeout_s)
    try:
        result = model_comment(record, settings, client)
    except ModelUnavailableError as exc:
        log.info("model unavailable (%s); using the template comment", exc)
        return template(record)
    finally:
        if http is None:
            client.close()
    db.cache_put(cache_key(record), result.model_dump(exclude={"cached"}))
    return result
