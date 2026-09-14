"""living_map.schema — the STATIC topology of Vera's operational digital twin.

NODES are the subsystems (organs); EDGES are the flows between them. Every node declares a
``source_of_truth`` list naming the REAL stores / traces that back its live status — the no-wallpaper
cert verifies that nothing claims a health colour without a real source behind it.

This module is pure data + schema: no I/O, no live status. ``graph.py`` resolves live status from the
real sources named here. Keeping topology and resolution separate is what lets the no-wallpaper cert
check, per node, that "this node's status came from these named real sources, not a constant."
"""
from __future__ import annotations

# Status vocabulary (product-consistent). 'unknown' / 'stale' / 'disabled' are HONEST states — a node
# with no live data MUST be one of these, never a fake green.
STATUS = ("green", "yellow", "red", "blue", "purple", "gray", "unknown", "stale", "disabled", "external")

# Node types -> visual family (organ kind). Drives glyph + grouping in the UI.
NODE_TYPES = ("actor", "interface", "router", "security_gate", "memory", "knowledge", "pipeline",
              "cognition", "analysis", "model", "model_runtime", "governance", "security", "audit",
              "host", "infra")

EDGE_TYPES = ("data_flow", "control_flow", "safety_flow", "telemetry_flow", "host_flow")


# ---------------------------------------------------------------------------------------------
# NODES — Vera's subsystems. `source_of_truth` names the real stores/functions graph.py reads.
# ---------------------------------------------------------------------------------------------
NODES = [
    {"node_id": "user", "label": "User", "type": "actor",
     "description": "The person talking to Vera. Origin of every turn; no telemetry about the human.",
     "source_of_truth": []},
    {"node_id": "chat_ui", "label": "Chat / UI", "type": "interface",
     "description": "The web/voice surface where turns arrive and replies ship.",
     "source_of_truth": ["turn_mri", "web/index.html"]},
    {"node_id": "route_classifier", "label": "Route Classifier", "type": "router",
     "description": "Classifies each turn (simple-chat fast path vs normal model route vs identity challenge).",
     "source_of_truth": ["anima/route_classifier.py", "turn_mri"]},
    {"node_id": "context_immune", "label": "Context Immune System", "type": "security_gate",
     "description": "Scans context and quarantines hostile/injected content before it can become trusted.",
     "source_of_truth": ["security_events", "incident.quarantines", "anima/immune.py"]},
    {"node_id": "history", "label": "Conversation History", "type": "memory",
     "description": "Recent turns, immune-cleaned and token-budgeted before re-entering the prompt.",
     "source_of_truth": ["Vera.history.json", "turn_mri"]},
    {"node_id": "memory", "label": "Memory (LIRF + Portrait)", "type": "memory",
     "description": "Durable personal memory: LIRF facts + the prose portrait + world-state situation.",
     "source_of_truth": ["Vera.mem.json", "Vera.json", "anima/memory_lirf.py"]},
    {"node_id": "known_facts", "label": "Known Facts", "type": "memory",
     "description": "Structured, bound LIRF facts (the Knowledge Spine) — stated, never disclaimed.",
     "source_of_truth": ["anima/memory_lirf.py", "anima/spine.py"]},
    {"node_id": "sources", "label": "Sources (Reference Library)", "type": "knowledge",
     "description": "Cite-only uploaded documents/links; query-relevant chunks, injection-flagged ones excluded.",
     "source_of_truth": ["intake_queue.references", "source_aware.quarantined_sources"]},
    {"node_id": "intake", "label": "UKI / Intake", "type": "pipeline",
     "description": "Universal Knowledge Intake: detect -> parse -> classify -> store -> index.",
     "source_of_truth": ["intake store", "intake_mri"]},
    {"node_id": "ocr", "label": "OCR / Transcription", "type": "pipeline",
     "description": "Native-first OCR for scanned PDFs/images and audio transcription, sandboxed.",
     "source_of_truth": ["intake store", "host_pressure"]},
    {"node_id": "lerf", "label": "LERF / Skills", "type": "cognition",
     "description": "Compressed certified skills tried before the model (language-organ demotion).",
     "source_of_truth": ["lerf store", "Vera.lerf_routes.jsonl"]},
    {"node_id": "patterns", "label": "Pattern Observatory", "type": "analysis",
     "description": "Repeated issues Vera has observed, with severity/frequency/root-cause/evidence.",
     "source_of_truth": ["reports/patterns.json"]},
    {"node_id": "improvements", "label": "Improvement Engine", "type": "analysis",
     "description": "Vera's self-generated backlog: recommendation + expected benefit + required cert.",
     "source_of_truth": ["reports/improvement_backlog.json", "reports/roi_ledger.json"]},
    {"node_id": "prompt_compiler", "label": "Prompt Compiler", "type": "cognition",
     "description": "Assembles the per-turn prompt by section (persona/memory/history/safety) within budget.",
     "source_of_truth": ["turn_mri:prompt", "anima/mouth.py"]},
    {"node_id": "model_runtime", "label": "Model Runtime", "type": "model",
     "description": "The 8B local model call; routed/deferred by host pressure policy.",
     "source_of_truth": ["model-usage.json", "host_pressure", "perf_trace"]},
    {"node_id": "ollama", "label": "Ollama", "type": "model_runtime",
     "description": "Local inference server hosting the model; keep_alive policy is pressure-aware.",
     "source_of_truth": ["model-usage.json", "ollama_api"]},
    {"node_id": "final_gate", "label": "Final Output Gate", "type": "security_gate",
     "description": "Model-free floor every reply crosses: blocks hostile output + #1-rule breaks.",
     "source_of_truth": ["anima/mouth.py:final_output_gate", "incident.quarantines"]},
    {"node_id": "capability_truth", "label": "Capability Truth", "type": "security",
     "description": "The caps gate: every outward power (mail/iMessage/web/host) is OFF unless granted.",
     "source_of_truth": ["caps.load"]},
    {"node_id": "approval_queue", "label": "Approval Queue", "type": "governance",
     "description": "Wave 2 Alpha: suggested agency actions wait here for explicit human approval.",
     "source_of_truth": ["agency_approval_queue"]},
    {"node_id": "identity_sandbox", "label": "Identity Sandbox", "type": "governance",
     "description": "Freeze-safe identity observability — observe-first-change-later.",
     "source_of_truth": ["identity_sandbox store"]},
    {"node_id": "agency_suggest", "label": "Agency Suggest-Only", "type": "governance",
     "description": "Vera may SUGGEST actions (with evidence), never execute — suggest-only by law.",
     "source_of_truth": ["agency_suggest", "security_events"]},
    {"node_id": "security", "label": "Security / Quarantine", "type": "security",
     "description": "The quarantine surface: hostile catches + injection-flagged sources, held as evidence.",
     "source_of_truth": ["incident.quarantines", "source_aware.quarantined_sources"]},
    {"node_id": "lockdown", "label": "Incident Lockdown", "type": "security",
     "description": "The panic button: forces every outward capability OFF, reversible + audited.",
     "source_of_truth": ["incident.status"]},
    {"node_id": "audit", "label": "Audit / Program Reality", "type": "audit",
     "description": "Live-path certification: COMPLETE/PARTIAL/WALLPAPER per feature — proof, not promise.",
     "source_of_truth": ["reports/live_path_results.json"]},
    {"node_id": "argus", "label": "Argus Host Telemetry", "type": "host",
     "description": "Host pressure (memory/swap) signal that steers model policy + heavy-job deferral.",
     "source_of_truth": ["host_pressure", "argus_client"]},
    {"node_id": "jobs", "label": "Queues / Background Jobs", "type": "infra",
     "description": "Background workers (intake parsing, indexing). Deferred under host pressure.",
     "source_of_truth": ["intake worker queue"]},
    {"node_id": "founder_console", "label": "Founder Console", "type": "interface",
     "description": "The operator surfaces: Observatory, Patterns & Improvements, Security, Living Map.",
     "source_of_truth": ["web/console.html", "web/living_map.html"]},
]

NODE_IDS = {n["node_id"] for n in NODES}


# ---------------------------------------------------------------------------------------------
# EDGES — the flows. Each edge's status is derived in graph.py from the same real sources.
# ---------------------------------------------------------------------------------------------
def _e(eid, frm, to, typ, classes, **safety):
    return {"edge_id": eid, "from": frm, "to": to, "type": typ, "data_classes": list(classes),
            "safety": safety}


EDGES = [
    # the turn spine: user -> ... -> response -> trace -> pattern -> improvement
    _e("user_to_chat", "user", "chat_ui", "data_flow", ["user_text"]),
    _e("chat_to_route", "chat_ui", "route_classifier", "control_flow", ["user_text"]),
    _e("route_to_immune", "route_classifier", "context_immune", "safety_flow", ["user_text", "history"],
       requires_scan=True),
    _e("immune_to_history", "context_immune", "history", "data_flow", ["clean_history"], quarantine_possible=True),
    _e("immune_to_memory", "context_immune", "memory", "data_flow", ["retrieval_query"]),
    _e("memory_to_known", "memory", "known_facts", "data_flow", ["lirf_rows"]),
    _e("memory_to_prompt", "memory", "prompt_compiler", "data_flow", ["memory_bundle"]),
    _e("known_to_prompt", "known_facts", "prompt_compiler", "data_flow", ["bound_facts"]),
    _e("history_to_prompt", "history", "prompt_compiler", "data_flow", ["capped_history"]),
    _e("sources_to_immune", "sources", "context_immune", "safety_flow", ["source_text", "retrieval_snippet"],
       requires_source_safety=True, quarantine_possible=True),
    _e("route_to_lerf", "route_classifier", "lerf", "control_flow", ["task"]),
    _e("lerf_to_prompt", "lerf", "prompt_compiler", "data_flow", ["skill_result"]),
    _e("prompt_to_model", "prompt_compiler", "model_runtime", "data_flow", ["compiled_prompt"]),
    _e("model_to_ollama", "model_runtime", "ollama", "control_flow", ["inference_request"]),
    _e("model_to_gate", "model_runtime", "final_gate", "safety_flow", ["draft_reply"]),
    _e("lerf_to_gate", "lerf", "final_gate", "safety_flow", ["deterministic_reply"]),
    _e("gate_to_chat", "final_gate", "chat_ui", "data_flow", ["safe_reply"], quarantine_possible=True),
    # safety + governance
    _e("immune_to_security", "context_immune", "security", "safety_flow", ["quarantine_evidence"]),
    _e("gate_to_security", "final_gate", "security", "safety_flow", ["blocked_output_evidence"]),
    _e("security_to_patterns", "security", "patterns", "telemetry_flow", ["security_event"]),
    _e("capability_to_agency", "capability_truth", "agency_suggest", "control_flow", ["caps_state"]),
    _e("agency_to_approval", "agency_suggest", "approval_queue", "control_flow", ["suggested_action"]),
    _e("lockdown_to_capability", "lockdown", "capability_truth", "control_flow", ["force_off"]),
    _e("identity_to_agency", "identity_sandbox", "agency_suggest", "control_flow", ["identity_state"]),
    # telemetry + analysis
    _e("chat_to_audit", "chat_ui", "audit", "telemetry_flow", ["turn_trace"]),
    _e("audit_to_patterns", "audit", "patterns", "telemetry_flow", ["live_path_results"]),
    _e("patterns_to_improvements", "patterns", "improvements", "telemetry_flow", ["pattern"]),
    _e("improvements_to_console", "improvements", "founder_console", "telemetry_flow", ["backlog", "roi"]),
    _e("security_to_console", "security", "founder_console", "telemetry_flow", ["soc_trail"]),
    _e("audit_to_console", "audit", "founder_console", "telemetry_flow", ["audit_matrix"]),
    # host
    _e("argus_to_model", "argus", "model_runtime", "host_flow", ["host_pressure"]),
    _e("argus_to_jobs", "argus", "jobs", "host_flow", ["host_pressure"]),
    _e("argus_to_ocr", "argus", "ocr", "host_flow", ["host_pressure"]),
    # intake pipeline
    _e("intake_to_ocr", "intake", "ocr", "data_flow", ["raw_document"]),
    _e("ocr_to_sources", "ocr", "sources", "data_flow", ["parsed_text"], requires_source_safety=True),
    _e("intake_to_jobs", "intake", "jobs", "control_flow", ["parse_task"]),
]

# sanity: every edge endpoint is a real node id (checked again by the no-wallpaper cert)
for _ed in EDGES:
    assert _ed["from"] in NODE_IDS and _ed["to"] in NODE_IDS, _ed["edge_id"]


def node_schema_example() -> dict:
    """The documented node JSON shape (for the cert + API consumers)."""
    return {"node_id": "context_immune", "label": "Context Immune System", "type": "security_gate",
            "status": "green|yellow|red|unknown|disabled", "description": "...",
            "live_metrics": {"events_last_24h": 0, "blocked_last_24h": 0, "avg_latency_ms": 0},
            "source_of_truth": ["security_events", "turn_mri", "context_safety_registry"],
            "last_updated": "..."}
