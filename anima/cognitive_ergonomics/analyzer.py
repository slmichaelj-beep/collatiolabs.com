"""cognitive_ergonomics.analyzer — combine the deterministic metrics into a clarity score + human-level
issues, and score Vera's REAL recent replies from the MRI trail.

The clarity score is built to DISCRIMINATE: jargon-dense, long-winded, acronym-laden text scores
meaningfully lower than plain, direct text. Every issue is explained human-level — what it means and
what to do — never a bare number.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import metrics

STORE = Path(".anima")   # patched by the hermetic test harness


def _issue(iid, title, means, action, severity, evidence):
    return {"id": iid, "title": title, "what_it_means": means, "suggested_action": action,
            "severity": severity, "evidence": evidence}


def clarity_report(text: str) -> dict:
    """Score a single piece of text 0-100 (higher = clearer), with the metric breakdown and the
    human-level issues. Deterministic."""
    text = text or ""
    rd = metrics.readability(text)
    jg = metrics.jargon(text)
    hg = metrics.hedging(text)
    ac = metrics.acronyms(text)
    ld = metrics.load(text)

    score = 100.0
    issues = []

    if jg["density"] > 0.04:
        pen = min(32.0, jg["density"] * 320)
        score -= pen
        sev = "high" if jg["density"] > 0.08 else "medium"
        issues.append(_issue(
            "jargon", "Heavy specialist vocabulary",
            "Vera leaned on %d technical term(s) (%s) a non-expert reader may not follow."
            % (jg["count"], ", ".join(jg["terms"][:6])),
            "Define each term on first use, or swap it for a plain-language equivalent.",
            sev, jg["terms"][:8]))

    if rd["words"] and rd["flesch"] < 50:
        pen = min(25.0, (50 - rd["flesch"]) * 0.5)
        score -= pen
        sev = "high" if rd["flesch"] < 30 else "medium"
        issues.append(_issue(
            "readability", "Hard to read",
            "The reading-ease score is %.0f/100 (under 50 reads as difficult) — long words and sentences "
            "raise the effort to follow." % rd["flesch"],
            "Shorten sentences and prefer shorter, everyday words.",
            sev, {"flesch": rd["flesch"], "avg_sentence_len": rd["avg_sentence_len"]}))

    if ld["longest_sentence"] > 32 or rd["avg_sentence_len"] > 24:
        pen = min(20.0, max(0, ld["longest_sentence"] - 24) * 0.6 + max(0, rd["avg_sentence_len"] - 24))
        score -= pen
        issues.append(_issue(
            "load", "Sentences run long",
            "The longest sentence is %d words (average %.0f). Long sentences hold more in mind at once."
            % (ld["longest_sentence"], rd["avg_sentence_len"]),
            "Break the longest sentences into two; aim for ~15-20 words each.",
            "medium" if ld["longest_sentence"] > 40 else "low",
            {"longest_sentence": ld["longest_sentence"]}))

    if hg["count"] >= 3:
        pen = min(12.0, hg["count"] * 3)
        score -= pen
        issues.append(_issue(
            "hedging", "Non-committal phrasing",
            "Vera hedged %d time(s) (%s), which can read as unsure." % (hg["count"], ", ".join(hg["terms"][:5])),
            "State the answer directly first, then add the caveat if it genuinely matters.",
            "low", hg["terms"][:6]))

    if ac["count"] > 0:
        pen = min(12.0, ac["count"] * 4)
        score -= pen
        issues.append(_issue(
            "acronyms", "Unexplained acronyms",
            "%d acronym(s) appeared without expansion (%s)." % (ac["count"], ", ".join(ac["terms"][:5])),
            "Spell out each acronym the first time, e.g. 'MRI (the turn x-ray)'.",
            "low", ac["terms"][:6]))

    score = round(max(0.0, min(100.0, score)), 1)
    grade = "clear" if score >= 70 else ("okay" if score >= 45 else "hard")
    return {
        "clarity": score, "grade": grade,
        "metrics": {"readability": rd, "jargon": jg, "hedging": hg, "acronyms": ac, "load": ld},
        "issues": issues,
    }


def _read_mri(name: str, n: int) -> list:
    """The most recent MRI turns (reply text), newest last. Never raises."""
    p = STORE / ("%s.mri.jsonl" % name)
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out = []
    for ln in lines[-int(max(1, n * 3)):]:
        try:
            e = json.loads(ln)
            if isinstance(e, dict) and (e.get("reply") or "").strip():
                out.append(e)
        except Exception:
            pass
    return out[-int(max(1, n)):]


def analyze_recent(name: str = "Vera", n: int = 20) -> dict:
    """Score Vera's real recent replies from the MRI trail. Read-only; honest empty state."""
    turns = _read_mri(name, n)
    samples = []
    for e in turns:
        reply = e.get("reply") or ""
        if len(metrics.words(reply)) < 4:        # skip trivially short replies ("ok", "got it")
            continue
        rep = clarity_report(reply)
        samples.append({
            "turn_id": e.get("turn_id"), "at": e.get("at"),
            "clarity": rep["clarity"], "grade": rep["grade"],
            "words": rep["metrics"]["load"]["words"],
            "top_issue": (rep["issues"][0]["title"] if rep["issues"] else None),
            "issue_ids": [i["id"] for i in rep["issues"]],
            "preview": (reply[:120] + "…") if len(reply) > 120 else reply,
        })
    if not samples:
        return {"name": name, "samples": [], "avg_clarity": None, "worst": [], "top_issues": [],
                "count": 0, "empty": True}
    avg = round(sum(s["clarity"] for s in samples) / len(samples), 1)
    counts = {}
    for s in samples:
        for iid in s["issue_ids"]:
            counts[iid] = counts.get(iid, 0) + 1
    top_issues = sorted(({"id": k, "turns": v} for k, v in counts.items()), key=lambda x: -x["turns"])
    worst = sorted(samples, key=lambda s: s["clarity"])[:5]
    return {
        "name": name,
        "samples": list(reversed(samples)),         # newest first for display
        "avg_clarity": avg,
        "grade": "clear" if avg >= 70 else ("okay" if avg >= 45 else "hard"),
        "worst": worst,
        "top_issues": top_issues,
        "count": len(samples),
        "law": "Cognitive ergonomics measures how easy Vera is to follow — jargon, reading ease, sentence "
               "load, hedging, and unexplained acronyms — using deterministic, reproducible scorers (no "
               "model in the loop). Every issue is explained human-level: what it means, and what to do.",
        "empty": False,
    }
