# Vera — Governance & Control Map (Phase 8, GRC)

A reviewer's index: each security/privacy control Vera claims, mapped to the **cert that proves it**
(not prose). Every cert is runnable; the live-path audit (`scripts/certify_live_paths.py --gate`) and
`scripts/diamond_cert.py` aggregate them. Statuses are taken from the audit matrix, never hand-set.

| Control (CIS / SOC-2 CC mapping) | How Vera satisfies it | Cert |
|---|---|---|
| **Access control** (CC6.1) | constant-time `ANIMA_TOKEN` auth wall + Face-ID layer; 401 before dispatch | `certify_security_baseline` |
| **Least privilege / default-deny** (CC6.1) | every outward cap OFF by default; read≠act; route.py gates each action | `certify_permissions`, `certify_security_baseline` |
| **Capability fail-safe** (CC6.1) | corrupt enum coerces to safe default; sources can't self-grant | `certify_permissions`, `certify_ai_security` |
| **Data deletion / right to erasure** (CC6.5, GDPR 17) | delete a source (raw purged + audited); forget a memory (retract) | `certify_privacy` |
| **Confidentiality in transit to cloud** (CC6.7) | structured PII + known names scrubbed before any cloud egress | `certify_privacy`, `certify.py` PII tier |
| **Portability** (GDPR 20) | export/import a self-describing Mind Bundle | `certify_privacy` |
| **Input integrity / injection defense** (CC6.8) | source-is-data; injection detected, flagged, and **neutralized** before the model | `certify_ai_security` |
| **Audit logging** (CC7.2) | append-only, timestamped security event trail | `certify_incident_response` |
| **Incident response** (CC7.3, CC7.4) | one-call lockdown → safe state; reversible; audited; runbook | `certify_incident_response` |
| **Availability / recovery** (A1.2) | backups, health checks, corruption recovery; disk pre-flight | `certify_reliability_recovery`, `certify_live_ux` |
| **Resource safety** (A1.1) | host-pressure deferral; bounded generation; model unload under load | `certify_host_pressure`, `certify_performance` |
| **Change management / deploy integrity** (CC8.1) | running == committed (sha + clean tree) before any green | `deploy_check`, `diamond_cert` |
| **Monitoring & secret hygiene** (CC7.1) | token never logged; metrics/telemetry; MRI traces | `certify_security_baseline`, `certify_metrics_telemetry` |

## Honest scope
This is the **engineering evidence** a SOC-2 / ISO program would attest to — not a substitute for a
formal audit, a signed DPA, or third-party penetration testing. Those are organizational artifacts
beyond a local-first product's code. What's here is real, runnable proof that the underlying controls
exist and hold. Residual disclosed items live in `docs/threat_model.md` (Out of scope) and each
contract's `known_gaps`.
