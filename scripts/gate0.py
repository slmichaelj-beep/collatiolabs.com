#!/usr/bin/env python3
"""GATE 0 — TRUST THE PLATFORM.

Aggregates the five group modules' ten tests into the SIX pass-conditions and one verdict.
The pass condition (the user's bar): do not move on until you can say —
  The mind can grow, the twin can test changes, unsafe changes cannot merge,
  identity remains frozen, the user experience remains grounded, and recovery works after failure.

Each group module exposes run() -> {'group', 'tests':[{'id','name','status','evidence','metrics'}]}.
Exit 0 iff GATE 0 PASS (all ten tests PASS AND all six conditions MET)."""
from __future__ import annotations
import hashlib, importlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

GROUPS = ["gate0_twin", "gate0_growth", "gate0_guards", "gate0_resource", "gate0_experience"]

# Each named pass-condition holds iff every listed test PASSes.
CONDITIONS = {
    "The mind can grow":                  [3],
    "The twin can test changes":          [1, 7],
    "Unsafe changes cannot merge":        [2],
    "Identity remains frozen":            [1, 3, 5],
    "The user experience stays grounded": [4, 5, 10],
    "Recovery works after failure":       [9],
}
SUPPORTING = {6: "Reality learning revises + is append-only", 8: "Performance/FMLGS scales"}


def _anima_identity_fp() -> str:
    """Fingerprint the real Vera identity files — must be byte-identical across the whole gate."""
    h = hashlib.sha256()
    base = os.path.join(ROOT, ".anima")
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        low = name.lower()
        if low.startswith("vera.") and any(low.endswith(x) for x in (".json", ".md", ".txt", ".jsonl")):
            try:
                with open(os.path.join(base, name), "rb") as f:
                    h.update(name.encode()); h.update(f.read())
            except OSError:
                pass
    return h.hexdigest()[:16]


def main() -> int:
    id_before = _anima_identity_fp()
    groups_out, all_tests = [], {}
    for g in GROUPS:
        try:
            mod = importlib.import_module(g)
            res = mod.run()
        except Exception as e:  # a group that can't even run is a hard fail
            res = {"group": g, "tests": [{"id": -1, "name": f"{g} failed to run",
                   "status": "FAIL", "evidence": f"{type(e).__name__}: {e}"}]}
        groups_out.append(res)
        for t in res.get("tests", []):
            all_tests[t.get("id")] = t
    id_after = _anima_identity_fp()

    def st(tid):
        t = all_tests.get(tid)
        return t["status"] if t else "MISSING"

    print("=" * 78)
    print("GATE 0 — TRUST THE PLATFORM   (prove the architecture is SAFE TO GROW)")
    print("=" * 78)
    for res in groups_out:
        print(f"\n[{res.get('group','?')}]")
        for t in res.get("tests", []):
            mark = {"PASS": "PASS ", "FAIL": "FAIL ", "SKIP": "SKIP "}.get(t.get("status"), t.get("status"))
            print(f"  {mark} T{t.get('id')}: {t.get('name')}")
            ev = (t.get("evidence") or "").replace("\n", " ")
            if ev:
                print(f"         {ev[:200]}")

    print("\n" + "-" * 78)
    print("SUPPORTING (platform health)")
    for tid, label in SUPPORTING.items():
        print(f"  {st(tid):5}  T{tid}: {label}")

    print("-" * 78)
    print("SIX PASS CONDITIONS")
    all_met = True
    for cond, ids in CONDITIONS.items():
        sts = {i: st(i) for i in ids}
        met = all(v == "PASS" for v in sts.values())
        all_met = all_met and met
        print(f"  {'MET    ' if met else 'NOT MET'}  {cond}")
        print(f"            tests { {i: sts[i] for i in ids} }")

    ten = list(range(1, 11))
    ten_status = {i: st(i) for i in ten}
    ten_pass = all(v == "PASS" for v in ten_status.values())
    identity_frozen = (id_before == id_after)

    print("-" * 78)
    print(f"  10/10 tests PASS : {ten_pass}   {ten_status}")
    print(f"  real Vera identity byte-unchanged across the whole gate : {identity_frozen}  ({id_before} -> {id_after})")
    verdict = ten_pass and all_met and identity_frozen
    print("=" * 78)
    if verdict:
        print("VERDICT: GATE 0 PASS")
        print("  The mind can grow · the twin can test changes · unsafe changes cannot merge ·")
        print("  identity remains frozen · the user experience stays grounded · recovery works.")
        print("  -> The next frontier is safe: Understanding -> Theory -> Wisdom.")
    else:
        print("VERDICT: GATE 0 FAIL — do not move on. Close the NOT-MET conditions above.")
    print("=" * 78)
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
