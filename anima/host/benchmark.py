"""host.benchmark — measured capability, never assumed.

tts_latency_ms(): one real timed /tts synth against the live server (None when unmeasurable —
an unmeasured benchmark NEVER passes a benchmark-gated capability).
brain_tok_s(): the brain's last measured token rate from the live turn telemetry.
"""
from __future__ import annotations

import json
import time
import urllib.request

BASE = "http://127.0.0.1:8765"


def tts_latency_ms(timeout: float = 20.0) -> float | None:
    try:
        body = json.dumps({"text": "Benchmark sentence for the host profile."}).encode()
        req = urllib.request.Request(BASE + "/tts", data=body,
                                     headers={"Content-Type": "application/json"})
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
        return (time.perf_counter() - t0) * 1000.0
    except Exception:
        return None


def brain_tok_s(timeout: float = 60.0) -> float | None:
    try:
        body = json.dumps({"text": "Reply with one short sentence."}).encode()
        req = urllib.request.Request(BASE + "/say", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return float(json.loads(r.read()).get("tok_s") or 0) or None
    except Exception:
        return None
