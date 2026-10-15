"""Title-menu labels (ゲームスタート オプション ポケットステーション おまけ ->
GAME START, OPTIONS, POCKETSTATION, EXTRAS). Two 4-bit 128x128 pictures side
by side in VRAM (832,0) / (864,0). Each label is one or two 16-row strips (a
long label continues in the next row); every label exists twice with
different shading. The English is drawn with Poppins Medium (tools/art/fonts,
SIL Open Font License), slanted, coloured row by row with the colours the
Japanese used in that row (fill: indices 1-5, 9; shadow: 6, 7, 8, A, B),
plus a 2-px shadow to the lower right. (Was work/exp21_title.py.)"""
import collections
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Poppins-Medium.ttf")

FILL, SHADE = {1, 2, 3, 4, 5, 9}, {6, 7, 8, 10, 11}

def mask(text, width, size=16, track=2, shear=0.1):
    f = ImageFont.truetype(FONT, size)
    im = Image.new("L", (width * 2, 32), 0); d = ImageDraw.Draw(im)
    x = 0
    for ch in text:
        d.text((x, 0), ch, font=f, fill=255)
        x += f.getlength(ch) + track
    a = np.array(im) > 110
    ys, xs = np.nonzero(a)
    a = a[ys.min():ys.max() + 1, :xs.max() + 1]
    h = a.shape[0]
    out = np.zeros((h, a.shape[1] + int(shear * h) + 1), bool)
    for r in range(h):                                # slant like the katakana
        s = int(round(shear * (h - 1 - r)))
        out[r, s:s + a.shape[1]] = a[r]
    return out

def label(strip, text, **kw):
    """strip: 16 x W indices (pieces joined). Returns the English strip."""
    h, w = strip.shape
    fillc, shadec = [], []
    for r in range(h):
        row = [int(v) for v in strip[r] if v]
        f = collections.Counter(v for v in row if v in FILL).most_common(1)
        s = collections.Counter(v for v in row if v in SHADE).most_common(1)
        fillc.append(f[0][0] if f else None); shadec.append(s[0][0] if s else 7)
    rows = [r for r in range(h) if fillc[r]]
    top, bot = rows[0], rows[-1]
    m = mask(text, w, **kw)
    if m.shape[0] > bot - top + 1 - 1:
        m = np.array(Image.fromarray(m).resize((m.shape[1], bot - top), Image.NEAREST))
    if m.shape[1] > w - 4:
        raise ValueError("%r is %d px wide, room for %d" % (text, m.shape[1], w - 4))
    M = np.zeros((h, w), bool)
    x0 = (w - 3 - m.shape[1]) // 2
    M[top:top + m.shape[0], x0:x0 + m.shape[1]] = m
    S = np.zeros_like(M)
    for dx, dy in ((1, 0), (2, 0), (1, 1), (2, 1)):
        S[dy:, dx:] |= M[:h - dy, :w - dx]
    S &= ~M
    out = np.zeros_like(strip)
    span = [fillc[r] for r in rows]
    for r in range(h):
        # fill colour by relative height, sampled from the Japanese
        rel = (r - top) / max(1, m.shape[0] - 1)
        fc = span[min(len(span) - 1, max(0, int(round(rel * (len(span) - 1)))))]
        out[r][M[r]] = fc
        out[r][S[r]] = shadec[min(max(r, top), bot)]
    return out

def strips(img, pieces):
    return np.hstack([img[y:y + 16, x0:x1] for y, x0, x1 in pieces])

def put(img, pieces, new):
    x = 0
    for y, x0, x1 in pieces:
        img[y:y + 16, x0:x1] = new[:, x:x + x1 - x0]; x += x1 - x0

LABELS = [  # (side, pieces, text)
    ("L", [(0, 0, 128), (16, 0, 40)], "GAME START"),
    ("L", [(96, 0, 128), (112, 0, 40)], "GAME START"),
    ("L", [(32, 0, 128)], "OPTIONS"),
    ("R", [(0, 0, 128)], "OPTIONS"),
    ("R", [(64, 0, 128), (80, 0, 104)], "POCKETSTATION"),
    ("R", [(96, 0, 128), (112, 0, 104)], "POCKETSTATION"),
    ("L", [(16, 42, 124)], "EXTRAS"),
    ("L", [(112, 42, 124)], "EXTRAS"),
]


def apply(left, right):
    px = {"L": left.copy(), "R": right.copy()}
    for side, pieces, text in LABELS:
        put(px[side], pieces, label(strips(px[side], pieces), text))
    return px["L"], px["R"]
