"""feed.py - the live governance feed: what the governed system is doing, read from the custody chains as they grow, with a loud alarm when a chain has been tampered with.

A Feed watches named sources (each a custody chain: one or more replica file paths). poll() returns the new events since the last poll. For every source it also checks the chain itself:
  CHAIN_BROKEN      the chain does not verify (an entry was edited, a replica disagrees, a file is unreadable)             critical
  CHAIN_SHORTENED   the chain is shorter than it was at the last poll (the newest entries were cut off)                      critical
  CHAIN_REWRITTEN   the entry the feed last saw is no longer the entry at that position (history was replaced)               critical
An alarm is raised once per distinct problem, not every poll. While a source is in alarm its cursor does not advance, so nothing is silently skipped.
Events carry a short summary built ONLY from an allow-list of payload fields, each credential-scrubbed, stripped of terminal escape sequences and cut to 200 characters; the full entry stays on
the chain. The feed reads; it never writes to a chain and never decides anything."""
import hashlib
import json
import os
import re
import threading

from vega_custody import safepaths as sp
from vega_custody.dag.dag import Chain, ChainBroken, DagError, contains_credential
from vega_feed.display import plain

SHOW = ("action", "cls", "status", "reason", "verdict", "state", "model", "lane", "task_class", "role", "kind", "gate", "origin", "level", "depth", "health", "id", "decision", "outcome")
ALERT_WORDS = ("DENIED", "REFUSED", "HALT", "SKIP", "FAIL", "REJECT", "REVOKE", "BURNED")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
MAX_SOURCES = 64


class FeedRefused(ValueError):
    pass


def _clip(v):
    s = v if isinstance(v, str) else json.dumps(v, sort_keys=True, default=str)
    p = plain(s)
    if contains_credential(s) or contains_credential(p):   # an escape sequence inserted inside a key must not hide it
        return "[REDACTED]"
    return p[:200]


def summarize(entry):
    p = entry.get("payload", {})
    return {k: _clip(p[k]) for k in SHOW if k in p and isinstance(p[k], (str, int, float, bool))}


def severity(kind):
    k = str(kind).upper()
    if k.startswith("CHAIN_"):
        return "critical"
    return "alert" if any(w in k for w in ALERT_WORDS) else "info"


class Feed:
    def __init__(self, sources, state_path=None):
        if not isinstance(sources, dict) or not sources or len(sources) > MAX_SOURCES:
            raise FeedRefused("sources is a non-empty dict of at most %d named chains" % MAX_SOURCES)
        self.sources = {}
        for name, paths in sources.items():
            if not isinstance(name, str) or not _NAME.fullmatch(name):
                raise FeedRefused("a source name is a plain id")
            if isinstance(paths, (str, bytes)) or not isinstance(paths, (list, tuple)) or not paths or any(not isinstance(p, (str, os.PathLike)) for p in paths):
                raise FeedRefused("a source is a list of replica file paths")
            self.sources[name] = [str(p) for p in paths]
        self.state_path = state_path
        self.cursor = {n: {"len": 0, "head": None} for n in self.sources}
        self._alarmed = {}
        self._subs = []
        self.counters = {}
        self._lock = threading.Lock()
        if state_path and os.path.exists(state_path):
            try:
                saved = json.loads(sp.read_capped(state_path, 1 << 20).decode("utf-8"))
                if not isinstance(saved, dict):
                    raise ValueError("state is not an object")
                for n in self.sources:
                    c = saved.get(n)
                    if isinstance(c, dict) and isinstance(c.get("len"), int) and not isinstance(c.get("len"), bool) and c["len"] >= 0 and (c.get("head") is None or isinstance(c.get("head"), str)):
                        self.cursor[n] = {"len": c["len"], "head": c.get("head")}
            except (OSError, ValueError, sp.PathRefused):
                pass  # reviewed: an unreadable state file means the feed starts from the beginning and says everything again, which is the safe direction

    def subscribe(self, fn):
        if not callable(fn):
            raise FeedRefused("a subscriber is a function")
        self._subs.append(fn)

    def _save(self):
        if self.state_path:
            sp.atomic_write(self.state_path, json.dumps(self.cursor, sort_keys=True))

    def _alarm(self, name, kind, detail):
        sig = hashlib.sha256((kind + detail).encode()).hexdigest()
        if self._alarmed.get(name) == sig:
            return []
        self._alarmed[name] = sig
        return [{"source": name, "seq": None, "kind": kind, "severity": "critical", "summary": {"reason": _clip(detail)}, "entry_hash": None}]

    def poll(self):
        out = []
        with self._lock:
            for name, paths in self.sources.items():
                cur = self.cursor[name]
                if not any(os.path.exists(p) for p in paths):
                    if cur["len"]:
                        out += self._alarm(name, "CHAIN_SHORTENED", "was %d entries, now the chain files are gone" % cur["len"])
                    continue                                                    # a chain never written yet is not an alarm; one that had entries and vanished is
                try:
                    ch = Chain(paths)
                except ChainBroken as exc:
                    out += self._alarm(name, "CHAIN_BROKEN", str(exc))
                    continue
                except (OSError, ValueError, DagError) as exc:
                    out += self._alarm(name, "CHAIN_BROKEN", "unreadable: %s" % exc)
                    continue
                rows = ch.entries()
                if len(rows) < cur["len"]:
                    out += self._alarm(name, "CHAIN_SHORTENED", "was %d entries, now %d" % (cur["len"], len(rows)))
                    continue
                if cur["len"] and rows[cur["len"] - 1].get("entry_hash") != cur["head"]:
                    out += self._alarm(name, "CHAIN_REWRITTEN", "the entry last seen at position %d is not there any more" % (cur["len"] - 1))
                    continue
                self._alarmed.pop(name, None)
                for e in rows[cur["len"]:]:
                    out.append({"source": name, "seq": e["seq"], "kind": e["kind"], "severity": severity(e["kind"]), "summary": summarize(e), "entry_hash": e["entry_hash"]})
                if rows:
                    cur["len"], cur["head"] = len(rows), rows[-1]["entry_hash"]
            for ev in out:
                self.counters[ev["severity"]] = self.counters.get(ev["severity"], 0) + 1
                k = "%s:%s" % (ev["source"], ev["kind"])
                self.counters[k] = self.counters.get(k, 0) + 1
            self._save()
        for ev in out:
            for fn in list(self._subs):
                try:
                    fn(ev)
                except Exception:
                    pass  # reviewed: one failing subscriber must not stop the feed or the others
        return out

    def snapshot(self):
        """Counters plus each source's cursor: a point-in-time view for a status panel."""
        with self._lock:
            return {"cursor": json.loads(json.dumps(self.cursor)), "counters": dict(self.counters), "alarmed": sorted(self._alarmed)}
