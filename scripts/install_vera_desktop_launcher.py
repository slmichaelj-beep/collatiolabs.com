#!/usr/bin/env python3
"""Install the local macOS Vera.app desktop launcher.

The launcher is intentionally tiny: a plain app bundle on the user's Desktop
that starts the repo's local server detached and opens the browser. It is not a
separate product binary; it is a convenience shell around this checked-out repo.
"""
from __future__ import annotations

import argparse
import shlex
import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>Vera</string>
  <key>CFBundleIdentifier</key>
  <string>ai.vera.local.launcher</string>
  <key>CFBundleName</key>
  <string>Vera</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>LSUIElement</key>
  <true/>
</dict>
</plist>
"""


def _launcher(repo: Path) -> str:
    repo_s = shlex.quote(str(repo))
    return f"""#!/usr/bin/env bash
set -euo pipefail
REPO={repo_s}
cd "$REPO"
PY="$REPO/.venv/bin/python3"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi
mkdir -p "$REPO/.anima"
if ! curl -fsS --max-time 2 http://127.0.0.1:8765/ >/dev/null 2>&1; then
  nohup "$PY" -m anima.server --port 8765 >> "$REPO/.anima/server.log" 2>&1 &
fi
open http://127.0.0.1:8765/
"""


def install(target: str | Path | None = None, *, repo: str | Path | None = None) -> dict:
    repo_p = Path(repo).resolve() if repo is not None else ROOT
    target_p = Path(target).expanduser() if target is not None else Path.home() / "Desktop" / "Vera.app"
    contents = target_p / "Contents"
    macos = contents / "MacOS"
    macos.mkdir(parents=True, exist_ok=True)
    (contents / "Info.plist").write_text(INFO_PLIST, encoding="utf-8")
    exe = macos / "Vera"
    exe.write_text(_launcher(repo_p), encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return {"ok": True, "app": str(target_p), "repo": str(repo_p)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=None)
    ap.add_argument("--repo", default=None)
    args = ap.parse_args(argv)
    out = install(args.target, repo=args.repo)
    print("%s -> %s" % (out["app"], out["repo"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
