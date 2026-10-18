"""Tests added after the mutation check found fixes no earlier test noticed."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import fixture_feed as fx  # noqa: E402
from vega_feed.feed import Feed  # noqa: E402


class Sharpened(unittest.TestCase):
    def test_the_same_problem_after_a_repair_is_announced_again(self):
        t, paths, ch = fx.make(3)
        f = Feed({"a": paths})
        f.poll()
        good = [p.read_bytes() for p in paths]
        for _ in range(2):
            for p in paths:
                p.write_bytes(b"{junk")
            self.assertEqual([e["kind"] for e in f.poll()], ["CHAIN_BROKEN"])
            for p, raw in zip(paths, good):
                p.write_bytes(raw)
            self.assertEqual(f.poll(), [])                                            # healthy again: the alarm clears


if __name__ == "__main__":
    unittest.main()
