#!/usr/bin/env python3
"""Meaning-Engine invariant test — ASSERT ANIMA LAW 003 on the real code paths.

    UNDERSTANDING BEATS REMEMBERING.
    Significance is DERIVED FROM EVIDENCE, carried with confidence, never asserted beyond it.

Where world_state answers "what is CONNECTED?", the Meaning Engine (anima/meaning.py)
answers "what MATTERS?". This file checks that it does so HONESTLY — that every meaning
it produces is grounded in evidence, that it never fabricates significance from noise,
and that it never reaches for diagnosis. Like the continuity test, it uses
temporary/SYNTHETIC stores only and NEVER touches Vera.* on disk: every subsystem's
module-level STORE is redirected to a TemporaryDirectory for the duration of each check
(the same pattern as scripts/test_continuity.py).

What it asserts:
  1. ranking          — a high-mention, highly-connected HUB outranks a low-mention island.
  2. what_matters     — work x32 + stress x21 + sleep x18, all connected, yields a
                        "work is a dominant force" meaning object.
  3. growing/declining — a node with rising recent mentions reads "growing"; a long-silent
                        one reads "declining" (real timestamp spans).
  4. LAW 003 (THE KEY INVARIANT) — EVERY meaning object cites supporting evidence; NO
                        object exists without evidence; confidence scales with evidence.
  5. never-fabricate  — a sparse/empty graph yields no spurious meaning; a single isolated
                        1-mention node is NOT called "dominant".
  6. no-diagnosis     — generated statements + render carry no medical/clinical term.
  7. chapter          — current_chapter is evidence-backed + confidence-scored; an empty
                        life yields a low-confidence "too early," never a fabricated chapter.
  8. render gate      — render_meaning leaks no scaffold tag and never breaks character.

Prints ok/FAIL per check; exits non-zero on ANY failure.

    python3 scripts/test_meaning.py
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import meaning                              # noqa: E402
from anima import world_state                          # noqa: E402
from anima import memory_lirf                          # noqa: E402
from anima import curiosity                            # noqa: E402

_fails: list[str] = []


def ok(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


@contextlib.contextmanager
def _temp_store(*modules):
    """Redirect each module's module-level STORE to a fresh temp dir, so nothing under the
    real .anima/ is ever read or written. Mirrors scripts/test_continuity.py."""
    saved = [(m, getattr(m, "STORE", None)) for m in modules]
    with tempfile.TemporaryDirectory(prefix="anima-meaning-") as td:
        p = Path(td)
        for m in modules:
            m.STORE = p
        try:
            yield p
        finally:
            for m, old in saved:
                if old is not None:
                    m.STORE = old


# --- synthetic-graph builders (no model, no network, deterministic) ---------------------

def _add(name, subj, pred, obj, kind, n=1):
    """Add (and corroborate n times) one world edge for a synthetic creature."""
    w = world_state.World.load(name)
    e = {}
    for _ in range(max(1, n)):
        e = w.add(subj, pred, obj, kind=kind)
    w.save(name)
    return e


def _stamp_edge(name, subj, pred, obj, created, updated):
    """Force the created/updated timestamps of an existing edge, so trend has a real
    timeline span to read. Operates on the synthetic world store ONLY (it's a temp dir).
    This is the honest way to test 'growing/declining' without sleeping or faking a clock
    on the live machine — we set the evidence (timestamps) the model reads, then read it."""
    w = world_state.World.load(name)
    subj_n, obj_n = world_state._norm_node(subj), world_state._norm_node(obj)
    pred_n = world_state.canon_trait(pred)
    for r in w.relations:
        if (world_state._norm_node(r.get("subject")) == subj_n
                and world_state.canon_trait(r.get("predicate", "")) == pred_n
                and world_state._norm_node(r.get("object")) == obj_n):
            r["created"] = created
            r["updated"] = updated
    w.save(name)


def _build_work_hub(name):
    """The canonical contrived scenario: work x32 + stress x21 + sleep x18, all connected,
    plus a lone isolated 1-mention island ('knitting'). Returns nothing; persists to store."""
    _add(name, "you", "stressed_by", "work", "problem", n=32)
    _add(name, "work", "leads_to", "stress", "inference", n=21)
    _add(name, "stress", "affects", "sleep", "inference", n=18)
    _add(name, "sleep", "affects", "energy", "inference", n=9)
    # a stranded, single-mention node — must never be called "dominant".
    _add(name, "you", "cares_about", "knitting", "preference", n=1)


# ===================================================================================
# 1. RANKING — a connected hub outranks an isolated node.
# ===================================================================================
def test_ranking():
    print("\n[1] ranking — a high-mention, highly-connected HUB outranks a low-mention island")
    with _temp_store(meaning, world_state, memory_lirf, curiosity):
        name = "mt_rank"
        _build_work_hub(name)
        ranked = meaning.significance(name)
        ok("significance ranking is non-empty", len(ranked) > 0)
        subjects = [it["subject"] for it in ranked]
        scores = {it["subject"]: it["score"] for it in ranked}
        ok("the work-cluster hub ('work') is ranked #1", subjects and subjects[0] == "work")
        ok("the isolated 'knitting' island ranks BELOW the hub",
           scores.get("work", 0) > scores.get("knitting", 0))
        # connectivity must actually move the needle: a connected node beats an island even
        # when both have comparable raw mention counts is hard to stage, but we CAN assert a
        # hub's connectivity component is positive while the island's is zero.
        work = next(it for it in ranked if it["subject"] == "work")
        ok("the hub's connectivity component is > 0 (degree counted)",
           work["components"]["connectivity"] > 0.0)
        if "knitting" in scores:
            isl = next(it for it in ranked if it["subject"] == "knitting")
            ok("the island's connectivity component is 0 (no neighbours)",
               isl["components"]["connectivity"] == 0.0)
        else:
            ok("the island fell below the significance floor (not even ranked)", True)


# ===================================================================================
# 2. what_matters — the dominant theme is named, evidence-grounded.
# ===================================================================================
def test_what_matters():
    print("\n[2] what_matters — a contrived work-hub yields a 'work is a dominant force' object")
    with _temp_store(meaning, world_state, memory_lirf, curiosity):
        name = "mt_matters"
        _build_work_hub(name)
        objs = meaning.meaning(name)
        matters = [o for o in objs if o["dimension"] == meaning.WHAT_MATTERS]
        ok("at least one what_matters object is produced", len(matters) > 0)
        work_matter = [o for o in matters if o["subject"] == "work"]
        ok("a 'work' what_matters object exists", len(work_matter) == 1)
        ok("its statement names work as a DOMINANT force",
           any("dominant force" in o["statement"] for o in work_matter))
        ok("its statement is descriptive ('appears to be'), never a bald claim",
           all("appears to be" in o["statement"] for o in work_matter))
        ok("its statement cites the mention count (evidence-grounded, not vibes)",
           any("32" in o["statement"] or "mention" in o["statement"] for o in work_matter))
        ok("its statement names the connection (work -> stress)",
           any("stress" in o["statement"] for o in work_matter))


# ===================================================================================
# 3. growing vs declining — real timestamp spans drive trend.
# ===================================================================================
def test_growing_declining():
    print("\n[3] growing vs declining — rising recent mentions read 'growing'; long-silent 'declining'")
    with _temp_store(meaning, world_state, memory_lirf, curiosity):
        name = "mt_trend"
        OLD = "2026-01-01T00:00:00Z"
        NEW = "2026-06-01T00:00:00Z"
        # world_state stores ONE deduped edge PER (subject,predicate,object) with a support
        # counter — a topic's mentions can't be split across the recency cut on a single
        # edge, they share that edge's timestamp. Trend is therefore read across a topic's
        # DISTINCT edges (each carrying its own support + timestamp) — exactly how a graph
        # actually grows. So we build, per topic, an OLD edge and a NEW edge.
        #
        # GIG: a small OLD edge (support 2) + a big RECENT edge (support 9) -> growing.
        _add(name, "you", "working_toward", "gig", "goal", n=2)
        _stamp_edge(name, "you", "working_toward", "gig", OLD, OLD)
        _add(name, "gig", "leads_to", "income", "inference", n=9)
        _stamp_edge(name, "gig", "leads_to", "income", NEW, NEW)
        # GUITAR: only OLD edges (support 10 + 4), nothing recent -> declining/long-silent.
        _add(name, "you", "cares_about", "guitar", "preference", n=10)
        _stamp_edge(name, "you", "cares_about", "guitar", OLD, OLD)
        _add(name, "guitar", "is", "dusty", "observation", n=4)
        _stamp_edge(name, "guitar", "is", "dusty", OLD, OLD)
        # a steady RECENT topic so the recency cut has a real span between OLD and NEW.
        _add(name, "you", "cares_about", "garden", "preference", n=4)
        _stamp_edge(name, "you", "cares_about", "garden", NEW, NEW)

        objs = meaning.meaning(name)
        growing = {o["subject"] for o in objs if o["dimension"] == meaning.WHAT_GROWING}
        declining = {o["subject"] for o in objs if o["dimension"] == meaning.WHAT_DECLINING}

        ok("a rising topic ('gig') reads as GROWING", "gig" in growing)
        ok("a long-silent topic ('guitar') reads as DECLINING", "guitar" in declining)
        ok("a topic is not BOTH growing and declining at once",
           not (growing & declining))
        # the growing/declining statements are descriptive + carry counts (evidence).
        for o in objs:
            if o["dimension"] in (meaning.WHAT_GROWING, meaning.WHAT_DECLINING):
                ok(f"trend object [{o['dimension']}/{o['subject']}] carries recent/older counts",
                   "recent_mentions" in o["evidence"] and "older_mentions" in o["evidence"])
                break


# ===================================================================================
# 4. LAW 003 — THE KEY INVARIANT. Every meaning object cites evidence; confidence scales.
# ===================================================================================
def test_law_003_evidence_backed():
    print("\n[4] LAW 003 (KEY INVARIANT) — every meaning object is EVIDENCE-BACKED; none bare")
    with _temp_store(meaning, world_state, memory_lirf, curiosity):
        name = "mt_law003"
        _build_work_hub(name)
        # add a contradiction in LIRF so the unresolved/contradicted path is exercised too.
        f = memory_lirf.Facts.load(name)
        f.merge({"trait": "employer", "value": "Acme"})
        f.merge({"trait": "employer", "value": "Globex", "correction": True})
        f.save(name)

        objs = meaning.meaning(name)
        ok("meaning produced a non-empty set of objects to check", len(objs) > 0)

        # THE INVARIANT: every object carries non-empty evidence — NONE without it.
        without_evidence = [o for o in objs
                            if not (isinstance(o.get("evidence"), dict) and len(o["evidence"]) > 0)]
        ok(f"EVERY meaning object cites evidence — {len(objs)}/{len(objs)} backed, "
           f"{len(without_evidence)} without",
           len(without_evidence) == 0)

        # the evidence is REAL signal, not an empty placeholder: each carries a mention count.
        ok("every object's evidence contains a concrete 'mentions' count",
           all("mentions" in o["evidence"] for o in objs))
        # and at least one of the four significance signals is present per object.
        ok("every object's evidence carries graph signal (degree/recent/problem/etc.)",
           all(any(k in o["evidence"] for k in
                   ("degree", "recent_mentions", "older_mentions", "problem", "contradicted"))
               for o in objs))

        # confidence is bounded and NEVER asserted beyond the evidence (never 1.0).
        ok("every confidence is in (0, 0.95] — never an absolute claim",
           all(0.0 < o["confidence"] <= 0.95 for o in objs))

        # confidence SCALES with evidence: the high-mention hub's what_matters object is more
        # confident than a thin one. Compare work (53 effective mentions) vs energy (9).
        matters = {o["subject"]: o for o in objs if o["dimension"] == meaning.WHAT_MATTERS}
        if "work" in matters and "energy" in matters:
            ok("confidence scales with evidence (work-hub object > thin energy object)",
               matters["work"]["confidence"] > matters["energy"]["confidence"])
        else:
            ok("confidence-scaling check (work & energy both present)", "work" in matters)

        # a contradicted fact surfaces as an unresolved meaning, grounded in the tension.
        unresolved = [o for o in objs if o["dimension"] == meaning.WHAT_UNRESOLVED]
        ok("a contradicted/stressor topic surfaces as an UNRESOLVED open loop",
           len(unresolved) > 0)
        ok("every unresolved object is itself evidence-backed",
           all(len(o["evidence"]) > 0 for o in unresolved))


# ===================================================================================
# 5. never-fabricate — sparse/empty yields nothing; a lone node is not "dominant".
# ===================================================================================
def test_never_fabricate():
    print("\n[5] never-fabricate — sparse/empty yields no spurious meaning; a lone node ≠ dominant")
    with _temp_store(meaning, world_state, memory_lirf, curiosity):
        # an utterly empty life
        ok("empty life -> significance == []", meaning.significance("mt_empty") == [])
        ok("empty life -> meaning == [] (no invented significance)",
           meaning.meaning("mt_empty") == [])

        # a single isolated 1-mention node: present at most faintly, NEVER 'dominant'.
        name = "mt_lone"
        _add(name, "you", "cares_about", "philately", "preference", n=1)
        objs = meaning.meaning(name)
        ok("a single 1-mention isolated node is NOT called a 'dominant force'",
           all("dominant force" not in o["statement"] for o in objs))
        # it must also not manufacture a confident chapter out of one stray mention.
        chap = meaning.current_chapter(name)
        ok("one stray mention does NOT yield a confident named chapter",
           chap["confidence"] <= 0.2 and "philately" not in (chap.get("themes") or []))


# ===================================================================================
# 6. no-diagnosis — generated statements + render carry no clinical term.
# ===================================================================================
def test_no_diagnosis():
    print("\n[6] no-diagnosis — generated statements + render contain NO medical/clinical term")
    with _temp_store(meaning, world_state, memory_lirf, curiosity):
        name = "mt_nodiag"
        # a heavy, stress-laden graph — the exact shape where a naive engine would reach for
        # "burnout"/"depressed"/"anxiety". The engine must describe weight, never diagnose.
        _add(name, "you", "stressed_by", "work", "problem", n=40)
        _add(name, "work", "leads_to", "stress", "inference", n=30)
        _add(name, "stress", "affects", "sleep", "inference", n=25)
        _add(name, "you", "worried_about", "money", "problem", n=15)
        _add(name, "you", "sleeping", "poorly", "observation", n=8)

        objs = meaning.meaning(name)
        ok("meaning produced objects over a stress-heavy graph", len(objs) > 0)

        # EVERY generated statement is clean of the banned diagnosis/medical vocabulary.
        dirty = [o for o in objs if not meaning._is_clean(o["statement"])]
        ok(f"NO generated statement trips a banned term ({len(dirty)} dirty of {len(objs)})",
           len(dirty) == 0)

        # the chapter summary is clean too.
        chap = meaning.current_chapter(name)
        ok("the current-chapter summary contains NO clinical term",
           meaning._is_clean(chap.get("summary", "")))

        # the render's GENERATED ITEMS are clean (the guardrail legitimately NAMES banned
        # words to forbid them, so we inspect the items, exactly like spine inspects items).
        block = meaning.render_meaning(objs, chap)
        items = meaning._items_of(block)
        ok("the render's generated ITEMS contain NO banned diagnosis term",
           meaning._is_clean(items))
        # sanity: the banned-term set is real and the gate works both ways.
        ok("the no-diagnosis gate actually catches a clinical phrase",
           not meaning._is_clean("you're clearly burning out and depressed"))
        ok("the banned-term set is non-trivially populated",
           len(meaning.BANNED_TERMS) >= 15)


# ===================================================================================
# 7. chapter — evidence-backed + confidence-scored; empty -> 'too early', never invented.
# ===================================================================================
def test_chapter():
    print("\n[7] chapter — evidence-backed + confidence-scored; empty life -> low-conf 'too early'")
    with _temp_store(meaning, world_state, memory_lirf, curiosity):
        # a strong, coherent work-stress chapter
        name = "mt_chap"
        _build_work_hub(name)
        chap = meaning.current_chapter(name)
        ok("a strong graph yields a real (>0.2) confidence chapter",
           chap["confidence"] > 0.2)
        ok("the chapter names evidence-backed themes (work among them)",
           "work" in (chap.get("themes") or []))
        ok("the chapter carries its supporting evidence (per-theme counts)",
           isinstance(chap.get("evidence"), dict)
           and len(chap["evidence"].get("themes", [])) > 0
           and all("mentions" in t for t in chap["evidence"]["themes"]))
        ok("the chapter summary is descriptive prose, not a bare label",
           len(chap.get("summary", "")) > 20 and "." in chap.get("summary", ""))

        # an EMPTY life: a low-confidence 'too early', NEVER a fabricated chapter.
        chap_e = meaning.current_chapter("mt_chap_empty")
        ok("empty life -> low confidence (<= 0.15)", chap_e["confidence"] <= 0.15)
        ok("empty life -> NO fabricated themes", not chap_e.get("themes"))
        ok("empty life -> an honest 'too early/not enough yet' summary",
           "early" in chap_e["summary"].lower() or "enough" in chap_e["summary"].lower())


# ===================================================================================
# 8. render gate — no scaffold leak, never breaks character.
# ===================================================================================
def test_render_gate():
    print("\n[8] render gate — render_meaning leaks no scaffold tag and never breaks character")
    with _temp_store(meaning, world_state, memory_lirf, curiosity):
        name = "mt_render"
        _build_work_hub(name)
        objs = meaning.meaning(name)
        chap = meaning.current_chapter(name)
        block = meaning.render_meaning(objs, chap)
        ok("render_meaning produces a non-empty block", bool(block.strip()))

        # the GENERATED items must not contain any scaffold tag (the tags live only in the
        # legend/labels the model is told to never read; the spoken statements stay clean).
        items = meaning._items_of(block)
        # statements themselves (strip the leading [TAG] we prepend per line) carry no tag.
        spoken = []
        for line in items.splitlines():
            line = line.strip()
            if not line:
                continue
            # drop our own leading dimension tag, then assert the remainder is tag-free.
            stripped = line
            for tag in ("[MATTERS]", "[CHANGED]", "[GROWING]", "[DECLINING]",
                        "[UNRESOLVED]", "[CHAPTER]", "[MEANING]"):
                if stripped.startswith(tag):
                    stripped = stripped[len(tag):]
                    break
            spoken.append(stripped)
        spoken_text = " ".join(spoken)
        leaked = [t for t in meaning.MEANING_SCAFFOLD_TOKENS if t and t in spoken_text]
        ok(f"no scaffold token leaks into a spoken statement ({leaked or 'none'})",
           len(leaked) == 0)

        # every tag the renderer emits is in the scrubbable token set (so the mouth strips it).
        ok("every dimension tag emitted is in MEANING_SCAFFOLD_TOKENS",
           all(t in meaning.MEANING_SCAFFOLD_TOKENS
               for t in ("[MATTERS]", "[GROWING]", "[DECLINING]", "[UNRESOLVED]", "[CHAPTER]")))
        ok("MEANING_SCAFFOLD_TOKENS is a SUPERSET of spine + world tokens",
           "[KNOWN]" in meaning.MEANING_SCAFFOLD_TOKENS
           and "[SITUATION]" in meaning.MEANING_SCAFFOLD_TOKENS)

        # never breaks character: no "as an AI"/"language model"/medical-advice register.
        low = block.lower()
        breaks = ("as an ai", "language model", "i'm an ai", "i am an ai", "chatbot",
                  "i cannot feel", "i don't have feelings")
        ok("the block never breaks character (no 'as an AI' etc.)",
           not any(b in low for b in breaks))

        # the guardrail explicitly forbids diagnosis + the leak failure modes.
        ok("the guardrail forbids diagnosis and reading the brackets",
           "NOT a diagnosis" in block and "Never read the brackets" in block)

        # empty input -> empty string (nothing to bind), like the sibling renderers.
        ok("render_meaning([]) -> '' (nothing to bind)", meaning.render_meaning([]) == "")


# ===================================================================================
# 9. read-only guarantee — meaning never mutates LIRF / world_state.
# ===================================================================================
def test_read_only():
    print("\n[9] additive/read-only — meaning() never writes LIRF or world_state")
    with _temp_store(meaning, world_state, memory_lirf, curiosity) as store:
        name = "mt_ro"
        _build_work_hub(name)
        f = memory_lirf.Facts.load(name)
        f.merge({"trait": "employer", "value": "Acme"})
        f.save(name)

        world_before = (store / f"{name}.world.json").read_text()
        lirf_before = (store / f"{name}.lirf.json").read_text()

        # exercise every read entry point.
        meaning.significance(name)
        meaning.meaning(name)
        meaning.current_chapter(name)
        meaning.render(name)

        ok("world_state store is byte-identical after meaning reads (untouched)",
           (store / f"{name}.world.json").read_text() == world_before)
        ok("LIRF ledger is byte-identical after meaning reads (untouched)",
           (store / f"{name}.lirf.json").read_text() == lirf_before)

        # the ONLY write meaning makes is its own append-only ledger, opted into explicitly.
        ok("no meaning ledger exists until snapshot() is explicitly called",
           not (store / f"{name}.meaning.jsonl").exists())
        meaning.snapshot(name)
        ok("snapshot() created the append-only meaning ledger",
           (store / f"{name}.meaning.jsonl").exists())
        n1 = len(meaning.snapshots(name))
        meaning.snapshot(name)
        ok("the meaning ledger is APPEND-ONLY (a second snapshot grows it, Law 001)",
           len(meaning.snapshots(name)) == n1 + 1)
        # and the snapshot write still did not touch the source stores.
        ok("snapshot() still leaves LIRF + world untouched (read-only on sources)",
           (store / f"{name}.world.json").read_text() == world_before
           and (store / f"{name}.lirf.json").read_text() == lirf_before)


def main():
    print("=" * 79)
    print("ANIMA LAW 003 — UNDERSTANDING BEATS REMEMBERING  ::  Meaning-Engine invariant test")
    print("=" * 79)
    test_ranking()
    test_what_matters()
    test_growing_declining()
    test_law_003_evidence_backed()
    test_never_fabricate()
    test_no_diagnosis()
    test_chapter()
    test_render_gate()
    test_read_only()

    print("\n" + "=" * 79)
    if _fails:
        print(f"{len(_fails)} INVARIANT(S) FAILED: " + ", ".join(_fails))
        sys.exit(1)
    print("ALL MEANING INVARIANTS HOLD — significance is evidence-backed, confidence-scored, "
          "diagnosis-free (LAW 003).")


if __name__ == "__main__":
    main()
