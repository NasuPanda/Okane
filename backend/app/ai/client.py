"""Ollama client and comment cache (brief sections 5 and 9, "AI layer"; A10, decided in #28/#45).

- The model writes a comment for one exception from ``prompts.user_prompt`` only: named figures
  it refers to as ``{name}``, masked context text, no title, no document numbers.
- Output must be JSON ``{"comment": "..."}``: passed to Ollama as a JSON schema and validated
  with pydantic.
- Each draft is rendered (slots filled by code), then checked: unknown names,
  ``verifier.verify`` on every figure and ``verifier.wording_issues``. A rejected draft is sent
  back once with the reasons (retry with feedback; at temperature 0 a plain retry repeats it).
- If the second draft is also rejected, the labelled template is returned with the rejected
  draft attached, so the preparer never copies an unconfirmed figure.
- Outcomes are cached in DuckDB by task, model, exception id and a hash of everything the model
  is given (prompt version, system prompt, output schema, prompt).
- If Ollama is unreachable or disabled, the labelled template is returned with
  ``verifier = "not_run"`` (not cached); the app keeps working.
- Errors and logs never carry the model's text: it can quote line texts and amounts (rule 3).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.ai.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    figures,
    render,
    template_comment,
    user_prompt,
)
from app.ai.verifier import VerifierOutput, verify, wording_issues
from app.config import Settings
from app.database import Database
from app.schemas import Comment, ExceptionRecord, Health

log = logging.getLogger("okane.ai")
MAX_ATTEMPTS = 2
TASK = "comment"


class ModelOutput(BaseModel):
    """The prompt contract: the only shape accepted from the model."""

    comment: str = Field(min_length=10, max_length=1200)


class ModelUnavailableError(RuntimeError):
    """Ollama is not reachable or returned something unusable."""


def failure_reason(exc: Exception) -> str:
    """Why a model call failed, without the model's text (pydantic errors quote the input)."""
    if isinstance(exc, httpx.HTTPError):
        return f"{type(exc).__name__}: {exc}"
    return f"{type(exc).__name__} in the model's answer"


@dataclass
class Attempt:
    raw: str  # the model's text, with {slots}
    text: str  # rendered: slots filled with the exact figures
    outcome: VerifierOutput
    reasons: list[str]  # why it was rejected, for the model; empty when it passes
    shown_reasons: list[str]  # the same, in plain words for the person (no slot names)


def prompt_hash(record: ExceptionRecord) -> str:
    """Hash of everything the model is given, so any change to it drafts again."""
    raw = json.dumps(
        {"v": PROMPT_VERSION, "system": SYSTEM_PROMPT, "schema": ModelOutput.model_json_schema(),
         "prompt": user_prompt(record)},
        sort_keys=True,
    )  # fmt: skip
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cache_key(record: ExceptionRecord, settings: Settings) -> str:
    return f"{TASK}:{settings.ollama_model}:{record.id}:{prompt_hash(record)}"


def cached_comment(record: ExceptionRecord, db: Database, settings: Settings) -> Comment | None:
    payload = db.cache_get(cache_key(record, settings))
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


def assistant_status(settings: Settings, http: httpx.Client | None = None) -> Health:
    """Whether the assistant can draft notes: Ollama answers and the model is pulled (A45)."""
    if not settings.ai_enabled:
        return Health(assistant="off", model=settings.ollama_model, reason="turned off in settings")
    client = http or httpx.Client(timeout=2.0)
    try:
        response = client.get(f"{settings.ollama_url}/api/tags")
        names = {m.get("name", "") for m in response.json().get("models", [])}
    except (httpx.HTTPError, ValueError):
        return Health(assistant="offline", model=settings.ollama_model,
                      reason="the local model server does not answer")  # fmt: skip
    finally:
        if http is None:
            client.close()
    wanted = settings.ollama_model
    if wanted not in names and f"{wanted}:latest" not in names:
        return Health(assistant="offline", model=wanted, reason="the model is not installed")
    return Health(assistant="on", model=wanted)


def chat[Output: BaseModel](
    messages: list[dict[str, str]], output: type[Output], settings: Settings, http: httpx.Client
) -> Output:
    """One Ollama chat call at temperature 0, its JSON answer validated against ``output``."""
    body = {
        "model": settings.ollama_model,
        "stream": False,
        "format": output.model_json_schema(),
        "options": {"temperature": 0},
        "messages": messages,
    }
    try:
        response = http.post(f"{settings.ollama_url}/api/chat", json=body)
        response.raise_for_status()
        content = response.json()["message"]["content"]
        return output.model_validate_json(content)
    except (httpx.HTTPError, KeyError, ValueError, ValidationError) as exc:
        raise ModelUnavailableError(failure_reason(exc)) from exc


def call_model(messages: list[dict[str, str]], settings: Settings, http: httpx.Client) -> str:
    """One comment call. Returns the validated comment text."""
    return chat(messages, ModelOutput, settings, http).comment.strip()


def check(raw: str, record: ExceptionRecord, figs: dict[str, dict[str, str]]) -> Attempt:
    """Render the draft and list every reason to reject it, in plain language.

    The model is told the unknown slot names; the person sees plain words instead.
    """
    text, unknown = render(raw, figs)
    outcome = verify(text, record.facts, [record.entity, record.account])
    figures_off = [
        f"'{figure}' doesn't match any of our figures" for figure in dict.fromkeys(outcome.failed)
    ]
    wording = wording_issues(raw)
    reasons = [f"Uses a figure name we don't have: {{{name}}}" for name in unknown]
    shown = ["Refers to a figure Okane doesn't have"] if unknown else []
    return Attempt(
        raw, text, outcome, reasons + figures_off + wording, shown + figures_off + wording
    )


def feedback(attempt: Attempt, figs: dict[str, dict[str, str]]) -> str:
    """The retry message: what was wrong and the names the model may use."""
    lines = "\n".join(f"- {reason}" for reason in attempt.reasons)
    names = ", ".join("{" + name + "}" for name in figs) or "(none)"
    return (
        f"Your note was not accepted:\n{lines}\n"
        "Rewrite it following the rules. Write every figure as its name in braces, using only "
        f"these names: {names}. Answer with JSON only."
    )


def model_comment(record: ExceptionRecord, settings: Settings, http: httpx.Client) -> Comment:
    """Draft and check; on rejection retry once with feedback; else the template + the draft."""
    figs = figures(record)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt(record)},
    ]
    attempt: Attempt | None = None
    for _ in range(MAX_ATTEMPTS):
        if attempt is not None:
            messages += [
                {"role": "assistant", "content": json.dumps({"comment": attempt.raw})},
                {"role": "user", "content": feedback(attempt, figs)},
            ]
        attempt = check(call_model(messages, settings, http), record, figs)
        if not attempt.reasons:
            return Comment(
                exception_id=record.id,
                comment=attempt.text,
                source="model",
                verifier="passed",
                checked_figures=attempt.outcome.checked,
                failed_figures=[],
                cached=False,
            )
        log.warning("comment for %s rejected (%d reasons)", record.id, len(attempt.reasons))
    assert attempt is not None
    return template(record).model_copy(
        update={"rejected_draft": attempt.text, "rejected_reasons": attempt.shown_reasons}
    )


def draft_comment(
    record: ExceptionRecord,
    db: Database,
    settings: Settings,
    refresh: bool = False,
    http: httpx.Client | None = None,
) -> Comment:
    """Cached outcome, a fresh model outcome, or the labelled template (model unavailable)."""
    if not refresh:
        hit = cached_comment(record, db, settings)
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
    db.cache_put(cache_key(record, settings), result.model_dump(exclude={"cached"}))
    return result
