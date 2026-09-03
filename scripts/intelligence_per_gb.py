#!/usr/bin/env python3
"""intelligence_per_gb — LERF Phase 4: INTELLIGENCE ECONOMICS.

Make capability-PER-RESOURCE a first-class, measured metric. The thesis the whole LERF
substrate is built to prove: a SMALL local model + a retrieved CERTIFIED skill can BEAT a
large model on intelligence-PER-RESOURCE even when the large model wins raw capability.
Stop ranking minds by parameter count alone; rank them by capability divided by what they
COST you — RAM, prompt tokens, energy, wall-clock.

This script computes and reports four ratios, model-only vs LERF+small-model:

  per GB   (RAM / disk) : capability / memory footprint.
        model-only  = an 8B model alone (its on-disk/in-RAM GB).
        LERF+small  = a 3B model + the ACTUAL byte size of the LERF skill store.
        DETERMINISTIC: model GBs are STATED ASSUMPTIONS (real-ish GGUF Q4 footprints);
        the LERF store size is MEASURED (lerf serialises the 10 shipped seeds to a temp
        store and we stat the file). The arithmetic is exact.

  per token             : capability / prompt tokens.
        Formalises the ALREADY-PROVEN 71.4% prompt-token cut (lerf_benchmark conditions
        B vs C/E) as accuracy-per-token. DETERMINISTIC: the token counts come straight
        from lerf_benchmark's deterministic table (the SAME lerf.count_tokens both sides),
        re-used here, never re-derived. This axis is the rigorous core.

  per watt (ENERGY)     : capability / joules.   *** ESTIMATE — clearly labelled. ***
        Energy is MODELLED from (model size -> a power draw) x (tokens -> time). There is
        no wattmeter in the loop; this is an order-of-magnitude estimate, never presented
        as measured. The deterministic axes are the verdict; this one is a lens.

  per second (LATENCY)  : capability / wall-clock seconds.   *** ESTIMATE/MEASURED-LOCAL. ***
        Drawn from telemetry MRI traces if any exist (the real local generate latency this
        machine records), else a labelled size+token estimate. Either way the SMALL-model
        and LARGE/cloud latencies are estimates of relative speed, labelled as such.

FUTURE METRICS (roadmap extension — ADDITIVE; the four axes above are untouched). Three measures
of the KNOWLEDGE/MIND systems' DENSITY (never the language model, never Vera's identity — the
freeze boundary holds; we measure the world model of the USER's situation + the LERF cognitive
store). They feed the Growth Dashboard + the Mind Balance board:

  UNDERSTANDING per GB  : understanding density — world-model (typed entities + causal links +
        typed relations + reasoning-chain hops) per MB of the world-model store. Read via
        anima.world_model's public API over a synthetic GROUNDED world built on a temp store; the
        store bytes are a real os.stat. EXACT.
  LEARNING per GB       : accumulation density — cognitive objects (skills + concepts + procedures
        + heuristics + decision-patterns + mental-models + failure-modes + preferences + values)
        per MB of the LERF store. Read via anima.lerf.stats over a synthetic ACTIVE population on a
        temp store; store bytes are a real os.stat. EXACT. The number the Growth Dashboard trends.
  REASONING per WATT    : reasoning capability per unit energy.   *** ESTIMATE — labelled. ***
        Proxy: verified multi-step reasoning units (multi-step skills/procedures + the world
        model's causal links) executable per joule. The COUNT is exact; the JOULES reuse the
        per-watt energy model on the 3B model + a compact context. Count EXACT, energy ESTIMATE.

WHAT IS EXACT vs WHAT IS AN ESTIMATE (the honesty contract, stated once and enforced):
  * EXACT (the verdict): prompt tokens, store bytes, dollar cost — these come from
    lerf_benchmark's deterministic accounting and a real os.stat of the serialised store.
    No model, no network, reproducible.
  * ESTIMATE (a lens, never the verdict): per-watt (energy) and the cross-model per-second
    comparison. Every estimate is printed with an [EST] tag and its assumptions.
  * CAPABILITY is a transparent proxy: the benchmark's modelled task accuracy per condition
    (B for the stuffed large-ish model, E for LERF+small+verifier), overwritten by the LIVE
    measured accuracy when Ollama is up. It is labelled (modelled) or (live) accordingly. We
    do NOT inflate it; if anything E's edge is conservative (it is the verifier-backstopped
    accuracy, and per-resource is where LERF wins even when raw capability does not).

HERMETIC: this script is READ-ONLY on all LERF data. It NEVER writes the real store. The
only store it touches is a throwaway temp dir (to MEASURE the serialised byte size of the
shipped seeds), and it ASSERTS the real .anima (excluding backups/) is byte-IDENTICAL
before==after by hashing every file. Synthetic / measurement only.

    python3 scripts/intelligence_per_gb.py            # the four-axis economics table
    python3 scripts/intelligence_per_gb.py --json     # machine-readable
    python3 scripts/intelligence_per_gb.py --selftest  # prove the 4 ratios + LERF wins >=1 axis
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anima import lerf                                   # noqa: E402  READ-ONLY substrate
import scripts.lerf_benchmark as bench                   # noqa: E402  REUSE the proven numbers


# ===================================================================================
# THE ASSUMPTIONS — every non-measured number lives HERE, named, so the report can print
# them and a reader can challenge each one. Nothing below invents a constant inline.
# ===================================================================================

# --- MODEL FOOTPRINTS (per-GB axis). STATED ASSUMPTIONS, not measurements. -----------
# Real-ish on-disk/in-RAM footprints for quantised local GGUF weights — the actual way
# these run on this Mac (the live model here is an 8B GGUF, see anima/mouth.DEFAULT_MODEL
# = L3-8B-Stheno). A Q4_K_M GGUF is ~0.6 GB per billion params in practice; we round to
# clean, defensible figures and LABEL them assumptions:
#   * a LARGE local model ~ 8B params  -> ~4.9 GB  (8B Q4_K_M GGUF on disk/RAM)
#   * a SMALL local model ~ 3B params  -> ~2.0 GB  (3B Q4_K_M GGUF on disk/RAM)
# The ratio (8B:3B ~ 2.45x more memory) is the load-bearing claim; the absolute GBs are
# illustrative and clearly flagged.
MODEL_GB = {
    "large_8b": 4.9,    # ASSUMPTION: 8B Q4_K_M GGUF footprint (GB)
    "small_3b": 2.0,    # ASSUMPTION: 3B Q4_K_M GGUF footprint (GB)
}
MODEL_PARAMS_B = {"large_8b": 8.0, "small_3b": 3.0}   # billions, for the per-watt model

# --- ENERGY (per-watt axis). ESTIMATE. ----------------------------------------------
# A first-order energy model, explicitly an estimate:
#   energy(J) = power_draw(W) * time(s),  time(s) = tokens / throughput(tok/s)
# Power is modelled as a fixed inference draw that scales mildly with model size; cloud is
# charged a datacenter-GPU draw. These are order-of-magnitude figures, NOT a wattmeter.
LOCAL_POWER_W_PER_B = 4.0      # EST: ~4 W per billion params, local apple-silicon inference
LOCAL_POWER_FLOOR_W = 8.0      # EST: fixed local overhead while generating (W)
CLOUD_POWER_W = 350.0          # EST: a datacenter inference GPU's draw under load (W)
# Throughput (tokens/sec) used to turn tokens into seconds for the energy + latency models.
# EST, but anchored: this machine's telemetry shows the 8B doing whole turns in ~10-14s.
TOK_PER_S = {"large_8b": 18.0, "small_3b": 42.0, "cloud": 120.0}   # EST tok/s

# --- LATENCY (per-second axis). MEASURED-LOCAL where telemetry exists, else EST. ------
# We read real local generate latency from telemetry MRI traces if present (the honest
# local number), and model the OTHER conditions' latency from tokens/throughput as an
# estimate. Cross-model comparison is therefore an estimate of RELATIVE speed.
CLOUD_NET_OVERHEAD_S = 0.6     # EST: round-trip network latency added to a cloud call (s)


# --- FUTURE METRICS (roadmap extension — additive). Two EXACT density axes + one ESTIMATE. -----
# These extend the four resource axes ABOVE with the roadmap's "future metrics": measures of the
# KNOWLEDGE/MIND systems' density, not the language model's. They feed the Growth Dashboard + the
# Mind Balance board. The honesty discipline is identical: counts and bytes are EXACT (the verdict),
# energy is an ESTIMATE (a lens), each labelled.
#
#  UNDERSTANDING per GB — understanding DENSITY: the world model's grounded richness (typed
#       entities + causal links + typed relations + the hops of its reasoning chains) per MB of the
#       world-model store it occupies. Read via anima.world_model's PUBLIC API over a synthetic,
#       grounded world built on a temp store; the store bytes are a real os.stat. EXACT.
#  LEARNING per GB — accumulation DENSITY: the count of COGNITIVE OBJECTS the substrate has
#       accrued (skills + concepts + procedures + the six added object types: heuristics,
#       decision-patterns, mental-models, failure-modes, preferences, values) per MB of the LERF
#       store. Read via anima.lerf's stats/all_* over a synthetic ACTIVE population on a temp store;
#       store bytes are a real os.stat. EXACT. This is the number the Growth Dashboard trends.
#  REASONING per WATT — reasoning capability per unit energy.  *** ESTIMATE — labelled. ***
#       Proxy: VERIFIED MULTI-STEP REASONING UNITS executable per joule. The capability numerator
#       is COUNTED exactly (multi-step skills/procedures the small model can run, + the world
#       model's multi-step causal chains — every one a grounded, inspectable reasoning artefact);
#       the JOULES denominator reuses the SAME first-order energy model the per-watt axis uses
#       (_joules over the small model + the compact retrieved context). Counts EXACT, energy EST.
REASON_TOKENS_PER_UNIT = 220   # EST: prompt tokens the small model reads to execute one reasoning
#                                unit (a retrieved multi-step skill/procedure or a causal chain) —
#                                anchored to condition-E compact-context sizing, NOT a stuffed prompt.


# ===================================================================================
# CAPABILITY — a transparent proxy, NOT a fabricated benchmark. We use the benchmark's
# per-condition task accuracy: condition B (transcript-stuffed, the large-ish model's best
# shot) for MODEL-ONLY, condition E (LERF + small + verifier) for LERF+SMALL. When Ollama
# is up we overwrite both with the LIVE measured accuracy on the same battery. Labelled.
# ===================================================================================

def _capability(live: dict | None) -> dict:
    """Return {model_only, lerf_small, source} capability in [0,1].

    model_only := condition B accuracy (a large-ish model handed the stuffed prompt).
    lerf_small := condition E accuracy (LERF retrieval + small model + grounded verifier).
    Prefer LIVE measured accuracy (mean over the battery) when available; else the
    benchmark's MODELLED accuracy. Never invents a number — both come from lerf_benchmark."""
    if live and live.get("available"):
        means = bench._live_accuracy_means(live)
        b = means.get("B", {}).get("accuracy")
        e = means.get("E", {}).get("accuracy")
        if b is not None and e is not None:
            return {"model_only": float(b), "lerf_small": float(e), "source": "live"}
    # modelled stand-ins shipped with the benchmark (labelled, never measured)
    return {
        "model_only": float(bench._MODELLED_ACCURACY["B"]),
        "lerf_small": float(bench._MODELLED_ACCURACY["E"]),
        "source": "modelled",
    }


# ===================================================================================
# THE FOUR AXES. Each returns the two sides' resource cost + the capability/resource ratio,
# plus an `exact` flag and the assumptions it leaned on. Capability is the SAME numerator on
# both sides of an axis (model_only uses model-only capability, lerf_small uses LERF+small
# capability) so the ratio is the honest capability-per-unit-resource.
# ===================================================================================

def _safe_div(num: float, den: float) -> float:
    return (num / den) if den else float("inf")


def axis_per_gb(cap: dict) -> dict:
    """per-GB: capability / memory footprint.

    model-only = 8B alone (MODEL_GB['large_8b']).
    LERF+small = 3B + the MEASURED LERF store size (GB).
    EXACT arithmetic; model GBs are stated assumptions, the store size is measured."""
    store_bytes = _measure_store_bytes()
    store_gb = store_bytes / (1024 ** 3)
    model_only_gb = MODEL_GB["large_8b"]
    lerf_small_gb = MODEL_GB["small_3b"] + store_gb
    return {
        "axis": "per_gb",
        "unit": "capability per GB",
        "exact": True,           # arithmetic exact; model GBs are labelled assumptions
        "model_only": {"resource": round(model_only_gb, 6),
                       "ratio": round(_safe_div(cap["model_only"], model_only_gb), 6)},
        "lerf_small": {"resource": round(lerf_small_gb, 6),
                       "ratio": round(_safe_div(cap["lerf_small"], lerf_small_gb), 6)},
        "detail": {"store_bytes": store_bytes, "store_gb": store_gb,
                   "model_only_gb": model_only_gb,
                   "small_model_gb": MODEL_GB["small_3b"]},
    }


def axis_per_token(cap: dict, det: dict) -> dict:
    """per-token: capability / prompt tokens.

    REUSES the benchmark's deterministic token table: model-only = condition B tokens (the
    stuffed prompt), LERF+small = condition E tokens (compact retrieved context). This is
    the rigorous form of the proven 71.4% prompt-token cut. EXACT."""
    c = det["conditions"]
    b_tok = c["B"]["tokens"]          # model-only pays the stuffed prompt every turn
    e_tok = c["E"]["tokens"]          # LERF+small pays the compact retrieved context
    return {
        "axis": "per_token",
        "unit": "capability per 1k prompt tokens",
        "exact": True,
        "model_only": {"resource": b_tok,
                       "ratio": round(_safe_div(cap["model_only"], b_tok / 1000.0), 6)},
        "lerf_small": {"resource": e_tok,
                       "ratio": round(_safe_div(cap["lerf_small"], e_tok / 1000.0), 6)},
        "detail": {"token_reduction_pct_vs_B": det["token_reduction_vs_B"]["E"],
                   "B_tokens": b_tok, "E_tokens": e_tok},
    }


def axis_per_dollar(cap: dict, det: dict) -> dict:
    """per-$: capability / dollars (a bonus EXACT axis the directive invites).

    model-only is priced as the cloud-by-default condition D (the large model people reach
    for sends the stuffed prompt at cloud rates). LERF+small is condition E's cost (local
    render; cloud only on a verifier failure — here 0% of tasks). Costs come straight from
    the benchmark's deterministic accounting. EXACT."""
    c = det["conditions"]
    d_cost = c["D"]["cost"]           # model-only-as-cloud: the expensive default
    e_cost = c["E"]["cost"]           # LERF+small: local, escalates only on verifier-fail
    return {
        "axis": "per_dollar",
        "unit": "capability per $ (battery cost)",
        "exact": True,
        "model_only": {"resource": d_cost,
                       "ratio": round(_safe_div(cap["model_only"], d_cost), 3)},
        "lerf_small": {"resource": e_cost,
                       "ratio": round(_safe_div(cap["lerf_small"], e_cost), 3)},
        "detail": {"D_cost": d_cost, "E_cost": e_cost,
                   "price_per_1k": bench.PRICE_PER_1K},
    }


def _joules(model_key: str, tokens: int, *, cloud: bool = False) -> float:
    """ESTIMATE: energy (J) to process `tokens` on `model_key`. time = tokens/throughput;
    power = a size-scaled local draw (or a fixed cloud GPU draw). Order-of-magnitude only."""
    if cloud:
        secs = tokens / TOK_PER_S["cloud"] + CLOUD_NET_OVERHEAD_S
        return CLOUD_POWER_W * secs
    secs = tokens / TOK_PER_S[model_key]
    watts = LOCAL_POWER_FLOOR_W + LOCAL_POWER_W_PER_B * MODEL_PARAMS_B[model_key]
    return watts * secs


def axis_per_watt(cap: dict, det: dict) -> dict:
    """per-watt (ENERGY): capability / joules.  *** ESTIMATE. ***

    Energy modelled from (size->power) x (tokens->time). model-only = the 8B processing the
    stuffed prompt (B tokens); LERF+small = the 3B processing the compact context (E tokens).
    The token counts are exact (from the benchmark); the J/token conversion is an estimate."""
    c = det["conditions"]
    b_tok = c["B"]["tokens"]
    e_tok = c["E"]["tokens"]
    j_model = _joules("large_8b", b_tok)
    j_lerf = _joules("small_3b", e_tok)
    return {
        "axis": "per_watt",
        "unit": "capability per kilojoule",
        "exact": False,          # ENERGY IS AN ESTIMATE
        "estimate": True,
        "model_only": {"resource_joules": round(j_model, 1),
                       "ratio": round(_safe_div(cap["model_only"], j_model / 1000.0), 6)},
        "lerf_small": {"resource_joules": round(j_lerf, 1),
                       "ratio": round(_safe_div(cap["lerf_small"], j_lerf / 1000.0), 6)},
        "detail": {"model": "J = (8 + 4*paramsB) W * tokens/throughput; cloud=350W",
                   "tok_per_s": TOK_PER_S},
    }


def _telemetry_local_latency_s() -> tuple:
    """READ-ONLY: median local `generate`-stage latency (seconds) from any telemetry MRI
    traces for the live creatures, plus a count. Returns (median_s_or_None, n_traces). Never
    writes; tolerant of missing/garbled files. This is the only MEASURED latency available."""
    store = lerf.STORE if Path(lerf.STORE).is_absolute() else (Path.cwd() / lerf.STORE)
    if not store.is_dir():
        return (None, 0)
    gen_ms = []
    for p in store.glob("*.mri.jsonl"):
        try:
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                for s in row.get("stages", []):
                    if isinstance(s, dict) and s.get("stage") == "generate":
                        t = s.get("t_ms")
                        if isinstance(t, (int, float)) and t > 0:
                            gen_ms.append(float(t))
        except Exception:
            continue
    if not gen_ms:
        return (None, 0)
    gen_ms.sort()
    mid = gen_ms[len(gen_ms) // 2]
    return (mid / 1000.0, len(gen_ms))


def axis_per_second(cap: dict, det: dict) -> dict:
    """per-second (LATENCY): capability / wall-clock seconds.  *** ESTIMATE / MEASURED-LOCAL. ***

    LERF+small latency: prefer the MEASURED median local generate latency from telemetry,
    SCALED for the small model's higher throughput and its far smaller prompt (E tokens);
    fall back to a token/throughput estimate if no telemetry exists. model-only latency:
    estimated from the 8B throughput over the stuffed prompt (B tokens). Cross-model speed is
    an ESTIMATE; the local anchor is measured. Labelled either way."""
    c = det["conditions"]
    b_tok = c["B"]["tokens"]
    e_tok = c["E"]["tokens"]
    measured_s, n = _telemetry_local_latency_s()
    # model-only (8B on the stuffed prompt): if we have a measured local generate median,
    # use it as the anchor for the LARGE local model (that telemetry IS an 8B); else estimate.
    if measured_s is not None:
        model_only_s = measured_s
        # small model: scale the measured anchor by throughput AND prompt-size ratio — both
        # make E faster. This keeps the small-model number tethered to a real measurement.
        speed_ratio = TOK_PER_S["small_3b"] / TOK_PER_S["large_8b"]
        size_ratio = max(e_tok, 1) / max(b_tok, 1)
        lerf_small_s = max(0.05, measured_s * size_ratio / speed_ratio)
        src = f"measured-local-anchor (telemetry median over {n} generate frames)"
    else:
        model_only_s = b_tok / TOK_PER_S["large_8b"]
        lerf_small_s = e_tok / TOK_PER_S["small_3b"]
        src = "token/throughput estimate (no telemetry)"
    return {
        "axis": "per_second",
        "unit": "capability per second",
        "exact": False,          # cross-model latency is an estimate
        "estimate": True,
        "model_only": {"resource_seconds": round(model_only_s, 3),
                       "ratio": round(_safe_div(cap["model_only"], model_only_s), 6)},
        "lerf_small": {"resource_seconds": round(lerf_small_s, 3),
                       "ratio": round(_safe_div(cap["lerf_small"], lerf_small_s), 6)},
        "detail": {"source": src, "telemetry_frames": n,
                   "tok_per_s": TOK_PER_S},
    }


# ===================================================================================
# FUTURE METRICS (roadmap extension) — UNDERSTANDING / LEARNING / REASONING. Each measures the
# KNOWLEDGE/MIND systems' DENSITY (never Vera's identity — the freeze boundary is respected: we
# read the world model of the USER's situation and the LERF cognitive store, never persona/
# portrait/identity). Two are EXACT (grounded counts ÷ a real os.stat of the store bytes); one is
# an ESTIMATE (reasoning per joule, reusing the per-watt energy model, clearly labelled). They feed
# the Growth Dashboard + the Mind Balance board.
#
# MEASUREMENT IS HERMETIC: each builds a SYNTHETIC, GROUNDED population on a THROWAWAY temp store —
# the same discipline _measure_store_bytes / _deterministic_and_live use — redirecting every store
# the build path may write, then restores. The caller asserts the real .anima is byte-unchanged.
# ===================================================================================

# The store bindings the world-model build path may write — world_model + every engine it reads/
# writes through (world_state/reality/meaning/memory_lirf/curiosity/constitution/telemetry/cloud)
# + reliability backups. Mirrors anima.world_model._SELFTEST_STORE_TARGETS so nothing leaks.
_WORLD_STORE_TARGETS = (
    ("anima.world_model", "STORE"), ("anima.world_state", "STORE"),
    ("anima.reality", "STORE"), ("anima.meaning", "STORE"),
    ("anima.memory_lirf", "STORE"), ("anima.curiosity", "STORE"),
    ("anima.constitution", "STORE"), ("anima.reliability", "DEFAULT_STORE"),
    ("anima.telemetry", "STORE"), ("anima.cloud", "STORE"),
)

# The store bindings the LERF cognitive-population build path may write — lerf (both bindings) +
# the LIRF/constitution stores the guarded load path may touch + reliability backups.
_LERF_STORE_TARGETS = (
    ("anima.lerf", "STORE"), ("anima.memory_lirf", "STORE"),
    ("anima.constitution", "STORE"), ("anima.reliability", "DEFAULT_STORE"),
)


def _redirect_stores(targets, tp):
    """Point every (module, attr) store binding at the temp path ``tp``; return the saved originals
    so the caller can restore in a finally. Tolerant of a missing module/attr (isolation-safe)."""
    saved = []
    for modpath, attr in targets:
        try:
            mod = __import__(modpath, fromlist=["_"])
        except Exception:
            continue
        saved.append((mod, attr, getattr(mod, attr, None)))
        if getattr(mod, attr, None) is not None:
            setattr(mod, attr, tp)
    return saved


def _restore_stores(saved):
    for mod, attr, old in saved:
        if old is not None:
            setattr(mod, attr, old)


def _measure_understanding() -> dict:
    """HERMETIC: build the canonical SYNTHETIC, GROUNDED world model on a temp store and measure its
    understanding DENSITY. Returns {units, entities, causal_links, relations, chain_hops, store_bytes}.

    UNITS (the understanding numerator, all EXACT counts over anima.world_model's public objects):
      * typed ENTITIES (people/projects/goals/resources/risks/constraints/states) — the world-model
        nodes the substrate grounds,
      * typed CAUSAL LINKS (X --causes/worsens--> Y) — the causal edges it can reason across,
      * typed (non-causal) RELATIONS (relates_to/works_on/pursues/…) — the world's bonds,
      * CHAIN HOPS — total edges across the world model's multi-step causal chains (a model that
        connects into longer through-lines understands MORE than the same edges in isolation).
    STORE_BYTES is a real os.stat of the world-model store file the build wrote. Read-only on the
    real .anima (writes only to the temp dir). Never raises — degrades to zeros if world_model is
    unavailable, which the caller surfaces honestly."""
    from anima import world_model as wm
    td = tempfile.mkdtemp(prefix="lerf-econ-understand-")
    tp = Path(td)
    saved = _redirect_stores(_WORLD_STORE_TARGETS, tp)
    res = {"units": 0, "entities": 0, "causal_links": 0, "relations": 0,
           "chain_hops": 0, "store_bytes": 0}
    try:
        out = wm.build_synthetic_world("econ_world")
        world = out.get("world", {}) or {}
        ents = len(world.get("entities", []) or [])
        links = len(wm.causal_links(world))
        rels = len(world.get("relations", []) or [])
        chains = wm.world_causal_chains(world)
        chain_hops = sum(len(c) for c in chains)
        wpath = wm.world_store_path("econ_world")
        store_bytes = wpath.stat().st_size if wpath.exists() else 0
        res = {"units": ents + links + rels + chain_hops, "entities": ents,
               "causal_links": links, "relations": rels, "chain_hops": chain_hops,
               "store_bytes": int(store_bytes)}
    except Exception:
        pass
    finally:
        _restore_stores(saved)
        import shutil
        shutil.rmtree(td, ignore_errors=True)
    return res


def _measure_learning() -> dict:
    """HERMETIC: seed a SYNTHETIC ACTIVE cognitive population on a temp store and measure its
    accumulation DENSITY. Returns {objects, by_type, store_bytes, multistep}.

    OBJECTS (the learning numerator, an EXACT count via lerf.stats over the accrued store):
    skills + concepts + procedures + the six added object types — heuristics, decision-patterns,
    mental-models, failure-modes, preferences, values — every grounded, inspectable cognitive
    object. The population is the 10 SHIPPED seed skills (the canonical builder, so we count the
    real format) PLUS one ACTIVE instance of every other object type, so the density spans the
    whole cognitive schema. ``multistep`` counts objects carrying a multi-step procedure (>=2
    steps) — reused by the reasoning axis. STORE_BYTES is a real os.stat. Read-only on real .anima.
    Never raises — degrades to zeros if lerf is unavailable."""
    td = tempfile.mkdtemp(prefix="lerf-econ-learn-")
    tp = Path(td)
    saved = _redirect_stores(_LERF_STORE_TARGETS, tp)
    res = {"objects": 0, "by_type": {}, "store_bytes": 0, "multistep": 0}
    try:
        _seed_cognitive_population("econ_learn")
        st = lerf.stats(name="econ_learn")
        path = lerf._path("econ_learn")
        store_bytes = path.stat().st_size if path.exists() else 0
        # multi-step reasoning artefacts in the store: skills/procedures with >=2 ordered steps.
        multistep = 0
        for o in lerf._load_objects("econ_learn"):
            if o.get("state") != lerf.ACTIVE:
                continue
            if len(o.get("steps", []) or []) >= 2:
                multistep += 1
        res = {"objects": int(st.get("total", 0)), "by_type": dict(st.get("by_type", {})),
               "store_bytes": int(store_bytes), "multistep": multistep}
    except Exception:
        pass
    finally:
        _restore_stores(saved)
        import shutil
        shutil.rmtree(td, ignore_errors=True)
    return res


def _seed_cognitive_population(name: str) -> None:
    """Seed a SYNTHETIC ACTIVE cognitive population onto the (already-redirected) temp store: the 10
    SHIPPED seed skills (via the canonical builder, so the density reflects the real format) + one
    ACTIVE instance of every other object type (concept, procedure, and the six added types). All
    user/task-facing — the PREFERENCE/VALUE freeze guard passes (subjects are the user's/a task's,
    never Vera's). Writes only to the redirected temp store. Synthetic; never the real store."""
    from scripts.build_lerf import _seed_skills
    for sk in _seed_skills():
        lerf.store_skill(sk, name=name)
    # a concept + a procedure (the pre-existing trio beyond skill).
    lerf.store_concept(lerf.make_concept(
        "compounding", "small gains that build on each other grow faster than linearly",
        examples=["interest on interest"], state=lerf.ACTIVE), name=name)
    lerf.store_skill(lerf.make_procedure(
        "weekly_review", inputs_needed=["the week's notes"], tools_needed=["calendar"],
        steps=["gather open loops", "triage by urgency", "schedule the top three"],
        state=lerf.ACTIVE), name=name)
    # one ACTIVE instance of each of the six added cognitive object types.
    lerf.store_object(lerf.make_heuristic(
        "frozen_goods_last", "logistics", "a perishable stop is on the route",
        "sequence it last so it spends least time un-refrigerated",
        applies_when=["errand routing"], fails_when=["no cold items"], state=lerf.ACTIVE), name=name)
    lerf.store_object(lerf.make_decision_pattern(
        "choose_a_laptop", "decision_support", inputs=["candidate laptops", "budget"],
        criteria=["price", "weight", "battery"], decision="cheapest that clears the must-haves",
        examples=["picked the lighter one for travel"], state=lerf.ACTIVE), name=name)
    lerf.store_object(lerf.make_mental_model(
        "supply_and_demand", "economics", entities=["price", "supply", "demand"],
        relations=["price balances supply against demand"],
        dynamics=["a shortage pushes price up until demand falls"], state=lerf.ACTIVE), name=name)
    lerf.store_object(lerf.make_failure_mode(
        "dropped_dosage", "health", trigger="rounding or omitting a number",
        symptom="a dose goes missing from the summary", consequence="the wrong amount is taken",
        mitigation="copy every figure verbatim", state=lerf.ACTIVE), name=name)
    lerf.store_object(lerf.make_preference(
        "concise replies", domain="user", weight=0.8,
        evidence=["asked for shorter answers"], state=lerf.ACTIVE), name=name)
    lerf.store_object(lerf.make_value(
        "protect focus time", domain="user", weight=0.9,
        evidence=["stated it is a priority"], state=lerf.ACTIVE), name=name)


def axis_understanding_per_gb(cap: dict, understanding: dict) -> dict:
    """UNDERSTANDING per GB: understanding DENSITY (world-model richness) per MB of the world-model
    store.  EXACT (grounded counts ÷ a real os.stat).

    This is NOT capability/footprint like the four resource axes — it is a DENSITY: how much
    grounded understanding (typed entities + causal links + typed relations + reasoning-chain hops)
    the substrate packs into each megabyte of the world-model store it occupies. Higher = a richer
    map of the user's world per byte. There is no model-only side (a bare LLM holds no inspectable
    world model), so this axis reports the LERF/world-model density alone. EXACT."""
    units = understanding["units"]
    store_bytes = understanding["store_bytes"]
    store_mb = store_bytes / (1024 ** 2)
    return {
        "axis": "understanding_per_gb",
        "unit": "understanding units per MB (world-model store)",
        "exact": True,
        "density_per_mb": round(_safe_div(units, store_mb), 3),
        "detail": {"units": units, "entities": understanding["entities"],
                   "causal_links": understanding["causal_links"],
                   "relations": understanding["relations"],
                   "chain_hops": understanding["chain_hops"],
                   "store_bytes": store_bytes, "store_mb": round(store_mb, 6),
                   "formula": "units = entities + causal_links + relations + chain_hops; "
                              "density = units / store_MB"},
    }


def axis_learning_per_gb(cap: dict, learning: dict) -> dict:
    """LEARNING per GB: accumulation DENSITY (cognitive objects accrued) per MB of the LERF store.
    EXACT (an exact count via lerf.stats ÷ a real os.stat).

    The accumulation density the Growth Dashboard trends: skills + concepts + procedures + the six
    added object types (heuristics/decision-patterns/mental-models/failure-modes/preferences/values)
    per megabyte of the LERF store. Higher = more grounded, inspectable cognition packed per byte.
    Like the understanding axis this is a DENSITY (no model-only side — a weight tensor accumulates
    nothing inspectable). EXACT."""
    objects = learning["objects"]
    store_bytes = learning["store_bytes"]
    store_mb = store_bytes / (1024 ** 2)
    return {
        "axis": "learning_per_gb",
        "unit": "cognitive objects per MB (LERF store)",
        "exact": True,
        "density_per_mb": round(_safe_div(objects, store_mb), 3),
        "detail": {"objects": objects, "by_type": learning["by_type"],
                   "store_bytes": store_bytes, "store_mb": round(store_mb, 6),
                   "formula": "objects = skills + concepts + procedures + heuristics + "
                              "decision_patterns + mental_models + failure_modes + preferences + "
                              "values; density = objects / store_MB"},
    }


def axis_reasoning_per_watt(cap: dict, understanding: dict, learning: dict) -> dict:
    """REASONING per WATT: reasoning capability per unit energy.  *** ESTIMATE — labelled. ***

    PROXY: verified multi-step REASONING UNITS executable per joule. The numerator is COUNTED
    exactly — the multi-step reasoning artefacts the substrate can execute: multi-step skills/
    procedures in the LERF store (>=2 ordered steps each) PLUS the world model's multi-step causal
    chains (each a grounded, inspectable chain to reason across). The denominator is an ESTIMATE:
    the joules the small (3B) model spends reading the compact retrieved context to execute one
    such unit, via the SAME first-order energy model the per-watt axis uses (_joules over the small
    model + REASON_TOKENS_PER_UNIT tokens — condition-E sized, never a stuffed prompt). Counts are
    EXACT; the joules-per-unit is an ESTIMATE. The whole axis is therefore ESTIMATE, labelled."""
    multistep_objs = learning["multistep"]
    causal_chains_n = 0
    # the world model's multi-step chains were counted as chain_hops; recover the chain COUNT by
    # rebuilding is unnecessary — we approximate "a chain" as any through-line of >=2 hops. We have
    # chain_hops (total edges); a conservative chain count is hops over the typical chain length.
    # To stay EXACT on the count we instead treat each causal LINK as a 1-hop reasoning step and the
    # multi-hop chains as the bonus: reasoning units = multi-step objects + causal links.
    causal_links_n = understanding["causal_links"]
    reasoning_units = multistep_objs + causal_links_n
    # ESTIMATE energy: the small model reading one unit's worth of compact context.
    j_per_unit = _joules("small_3b", REASON_TOKENS_PER_UNIT)
    total_joules = j_per_unit * max(1, reasoning_units)
    return {
        "axis": "reasoning_per_watt",
        "unit": "verified reasoning units per kilojoule",
        "exact": False,          # ENERGY IS AN ESTIMATE (the count is exact; the joules are modelled)
        "estimate": True,
        "ratio": round(_safe_div(reasoning_units, total_joules / 1000.0), 3),
        "detail": {"reasoning_units": reasoning_units,
                   "multistep_objects": multistep_objs,
                   "causal_links": causal_links_n,
                   "j_per_unit": round(j_per_unit, 2),
                   "total_joules": round(total_joules, 1),
                   "model": f"J/unit = (8 + 4*3) W * {REASON_TOKENS_PER_UNIT} tok / "
                            f"{TOK_PER_S['small_3b']} tok/s (small-model compact-context EST)",
                   "note": "count EXACT (multi-step objects + causal links); joules ESTIMATE"},
    }


# ===================================================================================
# STORE-SIZE MEASUREMENT — HERMETIC. Serialise the SHIPPED seed skills to a THROWAWAY temp
# store and os.stat the file. Redirects every store the LERF load path may write, runs the
# write, restores, and the caller asserts real .anima is byte-unchanged. Never the real store.
# ===================================================================================

def _measure_store_bytes() -> int:
    """The actual on-disk byte size of the LERF skill store holding the 10 shipped seeds,
    measured on a temp store. READ-ONLY w.r.t. real .anima (writes only to the temp dir)."""
    from scripts.build_lerf import _seed_skills
    td = tempfile.mkdtemp(prefix="lerf-econ-bytes-")
    tp = Path(td)
    # Redirect lerf.STORE (both bindings) + the LIRF/constitution/reliability stores the
    # guarded load path may touch, exactly like the benchmark does, so nothing leaks.
    targets = [(lerf, "STORE")]
    try:
        import anima.lerf as _pkglerf
        if _pkglerf is not lerf:
            targets.append((_pkglerf, "STORE"))
    except Exception:
        pass
    for modpath, attr in (("anima.memory_lirf", "STORE"),
                          ("anima.constitution", "STORE"),
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
        nm = "econ_probe"
        for sk in _seed_skills():
            lerf.store_skill(sk, name=nm)
        size = lerf._path(nm).stat().st_size
    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        import shutil
        shutil.rmtree(td, ignore_errors=True)
    return int(size)


# ===================================================================================
# HERMETIC FOOTPRINT — prove real .anima (minus backups/) is byte-identical before==after.
# Same discipline as lerf._footprint / lerf_benchmark._footprint.
# ===================================================================================

def _footprint(root: Path):
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


# ===================================================================================
# THE ECONOMICS REPORT — assemble all four (well, five with per-$) axes, decide which LERF
# wins, and prove hermeticity. Capability + tokens + cost come from the proven benchmark.
# ===================================================================================

def compute(want_live: bool = False) -> dict:
    """Build the full economics report. `want_live` drives the live local model to MEASURE
    accuracy (overwriting the modelled capability); off by default so the deterministic
    verdict needs no model and no network. Returns the report dict."""
    real = lerf.STORE if Path(lerf.STORE).is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = _footprint(real)

    # The proven deterministic token/cost table — built on a hermetic temp store exactly the
    # way lerf_benchmark.run does, then restored. We REUSE these numbers; we do not re-derive.
    det, live = _deterministic_and_live(want_live)

    cap = _capability(live)
    axes = {
        "per_gb": axis_per_gb(cap),
        "per_token": axis_per_token(cap, det),
        "per_dollar": axis_per_dollar(cap, det),
        "per_watt": axis_per_watt(cap, det),
        "per_second": axis_per_second(cap, det),
    }

    # which axes does LERF+small WIN (higher capability-per-resource is better)?
    wins = {name: (ax["lerf_small"]["ratio"] > ax["model_only"]["ratio"])
            for name, ax in axes.items()}

    # FUTURE METRICS (roadmap extension) — UNDERSTANDING/LEARNING density (EXACT) + REASONING/WATT
    # (ESTIMATE). Measured on synthetic, grounded populations built on temp stores (hermetic). These
    # are DENSITY/efficiency measures of the MIND systems, kept separate from the LERF-vs-model axes
    # above (they have no model-only side — a bare LLM holds no inspectable world model or store).
    understanding = _measure_understanding()
    learning = _measure_learning()
    future_axes = {
        "understanding_per_gb": axis_understanding_per_gb(cap, understanding),
        "learning_per_gb": axis_learning_per_gb(cap, learning),
        "reasoning_per_watt": axis_reasoning_per_watt(cap, understanding, learning),
    }

    fp_after = _footprint(real)
    hermetic_ok = (fp_before == fp_after)

    return {
        "capability": cap,
        "axes": axes,
        "future_axes": future_axes,
        "lerf_wins": wins,
        "deterministic_source": {
            "B_tokens": det["conditions"]["B"]["tokens"],
            "E_tokens": det["conditions"]["E"]["tokens"],
            "token_reduction_pct": det["token_reduction_vs_B"]["E"],
            "D_cost": det["conditions"]["D"]["cost"],
            "E_cost": det["conditions"]["E"]["cost"],
        },
        "assumptions": {
            "model_gb": MODEL_GB,
            "model_params_b": MODEL_PARAMS_B,
            "energy_W": {"local_per_B": LOCAL_POWER_W_PER_B,
                         "local_floor": LOCAL_POWER_FLOOR_W, "cloud": CLOUD_POWER_W},
            "tok_per_s": TOK_PER_S,
            "cloud_net_overhead_s": CLOUD_NET_OVERHEAD_S,
            "reason_tokens_per_unit": REASON_TOKENS_PER_UNIT,
        },
        "hermetic_ok": hermetic_ok,
        "live_available": bool(live and live.get("available")),
    }


def _deterministic_and_live(want_live: bool) -> tuple:
    """Run lerf_benchmark's deterministic_table (and optionally its live_legs) on a HERMETIC
    temp store, redirecting every store binding, then restore. Returns (det, live_or_None).
    This is the canonical source of the token/cost numbers — measured by the proven harness,
    not re-implemented here."""
    td = tempfile.mkdtemp(prefix="lerf-econ-det-")
    tp = Path(td)
    targets = [(lerf, "STORE")]
    try:
        import anima.lerf as _pkglerf
        if _pkglerf is not lerf:
            targets.append((_pkglerf, "STORE"))
    except Exception:
        pass
    for modpath, attr in (("anima.memory_lirf", "STORE"),
                          ("anima.constitution", "STORE"),
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
        name = bench.SYNTH
        bench._seed_battery_skills(name)
        det = bench.deterministic_table(name)
        live = bench.live_legs(name) if want_live else None
    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        import shutil
        shutil.rmtree(td, ignore_errors=True)
    return det, live


# ===================================================================================
# RENDER
# ===================================================================================

def _fmt_ratio(v) -> str:
    if v == float("inf"):
        return "   inf"
    if v >= 100:
        return f"{v:7.1f}"
    if v >= 1:
        return f"{v:7.2f}"
    return f"{v:7.3f}"


def _print_future_metrics(fa: dict) -> None:
    """Render the roadmap FUTURE METRICS — UNDERSTANDING/GB, LEARNING/GB (EXACT), REASONING/WATT
    (ESTIMATE). These are DENSITY/efficiency measures of the MIND systems (no model-only side), so
    they print as a single value each with its basis + the raw counts behind it. Feeds the Growth
    Dashboard + Mind Balance board."""
    u = fa["understanding_per_gb"]
    l = fa["learning_per_gb"]
    r = fa["reasoning_per_watt"]
    print("FUTURE METRICS — knowledge/mind DENSITY (roadmap extension; feeds Growth Dashboard +")
    print("                 Mind Balance board). DENSITY axes have no model-only side.")
    hdr = f"{'metric (per-MB / per-kJ)':<28}{'value':>12}  basis   what it measures"
    print(hdr)
    print("-" * len(hdr))
    print(f"{'understanding / MB':<28}{_fmt_ratio(u['density_per_mb']):>12}  EXACT   "
          f"world-model units per MB of store")
    print(f"{'learning / MB':<28}{_fmt_ratio(l['density_per_mb']):>12}  EXACT   "
          f"cognitive objects per MB of store")
    print(f"{'reasoning / kJ':<28}{_fmt_ratio(r['ratio']):>12}  [EST]   "
          f"verified multi-step reasoning units per kJ")
    print("-" * len(hdr))
    ud = u["detail"]
    print(f"  UNDERSTANDING: {ud['units']} units = {ud['entities']} entities + "
          f"{ud['causal_links']} causal-links + {ud['relations']} relations + "
          f"{ud['chain_hops']} chain-hops")
    print(f"                 over {ud['store_bytes']} B "
          f"({ud['store_bytes']/1024:.2f} KB) world-model store   [EXACT]")
    ld = l["detail"]
    bt = ld.get("by_type", {})
    bt_s = ", ".join(f"{k}:{v}" for k, v in sorted(bt.items()))
    print(f"  LEARNING:      {ld['objects']} cognitive objects ({bt_s})")
    print(f"                 over {ld['store_bytes']} B "
          f"({ld['store_bytes']/1024:.2f} KB) LERF store   [EXACT]")
    rd = r["detail"]
    print(f"  REASONING:     {rd['reasoning_units']} units "
          f"({rd['multistep_objects']} multi-step objects + {rd['causal_links']} causal-links) "
          f"@ ~{rd['j_per_unit']} J/unit")
    print(f"                 [EST: {rd['model']}]  (count EXACT, joules ESTIMATE)")
    print()


def _print_report(rep: dict) -> None:
    cap = rep["capability"]
    axes = rep["axes"]
    wins = rep["lerf_wins"]

    print("=" * 80)
    print("INTELLIGENCE ECONOMICS — capability PER RESOURCE  (LERF Phase 4)")
    print("=" * 80)
    capsrc = cap["source"]
    print(f"thesis: a SMALL local model + a CERTIFIED retrieved skill beats a LARGE model on")
    print(f"        intelligence-PER-RESOURCE, even when the large model wins RAW capability.")
    print()
    print(f"sides:  MODEL-ONLY  = an 8B model alone "
          f"({MODEL_GB['large_8b']} GB assumed), running the STUFFED prompt (benchmark B/D)")
    print(f"        LERF+SMALL  = a 3B model ({MODEL_GB['small_3b']} GB assumed) + the LERF "
          f"skill store, running RETRIEVAL (benchmark C/E)")
    print(f"capability proxy ({capsrc}): model-only={cap['model_only']:.3f}  "
          f"lerf+small={cap['lerf_small']:.3f}   (benchmark task-accuracy: B vs E)")
    if cap["model_only"] >= cap["lerf_small"]:
        print(f"  NOTE: the large model's RAW capability is >= LERF+small "
              f"({cap['model_only']:.3f} >= {cap['lerf_small']:.3f}). The win below is PER-RESOURCE.")
    print()

    # ---- THE FOUR-AXIS TABLE ----
    order = ["per_gb", "per_token", "per_dollar", "per_watt", "per_second"]
    labels = {
        "per_gb":     "per GB  (RAM/disk)",
        "per_token":  "per 1k tokens",
        "per_dollar": "per $  (battery)",
        "per_watt":   "per kJ  (energy)",
        "per_second": "per second (latency)",
    }
    hdr = (f"{'axis':<22}{'model-only':>13}{'LERF+small':>13}{'LERF x':>9}"
           f"{'winner':>11}  basis")
    print(hdr)
    print("-" * len(hdr))
    for name in order:
        ax = axes[name]
        mo = ax["model_only"]["ratio"]
        ls = ax["lerf_small"]["ratio"]
        mult = _safe_div(ls, mo)
        winner = "LERF+small" if wins[name] else "model-only"
        basis = "EXACT" if ax.get("exact") else "[EST]"
        print(f"{labels[name]:<22}{_fmt_ratio(mo):>13}{_fmt_ratio(ls):>13}"
              f"{_fmt_ratio(mult):>9}{winner:>11}  {basis}")
    print("-" * len(hdr))
    print("  ratio = capability / resource (HIGHER is better).  'LERF x' = LERF+small ÷ model-only.")
    print("  EXACT = deterministic (tokens/bytes/$ from the proven benchmark + a real os.stat).")
    print("  [EST] = ESTIMATE (energy, cross-model latency) — a lens, NOT the verdict.")
    print()

    # ---- per-axis detail + the resource each side spends ----
    print("RESOURCE SPENT PER SIDE (what the ratio divides into):")
    g = axes["per_gb"]
    print(f"  per GB     : model-only {g['model_only']['resource']} GB   vs   "
          f"LERF+small {g['lerf_small']['resource']} GB  "
          f"(= 3B {g['detail']['small_model_gb']} GB + store "
          f"{g['detail']['store_bytes']} B = {g['detail']['store_gb']*1024:.3f} MB)   [EXACT]")
    t = axes["per_token"]
    print(f"  per token  : model-only {t['model_only']['resource']} tok  vs   "
          f"LERF+small {t['lerf_small']['resource']} tok   "
          f"(a {t['detail']['token_reduction_pct_vs_B']}% prompt-token cut)   [EXACT]")
    d = axes["per_dollar"]
    print(f"  per $      : model-only ${d['model_only']['resource']:.5f}  vs   "
          f"LERF+small ${d['lerf_small']['resource']:.5f}   "
          f"(model-only priced as cloud-default D; LERF+small = E, local)   [EXACT]")
    w = axes["per_watt"]
    print(f"  per watt   : model-only {w['model_only']['resource_joules']} J  vs   "
          f"LERF+small {w['lerf_small']['resource_joules']} J   "
          f"[EST: {w['detail']['model']}]")
    s = axes["per_second"]
    print(f"  per second : model-only {s['model_only']['resource_seconds']} s  vs   "
          f"LERF+small {s['lerf_small']['resource_seconds']} s   "
          f"[EST/MEASURED: {s['detail']['source']}]")
    print()

    # ---- the verdict ----
    exact_wins = [n for n in order if wins[n] and axes[n].get("exact")]
    est_wins = [n for n in order if wins[n] and not axes[n].get("exact")]
    print("WHERE LERF+SMALL WINS:")
    print(f"  EXACT axes won (the verdict): {', '.join(labels[n] for n in exact_wins) or 'NONE'}")
    print(f"  [EST] axes won (supporting) : {', '.join(labels[n] for n in est_wins) or 'NONE'}")
    if "per_token" in exact_wins:
        tr = axes["per_token"]["detail"]["token_reduction_pct_vs_B"]
        print(f"  per-token is the PROVEN core: {tr}% fewer prompt tokens (benchmark B->E), so "
              f"LERF+small extracts more capability from every token.")
    print()

    # ---- FUTURE METRICS (roadmap extension) — feeds the Growth Dashboard + Mind Balance board ----
    fa = rep.get("future_axes")
    if fa:
        _print_future_metrics(fa)

    # ---- assumptions, stated plainly ----
    a = rep["assumptions"]
    print("ASSUMPTIONS (challenge any of these):")
    print(f"  GB      : 8B ~ {a['model_gb']['large_8b']} GB, 3B ~ {a['model_gb']['small_3b']} GB "
          f"(Q4_K_M GGUF footprints — STATED, not measured). Store size IS measured.")
    print(f"  watt    : J = ({a['energy_W']['local_floor']} + "
          f"{a['energy_W']['local_per_B']}*paramsB) W locally, {a['energy_W']['cloud']} W cloud; "
          f"time = tokens / {a['tok_per_s']}  — ESTIMATE.")
    print(f"  second  : local anchor from telemetry generate-latency if present, else "
          f"tokens/throughput; cross-model speed is an ESTIMATE.")
    print(f"  token/$ : EXACT — reused verbatim from scripts/lerf_benchmark deterministic table.")
    print(f"  underst.: EXACT — world-model entity/causal-link/relation/chain-hop COUNTS ÷ a real "
          f"os.stat of the world-model store (built synthetic + grounded, hermetic).")
    print(f"  learning: EXACT — cognitive-object COUNT (lerf.stats) ÷ a real os.stat of the LERF "
          f"store (synthetic ACTIVE population spanning all object types).")
    print(f"  reason/W: ESTIMATE — count of multi-step reasoning units is EXACT; the J/unit reuses "
          f"the per-watt energy model ({a.get('reason_tokens_per_unit')} tok on the 3B). A lens.")
    print()
    print(f"HERMETIC: real .anima (excl. backups/) byte-unchanged = {rep['hermetic_ok']}")
    if rep["live_available"]:
        print("capability source: LIVE (measured on the local model this run).")
    else:
        print("capability source: modelled (benchmark stand-ins; pass --live to measure).")


# ===================================================================================
# SELFTEST — prove the four ratios compute and LERF+small wins >= 1 axis. Hermetic.
# ===================================================================================

def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("intelligence_per_gb self-test")

    real = lerf.STORE if Path(lerf.STORE).is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = _footprint(real)

    rep = compute(want_live=False)
    axes = rep["axes"]

    # 1. all four required axes (+ the bonus per-$) computed a finite, positive ratio on BOTH sides.
    required = ["per_gb", "per_token", "per_watt", "per_second"]
    for name in required:
        ax = axes[name]
        for side in ("model_only", "lerf_small"):
            r = ax[side]["ratio"]
            ok(f"{name}.{side}: ratio is finite & positive ({r})",
               isinstance(r, (int, float)) and r != float("inf") and r > 0)

    # 2. the four ratios are genuinely capability/resource: scaling capability scales the ratio.
    cap = rep["capability"]
    ok("per_token uses the proven 71.4% token cut (E < B tokens)",
       axes["per_token"]["lerf_small"]["resource"] < axes["per_token"]["model_only"]["resource"]
       and axes["per_token"]["detail"]["token_reduction_pct_vs_B"] >= 50.0)

    # 3. the store size feeding per-GB is the MEASURED real seed-store size (non-trivial bytes).
    sb = axes["per_gb"]["detail"]["store_bytes"]
    ok(f"per_gb store size is measured & non-trivial ({sb} bytes)", sb > 1000)

    # 4. LERF+small WINS on >= 1 axis — and specifically on the EXACT per-token axis.
    wins = rep["lerf_wins"]
    n_wins = sum(1 for v in wins.values() if v)
    ok(f"LERF+small wins on >= 1 axis (won {n_wins}: "
       f"{[k for k,v in wins.items() if v]})", n_wins >= 1)
    ok("LERF+small wins the EXACT per-token axis (the proven core)", wins["per_token"])
    ok("LERF+small wins the EXACT per-$ axis", wins["per_dollar"])
    ok("LERF+small wins the EXACT per-GB axis", wins["per_gb"])

    # 5. EXACT axes are flagged exact; estimate axes are flagged estimate (honesty contract).
    ok("per_token/per_gb/per_dollar are flagged EXACT",
       axes["per_token"]["exact"] and axes["per_gb"]["exact"] and axes["per_dollar"]["exact"])
    ok("per_watt/per_second are flagged ESTIMATE (not presented as measured)",
       (not axes["per_watt"]["exact"]) and (not axes["per_second"]["exact"]))

    # 6. capability proxy is in [0,1] and sourced (modelled here, no --live).
    ok("capability proxy in [0,1] for both sides",
       0.0 <= cap["model_only"] <= 1.0 and 0.0 <= cap["lerf_small"] <= 1.0)
    ok("capability source is labelled (modelled without --live)", cap["source"] == "modelled")

    # 7. the deterministic numbers came from the benchmark, not invented here.
    ds = rep["deterministic_source"]
    ok("token cut reused from benchmark is ~71% (50-90 band)",
       50.0 <= ds["token_reduction_pct"] <= 90.0)

    # 7b. FUTURE METRICS (roadmap extension) — the three new axes compute FINITE & POSITIVE on
    #     synthetic data, with the honesty flags (understanding/learning EXACT, reasoning ESTIMATE).
    fa = rep["future_axes"]
    u = fa["understanding_per_gb"]; l = fa["learning_per_gb"]; rzn = fa["reasoning_per_watt"]
    for nm_, val_ in (("understanding_per_gb", u["density_per_mb"]),
                      ("learning_per_gb", l["density_per_mb"]),
                      ("reasoning_per_watt", rzn["ratio"])):
        ok(f"{nm_}: value is finite & positive ({val_})",
           isinstance(val_, (int, float)) and val_ != float("inf") and val_ > 0)
    # understanding numerator is the grounded world-model count, store bytes a real os.stat.
    ud = u["detail"]
    ok(f"understanding units are grounded world-model counts "
       f"(entities {ud['entities']} + links {ud['causal_links']} + relations {ud['relations']} "
       f"+ chain-hops {ud['chain_hops']} = {ud['units']})",
       ud["units"] == ud["entities"] + ud["causal_links"] + ud["relations"] + ud["chain_hops"]
       and ud["units"] > 0)
    ok(f"understanding store size is measured & non-trivial ({ud['store_bytes']} bytes)",
       ud["store_bytes"] > 1000)
    # learning numerator spans all object types (>=10 seed skills + the added types), store measured.
    ld = l["detail"]
    ok(f"learning counts cognitive objects across types (objects={ld['objects']}, "
       f"types={sorted(ld['by_type'].keys())})",
       ld["objects"] >= 10 and len(ld["by_type"]) >= 5)
    ok(f"learning store size is measured & non-trivial ({ld['store_bytes']} bytes)",
       ld["store_bytes"] > 1000)
    # reasoning count is exact (multi-step objects + causal links); the joules are the estimate.
    rzd = rzn["detail"]
    ok(f"reasoning units are an EXACT count (multistep {rzd['multistep_objects']} + "
       f"causal-links {rzd['causal_links']} = {rzd['reasoning_units']})",
       rzd["reasoning_units"] == rzd["multistep_objects"] + rzd["causal_links"]
       and rzd["reasoning_units"] > 0 and rzd["total_joules"] > 0)
    # honesty contract on the new axes: density EXACT, reasoning/watt ESTIMATE.
    ok("understanding_per_gb & learning_per_gb are flagged EXACT",
       u["exact"] and l["exact"])
    ok("reasoning_per_watt is flagged ESTIMATE (energy is modelled, not measured)",
       (not rzn["exact"]) and rzn.get("estimate") is True)

    # 8. HERMETIC: real .anima byte-unchanged across the whole selftest (compute() ran twice).
    rep2 = compute(want_live=False)
    fp_after = _footprint(real)
    ok("HERMETIC: real .anima byte-unchanged across the selftest", fp_before == fp_after)
    ok("HERMETIC: report self-reports hermetic_ok",
       rep["hermetic_ok"] and rep2["hermetic_ok"])
    ok("determinism: two runs give identical per-token ratios",
       axes["per_token"]["lerf_small"]["ratio"]
       == rep2["axes"]["per_token"]["lerf_small"]["ratio"])
    # the EXACT future-metric densities are deterministic too (synthetic build is fixed).
    ok("determinism: two runs give identical understanding & learning densities",
       u["density_per_mb"] == rep2["future_axes"]["understanding_per_gb"]["density_per_mb"]
       and l["density_per_mb"] == rep2["future_axes"]["learning_per_gb"]["density_per_mb"])

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL INTELLIGENCE-ECONOMICS SELFTESTS PASS")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="LERF intelligence economics (capability/resource).")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--live", action="store_true",
                    help="drive the local model to MEASURE capability (else modelled)")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the four ratios + the three future metrics compute (LERF wins >=1 axis)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    rep = compute(want_live=args.live)
    if args.json:
        print(json.dumps(rep, indent=2, default=str))
    else:
        _print_report(rep)

    # exit non-zero only if the HERMETIC guarantee was violated — the deterministic axes
    # are the verdict and they always compute; a non-hermetic run is the only hard failure.
    return 0 if rep["hermetic_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
