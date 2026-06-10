"""host.profile — detect the host, select the runtime profile, persist the contract.

Policy (Apple Silicon, by unified memory):
    < 16 GB  -> Minimal
      16 GB  -> Portable   (constrained)
      24 GB  -> Balanced
      36 GB+ -> Performance
      64 GB+ -> Ultra

The contract is written to reports/host_runtime_profile.{json,md}. Manual overrides are honoured
AND logged — never silent. The UI may only claim what enforcement.py actually enforces.
"""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS = ROOT / "reports"
CONTRACT_JSON = REPORTS / "host_runtime_profile.json"

PROFILES = ("Minimal", "Portable", "Balanced", "Performance", "Ultra")

# per-profile budgets + policies — the single source the runtime enforces against
BUDGETS = {
    "Minimal": dict(context_budget=2048, memory_retrieval_budget=10, source_retrieval_budget=2,
                    max_upload_mb=25, max_intake_job_mb=50, voice_mode="disabled",
                    ears_mode="disabled", background_job_policy="defer-all",
                    cert_policy="light-only", diamond_policy="manual-only",
                    knowledge_pack_policy="disabled"),
    "Portable": dict(context_budget=4096, memory_retrieval_budget=20, source_retrieval_budget=4,
                     max_upload_mb=50, max_intake_job_mb=100, voice_mode="optional",
                     ears_mode="optional", background_job_policy="defer-heavy",
                     cert_policy="defer-heavy", diamond_policy="manual-only",
                     knowledge_pack_policy="defer-builds"),
    "Balanced": dict(context_budget=8192, memory_retrieval_budget=40, source_retrieval_budget=6,
                     max_upload_mb=200, max_intake_job_mb=500, voice_mode="benchmark",
                     ears_mode="enabled", background_job_policy="async-bounded",
                     cert_policy="normal", diamond_policy="allowed",
                     knowledge_pack_policy="bounded-builds"),
    "Performance": dict(context_budget=16384, memory_retrieval_budget=80,
                        source_retrieval_budget=10, max_upload_mb=1024, max_intake_job_mb=2048,
                        voice_mode="enabled", ears_mode="enabled",
                        background_job_policy="allowed", cert_policy="normal",
                        diamond_policy="allowed", knowledge_pack_policy="allowed"),
    "Ultra": dict(context_budget=32768, memory_retrieval_budget=160,
                  source_retrieval_budget=16, max_upload_mb=4096, max_intake_job_mb=8192,
                  voice_mode="enabled", ears_mode="enabled", background_job_policy="allowed",
                  cert_policy="normal", diamond_policy="allowed",
                  knowledge_pack_policy="allowed"),
}


def select_profile(memory_gb: float) -> str:
    """The recommended profile for an Apple Silicon host with this much unified memory. Pure."""
    if memory_gb >= 64:
        return "Ultra"
    if memory_gb >= 36:
        return "Performance"
    if memory_gb >= 24:
        return "Balanced"
    if memory_gb >= 16:
        return "Portable"
    return "Minimal"


_DOWNGRADE = {"Ultra": "Performance", "Performance": "Balanced", "Balanced": "Portable",
              "Portable": "Minimal", "Minimal": "Minimal"}


def select_with_benchmark(memory_gb: float, *, simple_chat_ms: float | None = None,
                          host_pressure: str = "normal", disk_free_gb: float | None = None) -> dict:
    """The memory-based recommendation, then DOWNGRADED by measured reality: slow simple chat,
    high host pressure, or low disk each step the profile down. Final profile is capability-driven,
    not memory alone. Returns {recommended, selected, reasons}."""
    rec = select_profile(memory_gb)
    selected = rec
    reasons = []
    # slow simple chat -> down a step (budgets per profile; >6s simple chat is a clear miss)
    if simple_chat_ms is not None and simple_chat_ms > 6000:
        selected = _DOWNGRADE[selected]
        reasons.append("simple-chat latency %dms > 6000ms -> downgraded" % simple_chat_ms)
    if host_pressure == "high":
        selected = _DOWNGRADE[selected]
        reasons.append("host pressure high -> downgraded")
    if disk_free_gb is not None and disk_free_gb < 10:
        selected = _DOWNGRADE[selected]
        reasons.append("low disk (%dGB) -> downgraded" % disk_free_gb)
    if not reasons:
        reasons.append("benchmarks within budget -> recommended profile holds")
    return {"recommended": rec, "selected": selected, "reasons": reasons}


def detect() -> dict:
    """Measured host facts — never assumed."""
    chip, mem_gb = "", 0.0
    try:
        chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True,
                              text=True, timeout=10).stdout.strip()
        mem_gb = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                                    text=True, timeout=10).stdout.strip()) / (1024 ** 3)
    except Exception:
        pass
    try:
        disk_free_gb = shutil.disk_usage(str(Path.home())).free / (1024 ** 3)
    except Exception:
        disk_free_gb = 0.0
    from anima.verification.cert_result import host_id as _hid
    return {"host_id": _hid(), "hostname": platform.node(), "chip": chip,
            "memory_gb": round(mem_gb), "disk_free_gb": round(disk_free_gb)}


def _default_models() -> dict:
    return {"default_model": "hf.co/bartowski/L3-8B-Stheno-v3.2-GGUF",
            "fallback_model": "qwen2.5:7b-instruct"}


def build_contract(*, override_profile: str | None = None, override_by: str = "") -> dict:
    """Detect + select + persist. An override is applied AND logged in manual_overrides."""
    host = detect()
    recommended = select_profile(host["memory_gb"])
    prior = load()
    overrides = list((prior or {}).get("manual_overrides") or [])
    selected = recommended
    if override_profile and override_profile in PROFILES:
        selected = override_profile
        overrides.append({"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                          "by": override_by or "user",
                          "from": recommended, "to": override_profile,
                          "note": "manual override — logged, never silent"})
    elif prior and prior.get("manual_overrides"):
        # an earlier override sticks until cleared, and stays visible
        last = prior["manual_overrides"][-1]
        if last.get("to") in PROFILES and not last.get("cleared"):
            selected = last["to"]
    contract = {
        **host,
        "selected_profile": selected,
        "recommended_profile": recommended,
        **_default_models(),
        **BUDGETS[selected],
        "manual_overrides": overrides,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "enforcement_seams": {
            "max_upload_mb": "anima/server.py:_intake_plan (host-profile pre-flight refusal)",
            "max_intake_job_mb": "anima/server.py:_intake_plan (host-profile pre-flight refusal)",
            "background_job_policy": "anima/host/enforcement.py:allow_heavy_job (defer verdicts)",
            "voice_mode": "anima/host/enforcement.py:voice_allowed (benchmark-gated on Balanced)",
            "knowledge_pack_policy": "anima/host/enforcement.py:allow_pack_build",
            "cert_policy": "anima/host/enforcement.py:allow_heavy_job(kind='cert')",
            "diamond_policy": "anima/host/enforcement.py:allow_heavy_job(kind='diamond')",
        },
    }
    REPORTS.mkdir(exist_ok=True)
    CONTRACT_JSON.write_text(json.dumps(contract, indent=1, ensure_ascii=False))
    md = ["# Host runtime profile — %s" % contract["hostname"], "",
          "**%s** (%s, %d GB unified memory, %d GB free disk)" % (
              contract["selected_profile"], contract["chip"], contract["memory_gb"],
              contract["disk_free_gb"]),
          "", "Recommended: %s · host_id `%s` · generated %s" % (
              recommended, contract["host_id"], contract["generated_at"]), "",
          "| budget | value |", "|---|---|"]
    for k in ("context_budget", "memory_retrieval_budget", "source_retrieval_budget",
              "max_upload_mb", "max_intake_job_mb", "voice_mode", "ears_mode",
              "background_job_policy", "cert_policy", "diamond_policy",
              "knowledge_pack_policy"):
        md.append("| %s | %s |" % (k, contract[k]))
    if overrides:
        md += ["", "## Manual overrides (logged)", ""]
        md += ["- %(at)s %(by)s: %(from)s -> %(to)s" % o for o in overrides]
    (REPORTS / "host_runtime_profile.md").write_text("\n".join(md) + "\n")
    return contract


def load() -> dict | None:
    try:
        return json.loads(CONTRACT_JSON.read_text())
    except Exception:
        return None


def current() -> dict:
    """The active contract, building it on first use."""
    return load() or build_contract()


if __name__ == "__main__":
    c = build_contract()
    print(json.dumps({k: c[k] for k in ("hostname", "chip", "memory_gb", "selected_profile",
                                        "recommended_profile")}, indent=1))
