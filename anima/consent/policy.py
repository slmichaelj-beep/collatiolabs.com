"""consent.policy — the consent store, the runtime decision, and the memory gate.

The store (.anima/{name}.consent.json) holds per-(scope,domain) consent. The boundary that matters:
gate_memory_candidates() filters durable-memory candidates so a SENSITIVE-domain fact is never written
SILENTLY — without standing consent it is HELD (.anima/{name}.consent_pending.json) for the user to
approve / reject / forget. Every decision is auditable (a security/trust event). Guarded: a consent
hiccup must never break a turn — on any error the gate fails OPEN-but-LOGGED only for non-sensitive
items; sensitive items default to HELD (fail safe).
"""
from __future__ import annotations

import datetime
import hashlib
from pathlib import Path

from anima import secure_store

from . import schema, classifier

STORE = Path(".anima")


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _path(name: str) -> Path:
    return STORE / ("%s.consent.json" % name)


def _pending_path(name: str) -> Path:
    return STORE / ("%s.consent_pending.json" % name)


def load(name: str) -> dict:
    return secure_store.load_json(_path(name), {}) or {}


def _save(name: str, data: dict) -> None:
    try:
        secure_store.save_json(_path(name), data)
    except Exception:
        pass


def _key(scope: str, domain: str) -> str:
    return "%s::%s" % (scope, domain)


def _event(kind: str, detail: str, **extra) -> None:
    try:
        from anima import incident
        incident.security_event(kind, detail, **extra)
    except Exception:
        pass


def status(name: str, scope: str, domain: str) -> str:
    """The current consent status for (scope, domain) — stored, or the safe default."""
    rec = load(name).get(_key(scope, domain))
    if not rec:
        return schema.default_status(scope, domain)
    st = rec.get("status")
    # expiry
    exp = rec.get("expires_at")
    if exp:
        try:
            if datetime.datetime.fromisoformat(exp) < datetime.datetime.now():
                return "expired"
        except Exception:
            pass
    return st or schema.default_status(scope, domain)


def set_consent(name: str, scope: str, domain: str, new_status: str, pacing: str = None) -> dict:
    """Grant / deny / set ask-each-time for (scope, domain). Persisted + audited."""
    if scope not in schema.SCOPES or domain not in schema.DOMAINS or new_status not in schema.STATUSES:
        return {"ok": False, "error": "bad scope/domain/status"}
    data = load(name)
    rec = data.get(_key(scope, domain), {})
    rec.update({"consent_id": _key(scope, domain), "scope": scope, "domain": domain,
                "status": new_status, "pacing": pacing or rec.get("pacing") or schema.default_pacing(domain),
                "user_visible": True, "created_at": rec.get("created_at") or _now(),
                "updated_at": _now()})
    if new_status == "revoked":
        rec["revoked_at"] = _now()
    data[_key(scope, domain)] = rec
    _save(name, data)
    _event("consent_%s" % new_status, "consent %s for %s in %s" % (new_status, scope, domain),
           scope=scope, domain=domain, risk="high" if domain in schema.SENSITIVE_DOMAINS else "low")
    return {"ok": True, "consent": rec}


def revoke(name: str, scope: str, domain: str) -> dict:
    return set_consent(name, scope, domain, "revoked")


def check(name: str, scope: str, domain: str) -> dict:
    """The runtime decision for (scope, domain): allow / ask / block, with the reason + pacing."""
    st = status(name, scope, domain)
    pacing = (load(name).get(_key(scope, domain), {}) or {}).get("pacing") or schema.default_pacing(domain)
    if st == "granted":
        dec = "allow"
    elif st in ("denied", "revoked", "expired"):
        dec = "block"
    else:                                  # ask_each_time
        dec = "ask"
    return {"decision": dec, "status": st, "pacing": pacing, "scope": scope, "domain": domain,
            "reason": "%s consent for %s/%s" % (st, scope, domain)}


# ---------------------------------------------------------------------------------------------
# THE MEMORY GATE — no SILENT sensitive memory write.
# ---------------------------------------------------------------------------------------------
def _cand_text(cand) -> str:
    try:
        if isinstance(cand, dict):
            return " ".join(str(cand.get(k, "")) for k in ("trait", "value", "evidence", "text"))
        return str(cand)
    except Exception:
        return ""


def _pid(name: str, cand) -> str:
    return "p_" + hashlib.sha256((name + _cand_text(cand)).encode("utf-8")).hexdigest()[:12]


def gate_memory_candidates(name: str, cands: list):
    """Filter durable-memory candidates by consent. Returns (allowed, held). A SENSITIVE-domain
    candidate whose memory_write consent is not 'granted' is HELD (not persisted) and recorded as a
    pending sensitive write for the user to approve/reject. Non-sensitive candidates pass through.
    Guarded: on error, sensitive items are HELD (fail safe), non-sensitive pass."""
    allowed, held = [], []
    if not cands:
        return allowed, held
    try:
        pend = _load_pending(name)
        changed = False
        for c in cands:
            cls = classifier.classify_sensitivity(_cand_text(c))
            if not cls.get("sensitive"):
                allowed.append(c)
                continue
            dec = check(name, "memory_write", cls["domain"])
            if dec["decision"] == "allow":
                allowed.append(c)
                continue
            # HELD — a sensitive conclusion is not written silently
            entry = {"pending_id": _pid(name, c), "domain": cls["domain"], "markers": cls["markers"],
                     "candidate": c, "preview": _cand_text(c)[:160], "at": _now(),
                     "decision": dec["decision"], "status": "pending"}
            if not any(p.get("pending_id") == entry["pending_id"] for p in pend):
                pend.append(entry)
                changed = True
            held.append(entry)
            _event("sensitive_memory_held",
                   "a %s-domain memory was held for consent (not written silently)" % cls["domain"],
                   domain=cls["domain"], risk="high")
        if changed:
            _save_pending(name, pend)
    except Exception:
        # fail safe: hold anything that even looks sensitive, pass the rest
        for c in cands:
            (held if classifier.is_sensitive(_cand_text(c)) else allowed).append(c)
    return allowed, held


def _load_pending(name: str) -> list:
    data = secure_store.load_json(_pending_path(name), []) or []
    return data if isinstance(data, list) else []


def _save_pending(name: str, items: list) -> None:
    try:
        secure_store.save_json(_pending_path(name), items)
    except Exception:
        pass


def pending(name: str) -> list:
    """Sensitive memory candidates currently held for the user's decision."""
    return [p for p in _load_pending(name) if p.get("status") == "pending"]


def resolve_pending(name: str, pending_id: str, action: str) -> dict:
    """approve -> persist the held fact to durable memory; reject -> discard. Audited."""
    if action not in ("approve", "reject"):
        return {"ok": False, "error": "action must be approve|reject"}
    items = _load_pending(name)
    target = next((p for p in items if p.get("pending_id") == pending_id and p.get("status") == "pending"), None)
    if not target:
        return {"ok": False, "error": "no such pending item"}
    target["status"] = "approved" if action == "approve" else "rejected"
    target["resolved_at"] = _now()
    if action == "approve":
        try:                               # persist the held candidate now that consent is given
            from anima.memory_lirf import Facts
            f = Facts.load(name)
            f.merge(target["candidate"])
            f.save(name)
        except Exception as e:
            return {"ok": False, "error": "persist failed: %s" % e}
    _save_pending(name, items)
    _event("sensitive_memory_%s" % ("written" if action == "approve" else "discarded"),
           "user %sed a held %s-domain memory" % (action, target.get("domain")),
           domain=target.get("domain"), risk="high")
    return {"ok": True, "pending_id": pending_id, "status": target["status"]}


def settings(name: str) -> dict:
    """The full consent posture for the UI: per sensitive domain, the status of the durable-state
    scopes, plus the count of pending sensitive writes. Read-only."""
    data = load(name)
    rows = []
    for d in schema.SENSITIVE_DOMAINS:
        rows.append({
            "domain": d,
            "memory_write": status(name, "memory_write", d),
            "identity_learning": status(name, "identity_learning", d),
            "source_use": status(name, "source_use", d),
            "pacing": (data.get(_key("memory_write", d), {}) or {}).get("pacing") or schema.default_pacing(d),
        })
    return {"name": name, "domains": rows, "pending": pending(name),
            "scopes": list(schema.SCOPES),
            "doctrine": "Permissions ask CAN; consent asks SHOULD. Sensitive material is never written "
                        "to memory, learned into identity, or reused silently — it is held for your "
                        "decision, and consent can be revoked at any time.",
            "empty": not rows}
