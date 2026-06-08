#!/usr/bin/env python3
"""prompt_budget — break the live turn's PROMPT down by section, in tokens.

The performance bottleneck was measured (not guessed) to be prompt-EVAL of a large prompt, not slow
generation. Before tuning, we have to see WHICH part of the ~2.6k-token prompt is big. This tool
reconstructs the prompt Vera actually builds for a NORMAL (model) turn — the SAME assembly the live
turn uses (mouth._assemble_prompt: persona + dials + never-break-character hardening + name rule +
feeling + self-narrative + the memory bundle = portrait + bound LIRF facts + world-state situation),
plus the user message envelope and the capped conversation history that ride the model call — and
counts tokens per section with the codebase's own offline counter (lerf.count_tokens).

It does NOT change the prompt or any behavior — it only measures. It anchors the offline estimate to
GROUND TRUTH: the model's real prompt_eval_count from the server log ("[timing] … prompt N tok"), so
the difference (chat-template / role-marker overhead) is shown honestly rather than hidden.

    python3 scripts/prompt_budget.py                  # measure for the default sample turns
    python3 scripts/prompt_budget.py --name Vera       # a specific creature
    python3 scripts/prompt_budget.py --json            # machine output

Writes reports/prompt_budget.md (the BEFORE baseline for the slimming work). No model call, no network.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# representative NORMAL turns (real questions that route to the model, not the fast path)
SAMPLES = [
    "what's a good way to plan my week so I actually follow through?",
    "I've been feeling stretched thin lately — can we talk about it?",
]

# map a fragment's `source` label -> a human section bucket
_SECTION = [
    ("persona_hardening", "system · never-break-character (static)"),
    ("persona",           "system · personality"),
    ("dials",             "system · personality"),
    ("name_rule",         "system · personality"),
    ("feeling",           "system · feeling (per-turn)"),
    ("narrative",         "system · self-narrative"),
    ("memory",            "memory (portrait + LIRF facts + situation)"),
    ("guidance",          "safety/guidance (care tone)"),
]


def _section_of(source: str) -> str:
    s = (source or "").lower()
    for key, label in _SECTION:
        if s.startswith(key):
            return label
    return "system · other"


def _memory_bundle(name: str, user_text: str) -> str:
    """Reconstruct the SAME memory bundle respond() injects: portrait (prose USER profile) + the
    spine-bound LIRF facts for this turn + the world-state situation cluster. Guarded; mirrors
    anima/mouth.py respond() so the measured prompt matches the shipped prompt."""
    from anima import portrait
    try:
        mem = portrait.load(name) or ""
    except Exception:
        mem = ""
    # spine-bound LIRF facts (query-relevant; full-block fallback) — the Knowledge Spine
    try:
        from anima import spine
        from anima.memory_lirf import Facts
        rows = None
        try:
            from anima.organs.router import select_facts
            rows, _ = select_facts(name, user_text)
        except Exception:
            rows = None
        if rows is None:
            try:
                rows = Facts.load(name).about()
            except Exception:
                rows = []
        fb = spine.bind(rows, user_text)
        if not fb:
            try:
                fb = Facts.load(name).block()
            except Exception:
                fb = ""
        if fb:
            mem = (mem + "\n\n" + fb) if mem.strip() else fb
    except Exception:
        pass
    # world-state situation cluster (only when it has edges) — same as respond()
    try:
        from anima import world_state as ws
        cl = ws.situation(name, user_text, hops=2)
        if cl.get("edges"):
            sit = ws.render_situation(cl)
            if sit and sit.strip():
                mem = (mem + "\n\n" + sit) if mem.strip() else sit
    except Exception:
        pass
    return mem


def _feeling(name: str) -> dict:
    try:
        from anima.server import _path
        from anima.heart import Heart
        from anima.crypto import load_json
        return Heart.from_dict(load_json(_path(name))).feeling()
    except Exception:
        return {}


def _history(name: str, user_text: str):
    """The capped, immune-cleaned history that actually rides the model call (mouth._HISTORY_TO_MODEL
    most-recent turns, after the context-immune quarantine pass) — exactly what reply() sends."""
    from anima import mouth
    hist = []
    try:
        raw = json.loads((ROOT.parent / "collatiolabs.com" / ".anima" / f"{name}.history.json").read_text())
    except Exception:
        try:
            from anima.server import STORE
            raw = json.loads((STORE / f"{name}.history.json").read_text())
        except Exception:
            raw = []
    for item in (raw or []):
        try:
            hist.append((item[0], item[1]))
        except Exception:
            pass
    try:
        from anima import immune
        hist = immune.clean_history(hist, user_text)
    except Exception:
        pass
    # the SAME budgeted selection the live model call uses (token budget, not just turn count)
    return mouth._history_for_model(hist)


def _real_prompt_tokens() -> int | None:
    """Ground truth: the most recent real prompt_eval_count the model reported, from the server log
    line '[timing] … prompt N tok'. None if no model turn has been logged."""
    for p in (Path("/Users/lamarmichael/collatiolabs.com/.anima/server.log"),
              ROOT.parent / "collatiolabs.com" / ".anima" / "server.log"):
        try:
            hits = re.findall(r"prompt (\d+) tok", p.read_text())
            if hits:
                return int(hits[-1])
        except Exception:
            continue
    return None


def build(name: str, user_text: str) -> dict:
    from anima import mouth, care, rail
    f = _feeling(name)
    try:
        guidance = care.assess(user_text).guidance
    except Exception:
        guidance = ""
    mem = _memory_bundle(name, user_text)
    # pass user_text so the breakdown reflects the ROUTE-GATED hardening (full only when challenged)
    _text, frags = mouth._assemble_prompt(name, f, guidance, memory=mem, user_text=user_text)

    # roll fragments up into sections (tokens)
    sections: dict = {}
    for fr in frags:
        sec = _section_of(fr.get("source"))
        d = sections.setdefault(sec, {"tokens": 0, "chars": 0})
        d["tokens"] += int(fr.get("tokens") or 0)
        d["chars"] += int(fr.get("chars") or 0)

    # user message envelope (rail-hardened, as sent) + capped history (as sent)
    try:
        umsg = rail.harden(user_text)
    except Exception:
        umsg = user_text
    sections["user message (this turn)"] = {"tokens": mouth._count_tokens(umsg), "chars": len(umsg)}

    hist = _history(name, user_text)
    htok = hchar = 0
    for u, a in hist:
        htok += mouth._count_tokens(u) + mouth._count_tokens(a)
        hchar += len(u or "") + len(a or "")
    sections["history (%d turns, capped)" % len(hist)] = {"tokens": htok, "chars": hchar}

    est_total = sum(s["tokens"] for s in sections.values())
    return {"name": name, "user_text": user_text, "sections": sections,
            "estimated_tokens": est_total,
            "system_prompt_chars": len(_text),
            "fragments": sorted(frags, key=lambda d: -int(d.get("tokens") or 0))}


def render(rows: list, real_total) -> str:
    out = []
    out.append("PROMPT BUDGET — where the live turn's prompt tokens go (offline estimate)")
    out.append("=" * 92)
    for r in rows:
        out.append("\nturn: %r" % r["user_text"])
        secs = sorted(r["sections"].items(), key=lambda kv: -kv[1]["tokens"])
        tot = r["estimated_tokens"] or 1
        for name_, d in secs:
            bar = "█" * int(round(28 * d["tokens"] / tot))
            out.append("  %5d tok  %4.0f%%  %-44s %s" % (d["tokens"], 100 * d["tokens"] / tot, name_[:44], bar))
        out.append("  %5d tok  100%%  %-44s" % (r["estimated_tokens"], "ESTIMATED TOTAL (sections)"))
    if real_total:
        avg = sum(r["estimated_tokens"] for r in rows) / max(1, len(rows))
        out.append("\nGROUND TRUTH (model prompt_eval_count, latest live turn): %d tok" % real_total)
        out.append("  offline estimate avg: %d tok · chat-template/role-marker overhead ≈ %d tok"
                   % (int(avg), max(0, int(real_total - avg))))
    out.append("\nNote: tokens are the offline estimate (lerf.count_tokens = max(words, chars/4)); the")
    out.append("model total above is the real prompt_eval_count. Sources are NOT here — they ride a")
    out.append("separate deterministic recall seam, not the model prompt. No prompt/behavior changed.")
    return "\n".join(out)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    name = "Vera"
    if "--name" in argv:
        try:
            name = argv[argv.index("--name") + 1]
        except Exception:
            pass
    rows = [build(name, s) for s in SAMPLES]
    real = _real_prompt_tokens()
    try:
        (ROOT / "reports").mkdir(exist_ok=True)
        (ROOT / "reports" / "prompt_budget.json").write_text(
            json.dumps({"turns": rows, "real_prompt_tokens": real}, indent=2))
        (ROOT / "reports" / "prompt_budget.md").write_text(
            "# Prompt Budget — BEFORE baseline\n\n```\n" + render(rows, real) + "\n```\n")
    except Exception:
        pass
    if "--json" in argv:
        print(json.dumps({"turns": rows, "real_prompt_tokens": real}, indent=2))
        return 0
    print(render(rows, real))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
