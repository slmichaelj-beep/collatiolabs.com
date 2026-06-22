#!/usr/bin/env python3
"""certify_vault_requires_encryption — product/private mode refuses plaintext vault startup.

Local development can still run plaintext with an honest banner. Product/private mode cannot:
`--require-encryption`, `ANIMA_REQUIRE_ENCRYPTION=1`, or `ANIMA_PRODUCT_MODE=1` must refuse
startup unless ANIMA_KEY or the macOS Keychain item is available.
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


def _env(cwd: Path, *, key: str | None = None, require: bool = False) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["ANIMA_STORE"] = str(cwd / "store")
    env["ANIMA_DISABLE_KEYCHAIN"] = "1"
    env.pop("ANIMA_TOKEN", None)
    if key is None:
        env.pop("ANIMA_KEY", None)
    else:
        env["ANIMA_KEY"] = key
    if require:
        env["ANIMA_REQUIRE_ENCRYPTION"] = "1"
    else:
        env.pop("ANIMA_REQUIRE_ENCRYPTION", None)
    env.pop("ANIMA_PRODUCT_MODE", None)
    return env


def _run(argv: list[str], cwd: Path, env: dict, timeout: float = 8.0) -> tuple[int | None, str]:
    p = subprocess.Popen(argv, cwd=str(cwd), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        out, _ = p.communicate(timeout=5)
    return p.returncode, out


def main() -> int:
    fails: list[str] = []

    def ck(label: str, cond: bool):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("VAULT ENFORCEMENT — private/product mode requires encrypted vault")
    print("=" * 82)
    t0 = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="vera-vault-required-") as td:
        cwd = Path(td)

        port = _free_port()
        code, out = _run(
            [sys.executable, "-m", "anima.server", "--name", "VaultCert",
             "--port", str(port), "--require-encryption"],
            cwd, _env(cwd, key=None),
        )
        ck("A1: --require-encryption without ANIMA_KEY exits non-zero", code not in (0, None))
        ck("A2: refusal names encrypted vault setup without printing a key",
           "refusing to start Vera in private/product mode" in out
           and "ANIMA_KEY" in out and "cert-vault-key" not in out)
        ck("A3: --require-encryption without a key did NOT bind the port",
           not _can_connect(port))

        port2 = _free_port()
        code2, out2 = _run(
            [sys.executable, "-m", "anima.server", "--name", "VaultCert", "--port", str(port2)],
            cwd, _env(cwd, key=None, require=True),
        )
        ck("B1: ANIMA_REQUIRE_ENCRYPTION=1 without ANIMA_KEY exits non-zero",
           code2 not in (0, None))
        ck("B2: env-var refusal also names encrypted vault setup",
           "refusing to start Vera in private/product mode" in out2)
        ck("B3: env-var refusal did NOT bind the port", not _can_connect(port2))

        port3 = _free_port()
        env3 = _env(cwd, key="cert-vault-key", require=True)
        p3 = subprocess.Popen(
            [sys.executable, "-m", "anima.server", "--name", "VaultCert", "--port", str(port3)],
            cwd=str(cwd), env=env3,
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
            ck("C1: ANIMA_REQUIRE_ENCRYPTION=1 with ANIMA_KEY starts and binds",
               listening and p3.poll() is None)
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
        cr.emit("certify_vault_requires_encryption", "green" if green else "red",
                files_observed=[
                    "anima/server.py",
                    "anima/crypto.py",
                    "scripts/certify_vault_requires_encryption.py",
                ],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nVAULT-REQUIRES-ENCRYPTION CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
