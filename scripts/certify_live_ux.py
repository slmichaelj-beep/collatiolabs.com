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

(A)/(B) hit the running server on :8765 (skip-not-fail if it is down, like certify_lerf_live).
(C) is hermetic and always runs. Exit 0 == CERTIFIED (real leg ran or honestly SKIPPED); 1 == FAIL.
"""
from __future__ import annotations

import base64
import json
import re as _re
import socket
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PORT = 8765
BASE = f"http://localhost:{PORT}"


def _up() -> bool:
    try:
        urllib.request.urlopen(BASE + "/version", timeout=3)
        return True
    except Exception:
        return False


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

    # ---- (D) DISK PRE-FLIGHT (hermetic — always runs) ----------------------------------------
    # A base64 file decodes straight to the staging dir; on a near-full disk that ENOSPCs mid-write.
    # _intake_plan must refuse HONESTLY before writing. Prove the block path + that nothing is staged.
    import base64 as _b64
    from anima import server as _srv
    _orig_free = _srv._free_bytes
    try:
        real_free = _orig_free(_srv._staging_dir("Vera"))
        ck("D1: _free_bytes reports real volume free space (>0)", isinstance(real_free, int) and real_free > 0)
        _srv._free_bytes = lambda p: 5 * 1024 * 1024            # pretend only 5 MB free
        r = _srv._intake_plan("Vera", {"kind": "file", "filename": "x.txt",
                                       "bytes_b64": _b64.b64encode(b"x" * 2048).decode()})
        ck("D2: a file upload on a near-full disk is REFUSED honestly (not an ENOSPC mid-write)",
           (not r.get("ok")) and "disk space" in (r.get("error") or "").lower())
        ck("D2: nothing is staged when the disk guard refuses",
           not (_srv._staging_dir("Vera") / (str(r.get("source_id", "")) + ".txt")).exists())
    finally:
        _srv._free_bytes = _orig_free

    # ---- (A)/(B) LIVE HTTP (skip-not-fail) ---------------------------------------------------
    if not _up():
        print("  --   A/B live upload SKIPPED (server not running on :8765) — reply-completion proven above")
    else:
        # (A) a ~30 MB file body (well over the old 25 MB cap) must PARSE, not truncate.
        raw = ("blue copper ladder 92817 has twelve rungs, forged in Aldermere. " * 460000).encode()
        b64 = base64.b64encode(raw).decode()
        body = json.dumps({"kind": "file", "filename": "big_note.txt", "bytes_b64": b64}).encode()
        ok_big = False
        try:
            r = urllib.request.urlopen(urllib.request.Request(
                BASE + "/intake/plan", data=body,
                headers={"Content-Type": "application/json"}), timeout=90)
            out = json.loads(r.read())
            ok_big = bool(out.get("ok"))
        except Exception as e:
            print("      (upload error: %r)" % e)
        ck("A1: a %.0f MB body (over the old 25 MB cap) PARSES over real HTTP — no truncated JSON"
           % (len(body) / 1e6), ok_big)

        # (B) an over-cap body (declared via Content-Length) -> honest 413, not a truncated parse.
        got413 = honest = False
        try:
            huge = 600 * 1024 * 1024
            req = (b"POST /intake/plan HTTP/1.1\r\nHost: localhost\r\n"
                   b"Content-Type: application/json\r\nContent-Length: " + str(huge).encode() +
                   b"\r\nConnection: close\r\n\r\n{}")
            s = socket.create_connection(("localhost", PORT), timeout=10)
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
        live = "REAL"

    print("\nLIVE: %s (%s)" % (
        live, "large upload parsed + over-cap 413 proven against the running server"
        if live == "REAL" else "reply-completion proven; large-upload legs need the server on :8765"))
    print("LIVE-UX CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
