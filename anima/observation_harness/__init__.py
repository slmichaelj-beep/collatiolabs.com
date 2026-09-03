"""observation_harness — records EVERYTHING a Total Reality run produces, correlated by run_id.

bundle.py writes the evidence bundle (summary + per-scenario results + observations) under
reports/total_reality/<run_id>/. The hard rule: no scenario without an evidence record; no orphan log.
"""
from . import bundle  # noqa: F401
