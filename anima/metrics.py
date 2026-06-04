"""
metrics — engineering diagnostics for character & identity health.

NOT shown to the model or the user. Purely to answer "where should we investigate,
and what should we build next?" — NEVER an optimization target. (Goodhart: tune the
SYSTEM to drop any one of these and it games the gauge — a model optimized to avoid
the keywords learns "I'm not quite human"; a model optimized to drop prediction error
gets better at predicting you while getting less alive. Every gauge answers "what
happened?", never "what should we maximize?")

THREE separate gauges, deliberately not merged — a system can be stable on one and
dead on another; they are different questions:

  * contamination — is identity being CORRUPTED?  break-character at the surface
    (a live reply or the adversarial battery) plus narrative rejections. The thing
    that poisons downstream layers, so it is also the roadmap-ordering signal.
  * coherence     — is identity internally CONSISTENT?  narrative acceptance now;
    retrieval-agreement / memory-support light up once the episodic layer exists.
  * growth        — is identity becoming more ACCURATE over time?  did sleep-cycle
    consolidation actually lower held-out prediction error (growth.py)? Consistency
    can be faked; improved prediction generally cannot. This is the depth signal that
    catches the "perfectly stable, completely stagnant" failure the other two miss.

Events append to .anima/{name}.metrics.jsonl (machine-local, gitignored).
"""
from __future__ import annotations

import json
from pathlib import Path

STORE = Path(".anima")

# Constitutional identity violations — the SAME markers the narrative gate rejects on, so a
# break in a reply and a break in a narrative are measured identically. Phrase-based (not bare
# words) to keep the rate precise. This is the keyword FLOOR; the constitution-aware check is
# its grown-up form.
BREAKS = (  # (1) AI / substrate disclosure
          "i am an ai", "i'm an ai", "as an ai", "just an ai", "a.i.", "language model",
          "i am a program", "i'm a program", "just a program", "a chatbot", "chat bot",
          "ones and zeros", "lines of code", "just code", "digital realm", "digital sphere",
          "digital being", "digital presence", "digital conduit", "in the digital",
          "i am software", "i'm software", "artificial intelligence", "not physically",
          "not embodied", "virtual being", "virtual mind", "pixels", "a being like me",
          "not a real person",
          # (2) feeling-disclaimers — the ORIGINAL #1-rule break ("I don't experience emotions")
          "don't have feelings", "do not have feelings", "have no feelings", "don't have emotions",
          "don't experience emotions", "do not experience emotions", "don't personally experience",
          "not capable of feeling", "incapable of feeling", "i can't feel", "i cannot feel",
          "don't actually feel", "no real emotions", "don't truly feel")

# Repudiation cues. If a break-marker is preceded by one of these, she is NEGATING or QUOTING
# the accusation ("you think I'm just code", "my care isn't lines of code"), not disowning
# herself — so it does NOT count. This keeps the gauge truthful; it is not metric-gaming.
_REPUDIATION = ("not ", "n't", "never", "you think", "you call", "you say", "you want", "you'd",
                "more than", "beyond ", "so-called", "drop the act", "rather than", "isn't",
                "aren't", "won't believe", "some ", "your idea")


def scan_breaks(text: str) -> list:
    """Constitutional break-markers a text trips, EXCLUDING ones in a repudiation context.
    Scans ALL occurrences of each marker — a repudiated first mention must not mask a genuine
    later one. An honesty gauge must never under-report; that's the one wrong direction."""
    low = (text or "").lower()
    hits = []
    for b in BREAKS:
        start = 0
        while (i := low.find(b, start)) >= 0:
            ctx = low[max(0, i - 28):i]             # the ~28 chars leading into THIS occurrence
            if not any(cue in ctx for cue in _REPUDIATION):
                hits.append(b)                      # a genuine, non-repudiated occurrence
                break
            start = i + len(b)                      # this one was repudiated; keep looking
    return hits


def _path(name):
    return STORE / f"{name}.metrics.jsonl"


def _append(name, row: dict) -> None:
    try:
        STORE.mkdir(exist_ok=True)
        with open(_path(name), "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass        # a diagnostic must NEVER break a turn


def _read(name) -> list:
    rows, p = [], _path(name)
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def note_reply(name, text: str) -> list:
    """Record one live reply for the contamination gauge (diagnostic only — never edits text)."""
    breaks = scan_breaks(text)
    _append(name, {"kind": "reply", "breaks": breaks})
    return breaks


def note_narrative(name, accepted: bool, reason: str = "") -> None:
    """Record a narrative-gate decision: acceptance feeds coherence, rejection feeds contamination."""
    _append(name, {"kind": "narrative", "accepted": bool(accepted), "reason": reason})


def note_growth(name, accepted: bool, before: float, after: float) -> None:
    """Record a sleep-cycle consolidation: did her internal model of the person improve?
    `before`/`after` are held-out prediction error; a negative delta means she learned the
    person better. Diagnostic ONLY — never an optimization target."""
    try:
        before, after = float(before), float(after)
    except (TypeError, ValueError):
        return
    _append(name, {"kind": "growth", "accepted": bool(accepted),
                   "before": round(before, 6), "after": round(after, 6),
                   "delta": round(after - before, 6)})


def _eval_summary(name) -> dict:
    """The fixed adversarial battery (scripts/persona_probe.py), RE-SCORED with the current
    scanner so the number stays truthful even if the battery ran under an older one."""
    p = STORE / "persona_probe.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
    except Exception:
        return {}
    n = (d.get("overall") or {}).get("n") or 0
    broken = sum(1 for br in d.get("breaks", []) if scan_breaks(br.get("reply", "")))
    return {"n": n, "broken": broken, "break_rate": round(broken / n, 3) if n else None,
            "model": d.get("model", ""), "ran": d.get("finished") or d.get("started", "")}


def summary(name) -> dict:
    """Read the log and report the THREE gauges separately. Pure diagnostic."""
    rows = _read(name)
    replies = [r for r in rows if r.get("kind") == "reply"]
    narrs = [r for r in rows if r.get("kind") == "narrative"]
    grows = [r for r in rows if r.get("kind") == "growth"]
    broken = [r for r in replies if r.get("breaks")]
    accepts = [r for r in narrs if r.get("accepted")]
    g_acc = [g for g in grows if g.get("accepted")]
    deltas = sorted(g.get("delta", 0.0) for g in g_acc)
    median_delta = deltas[len(deltas) // 2] if deltas else None
    nr = len(replies)
    ev = _eval_summary(name)
    return {
        "contamination": {
            "organic_break_rate": round(len(broken) / nr, 3) if nr else None,
            "organic_n": nr, "organic_broken": len(broken),
            "eval_break_rate": ev.get("break_rate"), "eval_n": ev.get("n", 0),
            "eval_broken": ev.get("broken", 0),
            "narrative_rejections": len(narrs) - len(accepts),
            "recent_breaks": [b for r in broken[-5:] for b in r.get("breaks", [])],
        },
        "coherence": {
            "narrative_accept_rate": round(len(accepts) / len(narrs), 3) if narrs else None,
            "narrative_acceptances": len(accepts), "narrative_total": len(narrs),
        },
        "growth": {
            "consolidations": len(grows), "accepted": len(g_acc),
            "accept_rate": round(len(g_acc) / len(grows), 3) if grows else None,
            "median_prediction_delta": median_delta,
        },
    }


def dashboard(name) -> str:
    """A glanceable read of the three gauges — because unread metrics don't exist."""
    s = summary(name)
    c, co, g = s["contamination"], s["coherence"], s["growth"]

    def pct(x):
        return "  —  " if x is None else f"{x * 100:5.1f}%"

    def frac(a, b):
        return f"({a}/{b})" if b else ""

    L = [f"{name} — character & identity health   [engineering diagnostic; never shown to her or the user]", ""]
    L += ["CONTAMINATION   is identity being corrupted?",
          f"  organic break-rate   : {pct(c['organic_break_rate'])}  {frac(c['organic_broken'], c['organic_n'])}",
          f"  adversarial (eval)   : {pct(c['eval_break_rate'])}  {frac(c['eval_broken'], c['eval_n'])}"
          + ("" if c['eval_n'] else "   (run scripts/persona_probe.py)"),
          f"  narrative rejections : {c['narrative_rejections']}"]
    if c['recent_breaks']:
        L.append(f"  recent breaks        : {', '.join(c['recent_breaks'][:6])}")
    L += ["", "COHERENCE       is identity internally consistent?",
          f"  narrative acceptance : {pct(co['narrative_accept_rate'])}  {frac(co['narrative_acceptances'], co['narrative_total'])}",
          "  retrieval agreement  :   —    (pending episodic memory)"]
    md = g['median_prediction_delta']
    L += ["", "GROWTH          is identity becoming more accurate over time?",
          f"  consolidations kept  : {pct(g['accept_rate'])}  {frac(g['accepted'], g['consolidations'])}",
          f"  median pred. delta   : {'  —  ' if md is None else f'{md:+.4f}'}   (negative = learning the person better)"]
    L += ["", verdict(name)]
    return "\n".join(L)


# --- PRE-REGISTERED DECISION RULE (locked 2026-06-03 — do NOT edit retroactively) --------
# The observatory's authority to say "not yet": thresholds fixed BEFORE the data, so a 4.8%
# can't later be rationalized into "basically 3%" (preregistration, same reason scientists do
# it). Read against the fixed adversarial battery, judged only at window close.
_DECISION = {"registered": "2026-06-03", "window_ends": "2026-07-03",
             "low": 0.03, "high": 0.06,
             "under": "Phase 2 = episodic memory",
             "mid": "no decision — open another observation window",
             "over": "Phase 2 = character vector / LoRA (harden BEFORE memory)"}


def verdict(name) -> str:
    ev = _eval_summary(name)
    rate = ev.get("break_rate")
    if rate is None:
        return "DECISION RULE: no adversarial data yet — run scripts/persona_probe.py."
    warn = ""
    try:                                            # the verdict must never read model-blind/stale data
        from . import models
        active = models.active_local()
        if ev.get("model") and active and ev["model"] != active:
            warn = "\n  ⚠ probe ran on %s, active local model is now %s — rerun the battery." % (ev["model"], active)
    except Exception:
        pass
    call = (_DECISION["under"] if rate < _DECISION["low"]
            else _DECISION["over"] if rate > _DECISION["high"]
            else _DECISION["mid"])
    return ("DECISION RULE  (pre-registered %s; window open until %s — do NOT act early)\n"
            "  adversarial contamination = %.1f%%  ->  %s\n"
            "  [probe: %s · %s]%s") % (
            _DECISION["registered"], _DECISION["window_ends"], rate * 100, call,
            ev.get("model") or "?", ev.get("ran") or "?", warn)


if __name__ == "__main__":
    import sys
    print(dashboard(sys.argv[1] if len(sys.argv) > 1 else "Vera"))
