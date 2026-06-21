#!/usr/bin/env python3
"""certify_expose_requires_auth — LAN exposure cannot start without ANIMA_TOKEN.

This adversarial cert reproduces the old failure mode: `--expose` with no token
started a LAN listener. The fixed behavior is fail-closed before binding.

It also proves the intended path still works when ANIMA_TOKEN is present.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def _can_connect(port: int) -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=0.4)
        s.close()
        return True
    except Exception:
        return False


def _env(token: str | None, cwd: Path) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["ANIMA_STORE"] = str(cwd / "store")
    env.pop("ANIMA_KEY", None)
    if token is None:
        env.pop("ANIMA_TOKEN", None)
    else:
        env["ANIMA_TOKEN"] = token
    return env


def main() -> int:
    fails: list[str] = []

    def ck(label: str, cond: bool):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("EXPOSE AUTH — non-loopback bind requires ANIMA_TOKEN")
    print("=" * 74)
    t0 = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="vera-expose-auth-") as td:
        cwd = Path(td)

        # A. Old failure mode: --expose with no token must refuse and must not bind.
        port = _free_port()
        p = subprocess.Popen(
            [sys.executable, "-m", "anima.server", "--name", "ExposeCert", "--port", str(port), "--expose"],
            cwd=str(cwd), env=_env(None, cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            out, _ = p.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate(timeout=5)
        ck("A1: --expose without ANIMA_TOKEN exits non-zero", p.returncode != 0)
        ck("A2: refusal names ANIMA_TOKEN and does not print a secret",
           "ANIMA_TOKEN" in out and "refusing to expose Vera" in out)
        ck("A3: --expose without ANIMA_TOKEN did NOT bind the port", not _can_connect(port))

        # B. Manual non-loopback host is also blocked without token.
        port2 = _free_port()
        p2 = subprocess.Popen(
            [sys.executable, "-m", "anima.server", "--name", "ExposeCert", "--port", str(port2),
             "--host", "0.0.0.0"],
            cwd=str(cwd), env=_env(None, cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            out2, _ = p2.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            p2.kill()
            out2, _ = p2.communicate(timeout=5)
        ck("B1: --host 0.0.0.0 without ANIMA_TOKEN exits non-zero", p2.returncode != 0)
        ck("B2: manual non-loopback refusal also names ANIMA_TOKEN", "ANIMA_TOKEN" in out2)
        ck("B3: --host 0.0.0.0 without ANIMA_TOKEN did NOT bind the port", not _can_connect(port2))

        # C. With a token, expose may start; this proves we did not remove the intended path.
        port3 = _free_port()
        p3 = subprocess.Popen(
            [sys.executable, "-m", "anima.server", "--name", "ExposeCert", "--port", str(port3), "--expose"],
            cwd=str(cwd), env=_env("cert-token", cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        listening = False
        try:
            deadline = time.time() + 10
            while time.time() < deadline:
                if _can_connect(port3):
                    listening = True
                    break
                if p3.poll() is not None:
                    break
                time.sleep(0.2)
            ck("C1: --expose with ANIMA_TOKEN starts and binds", listening and p3.poll() is None)
        finally:
            if p3.poll() is None:
                p3.terminate()
                try:
                    p3.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    p3.kill()
                    p3.communicate(timeout=5)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_expose_requires_auth", "green" if green else "red",
                files_observed=["anima/server.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nEXPOSE-REQUIRES-AUTH CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
