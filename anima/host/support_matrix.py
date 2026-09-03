"""host.support_matrix — capability-certified Mac support, NOT chip-generation.

A Mac is supported iff it passes Vera Host Fit certification for at least Portable. Memory class
gives an initial recommendation only; the final profile is determined by Host Fit. This module
writes reports/apple_support_matrix.{json,md} and docs/system_requirements.md, all consistent with
the runtime policy.
"""
from __future__ import annotations

from pathlib import Path

from . import profile as _profile

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS = ROOT / "reports"
DOCS = ROOT / "docs"

MATRIX = [
    {"class": "< 16GB Apple Silicon", "likely": "Minimal/Unsupported",
     "note": "below the Portable floor unless benchmarks somehow pass"},
    {"class": "16GB Apple Silicon", "likely": "Portable",
     "note": "constrained; large jobs deferred — if benchmarks pass"},
    {"class": "24GB Apple Silicon", "likely": "Balanced", "note": "daily Vera — if benchmarks pass"},
    {"class": "36GB+ Apple Silicon", "likely": "Performance",
     "note": "stronger local Vera — if benchmarks pass"},
    {"class": "64GB+ Apple Silicon", "likely": "Ultra", "note": "large local work — if benchmarks pass"},
    {"class": "Intel Mac", "likely": "Unsupported", "note": "not supported (no Apple Silicon)"},
]

DOCTRINE = ("Vera supports Macs that pass Vera Host Fit certification. Capability decides, not chip "
            "generation. Memory class is an initial recommendation; the final profile comes from "
            "Host Fit (detection + dependency + benchmark).")


def build(*, write_docs: bool = True) -> dict:
    rec = {"report": "apple_support_matrix", "doctrine": DOCTRINE, "matrix": MATRIX,
           "profiles": list(_profile.PROFILES),
           "minimum_supported": "Portable-certified", "recommended": "Balanced-certified",
           "best": "Performance-certified", "ultra": "Ultra-certified"}
    REPORTS.mkdir(exist_ok=True)
    import json
    (REPORTS / "apple_support_matrix.json").write_text(json.dumps(rec, indent=1))
    md = ["# Apple support matrix — capability-certified", "", DOCTRINE, "",
          "| Mac class | likely profile | note |", "|---|---|---|"]
    md += ["| %s | %s | %s |" % (m["class"], m["likely"], m["note"]) for m in MATRIX]
    (REPORTS / "apple_support_matrix.md").write_text("\n".join(md) + "\n")
    if write_docs:
        DOCS.mkdir(exist_ok=True)
        doc = ["# System requirements", "", DOCTRINE, "",
               "## Support tiers (by Host Fit certification)",
               "- **Minimum supported experience:** a Portable-certified Mac.",
               "- **Recommended experience:** a Balanced-certified Mac.",
               "- **Best experience:** a Performance-certified Mac.",
               "- **Ultra experience:** an Ultra-certified Mac.", "",
               "## Initial guidance (examples, not hard requirements)",
               "- 16GB-class Apple Silicon Macs may qualify for Portable if benchmarks pass.",
               "- 24GB-class Apple Silicon Macs may qualify for Balanced if benchmarks pass.",
               "- 36GB+-class Apple Silicon Macs may qualify for Performance if benchmarks pass.",
               "- 64GB+-class Macs may qualify for Ultra if benchmarks pass.", "",
               "The final profile is determined by Vera Host Fit certification on YOUR Mac, "
               "not by chip generation alone."]
        (DOCS / "system_requirements.md").write_text("\n".join(doc) + "\n")
    return rec
