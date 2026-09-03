#!/usr/bin/env python3
"""certify_privacy_receipt_viewer — user-visible privacy receipts.

This cert proves W07's product-facing closure:
  * /privacy and /privacy/receipts.json are wired;
  * the receipt viewer can show turns, egress events, connector policy, and location precision;
  * weather defaults to coarse coordinate egress for named users, exact only when selected,
    and off blocks before any socket;
  * connector receipt policy is default-deny, receipt-required, and never stores raw payloads;
  * no prompt text, API keys, raw URLs, or query tokens persist in receipt files.
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
    def __init__(self, payload: dict, url: str):
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


def main() -> int:
    fails: list[str] = []

    def ck(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PRIVACY RECEIPT VIEWER — flight recorder + coarse location")
    print("=" * 76)
    t0 = time.perf_counter()

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)
    name = "PrivacyViewerCert"
    turn_id = "turn_2026_06_22_privacy_viewer"
    secret_prompt = "PRIVATE_PROMPT_SHOULD_NOT_RENDER_IN_PRIVACY_VIEWER"
    secret_key = "sk-viewer-secret"
    secret_query = "viewer_token_should_not_persist"

    with tempfile.TemporaryDirectory(prefix="privacy-viewer-cert-") as td:
        from anima import caps, context_gather, privacy_receipts as pr
        import urllib.request as _ureq

        old_pr_store = pr.STORE
        old_caps_store = caps.STORE
        old_urlopen = _ureq.urlopen
        old_zero = os.environ.get("ANIMA_ZERO_EGRESS")
        pr.STORE = Path(td)
        caps.STORE = Path(td)
        opened: list[str] = []

        def fake_urlopen(req, timeout=None):
            url = getattr(req, "full_url", req)
            opened.append(str(url))
            return _Resp({
                "current": {"temperature_2m": 71.0, "weather_code": 2},
                "daily": {"temperature_2m_max": [79.0], "temperature_2m_min": [63.0]},
            }, str(url))

        try:
            _ureq.urlopen = fake_urlopen

            ck("A1: location precision defaults to coarse for a named user",
               caps.load(name).get("location_precision") == "coarse"
               and pr.location_precision(name) == "coarse")

            wx = context_gather.weather(45.5231, -122.6765, name=name, turn_id=turn_id)
            ck("A2: coarse weather lookup succeeds through fake network",
               wx.ok is True and bool(opened))
            ck("A3: default coarse mode rounds before egress",
               "latitude=45.5000" in opened[-1] and "longitude=-122.7000" in opened[-1])

            caps.save(name, {"location_precision": "exact"})
            wx2 = context_gather.weather(45.5231, -122.6765, name=name, turn_id=turn_id + "x")
            ck("A4: exact mode is explicit and uses four decimal places",
               wx2.ok is True and "latitude=45.5231" in opened[-1]
               and "longitude=-122.6765" in opened[-1])

            before = len(opened)
            caps.save(name, {"location_precision": "off"})
            wx3 = context_gather.weather(45.5231, -122.6765, name=name, turn_id=turn_id + "o")
            ck("A5: off mode blocks weather before opening a socket",
               wx3.ok is False and len(opened) == before and "blocked weather" in wx3.note)

            pr.record_turn(
                name, turn_id=turn_id, route_model="local", backend="llama3.2",
                cloud_available=True, cloud_selected=False, facts_selected=2,
                facts_sent_to_model=True, facts_withheld_from_model=False,
                memory_ids=["m1"], route_reason="local sufficient")
            pr.record_turn(
                name, turn_id=turn_id + "c", route_model="cloud:openai",
                backend="openai:gpt-test", cloud_available=True, cloud_selected=True,
                facts_selected=2, facts_sent_to_model=False,
                facts_withheld_from_model=True,
                memory_ids=["m2"], route_reason="private facts withheld")
            pr.record_connector_egress(
                name, connector="gmail", action="draft_reply", decision="blocked",
                purpose="user has not enabled the Gmail connector",
                target=f"https://mail.google.com/mail/u/0/?token={secret_query}",
                turn_id=turn_id,
                metadata={
                    "api_key": secret_key,
                    "message": secret_prompt,
                    "recipient_domain": "example.com",
                    "raw_body": "do not store this",
                },
            )

            try:
                pr.record_connector_egress(
                    name, connector="", action="draft", decision="completed",
                    purpose="", target="https://example.com")
                missing_refused = False
            except ValueError:
                missing_refused = True
            ck("B1: connector receipts require connector/action/decision/purpose",
               missing_refused)

            view = pr.receipt_history(name, limit=50)
            ck("C1: receipt history exposes summary, location, connector policy, and events",
               view["ok"] is True and view["summary"]["turn_receipts"] >= 2
               and view["location"]["precision"] == "off"
               and view["connector_policy"]["receipt_required"] is True
               and len(view["events"]) >= 3)
            ck("C2: connector feed filter returns only connector events",
               all(str(e.get("egress_kind", "")).startswith("connector:")
                   for e in pr.receipt_history(name, kind="connectors")["events"]))
            ck("C3: blocked filter includes blocked weather/connector rows",
               view["summary"]["blocked_egress"] >= 2
               and all(e.get("decision") == "blocked"
                       for e in pr.receipt_history(name, kind="blocked")["events"]))
            ck("C4: connector policy is default-deny and raw-payload-free",
               view["connector_policy"]["default"] == "deny_until_enabled"
               and view["connector_policy"]["raw_payloads_allowed"] is False
               and "message" in view["connector_policy"]["denied_metadata_keys"])

            raw = "\n".join(p.read_text(errors="ignore") for p in Path(td).rglob("*.jsonl"))
            ck("D1: receipt files do not persist prompt text, API keys, query tokens, or raw URL paths",
               secret_prompt not in raw and secret_key not in raw and secret_query not in raw
               and "/mail/u/0" not in raw)
            ck("D2: egress targets are scheme+host only",
               all("/v1/forecast" not in e.get("target", "") and "?" not in e.get("target", "")
                   for e in pr.egress_events(name)))
        finally:
            _ureq.urlopen = old_urlopen
            pr.STORE = old_pr_store
            caps.STORE = old_caps_store
            if old_zero is None:
                os.environ.pop("ANIMA_ZERO_EGRESS", None)
            else:
                os.environ["ANIMA_ZERO_EGRESS"] = old_zero

    server_src = (ROOT / "anima" / "server.py").read_text(encoding="utf-8")
    idx_src = (ROOT / "anima" / "web" / "index.html").read_text(encoding="utf-8")
    privacy_html = (ROOT / "anima" / "web" / "privacy.html").read_text(encoding="utf-8")
    caps_src = (ROOT / "anima" / "caps.py").read_text(encoding="utf-8")
    cg_src = (ROOT / "anima" / "context_gather.py").read_text(encoding="utf-8")
    pr_src = (ROOT / "anima" / "privacy_receipts.py").read_text(encoding="utf-8")

    ck("E1: /privacy shell and /privacy/receipts.json data route are wired",
       '"/privacy"' in server_src and '"/privacy/receipts.json"' in server_src
       and "Privacy Flight Recorder" in privacy_html)
    ck("E2: main shell links privacy viewer and exposes location precision enum",
       'href="/privacy"' in idx_src and 'data-enum="location_precision"' in idx_src)
    ck("E3: viewer pairs query keys into HttpOnly auth and never stores auth secrets",
       "/auth/pair" in privacy_html and "localStorage.setItem" not in privacy_html
       and "anima_token" in privacy_html and "anima_sess" in privacy_html)
    ck("E4: caps/weather/receipt modules contain the certified hooks",
       '"location_precision"' in caps_src
       and "prepare_location_for_egress" in cg_src
       and "record_connector_egress" in pr_src
       and "receipt_history" in pr_src)

    fp_after = _footprint(real_anima)
    ck("F1: real .anima is byte-identical after the cert",
       fp_before == fp_after)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_privacy_receipt_viewer", "green" if green else "red",
                files_observed=["anima/privacy_receipts.py", "anima/context_gather.py",
                                "anima/caps.py", "anima/server.py",
                                "anima/web/privacy.html", "anima/web/index.html"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nPRIVACY RECEIPT VIEWER CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
