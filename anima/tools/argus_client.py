"""
argus_client — Vera's READ-ONLY client for the Argus host monitor (first integration wave).

Argus (a separate local tool at ~/Developer/Argus) is treated here as an EXTERNAL, READ-ONLY,
*frozen + certified* API. This client never imports Argus code, never writes Argus state, and
never performs a host action. It speaks only to Argus's documented localhost endpoints:

  GET  /capabilities   -> discovery + the certification handshake (checked FIRST)
  GET  /mri            -> HostMRIFrame: normalized findings (the primary read surface)
  POST /ask            -> deterministic host Q&A
  GET  /timeline       -> narrated recent history
  GET  /action_log     -> audit log of actions Argus has taken
  POST /simulate       -> PROJECT an effect WITHOUT executing (read-only what-if)

CERTIFICATION HANDSHAKE (the integration gate): before reading anything, the client reads
/capabilities and REFUSES to integrate unless Argus reports the frozen, certified, safe profile:

    release                          == "v0.1-host-mri-prime"
    certification                    == "ARGUS PRIME: PASS"
    loopback_only                    is true
    read_only                        is true
    third_party_python_dependencies  == 0

This prevents Vera from ever connecting to a non-certified or ACTION-CAPABLE Argus instance.

Safety posture:
  * READ-ONLY: there is no pause/resume/host-action method in this wave. The client cannot mutate
    host networking even if asked — the capability simply does not exist here.
  * LOCAL-FIRST: a non-loopback base URL is refused. Nothing about observed traffic leaves the Mac.
  * GUARDED: Argus may be down or uncertified — every method returns a graceful value (None) and
    never raises, so a missing/uncertified monitor never breaks a Vera turn.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Optional

_PORTS = tuple(range(8787, 8799))           # Argus binds 8787, falls back to 8788..8798
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
_CONNECT_TIMEOUT = 1.2
_READ_TIMEOUT = 4.0
_TOKEN_RE = re.compile(r"""(?:token["'=:\s]{1,6})([A-Za-z0-9_\-]{24,64})""", re.I)

# The ONLY Argus profile Vera will integrate with — frozen, certified, loopback-only, read-only,
# zero-dependency. Anything else is refused at the handshake.
_REQUIRED = {
    "release": "v0.1-host-mri-prime",
    "certification": "ARGUS PRIME: PASS",
    "third_party_python_dependencies": 0,
}


def _is_loopback(base_url: str) -> bool:
    host = re.sub(r"^https?://", "", base_url or "").split("/")[0].split(":")[0]
    return host in _LOOPBACK_HOSTS


def _truthy(v) -> bool:
    return v is True or v == 1 or (isinstance(v, str) and v.strip().lower() in ("true", "yes", "1"))


def _as_int(v) -> int:
    try:
        return int(v)
    except Exception:
        return -1


def _field(caps: dict, *keys):
    """Look a field up at top-level OR under a nested 'security'/'invariants' block."""
    blocks = [caps]
    for nest in ("security", "invariants", "certification_report"):
        b = caps.get(nest)
        if isinstance(b, dict):
            blocks.append(b)
    for blk in blocks:
        for k in keys:
            if k in blk:
                return blk[k]
    return None


def certified(caps: Optional[dict]) -> tuple:
    """Does /capabilities report the frozen, certified, safe Argus? Returns (ok, reasons[])."""
    if not isinstance(caps, dict):
        return False, ["no /capabilities response"]
    reasons = []
    rel = _field(caps, "release", "version")
    if str(rel) != _REQUIRED["release"]:
        reasons.append(f"release {rel!r} != {_REQUIRED['release']!r}")
    cert = _field(caps, "certification")
    if str(cert) != _REQUIRED["certification"]:
        reasons.append(f"certification {cert!r} != {_REQUIRED['certification']!r}")
    if not _truthy(_field(caps, "loopback_only")):
        reasons.append("loopback_only is not true")
    if not _truthy(_field(caps, "read_only", "read_only_mode")):
        reasons.append("read_only is not true")
    deps = _field(caps, "third_party_python_dependencies")
    if _as_int(deps) != 0:
        reasons.append(f"third_party_python_dependencies {deps!r} != 0")
    return (not reasons), reasons


class ArgusClient:
    """A guarded, READ-ONLY client that integrates only with a certified Argus."""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None,
                 *, timeout: float = _READ_TIMEOUT):
        self.timeout = float(timeout)
        self.base_url: Optional[str] = base_url or os.environ.get("ARGUS_BASE_URL")
        self.token: Optional[str] = token or os.environ.get("ARGUS_TOKEN")
        self._discovered = False
        self.cert_ok = False
        self.cert_reasons: list = []
        self.cert_caps: Optional[dict] = None
        if self.base_url and not _is_loopback(self.base_url):       # LOCAL-FIRST
            self.base_url = None

    # -- HTTP plumbing (all guarded, read verbs only) ---------------------------------------
    def _request(self, method: str, path: str, body: Optional[dict] = None,
                 *, timeout: Optional[float] = None):
        if not self.base_url or not _is_loopback(self.base_url):
            return None
        url = self.base_url.rstrip("/") + path
        if self.token:
            url += ("&" if "?" in url else "?") + "token=" + self.token
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-Argus-Token"] = self.token
        try:
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                raw = r.read().decode("utf-8", "replace")
                return json.loads(raw) if raw.strip().startswith(("{", "[")) else {"raw": raw}
        except Exception:
            return None

    def _probe_html(self, port: int) -> Optional[str]:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=_CONNECT_TIMEOUT) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            return None

    # -- discovery + the CERTIFICATION HANDSHAKE --------------------------------------------
    def discover(self, *, force: bool = False) -> bool:
        """Find Argus on loopback AND verify the certification handshake. Returns True only for a
        live, certified, frozen Argus. Idempotent + cached. A non-certified instance is refused."""
        if self._discovered and self.cert_ok and not force:
            return True

        def _accept(base, tok) -> bool:
            self.base_url, self.token = base, tok
            caps = self.capabilities()
            if not (isinstance(caps, dict) and str(caps.get("name", "")).lower() == "argus"):
                return False
            ok, reasons = certified(caps)
            self.cert_caps, self.cert_ok, self.cert_reasons = caps, ok, reasons
            if ok:
                self._discovered = True
                return True
            # found Argus but it is NOT certified/safe -> REFUSE this integration
            self.base_url = self.token = None
            return False

        # explicit base+token (env/ctor) first
        if self.base_url and self.token and not force:
            if _accept(self.base_url, self.token):
                return True
        for port in _PORTS:
            html = self._probe_html(port)
            if not html:
                continue
            m = _TOKEN_RE.search(html)
            if not m:
                continue
            if _accept(f"http://127.0.0.1:{port}", m.group(1)):
                return True
        return False

    def available(self) -> bool:
        """Is a live, CERTIFIED Argus reachable? Never raises."""
        try:
            return self.discover()
        except Exception:
            return False

    def certification(self) -> dict:
        """The handshake result — what Argus reported and whether it cleared the gate."""
        try:
            self.discover()
        except Exception:
            pass
        return {"certified": bool(self.cert_ok), "reasons": list(self.cert_reasons),
                "base_url": self.base_url, "release": _field(self.cert_caps or {}, "release", "version")}

    # -- READ surface (the documented set; all read-only) -----------------------------------
    def capabilities(self) -> Optional[dict]:
        return self._request("GET", "/capabilities")

    def mri(self) -> Optional[dict]:
        return self._request("GET", "/mri") if self.discover() else None

    def ask(self, question: str) -> Optional[dict]:
        return self._request("POST", "/ask", {"question": str(question or "")}) if self.discover() else None

    def timeline(self, hours: int = 12) -> Optional[dict]:
        return self._request("GET", f"/timeline?hours={int(hours)}") if self.discover() else None

    def action_log(self) -> Optional[dict]:
        return self._request("GET", "/action_log") if self.discover() else None

    def simulate_pause(self, target: str) -> Optional[dict]:
        """Read-only WHAT-IF: project the effect of pausing a destination. Argus executes nothing
        (and, being read_only, would refuse a real pause anyway). No host action is taken here."""
        return self._request("POST", "/simulate", {"kind": "pause", "target": str(target)}) if self.discover() else None


_DEFAULT: Optional[ArgusClient] = None


def client() -> ArgusClient:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = ArgusClient()
    return _DEFAULT


if __name__ == "__main__":
    import sys
    c = client()
    if c.available():
        cap = c.capabilities() or {}
        print(f"Argus reachable + CERTIFIED at {c.base_url} ({cap.get('release', cap.get('version','?'))})")
        counts = ((c.mri() or {}).get("counts") or {}).get("by_severity", {})
        print("findings by severity:", counts)
    else:
        cert = c.certification()
        if cert["reasons"] and cert["reasons"] != ["no /capabilities response"]:
            print("Argus found but REFUSED (not certified):", "; ".join(cert["reasons"]))
        else:
            print("No certified Argus monitor on 127.0.0.1:8787-8798.")
    sys.exit(0)
