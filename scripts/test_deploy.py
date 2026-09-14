#!/usr/bin/env python3
"""PROVE-DEPLOYMENT invariant test — ASSERT ANIMA LAW 005 on deploy_check's logic.

    DEPLOYED OVER BUILT.
    Built ≠ Tested ≠ Certified ≠ Deployed ≠ Running ≠ Being Used ≠ Working.
    The git, deployed, and running commits must match.

Unlike a written law, this file *checks* the comparison that the deploy check turns on. It
is FULLY SYNTHETIC and OFFLINE: every SHA is mocked and the network is monkeypatched away —
it never starts a server, never opens a socket, and never reads or writes a real Vera.* file.
What it proves is the decision logic itself:

  * match            -> GREEN (deployment proven, exit ok)
  * mismatch/behind  -> RED   (the exact failure that bit us: live process behind HEAD)
  * /version 404     -> RED   ("running process predates this check — redeploy")
  * server down      -> RED/DOWN (clear "server is DOWN" error)
  * unknown git HEAD -> RED   (no certified commit to prove against)
  * server 'unknown' -> RED   (running build's own capture failed)

    python3 scripts/test_deploy.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import deploy_check  # noqa: E402  — the module under test (scripts/ is on sys.path above)

_fails: list[str] = []


def ok(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


# ===================================================================================
# 1. compare() — the pure decision LAW 005 turns on. No I/O; mocked SHAs only.
# ===================================================================================
def test_compare_match_is_green():
    print("\n[1] compare — running sha == git HEAD  ->  GREEN (deployment proven)")
    r = deploy_check.compare("abc1234", {"reachable": True, "status": 200,
                                         "sha": "abc1234", "branch": "main",
                                         "started": "2026-06-05T07:00:00+00:00"})
    ok("state is GREEN", r["state"] == deploy_check.GREEN)
    ok("ok flag is True (exit 0)", r["ok"] is True)
    ok("both SHAs surfaced in the result", r["git_sha"] == "abc1234" and r["running_sha"] == "abc1234")
    ok("message asserts git == running", "git == running" in r["message"])
    ok("start time is carried through for the report", r["started"] == "2026-06-05T07:00:00+00:00")


def test_compare_mismatch_is_red():
    print("\n[2] compare — running BEHIND HEAD  ->  RED (the failure that bit us)")
    r = deploy_check.compare("newHEAD", {"reachable": True, "status": 200,
                                         "sha": "oldRUN", "branch": "main", "started": None})
    ok("state is RED", r["state"] == deploy_check.RED)
    ok("ok flag is False (non-zero exit)", r["ok"] is False)
    ok("message calls out the MISMATCH", "MISMATCH" in r["message"])
    ok("message names BOTH the HEAD and the running sha",
       "newHEAD" in r["message"] and "oldRUN" in r["message"])
    ok("message tells the operator to redeploy + RESTART", "RESTART" in r["message"])


def test_compare_404_predates_check():
    print("\n[3] compare — /version 404  ->  RED ('running process predates this check')")
    r = deploy_check.compare("abc1234", {"reachable": True, "status": 404, "error": "HTTP 404"})
    ok("state is RED", r["state"] == deploy_check.RED)
    ok("ok flag is False", r["ok"] is False)
    ok("message is the exact predates-check phrasing", "predates this check" in r["message"])
    ok("message still reports the git HEAD to deploy", "abc1234" in r["message"])


def test_compare_down_is_clear_error():
    print("\n[4] compare — server unreachable  ->  RED/DOWN with a clear error")
    r = deploy_check.compare("abc1234", {"reachable": False,
                                         "error": "server unreachable: Connection refused"})
    ok("state is DOWN", r["state"] == deploy_check.DOWN)
    ok("ok flag is False", r["ok"] is False)
    ok("message says the server is DOWN", "DOWN" in r["message"])
    ok("the underlying connection error is surfaced", "Connection refused" in r["message"])


def test_compare_unknown_git_head():
    print("\n[5] compare — git HEAD unknown  ->  RED (no certified commit to prove)")
    r = deploy_check.compare("", {"reachable": True, "status": 200, "sha": "abc1234"})
    ok("state is RED", r["state"] == deploy_check.RED)
    ok("ok flag is False", r["ok"] is False)
    ok("message explains git HEAD could not be read", "cannot determine git HEAD" in r["message"])


def test_compare_server_reports_unknown():
    print("\n[6] compare — server serves sha='unknown'  ->  RED (its capture failed)")
    r = deploy_check.compare("abc1234", {"reachable": True, "status": 200, "sha": "unknown"})
    ok("state is RED", r["state"] == deploy_check.RED)
    ok("ok flag is False", r["ok"] is False)
    ok("message flags the empty/'unknown' running commit", "unknown" in r["message"])


# ===================================================================================
# 7. check() — the full flow with git + HTTP monkeypatched. Still 100% offline.
# ===================================================================================
def test_check_flow_offline():
    print("\n[7] check — end-to-end with git + /version mocked (no network, no server)")
    _saved_git, _saved_fetch = deploy_check.git_head, deploy_check.fetch_version
    try:
        # GREEN: HEAD and the (mocked) running version agree.
        deploy_check.git_head = lambda repo=None: "deadbee"
        deploy_check.fetch_version = lambda url, token="", timeout=5.0: {
            "reachable": True, "status": 200, "sha": "deadbee", "branch": "main",
            "started": "2026-06-05T07:00:00+00:00"}
        g = deploy_check.check(url="http://localhost:9999")
        ok("matched flow is GREEN + ok", g["state"] == deploy_check.GREEN and g["ok"] is True)
        ok("check() records the queried /version url", g["url"].endswith("/version"))

        # RED: same HEAD, the running process is behind.
        deploy_check.fetch_version = lambda url, token="", timeout=5.0: {
            "reachable": True, "status": 200, "sha": "0ldbuild", "branch": "main"}
        b = deploy_check.check(url="http://localhost:9999")
        ok("behind-HEAD flow is RED + not ok", b["state"] == deploy_check.RED and b["ok"] is False)

        # DOWN: nothing answers.
        deploy_check.fetch_version = lambda url, token="", timeout=5.0: {
            "reachable": False, "error": "server unreachable: refused"}
        d = deploy_check.check(url="http://localhost:9999")
        ok("down flow is DOWN + not ok", d["state"] == deploy_check.DOWN and d["ok"] is False)
    finally:
        deploy_check.git_head, deploy_check.fetch_version = _saved_git, _saved_fetch


def test_render_is_safe_on_every_state():
    print("\n[8] _render — never raises, on each state (so the CLI can always print)")
    for state, payload in (
        ("green",  {"state": deploy_check.GREEN, "ok": True, "git_sha": "a", "running_sha": "a",
                    "branch": "main", "started": "t", "message": "m", "url": "u/version"}),
        ("red",    {"state": deploy_check.RED, "ok": False, "git_sha": "a", "running_sha": "b",
                    "message": "m", "url": "u/version"}),
        ("down",   {"state": deploy_check.DOWN, "ok": False, "git_sha": "a", "running_sha": "",
                    "message": "m", "url": "u/version"}),
    ):
        try:
            text = deploy_check._render(payload)
            ok(f"_render({state}) returns a non-empty string", isinstance(text, str) and len(text) > 0)
        except Exception as e:
            ok(f"_render({state}) returns a non-empty string", False)
            print(f"        raised: {e!r}")


def main():
    print("=" * 79)
    print("ANIMA LAW 005 — DEPLOYED OVER BUILT  ::  deploy-check logic (synthetic/offline)")
    print("=" * 79)
    test_compare_match_is_green()
    test_compare_mismatch_is_red()
    test_compare_404_predates_check()
    test_compare_down_is_clear_error()
    test_compare_unknown_git_head()
    test_compare_server_reports_unknown()
    test_check_flow_offline()
    test_render_is_safe_on_every_state()

    print("\n" + "=" * 79)
    if _fails:
        print(f"{len(_fails)} INVARIANT(S) FAILED: " + ", ".join(_fails))
        sys.exit(1)
    print("ALL DEPLOY-CHECK INVARIANTS HOLD (git == running is enforced)")


if __name__ == "__main__":
    main()
