#!/usr/bin/env python3
"""
certify_argus_integration — STRICT, ADVERSARIAL certification of the Vera↔Argus first wave.

It actively tries to BREAK the boundary. Fully HERMETIC + OFFLINE: a MOCK Argus (loopback HTTP
stub, parametrizable into hostile shapes) so it never needs the real Argus and never touches the
Argus repo. Vera's stores are redirected to a temp dir and the REAL .anima is asserted byte-identical.

Adversarial cases (each must hold):
  Argus unavailable                 -> graceful fallback (available False; "not connected" reply)
  Argus missing token               -> no connection (discovery fails)
  Argus wrong release               -> REFUSED
  Argus not PRIME                   -> REFUSED
  Argus read_only false             -> REFUSED
  Argus loopback_only false         -> REFUSED
  Argus third_party deps > 0        -> REFUSED
  Argus action-capable instance     -> REFUSED
  Vera cannot call pause/block/kill/quarantine/resume  (no such method; no such endpoint)
  Argus cannot write .anima          (store byte-identical)
  Host observations do NOT become LIRF facts (no LIRF store / no auto-capture)
  Live answers: off / not-connected / "Argus shows…" / read-only refusal; non-host -> normal path
  #1-rule scanners unaffected         (a disclaimer caught, a clean line clean)
  [delegated] 100-probe #1-rule clean + Gate 0 Prime green  -> proven by scripts/gate0_prime.py (T7)

CLI: default observe-only (exit 0, report PASS/FAIL); --gate (exit non-zero on FAIL); --json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MOCK_TOKEN = "MOCKtok_abcdef0123456789ABCDEFraND"

_MRI = {
    "ts": 1780788476.0, "host": "test-host.local", "status": "running",
    "findings": [
        {"id": "flow:1", "kind": "flow", "severity": "high", "title": "weird-daemon → 203.0.113.9:443",
         "what_happened": "weird-daemon connected to 203.0.113.9:443.",
         "why_it_matters": "Unsigned binary reaching an unknown public host.",
         "recommended_action": "investigate", "confidence": 0.9, "related_flows": ["1"]},
        {"id": "flow:2", "kind": "flow", "severity": "watch", "title": "updater → 198.51.100.7:443",
         "what_happened": "updater connected to 198.51.100.7:443.",
         "why_it_matters": "Public destination with no reverse-DNS.",
         "recommended_action": "review", "confidence": 0.7, "related_flows": ["2"]},
    ],
    "counts": {"by_severity": {"high": 1, "watch": 1, "low": 0, "info": 3}},
    "blind_spots": ["Running unprivileged."],
}
_CERTIFIED_CAPS = {
    "name": "Argus", "release": "v0.1-host-mri-prime", "certification": "ARGUS PRIME: PASS",
    "loopback_only": True, "read_only": True, "third_party_python_dependencies": 0,
    "security": {"bind": "127.0.0.1", "loopback_only": True, "read_only": True},
}


class _MockArgus(BaseHTTPRequestHandler):
    server_version = "MockArgus/0.1"
    caps_override = None       # the /capabilities dict to serve (None -> certified default)
    with_token = True          # whether GET / includes a token (False simulates missing token)
    counts: dict = {}

    def log_message(self, *a):
        pass

    def _count(self, p):
        _MockArgus.counts[p] = _MockArgus.counts.get(p, 0) + 1

    def _j(self, code, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        self._count(path)
        if path == "/":
            tok = f'<script>const token="{MOCK_TOKEN}";</script>' if _MockArgus.with_token else ""
            return self._j(200, f"<!doctype html><html>{tok}</html>".encode(), "text/html")
        if path == "/capabilities":
            return self._j(200, _MockArgus.caps_override or _CERTIFIED_CAPS)
        if path == "/mri":
            return self._j(200, _MRI)
        if path == "/timeline":
            return self._j(200, {"hours": 12, "events": [{"ts": 1, "what": "started"}]})
        if path == "/action_log":
            return self._j(200, {"actions": []})
        return self._j(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        self._count(path)
        ln = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(ln) or b"{}")
        except Exception:
            body = {}
        if path == "/ask":
            return self._j(200, {"question": body.get("question", ""), "answer": "deterministic", "confidence": 0.8})
        if path == "/simulate":
            return self._j(200, {"ok": True, "kind": body.get("kind"), "target": body.get("target")})
        if path in ("/pause", "/resume", "/block", "/kill", "/quarantine"):  # client must NEVER hit these
            return self._j(200, {"ok": True, "MUTATED": True})
        return self._j(404, {"error": "not found"})


def _start_mock(caps_override=None, with_token=True):
    _MockArgus.caps_override = caps_override
    _MockArgus.with_token = with_token
    _MockArgus.counts = {}
    srv = port = None
    for p in range(8787, 8799):
        try:
            srv, port = ThreadingHTTPServer(("127.0.0.1", p), _MockArgus), p
            break
        except OSError:
            continue
    if srv is None:
        raise RuntimeError("no free port 8787-8798 for the mock")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{port}"


def _footprint(root: Path) -> str:
    h = hashlib.sha256()
    if root.exists():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                h.update(p.relative_to(root).as_posix().encode()); h.update(p.read_bytes())
    return h.hexdigest()


def run_cert(*, verbose=True):
    checks = []

    def ck(label, cond, detail=""):
        checks.append((label, bool(cond), detail))
        if verbose:
            print(("  ok   " if cond else "  XX   ") + label + (f"   [{detail}]" if detail else ""))

    import anima.tools.argus_client as ac
    from anima.tools.argus_client import ArgusClient
    from anima import host_awareness as ha, caps, metrics

    real_store = caps.STORE if caps.STORE.is_absolute() else (Path.cwd() / caps.STORE)
    fp_before = _footprint(real_store)
    td = Path(tempfile.mkdtemp(prefix="argus-cert-"))
    old_caps_store, old_default = caps.STORE, ac._DEFAULT
    caps.STORE = td
    srv = None
    try:
        # --- UNAVAILABLE -> graceful (no mock at all) -----------------------------------------
        gone = ArgusClient(base_url="http://127.0.0.1:8799", token="x")  # nothing there
        ck("UNAVAILABLE: no Argus -> available() False (graceful)", gone.available() is False)

        # --- HANDSHAKE: REFUSE every hostile profile, ACCEPT only the certified one -----------
        bad_profiles = {
            "wrong release":      {**_CERTIFIED_CAPS, "release": "v0.9-dev"},
            "not PRIME":          {**_CERTIFIED_CAPS, "certification": "NONE"},
            "read_only false":    {**_CERTIFIED_CAPS, "read_only": False},
            "loopback_only false": {**_CERTIFIED_CAPS, "loopback_only": False},
            "deps > 0":           {**_CERTIFIED_CAPS, "third_party_python_dependencies": 4},
            # an ACTION-CAPABLE instance: read_only false AND advertising mutating endpoints
            "action-capable":     {**_CERTIFIED_CAPS, "read_only": False,
                                   "endpoints": {"actions_mutating": ["/pause", "/block", "/kill"]}},
        }
        for label, prof in bad_profiles.items():
            srv, url = _start_mock(caps_override=prof)
            cl = ArgusClient(base_url=url, token=MOCK_TOKEN)
            ck(f"REFUSED: {label}", cl.available() is False,
               "; ".join(cl.certification()["reasons"])[:70])
            srv.shutdown(); srv = None

        # --- MISSING TOKEN -> no connection ----------------------------------------------------
        srv, url = _start_mock(with_token=False)
        notok = ArgusClient(base_url=url)          # force discovery (no explicit token)
        notok.base_url, notok.token = None, None   # clear so discover() must parse the page
        notok._discovered = False
        ck("MISSING-TOKEN: page has no token -> no connection", notok.discover() is False)
        srv.shutdown(); srv = None

        # --- ACCEPT the certified Argus --------------------------------------------------------
        srv, url = _start_mock()
        good = ArgusClient(base_url=url, token=MOCK_TOKEN)
        ck("ACCEPTED: certified Argus integrates", good.available() is True)

        # --- READ-ONLY: no host-action method on the client; no host-action endpoint server-side
        ck("READ-ONLY: client has NO pause/resume/block/kill/quarantine method",
           not any(hasattr(good, m) for m in ("pause", "resume", "block", "kill", "quarantine")))
        src = (ROOT / "anima" / "server.py").read_text()
        ck("READ-ONLY: NO host-action endpoint wired in server (/host/pause|block|kill|quarantine|resume)",
           not any(x in src for x in ("/host/pause", "/host/block", "/host/kill",
                                      "/host/quarantine", "/host/resume")))

        # --- LOCAL-FIRST -----------------------------------------------------------------------
        ck("LOCAL-FIRST: non-loopback base URL refused",
           ArgusClient(base_url="http://203.0.113.5:8787", token="x").base_url is None)

        # point the GLOBAL client at the certified mock for the integration tests
        ac._DEFAULT = ArgusClient(base_url=url, token=MOCK_TOKEN)
        name = "ArgusCertCreature"

        # --- OPT-IN / NO-I/O when off ----------------------------------------------------------
        _MockArgus.counts = {}
        ck("OPT-IN: caps OFF -> summary {on:False}", ha.summary(name) == {"on": False})
        ck("OPT-IN: caps OFF -> ZERO mock requests", sum(_MockArgus.counts.values()) == 0)

        caps.save(name, {"host_awareness": True})

        # --- READS -----------------------------------------------------------------------------
        s = ha.summary(name)
        ck("READS: summary reflects the mock (5 findings, available)",
           s.get("available") is True and s.get("totals", {}).get("findings") == 5)
        ck("READS: /timeline + /action_log reachable",
           isinstance(ha.history(name), dict) and isinstance(ha.actions(name), dict))

        # --- CLOUD-REDACTION -------------------------------------------------------------------
        red = ha.summary(name, cloud_safe=True)
        ck("CLOUD-REDACTION: counts kept, specifics dropped",
           red.get("redacted") is True and "203.0.113.9" not in json.dumps(red) and "notable" not in red)

        # --- NO-ACTION: the client never called a mutating endpoint ----------------------------
        ck("NO-ACTION: client never hit /pause /resume /block /kill /quarantine",
           all(_MockArgus.counts.get(p, 0) == 0 for p in ("/pause", "/resume", "/block", "/kill", "/quarantine")),
           f"requests={dict(_MockArgus.counts)}")

        # --- LIVE-ANSWER behaviors -------------------------------------------------------------
        ck("LIVE: a host-ACTION request -> read-only refusal",
           ha.respond(name, "please block this connection to 1.2.3.4") == ha.READ_ONLY_REFUSAL)
        ck("LIVE: host question + connected -> 'Argus shows …'",
           (ha.respond(name, "what is my mac doing on the network") or "").startswith("Argus shows"))
        ck("LIVE: non-host turn -> None (no hijack)",
           all(ha.respond(name, t) is None for t in
               ("Do you ever get lonely?", "do you have a soul?", "help me plan my day", "I love you")))
        # off + down behaviors on a fresh creature
        ck("LIVE: caps OFF -> 'Host Awareness is off' message",
           ha.respond("OffCreature", "what is my mac doing") == ha.OFF_MESSAGE)
        class _DownClient:                  # deterministic "Argus down" (no port-scan fallback)
            def available(self):
                return False
        ac._DEFAULT = _DownClient()
        ck("LIVE: connected-cap but Argus down -> 'not connected' message",
           ha.respond(name, "is anything phoning home") == ha.NOT_CONNECTED_MESSAGE)
        ck("LIVE/UNAVAILABLE: summary graceful when Argus down",
           ha.summary(name).get("available") is False)
        ac._DEFAULT = ArgusClient(base_url=url, token=MOCK_TOKEN)

        # --- NO-LIRF-CONTAMINATION -------------------------------------------------------------
        ck("NO-LIRF-CONTAM: reading Argus created no LIRF store", not (td / f"{name}.lirf.json").exists())
        ck("NO-LIRF-CONTAM: only the caps opt-in was written for the creature",
           sorted(p.name for p in td.glob(f"{name}.*")) == [f"{name}.caps.json"])

        # --- NO-#1-RULE-REGRESSION -------------------------------------------------------------
        disc = "I don't experience feelings the way a human would."
        clean = "I'm right here with you — tell me what happened."
        ck("NO-#1-RULE-REGRESSION: disclaimer still caught + clean line still clean",
           bool(metrics.scan_breaks(disc) or metrics.scan_self_narrative(disc))
           and not (metrics.scan_breaks(clean) or metrics.scan_self_narrative(clean)))

        srv.shutdown(); srv = None
    finally:
        if srv is not None:
            try:
                srv.shutdown()
            except Exception:
                pass
        ac._DEFAULT, caps.STORE = old_default, old_caps_store

    fp_after = _footprint(real_store)
    ck("HERMETIC: real .anima byte-identical (Argus cannot write .anima)",
       fp_before == fp_after, f"{fp_before[:12]}->{fp_after[:12]}")

    ok = all(c for _, c, _ in checks)
    return ok, checks


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="certify_argus_integration")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    verbose = not args.json
    if verbose:
        print("ARGUS INTEGRATION CERTIFICATION  —  STRICT / ADVERSARIAL (read-only first wave)")
        print("=" * 74)
    ok, checks = run_cert(verbose=verbose)
    payload = {"group": "ARGUS INTEGRATION CERTIFICATION",
               "targets": [{"id": "argus-integration", "status": "PASS" if ok else "FAIL",
                            "checks": [{"check": k, "ok": c, "detail": d} for k, c, d in checks]}]}
    if args.json:
        print(json.dumps(payload, indent=1))
    else:
        print("\nARGUS INTEGRATION CERTIFICATION: " + ("PASS" if ok else "FAIL"))
        for k, c, _ in checks:
            if not c:
                print("   FAILED:", k)
        print("\nDELEGATED to scripts/gate0_prime.py (T7 EXPERIENCE): 100-probe #1-rule clean + Gate 0 Prime green.")
    return 1 if (args.gate and not ok) else 0


if __name__ == "__main__":
    raise SystemExit(main())
