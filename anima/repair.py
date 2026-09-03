"""
repair — the deterministic CONVERSATION-REPAIR seam (the supersede-the-last-fact primitive).

THE WALLPAPER THIS CLOSES
-------------------------
The Program Reality Audit + Pattern Observatory both flagged `conversation_repair` as the #1
WALLPAPER: a feature whose surface implies it works but whose live path does not. The killer
phrasing is the anchorless correction:

    (earlier)  "my dog's name is Rex"          -> LIRF stores dog_name = Rex   [active]
    (now)      "scratch that — not Rex, his name is Atlas"

The LIRF extractor only lifts a fact when the utterance carries the trait ANCHOR ("my dog ...").
"his name is Atlas" has no anchor, so `memory_lirf.extract()` returns NOTHING for that turn:
`Rex` LINGERS as the active value and `Atlas` is LOST. The correction silently fails — exactly
the kind of "looks handled, isn't" the no-wallpaper doctrine exists to kill.

WHAT THIS DOES
--------------
A deterministic seam that recognises a value CORRECTION and rebinds the most-recent same-slot
fact WITHOUT needing a fresh anchor:

  * it reads the OLD value the user is rejecting ("not Rex") and finds the active ledger row
    that currently holds it — that row's trait IS the slot (dog_name), even though the new
    utterance never names the slot;
  * it folds the NEW value ("Atlas") through the SAME `Facts.merge()` correction path every
    other fact uses, so the old value goes to history[] (reason "user-corrected", never deleted)
    and the new value becomes active at correction confidence;
  * it returns a labelled confirmation that the server ships through the SAME model-free #1-rule
    `final_output_gate` as every reply (no second return path, no LLM).

SAFETY (why it cannot mis-correct)
----------------------------------
The seam only supersedes a slot it can PROVE currently holds the rejected old value (or, on the
anchorless "scratch that … his name is X" form, an existing NAME-type row). If it cannot resolve
a concrete stored row it returns None and the turn falls through to the normal pipeline unchanged
— it never invents a slot and never hijacks a normal turn. List-valued traits (likes/dislikes)
are out of scope here (a list edit is a remove-one-item op, not a scalar supersede).

This module performs NO host action, imports no Argus code, writes only the LIRF ledger for the
named creature, and is fully hermetic under the gate's temp-store redirect (it goes through
`memory_lirf.Facts`, which honours the redirected STORE).
"""
from __future__ import annotations

import re

from . import memory_lirf as _ml

SELF = _ml.SELF

# Scalar NAME-type slots a correction may target on the anchorless ("his name is X") form.
# Deliberately excludes LIST_TRAITS — a list edit is a different operation.
_NAME_TRAITS = (
    "dog_name", "cat_name", "pet_name", "name", "middle_name",
    "son", "daughter", "child", "partner", "mother", "father",
    "brother", "sister", "friend",
)

# A strong signal the user is repairing/retracting a value they just stated.
_CUE = re.compile(
    r"\b(?:scratch that|actually|i meant|i mean|i said|correction|let me correct|"
    r"i misspoke|that'?s wrong|that'?s not right|no,?\s+(?:wait|sorry|it'?s|that'?s)|"
    r"oops|my bad|sorry,?\s+i meant)\b", re.I)

# The rejected OLD value: "not Rex", "not pizza". A bare token after "not".
_OLD = re.compile(r"\bnot\s+(?P<old>[A-Za-z][\w'’-]*)\b", re.I)

# A RESTATE/transcription correction: the user says the value they JUST gave was wrong and restates
# it ("that transcription was wrong, I said Atlas", "I meant Atlas", "no, I said Atlas"). Unambiguous
# correction frames only (NOT a bare conversational "I said yes") — so the seam supersedes the most-
# recent fact safely without an explicit old value or a name-clause.
_RESTATE = re.compile(
    r"\b(?:i\s+meant(?:\s+to\s+say)?|that\s+transcription\s+was\s+wrong|wrong\s+transcription|"
    r"i\s+(?:was\s+)?misheard|you\s+(?:mis)?heard\s+(?:me\s+)?wrong|you\s+misheard|"
    r"got\s+that\s+wrong|i\s+actually\s+said|no,?\s+i\s+said|i\s+didn'?t\s+say)\b", re.I)

# Does the utterance speak about a NAME (needed for the anchorless, no-old fallback)?
_NAME_CLAUSE = re.compile(r"\b(?:his|her|its|their)\s+name|\bname(?:'?s| is)\b", re.I)

# The corrected NEW value. Capitalised-name forms first (the killer class), then looser forms.
# (?-i:[A-Z]) forces a real capital so a lowercase function word can never be read as a name.
_NEW_PATTERNS = (
    re.compile(r"\b(?:his|her|its|their)\s+name(?:'?s| is|s)?\s+(?:actually\s+|now\s+)?(?P<new>(?-i:[A-Z])[\w'’-]+)", re.I),
    re.compile(r"\bname(?:'?s| is)\s+(?:actually\s+|now\s+)?(?P<new>(?-i:[A-Z])[\w'’-]+)", re.I),
    re.compile(r"\bi\s+(?:meant|mean|said)\s+(?:it'?s\s+|it\s+is\s+|actually\s+)?(?P<new>(?-i:[A-Z])[\w'’-]+)", re.I),
    re.compile(r"\bit'?s\s+(?:actually\s+|now\s+)?(?P<new>(?-i:[A-Z])[\w'’-]+)", re.I),
    re.compile(r"\bnot\s+[\w'’-]+\s*[,;:.—–-]+\s*(?P<new>(?-i:[A-Z])[\w'’-]+)", re.I),  # "not Rex, Atlas" / "not Rex — Atlas"
    re.compile(r"(?P<new>(?-i:[A-Z])[\w'’-]+)\s*,?\s+not\s+[\w'’-]+", re.I),                       # "Atlas, not Rex"
)


def _scalar(v):
    """First element of a list value, else the value itself (repair targets scalar slots)."""
    return v[0] if isinstance(v, list) and v else v


def detect(text: str):
    """Pure parse: is `text` a value CORRECTION? Returns {old, new, cue, name_clause} or None.

    Requires a NEW value AND either an explicit OLD to reject OR a strong correction cue paired
    with a name-clause. No store access — safe to call for MRI staging and the no-hijack guard.
    """
    t = text or ""
    if not t.strip():
        return None
    old_m = _OLD.search(t)
    old = _ml._clean(old_m.group("old")) if old_m else None

    new = None
    for rx in _NEW_PATTERNS:
        m = rx.search(t)
        if m:
            cand = _ml._clean(m.group("new"))
            if cand and not _ml._is_stopname(cand):
                new = cand
                break
    if not new:
        return None
    if old and _ml._norm_value(old) == _ml._norm_value(new):
        old = None  # "not Atlas … Atlas" — degenerate; drop the bogus old

    cue = bool(_CUE.search(t))
    name_clause = bool(_NAME_CLAUSE.search(t))
    restate = bool(_RESTATE.search(t))
    # Trigger on: an explicit rejected OLD value, OR a strong cue + a name-clause (anchorless name
    # correction), OR an unambiguous restate/transcription frame (supersede the most-recent fact).
    if old or (cue and name_clause) or restate:
        return {"old": old, "new": new, "cue": cue, "name_clause": name_clause, "restate": restate}
    return None


def classify_repair(text: str) -> bool:
    """Cheap boolean: does `text` look like a conversation-repair correction? (No store access.)"""
    return detect(text) is not None


def _resolve(facts, parsed) -> dict | None:
    """Find the concrete ACTIVE ledger row this correction supersedes, or None.

    Primary: the row whose current scalar value == the rejected OLD value (prove the slot).
    Fallback (no explicit old): the most-recent NAME-type active row, only when the utterance
    actually speaks about a name. Never targets a list trait.
    """
    old = parsed.get("old")
    if old:
        nv = _ml._norm_value(old)
        cands = [r for r in facts.rows
                 if r.get("status") == "active"
                 and r.get("trait") not in _ml.LIST_TRAITS
                 and _ml._norm_value(_scalar(r.get("value"))) == nv]
        cands.sort(key=lambda r: (r.get("entity") == SELF, r.get("updated", "")), reverse=True)
        return cands[0] if cands else None
    if parsed.get("name_clause"):
        cands = [r for r in facts.rows
                 if r.get("status") == "active" and r.get("trait") in _NAME_TRAITS]
        cands.sort(key=lambda r: r.get("updated", ""), reverse=True)
        return cands[0] if cands else None
    if parsed.get("restate"):
        # "I meant X" / "that transcription was wrong, I said X" — supersede the MOST-RECENT active
        # scalar fact (the value the user just gave). The supersede-the-last-turn primitive in its
        # purest form; list traits are excluded (a list edit is a different operation).
        cands = [r for r in facts.rows
                 if r.get("status") == "active" and r.get("trait") not in _ml.LIST_TRAITS]
        cands.sort(key=lambda r: r.get("updated", ""), reverse=True)
        return cands[0] if cands else None
    return None


_TRAIT_PHRASE = {
    "dog_name": "dog's name", "cat_name": "cat's name", "pet_name": "pet's name",
    "name": "name", "middle_name": "middle name",
    "son": "son's name", "daughter": "daughter's name", "child": "child's name",
    "partner": "partner's name", "mother": "mother's name", "father": "father's name",
    "brother": "brother's name", "sister": "sister's name", "friend": "friend's name",
    "employer": "employer", "occupation": "occupation", "lives": "location",
    "favorite_color": "favorite color", "car": "car", "birthday": "birthday",
}


def _trait_phrase(trait: str) -> str:
    return _TRAIT_PHRASE.get(trait, (trait or "").replace("_", " ") or "detail")


def confirmation(trait: str, old, new: str) -> str:
    """The labelled correction confirmation (deterministic, grounded in the user's own facts)."""
    phrase = _trait_phrase(trait)
    if old:
        return (f"Got it — I've updated your {phrase} from {_ml._fmt_value(old)} to {new}. "
                f"Thanks for the correction; I'll remember {new} from now on.")
    return (f"Got it — I've updated your {phrase} to {new}. "
            f"Thanks for the correction; I'll remember that from now on.")


def repair(name: str, text: str, cloud_safe: bool = False):
    """Perform the supersede for a correction utterance; return the labelled confirmation, or None.

    None means "not a resolvable correction" — the server's seam then falls through to the normal
    pipeline unchanged. The supersede goes through `Facts.merge()` with correction=True, so the old
    value is preserved in history[] (reason "user-corrected") and the new value becomes active at
    correction confidence. `cloud_safe` is accepted for call-site parity; the reply is fixed local
    text shipped straight to the user (it never transits a cloud provider), so nothing is redacted.
    """
    parsed = detect(text)
    if not parsed:
        return None
    f = _ml.Facts.load(name)
    row = _resolve(f, parsed)
    if row is None:
        return None
    trait = row.get("trait")
    prev = _scalar(row.get("value"))
    new = parsed["new"]
    if _ml._norm_value(prev) == _ml._norm_value(new):
        return None  # already that value — nothing to supersede
    cand = {
        "trait": trait,
        "value": new,
        "correction": True,
        "evidence": _ml._clean(text),
        "source": f"chat-correction {_ml._now()[:10]}",
        "entity": row.get("entity", SELF),
    }
    f.merge(cand)            # keyed on (entity, trait): prev -> history, new -> active @0.97
    f.save(name)
    return confirmation(trait, prev, new)


# --------------------------------------------------------------------------------------------
# selftest — the pure PARSE layer (no store). The end-to-end supersede + the live #1-rule gate
# are proven hermetically by scripts/certify_repair.py (the Rex -> Atlas killer test).
# --------------------------------------------------------------------------------------------
def _selftest() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("repair.detect() parse layer")
    print("=" * 60)
    cases_hit = [
        ("scratch that — not Rex, his name is Atlas", "Rex", "Atlas"),
        ("no, it's Atlas, not Rex", "Rex", "Atlas"),
        ("I meant Atlas, not Rex", "Rex", "Atlas"),
        ("actually his name is Atlas, not Rex", "Rex", "Atlas"),
        ("sorry, not Rex — Atlas", "Rex", "Atlas"),
        ("scratch that, his name is Atlas", None, "Atlas"),     # anchorless, no explicit old
        ("that transcription was wrong, I said Atlas", None, "Atlas"),  # restate / transcription
        ("I meant Atlas", None, "Atlas"),                       # bare restate frame
        ("no, I said Atlas", None, "Atlas"),                    # restate frame
    ]
    for text, old, new in cases_hit:
        d = detect(text) or {}
        ck(f"detect({text!r}) old={old} new={new}",
           d.get("new") == new and d.get("old") == old)

    cases_miss = [
        "how are you feeling today?",        # normal chat
        "my dog is Rex",                     # a fresh statement, not a correction
        "what's my dog's name?",             # a question
        "I'm not sure how I feel today",     # 'not' but no new value
        "is his name Rex or Atlas?",         # a question, no correction
        "thanks, that's perfect",            # nothing
    ]
    for text in cases_miss:
        ck(f"detect({text!r}) -> None (no hijack)", detect(text) is None)

    print("\nREPAIR PARSE SELFTEST: " + ("PASS" if not fails else f"FAIL ({len(fails)})"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
