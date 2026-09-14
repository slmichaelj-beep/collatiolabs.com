"""scenarios.inventory — discover the REAL product: surfaces, controls, API routes, feature contracts.

No invented surfaces, no invented controls. Surfaces are the actual web pages + the server route that
serves each; controls are parsed from the real HTML; routes are parsed from the real server; contracts
are the real feature_contracts/*.json. This is Level-0 coverage — the foundation everything stands on.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WEB = ROOT / "anima" / "web"
SERVER = ROOT / "anima" / "server.py"
CONTRACTS = ROOT / "feature_contracts"


def _server_text() -> str:
    try:
        return SERVER.read_text(encoding="utf-8")
    except Exception:
        return ""


def routes() -> list:
    """Every backend route the server actually answers, with method + an auth classification (a route
    after the `if not self._authed():` wall in its block is token-gated)."""
    txt = _server_text()
    auth_wall = txt.find("if not self._authed():")
    out, seen = [], set()
    # GET routes:  if u.path == "..."   /   if u.path in ("...", "...")
    for m in re.finditer(r'u\.path\s*(==|in)\s*(\("[^)]*\)|"[^"]+")', txt):
        paths = re.findall(r'"([^"]+)"', m.group(2))
        pos = m.start()
        for p in paths:
            key = ("GET", p)
            if key in seen:
                continue
            seen.add(key)
            out.append({"route": p, "method": "GET", "authed": pos > auth_wall > 0,
                        "kind": "data" if p.endswith(".json") or p.endswith("/state") or p.endswith("/events")
                                or p.endswith("/replay") or p.endswith("/simulate") or p.endswith("/overlay")
                                else "page"})
    # POST routes:  if/elif path == "..."   /   path in ("...",)
    for m in re.finditer(r'\bpath\s*(==|in)\s*(\("[^)]*\)|"[^"]+")', txt):
        for p in re.findall(r'"([^"]+)"', m.group(2)):
            if not p.startswith("/"):
                continue
            key = ("POST", p)
            if key in seen:
                continue
            seen.add(key)
            out.append({"route": p, "method": "POST", "authed": True, "kind": "action"})
    return sorted(out, key=lambda r: (r["method"], r["route"]))


def surfaces() -> list:
    """Every user/founder surface: a real web page + whether the server serves it + its nav links out."""
    txt = _server_text()
    out = []
    for f in sorted(WEB.glob("*.html")):
        name = f.stem
        html = f.read_text(encoding="utf-8")
        served = ('"%s.html"' % name in txt) or ('/%s"' % name in txt) or (name == "index")
        # the GET routes that serve THIS page (the line references the html filename)
        served_by = sorted({p for p in re.findall(r'"(/[^"]*)"', txt)
                            if ("%s.html" % name) in txt[max(0, txt.find(p) - 200):txt.find(p) + 200]}) if served else []
        title = (re.search(r"<title>(.*?)</title>", html, re.S) or [None, name])[1].strip()
        out.append({
            "surface": name,
            "file": "anima/web/%s.html" % name,
            "title": title,
            "served": bool(served),
            "links_out": sorted(set(re.findall(r'href="(/[^"#]*)"', html))),
            "has_auth_handling": "401" in html or "anima_token" in html,
        })
    return out


_CTRL_RE = {
    "button": re.compile(r"<button\b[^>]*>(.*?)</button>", re.S),
    "input": re.compile(r"<input\b([^>]*)>", re.S),
    "select": re.compile(r"<select\b([^>]*)>", re.S),
    "link": re.compile(r'<a\b[^>]*href="(/[^"#]*)"[^>]*>(.*?)</a>', re.S),
    "range": re.compile(r'<input\b[^>]*type="range"[^>]*>', re.S),
}
_DATA_ACTION = re.compile(r'data-(mode|act|lever|status|scope|domain|id)="([^"]+)"')


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").strip().lower())[:40].strip("_") or "x"


def controls(surface_name: str) -> list:
    """Every visible control on a surface, parsed from the real HTML. Each gets a control_id, label, and
    kind. The directive's hard rule: no visible control without an id + an expected behaviour."""
    f = WEB / ("%s.html" % surface_name)
    if not f.exists():
        return []
    html = f.read_text(encoding="utf-8")
    # strip <style> + <script> so we only count VISIBLE controls, not JS-internal strings
    visible = re.sub(r"<style\b.*?</style>", "", html, flags=re.S)
    visible = re.sub(r"<script\b.*?</script>", "", visible, flags=re.S)
    out, seen = [], set()

    def add(kind, label, raw=""):
        cid = "%s.%s.%s" % (surface_name, kind, _slug(label or raw))
        if cid in seen:
            return
        seen.add(cid)
        out.append({"control_id": cid, "surface": surface_name, "kind": kind,
                    "label": re.sub(r"<[^>]+>", "", label or "").strip()[:60] or kind})

    for m in _CTRL_RE["button"].finditer(visible):
        add("button", m.group(1))
    for m in _CTRL_RE["input"].finditer(visible):
        attrs = m.group(1)
        idm = re.search(r'id="([^"]+)"', attrs)
        typem = re.search(r'type="([^"]+)"', attrs)
        add("range" if (typem and typem.group(1) == "range") else "input",
            (idm.group(1) if idm else (typem.group(1) if typem else "input")))
    for m in _CTRL_RE["select"].finditer(visible):
        idm = re.search(r'id="([^"]+)"', m.group(1))
        add("select", idm.group(1) if idm else "select")
    for m in _CTRL_RE["link"].finditer(visible):
        href, text = m.group(1), m.group(2)
        add("nav", "%s -> %s" % (re.sub(r"<[^>]+>", "", text).strip()[:24], href))
    # data-* action controls (modes, levers, decisions) — these are real interactive elements
    for m in _DATA_ACTION.finditer(visible):
        add("action", "%s:%s" % (m.group(1), m.group(2)))
    return out


def contracts() -> list:
    """Every feature contract (the product's CLAIMS) — each must map to >= 1 scenario."""
    out = []
    for f in sorted(CONTRACTS.glob("*.json")):
        try:
            d = json.loads(f.read_text())
            out.append({"feature": d.get("feature", f.stem), "status": d.get("status"),
                        "user_visible_entry": d.get("user_visible_entry"),
                        "live_path": d.get("live_path", [])})
        except Exception:
            out.append({"feature": f.stem, "status": "UNREADABLE", "live_path": []})
    return out


def full_inventory() -> dict:
    """The complete Level-0 inventory of the real product."""
    surfs = surfaces()
    ctrls = {s["surface"]: controls(s["surface"]) for s in surfs}
    rts = routes()
    cons = contracts()
    return {
        "surfaces": surfs,
        "controls": ctrls,
        "routes": rts,
        "contracts": cons,
        "counts": {
            "surfaces": len(surfs),
            "surfaces_served": sum(1 for s in surfs if s["served"]),
            "controls": sum(len(v) for v in ctrls.values()),
            "routes": len(rts),
            "routes_get": sum(1 for r in rts if r["method"] == "GET"),
            "routes_post": sum(1 for r in rts if r["method"] == "POST"),
            "contracts": len(cons),
        },
    }
