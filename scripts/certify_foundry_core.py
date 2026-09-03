#!/usr/bin/env python3
"""certify_foundry_core — preflight envelope, venture registry, per-venture isolation, portfolio."""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.foundry import core   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("FOUNDRY CORE — preflight, ventures, isolation, portfolio")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "FoundryCoreCert"
        # 1. no operation without preflight
        ck("1. the Foundry cannot create ventures without a preflight envelope",
           not core.can_operate(N, store=st)["ok"]
           and not core.create_venture(N, "X", "idea_1", store=st)["ok"])
        core.set_preflight(N, total_capital=25000, max_loss=10000, allowed_jurisdictions=["US-DE"],
                           authority_level=0, max_active_ventures=2, store=st)
        ck("2. preflight set -> the Foundry can operate", core.can_operate(N, store=st)["ok"])
        # 3. jurisdiction enforced
        ck("3. a venture in a disallowed jurisdiction is refused",
           not core.create_venture(N, "Bad", "idea_x", jurisdiction="ZZ", store=st)["ok"])
        v1 = core.create_venture(N, "Invoicer", "idea_1", jurisdiction="US-DE", store=st)
        v2 = core.create_venture(N, "Scheduler", "idea_2", jurisdiction="US-DE", store=st)
        ck("4. ventures create within the jurisdiction + active cap", v1["ok"] and v2["ok"])
        # 5. active-venture cap enforced
        ck("5. the active-venture cap blocks a third active venture",
           not core.create_venture(N, "Third", "idea_3", jurisdiction="US-DE", store=st)["ok"])
        # 6. isolation: venture A data is namespaced + not readable as venture B
        a, b = v1["venture"]["venture_id"], v2["venture"]["venture_id"]
        core.write_venture_data(N, a, "memory", {"secret": "A-only customer list"}, store=st)
        ck("6. each venture's data is namespaced by venture_id (distinct store keys)",
           core.venture_store_key(a, "memory") != core.venture_store_key(b, "memory"))
        ck("7. venture B reads its OWN (empty) memory, never venture A's",
           core.read_venture_data(N, b, "memory", store=st) == {}
           and core.read_venture_data(N, a, "memory", store=st)["secret"].startswith("A-only"))
        ck("8. a cross-venture read is blocked at the guard",
           core.cross_venture_read_blocked(b, a) is True
           and core.cross_venture_read_blocked(a, a) is False)
        # 9. portfolio rolls up
        p = core.portfolio(N, store=st)
        ck("9. the portfolio rolls up budget + venture statuses",
           p["total_budget"] == 25000 and p["active_count"] == 2 and "idea" in p["by_status"])
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_foundry_core", "green" if green else "red",
                files_observed=["anima/foundry/core.py"], duration_sec=time.perf_counter() - t0,
                failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nFOUNDRY-CORE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
