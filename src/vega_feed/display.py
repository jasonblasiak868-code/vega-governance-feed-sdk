"""display.py - text that is safe to show: terminal escape sequences and control characters removed."""
import re

_ESC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?|\x1b[P^_X][^\x1b]*(?:\x1b\\)?|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-Z\\-_]|\x9b[0-?]*[ -/]*[@-~]|\x9d[^\x07\x9c]*[\x07\x9c]?")
_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩﻿]")


def plain(text):
    """Escape sequences peeled until none is left (so ESC ESC [ ... cannot re-form one), then any remaining control character becomes a space."""
    prev = None
    while prev != text:
        prev = text
        text = _ESC.sub("", text)
    return _CTRL.sub(" ", text)
