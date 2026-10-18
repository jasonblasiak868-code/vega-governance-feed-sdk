"""Functional tests for the governance feed."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import fixture_feed as fx  # noqa: E402
from vega_feed.feed import Feed, severity  # noqa: E402


class Basics(unittest.TestCase):
    def test_new_events_once(self):
        t, paths, ch = fx.make(3)
        f = Feed({"a": paths})
        self.assertEqual(len(f.poll()), 3)
        self.assertEqual(f.poll(), [])
        ch.record("TERMINAL_DENIED", {"reason": "needs signature", "action": "terminal_exec"})
        ev = f.poll()
        self.assertEqual((len(ev), ev[0]["severity"]), (1, "alert"))
        self.assertEqual(ev[0]["summary"]["action"], "terminal_exec")

    def test_severity_words(self):
        self.assertEqual(severity("MORNA_SKIP"), "alert")
        self.assertEqual(severity("TRACE_MAPPING"), "info")
        self.assertEqual(severity("CHAIN_BROKEN"), "critical")

    def test_subscribers_get_events_and_one_crashing_does_not_stop_the_rest(self):
        t, paths, ch = fx.make(2)
        got = []
        f = Feed({"a": paths})

        def boom(ev):
            raise RuntimeError("x")
        f.subscribe(boom)
        f.subscribe(got.append)
        f.poll()
        self.assertEqual(len(got), 2)

    def test_state_survives_a_restart(self):
        t, paths, ch = fx.make(3)
        state = str(t / "state.json")
        Feed({"a": paths}, state_path=state).poll()
        ch.record("EVENT", {"id": "new"})
        self.assertEqual(len(Feed({"a": paths}, state_path=state).poll()), 1)

    def test_multiple_sources_and_counters(self):
        t1, p1, c1 = fx.make(2)
        t2, p2, c2 = fx.make(1)
        f = Feed({"one": p1, "two": p2})
        f.poll()
        self.assertEqual(f.snapshot()["counters"]["info"], 3)
        self.assertEqual(f.snapshot()["counters"]["one:EVENT"], 2)


class Tamper(unittest.TestCase):
    def test_an_edited_entry_raises_one_critical_alarm_and_clears_when_repaired(self):
        t, paths, ch = fx.make(4)
        f = Feed({"a": paths})
        f.poll()
        original = [p.read_bytes() for p in paths]
        rows = [json.loads(x) for x in paths[0].read_text(encoding="utf-8").splitlines()]
        rows[1]["payload"]["status"] = "forged"
        for p in paths:
            p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        a = f.poll()
        self.assertEqual([e["kind"] for e in a], ["CHAIN_BROKEN"])
        self.assertEqual(f.poll(), [])                                              # same problem is not re-announced
        for p, raw in zip(paths, original):
            p.write_bytes(raw)
        ch2 = fx.Chain(paths)
        ch2.record("EVENT", {"id": "after"})
        self.assertEqual([e["kind"] for e in f.poll()], ["EVENT"])

    def test_cutting_off_the_newest_entries_is_noticed(self):
        t, paths, ch = fx.make(5)
        f = Feed({"a": paths})
        f.poll()
        for p in paths:
            lines = p.read_text(encoding="utf-8").splitlines()
            p.write_text("\n".join(lines[:3]) + "\n", encoding="utf-8")
        self.assertEqual([e["kind"] for e in f.poll()], ["CHAIN_SHORTENED"])

    def test_replacing_history_with_another_valid_chain_is_noticed(self):
        t, paths, ch = fx.make(3)
        f = Feed({"a": paths})
        f.poll()
        t2, p2, c2 = fx.make(0)
        c2 = fx.Chain(p2)
        for i in range(5):
            c2.record("EVENT", {"id": "other%d" % i})
        for p, q in zip(paths, p2):
            p.write_bytes(q.read_bytes())
        self.assertEqual([e["kind"] for e in f.poll()], ["CHAIN_REWRITTEN"])


if __name__ == "__main__":
    unittest.main()
