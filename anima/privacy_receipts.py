"""Privacy receipts and egress ledger.

These records are deliberately sparse: no prompt text, no raw URLs, no API keys,
and no stored personal facts. They answer one product-trust question per turn:
what was allowed to leave the Mac, what actually left, and what was withheld?
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import egress, secure_store

STORE = Path(".anima")
SCHEMA_VERSION = 1

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")
_URL = re.compile(r"https?://[^\s)]+", re.I)
_PROVIDER_PREFIXES = ("openai:", "anthropic:", "deepseek:", "mistral:", "grok:")
_LOCAL_PREFIXES = ("host:", "reference:", "repair:", "memory:", "lerf:")


def _name(name: str | None) -> str:
    n = _SAFE_NAME.sub("_", str(name or "global").strip())[:80].strip("._-")
    return n or "global"


def _privacy_dir() -> Path:
    return STORE / "privacy"


def receipt_path(name: str | None) -> Path:
    return _privacy_dir() / f"{_name(name)}.privacy_receipts.jsonl"


def egress_path(name: str | None = None) -> Path:
    return _privacy_dir() / f"{_name(name)}.egress.jsonl"


def sanitize_target(target: str | None) -> str:
    """Drop path/query/fragment/secrets; keep only the egress boundary."""
    s = str(target or "").strip()
    if not s:
        return ""
    try:
        u = urlparse(s)
    except Exception:
        u = None
    if u and u.scheme and u.hostname:
        host = (u.hostname or "").lower()
        if u.port:
            host = f"{host}:{u.port}"
        return f"{u.scheme.lower()}://{host}"
    return re.sub(r"[^A-Za-z0-9:_.-]+", "_", s)[:120]


def _clean_metadata(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return sanitize_target(value) if "://" in value else value[:160]
    if isinstance(value, (list, tuple)):
        return [_clean_metadata(v) for v in value[:20]]
    if isinstance(value, dict):
        return {str(k)[:60]: _clean_metadata(v) for k, v in list(value.items())[:20]}
    return str(value)[:120]


def _clean_reason(reason: str | None) -> str:
    s = str(reason or "")
    s = _URL.sub(lambda m: sanitize_target(m.group(0)), s)
    return s[:240]


def model_egress(route_model: str | None, backend: str | None) -> str:
    """Classify actual model egress from route intent + backend label."""
    b = str(backend or "").strip().lower()
    r = str(route_model or "").strip().lower()
    if not b or b.startswith(_LOCAL_PREFIXES):
        return "none"
    if b.startswith(_PROVIDER_PREFIXES):
        return "cloud_provider"
    if r.startswith("cloud:") and not b.startswith(_LOCAL_PREFIXES):
        return "cloud_provider"
    return "none"


def record_egress(
    name: str | None,
    *,
    kind: str,
    target: str = "",
    decision: str,
    turn_id: str = "",
    reason: str = "",
    metadata: dict | None = None,
) -> dict:
    """Append one sanitized egress event."""
    row = {
        "v": SCHEMA_VERSION,
        "kind": "egress_event",
        "at": time.time(),
        "name": str(name or "global")[:80],
        "turn_id": str(turn_id or "")[:120],
        "egress_kind": str(kind or "unknown")[:80],
        "target": sanitize_target(target),
        "decision": str(decision or "unknown")[:40],
        "zero_egress": egress.zero_enabled(),
        "reason": _clean_reason(reason),
        "metadata": _clean_metadata(metadata or {}),
    }
    secure_store.append_jsonl(egress_path(name), row)
    return row


def record_turn(
    name: str,
    *,
    turn_id: str,
    route_model: str,
    backend: str,
    cloud_available: bool,
    cloud_selected: bool,
    facts_selected: int,
    facts_sent_to_model: bool,
    facts_withheld_from_model: bool,
    memory_ids: list | None = None,
    route_reason: str = "",
) -> dict:
    actual = model_egress(route_model, backend)
    row = {
        "v": SCHEMA_VERSION,
        "kind": "privacy_receipt",
        "at": time.time(),
        "name": str(name or "")[:80],
        "turn_id": str(turn_id or "")[:120],
        "route_model": str(route_model or "local")[:120],
        "backend": str(backend or "")[:120],
        "cloud_available": bool(cloud_available),
        "cloud_selected_by_router": bool(cloud_selected),
        "actual_egress": actual,
        "zero_egress": egress.zero_enabled(),
        "facts_selected": max(0, int(facts_selected or 0)),
        "facts_sent_to_model": bool(facts_sent_to_model),
        "facts_withheld_from_model": bool(facts_withheld_from_model),
        "memory_ids": [str(x)[:80] for x in list(memory_ids or [])[:40]],
        "route_reason": _clean_reason(route_reason),
    }
    secure_store.append_jsonl(receipt_path(name), row)
    return row


def latest_receipt(name: str) -> dict | None:
    rows = secure_store.load_jsonl(receipt_path(name), skip_bad=True)
    return rows[-1] if rows else None


def egress_events(name: str | None = None) -> list[dict]:
    return secure_store.load_jsonl(egress_path(name), skip_bad=True)
