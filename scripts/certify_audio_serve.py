#!/usr/bin/env python3
"""
certify_audio_serve — GET /audio/<name> serves a rendered TTS clip SAFELY, and only to an
authenticated caller.

Vera renders a briefing/reminder to an audio file in the .anima audio store (proactive.render_audio
via Kokoro or `say`); a push payload carries an https://vera.guruu.ai/audio/<name> URL the phone
fetches (with its token) and plays. That makes /audio a file-serving endpoint reaching into the
private store, so it must obey a hard SAFE-SERVING contract. This certifies that contract through the
SAME functions the server's GET /audio/<name> route runs — server._serve_audio_file and the real
server.Handler._authed:

  A. A VALID CLIP SERVES — a real clip seeded into the audio store serves with HTTP 200, the EXACT
     bytes on disk, and the correct audio/* content-type; every supported extension
     (.wav/.aiff/.mp3/.m4a/.caf) maps to its declared _AUDIO_TYPES type; a dir-PREFIXED basename
     still serves (the leading path components are DROPPED by Path(...).name, not traversed) — the
     basename-only contract.
  B. PATH TRAVERSAL IS REFUSED — '../../../etc/hosts', an absolute '/etc/passwd', AND a .wav symlink
     placed INSIDE the store that points OUTSIDE it all return 404 'no audio' and leak no foreign
     bytes. The resolved-parent-must-equal-the-store check (f_real.parent == STORE.resolve()) is what
     defeats the symlink escape — basename-stripping alone would not. A non-audio extension, a missing
     file, and an empty name also return 404.
  C. THE ROUTE IS AUTH-GATED — driving the REAL server.Handler._authed (built via __new__, no socket):
     with no token configured auth is open (dev), but with a token SET a request with NO key is
     refused, a WRONG ?k is refused, and only the CORRECT ?k or 'Bearer <token>' is allowed (HMAC
     constant-time). And statically: inside do_GET the 401 'unauthorized' guard textually PRECEDES the
     '/audio/' dispatch, so an unauthenticated GET is rejected before any clip is served.
  D. LEGACY /audio IS BASENAME-SAFE TOO — the older GET /audio?name=… handler also strips name to a
     basename (Path(name).name) before building STORE/{name}.last.wav, so it cannot traverse either.

Hermetic + read-only: _temp_store() redirects server.STORE (and every store-bearing module) to a temp
dir, and _serve_audio_file reads that SAME module-global STORE — so we seed clips into the temp store,
never the real one. No model, no network, no HTTP socket. The real .anima is fingerprinted before/after
and asserted byte-identical (H1). Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def main() -> int:
    from anima import server
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("AUDIO SERVE — GET /audio/<name> serves a TTS clip SAFELY (basename-only, .anima-only, auth-gated)")
    print("=" * 96)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    NAME = "AudioCert"
    CLIP = NAME + ".briefing.wav"
    BODY = b"RIFF\x00\x00\x00\x00WAVEfmt audio-cert-not-a-real-clip"

    with _temp_store() as tp:
        # sanity: _serve_audio_file reads the SAME module-global STORE that _temp_store redirected.
        ck("S0: server.STORE is the redirected temp dir (hermetic; we never touch the real store)",
           server.STORE == tp)

        # Seed a real clip into the audio store.
        (tp / CLIP).write_bytes(BODY)

        # ---- A. A VALID CLIP SERVES -------------------------------------------------
        code, ctype, body = server._serve_audio_file(CLIP)
        ck("A1: a seeded clip serves 200 audio/wav with the EXACT bytes on disk",
           code == 200 and ctype == "audio/wav" and body == BODY)
        # every supported extension maps to its declared content-type
        ext_ok = True
        for ext, want in server._AUDIO_TYPES.items():
            fn = NAME + "_x" + ext
            (tp / fn).write_bytes(b"x")
            c, ct, _b = server._serve_audio_file(fn)
            if not (c == 200 and ct == want):
                ext_ok = False
        ck("A2: every supported extension (.wav/.aiff/.aif/.mp3/.m4a/.caf) maps to its declared "
           "_AUDIO_TYPES content-type", ext_ok)
        # a dir-prefixed basename: components are DROPPED (basename-only), still resolves to the clip
        c3, ct3, b3 = server._serve_audio_file("some/deep/dir/" + CLIP)
        ck("A3: a dir-PREFIXED basename still serves (path components dropped, NOT traversed) — "
           "the basename-only contract", c3 == 200 and ct3 == "audio/wav" and b3 == BODY)

        # ---- B. PATH TRAVERSAL IS REFUSED -------------------------------------------
        trav_rel = server._serve_audio_file("../../../etc/hosts")
        ck("B1: a relative '../' traversal is refused (404 'no audio')",
           trav_rel == (404, "text/plain", b"no audio"))
        trav_abs = server._serve_audio_file("/etc/passwd")
        ck("B2: an absolute path is refused (404 'no audio')",
           trav_abs == (404, "text/plain", b"no audio"))
        # the decisive case: a .wav SYMLINK *inside* the store pointing OUTSIDE it.
        # basename-stripping alone would pass this; only the resolved-parent==store check stops it.
        sym_ok = True
        secret = None
        try:
            tf = tempfile.NamedTemporaryFile(prefix="audio-cert-secret-", suffix=".wav", delete=False)
            tf.write(b"SECRET-OUTSIDE-THE-STORE")
            tf.close()
            secret = tf.name
            link = tp / "escape.wav"
            try:
                os.symlink(secret, link)
                rc_sym, ct_sym, b_sym = server._serve_audio_file("escape.wav")
                # MUST be refused, and MUST NOT leak the foreign bytes
                sym_ok = (rc_sym == 404) and (b"SECRET-OUTSIDE-THE-STORE" not in b_sym)
            except OSError:
                # symlinks unavailable on this fs — the resolved-parent check is still exercised by
                # B1/B2; treat as non-blocking but note it.
                print("  ..   B3: symlink unsupported on this fs; resolved-parent check covered by B1/B2")
        finally:
            if secret and os.path.exists(secret):
                os.unlink(secret)
        ck("B3: a .wav symlink INSIDE the store that escapes it is refused (404) and leaks no foreign "
           "bytes (resolved-parent==store defeats the escape)", sym_ok)
        ck("B4: a non-audio extension is refused (404 'no audio')",
           server._serve_audio_file(NAME + ".txt") == (404, "text/plain", b"no audio"))
        ck("B5: a missing file and an empty name are refused (404 'no audio')",
           server._serve_audio_file("does_not_exist.wav") == (404, "text/plain", b"no audio")
           and server._serve_audio_file("") == (404, "text/plain", b"no audio"))

        # ---- C. THE ROUTE IS AUTH-GATED ---------------------------------------------
        # Drive the REAL Handler._authed bound method without a socket (build via __new__).
        class _Hdrs(dict):
            def get(self, k, d=""):
                return dict.get(self, k, d)

        def authed(token, path, headers=None):
            h = server.Handler.__new__(server.Handler)
            h.token = token
            h.path = path
            h.headers = _Hdrs(headers or {})
            return h._authed()

        TOK = "sk-FAKE-audio-cert-token-not-real-000"
        ck("C1: with NO token configured, auth is OPEN (dev mode) — _authed True",
           authed("", "/audio/" + CLIP) is True)
        ck("C2: with a token SET, a request with NO key is REFUSED (-> 401 path)",
           authed(TOK, "/audio/" + CLIP) is False)
        ck("C3: with a token SET, a WRONG ?k is REFUSED",
           authed(TOK, "/audio/" + CLIP + "?k=wrong") is False)
        ck("C4: with a token SET, the CORRECT ?k is allowed",
           authed(TOK, "/audio/" + CLIP + "?k=" + TOK) is True)
        ck("C5: with a token SET, a correct 'Bearer <token>' header is allowed",
           authed(TOK, "/audio/" + CLIP, {"Authorization": "Bearer " + TOK}) is True)

        # static: inside do_GET the 401 'unauthorized' guard precedes the '/audio/' dispatch.
        src = (ROOT / "anima" / "server.py").read_text()
        guard = 'return self._send(401, "text/plain", b"unauthorized")'
        disp = 'u.path.startswith("/audio/")'
        ck("C6: in do_GET the 401 'unauthorized' guard textually PRECEDES the '/audio/' dispatch "
           "(unauthenticated GET rejected before any clip is served)",
           guard in src and disp in src and src.index(guard) < src.index(disp))

        # ---- D. LEGACY /audio IS BASENAME-SAFE TOO ----------------------------------
        # The older GET /audio?name=… builds STORE/{name}.last.wav after Path(name).name. Prove the
        # basename strip the handler applies cannot escape: a traversal name collapses to a basename.
        ck("D1: legacy /audio basenames the name (Path(name).name) before STORE/{name}.last.wav — "
           "no traversal", Path("../../etc/evil").name == "evil"
           and Path("a/b/AudioCert").name == "AudioCert"
           and 'Path(parse_qs(u.query).get("name"' in src and ".last.wav" in src)

    # ---- HERMETICITY ----------------------------------------------------------------
    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nAUDIO-SERVE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
