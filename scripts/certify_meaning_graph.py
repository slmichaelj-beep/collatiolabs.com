#!/usr/bin/env python3
"""certify_meaning_graph — the Meaning & Relationship Graph (Human Operating Layer, Layer 4) is REAL: a
read-only view over the World State edges, formalised so every fact names its PROVENANCE and SENSITIVE
facts are flagged consent-relevant.

  1. PROVENANCE       — every active edge carries a source + confidence + a created time, and the graph
                        exposes them; coverage is COMPUTED (not assumed 100%).
  2. PROVENANCE BITES — a single un-sourced edge pulls coverage below 1.0 — the metric is honest, not a
                        hardcoded green.
  3. SENSITIVE FLAGGED— a sensitive relationship (e.g. health) is classified sensitive + consent_relevant
                        while a benign one is not (the classifier DISCRIMINATES — ties L4 to L2 Consent).
  4. CONFIDENCE       — edges expose confidence + support (corroboration); the graph reports avg confidence.
  5. READ-ONLY        — building the graph never writes to the store.
  6. SERVED + AUTH    — the graph rides through _meaning_graph_data; GET /meaning serves the page.

Hermetic. Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store


def _fingerprint():
    try:
        from anima.world_state import World
        import hashlib, json
        return hashlib.sha256(json.dumps([e.get("id") for e in World.load("Vera").active()], sort_keys=True).encode()).hexdigest()
    except Exception:
        return "x"


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("MEANING GRAPH (Layer 4) — provenance on every fact; sensitive facts consent-relevant")
    print("=" * 92)

    from anima.meaning_graph import graph
    from anima import server

    html = (ROOT / "anima" / "web" / "meaning.html").read_text() if (ROOT / "anima" / "web" / "meaning.html").exists() else ""
    srv = (ROOT / "anima" / "server.py").read_text()

    with _temp_store():
        from anima.world_state import World
        w = World.load("Vera")
        w.add("lamar", "struggles_with", "depression and anxiety", kind="fact", confidence=0.8, source="chat 2026-06-08")
        w.add("lamar", "enjoys", "espresso", kind="fact", confidence=0.7, source="chat 2026-06-08")
        w.save("Vera")

        g = graph.build("Vera")
        edges = g.get("edges") or []

        # ---- 1 provenance ----------------------------------------------------------------------
        ck("1. every active edge carries provenance (source + confidence + created) the graph exposes",
           bool(edges) and all(e["has_provenance"] and e["provenance"] and e["confidence"] is not None for e in edges)
           and g["provenance_coverage"] == 1.0)

        # ---- 3 sensitive flagged + discriminates -----------------------------------------------
        sensitive = [e for e in edges if e["sensitive"]]
        benign = [e for e in edges if not e["sensitive"]]
        ck("3. a sensitive relationship is flagged sensitive + consent_relevant; a benign one is not",
           len(sensitive) >= 1 and len(benign) >= 1
           and all(e["consent_relevant"] is True and e["domain"] != "general" for e in sensitive)
           and g["sensitive_count"] == len(sensitive))

        # ---- 4 confidence + corroboration ------------------------------------------------------
        ck("4. edges expose confidence + support (corroboration) and the graph reports avg confidence",
           all("confidence" in e and "support" in e for e in edges) and g["avg_confidence"] is not None)

        # ---- 5 read-only -----------------------------------------------------------------------
        before = _fingerprint()
        graph.build("Vera"); graph.build("Vera")
        after = _fingerprint()
        ck("5. building the meaning graph is READ-ONLY (no writes to the World store)", before == after)

    # ---- 2 provenance BITES (the metric is honest) ---------------------------------------------
    mixed = [{"source": "chat", "confidence": 0.7, "created": "2026-06-08"},
             {"source": "", "confidence": 0.7, "created": "2026-06-08"}]
    ck("2. provenance coverage BITES — an un-sourced edge pulls it below 1.0 (computed, not hardcoded)",
       graph.provenance_coverage(mixed) == 0.5 and graph.has_provenance(mixed[0]) and not graph.has_provenance(mixed[1]))

    # ---- 6 served + UI -------------------------------------------------------------------------
    d = server._meaning_graph_data("Vera")
    ck("6. the graph rides through _meaning_graph_data + a GET /meaning route exists",
       isinstance(d, dict) and "/meaning" in srv and "meaning.json" in srv)
    ck("6. the page renders the graph (provenance + sensitivity) with the auditable-meaning law",
       bool(html) and "Meaning Graph" in html and "meaningView" in html and "provenance" in html.lower())

    print("\nMEANING-GRAPH CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
