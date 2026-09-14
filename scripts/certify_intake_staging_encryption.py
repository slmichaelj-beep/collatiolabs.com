#!/usr/bin/env python3
"""certify_intake_staging_encryption — raw intake staging is sealed at rest.

The intake parser APIs expect normal files, but the durable staging directory must not hold
raw uploads/text when ANIMA_KEY is set. This cert proves the new shape:
  * _write_staging stores sealed bytes for text, URL, and uploaded file kinds;
  * raw staged files do not contain a synthetic secret;
  * parser materialization produces the original bytes in a short-lived temp file;
  * the temp file is removed after the parser handoff context exits.
"""
from __future__ import annotations

import base64
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fails: list[str] = []

    def ck(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("INTAKE STAGING ENCRYPTION — sealed durable staging, temp parser handoff")
    print("=" * 86)
    t0 = time.perf_counter()

    old_cwd = Path.cwd()
    old_key = os.environ.get("ANIMA_KEY")
    with tempfile.TemporaryDirectory(prefix="intake-stage-cert-") as td:
        os.environ["ANIMA_KEY"] = "intake-stage-cert-key"
        os.chdir(td)
        try:
            from anima import server

            server.STORE = Path(".anima")
            name = "StageSealCert"
            secret = "RAW_STAGE_SECRET_91e5b7"

            text_path = server._write_staging(name, "src_text", "text", {"text": secret})
            url_path = server._write_staging(name, "src_url", "url", {"input": "https://example.invalid/" + secret})
            blob = ("file-prefix-" + secret + "-file-suffix").encode("utf-8")
            file_path = server._write_staging(
                name, "src_file", "file",
                {"filename": "upload.txt", "bytes_b64": base64.b64encode(blob).decode("ascii")},
            )

            text_raw = text_path.read_text(encoding="utf-8")
            url_raw = url_path.read_text(encoding="utf-8")
            file_raw = file_path.read_bytes()
            ck("A1: text staging is physically encrypted with ANIMAENC marker",
               text_raw.startswith("ANIMAENC1:"))
            ck("A2: URL staging is physically encrypted with ANIMAENC marker",
               url_raw.startswith("ANIMAENC1:"))
            ck("A3: uploaded-file staging is physically encrypted with ANIMAENC marker",
               file_raw.startswith(b"ANIMAENC1:"))
            ck("A4: no durable staging bytes contain the synthetic secret",
               secret not in text_raw and secret not in url_raw
               and secret.encode("utf-8") not in file_raw)

            with server._materialized_staging(text_path) as tmp_text:
                tmp_text_path = Path(tmp_text)
                ck("B1: materialized text temp exists during parser handoff", tmp_text_path.exists())
                ck("B2: materialized text temp recovers original secret",
                   tmp_text_path.read_text(encoding="utf-8") == secret)
            ck("B3: materialized text temp is removed after handoff", not tmp_text_path.exists())

            with server._materialized_staging(file_path) as tmp_file:
                tmp_file_path = Path(tmp_file)
                ck("C1: materialized file temp exists during parser handoff", tmp_file_path.exists())
                ck("C2: materialized file temp recovers original bytes", tmp_file_path.read_bytes() == blob)
            ck("C3: materialized file temp is removed after handoff", not tmp_file_path.exists())

            ck("D1: URL staging text load recovers original URL",
               server._staging_text(url_path).endswith(secret))
            ck("D2: _read_staging still finds sealed staged files by source id",
               server._read_staging(name, "src_file") == (file_path, True))
        finally:
            os.chdir(old_cwd)
            if old_key is None:
                os.environ.pop("ANIMA_KEY", None)
            else:
                os.environ["ANIMA_KEY"] = old_key

    green = not fails
    try:
        from anima.verification.cert_result import emit
        emit("certify_intake_staging_encryption", "green" if green else "red",
             files_observed=[
                 "anima/server.py",
                 "anima/secure_store.py",
                 "anima/crypto.py",
                 "scripts/certify_intake_staging_encryption.py",
             ],
             evidence_paths=["reports/cert_results/certify_intake_staging_encryption.json"],
             failures=fails,
             duration_sec=time.perf_counter() - t0,
             next_action="" if green else "Fix raw intake staging encryption/materialization")
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nINTAKE-STAGING-ENCRYPTION CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
