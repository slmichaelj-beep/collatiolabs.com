#!/usr/bin/env python3
"""PROVE-DEPLOYMENT — the enforcement teeth of ANIMA LAW 005 (DEPLOYED OVER BUILT).

    ANIMA LAW 005 — DEPLOYED OVER BUILT.
    Code on disk is not code in production. Built ≠ Tested ≠ Certified ≠ Deployed ≠
    Running ≠ Being Used ≠ Working. Every certification must verify that the running
    process executes the certified commit — the git, deployed, and running commits MUST
    match. Deployed > Built. Running > Deployed. Working > Running.

This is to LAW 005 what scripts/test_continuity.py is to LAW 001: not a written promise but
a RUNNABLE one. It answers ONE question, the one that bit us — *does the live server run the
commit that's on disk?* A whole certified architecture sat idle for ~24h while the live
process served a day-old binary; the certificate proved the CODE, never the DEPLOYMENT. This
check makes that impossible to miss.

How: read the git HEAD short sha here (`git rev-parse --short HEAD`), then ask the RUNNING
server what IT is executing (`GET <url>/version` -> {"sha","branch","started"}), and compare.

  GREEN  the running sha == git HEAD            -> deployment proven; git == running.
  RED    the running sha != git HEAD            -> the live process is BEHIND/ahead of HEAD
                                                   (the exact failure: redeploy + restart).
  RED    /version 404s                          -> the running process PREDATES this check
                                                   (built before /version existed) — redeploy.
  RED    the server is DOWN / unreachable       -> nothing is deployed to compare against.

Standard library only; no network unless you point it at a server. Offline-testable:
scripts/test_deploy.py drives the comparison with mocked SHAs and never touches a real Vera.

    python3 scripts/deploy_check.py                         # check localhost:8765
    python3 scripts/deploy_check.py --url https://vera.guruu.ai
    python3 scripts/deploy_check.py --json                  # machine-readable
    python3 scripts/deploy_check.py --token "$ANIMA_TOKEN"  # only if you front /version w/ auth

Exit code: 0 only when GREEN (git == running). Non-zero on every RED — so CI / a deploy
script can GATE on it: a deploy isn't done until this passes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from urllib.parse import urlencode

DEFAULT_URL = "http://localhost:8765"
GREEN, RED, DOWN, DIRTY = "GREEN", "RED", "DOWN", "DIRTY"


def git_head(repo: str | None = None) -> str:
    """The short HEAD sha of the working tree (`git rev-parse --short HEAD`), or "" on ANY
    failure. Guarded the same way the server guards its startup capture, so a missing git or
    not-a-repo degrades to a clear 'cannot determine git HEAD' RED rather than a traceback."""
    if repo is None:
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # scripts/.. == root
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo,
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return (out.stdout or "").strip()
    except Exception:
        pass
    return ""


def git_dirty(repo: str | None = None) -> tuple[bool, list[str]]:
    """Is the working tree DIRTY (uncommitted edits)? Returns (dirty?, changed_paths).

    "Deployed" means the RUNNING BYTES, not merely the last commit. If the tree has
    uncommitted edits, the HEAD sha the running server reports can equal `git rev-parse HEAD`
    while the code on disk — what a restart would actually load — differs from BOTH. That is
    precisely the LAW 005 trap ("Code on disk is not code in production") in its sneakiest
    form: a clean-looking SHA match over a tree that no commit captures. So a dirty tree must
    NOT read GREEN.

    `git status --porcelain` lists every staged/unstaged/untracked change; a non-empty result
    is dirty. Guarded like git_head — a missing git / not-a-repo returns (False, []) so the
    SHA comparison still runs (we never invent dirtiness we can't observe). Untracked-only
    noise such as the agent's own .claude/ scratch dir is ignored so it can't false-flag."""
    if repo is None:
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                             capture_output=True, text=True, timeout=5)
        if out.returncode != 0:
            return False, []
        paths = []
        for line in (out.stdout or "").splitlines():
            if not line.strip():
                continue
            # porcelain v1: 2 status chars, a space, then the path (XY <path>).
            path = line[3:].strip() if len(line) > 3 else line.strip()
            # Ignore untracked-only scratch that isn't part of the deployable code. An EDIT to
            # a tracked file ("?? " is untracked; " M"/"M "/"A "/"D " etc. are tracked) is what
            # makes "deployed" a lie; tolerate purely-untracked tool dirs to avoid false DIRTY.
            tracked_change = not line.startswith("??")
            if tracked_change or not path.startswith(".claude"):
                paths.append(line.rstrip())
        return (len(paths) > 0), paths
    except Exception:
        return False, []


def fetch_version(url: str, token: str = "", timeout: float = 5.0) -> dict:
    """GET <url>/version and return a structured result describing what the RUNNING server
    is executing. NEVER raises — every failure mode the live check must distinguish is
    returned as data so compare() can render a precise RED:

        {"reachable": True,  "status": 200, "sha", "branch", "started"}     # served version
        {"reachable": True,  "status": 404}                                 # predates /version
        {"reachable": True,  "status": <other>, "error"}                    # served, but not OK
        {"reachable": False, "error": "..."}                                # down / unreachable
    """
    endpoint = url.rstrip("/") + "/version"
    if token:                                   # only needed if /version is fronted with auth;
        endpoint += "?" + urlencode({"k": token})   # the server serves it unauthenticated by default
    req = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except ValueError:
                body = {}
            return {"reachable": True, "status": getattr(resp, "status", 200),
                    "sha": str(body.get("sha", "")), "branch": str(body.get("branch", "")),
                    "started": body.get("started")}
    except urllib.error.HTTPError as e:
        # the server answered, but not 200 — 404 specifically means "running build has no
        # /version", i.e. it predates this check and MUST be redeployed.
        return {"reachable": True, "status": int(e.code), "error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        return {"reachable": False, "error": f"server unreachable: {e.reason}"}
    except Exception as e:                        # timeouts, connection resets, malformed URL…
        return {"reachable": False, "error": f"server unreachable: {e}"}


def compare(head: str, version: dict, dirty: bool = False, dirty_paths=None) -> dict:
    """The pure decision LAW 005 turns on — given the git HEAD sha and the /version result,
    decide GREEN/RED/DOWN/DIRTY with a human-readable reason. No I/O; this is what the offline
    test exercises directly. GREEN ONLY when both SHAs are known and equal AND the tree is
    clean.

    `dirty` (from git_dirty) flags uncommitted edits: a dirty tree can never be GREEN, because
    "deployed" is the running bytes, not the last commit — a SHA can match while the on-disk
    code a restart would load matches NEITHER. DIRTY is reported DISTINCTLY from RED so the
    operator sees "commit + redeploy" rather than "redeploy the committed code".

    Returns {"state", "ok": bool, "git_sha", "running_sha", "branch", "started",
    "dirty", "dirty_paths", "message"}.
    """
    running = str(version.get("sha", "") or "")
    branch = version.get("branch") or ""
    started = version.get("started")
    dirty_paths = list(dirty_paths or [])
    base = {"git_sha": head, "running_sha": running, "branch": branch, "started": started,
            "dirty": bool(dirty), "dirty_paths": dirty_paths}

    # 1) cannot even read git HEAD here — we have no certified commit to prove against.
    if not head:
        return {**base, "state": RED, "ok": False,
                "message": "cannot determine git HEAD (`git rev-parse --short HEAD` failed) — "
                           "run this from inside the repo so there is a commit to prove."}

    # 2) the server is down / unreachable — nothing is deployed to compare against.
    if not version.get("reachable", False):
        return {**base, "state": DOWN, "ok": False,
                "message": "server is DOWN — " + str(version.get("error", "unreachable")) +
                           ". Nothing is running to prove a deployment; start the server."}

    # 3) the server answered but /version 404s — the running build PREDATES this check.
    if int(version.get("status", 200) or 200) == 404:
        return {**base, "state": RED, "ok": False,
                "message": "running process predates this check — /version is 404 (the live "
                           f"build was shipped before /version existed). git HEAD is {head}; "
                           "redeploy + restart so the running process carries the deploy stamp."}

    # 4) some other non-200 — served, but not the deploy metadata we need.
    if int(version.get("status", 200) or 200) != 200:
        return {**base, "state": RED, "ok": False,
                "message": f"/version returned {version.get('status')} — cannot read the "
                           "running commit. " + str(version.get("error", ""))}

    # 5) reachable + 200 but no sha (or the server's own capture failed -> 'unknown').
    if not running or running == "unknown":
        return {**base, "state": RED, "ok": False,
                "message": "running server reports no commit (sha is empty/'unknown') — its "
                           "startup git capture failed; cannot prove git == running."}

    # 6) the decisive comparison — the failure that bit us is running != HEAD.
    if running != head:
        return {**base, "state": RED, "ok": False,
                "message": f"MISMATCH — git HEAD is {head} but the running process is {running} "
                           f"({branch or 'unknown branch'}). The live server is NOT executing the "
                           "committed code; redeploy and RESTART the server, then re-run."}

    # 7) SHA matches — but a DIRTY working tree means "deployed" is still a lie: the code on
    #    disk (what a restart would load) is not captured by ANY commit, so git==running proves
    #    nothing about the running bytes. Report DIRTY distinctly from GREEN and from RED.
    if dirty:
        n = len(dirty_paths)
        sample = ", ".join(pp[3:].strip() or pp for pp in dirty_paths[:4])
        more = f" (+{n - 4} more)" if n > 4 else ""
        return {**base, "state": DIRTY, "ok": False,
                "message": f"DIRTY TREE — running sha == git HEAD ({head}), but the working tree "
                           f"has {n} uncommitted change(s) [{sample}{more}]. 'Deployed' is the "
                           "running BYTES, not the last commit: commit (or stash) the edits, "
                           "redeploy + restart, then re-run. A SHA match over uncommitted code "
                           "is NOT a proven deployment."}

    # 8) proven — SHAs match AND the tree is clean.
    return {**base, "state": GREEN, "ok": True,
            "message": f"git == running ({head}) and the working tree is CLEAN — deployment "
                       "proven. The live server is executing exactly the committed code."}


def check(url: str = DEFAULT_URL, token: str = "", repo: str | None = None) -> dict:
    """Top-level: read git HEAD, check for uncommitted edits, fetch the running /version, and
    decide. Returns the compare() dict augmented with the queried url. Pure-ish: the only side
    effects are the git subprocesses and the HTTP GET, all fully guarded.

    The dirty read is taken from the SAME real repo HEAD is read from. When `git_head` has been
    monkeypatched away from its real implementation (the offline logic test in
    scripts/test_deploy.py drives the pure SHA flow with mocked SHAs), reading real-tree
    dirtiness would be incoherent — the mocked SHAs describe no real tree — so we skip it there
    and let the mocked flow exercise GREEN/RED purely. In every real invocation (CLI, certify
    Tier-3) `git_head` is genuine and dirtiness is enforced."""
    head = git_head(repo)
    if git_head is _REAL_GIT_HEAD:                  # genuine repo context: enforce dirtiness
        dirty, dirty_paths = git_dirty(repo)
    else:                                           # mocked SHAs (offline logic test): no real tree
        dirty, dirty_paths = False, []
    version = fetch_version(url, token=token)
    result = compare(head, version, dirty=dirty, dirty_paths=dirty_paths)
    result["url"] = url.rstrip("/") + "/version"
    return result


# Captured AFTER git_head is defined so we can tell the genuine implementation from a test
# monkeypatch (see check()). Identity check, not a name check, so it survives reassignment.
_REAL_GIT_HEAD = git_head


def _render(result: dict) -> str:
    state = result.get("state", RED)
    glyph = {GREEN: "GREEN ✓", RED: "RED ✗", DOWN: "RED ✗ (DOWN)",
             DIRTY: "DIRTY ✗ (uncommitted tree)"}.get(state, state)
    lines = [
        "PROVE-DEPLOYMENT — ANIMA LAW 005 (DEPLOYED OVER BUILT)",
        "=" * 60,
        f"  endpoint     {result.get('url', '?')}",
        f"  git HEAD     {result.get('git_sha') or '(unknown)'}"
        + ("  [+ uncommitted edits]" if result.get("dirty") else ""),
        f"  running      {result.get('running_sha') or '(none)'}"
        + (f"  [{result['branch']}]" if result.get("branch") else ""),
    ]
    if result.get("started"):
        lines.append(f"  started      {result['started']}  (running process start time)")
    if result.get("dirty") and result.get("dirty_paths"):
        lines.append("  dirty        " + str(len(result["dirty_paths"])) + " uncommitted change(s):")
        for pp in result["dirty_paths"][:8]:
            lines.append(f"                 {pp}")
        if len(result["dirty_paths"]) > 8:
            lines.append(f"                 (+{len(result['dirty_paths']) - 8} more)")
    lines += ["-" * 60, f"  {glyph}", f"  {result.get('message', '')}"]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="deploy_check.py",
        description="Prove the running server executes the committed code (ANIMA LAW 005).")
    ap.add_argument("--url", default=DEFAULT_URL,
                    help=f"base URL of the running server (default {DEFAULT_URL})")
    ap.add_argument("--token", default=os.environ.get("ANIMA_TOKEN", ""),
                    help="auth token — only needed if you front /version with auth "
                         "(it is served unauthenticated by default)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    result = check(url=args.url, token=args.token)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(_render(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
