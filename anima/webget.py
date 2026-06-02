"""
webget — read-only web fetch, hard-restricted to an explicit allow-list of domains.

The companion is offline by default. This is the one, narrow exception: it will fetch
a page ONLY if its host is on the user's allow-list (subdomains of an allowed domain
are permitted; nothing else is). It refuses non-http(s) schemes, refuses redirects
that leave the allow-list (checked on the redirect itself, not after the fact), caps
the body size, and returns stripped text — never executes anything. No allow-list
entry ⇒ nothing is reachable.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .caps import _norm_host


def host_allowed(url: str, allowlist) -> bool:
    try:
        u = urlparse(url)
    except Exception:
        return False
    if u.scheme not in ("http", "https"):
        return False
    host = (u.hostname or "").lower()
    if not host:
        return False
    for a in allowlist:
        a = _norm_host(a)
        if a and (host == a or host == "www." + a or host.endswith("." + a)):
            return True
    return False


class _AllowlistRedirect(urllib.request.HTTPRedirectHandler):
    """Block a redirect the moment it would leave the allow-list."""

    def __init__(self, allowlist):
        self.allowlist = allowlist

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_allowed(newurl, self.allowlist):
            raise urllib.error.HTTPError(newurl, code, "redirect off allow-list", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_WS = re.compile(r"\n\s*\n\s*\n+")


def _strip_html(html: str) -> str:
    html = _SCRIPT.sub(" ", html)
    text = _TAG.sub(" ", html)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
            .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"'))
    text = "\n".join(line.strip() for line in text.splitlines())
    return _WS.sub("\n\n", text).strip()


def fetch(url: str, allowlist, max_bytes: int = 2_000_000, max_chars: int = 20_000) -> dict:
    """Fetch an allow-listed URL and return stripped text. Never raises."""
    if not host_allowed(url, allowlist):
        return {"ok": False, "error": "host is not on your allow-list"}
    opener = urllib.request.build_opener(_AllowlistRedirect(allowlist))
    req = urllib.request.Request(url, headers={"User-Agent": "anima/1.0 (local companion)"})
    try:
        with opener.open(req, timeout=15) as r:
            final = r.geturl()
            if not host_allowed(final, allowlist):          # belt-and-suspenders
                return {"ok": False, "error": "redirected off your allow-list"}
            raw = r.read(max_bytes)
        text = _strip_html(raw.decode("utf-8", "ignore"))
        return {"ok": True, "url": final, "text": text[:max_chars]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
