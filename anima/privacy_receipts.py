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
CONNECTOR_POLICY_VERSION = 1

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")
_URL = re.compile(r"https?://[^\s)]+", re.I)
_SAFE_ID = re.compile(r"[^A-Za-z0-9_.:-]+")
_PROVIDER_PREFIXES = ("openai:", "anthropic:", "deepseek:", "mistral:", "grok:")
_LOCAL_PREFIXES = ("host:", "reference:", "repair:", "memory:", "lerf:")
_LOCATION_PRECISIONS = {"off", "coarse", "exact"}
_CONNECTOR_DENIED_METADATA = {
    "api_key", "authorization", "body", "content", "message", "password",
    "payload", "prompt", "raw_body", "secret", "text", "token",
}


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


def _safe_id(value: str | None, fallback: str = "unknown") -> str:
    s = _SAFE_ID.sub("_", str(value or "").strip().lower())[:80].strip("._:-")
    return s or fallback


def _event_sort_key(row: dict) -> float:
    try:
        return float(row.get("at") or 0.0)
    except Exception:
        return 0.0


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


def connector_policy() -> dict:
    """The receipt contract future host/cloud connectors must satisfy."""
    return {
        "v": CONNECTOR_POLICY_VERSION,
        "default": "deny_until_enabled",
        "receipt_required": True,
        "raw_payloads_allowed": False,
        "secrets_allowed": False,
        "target_shape": "scheme_and_host_only",
        "required_fields": ["connector", "action", "decision", "purpose"],
        "decisions": ["blocked", "attempt", "completed", "failed"],
        "denied_metadata_keys": sorted(_CONNECTOR_DENIED_METADATA),
    }


def record_connector_egress(
    name: str | None,
    *,
    connector: str,
    action: str,
    decision: str,
    purpose: str,
    target: str = "",
    turn_id: str = "",
    metadata: dict | None = None,
) -> dict:
    """Record a future connector's egress without allowing raw payload capture."""
    conn = _safe_id(connector, "")
    act = _safe_id(action, "")
    dec = _safe_id(decision, "")
    if not conn or not act or dec not in set(connector_policy()["decisions"]):
        raise ValueError("connector, action, and a valid decision are required")
    why = _clean_reason(purpose)
    if not why:
        raise ValueError("connector egress requires a human-readable purpose")
    safe_meta = {}
    for k, v in (metadata or {}).items():
        key = str(k).strip().lower()[:60]
        if not key or key in _CONNECTOR_DENIED_METADATA:
            continue
        safe_meta[key] = v
    safe_meta.update({
        "connector": conn,
        "action": act,
        "purpose": why,
        "policy_version": CONNECTOR_POLICY_VERSION,
    })
    return record_egress(
        name,
        kind=f"connector:{conn}",
        target=target,
        decision=dec,
        turn_id=turn_id,
        reason=why,
        metadata=safe_meta,
    )


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


def location_precision(name: str | None = None, requested: str | None = None) -> str:
    """Return the weather/location egress precision, defaulting to coarse."""
    req = str(requested or "").strip().lower()
    if req in _LOCATION_PRECISIONS:
        return req
    if name:
        try:
            from . import caps
            val = str(caps.load(name).get("location_precision", "")).strip().lower()
            if val in _LOCATION_PRECISIONS:
                return val
        except Exception:
            pass
    return "coarse"


def prepare_location_for_egress(
    lat: float,
    lon: float,
    *,
    name: str | None = None,
    precision: str | None = None,
) -> dict:
    """Apply the user-visible location precision before a weather lookup."""
    mode = location_precision(name, precision)
    if mode == "off":
        return {"ok": False, "precision": "off", "lat": None, "lon": None,
                "label": "location off"}
    if mode == "coarse":
        clat = round(float(lat), 1)
        clon = round(float(lon), 1)
        return {"ok": True, "precision": "coarse", "lat": clat, "lon": clon,
                "label": f"{clat:.1f},{clon:.1f}"}
    elat = round(float(lat), 4)
    elon = round(float(lon), 4)
    return {"ok": True, "precision": "exact", "lat": elat, "lon": elon,
            "label": "exact coordinates"}


def receipt_history(name: str | None, *, limit: int = 80, kind: str = "all") -> dict:
    """Return a normal-user-safe privacy history view."""
    try:
        limit = max(1, min(int(limit or 80), 250))
    except Exception:
        limit = 80
    receipts = secure_store.load_jsonl(receipt_path(name), skip_bad=True)
    egress_rows = secure_store.load_jsonl(egress_path(name), skip_bad=True)
    if kind == "turns":
        egress_rows = []
    elif kind == "egress":
        receipts = []
    elif kind == "blocked":
        receipts = []
        egress_rows = [r for r in egress_rows if r.get("decision") == "blocked"]
    elif kind == "connectors":
        receipts = []
        egress_rows = [r for r in egress_rows if str(r.get("egress_kind", "")).startswith("connector:")]

    receipts = sorted(receipts, key=_event_sort_key, reverse=True)[:limit]
    egress_rows = sorted(egress_rows, key=_event_sort_key, reverse=True)[:limit]
    all_events = sorted(receipts + egress_rows, key=_event_sort_key, reverse=True)[:limit]
    return {
        "ok": True,
        "name": str(name or "global")[:80],
        "summary": privacy_summary(name),
        "location": {"precision": location_precision(name),
                     "modes": ["off", "coarse", "exact"]},
        "connector_policy": connector_policy(),
        "receipts": receipts,
        "egress": egress_rows,
        "events": all_events,
    }


def privacy_summary(name: str | None) -> dict:
    receipts = secure_store.load_jsonl(receipt_path(name), skip_bad=True)
    egress_rows = secure_store.load_jsonl(egress_path(name), skip_bad=True)
    return {
        "turn_receipts": len(receipts),
        "local_turns": sum(1 for r in receipts if r.get("actual_egress") == "none"),
        "cloud_turns": sum(1 for r in receipts if r.get("actual_egress") == "cloud_provider"),
        "egress_events": len(egress_rows),
        "completed_egress": sum(1 for r in egress_rows if r.get("decision") == "completed"),
        "blocked_egress": sum(1 for r in egress_rows if r.get("decision") == "blocked"),
        "connector_events": sum(
            1 for r in egress_rows if str(r.get("egress_kind", "")).startswith("connector:")
        ),
        "zero_egress": egress.zero_enabled(),
    }
