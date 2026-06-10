"""teaching.api — the server-facing surface for Teach Vera.

GET  /teaching/queue            -> {ok, pending:[review payloads], records:[all]}
POST /teaching/propose          -> {ok, record, review}
POST /teaching/decide           -> {ok, ...} for action in
                                    approve | edit | reject | chat_only | never_learn | rollback
"""
from __future__ import annotations

from . import apply as _apply, queue, review, rollback as _rb, schema


def serve_queue(name: str) -> dict:
    queue.sweep_expired(name)
    pend = queue.pending(name)
    return {"ok": True,
            "pending": [{"record": r, "review": review.payload(name, r)} for r in pend],
            "records": queue.load(name)}


def serve_propose(name: str, data: dict) -> dict:
    try:
        blocked = queue.blocked_by_do_not_learn(name, str(data.get("content") or ""))
        if blocked:
            return {"ok": False, "error": "blocked by an approved do-not-learn rule",
                    "do_not_learn": blocked.get("teaching_id")}
        rec = schema.make(
            str(data.get("type") or "preference"),
            str(data.get("content") or ""),
            evidence_turns=list(data.get("evidence_turns") or []),
            source=str(data.get("source") or "direct_user"),
            scope=str(data.get("scope") or "long_term"),
            expires_at=data.get("expires_at"),
            risk=str(data.get("risk") or "low"),
            target_store=str(data.get("target_store") or "memory"),
        )
        queue.propose(name, rec)
        return {"ok": True, "record": rec, "review": review.payload(name, rec)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


def serve_decide(name: str, data: dict) -> dict:
    tid = str(data.get("teaching_id") or "")
    action = str(data.get("action") or "")
    if action == "approve":
        return _apply.approve(name, tid, edited_content=data.get("content"),
                              confirm_sensitive=bool(data.get("confirm_sensitive")))
    if action == "edit":
        rec = queue.update(name, tid, to_state="edited",
                           patch={"content": str(data.get("content") or "")})
        return {"ok": rec is not None, "record": rec}
    if action == "reject":
        return _apply.reject(name, tid)
    if action == "chat_only":
        rec = queue.update(name, tid, patch={"scope": "chat"})
        if rec is None:
            return {"ok": False, "error": "no such teaching record"}
        return _apply.approve(name, tid)
    if action == "never_learn":
        # converts the proposal into an approved do-not-learn rule for its content
        rec = queue.get(name, tid)
        if rec is None:
            return {"ok": False, "error": "no such teaching record"}
        _apply.reject(name, tid)
        dnl = schema.make("do_not_learn", rec["content"], source="direct_user",
                          scope="until_revoked", risk="low", target_store="behavior_policy")
        queue.propose(name, dnl)
        return _apply.approve(name, dnl["teaching_id"])
    if action == "rollback":
        return _rb.rollback(name, tid, reason=str(data.get("reason") or "user requested"))
    return {"ok": False, "error": "unknown action %r" % action}
