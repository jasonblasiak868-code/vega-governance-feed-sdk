"""RED TEAM 1 - governance feed: every way to alter, cut, replace or hide a chain from the person watching it."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import fixture_feed as fx  # noqa: E402
from vega_feed.feed import Feed  # noqa: E402


def kinds(events):
    return [e["kind"] for e in events]


class A_Alterations(unittest.TestCase):
    def watch(self, n=5):
        t, paths, ch = fx.make(n)
        f = Feed({"a": paths})
        f.poll()
        return t, paths, ch, f

    def rewrite(self, paths, mutate):
        rows = [json.loads(x) for x in paths[0].read_text(encoding="utf-8").splitlines()]
        mutate(rows)
        text = "\n".join(json.dumps(r) for r in rows) + "\n"
        for p in paths:
            p.write_text(text, encoding="utf-8")

    def test_editing_the_oldest_entry(self):
        t, paths, ch, f = self.watch()
        self.rewrite(paths, lambda rows: rows[0]["payload"].update(status="forged"))
        self.assertEqual(kinds(f.poll()), ["CHAIN_BROKEN"])

    def test_editing_the_newest_entry(self):
        t, paths, ch, f = self.watch()
        self.rewrite(paths, lambda rows: rows[-1]["payload"].update(status="forged"))
        self.assertEqual(kinds(f.poll()), ["CHAIN_BROKEN"])

    def test_deleting_an_entry_from_the_middle(self):
        t, paths, ch, f = self.watch()
        self.rewrite(paths, lambda rows: rows.pop(2))
        self.assertEqual(kinds(f.poll()), ["CHAIN_BROKEN"])

    def test_reordering_entries(self):
        t, paths, ch, f = self.watch()
        self.rewrite(paths, lambda rows: rows.reverse())
        self.assertEqual(kinds(f.poll()), ["CHAIN_BROKEN"])

    def test_one_replica_changed_alone(self):
        t, paths, ch, f = self.watch()
        rows = [json.loads(x) for x in paths[1].read_text(encoding="utf-8").splitlines()]
        rows[0]["payload"]["status"] = "forged"
        paths[1].write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        self.assertEqual(kinds(f.poll()), ["CHAIN_BROKEN"])

    def test_garbage_and_binary_junk_in_the_file(self):
        for junk in (b"\x00\x01\x02not json", b"{not json}\n", b"[]\n", b"\xff\xfe"):
            t, paths, ch, f = self.watch()
            for p in paths:
                p.write_bytes(junk)
            self.assertEqual(kinds(f.poll()), ["CHAIN_BROKEN"], repr(junk))

    def test_truncation_to_zero_and_to_one(self):
        for keep in (0, 1):
            t, paths, ch, f = self.watch()
            for p in paths:
                lines = p.read_text(encoding="utf-8").splitlines()[:keep]
                p.write_text("".join(x + "\n" for x in lines), encoding="utf-8")
            self.assertEqual(kinds(f.poll()), ["CHAIN_SHORTENED"], keep)

    def test_deleting_every_replica(self):
        t, paths, ch, f = self.watch()
        for p in paths:
            p.unlink()
        self.assertEqual(kinds(f.poll()), ["CHAIN_SHORTENED"])

    def test_a_longer_replacement_chain_is_not_mistaken_for_growth(self):
        t, paths, ch, f = self.watch(3)
        t2, p2, _ = fx.make(0)
        c2 = fx.Chain(p2)
        for i in range(9):
            c2.record("EVENT", {"id": "x%d" % i})
        for p, q in zip(paths, p2):
            p.write_bytes(q.read_bytes())
        self.assertEqual(kinds(f.poll()), ["CHAIN_REWRITTEN"])

    def test_a_fork_at_the_same_length_is_noticed(self):
        t, paths, ch, f = self.watch(3)
        t2, p2, _ = fx.make(0)
        c2 = fx.Chain(p2)
        for i in range(3):
            c2.record("EVENT", {"id": "fork%d" % i})
        for p, q in zip(paths, p2):
            p.write_bytes(q.read_bytes())
        self.assertEqual(kinds(f.poll()), ["CHAIN_REWRITTEN"])

    def test_a_new_alarm_for_a_different_problem_is_announced_after_the_first(self):
        t, paths, ch, f = self.watch()
        self.rewrite(paths, lambda rows: rows[0]["payload"].update(status="forged"))
        self.assertEqual(kinds(f.poll()), ["CHAIN_BROKEN"])
        for p in paths:
            p.write_bytes(b"{junk")
        self.assertEqual(kinds(f.poll()), ["CHAIN_BROKEN"])

    def test_nothing_is_skipped_while_in_alarm(self):
        t, paths, ch, f = self.watch(2)
        keep = [p.read_bytes() for p in paths]
        for p in paths:
            p.write_bytes(b"{junk")
        f.poll()
        for p, raw in zip(paths, keep):
            p.write_bytes(raw)
        c = fx.Chain(paths)
        c.record("EVENT", {"id": "later"})
        self.assertEqual([e["summary"].get("id") for e in f.poll()], ["later"])


class B_State(unittest.TestCase):
    def test_a_missing_or_corrupt_state_file_starts_over_and_says_everything_again(self):
        t, paths, ch = fx.make(3)
        state = str(t / "state.json")
        Feed({"a": paths}, state_path=state).poll()
        for junk in (b"", b"not json", b"[]", b'{"a": {"len": -5, "head": 7}}', b'{"a": "x"}', b"\x00\xff"):
            with open(state, "wb") as fh:
                fh.write(junk)
            self.assertEqual(len(Feed({"a": paths}, state_path=state).poll()), 3, repr(junk))

    def test_a_state_file_claiming_more_than_the_chain_has_is_an_alarm_not_silence(self):
        t, paths, ch = fx.make(3)
        state = t / "state.json"
        state.write_text(json.dumps({"a": {"len": 50, "head": "00" * 32}}), encoding="utf-8")
        self.assertEqual(kinds(Feed({"a": paths}, state_path=str(state)).poll()), ["CHAIN_SHORTENED"])

    def test_a_state_file_with_the_wrong_head_is_an_alarm(self):
        t, paths, ch = fx.make(3)
        state = t / "state.json"
        state.write_text(json.dumps({"a": {"len": 2, "head": "ab" * 32}}), encoding="utf-8")
        self.assertEqual(kinds(Feed({"a": paths}, state_path=str(state)).poll()), ["CHAIN_REWRITTEN"])


if __name__ == "__main__":
    unittest.main()
