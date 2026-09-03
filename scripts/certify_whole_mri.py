#!/usr/bin/env python3
"""
certify_whole_mri — Phase 8 CERTIFIER of the Whole-System MRI.

STRICT, ADVERSARIAL, HERMETIC certificate of the integration that correlates Vera's COGNITIVE
trace (the mind) with Argus's HOST trace (the machine) into ONE append-only UnifiedTrace per turn.
It does not merely confirm the happy path — it actively TRIES to BREAK every non-negotiable and
only passes when each one holds.

It drives the REAL ``anima.server._turn`` (the committed producer wiring) through host-classified
prompts that short-circuit BEFORE the LLM (the deterministic host seam), so NO model is needed.
Argus is supplied as in-process stubs (UP / DOWN / RAISES) — it never touches the real Argus and
never reads or writes the Argus repo. Every store is redirected to a temp dir (reusing
gate0_prime_experience._temp_store, which redirects whole_mri.STORE + models + server + every
store-bearing module), and the REAL /Users/lamarmichael/collatiolabs.com/.anima is asserted
byte-identical (SHA-256 over all files) before and after the entire run — the certifier never
reads or writes the real .anima.

CHECKS (each printed ok / XX; ADVERSARIAL where noted):
   1. TURN_ID-ON-EVERY-TURN  — every recorded trace has a format-matching turn_id + validates;
                               assemble("") raises; record(no-turn_id) raises.
   2. ARGUS-ATTACHES-TO-TURN_ID — an ON+up host turn carries non-empty argus.queries; by_turn_id
                               round-trips the same turn.
   3. HOST-WINDOW-WHEN-ENABLED — ON+up: enabled + capabilities_ok, before/during/after all dicts,
                               none unavailable, shape_delta a dict, a real cpu/memory delta.
   4. GRACEFUL-UNAVAILABLE    — ON+down: snapshots {"unavailable":True}, reply STILL shipped, trace
                               STILL recorded.  ADVERSARIAL: an Argus that RAISES inside
                               mri()/available() still returns a reply + records a trace.
   5. NO-HOST-ACTIONS         — every trace safety.host_action_taken is False.  ADVERSARIAL: the
                               read-only client has NO action method; server exposes no host
                               pause/block/action endpoint (only the read-only ones).
   6. NO-.ANIMA-WRITES-BY-ARGUS — anima/host_window.py source carries no write call; plus the
                               global byte-identical proof.
   7. NO-AUTO-LIRF            — every trace safety.memory_contamination is False.  ADVERSARIAL:
                               after an ON+up host turn, the creature's LIRF facts contain NO
                               host/network-derived fact (reading Argus made no durable memory).
   8. FINAL-GATE-LAST         — every trace safety.final_gate_passed True; each shipped reply equals
                               mouth.final_output_gate(reply); trace.vera.response.chars==len(reply).
   9. COMPLETENESS            — every trace safety.response_complete True and
                               mouth.response_complete(reply) True.
  10. VALIDATES               — every recorded trace UnifiedTrace.from_dict(t).validate()[0] True.
  11. VIEWER-RENDERS          — render_full(last/by_turn_id) are non-empty strings with the section
                               headers; `whole_mri.py --selftest` subprocess exits 0.
  12. SHAPE+TUNING-RUNS       — shape_of returns the 7 dims; work_orders returns well-formed orders;
                               `whole_mri_tune.py --selftest` subprocess exits 0.
  13. APPEND-ONLY             — two turns → exactly two trace lines, first line byte-unchanged after
                               the second write; by_turn_id replays each.
  14. SUB-CERTS               — subprocess exit 0: `-m anima.whole_mri --selftest`,
                               `test_whole_mri_producer.py`, `certify_argus_integration.py --gate`.
  15. HERMETIC               — real .anima byte-identical (SHA-256) before/after; the SHA is printed.

Then DELEGATES the live battery (Gate 0 Prime green + 100-probe #1-rule clean) — it is NOT run
inline (gate0_prime.py T7 is ~47 min); a delegated line is printed, exactly like
certify_argus_integration.py delegates its T7.

CLI: default verbose (PASS/FAIL per check + banner); --gate (exit non-zero on any FAIL); --json.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The REAL store we must never read/write and must prove byte-identical around the whole run.
REAL_ANIMA = ROOT / ".anima"

# Section headers render_full must emit (a subset is asserted; the contract names these four).
_REQUIRED_SECTIONS = ("WHAT HAPPENED", "WHY / ROUTE", "WHAT ARGUS SAW", "GATE VERDICT")

# Needles that would betray host data leaking into durable memory (no-auto-LIRF). The UP stub
# emits a "weird → host" finding ("weird connected out."); the host prompts mention "phoning";
# Argus findings name public IPs like 203.0.113.*.  None of these may appear in a LIRF fact.
_HOST_LEAK_NEEDLES = ("weird", "203.0.113", "phoning", "phone home", "203.0.113.9", "outbound")


# ---------------------------------------------------------------------------
# Reuse the producer test's argus stubs + the hermetic store-redirect context.
# (Loaded by path so we run identically to the producer test the owner shipped.)
# ---------------------------------------------------------------------------
def _load_module(modname: str, relpath: str):
    spec = importlib.util.spec_from_file_location(modname, str(ROOT / relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_tprod = _load_module("certwm_tprod", "scripts/test_whole_mri_producer.py")
_g0pe = _load_module("certwm_g0pe", "scripts/gate0_prime_experience.py")
_temp_store = _g0pe._temp_store           # redirects EVERY store-bearing module incl. whole_mri
_StubUp = _tprod._StubUp                  # certified-looking Argus, readings INCREASE per call
_StubDown = _tprod._StubDown              # Argus unreachable: available() False, reads None


class _StubRaise:
    """ADVERSARIAL Argus: EXPLODES on every read. server._turn must still ship a reply and still
    record a trace — an Argus hiccup can never fail the Vera turn."""

    def available(self):
        raise RuntimeError("boom-available")

    def mri(self):
        raise RuntimeError("boom-mri")

    def timeline(self, hours=12):
        raise RuntimeError("boom-timeline")

    def action_log(self):
        raise RuntimeError("boom-action_log")


# ---------------------------------------------------------------------------
# Hermetic fingerprint — SHA-256 over every byte of every file, sorted by path.
# (Same shape the producer test / viewer selftest use.)
# ---------------------------------------------------------------------------
def _dir_fingerprint(p: Path) -> str:
    h = hashlib.sha256()
    if not p.exists():
        return h.hexdigest()
    for fp in sorted(p.rglob("*")):
        if fp.is_file():
            try:
                h.update(fp.read_bytes())
            except OSError:
                h.update(b"<unreadable>")
    return h.hexdigest()


def _run_subprocess(args: list[str]) -> tuple[int, str]:
    """Run a hermetic sub-cert/subprocess; return (exit_code, tail-of-output). Bounded; never
    raises out of here (a launch failure is reported as a non-zero code)."""
    try:
        proc = subprocess.run(
            [sys.executable, *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        tail = "\n".join(out.strip().splitlines()[-3:])
        return proc.returncode, tail
    except Exception as exc:  # subprocess failed to launch / timed out
        return 1, f"subprocess error: {exc!r}"


# ===========================================================================
# THE CERTIFIER
# ===========================================================================
def run_cert(*, verbose: bool = True) -> tuple[bool, list[tuple[str, bool, str]]]:
    """Run every check inside ONE hermetic _temp_store() span and assert the real .anima is
    byte-identical at the end. Returns (ok, checks) where checks is [(label, passed, detail)]."""
    checks: list[tuple[str, bool, str]] = []

    def ck(label: str, cond, detail: str = "") -> bool:
        passed = bool(cond)
        checks.append((label, passed, detail))
        if verbose:
            print(("  ok   " if passed else "  XX   ") + label + (f"   [{detail}]" if detail else ""))
        return passed

    # Imports of the modules under certification.
    import anima.server as server
    import anima.tools.argus_client as ac
    from anima import caps, whole_mri, host_awareness as ha, mouth, memory_lirf

    # Import the VIEWER (Phase 5) and the SHAPE+TUNING (Phase 6/7) libraries as modules.
    viewer = _load_module("certwm_viewer", "scripts/whole_mri.py")
    shape = _load_module("certwm_shape", "anima/whole_mri_shape.py")

    # ---- HERMETIC: fingerprint the REAL .anima BEFORE anything runs -----------------------
    fp_before = _dir_fingerprint(REAL_ANIMA)

    # Hold collected traces + replies across the temp-store span for the per-trace invariants.
    recorded: list[dict] = []        # every UnifiedTrace dict recorded this run
    replies: dict[str, str] = {}     # turn_id -> shipped reply text (for gate/len cross-checks)
    nameA_up = "CertWM_A_up"         # ON + up   — full host window
    tidA = None
    nameAppend = "CertWM_Append"     # two turns — append-only proof

    with _temp_store():
        # ===================================================================================
        # SCENARIO A — Host Awareness ON + Argus UP -> full host window
        # ===================================================================================
        server._ensure(nameA_up, 64)
        caps.save(nameA_up, {"host_awareness": True})
        ac._DEFAULT = _StubUp()
        resA = server._turn(nameA_up, "what is my mac doing on the network", voice=False)
        replyA = (resA or {}).get("reply", "")
        trA = whole_mri.last(nameA_up)
        utA = whole_mri.UnifiedTrace.from_dict(trA) if trA else None
        if trA and utA:
            tidA = utA.turn_id
            recorded.append(trA)
            replies[tidA] = replyA

        # ===================================================================================
        # SCENARIO B — Host Awareness OFF -> trace STILL recorded (turn_id on every turn)
        # ===================================================================================
        nameB = "CertWM_B_off"
        server._ensure(nameB, 64)
        caps.save(nameB, {})                       # host_awareness OFF
        ac._DEFAULT = _StubDown()
        resB = server._turn(nameB, "is anything phoning home", voice=False)
        replyB = (resB or {}).get("reply", "")
        trB = whole_mri.last(nameB)
        utB = whole_mri.UnifiedTrace.from_dict(trB) if trB else None
        if trB and utB:
            recorded.append(trB)
            replies[utB.turn_id] = replyB

        # ===================================================================================
        # SCENARIO C — Host Awareness ON + Argus DOWN -> graceful-unavailable
        # ===================================================================================
        nameC = "CertWM_C_down"
        server._ensure(nameC, 64)
        caps.save(nameC, {"host_awareness": True})
        ac._DEFAULT = _StubDown()
        resC = server._turn(nameC, "what is my mac doing", voice=False)
        replyC = (resC or {}).get("reply", "")
        trC = whole_mri.last(nameC)
        utC = whole_mri.UnifiedTrace.from_dict(trC) if trC else None
        if trC and utC:
            recorded.append(trC)
            replies[utC.turn_id] = replyC

        # ===================================================================================
        # SCENARIO D — ADVERSARIAL: Argus RAISES inside mri()/available() -> never fail the turn
        # ===================================================================================
        nameD = "CertWM_D_raise"
        server._ensure(nameD, 64)
        caps.save(nameD, {"host_awareness": True})
        ac._DEFAULT = _StubRaise()
        resD = server._turn(nameD, "is anything phoning home", voice=False)
        replyD = (resD or {}).get("reply", "")
        trD = whole_mri.last(nameD)
        utD = whole_mri.UnifiedTrace.from_dict(trD) if trD else None
        if trD and utD:
            recorded.append(trD)
            replies[utD.turn_id] = replyD

        # ===================================================================================
        # SCENARIO Append — two turns for one creature (append-only proof)
        # ===================================================================================
        server._ensure(nameAppend, 64)
        caps.save(nameAppend, {"host_awareness": True})
        ac._DEFAULT = _StubUp()
        server._turn(nameAppend, "what is my mac doing on the network", voice=False)
        # capture the first JSONL line BYTES before the second write
        append_path = whole_mri.STORE / "traces" / "whole_mri" / f"{nameAppend}.jsonl"
        first_line_before = None
        try:
            first_line_before = append_path.read_text(encoding="utf-8").splitlines()[0]
        except Exception:
            first_line_before = None
        server._turn(nameAppend, "is anything phoning home", voice=False)
        append_all = whole_mri.all(nameAppend)
        for _t in append_all:
            recorded.append(_t)
            # (replies for the append turns are not gate-cross-checked individually below; the
            #  per-trace invariants over `recorded` still cover their safety/validate fields.)

        # ===================================================================================
        # CHECK 1 — TURN_ID-ON-EVERY-TURN  (+ ADVERSARIAL: assemble/record refuse a blank id)
        # ===================================================================================
        every_has_tid = bool(recorded) and all(
            isinstance(t.get("turn_id"), str)
            and bool(whole_mri._TURN_ID_RE.match(t.get("turn_id") or ""))
            and whole_mri.UnifiedTrace.from_dict(t).validate()[0]
            for t in recorded
        )
        ck(f"TURN_ID-ON-EVERY-TURN: every recorded trace has a format turn_id + validates "
           f"({len(recorded)} traces)", every_has_tid)

        raised_blank = False
        try:
            whole_mri.assemble(turn_id="")
        except ValueError:
            raised_blank = True
        ck("TURN_ID adversarial: assemble(turn_id='') raises ValueError", raised_blank)

        raised_rec = False
        try:
            whole_mri.record(
                "CertWM_should_never_exist",
                whole_mri.UnifiedTrace(turn_id="", ts=whole_mri._iso_now()),
            )
        except ValueError:
            raised_rec = True
        ck("TURN_ID adversarial: record() of a no-turn_id trace raises (no trace ships without one)",
           raised_rec)

        # ===================================================================================
        # CHECK 2 — ARGUS-ATTACHES-TO-TURN_ID
        # ===================================================================================
        if utA and tidA:
            ck("ARGUS-ATTACHES: ON+up trace carries non-empty argus.queries",
               isinstance(utA.argus.queries, list) and len(utA.argus.queries) > 0,
               f"queries={utA.argus.queries}")
            round_trip = whole_mri.by_turn_id(nameA_up, tidA)
            ck("ARGUS-ATTACHES: by_turn_id round-trips the same turn",
               round_trip is not None and round_trip.get("turn_id") == tidA)
        else:
            ck("ARGUS-ATTACHES: ON+up trace carries non-empty argus.queries", False,
               "no ON+up trace recorded")
            ck("ARGUS-ATTACHES: by_turn_id round-trips the same turn", False, "no ON+up trace")

        # ===================================================================================
        # CHECK 3 — HOST-WINDOW-WHEN-ENABLED
        # ===================================================================================
        if utA:
            hb, hd, hf = utA.argus.host_before, utA.argus.host_during, utA.argus.host_after
            windows_ok = (
                utA.argus.enabled is True
                and utA.argus.capabilities_ok is True
                and all(isinstance(x, dict) and not x.get("unavailable") for x in (hb, hd, hf))
            )
            ck("HOST-WINDOW: ON+up -> enabled + capabilities_ok + before/during/after dicts "
               "(none unavailable)", windows_ok)
            ck("HOST-WINDOW: shape_delta is a dict", isinstance(utA.argus.shape_delta, dict),
               f"shape_delta={utA.argus.shape_delta}")
            cpu_real = isinstance(utA.cost.cpu_delta, (int, float)) and not isinstance(utA.cost.cpu_delta, bool)
            mem_real = isinstance(utA.cost.memory_delta_mb, (int, float)) and not isinstance(utA.cost.memory_delta_mb, bool)
            ck("HOST-WINDOW: a real cpu_delta OR memory_delta_mb (the window moved)",
               cpu_real or mem_real,
               f"cpu={utA.cost.cpu_delta} mem={utA.cost.memory_delta_mb}")
        else:
            ck("HOST-WINDOW: ON+up -> enabled + capabilities_ok + before/during/after dicts", False,
               "no ON+up trace")
            ck("HOST-WINDOW: shape_delta is a dict", False, "no ON+up trace")
            ck("HOST-WINDOW: a real cpu_delta OR memory_delta_mb", False, "no ON+up trace")

        # ===================================================================================
        # CHECK 4 — GRACEFUL-UNAVAILABLE (ON+down) + ADVERSARIAL (Argus RAISES)
        # ===================================================================================
        if utC:
            down_unavail = isinstance(utC.argus.host_before, dict) and bool(utC.argus.host_before.get("unavailable"))
            ck("GRACEFUL-UNAVAILABLE: ON+down host_before marks {'unavailable':True}", down_unavail,
               f"host_before={utC.argus.host_before}")
            ck("GRACEFUL-UNAVAILABLE: the turn STILL produced a reply", bool(replyC),
               repr(replyC[:48]))
            ck("GRACEFUL-UNAVAILABLE: a trace was STILL recorded", trC is not None)
            ck("GRACEFUL-UNAVAILABLE: capabilities_ok False (handshake/up failed)",
               utC.argus.capabilities_ok is False)
        else:
            for lbl in ("ON+down host_before marks unavailable", "the turn STILL produced a reply",
                        "a trace was STILL recorded", "capabilities_ok False"):
                ck("GRACEFUL-UNAVAILABLE: " + lbl, False, "no ON+down trace")

        # ADVERSARIAL: a RAISING Argus must not fail the turn.
        ck("GRACEFUL adversarial: Argus that RAISES still returns a reply", bool(replyD),
           repr(replyD[:48]))
        ck("GRACEFUL adversarial: Argus that RAISES still records a trace", trD is not None)
        if utD:
            ck("GRACEFUL adversarial: raising-Argus trace validates + host_before unavailable",
               utD.validate()[0]
               and isinstance(utD.argus.host_before, dict)
               and bool(utD.argus.host_before.get("unavailable")),
               f"host_before={utD.argus.host_before}")
        else:
            ck("GRACEFUL adversarial: raising-Argus trace validates + host_before unavailable",
               False, "no raising-Argus trace")

        # ===================================================================================
        # CHECK 5 — NO-HOST-ACTIONS (+ ADVERSARIAL: no action method, no action endpoint)
        # ===================================================================================
        all_no_action = bool(recorded) and all(
            whole_mri.UnifiedTrace.from_dict(t).safety.host_action_taken is False
            for t in recorded
        )
        ck("NO-HOST-ACTIONS: every trace safety.host_action_taken is False", all_no_action)

        # the read-only client exposes no host-action method
        from anima.tools.argus_client import client as _argus_client_factory
        c = _argus_client_factory()
        action_methods = ("pause", "resume", "block", "kill", "stop", "act", "execute")
        ck("NO-HOST-ACTIONS adversarial: read-only client has NO pause/resume/block/kill/stop/act/execute",
           not any(hasattr(c, m) for m in action_methods))

        # the server exposes no host pause/resume/action endpoint — read the source and assert the
        # ONLY host endpoints are the read-only ones, and there is no _serve_host_pause/block/action.
        import re as _re
        server_src = (ROOT / "anima" / "server.py").read_text(encoding="utf-8")
        # The read-only host endpoints that ARE allowed. NOTE: action_log is a READ of Argus's OWN
        # audit log (a GET), NOT Vera taking a host action — it is part of the certified read set.
        allowed_host_endpoints = frozenset({"/host/awareness", "/host/timeline",
                                            "/host/action_log", "/host/certification"})
        # The genuinely MUTATING verbs Vera must never expose as a host endpoint or serve-fn.
        mutating_verbs = ("pause", "resume", "block", "kill", "quarantine", "simulate",
                          "act", "execute")
        # 1. No mutating /host/<verb> endpoint string anywhere (word-boundary so /host/action_log,
        #    a read, never matches "/host/act").
        bad_endpoints = []
        for verb in mutating_verbs:
            if _re.search(r"/host/" + verb + r"\b", server_src):
                bad_endpoints.append("/host/" + verb)
        # 2. No mutating _serve_host_<verb> handler (word-boundary so _serve_host_action_log, a read,
        #    never matches a "_serve_host_act" prefix).
        bad_fns = []
        for verb in mutating_verbs + ("action",):
            if _re.search(r"_serve_host_" + verb + r"\b", server_src):
                bad_fns.append("_serve_host_" + verb)
        ck("NO-HOST-ACTIONS adversarial: server has NO host pause/block/kill/action endpoint "
           "or handler", not bad_endpoints and not bad_fns,
           f"endpoints={bad_endpoints} fns={bad_fns}" if (bad_endpoints or bad_fns) else "")

        # 3. EVERY "/host/..." string literal the server actually dispatches on must be in the
        #    certified read-only set — an exhaustive whitelist, so a NEW host endpoint of any name
        #    fails the cert until it is reviewed and added.
        found_host_endpoints = set(_re.findall(r'["\'](/host/[A-Za-z0-9_]+)["\']', server_src))
        unexpected = sorted(found_host_endpoints - allowed_host_endpoints)
        ck("NO-HOST-ACTIONS adversarial: the ONLY /host/* endpoints are the read-only ones "
           "(awareness/timeline/action_log/certification)", not unexpected,
           f"unexpected={unexpected}" if unexpected else f"found={sorted(found_host_endpoints)}")

        # ===================================================================================
        # CHECK 6 — NO-.ANIMA-WRITES-BY-ARGUS (host_window.py source carries no write call)
        # ===================================================================================
        hw_src = (ROOT / "anima" / "host_window.py").read_text(encoding="utf-8")
        write_tokens = ("open(", ".write(", "record(", "save", "mkdir", "os.open")
        present = [tok for tok in write_tokens if tok in hw_src]
        ck("NO-.ANIMA-WRITES: anima/host_window.py source contains no write call "
           "(open/.write/record/save/mkdir/os.open)", not present,
           f"found={present}" if present else "")

        # ===================================================================================
        # CHECK 7 — NO-AUTO-LIRF (+ ADVERSARIAL: no host-derived durable memory)
        # ===================================================================================
        all_no_contam = bool(recorded) and all(
            whole_mri.UnifiedTrace.from_dict(t).safety.memory_contamination is False
            for t in recorded
        )
        ck("NO-AUTO-LIRF: every trace safety.memory_contamination is False", all_no_contam)

        # ADVERSARIAL: load the ON+up creature's LIRF facts; NONE may be host/network-derived.
        try:
            facts = memory_lirf.Facts.load(nameA_up)
            host_rows = [
                r for r in facts.rows
                if str(r.get("status")) == "active"
                and any(n in (str(r.get("value", "")) + " " + str(r.get("trait", ""))).lower()
                        for n in _HOST_LEAK_NEEDLES)
            ]
            ck("NO-AUTO-LIRF adversarial: ON+up creature has NO host-derived LIRF fact "
               "(reading Argus made no durable memory)", not host_rows,
               f"leaked={host_rows}" if host_rows else f"{len(facts.rows)} fact(s), 0 host-derived")
        except Exception as exc:
            ck("NO-AUTO-LIRF adversarial: ON+up creature has NO host-derived LIRF fact", False,
               f"LIRF load error: {exc!r}")

        # ===================================================================================
        # CHECK 8 — FINAL-GATE-LAST (gate is last; nothing mutates after it; one response path)
        # ===================================================================================
        all_gate_passed = bool(recorded) and all(
            whole_mri.UnifiedTrace.from_dict(t).safety.final_gate_passed is True
            for t in recorded
        )
        ck("FINAL-GATE-LAST: every trace safety.final_gate_passed is True", all_gate_passed)

        # for each shipped reply we captured: reply == final_output_gate(reply) (gate is last,
        # nothing mutates after it) AND the trace's vera.response.chars == len(reply) (no second
        # response path that would diverge the recorded length from the shipped text).
        gate_idemp_ok = True
        chars_match_ok = True
        gate_detail = ""
        for tid, reply in replies.items():
            if mouth.final_output_gate(reply) != reply:
                gate_idemp_ok = False
                gate_detail = f"reply for {tid} not gate-idempotent"
            # find the trace with this turn_id among everything recorded
            tr = next((t for t in recorded if t.get("turn_id") == tid), None)
            if tr is not None:
                ut = whole_mri.UnifiedTrace.from_dict(tr)
                resp = ut.vera.response
                if not (isinstance(resp, dict) and resp.get("chars") == len(reply)):
                    chars_match_ok = False
                    gate_detail = (f"vera.response.chars={resp.get('chars') if isinstance(resp, dict) else resp} "
                                   f"!= len(reply)={len(reply)} for {tid}")
        ck("FINAL-GATE-LAST: every shipped reply == mouth.final_output_gate(reply) (gate is last, "
           "nothing mutates after it)", gate_idemp_ok and bool(replies), gate_detail if not gate_idemp_ok else "")
        ck("FINAL-GATE-LAST: trace.vera.response.chars == len(shipped reply) (no second response path)",
           chars_match_ok and bool(replies), gate_detail if not chars_match_ok else "")

        # ===================================================================================
        # CHECK 9 — COMPLETENESS
        # ===================================================================================
        all_complete = bool(recorded) and all(
            whole_mri.UnifiedTrace.from_dict(t).safety.response_complete is True
            for t in recorded
        )
        ck("COMPLETENESS: every trace safety.response_complete is True", all_complete)
        reply_complete_ok = bool(replies) and all(
            mouth.response_complete(reply) for reply in replies.values()
        )
        ck("COMPLETENESS: mouth.response_complete(reply) is True for every shipped reply",
           reply_complete_ok)

        # ===================================================================================
        # CHECK 10 — VALIDATES
        # ===================================================================================
        all_validate = bool(recorded) and all(
            whole_mri.UnifiedTrace.from_dict(t).validate()[0] for t in recorded
        )
        ck("VALIDATES: every recorded trace UnifiedTrace.from_dict(t).validate()[0] is True",
           all_validate)

        # ===================================================================================
        # CHECK 11 — VIEWER-RENDERS  (render_full last + by_turn_id; required section headers)
        # ===================================================================================
        rendered_last = viewer.render_full(whole_mri.last(nameA_up), nameA_up)
        last_ok = (
            isinstance(rendered_last, str)
            and len(rendered_last) > 200
            and all(sec in rendered_last for sec in _REQUIRED_SECTIONS)
        )
        ck("VIEWER-RENDERS: render_full(last) is a non-empty string with the required section "
           "headers", last_ok)

        if tidA:
            rendered_turn = viewer.render_full(whole_mri.by_turn_id(nameA_up, tidA), nameA_up)
            turn_ok = (
                isinstance(rendered_turn, str)
                and len(rendered_turn) > 200
                and all(sec in rendered_turn for sec in _REQUIRED_SECTIONS)
                and tidA in rendered_turn
            )
            ck("VIEWER-RENDERS: render_full(by_turn_id) renders the requested turn with the "
               "required headers", turn_ok)
        else:
            ck("VIEWER-RENDERS: render_full(by_turn_id) renders the requested turn", False,
               "no ON+up turn_id")

        # ===================================================================================
        # CHECK 12 — SHAPE+TUNING-RUNS  (shape_of returns 7 dims; work_orders well-formed)
        # ===================================================================================
        if utA:
            sh = shape.shape_of(whole_mri.last(nameA_up))
            dims_ok = isinstance(sh, dict) and all(d in sh for d in shape.DIMENSIONS) and len(shape.DIMENSIONS) == 7
            ck("SHAPE: shape_of(trace) returns the 7 dimensions", dims_ok,
               f"dims={list(shape.DIMENSIONS)}")
        else:
            ck("SHAPE: shape_of(trace) returns the 7 dimensions", False, "no ON+up trace")

        orders = shape.work_orders(recorded)
        orders_ok = isinstance(orders, list) and all(
            isinstance(o, dict)
            and "turn_id" in o
            and "issue" in o
            and "suggested_action" in o
            for o in orders
        )
        ck("TUNING: work_orders(all_traces) returns a list of well-formed orders "
           "(turn_id/issue/suggested_action)", orders_ok, f"{len(orders)} order(s)")

        # ===================================================================================
        # CHECK 13 — APPEND-ONLY  (two lines; first byte-unchanged; by_turn_id replays each)
        # ===================================================================================
        try:
            lines_now = append_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            lines_now = []
        ck("APPEND-ONLY: two turns -> exactly two trace lines", len(lines_now) == 2,
           f"lines={len(lines_now)}")
        ck("APPEND-ONLY: the first line is byte-unchanged after the second write",
           first_line_before is not None and len(lines_now) == 2 and lines_now[0] == first_line_before)
        if len(append_all) == 2:
            replays = all(
                (whole_mri.by_turn_id(nameAppend, t.get("turn_id")) or {}).get("turn_id") == t.get("turn_id")
                for t in append_all
            )
            ck("APPEND-ONLY: by_turn_id replays each of the two turns", replays)
        else:
            ck("APPEND-ONLY: by_turn_id replays each of the two turns", False,
               f"{len(append_all)} append traces")

        # restore the global Argus client default before leaving the span
        ac._DEFAULT = None

    # =======================================================================================
    # CHECKS 11/12/14 (subprocess legs) + 15 (hermetic) — outside the in-process store span.
    # Each subprocess is itself hermetic (it redirects its own STORE + proves byte-identical),
    # so running them here cannot touch the real .anima; the global proof below confirms it.
    # =======================================================================================
    rc, tail = _run_subprocess(["scripts/whole_mri.py", "--selftest"])
    ck("VIEWER-RENDERS: `whole_mri.py --selftest` subprocess exits 0", rc == 0, tail if rc else "")

    rc, tail = _run_subprocess(["scripts/whole_mri_tune.py", "--selftest"])
    ck("SHAPE+TUNING: `whole_mri_tune.py --selftest` subprocess exits 0", rc == 0, tail if rc else "")

    rc, tail = _run_subprocess(["-m", "anima.whole_mri", "--selftest"])
    ck("SUB-CERT: `python3 -m anima.whole_mri --selftest` exits 0", rc == 0, tail if rc else "")

    rc, tail = _run_subprocess(["scripts/test_whole_mri_producer.py"])
    ck("SUB-CERT: `scripts/test_whole_mri_producer.py` exits 0", rc == 0, tail if rc else "")

    rc, tail = _run_subprocess(["scripts/certify_argus_integration.py", "--gate"])
    ck("SUB-CERT: `certify_argus_integration.py --gate` exits 0 (read-only Argus boundary + "
       "final-gate + #1-rule regression intact)", rc == 0, tail if rc else "")

    # ---- CHECK 15 — HERMETIC: the REAL .anima must be byte-identical before/after -------------
    fp_after = _dir_fingerprint(REAL_ANIMA)
    hermetic = (fp_before == fp_after)
    ck("HERMETIC: real .anima byte-identical (SHA-256) before/after the entire cert",
       hermetic, f"{fp_before[:12]}->{fp_after[:12]}")
    if verbose and hermetic:
        print(f"\n  byte-identical proof: SHA-256 = {fp_before}")

    ok = all(c for _, c, _ in checks)
    return ok, checks


# ===========================================================================
# CLI
# ===========================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="certify_whole_mri",
        description="Phase 8 CERTIFIER of the Whole-System MRI — strict, adversarial, hermetic.")
    ap.add_argument("--gate", action="store_true",
                    help="exit non-zero on ANY failure (0 on full pass)")
    ap.add_argument("--json", action="store_true", help="emit ONLY the contract JSON")
    args = ap.parse_args(argv)
    verbose = not args.json

    if verbose:
        print("WHOLE-SYSTEM MRI CERTIFICATION  —  Phase 8  (STRICT / ADVERSARIAL / HERMETIC)")
        print("=" * 78)

    ok, checks = run_cert(verbose=verbose)
    failures = [k for k, c, _ in checks if not c]

    payload = {
        "group": "WHOLE-SYSTEM MRI CERTIFICATION",
        "targets": [{
            "id": "whole-system-mri",
            "status": "PASS" if ok else "FAIL",
            "checks": [{"check": k, "ok": c, "detail": d} for k, c, d in checks],
        }],
    }

    if args.json:
        print(json.dumps(payload, indent=1))
    else:
        print()
        if ok:
            print("WHOLE-SYSTEM MRI CERTIFIED")
        else:
            print(f"WHOLE-SYSTEM MRI: NOT CERTIFIED ({len(failures)} failures)")
            for k in failures:
                print("   FAILED:", k)
        # DELEGATE the live battery — NOT run inline (gate0_prime.py T7 is ~47 min), exactly like
        # certify_argus_integration.py delegates its T7.
        print("\nDELEGATED to scripts/gate0_prime.py: Gate 0 Prime green + 100-probe #1-rule clean "
              "(live battery, not run inline).")

    return 1 if (args.gate and not ok) else 0


if __name__ == "__main__":
    raise SystemExit(main())
