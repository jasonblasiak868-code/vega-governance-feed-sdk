"""Shared helpers for the feed tests (not a test file)."""
import pathlib
import tempfile

from vega_custody.dag.dag import Chain


def make(n=0, replicas=2):
    t = pathlib.Path(tempfile.mkdtemp())
    paths = [t / ("r%d.jsonl" % i) for i in range(replicas)]
    ch = Chain(paths)
    for i in range(n):
        ch.record("EVENT", {"id": "e%d" % i, "status": "ok"})
    return t, paths, ch
