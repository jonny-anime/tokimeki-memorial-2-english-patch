"""File-select screen pictures (Disc 2).

date_box(): the background piece with the date box has 年 月 日 baked in
(digits are separate sprites): 年 and 日 are erased and 月 becomes "/"
(ink 10, outline 2, the colours of the original glyphs).

buttons(): button labels are index-1 letters cut out of a gradient fill
(one colour per row). Each button's rows get their gradient colour back and
the English is drawn in index 1 with font_en capitals made bold (OR with a
1-px shift: 6 px wide, 9 rows, 7 px pitch). (Was work/exp19_buttons.py.)"""
import collections
import numpy as np
from .common import font_en, outline


def date_box(px):
    px = px.copy()
    px[26:40, 4:24] = 0        # 年
    px[26:40, 44:64] = 0       # 月
    px[26:40, 85:101] = 0      # 日
    g = np.zeros(px.shape, bool)
    for i, r in enumerate(range(37, 27, -1)):
        c = 47 + i * 5 // 9
        g[r, c] = g[r, c + 1] = True
    px[outline(g)] = 2
    px[g] = 10
    return px


def _glyph(ch):
    g = np.zeros((9, 6), bool)
    for r, row in enumerate(font_en.rows(ch)[:9]):
        for c in range(5):
            if row >> (4 - c) & 1:
                g[r, c] = g[r, c + 1] = True
    return g


def _text(s):
    m = np.zeros((9, 7 * len(s) - 1), bool)
    for i, ch in enumerate(s):
        m[:, 7 * i:7 * i + 6] |= _glyph(ch)
    return m


def buttons(px, specs):
    """specs: [(x0, x1, y0, y1, "TEXT" or "LINE1|LINE2")], inclusive ranges."""
    px = px.copy()
    for x0, x1, y0, y1, text in specs:
        for y in range(y0, y1 + 1):
            row = px[y, x0:x1 + 1]
            fill = collections.Counter(int(v) for v in row if v not in (1, 2)).most_common(1)[0][0]
            row[(row == 1) | (row == 2)] = fill
        lines = text.split("|")
        h = 9 * len(lines) + 3 * (len(lines) - 1)
        top = y0 + (y1 - y0 + 1 - h) // 2
        for k, line in enumerate(lines):
            m = _text(line)
            left = x0 + (x1 - x0 + 1 - m.shape[1]) // 2
            px[top + 12 * k:top + 12 * k + 9, left:left + m.shape[1]][m] = 1
    return px


NEW_LOAD = [(3, 58, 114, 124, "NEW"), (69, 124, 114, 124, "LOAD")]
COPY_ERASE = [(3, 58, 114, 124, "COPY"), (69, 124, 114, 124, "ERASE")]
SAVE = [(59, 114, 114, 124, "SAVE")]
REBUILD = [(3, 124, 98, 119, "REBUILD|SYSTEM FILE")]
