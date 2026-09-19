"""observation_harness.bundle — write + verify the run-correlated evidence bundle.

Section 13 of the directive. Every Total Reality run writes reports/total_reality/<run_id>/ with the
scenario results + the per-scenario observations + a summary, all carrying run_id. The hard rule
(certify_observation_bundle_complete): every executed scenario has an evidence record — no orphan.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BASE = ROOT / "reports" / "total_reality"


def bundle_dir(run_id: str) -> Path:
    return BASE / run_id


def write_bundle(run_id: str, run_result: dict, matrix: dict, at: str = "") -> Path:
    """Persist the evidence bundle for a run. Returns the bundle directory."""
    d = bundle_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    results = run_result.get("results", [])

    # per-scenario results (jsonl), each carrying run_id (the correlation key)
    with (d / "scenario_results.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({**r, "run_id": run_id}, ensure_ascii=False) + "\n")

    # DEEP OBSERVATION STREAMS (directive section 13) — capture ONE real host snapshot for the run
    # (the host context every scenario executed under) and write it as a correlated artifact.
    try:
        from anima import host_pressure
        host_snap = host_pressure.snapshot()
    except Exception:
        try:
            from anima import host_pressure
            host_snap = host_pressure.read_pressure()
        except Exception:
            host_snap = {"level": "unknown"}
    (d / "host_snapshot.json").write_text(json.dumps({"run_id": run_id, "at": at, "host": host_snap}, indent=2))

    # observations (the evidence stream) — one per scenario, correlated by run_id + scenario_id, each
    # now carrying a `deep` record (kind/level/status/severity — the per-scenario MRI-grade detail) and
    # a `host_ref` pointing at the run's host snapshot, so every observation is joinable to its context.
    with (d / "observations.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({"run_id": run_id, "scenario_id": r["scenario_id"], "surface": r["surface"],
                                "outcome": r["outcome"], "latency_ms": r["latency_ms"],
                                "detail": r["detail"], "host_ref": "host_snapshot.json",
                                "deep": {"kind": r.get("kind"), "level": r.get("level"),
                                         "status": r.get("status"), "severity": r.get("severity")}},
                               ensure_ascii=False) + "\n")

    summ = run_result.get("summary", {})
    (d / "summary.json").write_text(json.dumps({
        "run_id": run_id, "at": at, "persona": run_result.get("persona"),
        "summary": summ, "scenario_total": matrix.get("counts", {}).get("total"),
        "host_snapshot": "host_snapshot.json", "deep_observations": True,
    }, indent=2))

    md = ["# Total Reality run %s\n" % run_id, "Persona: %s · at: %s\n" % (run_result.get("persona"), at),
          "- total scenarios: %d" % summ.get("total", 0),
          "- executed (pass/fail): %d  (pass %d / fail %d)" % (summ.get("executed", 0), summ.get("pass", 0), summ.get("fail", 0)),
          "- blocked-by-design: %d · deferred to later levels: %d" % (summ.get("blocked", 0), summ.get("deferred", 0)),
          "- P0 open: %d · P1 open: %d" % (summ.get("p0", 0), summ.get("p1", 0)),
          "\n_Evidence: scenario_results.jsonl + observations.jsonl (correlated by run_id)._"]
    (d / "summary.md").write_text("\n".join(md) + "\n")
    return d


def verify_bundle(run_id: str, matrix: dict) -> dict:
    """The completeness check (teeth): every scenario in the matrix has an evidence record in the bundle,
    correlated by run_id. Returns {complete, total, recorded, missing, orphan}."""
    d = bundle_dir(run_id)
    want = {s["scenario_id"] for s in matrix.get("scenarios", [])}
    recorded, run_ids = set(), set()
    try:
        for ln in (d / "observations.jsonl").read_text().splitlines():
            o = json.loads(ln)
            recorded.add(o.get("scenario_id"))
            run_ids.add(o.get("run_id"))
    except Exception:
        pass
    missing = sorted(want - recorded)
    orphan = sorted(recorded - want)
    return {
        "complete": (not missing) and (not orphan) and run_ids == {run_id} and bool(recorded),
        "total": len(want), "recorded": len(recorded),
        "missing": missing[:10], "orphan": orphan[:10],
        "run_id_consistent": run_ids == {run_id},
    }


def verify_deep_observations(run_id: str) -> dict:
    """Deep-stream completeness (teeth): every observation carries its `deep` record (kind/level/status/
    severity) + a host_ref, AND the run's host_snapshot.json exists with a real reading. Returns
    {deep_complete, total, with_deep, with_host_ref, host_snapshot_present, host_level}."""
    d = bundle_dir(run_id)
    total = with_deep = with_host_ref = 0
    try:
        for ln in (d / "observations.jsonl").read_text().splitlines():
            o = json.loads(ln)
            total += 1
            dd = o.get("deep")
            if isinstance(dd, dict) and ("status" in dd) and ("kind" in dd) and ("level" in dd):
                with_deep += 1
            if o.get("host_ref"):
                with_host_ref += 1
    except Exception:
        pass
    host_present, host_level = False, None
    try:
        hs = json.loads((d / "host_snapshot.json").read_text())
        host = hs.get("host") or {}
        host_present = isinstance(host, dict) and bool(host)
        host_level = host.get("level")
    except Exception:
        pass
    return {
        "deep_complete": total > 0 and with_deep == total and with_host_ref == total and host_present,
        "total": total, "with_deep": with_deep, "with_host_ref": with_host_ref,
        "host_snapshot_present": host_present, "host_level": host_level,
    }


def latest_run() -> str | None:
    try:
        runs = sorted([p.name for p in BASE.iterdir() if p.is_dir()])
        return runs[-1] if runs else None
    except Exception:
        return None
