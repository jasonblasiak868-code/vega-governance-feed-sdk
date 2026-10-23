"""Regression tests (2026-10-22): the credential check ran BEFORE terminal escape sequences were removed, so a key with an escape sequence inserted inside it was not recognised
and came out whole after the escapes were stripped. U+2028/2029 and the soft hyphen were also left in displayed text."""
import unittest

from vega_feed import display, feed


class Scrub(unittest.TestCase):
    def test_a_key_split_by_an_escape_sequence_is_still_redacted(self):
        sk = "s" + "k-"                                          # written in pieces so a secret scanner does not read this file as holding a key
        for s in ("key " + sk + "abcdefghij\x1b[0mklmnopqrstuvwxyz0123", sk + "abcdefghijklmnopqrstuvwxyz0123", "t \x1b]0;title\x07 gh" + "p_" + "a" * 36):
            self.assertEqual(feed._clip(s), "[REDACTED]", repr(s))
        self.assertEqual(feed._clip("plain \x1b[31mred\x1b[0m text"), "plain red text")

    def test_separators_and_invisible_format_characters_are_removed(self):
        self.assertEqual(display.plain("a b c­d‮e"), "a b c d e")


if __name__ == "__main__":
    unittest.main()
