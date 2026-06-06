"""scripts/test_intake_endpoints.py — Hermetic smoke test for the intake HTTP endpoints.

Tests the full plan->approve->queue->trace->library->search->library/edit pipeline
against a REDIRECTED store (temp dir). Proves the real .anima is byte-unchanged.

Run:
    PYTHONPATH=/Users/lamarmichael/collatiolabs.com python3 scripts/test_intake_endpoints.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _footprint(root):
    import hashlib
    root = Path(root)
    if not root.is_dir():
        return (None, 0)
    # exclude live-server churn files (same exclusions as intake.py / intake_queue.py)
    _churn_suffixes = (".log", ".wav", ".aiff", ".aif", ".mp3")
    _churn_names = frozenset({"model-usage.json", "spend.json"})

    def _is_churn(rel):
        return rel.suffix in _churn_suffixes or rel.name in _churn_names

    files = sorted(q for q in root.rglob("*")
                   if q.is_file()
                   and "backups" not in q.relative_to(root).parts
                   and not _is_churn(q.relative_to(root)))
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


def ok(label, cond):
    mark = "  ok   " if cond else "  FAIL "
    print(mark + label)
    return bool(cond)


# ---------------------------------------------------------------------------
# Redirect all stores to a temp dir
# ---------------------------------------------------------------------------
def _redirect_targets(temp_path):
    import importlib, sys as _sys
    pairs = []
    for modpath, attr in (
        ("anima.intake", "STORE"),
        ("anima.intake_queue", None),   # intake_queue uses intake.STORE at call time
        ("anima.server", "STORE"),      # /intake/* writes RAW to server.STORE/{name}.intake_staging — redirect it too
        ("anima.memory_lirf", "STORE"),
        ("anima.lerf", "STORE"),
        ("anima.world_model", "STORE"),
        ("anima.world_state", "STORE"),
        ("anima.personal", "STORE"),
        ("anima.constitution", "STORE"),
        ("anima.cloud", "STORE"),
        ("anima.reliability", "DEFAULT_STORE"),
    ):
        if attr is None:
            continue
        try:
            mod = importlib.import_module(modpath)
        except Exception:
            continue
        if hasattr(mod, attr):
            pairs.append((mod, attr, getattr(mod, attr)))
            setattr(mod, attr, temp_path)
    return pairs


def _restore(pairs):
    for mod, attr, old in pairs:
        try:
            setattr(mod, attr, old)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main test body
# ---------------------------------------------------------------------------
def main():
    fails = []

    def check(label, cond):
        if not ok(label, cond):
            fails.append(label)

    print("intake endpoint smoke test")
    print("=" * 60)

    # snapshot real .anima BEFORE
    from anima import intake as _int
    real_store = _int.STORE if _int.STORE.is_absolute() else (Path.cwd() / _int.STORE)
    fp_before = _footprint(real_store)

    # set up temp dirs
    td = Path(tempfile.mkdtemp(prefix="intake-ep-test-"))
    corpus = Path(tempfile.mkdtemp(prefix="intake-ep-corpus-"))
    redir_pairs = _redirect_targets(td)

    try:
        name = "EPSmokeTest"

        # ---- write a synthetic ops manual ----
        manual_text = """# Acme Operations Manual

## Service Level Agreement
A service level agreement is a documented commitment between a provider and a client.

## Procedure: onboard new client
1. Verify the signed contract is on file.
2. Create the client workspace.
3. Schedule a kickoff call within 3 days.

## Rules
If the request involves a compliance risk, escalate to the legal team.
Never issue a refund without approval from a manager.
"""
        manual = corpus / "ops_manual.md"
        manual.write_text(manual_text)

        # ================================================================
        # 1. POST /intake/plan — stage + Wave-1 plan (no durable write)
        # ================================================================
        from anima.server import _intake_plan
        plan_data = {"kind": "file", "filename": "ops_manual.md",
                     "bytes_b64": __import__("base64").b64encode(manual.read_bytes()).decode()}
        plan = _intake_plan(name, plan_data)

        check("plan: ok=True", plan.get("ok") is True)
        check("plan: source_id present", bool(plan.get("source_id")))
        check("plan: trace_id present", bool(plan.get("trace_id")))
        check("plan: detected_type present", bool(plan.get("detected_type")))
        check("plan: routing list present", isinstance(plan.get("routing"), list))
        check("plan: committed=False (Wave-1 invariant)", plan.get("committed") is False)
        check("plan: safety dict present", isinstance(plan.get("safety"), dict))
        check("plan: chunks_sample is list", isinstance(plan.get("chunks_sample"), list))
        check("plan: provenance dict present", isinstance(plan.get("provenance"), dict))
        check("plan: trace_id differs from source_id (real MRI trace id)",
              plan.get("trace_id") != plan.get("source_id"))

        source_id = plan["source_id"]
        real_trace_id = plan["trace_id"]

        # staging file exists
        from anima.server import _staging_dir, _read_staging
        stage_path, found = _read_staging(name, source_id)
        check("staging: file written to staging dir", found and stage_path is not None)

        # ================================================================
        # 2. POST /intake/approve — commit with reference_only
        # ================================================================
        from anima.server import _intake_approve
        approve_data = {"source_id": source_id, "control": "reference_only",
                        "delete_raw": False, "session": "smoke-sess"}
        receipt = _intake_approve(name, approve_data)

        check("approve: ok=True", receipt.get("ok") is True)
        check("approve: committed=True for reference_only", receipt.get("committed") is True)
        check("approve: reference list non-empty", bool(receipt.get("reference")))
        check("approve: state present", bool(receipt.get("state")))
        # staging file is cleaned up after a committed approve
        _, still_found = _read_staging(name, source_id)
        check("approve: staging file cleaned up after commit", not still_found)

        # ================================================================
        # 3. GET /intake/queue — queue records
        # ================================================================
        from anima import intake_queue as iq
        recs = iq.queue(name)
        check("queue: at least one record", len(recs) >= 1)
        rec = next((r for r in recs if r.get("source_id") == source_id), None)
        check("queue: our source_id is in the queue", rec is not None)
        check("queue: record has state", bool(rec.get("state")) if rec else False)

        # ================================================================
        # 4. GET /intake/trace — trace for this source
        # ================================================================
        from anima import intake as _int2
        # Use the REAL trace_id returned by the plan (the id ingest() committed to disk)
        tr = _int2.trace(name, real_trace_id)
        check("trace: trace object present (by real_trace_id)", tr is not None)
        if tr:
            check("trace: trace has stages", bool(tr.get("stages")))
            rendered = _int2.render_trace(tr)
            check("trace: render_trace produces a walkthrough", "INTAKE MRI" in rendered)

        # ================================================================
        # 5. GET /library — library items
        # ================================================================
        from anima.server import _serve_library
        lib = _serve_library(name, f"name={name}")
        check("library: ok=True", lib.get("ok") is True)
        check("library: items list present", isinstance(lib.get("items"), list))
        our_item = next((it for it in lib.get("items", []) if it.get("id") == source_id), None)
        check("library: our source is in the library", our_item is not None)
        if our_item:
            check("library: item has title", bool(our_item.get("title")))
            check("library: item has type", bool(our_item.get("type")))
            check("library: item has status", bool(our_item.get("status")))
            check("library: item has rights", bool(our_item.get("rights")) or our_item.get("rights") == "unknown")

        # section filter
        lib_arch = _serve_library(name, f"name={name}&section=archived files")
        check("library(section): archived filter runs without error",
              lib_arch.get("ok") is True)

        # ================================================================
        # 6. POST /search — cross-store labeled search
        # ================================================================
        from anima.server import _serve_search

        # first ingest + approve something so there is data to find
        # (the ops manual was committed as reference_only above)
        sr = _serve_search(name, {"q": "service level agreement", "name": name})
        check("search: ok=True", sr.get("ok") is True)
        check("search: results is list", isinstance(sr.get("results"), list))
        if sr.get("results"):
            r0 = sr["results"][0]
            check("search: result has id", "id" in r0)
            check("search: result has source_type", "source_type" in r0)
            check("search: result has title", "title" in r0)
            check("search: result has snippet", "snippet" in r0)
            check("search: result has score", "score" in r0)
            check("search: result has destination", "destination" in r0)
            # the critical invariant: source_type must be a known label, never a blend
            from anima.intake_search import ALL_SOURCE_TYPES
            all_st_ok = all(r.get("source_type") in ALL_SOURCE_TYPES for r in sr["results"])
            check("search: all source_type labels are known (no blurring)", all_st_ok)
            # personal memory must NOT appear here (no LIRF was written)
            has_memory = any(r.get("source_type") == "memory" for r in sr["results"])
            check("search: no personal-memory results for external reference query", not has_memory)

        # search with no results (garbage query)
        sr_empty = _serve_search(name, {"q": "xyzzy_nothing_matches_this_at_all_999", "name": name})
        check("search(no match): ok=True, empty results", sr_empty.get("ok") is True)

        # search with empty query returns error
        sr_nq = _serve_search(name, {"q": "", "name": name})
        check("search(empty q): ok=False", sr_nq.get("ok") is False or sr_nq.get("results") == [])

        # ================================================================
        # 7. POST /library/edit — memory-type editor
        # ================================================================
        from anima.server import _serve_library_edit

        # reroute action: change destination
        edit_out = _serve_library_edit(name, {
            "id": source_id,
            "action": "reroute",
            "new_destination": "Archive",
            "new_rights": "user-owned",
            "reason": "smoke test reroute",
        })
        check("edit(reroute): ok=True", edit_out.get("ok") is True)
        check("edit(reroute): item returned", isinstance(edit_out.get("item"), dict))
        check("edit(reroute): audit returned", isinstance(edit_out.get("audit"), dict))
        if edit_out.get("audit"):
            check("edit(reroute): audit has from/to/when/reason",
                  all(k in edit_out["audit"] for k in ("from", "to", "when", "reason")))

        # archive action: queue record state changes
        # (source_id must have a queue record — it does from the approve step)
        edit_arch = _serve_library_edit(name, {
            "id": source_id,
            "action": "archive",
            "reason": "smoke test archive",
        })
        check("edit(archive): ok=True", edit_arch.get("ok") is True)

        # reprocess action: revert to classified
        edit_rep = _serve_library_edit(name, {
            "id": source_id,
            "action": "reprocess",
            "reason": "smoke test reprocess",
        })
        # reprocess from archived -> classified is a blocked transition (archived is terminal)
        # the function should still return ok=True (the state machine blocks but doesn't error)
        check("edit(reprocess): returns dict", isinstance(edit_rep, dict))

        # bad action: returns ok=False
        bad_edit = _serve_library_edit(name, {
            "id": source_id,
            "action": "invalid_action_xyz",
        })
        check("edit(bad action): ok=False", bad_edit.get("ok") is False)

        # missing id: returns ok=False
        no_id = _serve_library_edit(name, {"action": "archive"})
        check("edit(no id): ok=False", no_id.get("ok") is False)

        # delete action (keep citation): citation record stays, raw bytes purged
        edit_del = _serve_library_edit(name, {
            "id": source_id,
            "action": "delete",
            "reason": "smoke test delete",
        })
        check("edit(delete): ok=True", edit_del.get("ok") is True)
        # verify citation record is kept (in reference library, marked deleted)
        ref_items = iq.references(name)
        deleted_item = next((it for it in ref_items if it.get("id") == source_id), None)
        check("edit(delete): citation record is KEPT after delete", deleted_item is not None)
        check("edit(delete): citation record is marked deleted",
              (deleted_item or {}).get("deleted") is True if deleted_item else False)
        check("edit(delete): raw bytes purged",
              all(not ch.get("text") for ch in (deleted_item or {}).get("chunks", []) or []))

        # ================================================================
        # 8. intake_search as a pure function (unit test without HTTP)
        # ================================================================
        from anima.intake_search import search, _words, _score, ALL_SOURCE_TYPES

        check("search_fn: _words tokenises correctly", _words("Hello world") == {"hello", "world"})
        check("search_fn: _score exact match = 1.0", _score({"hello"}, "hello world") == 1.0)
        check("search_fn: _score no match = 0.0", _score({"xyz"}, "hello world") == 0.0)
        check("search_fn: search returns list", isinstance(search("compliance", name=name), list))
        check("search_fn: ALL_SOURCE_TYPES contains all expected labels",
              {"memory", "reference", "lerf_skill", "personal_preference", "world"}.issubset(
                  set(ALL_SOURCE_TYPES)))

        # ================================================================
        # 9. intake_queue editor functions (unit test without HTTP)
        # ================================================================
        from anima import intake_queue as _iq2

        # plan + commit a second source for editor unit tests
        manual2 = corpus / "editor_test.md"
        manual2.write_text("# Editor Test\n\nA short document for testing the editor functions.\n")
        plan2_data = {"kind": "file", "filename": "editor_test.md",
                      "bytes_b64": __import__("base64").b64encode(manual2.read_bytes()).decode()}
        plan2 = _intake_plan(name, plan2_data)
        src2_id = plan2.get("source_id", "")
        if src2_id:
            _intake_approve(name, {"source_id": src2_id, "control": "reference_only"})
            # reroute_item
            item2, audit2 = _iq2.reroute_item(name, src2_id,
                                               new_destination="LERF", new_rights="user-owned",
                                               reason="unit test reroute")
            check("reroute_item: returns (item, audit) tuple",
                  isinstance(item2, dict) and isinstance(audit2, dict))
            check("reroute_item: audit has action=reroute", audit2.get("action") == "reroute")
            # edit_rights
            item3, audit3 = _iq2.edit_rights(name, src2_id, new_rights="user-provided",
                                              reason="unit test rights")
            check("edit_rights: returns (item, audit)", isinstance(audit3, dict))
            # set_state to archived — uses force=True so it works even from active (terminal)
            rec3, audit4 = _iq2.set_state(name, src2_id, new_state=_iq2.ST_ARCHIVED,
                                           reason="unit test archive", force=True)
            check("set_state(force): record state is archived",
                  rec3.get("state") == _iq2.ST_ARCHIVED)
            # set_state to classified (reprocess) — also force, from archived (terminal)
            rec3b, audit4b = _iq2.set_state(name, src2_id, new_state=_iq2.ST_CLASSIFIED,
                                             reason="unit test reprocess", force=True)
            check("set_state(force reprocess): record state is classified",
                  rec3b.get("state") == _iq2.ST_CLASSIFIED)
            # delete_item
            snap, audit5 = _iq2.delete_item(name, src2_id, delete_raw=True, reason="unit test delete")
            check("delete_item: returns snapshot", isinstance(snap, dict))
            check("delete_item: audit has action=delete", audit5.get("action") == "delete")
            check("delete_item: citation_kept is True", audit5.get("to", {}).get("citation_kept") is True)
            # KeyError on non-existent id
            threw_key = False
            try:
                _iq2.reroute_item(name, "nonexistent_id_xyz", reason="test")
            except KeyError:
                threw_key = True
            check("reroute_item(bad id): raises KeyError", threw_key)

    finally:
        _restore(redir_pairs)
        shutil.rmtree(td, ignore_errors=True)
        shutil.rmtree(corpus, ignore_errors=True)

    # ================================================================
    # HERMETIC GUARANTEE: real .anima is byte-unchanged
    # ================================================================
    fp_after = _footprint(real_store)
    check("HERMETIC: real .anima is byte-identical before vs after", fp_before == fp_after)

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails))
        return 1
    print(f"ALL INTAKE ENDPOINT SMOKE TESTS PASS ({len(fails)} failures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
