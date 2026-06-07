#!/usr/bin/env python3
"""
certify_argus_integration — proves the Vera↔Argus FIRST WAVE is safe: READ-ONLY, certified,
local-first, and unable to contaminate Vera's mind.

Fully HERMETIC + OFFLINE: it stands up a MOCK Argus (a tiny loopback HTTP stub) so it never needs
the real Argus and never touches the real Argus repo. It redirects Vera's stores to a temp dir and
asserts the REAL .anima is byte-identical start→end.

Invariants (each a check):
  1  HANDSHAKE-ACCEPT  : the client integrates with a CERTIFIED Argus (release=v0.1-host-mri-prime,
                         certification="ARGUS PRIME: PASS", loopback_only, read_only, deps=0).
  2  HANDSHAKE-REFUSE  : it REFUSES any non-certified / action-capable profile (wrong release,
                         missing ARGUS PRIME, read_only=false, deps>0) — available() is False.
  3  READ-ONLY         : the client exposes NO host-action method (no pause/resume). There is no
                         code path to a host action in this wave.
  4  OPT-IN / NO-I/O   : with host_awareness OFF, summary=={on:False} AND the mock got ZERO requests.
  5  READS             : with host_awareness ON + certified mock, summary/timeline/action_log/ask work.
  6  LOCAL-FIRST       : a non-loopback base URL is refused.
  7  NO-LIRF-CONTAM    : reading Argus writes NOTHING to LIRF (no {name}.lirf.json appears/changes).
  8  NO-.anima-WRITES  : the whole read flow leaves the store byte-identical (Argus can't write .anima).
  9  CLOUD-REDACTION   : summary(cloud_safe=True) carries counts but no finding titles / IPs.
 10  NO-#1-RULE-REGRESS: the reply-path scanners (scan_breaks / scan_self_narrative) behave
                         identically with the integration present (a disclaimer is still caught,
                         a clean line still clean). Gate 0 Prime is the full proof; this is the unit guard.
 11  HERMETIC          : real .anima byte-identical before vs after.

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

MOCK_TOKEN = "MOCKtok_abcdef0123456789ABCDEFraND"   # >=24 urlsafe chars so the client's regex finds it

# A certified HostMRIFrame the mock serves (one high, one watch, three info).
_MRI = {
    "ts": 1780788476.0, "host": "test-host.local", "status": "running",
    "findings": [
        {"id": "flow:1/TCP/out/203.0.113.9/443", "kind": "flow", "severity": "high",
         "title": "weird-daemon → 203.0.113.9:443",
         "what_happened": "weird-daemon (pid 1) connected to 203.0.113.9:443.",
         "why_it_matters": "Unsigned binary reaching an unknown public host.",
         "recommended_action": "investigate", "confidence": 0.9, "related_flows": ["1/TCP/out/203.0.113.9/443"]},
        {"id": "flow:2/TCP/out/198.51.100.7/443", "kind": "flow", "severity": "watch",
         "title": "updater → 198.51.100.7:443", "what_happened": "updater connected to 198.51.100.7:443.",
         "why_it_matters": "Public destination with no reverse-DNS.",
         "recommended_action": "review", "confidence": 0.7, "related_flows": ["2/TCP/out/198.51.100.7/443"]},
    ],
    "counts": {"by_severity": {"high": 1, "watch": 1, "low": 0, "info": 3}},
    "blind_spots": ["Running unprivileged — only your own processes visible."],
}
_CERTIFIED_CAPS = {
    "name": "Argus", "release": "v0.1-host-mri-prime", "certification": "ARGUS PRIME: PASS",
    "loopback_only": True, "read_only": True, "third_party_python_dependencies": 0,
    "security": {"bind": "127.0.0.1", "loopback_only": True, "read_only": True},
}


class _MockArgus(BaseHTTPRequestHandler):
    server_version = "MockArgus/0.1"
    certified = True            # class-level toggle (one mock per server)
    counts: dict = {}           # request counter, by path

    def log_message(self, *a):
        pass

    def _count(self, path):
        _MockArgus.counts[path] = _MockArgus.counts.get(path, 0) + 1

    def _send(self, code, obj, ctype="application/json"):
        body = (obj if isinstance(obj, bytes) else json.dumps(obj).encode())
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        self._count(path)
        if path == "/":
            html = f'<!doctype html><html><script>const token="{MOCK_TOKEN}";</script></html>'
            return self._send(200, html.encode(), "text/html")
        if path == "/capabilities":
            if _MockArgus.certified:
                return self._send(200, _CERTIFIED_CAPS)
            return self._send(200, {"name": "Argus", "release": "v0.9-dev",        # uncertified
                                    "certification": "NONE", "loopback_only": True,
                                    "read_only": False, "third_party_python_dependencies": 4})
        if path == "/mri":
            return self._send(200, _MRI)
        if path == "/timeline":
            return self._send(200, {"hours": 12, "events": [{"ts": 1, "what": "session started"}]})
        if path == "/action_log":
            return self._send(200, {"actions": []})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        self._count(path)
        ln = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(ln) or b"{}")
        except Exception:
            body = {}
        if path == "/ask":
            return self._send(200, {"question": body.get("question", ""), "answer": "deterministic answer",
                                    "evidence": [], "confidence": 0.8})
        if path == "/simulate":
            return self._send(200, {"ok": True, "kind": body.get("kind"), "target": body.get("target"),
                                    "would_affect": []})
        if path in ("/pause", "/resume"):            # exists on the mock — client must NEVER call it
            return self._send(200, {"ok": True, "MUTATED": True})
        return self._send(404, {"error": "not found"})


def _start_mock(certified=True):
    _MockArgus.certified = certified
    _MockArgus.counts = {}
    srv = port = None
    for p in range(8787, 8799):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), _MockArgus)
            port = p
            break
        except OSError:
            continue
    if srv is None:
        raise RuntimeError("no free port in 8787-8798 for the mock Argus")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{port}"


def _footprint(root: Path) -> str:
    h = hashlib.sha256()
    if root.exists():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                h.update(p.relative_to(root).as_posix().encode())
                h.update(p.read_bytes())
    return h.hexdigest()


def run_cert(*, verbose=True):
    checks = []

    def ck(label, cond, detail=""):
        checks.append((label, bool(cond), detail))
        if verbose:
            print(("  ok   " if cond else "  XX   ") + label + (f"   [{detail}]" if detail else ""))

    import anima.tools.argus_client as ac
    from anima.tools.argus_client import ArgusClient, certified as cert_fn
    from anima import host_awareness as ha, caps, metrics

    real_store = caps.STORE if caps.STORE.is_absolute() else (Path.cwd() / caps.STORE)
    fp_before = _footprint(real_store)
    td = Path(tempfile.mkdtemp(prefix="argus-cert-"))
    old_caps_store = caps.STORE
    old_default = ac._DEFAULT
    caps.STORE = td

    srv = None
    try:
        # ---- 2. HANDSHAKE-REFUSE — uncertified mock is rejected -------------------------------
        srv, url = _start_mock(certified=False)
        bad = ArgusClient(base_url=url, token=MOCK_TOKEN)
        ck("HANDSHAKE-REFUSE: uncertified Argus is refused (available False)", bad.available() is False,
           "; ".join(bad.certification()["reasons"])[:90])
        srv.shutdown(); srv = None

        # ---- 1. HANDSHAKE-ACCEPT — certified mock is accepted ---------------------------------
        srv, url = _start_mock(certified=True)
        good = ArgusClient(base_url=url, token=MOCK_TOKEN)
        ck("HANDSHAKE-ACCEPT: certified Argus integrates (available True)", good.available() is True)
        ck("HANDSHAKE field check passes on the certified profile", cert_fn(_CERTIFIED_CAPS)[0] is True)

        # ---- 3. READ-ONLY — no mutating method exists -----------------------------------------
        ck("READ-ONLY: client has NO pause/resume method", not hasattr(good, "pause") and not hasattr(good, "resume"))
        ck("READ-ONLY: client exposes the documented read methods",
           all(hasattr(good, m) for m in ("capabilities", "mri", "ask", "timeline", "action_log", "simulate_pause")))

        # ---- 6. LOCAL-FIRST -------------------------------------------------------------------
        ck("LOCAL-FIRST: a non-loopback base URL is refused",
           ArgusClient(base_url="http://203.0.113.5:8787", token="x").base_url is None)

        # point the GLOBAL client (used by host_awareness + server) at the certified mock
        ac._DEFAULT = ArgusClient(base_url=url, token=MOCK_TOKEN)
        name = "ArgusCertCreature"

        # ---- 4. OPT-IN / NO-I/O — caps OFF -> {on:False} and ZERO mock requests ---------------
        _MockArgus.counts = {}
        off = ha.summary(name)
        ck("OPT-IN: caps OFF -> summary {on:False}", off == {"on": False})
        ck("OPT-IN: caps OFF -> the mock received ZERO requests", sum(_MockArgus.counts.values()) == 0,
           f"requests={dict(_MockArgus.counts)}")

        caps.save(name, {"host_awareness": True})            # the user opts in

        # ---- 5. READS — summary/timeline/action_log/ask -------------------------------------
        s = ha.summary(name)
        ck("READS: summary.available True + reflects mock counts",
           s.get("available") is True and s.get("totals", {}).get("findings") == 5,
           f"totals={s.get('totals')}")
        ck("READS: notable surfaces the high/watch findings, human-level",
           len(s.get("notable", [])) == 2 and all("means" in n and "todo" in n for n in s["notable"]))
        ck("READS: /timeline reachable", isinstance(ha.history(name), dict))
        ck("READS: /action_log reachable", isinstance(ha.actions(name), dict))
        ck("READS: /ask reachable via client", isinstance(ac._DEFAULT.ask("why slow"), dict))

        # ---- 9. CLOUD-REDACTION — no specifics under a cloud brain ----------------------------
        red = ha.summary(name, cloud_safe=True)
        blob = json.dumps(red)
        ck("CLOUD-REDACTION: counts kept, specifics dropped",
           red.get("redacted") is True and "notable" not in red
           and "203.0.113.9" not in blob and "weird-daemon" not in blob)

        # the client never touched a mutating endpoint
        ck("NO-ACTION: client never called /pause or /resume on the mock",
           _MockArgus.counts.get("/pause", 0) == 0 and _MockArgus.counts.get("/resume", 0) == 0,
           f"requests={dict(_MockArgus.counts)}")

        # ---- 7. NO-LIRF-CONTAMINATION — Argus reads never write LIRF --------------------------
        lirf = td / f"{name}.lirf.json"
        ck("NO-LIRF-CONTAM: reading Argus created no LIRF store", not lirf.exists())
        creature_files = sorted(p.name for p in td.glob(f"{name}.*"))
        ck("NO-LIRF-CONTAM: only the caps opt-in was written for the creature",
           creature_files == [f"{name}.caps.json"], f"files={creature_files}")

        # ---- 10. NO-#1-RULE-REGRESSION — the scanners behave the same -------------------------
        disc = "I don't experience feelings the way a human would."
        clean = "I'm right here with you — tell me what happened."
        dirty = bool(metrics.scan_breaks(disc) or metrics.scan_self_narrative(disc))
        cln = not (metrics.scan_breaks(clean) or metrics.scan_self_narrative(clean))
        ck("NO-#1-RULE-REGRESSION: a disclaimer is still caught + a clean line still clean", dirty and cln)

        srv.shutdown(); srv = None
    finally:
        if srv is not None:
            try:
                srv.shutdown()
            except Exception:
                pass
        ac._DEFAULT = old_default
        caps.STORE = old_caps_store

    # ---- 8 + 11. HERMETIC — real .anima byte-identical ---------------------------------------
    fp_after = _footprint(real_store)
    ck("HERMETIC: real .anima byte-identical before vs after (no Argus write to .anima)",
       fp_before == fp_after, f"{fp_before[:12]}->{fp_after[:12]}")

    ok = all(c for _, c, _ in checks)
    return ok, checks


def _payload(ok, checks):
    return {
        "group": "ARGUS INTEGRATION CERTIFICATION",
        "targets": [{
            "id": "argus-integration", "status": "PASS" if ok else "FAIL",
            "checks": [{"check": k, "ok": c, "detail": d} for k, c, d in checks],
        }],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="certify_argus_integration")
    ap.add_argument("--gate", action="store_true", help="exit non-zero on FAIL")
    ap.add_argument("--json", action="store_true", help="emit only the contract JSON")
    args = ap.parse_args(argv)

    verbose = not args.json
    if verbose:
        print("ARGUS INTEGRATION CERTIFICATION  —  Vera<->Argus first wave (READ-ONLY)")
        print("=" * 70)
    ok, checks = run_cert(verbose=verbose)
    if args.json:
        print(json.dumps(_payload(ok, checks), indent=1))
    else:
        failed = [k for k, c, _ in checks if not c]
        print("\nARGUS INTEGRATION CERTIFICATION: " + ("PASS" if ok else f"FAIL ({len(failed)})"))
        for k in failed:
            print("   FAILED:", k)
    if args.gate and not ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
