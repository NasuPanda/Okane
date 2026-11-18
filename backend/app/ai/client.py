"""AI comment drafting with cache.

Phase 4 version: deterministic template only (``verifier = "not_run"``). The Ollama client and
the verifier are added in Phase 5.
"""

from __future__ import annotations

import hashlib
import json

from app.ai.prompts import PROMPT_VERSION, template_comment
from app.config import Settings
from app.database import Database
from app.schemas import Comment, ExceptionRecord


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


def draft_comment(
    record: ExceptionRecord, db: Database, settings: Settings, refresh: bool = False
) -> Comment:
    """Cached model comment if any, else the labelled template."""
    if not refresh:
        hit = cached_comment(record, db)
        if hit is not None:
            return hit
    return template(record)
