#!/usr/bin/env python3
"""certify_route_backend_enforcement — per-turn route intent controls the generation backend.

Vera may have a cloud provider configured as the default brain, but the Router makes a
per-turn decision. A private/memory-grounded turn marked ``local`` must not silently
egress to the cloud just because the global mouth has a cloud brain.

Certified hermetically + offline with fake brains through the real ``Mouth.respond``
path:

  A. SELECTOR — ``Mouth.brain_for_route("local")`` returns the local backend, while
     ``"cloud:*"`` returns the provider backend when one is present.
  B. LOCAL TURN — a cloud-capable mouth handling a local route calls only the local
     brain, labels the Utterance with the local backend, and the private portrait
     memory is present only in the local system prompt.
  C. CLOUD TURN — a cloud route calls the cloud brain, labels the Utterance with the
     cloud backend, and the private portrait memory is blanked before the brain sees
     the system prompt.
  D. SERVER WIRING — server._turn passes RouteDecision.model into mouth.respond for
     the first draft and verifier retries; LERF task rendering forces the local brain.

Exit 0 == CERTIFIED, 1 == FAIL.
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


class _FakeHeart:
    name = "RouteBackendCert"

    def feeling(self) -> dict:
        return {
            "valence": 0.12,
            "arousal": 0.08,
            "reaching": 0.06,
            "settled": 0.18,
            "unrest": 0.05,
        }


class _FakeBrain:
    def __init__(self, name: str, reply: str, *, provider: str | None = None):
        self.name = name
        self._reply = reply
        self.provider = provider
        self.max_tokens = 160
        self.last_tok_s = 42.0
        self.last_prompt_tokens = 17
        self.calls: list[dict] = []
        self.creature = None

    def available(self) -> bool:
        return True

    def reply(self, system: str, user: str, history) -> str:
        self.calls.append({"system": system, "user": user, "history": list(history or [])})
        return self._reply


def main() -> int:
    from anima import mouth, portrait

    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("ROUTE BACKEND — per-turn local/cloud enforcement")
    print("=" * 72)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    secret = "ROUTE_BACKEND_CERT_PRIVATE_MEMORY_MARKER"
    turn = "Please reason carefully about the backend boundary for this private route."
    heart = _FakeHeart()

    with _temp_store():
        portrait.save(heart.name, f"- private marker: {secret}")
        local = _FakeBrain(
            "test-local",
            "The local route handled this private request without an outside call.",
        )
        cloud = _FakeBrain(
            "test-cloud",
            "The cloud route handled this non-private request after memory was withheld.",
            provider="test-provider",
        )
        m = mouth.Mouth(brain=cloud, local_brain=local)

        # ---- A. SELECTOR ------------------------------------------------------------------
        ck("A1: a local route selects the local brain, even when the default brain is cloud",
           m.brain_for_route("local") is local)
        ck("A2: a cloud route selects the configured cloud/provider brain",
           m.brain_for_route("cloud:test-provider") is cloud)

        # ---- B. LOCAL TURN ----------------------------------------------------------------
        u_local = m.respond(heart, turn, history=[], route_model="local")
        ck("B1: the local-routed turn called the local brain exactly once",
           len(local.calls) == 1)
        ck("B2: the local-routed turn did NOT call the cloud brain",
           len(cloud.calls) == 0)
        ck("B3: the shipped backend label is the local backend",
           u_local.backend == "test-local")
        ck("B4: private portrait memory is available to the local system prompt only",
           secret in local.calls[-1]["system"])

        # ---- C. CLOUD TURN ----------------------------------------------------------------
        u_cloud = m.respond(heart, turn, history=[], route_model="cloud:test-provider")
        ck("C1: the cloud-routed turn called the cloud brain exactly once",
           len(cloud.calls) == 1)
        ck("C2: the cloud-routed turn did not add a second local call",
           len(local.calls) == 1)
        ck("C3: the shipped backend label is the cloud backend",
           u_cloud.backend == "test-cloud")
        ck("C4: private portrait memory is blanked before the cloud brain sees the prompt",
           secret not in cloud.calls[-1]["system"])

        # ---- D. SERVER WIRING --------------------------------------------------------------
        server_src = (ROOT / "anima" / "server.py").read_text()
        ck("D1: server._turn passes RouteDecision.model into the first mouth.respond call",
           "route_model=_route_model" in server_src)
        ck("D2: verifier retry calls also keep the same route_model",
           server_src.count("route_model=_route_model") >= 3)
        ck("D3: LERF task rendering forces mouth.brain_for_route(\"local\")",
           'brain_for_route("local")' in server_src and "_LERF_TASK_SYS" in server_src)
        ck("D4: per-turn cloud redaction is based on the selected route, not global cloud availability",
           "if not _route_cloud:" in server_src and '"cloud_available": _cloud_on' in server_src)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (hermetic; no real memory touched)",
       fp_before == fp_after)

    print("\nROUTE-BACKEND CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
