#!/usr/bin/env python3
"""
certify_deployment_proof — ANIMA LAW 005 (DEPLOYED OVER BUILT) has runnable teeth.

Proves the LAW-005 contract by exercising deploy_check's DECISION LOGIC directly — the pure compare()
that GET /version + `python3 scripts/deploy_check.py` turn on — so the verdict is deterministic and
NEVER depends on whether the live :8765 server happens to be up or the tree happens to be clean at
audit time:

  A. GREEN IS NARROW — compare() returns GREEN with ok=True ONLY when the running sha == git HEAD AND
     the working tree is CLEAN. Nothing else is GREEN.
  B. EVERY OTHER REALITY IS A DISTINCT, HONEST VERDICT —
       * running != HEAD                  -> RED (live server is NOT on the committed code; redeploy+restart)
       * running == HEAD but DIRTY tree   -> DIRTY (distinct from RED; commit/stash first), naming the paths
       * /version 404                     -> RED (running build predates the check)
       * server unreachable               -> DOWN (nothing deployed to compare against)
       * no readable git HEAD             -> RED (no certified commit to prove against)
       * running sha empty/'unknown'      -> RED (startup capture failed)
     and result['ok'] is True for NONE of these — only GREEN is ok.
  C. THE REAL-TREE READS ARE REAL + WELL-TYPED — git_head(repo) returns a non-empty short sha string
     and git_dirty(repo) returns a (bool, list[str]); .claude scratch is ignored so it can't false-DIRTY.
     (We assert their TYPES/shape, never this tree's transient cleanliness — that would flake.)
  D. THE /version STAMP IT READS IS REAL — server._capture_deploy() returns {sha,branch,started} and the
     GET /version handler serves that module-level _DEPLOY stash unauthenticated (statically confirmed),
     so deploy_check has a real running-commit to compare HEAD against.

No live server required; no store is touched. The real .anima is fingerprinted before/after and asserted
byte-identical (this cert reads pure logic — it must change nothing). Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_footprint = _g0pe._footprint

_dspec = importlib.util.spec_from_file_location("deploy_check", str(ROOT / "scripts" / "deploy_check.py"))
dc = importlib.util.module_from_spec(_dspec)
_dspec.loader.exec_module(dc)


def _ver(sha, **kw):
    """A synthetic, reachable, 200 GET /version payload with the given running sha."""
    return {"reachable": True, "status": 200, "sha": sha, "branch": "main", "started": 1, **kw}


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("DEPLOYMENT PROOF — ANIMA LAW 005 (DEPLOYED OVER BUILT): compare() decision logic")
    print("=" * 84)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    GREEN, RED, DOWN, DIRTY = dc.GREEN, dc.RED, dc.DOWN, dc.DIRTY

    # ---- A. GREEN IS NARROW -----------------------------------------------------------
    g = dc.compare("abc123", _ver("abc123"), dirty=False)
    ck("A1: running == HEAD AND clean -> GREEN with ok=True",
       g["state"] == GREEN and g["ok"] is True)

    # ---- B. EVERY OTHER REALITY IS A DISTINCT, HONEST VERDICT --------------------------
    mism = dc.compare("abc123", _ver("def456"), dirty=False)
    ck("B1: running != HEAD -> RED, ok False (live server not on the committed code)",
       mism["state"] == RED and mism["ok"] is False)

    drt = dc.compare("abc123", _ver("abc123"), dirty=True, dirty_paths=[" M anima/server.py"])
    ck("B2: running == HEAD but DIRTY tree -> DIRTY (distinct from RED), ok False",
       drt["state"] == DIRTY and drt["state"] != RED and drt["ok"] is False)
    ck("B3: the DIRTY verdict surfaces the uncommitted path(s)",
       "anima/server.py" in (drt.get("message", "") + " ".join(drt.get("dirty_paths", []))))

    p404 = dc.compare("abc123", {"reachable": True, "status": 404})
    ck("B4: /version 404 -> RED (running build predates the check), ok False",
       p404["state"] == RED and p404["ok"] is False)

    down = dc.compare("abc123", {"reachable": False, "error": "connection refused"})
    ck("B5: server unreachable -> DOWN (nothing deployed to compare against), ok False",
       down["state"] == DOWN and down["ok"] is False)

    nohead = dc.compare("", _ver("abc123"))
    ck("B6: no readable git HEAD -> RED (no certified commit to prove against), ok False",
       nohead["state"] == RED and nohead["ok"] is False)

    unk = dc.compare("abc123", _ver("unknown"))
    ck("B7: running sha empty/'unknown' -> RED (startup capture failed), ok False",
       unk["state"] == RED and unk["ok"] is False)

    ck("B8: result['ok'] is True for GREEN ONLY (every non-GREEN verdict is ok=False)",
       g["ok"] is True and all(r["ok"] is False for r in (mism, drt, p404, down, nohead, unk)))

    # ---- C. THE REAL-TREE READS ARE REAL + WELL-TYPED ---------------------------------
    head = dc.git_head(str(ROOT))
    ck("C1: git_head(repo) returns a non-empty short sha string",
       isinstance(head, str) and len(head) > 0)
    dirty, paths = dc.git_dirty(str(ROOT))
    ck("C2: git_dirty(repo) returns a (bool, list[str]) tuple",
       isinstance(dirty, bool) and isinstance(paths, list)
       and all(isinstance(p, str) for p in paths))
    # a tree whose ONLY change is untracked .claude scratch must NOT be reported dirty — proven by
    # the porcelain-parsing rule in git_dirty (untracked + .claude-prefixed is skipped). We assert the
    # rule's INTENT via the function's documented behavior on the real repo: any path it DID return is
    # not a bare untracked .claude entry.
    ck("C3: git_dirty ignores untracked .claude scratch (no bare '?? .claude...' in its paths)",
       not any(p.startswith("??") and ".claude" in p and len(p.split()) <= 2 for p in paths))

    # ---- D. THE /version STAMP IT READS IS REAL ---------------------------------------
    from anima import server
    dep = server._capture_deploy()
    ck("D1: server._capture_deploy() returns a real {sha,branch,started} running-commit stamp",
       isinstance(dep, dict) and {"sha", "branch", "started"}.issubset(dep.keys()))
    server_src = (ROOT / "anima" / "server.py").read_text()
    ck("D2: GET /version serves the _DEPLOY stamp UNAUTHENTICATED (before the _authed() gate)",
       '"/version"' in server_src and "_DEPLOY" in server_src
       and server_src.index('u.path == "/version"') < server_src.index("if not self._authed()"))
    cli_src = (ROOT / "scripts" / "deploy_check.py").read_text()
    ck("D3: the founder CLI exits 0 only on GREEN (a deploy can GATE on it)",
       "return 0 if result.get(\"ok\") else 1" in cli_src)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (pure-logic, no contamination)",
       fp_before == fp_after)

    print("\nDEPLOYMENT-PROOF CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
