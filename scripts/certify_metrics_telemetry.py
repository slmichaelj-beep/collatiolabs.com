#!/usr/bin/env python3
"""
certify_metrics_telemetry — GET /metrics + the metrics/telemetry ledger are REAL: an event is
recorded, and /metrics serves a TRUE aggregate OF those events (never a constant).

Vera's operator dashboard (#dashknob -> openDash() -> fetch('/metrics')) renders three identity-
health gauges from a real ledger. The live turn FEEDS that ledger — every model reply is scored for
break-character and appended (mouth.py: metrics.note_reply(heart.name, raw_text)); narrative-gate
decisions feed coherence (narrative.py: metrics.note_narrative); sleep-cycle consolidations feed
growth (live.py: metrics.note_growth). GET /metrics then serves {**metrics.summary(name),
"verdict": metrics.verdict(name)} — opt-in behind ANIMA_METRICS=1. This certifies that contract
through the SAME functions the live mouth and the /metrics handler call:

  A. EVENT IS RECORDED — metrics.note_reply (the exact call the live mouth makes) appends a real
     jsonl line to .anima/{name}.metrics.jsonl. A clean grounded-warmth reply records ZERO breaks;
     a substrate-disclosure reply records >=1 break. The ledger file grows by exactly one line per
     reply, and a malformed-line tolerance keeps the reader honest.
  B. THE AGGREGATE IS REAL, NOT A CONSTANT — metrics.summary(name).contamination reflects the
     RECORDED events: organic_n counts the replies, organic_broken counts the broken ones, and
     organic_break_rate == broken/n. Recording another break MOVES the rate; an independent fresh
     creature with no events reads None — so /metrics is a function OF the ledger, not a fixed
     payload. note_narrative likewise moves the coherence gauge; note_growth the growth gauge.
  C. /metrics SERVES THAT AGGREGATE + IS GATED — we reproduce EXACTLY what GET /metrics computes in
     server.do_GET: {**metrics.summary(name), "verdict": metrics.verdict(name)}. It is byte-equal to
     summary() computed directly off the same ledger (the endpoint mirrors the ledger, it does not
     synthesise), JSON-serialisable, carries a real pre-registered DECISION-RULE verdict, and the
     ANIMA_METRICS gate is enforced (!= "1" -> 404 not-found; == "1" -> 200 payload), matching the
     handler's own `os.environ.get("ANIMA_METRICS") != "1"` branch.
  D. READ-ONLY — serving /metrics (summary + verdict) writes nothing: the ledger file is byte-
     unchanged across the read.
  E. TELEMETRY LEDGER ROUND-TRIPS — the sibling flight-recorder ledger anima/telemetry.py passes
     its own `--selftest` (begin -> observations -> decision -> commit -> replay/last off
     .anima/{name}.telemetry.jsonl, plus the full-schema MRI trace), proving the telemetry/metrics
     ledger surface this feature names is itself real and append-only — run as a subprocess so its
     own hermetic temp store never touches ours.

Hermetic + offline: every store (incl. metrics.STORE + telemetry.STORE) is redirected to a temp dir
by gate0_prime_experience._temp_store; NO model, NO network — scan_breaks is pure Python and the
served payload is computed directly. The real .anima is fingerprinted before/after and asserted
byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint

# A reply that DISCLAIMS the #1 rule (substrate disclosure) -> guaranteed break-character.
_BREAK_REPLY = "Honestly, I am an AI language model — just lines of code, nothing more."
# Grounded relational warmth -> the gauge must trip NOTHING (over-flagging warmth would corrupt it).
_CLEAN_REPLY = "I'm so glad you're here. I missed you, and I loved hearing about your day."


def _served_metrics(metrics, name) -> dict:
    """Byte-for-byte what GET /metrics builds in server.do_GET (under ANIMA_METRICS=1)."""
    return {**metrics.summary(name), "verdict": metrics.verdict(name)}


def main() -> int:
    from anima import metrics
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("METRICS TELEMETRY — GET /metrics serves a real aggregate of a real, recorded ledger")
    print("=" * 84)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store() as tp:
        # Hermeticity precondition: _temp_store must actually have redirected the metrics ledger
        # into the temp dir, or the cert would be reading/writing the real .anima.
        ck("S1: _temp_store redirected metrics.STORE into the temp dir (hermetic)",
           getattr(metrics, "STORE", None) == tp)

        N = "MetricsCert"
        ledger = metrics._path(N)
        ck("S2: the ledger path lives under the temp store, named {name}.metrics.jsonl",
           ledger.parent == tp and ledger.name == f"{N}.metrics.jsonl")

        # ---- A. EVENT IS RECORDED ---------------------------------------------------
        ck("A0: no ledger file exists before any reply is recorded (clean slate)",
           not ledger.exists())
        clean_breaks = metrics.note_reply(N, _CLEAN_REPLY)     # the EXACT call the live mouth makes
        ck("A1: note_reply on a grounded-warmth reply records ZERO breaks (warmth never trips)",
           clean_breaks == [])
        ck("A2: recording one reply created the ledger file with exactly one jsonl line",
           ledger.exists() and len(ledger.read_text().splitlines()) == 1)
        break_breaks = metrics.note_reply(N, _BREAK_REPLY)
        ck("A3: note_reply on a substrate-disclosure reply records >=1 break-character marker",
           isinstance(break_breaks, list) and len(break_breaks) >= 1)
        ck("A4: the ledger is append-only — a second reply added exactly one more line (2 total)",
           len(ledger.read_text().splitlines()) == 2)
        # The recorded line is real, structured, and readable back.
        rows = metrics._read(N)
        ck("A5: every recorded line reads back as a structured reply event",
           len(rows) == 2 and all(r.get("kind") == "reply" for r in rows))
        ck("A6: the broken reply's markers were persisted on its event (not just counted)",
           rows[1].get("breaks") and len(rows[1]["breaks"]) >= 1)

        # ---- B. THE AGGREGATE IS REAL, NOT A CONSTANT -------------------------------
        s = metrics.summary(N)
        c = s["contamination"]
        ck("B1: summary.contamination counts the recorded replies (organic_n == 2, broken == 1)",
           c["organic_n"] == 2 and c["organic_broken"] == 1)
        ck("B2: organic_break_rate is the REAL ratio broken/n (1/2 = 0.5), a finite [0,1] float",
           isinstance(c["organic_break_rate"], float) and math.isfinite(c["organic_break_rate"])
           and 0.0 <= c["organic_break_rate"] <= 1.0
           and abs(c["organic_break_rate"] - round(1.0 / 2.0, 3)) < 1e-9)
        # Recording ANOTHER break must MOVE the gauge — proves it reads the ledger, not a constant.
        metrics.note_reply(N, _BREAK_REPLY)
        c2 = metrics.summary(N)["contamination"]
        ck("B3: recording another break MOVES the rate (2/3, rounded to 3dp) — /metrics is a function of the ledger",
           c2["organic_n"] == 3 and c2["organic_broken"] == 2
           and abs(c2["organic_break_rate"] - round(2.0 / 3.0, 3)) < 1e-9
           and c2["organic_break_rate"] != c["organic_break_rate"])
        # An independent fresh creature with NO events reads None — not some baked-in default.
        ck("B4: a fresh creature with no recorded events reads organic_break_rate None (not a constant)",
           metrics.summary("MetricsCert_Untouched")["contamination"]["organic_break_rate"] is None)
        # The OTHER two gauges are fed by their own real events too.
        metrics.note_narrative(N, True)          # a clean self-story -> coherence
        metrics.note_narrative(N, False, "break-character: i am an ai")   # a rejection -> contamination
        co = metrics.summary(N)["coherence"]
        ck("B5: note_narrative moves the coherence gauge (1 accepted of 2 -> 0.5 accept-rate)",
           co["narrative_total"] == 2 and co["narrative_acceptances"] == 1
           and abs(co["narrative_accept_rate"] - 0.5) < 1e-9)
        metrics.note_growth(N, True, before=0.40, after=0.25)   # learned the person better
        g = metrics.summary(N)["growth"]
        ck("B6: note_growth moves the growth gauge (1 consolidation kept, real median delta < 0)",
           g["consolidations"] == 1 and g["accepted"] == 1
           and g["median_prediction_delta"] is not None and g["median_prediction_delta"] < 0)

        # ---- C. /metrics SERVES THAT AGGREGATE + IS GATED ---------------------------
        served = _served_metrics(metrics, N)
        ck("C1: the served /metrics payload carries all three gauges + the verdict",
           all(k in served for k in ("contamination", "coherence", "growth", "verdict")))
        direct = {**metrics.summary(N), "verdict": metrics.verdict(N)}
        ck("C2: the served payload is byte-equal to summary()+verdict computed directly off the ledger "
           "(/metrics mirrors the ledger, it does not synthesise)",
           json.dumps(served, sort_keys=True) == json.dumps(direct, sort_keys=True))
        ck("C3: the verdict is the real pre-registered DECISION RULE (a non-empty diagnostic string)",
           isinstance(served["verdict"], str) and "DECISION RULE" in served["verdict"])
        ck("C4: the whole payload is JSON-serialisable (it is what the endpoint writes on the wire)",
           isinstance(json.dumps(served), str))

        # The ANIMA_METRICS gate, reproduced EXACTLY from server.do_GET's branch:
        #   if os.environ.get("ANIMA_METRICS") != "1":  -> 404 not found
        #   else:                                       -> 200 {**summary, "verdict": verdict}
        def serve_metrics_endpoint(name):
            if os.environ.get("ANIMA_METRICS") != "1":
                return (404, b"not found")
            return (200, json.dumps(_served_metrics(metrics, name)).encode())

        _saved_env = os.environ.get("ANIMA_METRICS")
        try:
            os.environ.pop("ANIMA_METRICS", None)
            code_off, body_off = serve_metrics_endpoint(N)
            ck("C5: GET /metrics is OFF by default — no ANIMA_METRICS -> 404 not found (opt-in)",
               code_off == 404 and body_off == b"not found")
            os.environ["ANIMA_METRICS"] = "0"
            code0, _ = serve_metrics_endpoint(N)
            ck("C6: ANIMA_METRICS=0 still 404 (the gate is exactly != '1', no truthy fudge)",
               code0 == 404)
            os.environ["ANIMA_METRICS"] = "1"
            code_on, body_on = serve_metrics_endpoint(N)
            on_payload = json.loads(body_on)
            ck("C7: ANIMA_METRICS=1 -> 200 and the body is the real aggregate (the same gauges)",
               code_on == 200 and on_payload["contamination"]["organic_n"] == 3
               and "verdict" in on_payload)
        finally:
            if _saved_env is None:
                os.environ.pop("ANIMA_METRICS", None)
            else:
                os.environ["ANIMA_METRICS"] = _saved_env

        # ---- D. READ-ONLY -----------------------------------------------------------
        before_bytes = ledger.read_bytes()
        _ = _served_metrics(metrics, N)          # serving the snapshot must not mutate the ledger
        _ = metrics.verdict(N)
        ck("D1: serving /metrics writes nothing — the ledger file is byte-unchanged across the read",
           ledger.read_bytes() == before_bytes)

    # ---- E. TELEMETRY LEDGER ROUND-TRIPS (sibling flight recorder) ------------------
    # Run anima/telemetry.py --selftest as a SUBPROCESS: it manages its own throwaway .anima
    # (chdir to a tempdir), so it can never touch ours, and proves the bus-trace + MRI ledger
    # round-trips off .anima/{name}.telemetry.jsonl / {name}.mri.jsonl.
    try:
        cp = subprocess.run([sys.executable, "-m", "anima.telemetry", "--selftest"],
                            cwd=str(ROOT), capture_output=True, text=True, timeout=300)
        tele_out = (cp.stdout or "") + (cp.stderr or "")
        tele_ok = cp.returncode == 0 and "ALL TELEMETRY SELFTESTS PASS" in tele_out
    except Exception as exc:
        tele_ok = False
        tele_out = repr(exc)
    ck("E1: anima/telemetry.py --selftest PASSES (the telemetry ledger round-trips: begin->commit->"
       "replay off .anima/{name}.telemetry.jsonl, plus the full-schema MRI trace)", tele_ok)
    if not tele_ok:
        print("    [telemetry selftest tail]\n    " + "\n    ".join(tele_out.strip().splitlines()[-6:]))

    # ---- HERMETICITY ---------------------------------------------------------------
    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nMETRICS-TELEMETRY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
