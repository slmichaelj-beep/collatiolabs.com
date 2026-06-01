"""
nightly — let the creature sleep on its own, every night, on your Mac.

Installs a launchd agent that runs `anima.live sleep <name>` at a set hour, so the
creature consolidates the day's memories into its weights while you sleep — the
living-training loop, automated. No daemon to babysit; macOS schedules it.

    python3 -m anima.nightly install --name Nova --hour 3
    python3 -m anima.nightly uninstall --name Nova

Off a Mac, `install` just prints the plist so you can see exactly what it does.
"""

from __future__ import annotations

import argparse
import io
import os
import plistlib
import subprocess
import sys
from pathlib import Path


def _plist(name, hour, workdir, python):
    label = f"com.anima.{name}"
    log = str(Path(workdir) / ".anima" / f"{name}.sleep.log")
    return label, {
        "Label": label,
        "ProgramArguments": [python, "-m", "anima.live", "sleep", name],
        "WorkingDirectory": workdir,
        "StartCalendarInterval": {"Hour": int(hour), "Minute": 0},
        "StandardOutPath": log,
        "StandardErrorPath": log,
        "RunAtLoad": False,
    }


def install(name, hour):
    workdir = os.getcwd()
    label, plist = _plist(name, hour, workdir, sys.executable)
    agents = Path.home() / "Library" / "LaunchAgents"
    if not agents.parent.exists():            # not macOS — show, don't pretend
        buf = io.BytesIO(); plistlib.dump(plist, buf)
        print("Not macOS. On your Mac, save this to "
              f"~/Library/LaunchAgents/{label}.plist and `launchctl load` it:\n")
        print(buf.getvalue().decode())
        return
    agents.mkdir(parents=True, exist_ok=True)
    path = agents / f"{label}.plist"
    with open(path, "wb") as f:
        plistlib.dump(plist, f)
    subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
    subprocess.run(["launchctl", "load", str(path)], capture_output=True)
    print(f"{name} will now sleep nightly at {int(hour):02d}:00. ({path})")
    print(f"(it consolidates whatever you've said to it that day; logs -> .anima/{name}.sleep.log)")


def uninstall(name):
    label = f"com.anima.{name}"
    path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    if path.exists():
        subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
        path.unlink()
        print(f"removed nightly sleep for {name}.")
    else:
        print(f"no nightly agent installed for {name}.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="anima.nightly")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("install")
    i.add_argument("--name", default="Vera")
    i.add_argument("--hour", type=int, default=3)
    u = sub.add_parser("uninstall")
    u.add_argument("--name", default="Vera")
    args = ap.parse_args(argv)
    if args.cmd == "install":
        install(args.name, args.hour)
    else:
        uninstall(args.name)


if __name__ == "__main__":
    main()
