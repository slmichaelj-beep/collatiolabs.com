"""auto_learn.api — the server surface. Suggestion-only; the only persistence path is a
Teaching Mode draft (which then requires explicit approval).

GET  /auto_learn/queue   -> {ok, pending, suggestions}
POST /auto_learn/decide  -> action in convert | dismiss | never_ask_again
"""
from __future__ import annotations

from . import queue


def serve_queue(name: str) -> dict:
    return {"ok": True, "pending": queue.pending(name), "suggestions": queue.load(name)}


def serve_decide(name: str, data: dict, store=None) -> dict:
    al_id = str(data.get("auto_learn_id") or "")
    action = str(data.get("action") or "")
    rec = queue.get(name, al_id, store)
    if rec is None:
        return {"ok": False, "error": "no such suggestion"}
    if action == "convert":
        # the ONLY path toward a store: create a PENDING Teaching draft (no direct persistence)
        try:
            from anima.teaching import queue as tq, schema as tsch
            draft = tsch.make("preference" if rec["scope_recommendation"] != "project"
                              else "project_rule",
                              rec["proposed_learning"], source="auto_learn_draft",
                              scope=rec["scope_recommendation"],
                              risk=rec.get("risk", "low"),
                              target_store="memory",
                              evidence_turns=list(rec.get("evidence") or []))
            tq.propose(name, draft, store=store)
            queue.set_status(name, al_id, "converted_to_teaching_draft", store)
            return {"ok": True, "teaching_draft": draft["teaching_id"],
                    "note": "a PENDING Teaching draft was created — nothing persists without approval"}
        except Exception as e:
            return {"ok": False, "error": repr(e)}
    if action == "dismiss":
        return {"ok": True, "suggestion": queue.set_status(name, al_id, "dismissed", store)}
    if action == "never_ask_again":
        return {"ok": True, "suggestion": queue.set_status(name, al_id, "never_ask_again", store)}
    return {"ok": False, "error": "unknown action %r" % action}
