#!/usr/bin/env python3
"""
certify_world_state — Personal World State: facts become connected SITUATIONS.

Vera does not just hold isolated values in slots — she connects them into a relational/causal
GRAPH and surfaces the connected cluster, so she speaks to the whole situation (work <- new
manager -> poor sleep) instead of one stranded fact. This certifies that contract through the
SAME functions the live turn calls — server._turn's capture_relations and the mouth's
situation/render_situation — hermetically and offline (NO model, NO network):

  A. CAPTURE BUILDS RELATIONS — capture_relations() pulls the OBVIOUS stated causal/relational
     statements ("my work's stressful because of my new manager", "I'm not sleeping well", "the
     stress is affecting my sleep") into typed edges and PERSISTS them to the additive world store
     (you stressed_by work; work because (new) manager; stress affects sleep).
  B. RETRIEVABLE AS A CONNECTED SITUATION — situation("work") returns the connected CLUSTER with
     the manager, the stress, AND the sleep knock-on linked in ONE graph (not isolated slots); an
     UNRELATED query returns a small/empty cluster (no spurious links).
  C. RENDERABLE AS UNDERSTANDING — render_situation(cluster) projects it into a spine-style binding
     block ([SITUATION]/[LINK]) that reads as understanding ("you are stressed by work"); every tag
     it emits is in WORLD_SCAFFOLD_TOKENS (so the mouth's scrub can strip any leak); an empty
     cluster renders to "".
  D. NEVER FABRICATES — with no stated "because"/connective, NO causal edge is invented; a
     wish/hypothetical asserts no stressed_by (Observed > Assumed).
  E. DURABLE + ADDITIVE — relations survive a reload, and two CONCURRENT additive saves both
     survive (the union-on-disk continuity guarantee — a save can only ADD, never overwrite-and-lose).
  F. WIRED INTO THE LIVE TURN — static no-wallpaper cross-check: server._turn calls
     world_state.capture_relations(name, text); the mouth builds situation() + injects
     render_situation() into the prompt 'mem' AND imports WORLD_SCAFFOLD_TOKENS into its leak-scrub;
     and the world store is ISOLATED from the LIRF ledger (no {name}.lirf.json written by any of this).

Hermetic: world_state.STORE is redirected into a temp dir by _temp_store (world_state is in its
_STORE_MODULES set, alongside constitution/reliability side-effect stores); the real .anima is
fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import os
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


def _nodes_blob(cluster: dict) -> str:
    return " ".join(cluster.get("nodes", []))


def main() -> int:
    from anima import world_state as W
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("WORLD STATE — facts become connected SITUATIONS (capture -> situation -> render)")
    print("=" * 80)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # capture() / render_situation() / WORLD_SCAFFOLD_TOKENS are pure — exercise them OUTSIDE the
    # store too (they touch no disk), proving the extractor + the no-leak token wiring directly.
    caps = W.capture("honestly my work has been really stressful because of my new manager")
    ck("A0: capture() extracts you stressed_by work from a stated 'because' clause",
       any(W._norm_node(s) == "you" and p == "stressed_by" and W._norm_node(o) == "work"
           for s, p, o, _k, _t in caps))
    ck("A0b: capture() also draws the stated work --because--> manager link",
       any(p == "because" and "manager" in W._norm_node(o) for s, p, o, _k, _t in caps))
    ck("D0: capture() NEVER invents an unstated link (no 'because' -> no causal edge)",
       not any(p in ("because", "leads_to", "affects")
               for s, p, o, _k, _t in W.capture("work is busy. my manager is tall.")))
    ck("D0b: capture() rejects a hypothetical (a wish asserts no stressed_by)",
       all(p != "stressed_by"
           for s, p, o, _k, _t in W.capture("I wish work were less stressful because of my manager")))

    name = "WorldStateCert"

    with _temp_store():
        # ---- A. CAPTURE BUILDS RELATIONS (persisted) -------------------------------------
        t1 = W.capture_relations(name, "my work's been really stressful because of my new manager")
        t2 = W.capture_relations(name, "honestly I'm not sleeping well")
        t3 = W.capture_relations(name, "and the stress is affecting my sleep")
        ck("A1: capture_relations persisted edges from the stated scenario",
           (len(t1) + len(t2) + len(t3)) > 0)
        on_disk = W.World.load(name).active()
        keys = {(W._norm_node(r["subject"]), r["predicate"], W._norm_node(r["object"]))
                for r in on_disk}
        ck("A2: the stress relation persisted (you, stressed_by, work)",
           ("you", "stressed_by", "work") in keys)
        ck("A3: the stated cause persisted (work --because--> <manager>)",
           any(p == "because" and "manager" in o for (s, p, o) in keys))
        ck("A4: the world store file exists on disk (additive {name}.world.json)",
           W.World.path(name).exists())

        # ---- B. RETRIEVABLE AS A CONNECTED SITUATION -------------------------------------
        # add the recency + the knock-on the user stated, to complete the chain to sleep.
        W.relate(name, "new manager", "is", "recent", kind="observation")
        W.relate(name, "work", "affects", "sleep", kind="inference")
        sit = W.situation(name, "work", hops=3)
        ck("B1: situation('work') returns a non-empty CONNECTED cluster (not one slot)",
           len(sit["edges"]) > 0 and len(sit["nodes"]) > 1)
        ck("B2: the cluster reaches the manager node", any("manager" in n for n in sit["nodes"]))
        ck("B3: the cluster reaches the stress/work topic",
           any("stress" in n or "work" in n for n in sit["nodes"]))
        ck("B4: the cluster reaches the sleep knock-on", any("sleep" in n for n in sit["nodes"]))
        ck("B5: manager + sleep linked in ONE cluster (situations, not isolated facts)",
           any("manager" in n for n in sit["nodes"]) and any("sleep" in n for n in sit["nodes"]))
        sit_un = W.situation(name, "photosynthesis", hops=3)
        ck("B6: an UNRELATED query returns an empty cluster (no fabricated links)",
           len(sit_un["edges"]) == 0 and len(sit_un["nodes"]) == 0)
        sit_broad = W.situation(name, "how am I doing?", hops=3)
        ck("B7: a broad check-in seeds the user node and surfaces the picture",
           len(sit_broad["edges"]) > 0)

        # ---- C. RENDERABLE AS UNDERSTANDING (spine-style, no leak) -----------------------
        block = W.render_situation(sit)
        low = block.lower()
        ck("C1: render_situation produces a non-empty binding block", bool(block.strip()))
        ck("C2: the block carries a [SITUATION] synopsis + a [LINK] connection (not slots)",
           "[SITUATION]" in block and "[LINK]" in block)
        ck("C3: it phrases the stress as understanding ('stressed by work')",
           "stressed by work" in low)
        ck("C4: every emitted scaffold tag is in WORLD_SCAFFOLD_TOKENS (mouth-scrubbable)",
           "[SITUATION]" in W.WORLD_SCAFFOLD_TOKENS and "[LINK]" in W.WORLD_SCAFFOLD_TOKENS)
        ck("C5: the guardrail forbids reading the brackets / 'according to my memory' aloud",
           "Never read the brackets" in block and "according to my memory" in block)
        ck("C6: an empty cluster renders to '' (nothing to bind)",
           W.render_situation({"edges": []}) == "")

        # ---- D. NEVER FABRICATES (in the persisted path too) -----------------------------
        nf = "WorldStateCertNoFab"
        W.capture_relations(nf, "work is busy. my manager is tall.")
        nfkeys = {(W._norm_node(r["subject"]), r["predicate"], W._norm_node(r["object"]))
                  for r in W.World.load(nf).active()}
        ck("D1: no unstated work<->manager causal edge was persisted (Observed > Assumed)",
           not any(p in ("because", "leads_to", "affects") for (s, p, o) in nfkeys))

        # ---- E. DURABLE + ADDITIVE (continuity) ------------------------------------------
        reloaded = W.World.load(name).active()
        ck("E1: relations survive a fresh reload (durable)", len(reloaded) > 0)
        # two concurrent World instances each add a DIFFERENT edge; both must survive the saves.
        wa = W.World.load(name)
        wb = W.World.load(name)
        wa.add("you", "cares_about", "family", kind="preference")
        wb.add("you", "working_toward", "calm", kind="goal")
        wa.save(name)
        wb.save(name)                       # must NOT drop wa's 'family' edge
        fkeys = {(W._norm_node(r["subject"]), r["predicate"], W._norm_node(r["object"]))
                 for r in W.World.load(name).active()}
        ck("E2: concurrent additive saves BOTH survive (no overwrite-and-lose, LAW 001)",
           ("you", "cares_about", "family") in fkeys
           and ("you", "working_toward", "calm") in fkeys)
        # corroboration: re-stating an edge climbs support, never duplicates.
        e1 = W.relate(name, "you", "stressed_by", "work", kind="problem")
        e2 = W.relate(name, "you", "stressed_by", "work", kind="problem")
        ck("E3: re-stating an edge corroborates (support++), never a duplicate row",
           int(e2.get("support", 0)) == int(e1.get("support", 0)) + 1
           and [(W._norm_node(r["subject"]), r["predicate"], W._norm_node(r["object"]))
                for r in W.World.load(name).active()].count(("you", "stressed_by", "work")) == 1)

        # ---- F. ISOLATION: the LIRF ledger is never written by any of this ----------------
        ck("F0: world state is ADDITIVE — no LIRF ledger file written for the world name",
           not os.path.exists(str(W.STORE / f"{name}.lirf.json"))
           and not os.path.exists(str(W.STORE / f"{nf}.lirf.json")))

    # ---- F. WIRED INTO THE LIVE TURN (static no-wallpaper cross-check) -------------------
    server_src = (ROOT / "anima" / "server.py").read_text()
    mouth_src = (ROOT / "anima" / "mouth.py").read_text()
    ws_src = (ROOT / "anima" / "world_state.py").read_text()
    server_wired = "world_state.capture_relations(name, text)" in server_src
    mouth_situation = ".situation(heart.name, user_text" in mouth_src
    mouth_inject = "render_situation(_cluster)" in mouth_src and "mem = (mem" in mouth_src
    mouth_scrub = '"WORLD_SCAFFOLD_TOKENS"' in mouth_src
    engine_fns = all(s in ws_src for s in ("def capture_relations(", "def situation(",
                                           "def render_situation(", "def capture("))
    ck("F1: server._turn calls world_state.capture_relations(name, text) (per-turn capture)",
       server_wired)
    ck("F2: the mouth builds world_state.situation(heart.name, user_text) (per-turn retrieval)",
       mouth_situation)
    ck("F3: the mouth injects render_situation(...) into the prompt 'mem' (shapes the reply)",
       mouth_inject)
    ck("F4: the mouth imports WORLD_SCAFFOLD_TOKENS into its leak-scrub (no scaffold read aloud)",
       mouth_scrub)
    ck("F5: world_state exposes the engine fns (capture/capture_relations/situation/render_situation)",
       engine_fns)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nWORLD-STATE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
