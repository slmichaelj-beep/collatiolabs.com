#!/usr/bin/env python3
"""certify_live_ux — the REAL browser-facing paths the hermetic certs missed.

These are the two live failures the program-reality gate was green through:

  (A) a large file upload (bigger than the old 25 MB body cap) PARSES over REAL HTTP — the cap +
      single-read used to silently truncate the base64 body into invalid JSON, surfacing in the UI
      as the confusing "Intake unavailable: could not reach the server".
  (B) a genuinely over-cap body returns an HONEST 413 with an actionable message, not a truncated
      parse and not a connection error.
  (C) a generated reply NEVER ends mid-sentence — the _finish_on_sentence guard trims a reply that
      hit the token ceiling back to its last complete sentence, and the token floor is sane (the old
      48–160 cap cut replies off partway, the "Vera stops at half-finished sentences" bug).

(A)/(B) hit a temporary loopback server that uses the real HTTP Handler with all stores redirected.
(C) is hermetic and always runs. Exit 0 == CERTIFIED; 1 == FAIL.
"""
from __future__ import annotations

import base64
import contextlib
import importlib.util
import json
import os
import re as _re
import socket
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store

@contextlib.contextmanager
def _isolated_http_server():
    """Run the real HTTP Handler on an ephemeral loopback port with redirected stores."""
    from anima import server as _srv

    class _CertHandler(_srv.Handler):
        name = "Vera"
        token = ""
        pairing_codes: set[str] = set()

        def log_message(self, _fmt, *_args):
            return

    old_no_passkey = os.environ.get("ANIMA_NO_PASSKEY")
    os.environ["ANIMA_NO_PASSKEY"] = "1"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _CertHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = int(httpd.server_address[1])
        yield f"http://127.0.0.1:{port}", port
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        if old_no_passkey is None:
            os.environ.pop("ANIMA_NO_PASSKEY", None)
        else:
            os.environ["ANIMA_NO_PASSKEY"] = old_no_passkey


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("LIVE UX INTEGRITY — large upload parses / over-cap 413 / replies finish on a sentence")
    print("=" * 92)
    live = "SKIPPED"

    # ---- (C) REPLY COMPLETION (hermetic — always runs) ---------------------------------------
    from anima.mouth import _finish_on_sentence as fos
    frag = ("I'm not aware of any uploads from you regarding a 'blue copper ladder'. My memory only "
            "retains information from our direct conversations, so if that topic wasn't discussed "
            "between us, I wouldn't have any records of it. If you'd like to share more about what "
            "this is or")
    trimmed = fos(frag)
    ck("C1: a reply cut off mid-sentence is trimmed back to the last COMPLETE sentence",
       trimmed != frag and trimmed.rstrip().endswith("of it."))
    ck("C2: a clean reply is left untouched (no over-trimming)",
       fos("July 25, 1977 — like I'd forget your birthday.")
       == "July 25, 1977 — like I'd forget your birthday.")
    ck("C2: a short punctuation-less reply is left untouched (never blanks a reply)",
       fos("sure thing") == "sure thing")
    msrc = (ROOT / "anima" / "mouth.py").read_text()
    m = _re.search(r"(?:self\.brain|brain)\.max_tokens = max\((\d+),", msrc)
    floor = int(m.group(1)) if m else 0
    ck("C3: the reply token floor is sane (>=256 — not the old 48/160 that cut sentences off)",
       floor >= 256)

    with _temp_store():
        # ---- (D) DISK PRE-FLIGHT (hermetic — always runs) ------------------------------------
        # A base64 file decodes straight to the staging dir; on a near-full disk that ENOSPCs
        # mid-write. _intake_plan must refuse HONESTLY before writing. Prove the block path + that
        # nothing is staged.
        import base64 as _b64
        from anima import server as _srv
        _orig_free = _srv._free_bytes
        try:
            real_free = _orig_free(_srv._staging_dir("Vera"))
            ck("D1: _free_bytes reports real volume free space (>0)",
               isinstance(real_free, int) and real_free > 0)
            _srv._free_bytes = lambda p: 5 * 1024 * 1024        # pretend only 5 MB free
            r = _srv._intake_plan("Vera", {"kind": "file", "filename": "x.txt",
                                           "bytes_b64": _b64.b64encode(b"x" * 2048).decode()})
            ck("D2: a file upload on a near-full disk is REFUSED honestly (not an ENOSPC mid-write)",
               (not r.get("ok")) and "disk space" in (r.get("error") or "").lower())
            ck("D2: nothing is staged when the disk guard refuses",
               not (_srv._staging_dir("Vera") / (str(r.get("source_id", "")) + ".txt")).exists())
        finally:
            _srv._free_bytes = _orig_free

        # ---- (A)/(B) ISOLATED REAL HTTP ------------------------------------------------------
        with _isolated_http_server() as (base, port):
            live = "REAL"

            # (A) a ~30 MB file body (well over the old 25 MB cap) must PARSE, not truncate.
            raw = ("blue copper ladder 92817 has twelve rungs, forged in Aldermere. " * 460000).encode()
            b64 = base64.b64encode(raw).decode()
            body = json.dumps({"kind": "file", "filename": "big_note.txt", "bytes_b64": b64}).encode()
            ok_big = False
            try:
                r = urllib.request.urlopen(urllib.request.Request(
                    base + "/intake/plan", data=body,
                    headers={"Content-Type": "application/json"}), timeout=90)
                out = json.loads(r.read())
                ok_big = bool(out.get("ok"))
            except Exception as e:
                print("      (upload error: %r)" % e)
            ck("A1: a %.0f MB body (over the old 25 MB cap) PARSES over isolated real HTTP — "
               "no truncated JSON" % (len(body) / 1e6), ok_big)

            # (B) an over-cap body (declared via Content-Length) -> honest 413, not a truncated parse.
            got413 = honest = False
            try:
                huge = 600 * 1024 * 1024
                req = (b"POST /intake/plan HTTP/1.1\r\nHost: localhost\r\n"
                       b"Content-Type: application/json\r\nContent-Length: " + str(huge).encode() +
                       b"\r\nConnection: close\r\n\r\n{}")
                s = socket.create_connection(("127.0.0.1", port), timeout=10)
                s.sendall(req)
                resp = b""
                while len(resp) < 2048:
                    d = s.recv(2048)
                    if not d:
                        break
                    resp += d
                s.close()
                got413 = b"413" in resp.split(b"\r\n", 1)[0]
                honest = b"too large" in resp.lower()
            except Exception as e:
                print("      (413 probe error: %r)" % e)
            ck("B1: an over-cap body returns an HONEST 413 (not 'could not reach the server')",
               got413 and honest)

    print("\nLIVE: %s (%s)" % (
        live, "large upload parsed + over-cap 413 proven against an isolated temp-store HTTP server"
        if live == "REAL" else "reply-completion proven; isolated HTTP legs did not run"))
    print("LIVE-UX CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
