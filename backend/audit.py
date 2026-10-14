"""Append-only audit trail: output/audit_trail.json (a JSON array of events).

Earlier activity is never deleted: each write reads the existing array, appends,
and atomically replaces the file. A corrupt/non-list file is preserved under a
backup name rather than overwritten.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIT_PATH = Path(__file__).resolve().parent.parent / "output" / "audit_trail.json"
MAX_FIELD_CHARS = 2000  # keep the trail readable; full data stays in the database

_lock = threading.Lock()


def _clip(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) <= MAX_FIELD_CHARS:
        return value
    return text[:MAX_FIELD_CHARS] + f"... [truncated {len(text) - MAX_FIELD_CHARS} chars]"


def _load() -> list:
    if not AUDIT_PATH.exists():
        return []
    try:
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8") or "[]")
    except json.JSONDecodeError:
        data = None
    if isinstance(data, list):
        return data
    backup = AUDIT_PATH.with_suffix(f".corrupt-{datetime.now():%Y%m%d%H%M%S}.json")
    AUDIT_PATH.replace(backup)
    return []


def log(event: str, *, run_id: str | None = None, ticket_id: int | None = None,
        agent: str | None = None, **fields: Any) -> dict:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": run_id,
        "ticket_id": ticket_id,
        "agent": agent,
        "event": event,
        **{k: _clip(v) for k, v in fields.items()},
    }
    with _lock:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        events = _load()
        events.append(entry)
        tmp = AUDIT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(events, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, AUDIT_PATH)
    return entry


def read_all() -> list:
    with _lock:
        return _load()
