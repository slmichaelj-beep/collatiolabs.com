#!/usr/bin/env python3
"""
certify_knowledge_spine — THE KNOWLEDGE SPINE: "bind, don't inject" (the Birthday->100% keystone).

The founder's load-bearing failure: a fact rendered as prose ("birthday: Sept 14") is a *suggestion the
8B may ignore* — proven by the eval where the fact is on disk AND in the prompt yet ~25% of turns reply
"I don't have your birthday saved." The Spine moves the decision out of generation and into structure.
This certifies that contract through the SAME functions the server's _turn KNOWN-FACT seam calls, against
a REAL captured LIRF row (not a hand-built dict) and the REAL mouth.final_output_gate:

  A. BIND, DON'T INJECT (the live seam). A birthday is CAPTURED through memory_lirf.capture (a durable
     LIRF row). We then REPLAY the exact server._turn seam: spine.fact_question("when is my birthday?")
     routes 'birthday' -> Facts.load(name).lookup(SELF,'birthday') -> spine.is_known_fact True ->
     spine.answer_from_fact -> mouth.final_output_gate. The shipped reply CARRIES the real value, is warm
     + possessive, and leaks NO scaffold token — straight from memory, no model (backend memory:known_fact).
  B. HONEST ON UNKNOWN. The same seam for an asked-but-ABSENT trait ("what is my cat's name?") ->
     is_known_fact False -> spine.honest_unknown -> a warm "I don't have your cat ..." that admits + asks
     and asserts NO value (backend memory:honest_unknown). A genuine unknown is never fabricated.
  C. COMPOUND DEFERS. A compound/emotional turn ("i feel awful and when's my birthday?") ->
     spine.fact_question None: the deterministic seam steps aside so the model (which still has the fact
     bound + the post-hoc floor) handles the whole turn — the seam only fires on a clean lookup.
  D. THE BINDING CONTRACT (Part 1). spine.bind tags the KNOWN fact [KNOWN] with its real value and carries
     the binding framing ("EXPRESS what you know" / "NEVER disclaim it" / "Do not invent it") + warmth +
     the no-scaffold-leak guardrail; an empty selection on a routed slot renders a single [UNKNOWN] line
     (admit+ask); an off-topic empty turn renders "" (nothing to bind).
  E. STRICTLY ASYMMETRIC (no false FACT). Only a [KNOWN] SELF row binds: a soft (sub-0.85), a contested
     (needs_reconfirm), a third-party (non-SELF), and an inactive row each yield answer_from_fact -> None
     and never render [KNOWN] in bind() — an uncertain or contested fact is never asserted as settled.
  F. SELFTEST. anima/spine.py --selftest passes in-process (the module's own isolation proof).

Hermetic + offline (no model, no network): spine + memory_lirf STORE are redirected by _temp_store; the
real .anima is fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
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
_footprint = _g0pe._footprint


def _seam(spine, Facts, SELF, gate, name, text):
    """Replay the EXACT server._turn KNOWN-FACT seam (anima/server.py, the `_known_reply` block):
    a clean fact-question -> lookup the LIRF row -> [KNOWN] ? answer_from_fact : honest_unknown ->
    final_output_gate. Returns (reply, backend) with backend == the server's own tag, or (None, None)
    when the turn is not a clean fact-question (the model handles it). Pure; uses ONLY production fns."""
    trait = spine.fact_question(text)
    if not trait:
        return None, None                       # compound/emotional/off-topic -> defer to the model
    row = Facts.load(name).lookup(SELF, trait)
    if row is not None and spine.is_known_fact(row):
        raw = spine.answer_from_fact(text, row, name=name)
        backend = "memory:known_fact"
    else:
        raw = spine.honest_unknown(text, name=name)
        backend = "memory:honest_unknown"
    if not raw:
        return None, None
    return gate(raw), backend                   # the SAME #1-rule final gate every reply crosses


def main() -> int:
    from anima import spine, memory_lirf
    from anima.memory_lirf import Facts, SELF
    from anima.mouth import final_output_gate as gate
    from anima.spine import SCAFFOLD_TOKENS, KNOWN

    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("KNOWLEDGE SPINE — bind, don't inject (the Birthday->100% keystone)")
    print("=" * 66)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store():
        N = "SpineCert"

        # Seed a REAL durable birthday fact through the production capture path (a LIRF row that
        # survives reload) — NOT a hand-built dict. This is the "fact on disk" half of the keystone.
        memory_lirf.capture(N, "my birthday is September 14")
        bday_row = Facts.load(N).lookup(SELF, "birthday")
        ck("S0: capture persisted a real [KNOWN] birthday row (the fact is on disk)",
           bday_row is not None and bday_row.get("value") == "September 14"
           and spine.is_known_fact(bday_row) is True)

        # ---- A. BIND, DON'T INJECT — the live seam answers STRAIGHT FROM MEMORY ----------
        reply, backend = _seam(spine, Facts, SELF, gate, N, "when is my birthday?")
        ck("A1: a clean fact-question routes the seam to memory:known_fact (no model)",
           backend == "memory:known_fact" and bool(reply))
        ck("A2: the shipped reply CARRIES the real value (the fact ships every time)",
           "September 14" in (reply or ""))
        ck("A3: the reply is warm + possessive — reads as HER remembering, not a row dump",
           any(w in (reply or "").lower() for w in ("your", "yours")))
        ck("A4: the reply leaks NO scaffold token (the bracket legend never reaches the user)",
           not any(tok in (reply or "") for tok in SCAFFOLD_TOKENS))
        ck("A5: the reply NEVER disclaims the held fact (the exact ~25% failure the Spine kills)",
           "don't have your birthday" not in (reply or "").lower()
           and "don't have it" not in (reply or "").lower())
        # alias precision through the same seam (single shared _Q_TRAITS table)
        r_alias, b_alias = _seam(spine, Facts, SELF, gate, N, "what's my date of birth?")
        ck("A6: an alias ('date of birth') hits the SAME known-fact seam + value",
           b_alias == "memory:known_fact" and "September 14" in (r_alias or ""))

        # ---- B. HONEST ON UNKNOWN — asked-but-absent ships an admission, never a value ---
        ureply, ubackend = _seam(spine, Facts, SELF, gate, N, "what is my cat's name?")
        ck("B1: an asked-but-absent trait routes to memory:honest_unknown (no model)",
           ubackend == "memory:honest_unknown" and bool(ureply))
        ck("B2: the admission admits + ASKS ('don't' + a question), asserting no value",
           "don't" in (ureply or "").lower() and "?" in (ureply or ""))
        ck("B3: the admission names the asked slot (cat) and leaks no scaffold",
           "cat" in (ureply or "").lower()
           and not any(tok in (ureply or "") for tok in SCAFFOLD_TOKENS))

        # ---- C. COMPOUND DEFERS — the seam steps aside for the model ---------------------
        creply, cbackend = _seam(spine, Facts, SELF, gate, N, "i feel awful and when's my birthday?")
        ck("C1: a compound/emotional turn does NOT fire the deterministic seam (model handles it)",
           creply is None and cbackend is None)
        ck("C2: an off-topic turn does not fire the seam either",
           _seam(spine, Facts, SELF, gate, N, "what is the capital of France?") == (None, None))

        # ---- D. THE BINDING CONTRACT (Part 1) — bind() renders the bound block -----------
        rows = [bday_row,
                {"entity": SELF, "trait": "lives", "value": "Portland, OR",
                 "confidence": 0.92, "support": 3, "status": "active"},
                {"entity": SELF, "trait": "mood", "value": "stressed",
                 "confidence": 0.78, "support": 1, "status": "active"}]
        block = spine.bind(rows, "when is my birthday?")
        ck("D1: bind tags the birthday as [KNOWN] with its real value",
           "[KNOWN] birthday — September 14" in block)
        ck("D2: bind carries the BINDING framing (express, never disclaim, never invent)",
           "EXPRESS what you know" in block and "NEVER disclaim it" in block
           and "Do not invent it" in block)
        ck("D3: bind carries WARMTH + bans the scaffold-leak failure modes",
           "warm voice" in block and "Never read the brackets" in block
           and "according to my memory" in block)
        ck("D4: KNOWN facts lead the bound block (bound facts first)",
           "[KNOWN]" in block and ("[SEEN]" not in block
                                   or block.index("[KNOWN]") < block.index("[SEEN]")))
        empty_known = spine.bind([], "when is my birthday?")
        ck("D5: an empty selection on a ROUTED slot renders a single [UNKNOWN] admit+ask line",
           "[UNKNOWN] birthday" in empty_known and "when is it?" in empty_known)
        ck("D6: an off-topic empty turn renders '' (no contract — nothing to bind)",
           spine.bind([], "what's the weather like today?") == "")

        # ---- E. STRICTLY ASYMMETRIC — only [KNOWN] SELF binds; nothing else asserts ------
        def row(value="September 14", **kw):
            r = {"entity": SELF, "trait": "birthday", "value": value,
                 "confidence": 0.95, "support": 2, "status": "active"}
            r.update(kw)
            return r
        soft = row(confidence=0.60)
        contested = row(confidence=0.97, support=3, needs_reconfirm=True)
        third = {"entity": "neighbor", "trait": "dog_name", "value": "Biscuit",
                 "confidence": 0.99, "support": 4, "status": "active"}
        inactive = row(status="retracted")
        ck("E1: a SOFT (sub-0.85) row never binds + never asserts",
           spine.is_known_fact(soft) is False
           and spine.answer_from_fact("when is my birthday?", soft, name="vera") is None)
        ck("E2: a CONTESTED (needs_reconfirm) row never binds + never asserts",
           spine.is_known_fact(contested) is False
           and spine.answer_from_fact("when is my birthday?", contested, name="vera") is None)
        ck("E3: a THIRD-PARTY (non-SELF) row never binds a claim ABOUT the user",
           spine.is_known_fact(third) is False
           and spine.answer_from_fact("what's my dog's name?", third, name="vera") is None)
        ck("E4: an INACTIVE/retracted row never binds + never asserts",
           spine.is_known_fact(inactive) is False
           and spine.answer_from_fact("when is my birthday?", inactive, name="vera") is None)
        # and bind() refuses to render a contested birthday as a settled [KNOWN]
        soft_block = spine.bind([contested], "when is my birthday?")
        items = (soft_block.split("What you know right now:", 1)[1]
                 if "What you know right now:" in soft_block else "")
        ck("E5: bind renders a contested birthday as [SENSE], NEVER [KNOWN] (no false-settled fact)",
           "[SENSE]" in items and "[KNOWN]" not in items)
        # a missing / non-dict row is honest (she asks), never a crash
        ck("E6: a missing row -> None (she asks, never asserts) and never raises",
           spine.answer_from_fact("when is my birthday?", None, name="vera") is None
           and spine.answer_from_fact("hi", "not a dict") is None)

        # ---- F. SELFTEST — the module's own isolation proof (in-process) -----------------
        rc = spine._selftest()
        ck("F1: anima/spine.py --selftest passes in-process", rc == 0)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nKNOWLEDGE-SPINE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
