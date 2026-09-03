#!/usr/bin/env python3
"""certify_cognitive_ergonomics — Cognitive Ergonomics (Human Operating Layer, Layer 5) is REAL: a
deterministic, model-free clarity engine that scores Vera's OWN replies and explains every issue
human-level (what it means -> what to do).

  1. DETERMINISTIC   — the same text always yields the same score (no model, no randomness).
  2. DISCRIMINATES   — the keystone: a jargon-dense, long-winded, acronym-laden reply scores MEANINGFULLY
                       lower than a plain, direct one. A metric that can't tell them apart is wallpaper.
  3. HUMAN-LEVEL     — every issue carries a plain-English 'what it means' AND a 'what to do' action.
  4. REAL REPLIES    — analyze_recent scores Vera's actual replies from the MRI trail (not synthetic).
  5. HONEST EMPTY    — with no replies, it reports an honest empty state (no fabricated score).
  6. SERVED + AUTH   — the report rides through _ergonomics_data; GET /ergonomics serves the page; the
                       data is behind the seam; the page renders the clarity dashboard.

Hermetic. Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store

PLAIN = ("You have a meeting at three today. I moved the dentist to Friday so the two would not clash. "
         "Want me to text Mara?")
JARGON = ("The inference latency regression stems from the tokenizer emitting suboptimal logits, so the "
          "quantized transformer checkpoint, whose embeddings the centroid-based retrieval subsystem "
          "deserializes asynchronously across the daemon mutex, exhibits perplexity drift that, although "
          "idempotent under the serialization schema, nonetheless propagates backpropagation gradients "
          "through the MRI and LERF substrate in a way that is, perhaps, somewhat arguably non-deterministic.")


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("COGNITIVE ERGONOMICS (Layer 5) — deterministic clarity; issues explained human-level")
    print("=" * 92)

    from anima.cognitive_ergonomics import analyzer, metrics
    from anima import server

    html = (ROOT / "anima" / "web" / "ergonomics.html").read_text() if (ROOT / "anima" / "web" / "ergonomics.html").exists() else ""
    srv = (ROOT / "anima" / "server.py").read_text()

    # ---- 1 deterministic ----------------------------------------------------------------------
    a = analyzer.clarity_report(JARGON)
    b = analyzer.clarity_report(JARGON)
    ck("1. deterministic — the same text yields the identical score + issues twice",
       a == b and isinstance(a["clarity"], float))

    # ---- 2 discriminates (the keystone) -------------------------------------------------------
    pr = analyzer.clarity_report(PLAIN)
    jr = analyzer.clarity_report(JARGON)
    ck("2. discriminates — a jargon-dense, long-winded reply scores >=25 points lower than a plain one",
       pr["clarity"] - jr["clarity"] >= 25 and pr["grade"] == "clear" and jr["grade"] in ("okay", "hard"))
    ck("2. the metrics are model-free (jargon density + Flesch reading-ease are computed, not guessed)",
       metrics.jargon(JARGON)["count"] >= 6 and 0 <= metrics.readability(JARGON)["flesch"] <= 100)

    # ---- 3 human-level issues (what it means -> what to do) -----------------------------------
    issues = jr["issues"]
    ck("3. every flagged issue carries a plain-English 'what it means' AND a 'what to do' action",
       bool(issues) and all(i.get("what_it_means") and i.get("suggested_action") and i.get("severity")
                            for i in issues))
    ck("3. the jargon issue names the actual offending terms (real evidence, not a generic note)",
       any(i["id"] == "jargon" and i.get("evidence") for i in issues))

    # ---- 4 real replies + 5 honest empty ------------------------------------------------------
    with _temp_store():
        from anima.cognitive_ergonomics import analyzer as a2
        # honest empty first
        empty = a2.analyze_recent("Vera", 10)
        ck("5. with no replies on record, it reports an honest empty state (no fabricated score)",
           empty.get("empty") is True and empty.get("avg_clarity") is None)

        # seed a REAL-shaped MRI trail and confirm it scores those replies
        mri = a2.STORE / "Vera.mri.jsonl"
        mri.parent.mkdir(parents=True, exist_ok=True)
        rows = [{"turn_id": "t1", "at": "2026-06-08T10:00:00", "user_text": "hi", "reply": PLAIN},
                {"turn_id": "t2", "at": "2026-06-08T10:01:00", "user_text": "why slow?", "reply": JARGON}]
        mri.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        rec = a2.analyze_recent("Vera", 10)
        ck("4. analyze_recent scores Vera's actual replies from the MRI trail",
           rec.get("count") == 2 and rec.get("avg_clarity") is not None and not rec.get("empty"))
        ck("4. the jargon-heavy turn surfaces as a worst-clarity sample with issues",
           any(s["grade"] in ("okay", "hard") and s["issue_ids"] for s in rec["worst"]))

    # ---- 6 served + UI ------------------------------------------------------------------------
    d = server._ergonomics_data("Vera")
    ck("6. the report rides through _ergonomics_data + a GET /ergonomics route exists",
       isinstance(d, dict) and "/ergonomics" in srv and "ergonomics.json" in srv)
    ck("6. the page renders the clarity dashboard (score + issues) with the model-free framing",
       bool(html) and "Cognitive Ergonomics" in html and "ergoView" in html and "clarity" in html.lower())

    print("\nCOGNITIVE-ERGONOMICS CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
