"""Disc 1 name-entry buttons (かな カナ 記号 漢字 戻る 終了 -> ABC Kana Symbol
Kanji Back Done): each 56x24 button's face is cleared and the label drawn
in font_en with a one-pixel shadow. (Was work/exp13_tabs.py.)"""
from .common import font_en

LABELS = {(0, 0): "ABC", (64, 0): "Kanji", (0, 24): "Kana", (64, 24): "Back",
          (0, 48): "Symbol", (64, 48): "Done"}
FACE, INK, SHADE = 5, 7, 0xC


def apply(px):
    px = px.copy()
    for (bx, by), text in LABELS.items():
        px[by + 3:by + 17, bx + 4:bx + 54] = FACE
        w = 6 * len(text) - 1
        x0 = bx + 4 + (50 - w) // 2
        for i, ch in enumerate(text):
            for r, row in enumerate(font_en.rows(ch)):
                for col in range(font_en.W):
                    if row >> (font_en.W - 1 - col) & 1:
                        y, x = by + 4 + r, x0 + 6 * i + col
                        px[y, x] = INK
                        if px[y + 1, x + 1] == FACE:
                            px[y + 1, x + 1] = SHADE
    return px
