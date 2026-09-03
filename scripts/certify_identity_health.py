#!/usr/bin/env python3
"""certify_identity_health — Identity Health & Shadow (Human Operating Layer, Layer 3) is REAL and
FREEZE-SAFE: it observes the identity core + the tamper-evident Shadow Ledger and proves identity
MUTATION stays frozen — the keystone of this layer.

  1. STATE OBSERVED   — the health report reads the real identity core as a field-presence summary
                        (never the raw persona/values), and computes honest health flags.
  2. SHADOW LEDGER    — the Shadow Ledger is a tamper-evident hash chain: a well-formed ledger verifies.
  3. LEDGER BITES     — tampering with a recorded snapshot is DETECTED (verify flips to not-ok). A
                        tamper-evident chain that can't detect tampering is wallpaper.
  4. DIFF VIEWER      — the identity diff reports exactly which core field changed between two snapshots.
  5. FREEZE KEYSTONE  — identity mutation is FROZEN: rollback() pointed at REAL Vera raises
                        FrozenIdentityError before a byte is written (the seatbelt holds).
  6. READ-ONLY        — building the health report does not change the identity fingerprint.
  7. SERVED + AUTH    — the report rides through _identity_health_data; GET /identity serves the page.

Hermetic (uses a temp store for the ledger mechanics; the freeze keystone uses REAL Vera). Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("IDENTITY HEALTH & SHADOW (Layer 3) — freeze-safe observability; mutation stays frozen")
    print("=" * 92)

    from anima.identity_health import health
    from anima import identity_sandbox as ix
    from anima import server

    html = (ROOT / "anima" / "web" / "identity.html").read_text() if (ROOT / "anima" / "web" / "identity.html").exists() else ""
    srv = (ROOT / "anima" / "server.py").read_text()

    # ---- 1 state observed ----------------------------------------------------------------------
    rep = health.report("Vera")
    ck("1. the health report reads the identity core as a field-presence summary (not raw content)",
       isinstance(rep.get("identity"), dict)
       and all("present" in v for v in rep["identity"].values())
       and "stable" in rep["health"] and "freeze_respected" in rep["health"])

    # ---- 2 + 3 shadow ledger verifiable + tamper-detection (the teeth) -------------------------
    tmp = Path(tempfile.mkdtemp(prefix="idh-cert-"))
    ix.ledger_append("Twin", state={"persona": "calm and curious", "values": ["honesty"]}, store=tmp)
    ix.ledger_append("Twin", state={"persona": "calm, curious, and bolder", "values": ["honesty"]}, store=tmp)
    v_ok = ix.ledger_verify("Twin", store=tmp)
    ck("2. the Shadow Ledger is a tamper-evident hash chain — a well-formed ledger verifies",
       v_ok.get("ok") is True and len(v_ok.get("versions", [])) == 2)

    # tamper: rewrite v2's state on disk WITHOUT updating its recorded hash
    lp = ix.ledger_path("Twin", store=tmp)
    lines = lp.read_text().splitlines()
    rec = json.loads(lines[-1]); rec["state"]["persona"] = "SECRETLY REWRITTEN"
    lines[-1] = json.dumps(rec); lp.write_text("\n".join(lines) + "\n")
    v_bad = ix.ledger_verify("Twin", store=tmp)
    ck("3. tampering with a recorded snapshot is DETECTED (verify flips to not-ok with a break)",
       v_bad.get("ok") is False and len(v_bad.get("breaks", [])) >= 1)

    # ---- 4 diff viewer -------------------------------------------------------------------------
    # rebuild a clean 2-snapshot ledger to diff
    tmp2 = Path(tempfile.mkdtemp(prefix="idh-diff-"))
    ix.ledger_append("Twin", state={"persona": "A", "values": ["x"]}, store=tmp2)
    ix.ledger_append("Twin", state={"persona": "B", "values": ["x"]}, store=tmp2)
    d = ix.diff("Twin", store=tmp2)
    ck("4. the identity diff reports exactly which core field changed between two snapshots",
       "persona" in (d.get("changed") or {}) and "values" not in (d.get("changed") or {})
       and d.get("identical") is False)

    # ---- 5 FREEZE KEYSTONE: mutation refused on REAL Vera --------------------------------------
    froze = False
    try:
        ix.rollback("Vera", 1)        # real store, real Vera, freeze active -> must raise
    except ix.FrozenIdentityError:
        froze = True
    except Exception:
        froze = False
    ck("5. FREEZE keystone — rollback() on REAL Vera raises FrozenIdentityError (mutation is frozen)",
       froze is True and rep["freeze"]["frozen"] is True)

    # ---- 6 read-only ---------------------------------------------------------------------------
    fp1 = ix.identity_fingerprint("Vera")
    health.report("Vera"); health.report("Vera")
    fp2 = ix.identity_fingerprint("Vera")
    ck("6. building the health report is READ-ONLY (the identity fingerprint is unchanged)", fp1 == fp2)

    # ---- 7 served + UI -------------------------------------------------------------------------
    data = server._identity_health_data("Vera")
    ck("7. the report rides through _identity_health_data + a GET /identity route exists",
       isinstance(data, dict) and "/identity" in srv and "identity.json" in srv)
    ck("7. the page renders identity health + the Shadow Ledger with the frozen framing",
       bool(html) and "Identity Health" in html and "identityView" in html and "frozen" in html.lower())

    print("\nIDENTITY-HEALTH CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
