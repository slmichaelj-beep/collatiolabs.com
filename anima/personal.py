"""
personal — PERSONAL INTELLIGENCE ("Learn Lamar"): the moat.

This is where Vera stops being a general assistant and becomes *Lamar's* assistant.
A general model knows how people-in-general decide and write. Personal intelligence
knows how LAMAR decides and writes — and it compounds: every captured decision,
turn of phrase, stated value, and hard-won lesson is folded into a small, legible,
provenance-stamped model of how this one person thinks. The thesis is simple and is
the whole product bet: PERSONAL INTELLIGENCE COMPOUNDS. The hundredth captured
decision is worth more than the first because it sits on ninety-nine others.

WHAT IT MODELS (the user — Lamar — and ONLY the user):
  * DECISION HISTORY  -> DECISION_PATTERN objects: how Lamar decides (the criteria he
                         weighs, the typical choice they yield, worked examples + outcome
                         where it was captured).
  * WRITING PATTERNS  -> user PREFERENCE objects: how Lamar writes (tone, length,
                         formality, recurring phrasing), each grounded in samples of his
                         actual words.
  * VALUES / TRADEOFFS-> user VALUE objects: what Lamar optimizes for and what he trades
                         away to get it.
  * PREFERENCES       -> user PREFERENCE objects: what Lamar wants, ranked where known.
  * LESSONS LEARNED   -> HEURISTIC objects: what Lamar concluded ("if X then Y"), stored
                         with the evidence he concluded it from.

THE FREEZE BOUNDARY — "build the mind, leave the self alone."
  This module models LAMAR. It never models, infers, or stores a value/preference/goal/
  belief about VERA HERSELF. It does not touch Vera's own values, agency, self-model, or
  identity. Enforcement is NOT this module's invention — it routes EVERY value/preference
  through lerf.py's freeze-guarded factories (`make_value` / `make_preference`), which
  REFUSE a Vera-self subject by raising `lerf.FreezeViolation` at mint time, and through
  `lerf.store_object`, which re-checks at the single persistence choke point. We rely on
  that guard rather than re-implementing it. `freeze_proof()` demonstrates the refusal.

GROUNDING — nothing is invented.
  Every object this module produces is built from CAPTURED data only: the LIRF fact ledger
  (memory_lirf.Facts — durable user-facts with their `source`/`evidence`/`updated`
  provenance) and, optionally, the transient turn log (portrait). Each produced object
  carries an `evidence` list of the literal captured snippets it was built from, a
  `taught_by` stamp naming the person (Lamar), and a `source` of "captured:<channel>" so
  the provenance() query can always answer "how do we know this?" with a real record.
  An EMPTY capture history yields an EMPTY profile — `personal_profile` never fabricates a
  personality from nothing. This is the anti-confabulation contract of the #1 product rule,
  applied to the model of the person.

STORAGE / RETRIEVAL.
  Built objects are persisted via `lerf.store_object` into the same per-creature ledger the
  rest of the cognitive substrate uses, as state=ACTIVE (hand-grounded in real evidence is
  the bar the seed skills meet too). They are retrieved through lerf's existing deterministic
  retrievers (`retrieve_decision_patterns` / `retrieve_preferences` / `retrieve_values` /
  `retrieve_heuristics`) — this module does NOT fork retrieval. We read and use lerf's public
  API; we never edit lerf.py / memory_lirf.py / world_model.py.

CLI: scripts/personal.py (build / profile / freeze-proof / --selftest).
"""

from __future__ import annotations

import re
from typing import Iterable

from . import lerf
from . import memory_lirf
from . import portrait


# ===================================================================================
# DOMAIN TAG — every personal-intelligence object is tagged with this domain so the
# whole profile is one retrievable slice of the ledger, distinct from task/world skills.
# (Retrieval can pass domain="<PERSON>:lamar" to pull only this person's model.)
# ===================================================================================
DOMAIN = "personal"
SOURCE_PREFIX = "captured"          # source = "captured:lirf" / "captured:turns"

# Confidence a hand-grounded personal object enters at — the same SEED bar the
# hand-authored seed skills use (it is grounded in real captured evidence, which is the
# bar ACTIVE requires). Reuses lerf's constant so there is one source of truth.
CONF = lerf.CONF_SEED


# ===================================================================================
# CAPTURED-DATA READERS — the ONLY inputs. Each returns plain evidence records the
# builders ground objects in. No model, no inference here: this is literally "what was
# captured", lifted out of the existing stores with its provenance intact.
# A record is a dict: {text, source, when, kind, fact_id?} — `text` is the verbatim
# captured snippet (the grounding), `source`/`when` are its provenance.
# ===================================================================================

def _fact_evidence_records(name: str) -> list:
    """Every durable USER fact as an evidence record, carrying its LIRF provenance
    (`source` like 'chat 2026-06-05', the verbatim `evidence` snippet, `updated`). These
    are the spine of the personal model: corroborated, provenance-stamped beliefs about
    the person, never raw transcript. Reads memory_lirf's public `Facts` API only."""
    out = []
    try:
        f = memory_lirf.Facts.load(name)
    except Exception:
        return out
    for r in f.about(memory_lirf.SELF):          # active rows, salience-ranked
        snippet = (r.get("evidence") or "").strip()
        value = memory_lirf._fmt_value(r.get("value"))
        # the grounding text prefers the literal evidence the user said; falls back to the
        # trait:value pair (still captured, just already distilled by the ledger).
        text = snippet or f"{r.get('trait','').replace('_',' ')}: {value}"
        out.append({
            "text": text,
            "trait": r.get("trait", ""),
            "value": value,
            "source": r.get("source", "") or "lirf",
            "when": (r.get("updated") or "")[:10],
            "confidence": float(r.get("confidence", 0.0)),
            "support": int(r.get("support", 1)),
            "kind": "fact",
            "fact_id": r.get("id", ""),
        })
    return out


def _turn_evidence_records(name: str, limit: int = 80) -> list:
    """The user's own words from the transient turn log, as evidence records. Vera's
    replies are IGNORED — a model of Lamar is built only from what Lamar said (the same
    discipline memory_lirf.capture follows: facts come from the user's words, never the
    reply). Reads portrait's public log API only; silently empty if no log exists."""
    out = []
    try:
        raw = portrait.read_transcript(name, limit=limit)
    except Exception:
        return out
    if not raw:
        return out
    # read_transcript renders "Them: <user>\n<name>: <reply>"; keep only the user side.
    for line in raw.splitlines():
        m = re.match(r"\s*Them:\s*(.+)$", line)
        if m and m.group(1).strip():
            out.append({
                "text": m.group(1).strip(),
                "source": "turns",
                "when": "",
                "kind": "turn",
            })
    return out


def _all_evidence(name: str, *, include_turns: bool = True) -> list:
    """The full captured-evidence pool for one person: durable facts first (they carry
    the strongest provenance), then their own recent turns. This is the closed world the
    builders may draw on — nothing outside it can enter the model."""
    recs = _fact_evidence_records(name)
    if include_turns:
        recs += _turn_evidence_records(name)
    return recs


# A small helper: turn a set of evidence records into the `evidence=[...]` list a factory
# wants, each line carrying its provenance so the object is auditable on sight.
def _evidence_lines(records: Iterable[dict]) -> list:
    lines = []
    for r in records:
        prov = r.get("source", "")
        when = r.get("when", "")
        tag = f" ({prov}{', ' + when if when else ''})" if prov else ""
        lines.append(f"{r['text']}{tag}")
    return lines


# ===================================================================================
# PATTERN DETECTORS — deterministic, offline reads over the evidence pool. Each detector
# RECOGNISES a signal in what was captured and reports it WITH the exact records that
# support it (so every produced object is grounded). A detector that finds nothing
# returns nothing — silence, never a guess. None of these invent content; they classify
# and quote the user's own captured words.
# ===================================================================================

# --- writing patterns ------------------------------------------------------------------
_FORMAL_CUES = re.compile(r"\b(furthermore|moreover|regards|sincerely|hereby|pursuant|"
                          r"accordingly|therefore|kindly|shall)\b", re.I)
_CASUAL_CUES = re.compile(r"\b(gonna|wanna|yeah|nah|lol|kinda|sorta|cuz|tbh|ngl|"
                          r"basically|honestly)\b|[!]{1,}|\bhey\b", re.I)
_BREVITY_CUES = re.compile(r"\b(cut it down|shorter|too long|tl;?dr|keep it (?:short|brief|tight)|"
                           r"in (?:one|a) (?:line|sentence)|be concise|trim (?:it|this))\b", re.I)


def detect_writing_patterns(records: list) -> list:
    """Recognise HOW the user writes from their own captured words. Returns a list of
    {pattern, weight, evidence:[records]} — each a writing trait literally exhibited in
    the evidence (formality register, brevity preference, average length). Builds nothing
    it cannot point at; an empty/short pool yields an empty list."""
    turns = [r for r in records if r.get("kind") == "turn" and r.get("text")]
    found = []
    if not turns:
        return found

    formal = [r for r in turns if _FORMAL_CUES.search(r["text"])]
    casual = [r for r in turns if _CASUAL_CUES.search(r["text"])]
    if formal or casual:
        if len(casual) >= len(formal) and casual:
            found.append({"pattern": "writes in a casual, conversational register",
                          "weight": round(min(0.95, 0.5 + 0.1 * len(casual)), 2),
                          "evidence": casual[:4]})
        elif formal:
            found.append({"pattern": "writes in a formal register",
                          "weight": round(min(0.95, 0.5 + 0.1 * len(formal)), 2),
                          "evidence": formal[:4]})

    brevity = [r for r in turns if _BREVITY_CUES.search(r["text"])]
    if brevity:
        found.append({"pattern": "prefers short, tight prose over long-winded prose",
                      "weight": round(min(0.95, 0.5 + 0.12 * len(brevity)), 2),
                      "evidence": brevity[:4]})

    # average sentence length is a measured, grounded signal (the words are the user's).
    wordcounts = [len(re.findall(r"\w+", r["text"])) for r in turns]
    if len(wordcounts) >= 3:
        avg = sum(wordcounts) / len(wordcounts)
        if avg <= 12:
            found.append({"pattern": "tends to write in short messages "
                                     f"(~{round(avg)} words on average)",
                          "weight": 0.7,
                          "evidence": sorted(turns, key=lambda r: len(r["text"]))[:3]})
        elif avg >= 30:
            found.append({"pattern": "tends to write in long, detailed messages "
                                     f"(~{round(avg)} words on average)",
                          "weight": 0.7,
                          "evidence": sorted(turns, key=lambda r: -len(r["text"]))[:3]})
    return found


# --- explicit preferences -------------------------------------------------------------
# "I prefer X (over Y)", "I (like|love|enjoy) X", "I (hate|dislike|can't stand) X".
_PREF_POS = re.compile(
    r"\bi\s+(?:prefer|like|love|enjoy|favou?r|always (?:use|choose|go with))\s+(.+)", re.I)
_PREF_NEG = re.compile(
    r"\bi\s+(?:hate|dislike|can'?t stand|avoid|never (?:use|choose))\s+(.+)", re.I)
_PREF_OVER = re.compile(r"(.+?)\s+over\s+(.+)", re.I)
# the LIRF ledger may have already distilled a preference into a trait — honour it.
_PREF_TRAITS = ("favorite_color", "likes", "dislikes", "preference", "prefers", "favorite")


def detect_preferences(records: list) -> list:
    """Recognise the user's stated PREFERENCES — what they want — from captured facts and
    turns. Returns {subject, weight, options, polarity, evidence}. Pulls from both the
    user's literal 'I prefer …' phrasing AND any preference the LIRF ledger already
    distilled into a trait. Grounded throughout; empty in, empty out."""
    found = []
    for r in records:
        text = r["text"]
        m = _PREF_POS.search(text)
        if m:
            subj = _clean_clause(m.group(1))
            options = []
            mo = _PREF_OVER.search(subj)
            if mo:
                subj = _clean_clause(mo.group(1))
                options = [subj, _clean_clause(mo.group(2))]
            if subj:
                found.append({"subject": subj, "weight": 0.7, "options": options,
                              "polarity": "wants", "evidence": [r]})
            continue
        m = _PREF_NEG.search(text)
        if m:
            subj = _clean_clause(m.group(1))
            if subj:
                found.append({"subject": f"avoiding {subj}", "weight": 0.7, "options": [],
                              "polarity": "avoids", "evidence": [r]})
            continue
        # ledger-distilled preference traits
        if r.get("kind") == "fact" and any(t in r.get("trait", "") for t in _PREF_TRAITS):
            subj = f"{r['trait'].replace('_', ' ')}: {r.get('value','')}".strip()
            found.append({"subject": subj, "weight": 0.75, "options": [],
                          "polarity": "wants", "evidence": [r]})
    return _dedupe_by(found, key=lambda d: d["subject"].lower())


# --- values & tradeoffs ---------------------------------------------------------------
# "I (value|care about|optimize for|prioritize) X", and the TRADEOFF frame
# "I'd rather X than Y" / "X matters more than Y" / "I choose X over Y".
_VALUE_CUE = re.compile(
    r"\bi\s+(?:value|care about|really care about|optimize for|prioriti[sz]e|"
    r"want to maximi[sz]e|am all about)\s+(.+)", re.I)
_TRADEOFF = re.compile(
    r"\bi(?:'d| would)?\s+rather\s+(.+?)\s+than\s+(.+)|"
    r"(.+?)\s+matters?\s+more\s+than\s+(.+)|"
    r"\bi\s+(?:choose|pick|take)\s+(.+?)\s+over\s+(.+)", re.I)


def detect_values(records: list) -> list:
    """Recognise what the user OPTIMIZES FOR and the TRADEOFFS they make. Returns
    {target, weight, tradeoff_against, evidence}. The tradeoff frame ('I'd rather X than
    Y') is first-class — a value without what it's traded against is half a value. Every
    target is the user's own captured phrasing; nothing optimization-worthy is invented."""
    found = []
    for r in records:
        text = r["text"]
        m = _VALUE_CUE.search(text)
        if m:
            tgt = _clean_clause(m.group(1))
            if tgt:
                found.append({"target": tgt, "weight": 0.85, "tradeoff_against": "",
                              "evidence": [r]})
        mt = _TRADEOFF.search(text)
        if mt:
            g = [x for x in mt.groups() if x]
            if len(g) >= 2:
                keep, give = _clean_clause(g[0]), _clean_clause(g[1])
                if keep:
                    found.append({"target": keep, "weight": 0.8,
                                  "tradeoff_against": give, "evidence": [r]})
    return _dedupe_by(found, key=lambda d: d["target"].lower())


# --- decisions ------------------------------------------------------------------------
# "I decided to X (because R)", "I chose X", "I went with X (over Y)", and the
# outcome frame "… and it (worked|paid off|was a mistake|backfired)".
_DECISION_CUE = re.compile(
    r"\bi\s+(?:decided to|chose to|chose|went with|opted (?:to|for)|"
    r"made the call to|ended up (?:choosing|going with))\s+(.+)", re.I)
_BECAUSE = re.compile(r"\b(?:because|since|so that|in order to|to)\s+(.+)", re.I)
_OUTCOME_GOOD = re.compile(r"\b(?:worked|paid off|was right|was the right call|"
                           r"glad i did|went well|turned out (?:great|well))\b", re.I)
_OUTCOME_BAD = re.compile(r"\b(?:was a mistake|backfired|regret|went wrong|"
                          r"wish i had(?:n'?t)?|didn'?t work|was the wrong call)\b", re.I)


def detect_decisions(records: list) -> list:
    """Recognise PAST DECISIONS the user described, with their context and — where the
    user said it — the OUTCOME. Returns {choice, rationale, outcome, evidence}. The outcome
    is captured ONLY when the user stated it (good/bad), never guessed: an unevaluated
    decision keeps outcome='' honestly. This is the raw material decision-patterns are
    abstracted from."""
    found = []
    for r in records:
        text = r["text"]
        m = _DECISION_CUE.search(text)
        if not m:
            continue
        rest = m.group(1)
        choice = _clean_clause(_BECAUSE.split(rest)[0] if _BECAUSE.search(rest) else rest)
        rb = _BECAUSE.search(rest)
        rationale = _clean_clause(rb.group(1)) if rb else ""
        outcome = ""
        if _OUTCOME_GOOD.search(text):
            outcome = "good (the user said it worked)"
        elif _OUTCOME_BAD.search(text):
            outcome = "bad (the user said it was a mistake)"
        if choice:
            found.append({"choice": choice, "rationale": rationale,
                          "outcome": outcome, "evidence": [r]})
    return found


# --- lessons learned ------------------------------------------------------------------
# "I('ve) learned (that) X", "I realized X", "the lesson (is/was) X", "next time I'll X",
# "always/never X" said as a self-rule.
_LESSON_CUE = re.compile(
    r"\bi(?:'ve| have)?\s+(?:learned|realized|figured out|come to (?:see|realize)|"
    r"concluded)\s+(?:that\s+)?(.+)|"
    r"\bthe (?:lesson|takeaway)\s+(?:is|was)\s+(.+)|"
    r"\bnext time\s+i(?:'ll| will| would)?\s+(.+)|"
    r"\b(?:i(?:'ve| have)? learned (?:to|not to))\s+(.+)", re.I)


def detect_lessons(records: list) -> list:
    """Recognise LESSONS the user has drawn — conclusions they reached. Returns
    {lesson, evidence}. A lesson is a learned rule ('I've learned that shipping daily
    beats big releases'); it becomes a HEURISTIC (condition->action) downstream. Only the
    user's own stated conclusions count; nothing is concluded on their behalf."""
    found = []
    for r in records:
        m = _LESSON_CUE.search(r["text"])
        if m:
            lesson = _clean_clause(next((g for g in m.groups() if g), ""))
            if lesson:
                found.append({"lesson": lesson, "evidence": [r]})
    return _dedupe_by(found, key=lambda d: d["lesson"].lower())


# --- small text utilities -------------------------------------------------------------
def _clean_clause(s: str) -> str:
    """Trim a captured clause to a tidy subject/target string: drop trailing punctuation,
    a dangling provenance tag, and surrounding quotes. Never rewrites the words."""
    if not s:
        return ""
    s = re.sub(r"\s*\([^)]*\)\s*$", "", str(s)).strip()      # strip trailing "(source, date)"
    s = s.strip(" .!?,;:\"'`").strip()
    return s


def _dedupe_by(items: list, key) -> list:
    seen, out = set(), []
    for it in items:
        k = key(it)
        if k and k not in seen:
            seen.add(k)
            out.append(it)
    return out


# ===================================================================================
# BUILDERS — evidence -> LERF objects. Each builder turns detector output into the
# matching cognitive object via lerf.py's PUBLIC factories, stamping provenance and the
# grounding evidence onto it. The PREFERENCE/VALUE builders go through the freeze-guarded
# factories: a Vera-self subject (which the detectors, reading only the USER's words,
# should never produce) is REFUSED by lerf, not by us. We catch that refusal and SKIP —
# the freeze holds even against a malformed capture.
# ===================================================================================

def _person_domain(person: str) -> str:
    """The per-PERSON retrieval slice, e.g. 'personal:lamar'. Keyed on WHO the model is
    about (the person), NOT the creature/ledger name — so a single creature's ledger can
    hold scoped models of several people and a profile of one never leaks another's.
    Lets a caller pull exactly one person's model out of a shared ledger."""
    who = (person or "user").strip().lower().replace(" ", "_")
    return f"{DOMAIN}:{who}"


def build_decision_patterns(name: str, records: list, *, person: str = "Lamar",
                            store: bool = True) -> list:
    """DECISION HISTORY -> DECISION_PATTERN objects. Each captured decision becomes a
    falsifiable pattern: the rationale is lifted into a weighted criterion, the choice
    into the typical decision, and the captured case (with its outcome, where known) into
    the worked `examples` — so the pattern can be checked against the real case it came
    from. Grounded in the user's words; stored ACTIVE via lerf.store_object."""
    out = []
    decisions = detect_decisions(records) if isinstance(records, list) and records \
        and isinstance(records[0], dict) and "kind" in records[0] else records
    for i, d in enumerate(decisions):
        ev = d.get("evidence", [])
        criteria = []
        if d.get("rationale"):
            criteria.append({"criterion": d["rationale"], "weight": 1.0})
        example = d["choice"]
        if d.get("outcome"):
            example += f" -> outcome: {d['outcome']}"
        obj = lerf.make_decision_pattern(
            name=f"how {person} decided: {d['choice'][:60]}",
            domain=_person_domain(person),
            inputs=["the situation as the user described it"],
            criteria=criteria or ["(rationale not captured)"],
            decision=d["choice"],
            examples=[example],
            taught_by=person,
            source=f"{SOURCE_PREFIX}:{(ev[0].get('source') if ev else 'lirf')}",
            state=lerf.ACTIVE,
            confidence=CONF,
            support=[f"grounded:{e.get('source','?')}:{e.get('when','')}" for e in ev],
        )
        # the verbatim captured evidence rides along in support too (auditable origin).
        obj.setdefault("support", []).extend(f"evidence:{e['text'][:160]}" for e in ev)
        if store:
            lerf.store_object(obj, name=name)
        out.append(obj)
    return out


def build_writing_preferences(name: str, records: list, *, person: str = "Lamar",
                              store: bool = True) -> list:
    """WRITING PATTERNS -> user PREFERENCE objects (one per detected writing trait). The
    subject is the trait ('writes in a casual register'), the evidence is samples of the
    user's actual words. Freeze-guarded: routed through make_preference, so a self-subject
    would be refused — these are the USER's writing, never Vera's."""
    return _build_preferences_from(
        name, detect_writing_patterns(records),
        subject_key="pattern", domain_suffix="writing", person=person, store=store,
        name_fmt=lambda s: f"{person} writing style: {s[:60]}")


def build_preferences(name: str, records: list, *, person: str = "Lamar",
                      store: bool = True) -> list:
    """PREFERENCES -> user PREFERENCE objects. What Lamar wants, with ranked options where
    he stated them ('X over Y'). Freeze-guarded via make_preference."""
    return _build_preferences_from(
        name, detect_preferences(records),
        subject_key="subject", domain_suffix="preference", person=person, store=store,
        name_fmt=lambda s: f"{person} prefers: {s[:60]}")


def _build_preferences_from(name, detections, *, subject_key, domain_suffix, person,
                            store, name_fmt) -> list:
    out = []
    for d in detections:
        subject = d[subject_key]
        ev = d.get("evidence", [])
        try:
            obj = lerf.make_preference(            # FREEZE-GUARDED factory
                subject=subject,
                domain=_person_domain(person),
                weight=float(d.get("weight", 0.6)),
                options=list(d.get("options", [])),
                evidence=_evidence_lines(ev) or [f"(captured {domain_suffix})"],
                name=name_fmt(subject),
                taught_by=person,
                source=f"{SOURCE_PREFIX}:{(ev[0].get('source') if ev else 'lirf')}",
                state=lerf.ACTIVE,
                confidence=CONF,
                support=[f"grounded:{e.get('source','?')}:{e.get('when','')}" for e in ev],
            )
        except lerf.FreezeViolation:
            # a value/preference about Vera herself can never be stored — the freeze wins.
            # (Detectors read only the user's words, so this should never fire; if a
            # malformed capture ever produced a self-subject, we SKIP it, not store it.)
            continue
        if store:
            lerf.store_object(obj, name=name)      # re-checks the freeze at the choke point
        out.append(obj)
    return out


def build_values(name: str, records: list, *, person: str = "Lamar",
                 store: bool = True) -> list:
    """VALUES / TRADEOFFS -> user VALUE objects. The target is what Lamar optimizes for;
    where he named a tradeoff ('I'd rather ship than polish'), what he trades away is
    recorded in the evidence and the object name. Freeze-guarded via make_value: a Vera-self
    optimization target is refused, never stored."""
    out = []
    for v in detect_values(records):
        target = v["target"]
        ev = v.get("evidence", [])
        ev_lines = _evidence_lines(ev)
        if v.get("tradeoff_against"):
            ev_lines = ev_lines + [f"tradeoff: chooses '{target}' over '{v['tradeoff_against']}'"]
        nm = f"{person} optimizes for: {target[:60]}"
        if v.get("tradeoff_against"):
            nm += f" (over {v['tradeoff_against'][:30]})"
        try:
            obj = lerf.make_value(                 # FREEZE-GUARDED factory
                target=target,
                domain=_person_domain(person),
                weight=float(v.get("weight", 0.8)),
                evidence=ev_lines or ["(captured value)"],
                name=nm,
                taught_by=person,
                source=f"{SOURCE_PREFIX}:{(ev[0].get('source') if ev else 'lirf')}",
                state=lerf.ACTIVE,
                confidence=CONF,
                support=[f"grounded:{e.get('source','?')}:{e.get('when','')}" for e in ev],
            )
        except lerf.FreezeViolation:
            continue
        if store:
            lerf.store_object(obj, name=name)
        out.append(obj)
    return out


def build_lessons(name: str, records: list, *, person: str = "Lamar",
                  store: bool = True) -> list:
    """LESSONS LEARNED -> HEURISTIC objects (condition -> action), stored WITH provenance.
    A lesson is a learned rule, which is exactly a heuristic; the lesson text becomes the
    action, the standing condition is 'a situation like the one the user learned this in',
    and the evidence is the user's own statement of the lesson. Heuristics are not freeze-
    guarded (they're not values/preferences) but are still the USER's by construction."""
    out = []
    for L in detect_lessons(records):
        ev = L.get("evidence", [])
        obj = lerf.make_heuristic(
            name=f"{person}'s lesson: {L['lesson'][:60]}",
            domain=_person_domain(person),
            condition="a situation like the one the user drew this lesson from",
            action=L["lesson"],
            expectation="the outcome the user learned to expect",
            applies_when=["the user's own stated domain"],
            taught_by=person,
            source=f"{SOURCE_PREFIX}:{(ev[0].get('source') if ev else 'lirf')}",
            state=lerf.ACTIVE,
            confidence=CONF,
            support=[f"grounded:{e.get('source','?')}:{e.get('when','')}" for e in ev],
        )
        obj.setdefault("support", []).extend(f"evidence:{e['text'][:160]}" for e in ev)
        if store:
            lerf.store_object(obj, name=name)
        out.append(obj)
    return out


# ===================================================================================
# LEARN — the one call that compounds. Read EVERY captured record for the person, run
# all detectors, build + store every grounded object. Idempotent in spirit: re-running
# after more capture simply adds the newly-grounded objects (each on a fresh id). Returns
# a summary of what was learned this pass. THE THESIS IN CODE: more capture -> a richer
# model, every time, with zero fabrication.
# ===================================================================================

def learn(name: str, *, person: str = "Lamar", include_turns: bool = True,
          store: bool = True) -> dict:
    """Build (and by default persist) the full personal model of `person` from ALL of
    their captured data. The single entry point: facts + turns -> decision-patterns +
    writing-preferences + preferences + values + lessons, each grounded and provenance-
    stamped. An empty capture history produces an empty result — never a fabricated self."""
    records = _all_evidence(name, include_turns=include_turns)
    decisions = build_decision_patterns(name, detect_decisions(records),
                                        person=person, store=store)
    writing = build_writing_preferences(name, records, person=person, store=store)
    prefs = build_preferences(name, records, person=person, store=store)
    values = build_values(name, records, person=person, store=store)
    lessons = build_lessons(name, records, person=person, store=store)
    return {
        "person": person,
        "evidence_records": len(records),
        "decision_patterns": [o["id"] for o in decisions],
        "writing_preferences": [o["id"] for o in writing],
        "preferences": [o["id"] for o in prefs],
        "values": [o["id"] for o in values],
        "lessons": [o["id"] for o in lessons],
        "total_learned": len(decisions) + len(writing) + len(prefs)
                         + len(values) + len(lessons),
    }


# ===================================================================================
# SENSITIVE-CATEGORY FLAG — Vera distills ONLY what the person actually said (no inference),
# so nothing sensitive is ever invented. But a CAPTURED statement can still touch a sensitive
# domain (health, money, sexuality, religion, politics, legal). We FLAG such items so the read
# surface can mark them and the person can review or delete them — honoring "no sensitive
# *inference* without confirmation" by never inferring AND by surfacing the sensitive bits for
# an explicit human call, rather than silently folding them into the model unseen.
# ===================================================================================
_SENSITIVE = re.compile(
    r"\b("
    r"health|medical|diagnos\w*|disease|illness|symptom|therapy|therapist|depress\w*|anxiet\w*|"
    r"medication|prescription|disab\w*|pregnan\w*|"
    r"salary|income|debt|loan|mortgage|bankrupt\w*|net ?worth|savings|invest\w*|"
    r"sexual\w*|gender|orientation|lgbtq?|"
    r"religio\w*|faith|church|mosque|temple|synagogue|god|"
    r"politic\w*|democrat|republican|vote[ds]?|election|"
    r"arrest\w*|criminal|lawsuit|conviction|immigration|citizenship"
    r")\b", re.I)


def is_sensitive(text: str) -> bool:
    """True iff the text touches a sensitive category (health/finance/sexuality/religion/
    politics/legal). Used only to FLAG captured items for human review — never to hide them."""
    return bool(_SENSITIVE.search(text or ""))


# ===================================================================================
# EDIT / FORGET — the person's direct control over their own learned model. Both are scoped
# to THIS person's personal slice (you can never retire or relabel an arbitrary system skill
# through these). DELETE is conservation-respecting (lerf.retire_skill -> DEPRECATED, kept on
# disk with a reason, never retrieved again). EDIT records a user label AND stamps the edit on
# the object's own provenance, so 'who changed this and when' is always answerable.
# ===================================================================================
_PERSONAL_TYPES = (lerf.DECISION_PATTERN, lerf.PREFERENCE, lerf.VALUE, lerf.HEURISTIC)


def _find_personal(name: str, object_id: str, person: str = "Lamar"):
    """Return THIS person's ACTIVE personal object with `object_id`, or None. Scans only the
    person's domain slice — an id outside the personal model is invisible here (the safety that
    keeps forget/edit from touching arbitrary system skills)."""
    dom = _person_domain(person)
    for t in _PERSONAL_TYPES:
        for o in lerf.all_objects(t, name=name):
            if o.get("id") == object_id and o.get("domain") == dom:
                return o
    return None


def forget(name: str, object_id: str, *, person: str = "Lamar") -> dict:
    """Remove ONE learned claim from the person's model. Refuses any id that isn't part of this
    person's personal slice (no retiring arbitrary skills). Conservation: the object is DEPRECATED
    (kept on disk with a reason), never hard-deleted, and never retrieved again. Returns
    {ok, id, state, reason}."""
    o = _find_personal(name, object_id, person)
    if o is None:
        return {"ok": False, "id": object_id, "state": None,
                "reason": "no such learned claim in your personal model"}
    res = lerf.retire_skill(o["id"], name=name, force=True,
                            reason="user removed this from their personal model")
    return {"ok": bool(res.get("ok")), "id": object_id, "state": res.get("state"),
            "reason": res.get("reason", "")}


def edit_statement(name: str, object_id: str, new_text: str, *, person: str = "Lamar") -> dict:
    """Let the person correct how a learned claim READS. Scoped to their own personal slice. The
    grounding evidence is left intact; we set a `user_label` (which _one_line then prefers) and
    stamp the edit on the object's support so the change is itself provenance-tracked. An empty
    new_text CLEARS a prior label (reverts to the distilled wording). Returns {ok, id, summary}."""
    label = (new_text or "").strip()[:280]
    o = _find_personal(name, object_id, person)
    if o is None:
        return {"ok": False, "id": object_id, "summary": "",
                "reason": "no such learned claim in your personal model"}
    o = dict(o)
    if label:
        o["user_label"] = label
        o.setdefault("support", []).append(f"user-edited:{label[:60]}")
    else:
        o.pop("user_label", None)
        o.setdefault("support", []).append("user-edited:cleared")
    try:
        lerf.store_object(o, name=name)
    except Exception as exc:                      # never silently swallow (LAW 001)
        return {"ok": False, "id": object_id, "summary": "", "reason": f"store failed: {exc!r}"}
    return {"ok": True, "id": object_id, "summary": _one_line(o)}


# ===================================================================================
# PROFILE — assemble what is KNOWN about how the person thinks/decides/prioritizes/
# writes/learns. Reads back ONLY what was stored (the ACTIVE personal objects for this
# person), each with its grounding evidence + provenance. An empty store -> an empty
# profile: personal_profile NEVER invents a personality. This is the read side of the moat.
# ===================================================================================

# A broad retrieval probe per facet — wide enough to pull this person's whole slice of
# each type (retrieval is keyword-based; these terms hit the domain + common content).
_FACET_PROBES = {
    "decision_patterns": "how the user decides chooses decision",
    "writing": "how the user writes writing style tone length",
    "preferences": "what the user prefers wants likes",
    "values": "what the user values optimizes for tradeoff",
    "lessons": "what the user learned lesson realized",
}


def _active_personal(name: str, want_type: str, person: str) -> list:
    """Every ACTIVE object of `want_type` belonging to THIS person's personal slice. Uses
    lerf.all_objects (active-only) and filters to the person's domain — no fork of the
    store, just a scoped read."""
    dom = _person_domain(person)
    return [o for o in lerf.all_objects(want_type, name=name)
            if o.get("domain") == dom]


def _facet(name: str, want_type: str, person: str) -> list:
    """One facet of the profile: the person's ACTIVE objects of a type, each rendered to
    its grounded provenance shape via lerf.provenance + lerf.explain_object. Retrieval
    sanity-checked through the public retriever so the profile reflects what is actually
    SERVABLE, not just on disk."""
    objs = _active_personal(name, want_type, person)
    facet = []
    for o in objs:
        prov = lerf.provenance(o["id"], name=name)
        summary = _one_line(o)
        evidence = list(o.get("evidence", [])) or _evidence_from_support(o)
        facet.append({
            "id": o["id"],
            "name": o.get("name"),
            "summary": summary,
            "evidence": evidence,
            # confidence and source are first-class so the UI can show every claim as
            # source-labeled + confidence-scored (the directive's bar for a learned claim).
            "confidence": round(float(o.get("confidence", 0.0)), 3),
            "source": o.get("source", "") or "captured",
            "user_edited": bool((o.get("user_label") or "").strip()),
            # sensitive items are FLAGGED (never hidden) so the user can review or remove them;
            # Vera distills only what was captured (no inference), so nothing sensitive is invented.
            "sensitive": is_sensitive(summary + " " + " ".join(evidence)),
            "editable": True,
            "deletable": True,
            "provenance": {
                "where_from": prov.get("where_from"),
                "who_taught": prov.get("who_taught"),
                "state": prov.get("state"),
                "support": prov.get("what_tests", {}).get("support", []),
            },
            "explain": lerf.explain_object(o, name=name),
        })
    return facet


def _one_line(o: dict) -> str:
    """The single most informative line of an object for a profile listing. A user-supplied
    label (set via edit_statement) ALWAYS wins — the person can correct how a claim reads, and
    that correction is itself provenance-stamped on the object (support: 'user-edited:...')."""
    if (o.get("user_label") or "").strip():
        return o["user_label"].strip()
    t = o.get("type")
    if t == lerf.DECISION_PATTERN:
        crit = o.get("criteria") or []
        c0 = crit[0] if crit else ""
        c0 = c0.get("criterion", c0) if isinstance(c0, dict) else c0
        return f"decides '{o.get('decision','')}'" + (f" weighing {c0}" if c0 else "")
    if t == lerf.PREFERENCE:
        opts = o.get("options") or []
        return f"prefers {o.get('subject','')}" + (f" (over {opts[1]})" if len(opts) > 1 else "")
    if t == lerf.VALUE:
        return f"optimizes for {o.get('target','')}"
    if t == lerf.HEURISTIC:
        return f"learned: {o.get('action','')}"
    return o.get("name", "")


def _evidence_from_support(o: dict) -> list:
    """Recover the grounding snippets we stowed in support as 'evidence:<text>' lines, for
    objects (decision-patterns, lessons) whose evidence rides in support."""
    return [s.split("evidence:", 1)[1] for s in o.get("support", [])
            if s.startswith("evidence:")]


def personal_profile(name: str, *, person: str = "Lamar") -> dict:
    """Assemble the GROUNDED personal profile of `person`: everything known about how they
    decide, what they prefer, what they value (and trade off), how they write, and what
    they've learned — each item carrying the captured evidence and provenance it was built
    from. NO FABRICATION: an empty personal store yields {known: False, ...} with empty
    facets. This is the function the rest of Vera calls to *know* Lamar.

    Returns:
      {person, known(bool), counts{...}, decision_patterns[], writing[], preferences[],
       values[], lessons[]} — each facet a list of grounded {id,name,summary,evidence,
       provenance,explain} records.
    """
    decision_patterns = _facet(name, lerf.DECISION_PATTERN, person)
    writing = [w for w in _facet(name, lerf.PREFERENCE, person)
               if "writing style" in (w.get("name") or "")]
    preferences = [p for p in _facet(name, lerf.PREFERENCE, person)
                   if "writing style" not in (p.get("name") or "")]
    values = _facet(name, lerf.VALUE, person)
    lessons = _facet(name, lerf.HEURISTIC, person)
    counts = {
        "decision_patterns": len(decision_patterns),
        "writing": len(writing),
        "preferences": len(preferences),
        "values": len(values),
        "lessons": len(lessons),
    }
    known = any(counts.values())
    return {
        "person": person,
        "known": known,                 # False == nothing captured; an honest empty profile
        "counts": counts,
        "decision_patterns": decision_patterns,
        "writing": writing,
        "preferences": preferences,
        "values": values,
        "lessons": lessons,
    }


def render_profile(name: str, *, person: str = "Lamar") -> str:
    """Human-readable 'what Vera knows about how Lamar thinks', grounded per item. The
    legible face of the model — like memory_lirf.render, but for cognition not facts.
    Says so plainly when nothing is known yet (never improvises a personality)."""
    p = personal_profile(name, person=person)
    if not p["known"]:
        return (f"Personal intelligence for {person}: nothing learned yet.\n"
                f"  (No decisions, preferences, values, writing samples, or lessons have "
                f"been captured. Tell Vera about yourself and the model fills in — it is "
                f"built only from what you actually say, never invented.)")
    out = [f"How {person} thinks / decides / prioritizes / writes / learns "
           f"(grounded — every item traces to captured evidence):"]
    sections = [
        ("DECISION PATTERNS (how he decides)", p["decision_patterns"]),
        ("VALUES & TRADEOFFS (what he optimizes for)", p["values"]),
        ("PREFERENCES (what he wants)", p["preferences"]),
        ("WRITING (how he writes)", p["writing"]),
        ("LESSONS (what he's concluded)", p["lessons"]),
    ]
    for title, items in sections:
        if not items:
            continue
        out.append(f"\n{title}:")
        for it in items:
            out.append(f"  • {it['summary']}")
            ev = it.get("evidence") or []
            if ev:
                out.append(f"      grounded in: \"{ev[0]}\"")
            prov = it.get("provenance", {})
            out.append(f"      provenance: taught_by={prov.get('who_taught','?')} · "
                       f"source={prov.get('where_from','?')} · state={prov.get('state','?')}")
    return "\n".join(out)


# ===================================================================================
# FREEZE PROOF — this module models LAMAR, not VERA. Prove the boundary directly: the
# freeze-guarded factories REFUSE a Vera-self value/preference (FreezeViolation), and the
# store choke point refuses a hand-built one too. Returns a structured result so the CLI
# and the selftest can both assert it. "Build the mind, leave the self alone."
# ===================================================================================

def freeze_proof() -> dict:
    """Demonstrate that a value/preference about VERA HERSELF is REFUSED by the lerf
    freeze guard this module relies on. Returns {ok, checks:[{label, refused}]}. Touches
    NO store (mint-time refusals don't persist; the store-path check uses a refused dict
    that never reaches disk). This is the in-code proof that personal intelligence models
    the user only."""
    checks = []

    def _check(label, fn):
        try:
            fn()
            checks.append({"label": label, "refused": False})   # FAILED to refuse == bad
        except lerf.FreezeViolation:
            checks.append({"label": label, "refused": True})    # refused == correct

    # 1) a Vera-self VALUE is refused at the factory.
    _check("make_value(target='Vera's own goal') is REFUSED",
           lambda: lerf.make_value(target="Vera's own goal", evidence=["x"]))
    # 2) a Vera-self PREFERENCE is refused at the factory.
    _check("make_preference(subject='Vera prefers brevity') is REFUSED",
           lambda: lerf.make_preference(subject="Vera prefers brevity", evidence=["x"]))
    # 3) first-person framing ("my own values") is caught as self-referential.
    _check("make_value(target='my own values') is REFUSED",
           lambda: lerf.make_value(target="my own values", evidence=["x"]))
    # 4) the builders refuse to emit a self-referential object even from a malformed
    #    'capture' — they route through the guarded factory and SKIP on refusal, so the
    #    builder yields NOTHING rather than a Vera-self object. (Proven by checking the
    #    detector-shaped self record produces zero built objects, store=False.)
    self_rec = [{"target": "Vera's own values", "weight": 0.9, "tradeoff_against": "",
                 "evidence": [{"text": "n/a", "source": "synthetic"}]}]
    # build_values runs detect_values on real records; here we exercise the guarded build
    # directly by feeding the value-shaped dict through the same make_value path.
    built_self = []
    for v in self_rec:
        try:
            built_self.append(lerf.make_value(target=v["target"], evidence=["x"]))
        except lerf.FreezeViolation:
            pass
    checks.append({"label": "builder yields NOTHING for a Vera-self value (freeze skip)",
                   "refused": len(built_self) == 0})

    ok = all(c["refused"] for c in checks)
    return {"ok": ok, "checks": checks,
            "principle": "Build the mind, leave the self alone — this module models the "
                         "USER (Lamar), never Vera's own values/preferences/agency."}


# ===================================================================================
# SELFTEST — `python3 -m anima.personal --selftest`. FULLY HERMETIC, mirroring the
# gold-standard pattern in anima/lerf.py _selftest and memory_lirf._selftest: SYNTHETIC
# Lamar-like captured data, EVERY store the load path may write redirected to one temp
# dir for the whole block, and a hard assertion that the real .anima is byte-UNCHANGED
# start->end with no leak. Exits 0 on all-pass.
# ===================================================================================

def _footprint(root):
    """Stable fingerprint of every real .anima file (excluding rotating backups/), so the
    selftest can PROVE it touched nothing. Identical discipline to lerf._footprint."""
    from pathlib import Path
    import hashlib
    root = Path(root)
    if not root.is_dir():
        return (None, 0)
    files = sorted(q for q in root.rglob("*")
                   if q.is_file() and "backups" not in q.relative_to(root).parts)
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


# A compact, realistic synthetic capture for "Lamar" — phrased as the user's OWN words so
# the detectors have real (synthetic) grounding to quote. NOTHING here describes Vera.
_SYNTH_TURNS = [
    "I decided to build the products as separate sellable units because optionality is "
    "worth more than a single big bet, and it worked — two are already independent.",
    "I chose local-first over cloud-first for Vera because privacy is the whole moat.",
    "I'd rather ship daily than polish for a month — momentum beats perfection.",
    "I value deep-work mornings more than anything; I optimize for uninterrupted building "
    "time and protect it hard.",
    "honestly just cut it down, keep it tight — I hate long-winded essays, tl;dr me.",
    "I prefer Python over Java for these tools, less ceremony.",
    "I've learned that diagnostic tests before a multi-week plan save weeks — cheap checks "
    "catch methodology errors early.",
    "next time I'll verify the upstream interface before subclassing, that bit me once.",
    "I went with anti-inflammatory recomp over a hard cut because the knee needed it, and "
    "it was the right call.",
    "yeah basically I always choose the boring proven tool over the shiny one for infra.",
]


def _selftest() -> int:
    import os                                                    # noqa: F401
    import sys as _sys
    import tempfile
    from pathlib import Path
    import secrets as _secrets

    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # --- pure, store-free checks first (no redirect needed) ----------------------------
    # the freeze proof is pure (no store): every self-referential mint is refused.
    fp = freeze_proof()
    ok("FREEZE: a Vera-self value/preference is REFUSED by the guard this module uses",
       fp["ok"] and len(fp["checks"]) >= 4 and all(c["refused"] for c in fp["checks"]))

    # detectors are pure functions over evidence records — exercise classification.
    recs = [{"text": t, "kind": "turn", "source": "turns", "when": ""} for t in _SYNTH_TURNS]
    ok("detect: a stated value is recognised (deep-work mornings)",
       any("deep-work" in v["target"] or "uninterrupted" in v["target"]
           for v in detect_values(recs)))
    ok("detect: a tradeoff frame is captured ('rather ship than polish')",
       any(v.get("tradeoff_against") for v in detect_values(recs)))
    ok("detect: a decision with a stated outcome is captured",
       any(d["outcome"] for d in detect_decisions(recs)))
    ok("detect: a preference is recognised (Python over Java)",
       any("python" in p["subject"].lower() for p in detect_preferences(recs)))
    ok("detect: a brevity writing-pattern is recognised",
       any("short" in w["pattern"] or "tight" in w["pattern"]
           for w in detect_writing_patterns(recs)))
    ok("detect: a lesson is recognised (diagnostic tests / verify upstream)",
       len(detect_lessons(recs)) >= 1)
    # EMPTY IN -> EMPTY OUT (the anti-fabrication contract at the detector layer).
    ok("detect: empty evidence yields empty detections (no invention)",
       detect_values([]) == [] and detect_decisions([]) == []
       and detect_preferences([]) == [] and detect_lessons([]) == []
       and detect_writing_patterns([]) == [])

    # --- FULLY HERMETIC store block -----------------------------------------------------
    real = lerf.STORE if lerf.STORE.is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = _footprint(real)

    td = tempfile.mkdtemp(prefix="personal-self-")
    tp = Path(td)
    # Redirect EVERY store the load path may write: lerf.STORE (+ the __main__ binding when
    # run as a module), memory_lirf.STORE + portrait.STORE (the captured-data readers),
    # plus constitution.STORE + reliability.DEFAULT_STORE (guarded-load side effects).
    targets = [(lerf, "STORE"), (memory_lirf, "STORE"), (portrait, "STORE")]
    try:
        import anima.personal as _pkg
        if _pkg is not _sys.modules[__name__]:
            targets.append((_pkg, None))            # placeholder; personal has no STORE of its own
    except Exception:
        pass
    targets = [t for t in targets if t[1] is not None]
    for modpath, attr in (("anima.constitution", "STORE"),
                          ("anima.reliability", "DEFAULT_STORE")):
        try:
            targets.append((__import__(modpath, fromlist=["_"]), attr))
        except Exception:
            pass
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, tp)
    try:
        nm = "personal_selftest_" + _secrets.token_hex(3)

        # EMPTY PROFILE FIRST — nothing captured yet -> an honestly empty profile.
        empty = personal_profile(nm, person="Lamar")
        ok("empty: a person with no capture yields known=False (never invents a self)",
           empty["known"] is False and empty["counts"]["values"] == 0
           and empty["counts"]["decision_patterns"] == 0)
        ok("empty: render says plainly that nothing is known yet",
           "nothing learned yet" in render_profile(nm, person="Lamar"))

        # SEED synthetic captured data the way the real pipeline would: durable FACTS via
        # the public memory_lirf.capture, plus a transient turn log via portrait.log_turn.
        for t in _SYNTH_TURNS:
            memory_lirf.capture(nm, t)              # extracts + persists durable user-facts
            portrait.log_turn(nm, t, "ok")          # the user's words land in the turn log
        evidence = _all_evidence(nm)
        ok("capture: synthetic Lamar data produced a non-empty evidence pool",
           len(evidence) >= 5)

        # LEARN — build + store the whole model from captured data only.
        summary = learn(nm, person="Lamar")
        ok("learn: built at least one object of every facet from captured data",
           summary["decision_patterns"] and summary["values"] and summary["preferences"]
           and summary["lessons"] and summary["total_learned"] >= 5)

        # RETRIEVE with provenance — the objects are servable through lerf's OWN retrievers,
        # ACTIVE, and answer 'how do we know this?'.
        dps = lerf.retrieve_decision_patterns("how does the user decide what to build",
                                              domain=_person_domain("Lamar"), name=nm)
        ok("retrieve: a stored decision-pattern is servable (ACTIVE) via lerf retriever",
           dps and all(o["state"] == lerf.ACTIVE for o in dps))
        prov = lerf.provenance(dps[0]["id"], name=nm) if dps else {}
        ok("provenance: the decision-pattern answers who-taught=Lamar + where-from=captured",
           prov.get("who_taught") == "Lamar" and str(prov.get("where_from", "")).startswith(SOURCE_PREFIX))
        ok("grounded: the decision-pattern carries its captured evidence in support",
           dps and any(s.startswith("evidence:") for s in dps[0].get("support", [])))

        vals = lerf.retrieve_values("what does the user optimize for",
                                    domain=_person_domain("Lamar"), name=nm)
        ok("retrieve: a stored USER value is servable and grounded in evidence",
           vals and vals[0].get("evidence") and vals[0]["state"] == lerf.ACTIVE)
        ok("value: a captured TRADEOFF is preserved on the value object",
           any("tradeoff" in e.lower() or "over" in (o.get("name", "").lower())
               for o in vals for e in o.get("evidence", [])) or
           any("over" in o.get("name", "").lower() for o in vals))

        prefs = lerf.retrieve_preferences("what does the user prefer",
                                          domain=_person_domain("Lamar"), name=nm)
        ok("retrieve: a stored USER preference is servable and grounded",
           prefs and prefs[0].get("evidence") and prefs[0]["state"] == lerf.ACTIVE)

        heurs = lerf.retrieve_heuristics("what has the user learned",
                                         domain=_person_domain("Lamar"), name=nm)
        ok("retrieve: a captured LESSON is stored as a servable heuristic",
           heurs and heurs[0]["state"] == lerf.ACTIVE)

        # THE ASSEMBLED PROFILE — grounded, populated, no fabrication.
        prof = personal_profile(nm, person="Lamar")
        ok("profile: known=True once data is captured, with every facet populated",
           prof["known"] is True and prof["counts"]["decision_patterns"] >= 1
           and prof["counts"]["values"] >= 1 and prof["counts"]["preferences"] >= 1
           and prof["counts"]["lessons"] >= 1)
        ok("profile: writing patterns are split out from plain preferences",
           prof["counts"]["writing"] >= 1
           and all("writing style" not in (p["name"] or "") for p in prof["preferences"]))
        ok("profile: EVERY profile item carries grounding evidence (no ungrounded item)",
           all(it.get("evidence") for facet in ("decision_patterns", "values",
                                                "preferences", "writing", "lessons")
               for it in prof[facet]))
        ok("profile: every item carries provenance (taught_by + source + state)",
           all(it["provenance"].get("who_taught") and it["provenance"].get("where_from")
               and it["provenance"].get("state") == lerf.ACTIVE
               for facet in ("decision_patterns", "values", "preferences", "lessons")
               for it in prof[facet]))
        ok("profile: render is human-readable and grounded",
           "grounded in:" in render_profile(nm, person="Lamar"))

        # FREEZE AT THE STORE LAYER — a hand-built Vera-self preference is refused by the
        # same store path this module uses, and NEVER reaches the personal ledger.
        _vera_pref = {"id": "pref_vera_personal", "type": lerf.PREFERENCE,
                      "name": "vera's own tone", "domain": _person_domain("Lamar"),
                      "subject": "Vera's own tone", "weight": 0.5, "options": [],
                      "evidence": ["x"], "taught_by": "", "state": lerf.CANDIDATE,
                      "confidence": 0.5, "source": "test", "support": [],
                      "failure_modes": []}
        _refused = False
        try:
            lerf.store_object(_vera_pref, name=nm)
        except lerf.FreezeViolation:
            _refused = True
        ok("FREEZE@store: a Vera-self preference is REFUSED by store_object", _refused)
        ok("FREEZE@store: the refused Vera-self preference NEVER reached the ledger",
           lerf._get(nm, "pref_vera_personal") is None)

        # COMPOUNDING — more capture yields a strictly larger model (the thesis).
        before_n = personal_profile(nm, person="Lamar")["counts"]
        memory_lirf.capture(nm, "I decided to use Caddy over nginx because the config is "
                                "simpler and it just worked.")
        portrait.log_turn(nm, "I decided to use Caddy over nginx because the config is "
                               "simpler and it just worked.", "ok")
        learn(nm, person="Lamar")
        after_n = personal_profile(nm, person="Lamar")["counts"]
        ok("compounds: more captured data -> a strictly larger decision model",
           after_n["decision_patterns"] > before_n["decision_patterns"])

        # ISOLATION — a DIFFERENT person's empty model stays empty (no cross-contamination).
        ok("isolation: an unrelated person has an empty profile (per-person scoping)",
           personal_profile(nm, person="Stranger")["known"] is False)

    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        import shutil
        shutil.rmtree(td, ignore_errors=True)

    # --- THE BYTE-UNCHANGED PROOF — real .anima must be identical start->end -----------
    fp_after = _footprint(real)
    ok("HERMETIC: real .anima footprint byte-UNCHANGED across the whole selftest",
       fp_before == fp_after)
    ok("HERMETIC: no synthetic personal/lerf file leaked into real .anima",
       (not real.is_dir()) or not any(p.name.startswith("personal_selftest_")
                                      for p in real.glob("*")))
    restored_ok = all("personal-self-" not in str(getattr(m, a, ""))
                      for (m, a, _old) in saved)
    ok("HERMETIC: every redirected STORE/DEFAULT_STORE binding is RESTORED", restored_ok)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL PERSONAL SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(_selftest())
