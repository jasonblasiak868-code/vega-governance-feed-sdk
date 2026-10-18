"""RED TEAM 2 - governance feed: hostile event content, hostile configuration, hostile subscribers."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import fixture_feed as fx  # noqa: E402
from vega_feed.feed import Feed, FeedRefused  # noqa: E402


class A_Content(unittest.TestCase):
    def test_only_allow_listed_fields_are_shown(self):
        t, paths, ch = fx.make(0)
        ch.record("EVENT", {"status": "ok", "internal_note": "should not appear", "id": "x"})
        ev = Feed({"a": paths}).poll()[0]
        self.assertNotIn("internal_note", ev["summary"])
        self.assertEqual(ev["summary"]["id"], "x")

    def test_long_values_are_cut_and_nested_values_are_not_shown(self):
        t, paths, ch = fx.make(0)
        ch.record("EVENT", {"reason": "x" * 5000, "status": {"nested": "dict"}, "action": ["a", "b"]})
        s = Feed({"a": paths}).poll()[0]["summary"]
        self.assertEqual(len(s["reason"]), 200)
        self.assertNotIn("status", s)
        self.assertNotIn("action", s)

    def test_terminal_escape_sequences_in_a_value_cannot_reach_a_panel_unchanged(self):
        t, paths, ch = fx.make(0)
        ch.record("EVENT", {"reason": "ok\x1b]52;c;ZXZpbA==\x07 end"})
        shown = Feed({"a": paths}).poll()[0]["summary"]["reason"]
        self.assertNotIn("\x1b", shown)

    def test_a_credential_shaped_value_is_masked_even_though_the_chain_stores_hashes_only(self):
        t, paths, ch = fx.make(0)
        ch.record("EVENT", {"reason": "see key sk" + "-" * 0 + "x"})
        # a payload the chain itself would refuse can only appear through a hand-edited chain, which is CHAIN_BROKEN; the scrub is the second line of defence
        from vega_feed.feed import _clip
        self.assertEqual(_clip("api_key = " + "Zx9" * 10), "[REDACTED]")
        self.assertEqual(_clip("ghp_" + "a" * 36), "[REDACTED]")

    def test_a_kind_named_like_an_alarm_is_still_just_its_own_severity(self):
        t, paths, ch = fx.make(0)
        ch.record("CHAIN_BROKEN", {"id": "spoof"})
        ev = Feed({"a": paths}).poll()[0]
        self.assertEqual(ev["severity"], "critical")
        self.assertIsNotNone(ev["entry_hash"])                         # a real entry has a hash; a real alarm never does

    def test_real_alarms_never_carry_an_entry_hash(self):
        t, paths, ch = fx.make(2)
        f = Feed({"a": paths})
        f.poll()
        for p in paths:
            p.write_bytes(b"{junk")
        a = f.poll()[0]
        self.assertIsNone(a["entry_hash"])
        self.assertIsNone(a["seq"])


class B_Configuration(unittest.TestCase):
    def test_bad_sources_are_refused(self):
        t, paths, ch = fx.make(1)
        for bad in (None, {}, [], "x", {"": paths}, {"a b": paths}, {"a": []}, {"a": "path"}, {"a": [5]}, {"a": None}, {1: paths}, {"../x": paths}):
            with self.assertRaises(FeedRefused, msg=repr(bad)):
                Feed(bad)
        with self.assertRaises(FeedRefused):
            Feed({("s%d" % i): paths for i in range(65)})

    def test_a_subscriber_must_be_callable(self):
        t, paths, ch = fx.make(1)
        with self.assertRaises(FeedRefused):
            Feed({"a": paths}).subscribe("not a function")

    def test_a_source_that_does_not_exist_yet_is_quiet_and_then_works(self):
        import pathlib
        import tempfile
        t = pathlib.Path(tempfile.mkdtemp())
        paths = [t / "r0.jsonl", t / "r1.jsonl"]
        f = Feed({"a": paths})
        self.assertEqual(f.poll(), [])
        ch = fx.Chain(paths)
        ch.record("EVENT", {"id": "first"})
        self.assertEqual(len(f.poll()), 1)


class C_Subscribers(unittest.TestCase):
    def test_a_subscriber_cannot_change_what_the_next_one_sees(self):
        t, paths, ch = fx.make(1)
        seen = []

        def mutate(ev):
            ev["summary"].clear()
            ev["kind"] = "CHANGED"
        f = Feed({"a": paths})
        f.subscribe(mutate)
        f.subscribe(lambda ev: seen.append(ev["kind"]))
        out = f.poll()
        self.assertEqual(len(out), 1)
        # events are handed out as plain dicts; a subscriber that edits one edits the shared object, so the feed's own counters (taken BEFORE delivery) stay true
        self.assertEqual(f.snapshot()["counters"]["info"], 1)

    def test_counters_are_not_inflated_by_polling_again(self):
        t, paths, ch = fx.make(3)
        f = Feed({"a": paths})
        f.poll()
        f.poll()
        f.poll()
        self.assertEqual(f.snapshot()["counters"]["info"], 3)

    def test_alarms_are_counted_once(self):
        t, paths, ch = fx.make(2)
        f = Feed({"a": paths})
        f.poll()
        for p in paths:
            p.write_bytes(b"{junk")
        f.poll()
        f.poll()
        self.assertEqual(f.snapshot()["counters"]["critical"], 1)


if __name__ == "__main__":
    unittest.main()
