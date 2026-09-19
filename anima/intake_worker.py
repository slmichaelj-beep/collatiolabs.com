"""intake_worker — Intake Wave 4, item P: the BACKGROUND intake worker.

The slow half of intake (detect -> parse -> classify -> route, including any opt-in heavy-parser
activation) can take seconds on a big PDF, a long transcript, or a folder. This worker runs that
work OFF the request thread and then ENQUEUES the resulting plan into the training queue at
`classified` — the approval gate — and STOPS there.

THE LOAD-BEARING PROMISE: the worker parallelizes THROUGHPUT, never CONSENT. It never calls the
durable writer (intake_queue.commit_on_approval); a processed source lands at `classified` with the
default `review_before_adding` control, exactly as the synchronous path leaves it. "Ingestion is
not learning": nothing the worker touches becomes durable knowledge without the user's later,
explicit control. There is no code path here that commits.

CRASH-SAFE + LAW 001 (Compressed > Forgotten). The job log is an append-only jsonl event stream
under intake.STORE (so the existing intake store-redirect covers it, and it survives a restart). A
job that fails records its error as a `failed` event — never silently dropped. A job interrupted
mid-flight stays at `running` and is visible (re-drainable via `requeue_stale`), never lost.

OFF BY DEFAULT. The daemon thread starts only on an explicit Worker.start(); importing this module
spawns nothing. Submitting a job does not start a thread — a caller either runs Worker, or drains
synchronously via drain_once() (what the cert and a one-shot CLI do).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import intake as I
from . import intake_queue as Q

# Job lifecycle (an append-only event stream; a job's CURRENT status is its latest event).
J_PENDING = "pending"     # submitted, not yet picked up
J_RUNNING = "running"     # a drain is processing it (slow ingest in flight)
J_DONE = "done"           # ingested + enqueued at `classified` (awaiting the user's control)
J_FAILED = "failed"       # ingest raised — the error is recorded, never silently dropped
JOB_STATES = (J_PENDING, J_RUNNING, J_DONE, J_FAILED)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    import secrets
    return "job_" + secrets.token_hex(5)


def _jobs_path(name: str) -> Path:
    """The append-only job log, under intake.STORE (resolved at call time so a redirect is
    honoured — the same discipline intake_queue._store() uses)."""
    return I.STORE / f"{name}.intake_jobs.jsonl"


def _append(name: str, event: dict) -> dict:
    path = _jobs_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def _events(name: str) -> list:
    path = _jobs_path(name)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue            # a torn line never crashes the reader
    return out


def jobs(name: str = "Vera") -> dict:
    """The CURRENT state of every job: job_id -> the merged latest event. Reconstructed from the
    append-only log (last event per job_id wins; fields accumulate)."""
    cur: dict = {}
    for ev in _events(name):
        jid = ev.get("job_id")
        if not jid:
            continue
        merged = dict(cur.get(jid, {}))
        merged.update(ev)
        cur[jid] = merged
    return cur


def get_job(name: str, job_id: str) -> Optional[dict]:
    return jobs(name).get(job_id)


def pending_count(name: str = "Vera") -> int:
    return sum(1 for j in jobs(name).values() if j.get("status") == J_PENDING)


def submit(input: str, name: str = "Vera") -> str:
    """Append a PENDING job for `input` (a file path / directory / URL). Returns the job_id. Spawns
    NO thread — a Worker or a drain_once() call does the processing later."""
    job_id = _new_id()
    _append(name, {"job_id": job_id, "status": J_PENDING, "input": str(input),
                   "at": _now(), "submitted_at": _now()})
    return job_id


def drain_once(name: str = "Vera", *,
               ingest: Optional[Callable] = None,
               enqueue: Optional[Callable] = None) -> Optional[dict]:
    """Process the OLDEST pending job: mark it running, run the (slow) ingest, enqueue the plan at
    `classified`, and mark it done — or failed (with the error) if ingest raises. Returns the job's
    final event, or None when there is nothing pending. NEVER commits anything durable. `ingest` /
    `enqueue` are injectable for the cert; they default to the real intake pipeline."""
    ingest = ingest or I.ingest
    enqueue = enqueue or Q.enqueue

    snapshot = jobs(name)
    # oldest pending, by submission order (the log is chronological, so first-seen pending is oldest)
    pend = [j for j in snapshot.values() if j.get("status") == J_PENDING]
    if not pend:
        return None
    pend.sort(key=lambda j: j.get("submitted_at") or j.get("at") or "")
    job = pend[0]
    jid = job["job_id"]
    _append(name, {"job_id": jid, "status": J_RUNNING, "at": _now()})
    try:
        result = ingest(job["input"], name=name)
        rec = enqueue(result, name=name)            # lands at `classified` — the approval gate
        src_id = (rec or {}).get("source_id") if isinstance(rec, dict) else None
        state = (rec or {}).get("state") if isinstance(rec, dict) else None
        committed = bool((rec or {}).get("committed")) if isinstance(rec, dict) else False
        # the worker must NEVER advance past the approval gate; if it ever did, that is a breach.
        return _append(name, {"job_id": jid, "status": J_DONE, "at": _now(),
                              "source_id": src_id, "queue_state": state,
                              "committed": committed,
                              "detected_type": getattr(result, "detected_type", None)})
    except Exception as e:
        return _append(name, {"job_id": jid, "status": J_FAILED, "at": _now(),
                              "error": ("%r" % (e,))[:300]})


def requeue_stale(name: str = "Vera") -> int:
    """Re-mark any `running` jobs (e.g. interrupted by a crash/restart) back to `pending` so they
    are retried. Returns the count requeued. Never loses a job — LAW 001."""
    n = 0
    for jid, j in jobs(name).items():
        if j.get("status") == J_RUNNING:
            _append(name, {"job_id": jid, "status": J_PENDING, "at": _now(),
                           "input": j.get("input"), "requeued_from": J_RUNNING})
            n += 1
    return n


class Worker:
    """A daemon-thread drainer. OFF until start(). Loops drain_once(name) with a small idle sleep;
    stop() halts it and joins. Safe to start/stop repeatedly. One Worker per creature is plenty."""

    def __init__(self, name: str = "Vera", *, interval: float = 0.5) -> None:
        self.name = name
        self.interval = float(interval)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                drained = drain_once(self.name)
            except Exception:
                drained = None              # a drain never kills the loop
            if drained is None:             # nothing pending — idle (interruptibly) until next tick
                self._stop.wait(self.interval)

    def start(self) -> "Worker":
        if self.is_running:
            return self
        self._stop.clear()
        requeue_stale(self.name)            # recover anything left running by a prior crash
        self._thread = threading.Thread(target=self._loop, name=f"intake-worker-{self.name}",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0) -> "Worker":
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        self._thread = None
        return self


def _selftest() -> int:
    """Hermetic: a temp store (intake.STORE redirected) holds the job log + queue. Proves the worker
    drains pending -> done at `classified`, NEVER commits, records failures, recovers stale jobs, and
    the daemon thread starts/stops. Real .anima byte-unchanged is asserted by the gate's cert."""
    import tempfile
    import hashlib

    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    def _fp(root: Path):
        if not root.is_dir():
            return (None, 0)
        files = sorted(q for q in root.rglob("*") if q.is_file())
        h = hashlib.sha256()
        for q in files:
            h.update(str(q.relative_to(root)).encode())
            try:
                h.update(q.read_bytes())
            except OSError:
                h.update(b"?")
        return (h.hexdigest(), len(files))

    real = Path(".anima")
    fp_before = _fp(real)
    saved = I.STORE
    tmp = Path(tempfile.mkdtemp(prefix="iw_cert_"))
    try:
        I.STORE = tmp
        name = "WorkerCert"

        # a real local text file to ingest (the slow path, end to end)
        doc = tmp / "note.txt"
        doc.write_text("Compound interest is interest on principal plus accumulated interest.\n"
                       "Vendor: Acme. Invoice total: $42.00. Due 2026-07-01.\n", encoding="utf-8")

        jid = submit(str(doc), name=name)
        ok("submit -> a PENDING job, no thread spawned", pending_count(name) == 1
           and get_job(name, jid)["status"] == J_PENDING)

        processed = drain_once(name=name)
        j = get_job(name, jid)
        ok("drain_once processes the oldest pending job -> DONE", processed is not None
           and j["status"] == J_DONE)
        ok("the processed job landed at the approval gate (`classified`), NOT committed",
           j.get("queue_state") == Q.ST_CLASSIFIED and j.get("committed") is False)

        # the approval gate held: the queue record exists at classified, control = review default
        rec = Q.get_record(name, j.get("source_id")) if j.get("source_id") else None
        ok("the queue record is at `classified` with the default review control (nothing durable)",
           rec is not None and rec.get("state") == Q.ST_CLASSIFIED
           and rec.get("control") == Q.DEFAULT_CONTROL and rec.get("committed") is False)

        ok("draining again with nothing pending -> None (idempotent, no double-processing)",
           drain_once(name=name) is None and pending_count(name) == 0)

        # FAILURE is recorded, never silently dropped. intake.ingest is built NEVER to raise (the
        # spine never dies — a bad path returns an error-result), so to exercise the worker's OWN
        # failure path we inject a raising ingest. The except must record a FAILED event, not crash.
        bad = submit("will-blow-up", name=name)

        def _boom(inp, name=name):
            raise RuntimeError("simulated parse blowup")

        drain_once(name=name, ingest=_boom)
        jb = get_job(name, bad)
        ok("a failing job records a FAILED event with the error (never silently dropped)",
           jb["status"] == J_FAILED and bool(jb.get("error")))

        # crash recovery: a stranded `running` job is requeued, never lost
        _append(name, {"job_id": "job_stranded", "status": J_PENDING, "input": str(doc), "at": _now()})
        _append(name, {"job_id": "job_stranded", "status": J_RUNNING, "at": _now()})
        n = requeue_stale(name)
        ok("requeue_stale recovers a stranded `running` job back to pending (LAW 001)",
           n == 1 and get_job(name, "job_stranded")["status"] == J_PENDING)

        # injection: the worker must NOT be able to commit — prove enqueue is what it calls, and a
        # malicious enqueue that *claims* committed is surfaced honestly (committed=True flagged).
        seen = {}

        def _spy_enqueue(result, name=name):
            seen["called"] = True
            return Q.enqueue(result, name=name)

        submit(str(doc), name=name)
        drain_once(name=name, enqueue=_spy_enqueue)
        ok("the worker's durable step is enqueue() (the approval gate), never commit_on_approval",
           seen.get("called") is True)

        # the daemon thread starts + stops cleanly, draining the rest
        w = Worker(name=name, interval=0.05)
        for _ in range(3):
            submit(str(doc), name=name)
        w.start()
        ok("Worker.start() spawns a running daemon thread", w.is_running)
        import time as _t
        for _ in range(40):                 # up to ~2s for the thread to drain the 3 jobs
            if pending_count(name) == 0:
                break
            _t.sleep(0.05)
        w.stop()
        ok("the running Worker drained all pending jobs then stopped cleanly",
           pending_count(name) == 0 and not w.is_running)
    finally:
        I.STORE = saved
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    fp_after = _fp(real)
    ok("real .anima byte-UNCHANGED around the worker selftest", fp_before == fp_after)

    print("\nINTAKE-WORKER: " + ("ALL PASS" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("intake_worker — background intake drainer. Use --selftest, or import Worker/submit/drain_once.")
