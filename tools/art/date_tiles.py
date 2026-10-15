"""Main-screen date tiles (with tools/datepatch.py): the weekday tiles of row
0 become Su Mo Tu We Th Fr Sa and the 年 tile (u 32, v 16) becomes "/".
Ink 8 with a 1-px index-1 outline, like the original glyphs. (Was
work/exp16_date.py.)"""
import numpy as np
from .common import letters, outline

INK, OUT = 8, 1
DAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]


def _put(px, x, y, glyph):
    box = px[y:y + 16, x:x + 16]
    box[:] = 0
    box[outline(glyph)] = OUT
    box[glyph] = INK


def slash(h=16, w=16, bottom=12, top=3, left=5):
    g = np.zeros((h, w), bool)
    n = bottom - top
    for i, r in enumerate(range(bottom, top - 1, -1)):
        c = left + i * 5 // n
        g[r, c] = g[r, c + 1] = True
    return g


def apply(px):
    px = px.copy()
    for k, name in enumerate(DAYS):
        _put(px, 16 * k, 0, letters(name, 4, 2, 16, 16))
    _put(px, 32, 16, slash())
    return px
