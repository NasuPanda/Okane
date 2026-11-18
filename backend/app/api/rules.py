"""Rules and the append-only change log (brief section 7).

Every PUT records one log entry per changed field (who, when, old value, new value, reason)
and starts a re-run on the current snapshot so the inbox reflects the new rules.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from fastapi import APIRouter, Depends

from app.api import AppState, get_state
from app.database import utcnow
from app.schemas import RuleChange, Rules, RulesUpdate
from app.services.pipeline import RunInProgressError

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _flat(value: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested rules so each weight or profile field is its own log line."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out.update(_flat(item, f"{prefix}.{key}" if prefix else str(key)))
        return out
    if isinstance(value, list) and value and isinstance(value[0], dict):
        out = {}
        for index, item in enumerate(value):
            out.update(_flat(item, f"{prefix}[{index}]"))
        return out
    return {prefix: value}


def diff_rules(old: Rules, new: Rules) -> list[tuple[str, Any, Any]]:
    before, after = _flat(old.model_dump()), _flat(new.model_dump())
    keys = sorted(set(before) | set(after))
    return [(k, before.get(k), after.get(k)) for k in keys if before.get(k) != after.get(k)]


@router.get("")
def get_rules(state: AppState = Depends(get_state)) -> Rules:
    """The rules every engine uses."""
    return state.db.get_rules()


@router.put("")
def put_rules(update: RulesUpdate, state: AppState = Depends(get_state)) -> Rules:
    """Replace the rules; log each changed field; re-run on the current snapshot."""
    old = state.db.get_rules()
    changes = diff_rules(old, update.rules)
    if not changes:
        return old
    who = update.changed_by or state.settings.default_user
    now = utcnow()
    log = [
        RuleChange(
            seq=state.db.next_rule_seq(),
            changed_at=now,
            changed_by=who,
            field=name,
            old_value=json.dumps(before),
            new_value=json.dumps(after),
            reason=update.reason,
        )
        for name, before, after in changes
    ]
    state.db.save_rules(update.rules, log)
    if state.db.latest_run() is not None:
        # if a run is already going, the next run picks up the new rules
        with contextlib.suppress(RunInProgressError):
            state.pipeline.run_in_background("rules_change", reuse_snapshot=True)
    return update.rules


@router.get("/log")
def rules_log(state: AppState = Depends(get_state)) -> list[RuleChange]:
    """Who changed which rule, when, from what to what, and why (newest first)."""
    return state.db.rule_log()
