import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import font_en  # noqa: E402


def outline(glyph):
    """Pixels within 1 px (8 neighbours) of the glyph, the glyph included."""
    o = np.zeros_like(glyph)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            o |= np.roll(np.roll(glyph, dy, 0), dx, 1)
    return o


def letters(text, top, left, h, w, pitch=6):
    """font_en glyphs as a boolean mask of size (h, w), first glyph row at
    `top`, first letter at `left`."""
    g = np.zeros((h, w), bool)
    x = left
    for ch in text:
        for r, row in enumerate(font_en.rows(ch)):
            for c in range(font_en.W):
                if row >> (font_en.W - 1 - c) & 1:
                    g[top + r, x + c] = True
        x += pitch
    return g
