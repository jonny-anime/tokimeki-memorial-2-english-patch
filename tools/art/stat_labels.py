"""Main-screen stat labels (体調 文系 理系 芸術 運動 雑学 容姿 根性 ストレス).
Each label is a 40x16 slot, 3 per row at y 80/96/112; the Japanese is ink
plus a 1-px index-1 outline, and so is the English. (Was work/exp14_stats.py.)"""
import collections
import numpy as np
from .common import letters, outline

LABELS = {(0, 80): "Health", (40, 80): "Lit.", (80, 80): "Sci.",
          (0, 96): "Art", (40, 96): "Sports", (80, 96): "Trivia",
          (0, 112): "Looks", (40, 112): "Guts", (80, 112): "Stress"}


def apply(px):
    px = px.copy()
    for (bx, by), text in LABELS.items():
        box = px[by:by + 16, bx:bx + 40]
        ink = collections.Counter(int(v) for v in box.ravel() if v not in (0, 1)).most_common(1)[0][0]
        assert 6 * len(text) + 1 <= 40, text
        glyph = letters(text, 3, 2, 16, 40)
        box[:] = 0
        box[outline(glyph)] = 1
        box[glyph] = ink
    return px


def with_record(record, packet_ja, packet_en):
    """The main screen draws the labels from an image record that also holds
    the hand cursors (pictures/main_stats_hands.png): take the record and
    copy in every pixel the English packet changed."""
    return np.where(packet_en != packet_ja, packet_en, record).astype(np.uint8)
