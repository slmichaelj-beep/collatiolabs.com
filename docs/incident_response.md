# Vera — Incident Response Runbook (Phase 7)

Vera is local-first, single-user, on the user's Mac. "Incident response" here means: a fast, reversible
way to put Vera into a **safe state**, plus a local trail to review afterward. Backed by
`anima/incident.py` and certified by `scripts/certify_incident_response.py`.

## The panic button

```
python3 -m anima.incident lockdown "why"     # enter safe state
python3 -m anima.incident status             # see posture + recent events
python3 -m anima.incident restore            # lift it
```

**Lockdown** forces **every** outward capability OFF — mail, iMessage, web, host access, calendar,
reminders, notes, autonomous growth — *regardless of what's enabled in settings*. It's enforced at the
gate (`caps.enabled` returns `False` while locked), so nothing can send, fetch, or act. It is:
- **reversible** — `restore` hands the user's stored settings back, untouched (lockdown overrides, never deletes);
- **audited** — every lockdown/restore is written to the security event trail;
- **idempotent** — a second lockdown is safe; restoring with nothing active is a no-op.

## When to lock down
- You suspect a malicious or poisoned source was ingested.
- You see unexpected outbound activity (cross-check with Argus).
- You're handing the Mac to someone else, or stepping away mid-sensitive-work.
- Anything feels off and you want Vera inert until you've looked.

## Playbook
1. **Contain** — `lockdown "<reason>"`. Vera is now inert outward; the conversation still works.
2. **Assess** — `status` for the event trail; the live-path audit (`scripts/certify_live_paths.py`)
   for posture; Argus for host/network. Identify what changed.
3. **Eradicate** — delete the suspect source (right-to-erasure: `intake_queue.delete_item`); retract any
   poisoned memory (`memory_lirf` retraction, the "forget that" path).
4. **Recover** — `restore` to return to normal; re-run `scripts/diamond_cert.py --gate` to confirm green.
5. **Review** — the security event trail + the MRI traces tell you what happened, cold.

## What is NOT automated (honest)
- Lockdown is **manual** (or script-invoked) — there is no auto-trip heuristic yet; that's a deliberate
  choice to avoid false-positive self-lockouts. An auto-trip on a strong Argus signal is a tracked item.
- Notification/paging is out of scope for a single-user local product (you are the on-call).
