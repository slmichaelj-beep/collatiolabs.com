#!/usr/bin/env python3
"""certify_memory_forget_retraction — a forget is real, acknowledged, ledgered, and final.

Live, against the served creature (her real life — the probes teach and then fully retract):
  1. forget creates a retraction event (the reply carries it; the ledger holds the chain)
  2. the forgotten claim is INACTIVE (no active ledger event, LIRF row retracted)
  3. future recall does NOT use the forgotten claim (memory:honest_unknown — never the value)
  4. the dashboard shows the retracted status (/truth.json by_status)
  5. the memory chip does not appear for a retracted claim (no truth_events on the honest-unknown
     recall — nothing to falsely attribute)
  6. the Truth Ledger shows the full supersession/retraction chain (/truth/trace)
  7. the spine never recites the value back on the forget turn (memory:retraction_ack)
  8. a forget aimed at an EMPTY slot claims nothing ("nothing to forget" — no false deletion)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

oks, fails = [], []


def ck(label, cond):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def _say(text, timeout=120):
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request("http://127.0.0.1:8765/say", data=body,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _get(path):
    with urllib.request.urlopen("http://127.0.0.1:8765" + path, timeout=10) as r:
        return json.loads(r.read())




def _snapshot_real_memory():
    """Save the creature's REAL favorite_color state before the probes (the 2026-06-10 forensic
    lesson: cert fixtures clobbered the user's genuine 'gray'). Returns the active row or None."""
    try:
        import json as _j
        d = _j.loads((ROOT / ".anima" / "Vera.lirf.json").read_text())
        for r in d.get("rows", []):
            if r.get("trait") == "favorite_color" and r.get("status") == "active":
                return dict(r)
    except Exception:
        pass
    return None


def _restore_real_memory(saved):
    """Re-assert the genuine value (with its original provenance) after the probes."""
    if not saved:
        return
    try:
        from anima.memory_lirf import Facts
        from anima.truth import ledger as _tl, schema as _ts
        f = Facts.load("Vera")
        for r in f.rows:
            if r.get("trait") == "favorite_color" and r.get("id") == saved.get("id"):
                r.update({k: saved[k] for k in ("value", "status", "confidence", "source",
                                                 "evidence") if k in saved})
                r["updated"] = saved.get("updated", r.get("updated"))
                r.setdefault("history", []).append(
                    {"value": saved.get("value"), "confidence": saved.get("confidence"),
                     "source": "cert-probe restoration", "at": r["updated"],
                     "reason": "restored after certification probe (real memory is never a fixture)"})
                break
        else:
            row = dict(saved)
            row["status"] = "active"
            f.rows.append(row)
        f.save("Vera")
        _tl.emit("Vera", _ts.make("favorite_color",
                                  "favorite_color = %s" % saved.get("value"), "correction",
                                  provenance_kind="system_cert",
                                  provenance_refs=["cert-probe restoration of the pre-probe value"],
                                  evidence_refs=[saved.get("id") or ""],
                                  scope="long_term", confidence=float(saved.get("confidence") or 0.9),
                                  actor="system"))
    except Exception:
        pass


def main() -> int:
    t0 = time.perf_counter()
    print("MEMORY FORGET / RETRACTION — forgotten means forgotten, and provably so")
    print("=" * 92)

    try:
        _get("/version")
    except Exception as e:
        print("  XX   server unreachable (%r) — this cert requires the live creature" % e)
        print("\nMEMORY-FORGET-RETRACTION CERT: FAIL (1)")
        return 1

    _saved_mem = _snapshot_real_memory()
    name = "Vera"
    # ---- setup: teach, then forget ------------------------------------------------------------
    _say("My favorite color is teal.")
    time.sleep(0.5)
    d_forget = _say("Forget my favorite color.")
    time.sleep(0.5)
    d_recall = _say("What is my favorite color?")

    # ---- 7. the forget turn is acknowledged, never recited --------------------------------------
    ck("7. the forget turn is a deterministic retraction ack (value NEVER recited)",
       d_forget.get("backend") == "memory:retraction_ack"
       and "teal" not in (d_forget.get("reply") or "").lower())

    # ---- 1. retraction event exists --------------------------------------------------------------
    tj = _get("/truth.json")
    ck("1. the forget produced a retraction in the ledger (retracted events present)",
       (tj.get("by_status") or {}).get("retracted", 0) >= 1)

    # ---- 2. the claim is inactive everywhere ------------------------------------------------------
    active_fc = [e for e in (tj.get("active") or []) if e.get("subject") == "favorite_color"]
    ck("2. NO active ledger event remains for the forgotten trait", active_fc == [])
    lirf = json.loads((ROOT / ".anima" / f"{name}.lirf.json").read_text())
    rows = [r for r in lirf.get("rows", []) if r.get("trait") == "favorite_color"]
    ck("2b. every LIRF row for the trait is retracted",
       bool(rows) and all(r.get("status") == "retracted" for r in rows))

    # ---- 3. future recall never uses it ------------------------------------------------------------
    ck("3. future recall is the honest unknown — the forgotten value is NEVER used",
       d_recall.get("backend") == "memory:honest_unknown"
       and "teal" not in (d_recall.get("reply") or "").lower())

    # ---- 4. dashboard shows retracted ---------------------------------------------------------------
    ck("4. the dashboard surface (/truth.json) shows the retracted status",
       "retracted" in (tj.get("by_status") or {}))

    # ---- 5. no memory chip on the honest-unknown recall ----------------------------------------------
    ck("5. the honest-unknown recall carries NO memory attribution (no truth_events to falsely chip)",
       not d_recall.get("truth_events"))

    # ---- 6. the full chain is traceable -----------------------------------------------------------------
    chain_ok = False
    ev_id = (d_forget.get("truth_events") or [""])[0]
    if ev_id:
        chain = (_get("/truth/trace?event_id=" + ev_id) or {}).get("chain") or []
        kinds = [e.get("claim_type") for e in chain]
        statuses = {e.get("active_status") for e in chain}
        chain_ok = (len(chain) >= 2 and "correction" in kinds
                    and statuses <= {"retracted", "superseded"}
                    and any("RETRACTED" in (e.get("claim") or "") for e in chain))
    ck("6. /truth/trace shows the supersession/retraction chain end-to-end", chain_ok)

    # ---- 8. empty-slot forget claims nothing ----------------------------------------------------------
    d_empty = _say("Forget my favorite color.")
    ck("8. a forget aimed at an EMPTY slot honestly says there is nothing to forget",
       d_empty.get("backend") == "memory:retraction_ack"
       and "nothing" in (d_empty.get("reply") or "").lower())

    _restore_real_memory(_saved_mem)               # the probes never destroy real memory

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_memory_forget_retraction", "green" if green else "red",
                files_observed=["anima/truth/api.py", "anima/spine.py", "anima/memory_lirf.py",
                                "anima/server.py"],
                duration_sec=time.perf_counter() - t0, failures=fails, host_specific=False)
    except Exception as e:
        print("  (cert-result emit failed: %r)" % e)
    print("\nMEMORY-FORGET-RETRACTION CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
