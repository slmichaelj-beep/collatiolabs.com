#!/usr/bin/env python3
"""certify_zero_egress_mode — hard switch blocks cloud/web/weather sockets.

Zero-egress mode is a product privacy invariant, not a UI preference. With
``ANIMA_ZERO_EGRESS=1``:
  * cloud provider config is not considered active;
  * cloud brains are unavailable and direct replies refuse without opening sockets;
  * cloud key verification refuses before /models;
  * allow-listed web fetch refuses before opener.open;
  * weather lookup refuses before Open-Meteo urlopen;
  * the public brain config surfaces zero_egress=true.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fails: list[str] = []

    def ck(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("ZERO-EGRESS MODE — cloud/web/weather blocked before sockets")
    print("=" * 76)
    t0 = time.perf_counter()

    old_zero = os.environ.get("ANIMA_ZERO_EGRESS")
    opened: list[str] = []

    with tempfile.TemporaryDirectory(prefix="zero-egress-cert-") as td:
        from anima import cloud, context_gather, privacy_receipts, webget
        import urllib.request as _ureq

        old_store = cloud.STORE
        old_privacy_store = privacy_receipts.STORE
        old_urlopen = _ureq.urlopen
        old_build_opener = _ureq.build_opener
        cloud.STORE = Path(td)
        privacy_receipts.STORE = Path(td)
        os.environ["ANIMA_ZERO_EGRESS"] = "1"

        class _TripwireOpener:
            def open(self, req, timeout=None):
                opened.append("opener.open")
                raise AssertionError("network opener reached under zero-egress")

        def _tripwire_urlopen(*a, **kw):
            opened.append("urlopen")
            raise AssertionError("urlopen reached under zero-egress")

        try:
            _ureq.urlopen = _tripwire_urlopen
            _ureq.build_opener = lambda *a, **kw: _TripwireOpener()

            cloud.save_cfg("openai", "gpt-4o-mini", "fake-key", budget=2.0)
            ck("A1: cloud.is_cloud is false under zero-egress even with provider+key configured",
               cloud.is_cloud() is False)
            ck("A2: build_cloud_brain returns None under zero-egress",
               cloud.build_cloud_brain() is None)
            ck("A3: public brain config surfaces zero_egress=true",
               cloud.public().get("zero_egress") is True)
            ok, detail, models = cloud.verify_key("openai", "fake-key")
            ck("A4: cloud key verification is refused before network",
               ok is False and "zero-egress" in detail and models == [])
            b = cloud.OpenAICompatBrain("https://api.openai.com/v1", "gpt-4o-mini",
                                        "fake-key", "openai:gpt-4o-mini", "openai")
            ck("A5: a direct cloud brain reports unavailable under zero-egress",
               b.available() is False)
            ck("A6: a direct cloud reply refuses locally without socket",
               "Zero-egress mode is on" in b.reply("sys", "hello", []))

            wf = webget.fetch("https://example.com/private", ["example.com"])
            ck("B1: allow-listed web fetch is blocked by zero-egress",
               wf.get("ok") is False and "zero-egress" in wf.get("error", ""))
            wx = context_gather.weather(45.5231, -122.6765)
            ck("C1: weather lookup is blocked by zero-egress",
               wx.ok is False and "zero-egress" in wx.note)
            ck("Z1: no socket/open call was reached in any zero-egress path",
               opened == [])
        finally:
            _ureq.urlopen = old_urlopen
            _ureq.build_opener = old_build_opener
            cloud.STORE = old_store
            privacy_receipts.STORE = old_privacy_store
            if old_zero is None:
                os.environ.pop("ANIMA_ZERO_EGRESS", None)
            else:
                os.environ["ANIMA_ZERO_EGRESS"] = old_zero

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_zero_egress_mode", "green" if green else "red",
                files_observed=["anima/egress.py", "anima/cloud.py",
                                "anima/webget.py", "anima/context_gather.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nZERO-EGRESS-MODE CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
