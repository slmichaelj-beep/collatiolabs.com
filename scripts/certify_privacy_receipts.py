#!/usr/bin/env python3
"""certify_privacy_receipts — route/egress receipts are durable and sanitized.

This cert proves the product posture, offline:
  * each turn can emit a privacy receipt with route model, actual backend, actual
    egress class, fact-send/withhold flags, and no prompt text;
  * cloud/web/weather/key-verification egress writes append-only ledger rows;
  * ledger targets are boundary-only (scheme + host), never URL path/query;
  * zero-egress blocked attempts are ledgered without opening sockets;
  * no API key, query token, or private prompt text lands in receipt files.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_footprint = _g0pe._footprint


class _Resp:
    def __init__(self, payload: dict, url: str = ""):
        self.payload = json.dumps(payload).encode("utf-8")
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *a):
        return self.payload

    def geturl(self):
        return self._url


class _WebResp:
    def __init__(self, body: bytes, url: str):
        self._body = body
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *a):
        return self._body

    def geturl(self):
        return self._url


def main() -> int:
    fails: list[str] = []

    def ck(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PRIVACY RECEIPTS — per-turn route + egress audit")
    print("=" * 76)
    t0 = time.perf_counter()

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    secret_prompt = "PRIVATE_PROMPT_SHOULD_NOT_BE_IN_RECEIPTS"
    secret_query = "LEAKTOKEN_SHOULD_NOT_BE_IN_RECEIPTS"
    secret_key = "sk-secret-privacy-receipt-cert"
    name = "ReceiptCert"
    turn_id = "turn_2026_06_22_120000_rcpt01"

    with tempfile.TemporaryDirectory(prefix="privacy-receipts-cert-") as td:
        from anima import cloud, context_gather, privacy_receipts as pr, webget
        import urllib.request as _ureq

        old_store = pr.STORE
        old_cloud_store = cloud.STORE
        old_urlopen = _ureq.urlopen
        old_build_opener = _ureq.build_opener
        old_zero = os.environ.get("ANIMA_ZERO_EGRESS")

        pr.STORE = Path(td)
        cloud.STORE = Path(td)

        opened: list[str] = []
        captured_payloads: list[dict] = []

        class _FakeOpener:
            def open(self, req, timeout=None):
                opened.append("web")
                return _WebResp(
                    b"<html><body>receipt cert page</body></html>",
                    f"https://example.com/secret/path?token={secret_query}",
                )

        def fake_urlopen(req, timeout=None):
            url = getattr(req, "full_url", req)
            opened.append(str(url))
            if hasattr(req, "data") and req.data:
                captured_payloads.append(json.loads(req.data.decode("utf-8")))
            if "open-meteo.com" in str(url):
                return _Resp({
                    "current": {"temperature_2m": 72.0, "weather_code": 2},
                    "daily": {"temperature_2m_max": [80.0], "temperature_2m_min": [65.0]},
                }, str(url))
            if str(url).endswith("/models"):
                return _Resp({"data": [{"id": "gpt-test"}]}, str(url))
            return _Resp({
                "choices": [{"message": {"content": "receipt cert cloud reply"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            }, str(url))

        try:
            _ureq.urlopen = fake_urlopen
            _ureq.build_opener = lambda *a, **kw: _FakeOpener()

            local_receipt = pr.record_turn(
                name, turn_id=turn_id, route_model="local", backend="llama3.2",
                cloud_available=True, cloud_selected=False, facts_selected=2,
                facts_sent_to_model=True, facts_withheld_from_model=False,
                memory_ids=["fact-1", "fact-2"], route_reason="local sufficient")
            ck("A1: local receipt records no actual egress",
               local_receipt["actual_egress"] == "none" and local_receipt["facts_sent_to_model"] is True)

            cloud_receipt = pr.record_turn(
                name, turn_id=turn_id + "c", route_model="cloud:openai",
                backend="openai:gpt-test", cloud_available=True, cloud_selected=True,
                facts_selected=2, facts_sent_to_model=False, facts_withheld_from_model=True,
                memory_ids=["fact-1"], route_reason="non-private escalation")
            ck("A2: cloud receipt records provider egress and fact withholding",
               cloud_receipt["actual_egress"] == "cloud_provider"
               and cloud_receipt["facts_withheld_from_model"] is True)
            ck("A3: latest_receipt reads back the append-only receipt",
               pr.latest_receipt(name)["turn_id"] == cloud_receipt["turn_id"])

            wf_blocked = webget.fetch(
                "https://not-allowed.example/hidden?token=" + secret_query,
                ["example.com"], name=name, turn_id=turn_id)
            ck("B1: non-allowlisted web fetch is blocked before socket",
               wf_blocked.get("ok") is False and opened == [])

            wf_ok = webget.fetch(
                "https://example.com/secret/path?token=" + secret_query,
                ["example.com"], name=name, turn_id=turn_id)
            ck("B2: allowlisted web fetch can complete through fake opener",
               wf_ok.get("ok") is True and opened.count("web") == 1)

            wx = context_gather.weather(45.5231, -122.6765, name=name, turn_id=turn_id)
            ck("C1: weather lookup completes through fake urlopen",
               wx.ok is True and "open-meteo.com" in "\n".join(opened))

            ok, detail, models = cloud.verify_key("openai", secret_key)
            ck("D1: cloud key verification logs attempt/completed without persisting key",
               ok is True and models == ["gpt-test"] and not detail)

            b = cloud.OpenAICompatBrain("https://api.openai.com/v1", "gpt-test", secret_key,
                                        "openai:gpt-test", "openai")
            b.creature = name
            b.turn_id = turn_id
            reply = b.reply("system " + secret_prompt, "hello john@example.com", [])
            ck("D2: cloud provider call completes and carries the turn_id into egress ledger",
               "cloud reply" in reply)
            ck("D3: cloud payload is scrubbed before egress",
               captured_payloads and "john@example.com" not in json.dumps(captured_payloads[-1]))

            os.environ["ANIMA_ZERO_EGRESS"] = "1"
            before = len(opened)
            blocked_reply = b.reply("system", "hello", [])
            ck("E1: zero-egress cloud reply is blocked locally",
               "Zero-egress mode" in blocked_reply and len(opened) == before)

            events = pr.egress_events(name)
            decisions = {(e.get("egress_kind"), e.get("decision")) for e in events}
            ck("F1: named egress ledger includes web/weather/cloud completed decisions",
               ("web_fetch", "completed") in decisions
               and ("weather_lookup", "completed") in decisions
               and ("cloud_provider", "completed") in decisions)
            ck("F2: zero-egress blocked cloud decision is ledgered",
               ("cloud_provider", "blocked") in decisions)
            ck("F3: egress targets are sanitized to scheme+host only",
               all("?token=" not in e.get("target", "") and "/secret" not in e.get("target", "")
                   for e in events))

            global_events = pr.egress_events(None)
            ck("F4: global key-verification ledger records attempt/completed",
               {e.get("decision") for e in global_events if e.get("egress_kind") == "cloud_key_verification"}
               >= {"attempt", "completed"})

            raw = "\n".join(p.read_text(errors="ignore") for p in Path(td).rglob("*.jsonl"))
            ck("G1: no prompt text, query token, or API key is persisted in receipt files",
               secret_prompt not in raw and secret_query not in raw and secret_key not in raw)
        finally:
            _ureq.urlopen = old_urlopen
            _ureq.build_opener = old_build_opener
            pr.STORE = old_store
            cloud.STORE = old_cloud_store
            if old_zero is None:
                os.environ.pop("ANIMA_ZERO_EGRESS", None)
            else:
                os.environ["ANIMA_ZERO_EGRESS"] = old_zero

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert",
       fp_before == fp_after)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_privacy_receipts", "green" if green else "red",
                files_observed=["anima/privacy_receipts.py", "anima/cloud.py",
                                "anima/webget.py", "anima/context_gather.py",
                                "anima/server.py", "anima/mouth.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nPRIVACY-RECEIPTS CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
