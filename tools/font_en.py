"""English font and letter-pair encoding for TM2's dialogue renderer.

The game draws every 2-byte character into one 16 x 15 cell, 19 px apart.
English uses two narrow letters per cell ("letter pairs"): the 2-byte code
names both letters, and the patched glyph lookup (tools/glyphpatch.py)
builds the cell bitmap from this font at run time.

Code of a pair cell (left letter L, right letter R, both from CHARSET):
    lead byte  = LEAD[index(L)]   (values no original script uses, see
                                   docs/game-internals.md section 9.2)
    trail byte = 0x40 + index(R)  (0x40..0x87)

Glyphs are 5 x 11 pixels ('#' = ink), placed at cell rows 3-13: left letter
at x 0-4, right letter at x 10-14. Glyph rows: 0-8 capitals and ascenders,
3-8 x-height (baseline under row 8), 9-10 descenders.

The artwork below is original to this project. Edit it freely; the patch
builder packs it (5-bit rows, most significant bit first, glyph i at
bit 55*i; 495 bytes in all).
"""

CHARSET = " ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?'\"-~\u2026"
W, H = 5, 11          # glyph size in pixels
CELL_TOP = 3          # cell row of glyph row 0
LEFT_X, RIGHT_X = 0, 10   # x of the left and right letter in the 16-px cell

# Lead byte for glyph index i: 0xA0-0xDF, then 0x85-0x87, then 0xEB-0xEF.
LEAD = list(range(0xA0, 0xE0)) + [0x85, 0x86, 0x87] + list(range(0xEB, 0xF0))
TRAIL0 = 0x40

ART = """
[sp]-  [A]--  [B]--  [C]--  [D]--  [E]--  [F]--  [G]--  [H]--  [I]--  [J]--  [K]--
.....  .###.  ####.  .###.  ###..  #####  #####  .###.  #...#  .###.  ..###  #...#
.....  #...#  #...#  #...#  #..#.  #....  #....  #...#  #...#  ..#..  ...#.  #..#.
.....  #...#  #...#  #....  #...#  #....  #....  #....  #...#  ..#..  ...#.  #.#..
.....  #...#  #...#  #....  #...#  #....  #....  #....  #...#  ..#..  ...#.  ##...
.....  #####  ####.  #....  #...#  ####.  ####.  #.###  #####  ..#..  ...#.  ##...
.....  #...#  #...#  #....  #...#  #....  #....  #...#  #...#  ..#..  ...#.  #.#..
.....  #...#  #...#  #....  #...#  #....  #....  #...#  #...#  ..#..  ...#.  #..#.
.....  #...#  #...#  #...#  #..#.  #....  #....  #...#  #...#  ..#..  #..#.  #...#
.....  #...#  ####.  .###.  ###..  #####  #....  .####  #...#  .###.  .##..  #...#
.....  .....  .....  .....  .....  .....  .....  .....  .....  .....  .....  .....
.....  .....  .....  .....  .....  .....  .....  .....  .....  .....  .....  .....

[L]--  [M]--  [N]--  [O]--  [P]--  [Q]--  [R]--  [S]--  [T]--  [U]--  [V]--  [W]--
#....  #...#  #...#  .###.  ####.  .###.  ####.  .###.  #####  #...#  #...#  #...#
#....  ##.##  ##..#  #...#  #...#  #...#  #...#  #...#  ..#..  #...#  #...#  #...#
#....  #.#.#  ##..#  #...#  #...#  #...#  #...#  #....  ..#..  #...#  #...#  #...#
#....  #.#.#  #.#.#  #...#  #...#  #...#  #...#  #....  ..#..  #...#  #...#  #...#
#....  #...#  #.#.#  #...#  ####.  #...#  ####.  .###.  ..#..  #...#  #...#  #.#.#
#....  #...#  #.#.#  #...#  #....  #...#  #.#..  ....#  ..#..  #...#  .#.#.  #.#.#
#....  #...#  #..##  #...#  #....  #.#.#  #..#.  ....#  ..#..  #...#  .#.#.  #.#.#
#....  #...#  #..##  #...#  #....  #..#.  #...#  #...#  ..#..  #...#  .#.#.  ##.##
#####  #...#  #...#  .###.  #....  .##.#  #...#  .###.  ..#..  .###.  ..#..  #...#
.....  .....  .....  .....  .....  .....  .....  .....  .....  .....  .....  .....
.....  .....  .....  .....  .....  .....  .....  .....  .....  .....  .....  .....

[X]--  [Y]--  [Z]--  [a]--  [b]--  [c]--  [d]--  [e]--  [f]--  [g]--  [h]--  [i]--
#...#  #...#  #####  .....  #....  .....  ....#  .....  ..##.  .....  #....  .....
#...#  #...#  ....#  .....  #....  .....  ....#  .....  .#..#  .....  #....  ..#..
.#.#.  .#.#.  ...#.  .....  #....  .....  ....#  .....  .#...  .....  #....  .....
.#.#.  .#.#.  ...#.  .###.  #.##.  .###.  .##.#  .###.  .#...  .####  #.##.  .##..
..#..  ..#..  ..#..  ....#  ##..#  #...#  #..##  #...#  ####.  #...#  ##..#  ..#..
.#.#.  ..#..  .#...  .####  #...#  #....  #...#  #####  .#...  #...#  #...#  ..#..
.#.#.  ..#..  .#...  #...#  #...#  #....  #...#  #....  .#...  #...#  #...#  ..#..
#...#  ..#..  #....  #..##  ##..#  #...#  #..##  #...#  .#...  #..##  #...#  ..#..
#...#  ..#..  #####  .##.#  #.##.  .###.  .##.#  .###.  .#...  .##.#  #...#  .###.
.....  .....  .....  .....  .....  .....  .....  .....  .....  ....#  .....  .....
.....  .....  .....  .....  .....  .....  .....  .....  .....  .###.  .....  .....

[j]--  [k]--  [l]--  [m]--  [n]--  [o]--  [p]--  [q]--  [r]--  [s]--  [t]--  [u]--
.....  #....  .##..  .....  .....  .....  .....  .....  .....  .....  .....  .....
...#.  #....  ..#..  .....  .....  .....  .....  .....  .....  .....  .#...  .....
.....  #....  ..#..  .....  .....  .....  .....  .....  .....  .....  .#...  .....
..##.  #..#.  ..#..  ##.#.  #.##.  .###.  #.##.  .##.#  #.##.  .###.  ####.  #...#
...#.  #.#..  ..#..  #.#.#  ##..#  #...#  ##..#  #..##  ##..#  #...#  .#...  #...#
...#.  ##...  ..#..  #.#.#  #...#  #...#  #...#  #...#  #....  .##..  .#...  #...#
...#.  #.#..  ..#..  #.#.#  #...#  #...#  #...#  #...#  #....  ...#.  .#...  #...#
...#.  #..#.  ..#..  #.#.#  #...#  #...#  ##..#  #..##  #....  #...#  .#..#  #..##
...#.  #...#  .###.  #.#.#  #...#  .###.  #.##.  .##.#  #....  .###.  ..##.  .##.#
#..#.  .....  .....  .....  .....  .....  #....  ....#  .....  .....  .....  .....
.##..  .....  .....  .....  .....  .....  #....  ....#  .....  .....  .....  .....

[v]--  [w]--  [x]--  [y]--  [z]--  [0]--  [1]--  [2]--  [3]--  [4]--  [5]--  [6]--
.....  .....  .....  .....  .....  .###.  ..#..  .###.  .###.  ...#.  #####  .###.
.....  .....  .....  .....  .....  #...#  .##..  #...#  #...#  ..##.  #....  #...#
.....  .....  .....  .....  .....  #..##  #.#..  ....#  ....#  .#.#.  #....  #....
#...#  #...#  #...#  #...#  #####  #.#.#  ..#..  ....#  ....#  #..#.  ####.  #....
#...#  #...#  .#.#.  #...#  ...#.  #.#.#  ..#..  ...#.  ..##.  #..#.  ....#  ####.
#...#  #.#.#  ..#..  #...#  ..#..  #.#.#  ..#..  ..#..  ....#  #####  ....#  #...#
.#.#.  #.#.#  ..#..  #...#  .#...  ##..#  ..#..  .#...  ....#  ...#.  ....#  #...#
.#.#.  #.#.#  .#.#.  #..##  #....  #...#  ..#..  #....  #...#  ...#.  #...#  #...#
..#..  .#.#.  #...#  .##.#  #####  .###.  #####  #####  .###.  ...#.  .###.  .###.
.....  .....  .....  ....#  .....  .....  .....  .....  .....  .....  .....  .....
.....  .....  .....  .###.  .....  .....  .....  .....  .....  .....  .....  .....

[7]--  [8]--  [9]--  [.]--  [,]--  [!]--  [?]--  [']--  ["]--  [-]--  [~]--  […]--
#####  .###.  .###.  .....  .....  ..#..  .###.  ..#..  .#.#.  .....  .....  .....
....#  #...#  #...#  .....  .....  ..#..  #...#  ..#..  .#.#.  .....  .....  .....
....#  #...#  #...#  .....  .....  ..#..  ....#  .#...  .#.#.  .....  .....  .....
...#.  #...#  #...#  .....  .....  ..#..  ...#.  .....  .....  .....  .....  .....
...#.  .###.  .####  .....  .....  ..#..  ..#..  .....  .....  .....  .#...  .....
..#..  #...#  ....#  .....  .....  ..#..  ..#..  .....  .....  .###.  #.#.#  .....
..#..  #...#  ....#  .....  .....  .....  .....  .....  .....  .....  ...#.  .....
..#..  #...#  #...#  .##..  .##..  ..#..  ..#..  .....  .....  .....  .....  .....
..#..  .###.  .###.  .##..  .##..  ..#..  ..#..  .....  .....  .....  .....  #.#.#
.....  .....  .....  .....  ..#..  .....  .....  .....  .....  .....  .....  .....
.....  .....  .....  .....  .#...  .....  .....  .....  .....  .....  .....  .....
"""


def _parse(art):
    glyphs = {}
    lines = art.strip("\n").split("\n")
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        heads = lines[i].split("  ")
        rows = [l.split("  ") for l in lines[i + 1:i + 1 + H]]
        for k, h in enumerate(heads):
            ch = " " if h.startswith("[sp]") else h[1]
            glyphs[ch] = [r[k] for r in rows]
        i += 1 + H
    return glyphs


GLYPHS = _parse(ART)
assert len(CHARSET) == len(LEAD) == 72 and set(GLYPHS) == set(CHARSET)
for _c, _g in GLYPHS.items():
    assert len(_g) == H and all(len(r) == W and set(r) <= set(".#") for r in _g), _c
INDEX = {c: i for i, c in enumerate(CHARSET)}


def rows(ch):
    """H row values, W bits each, top bit = leftmost pixel."""
    return [int(r.replace(".", "0").replace("#", "1"), 2) for r in GLYPHS[ch]]


def font_blob():
    """72 glyphs x W*H bits, packed MSB first."""
    acc = 0
    for ch in CHARSET:
        for r in rows(ch):
            acc = (acc << W) | r
    nbits = len(CHARSET) * W * H
    n = (nbits + 7) // 8
    return (acc << (8 * n - nbits)).to_bytes(n, "big")


def pair_code(left, right):
    """Two characters -> the 2 bytes of their cell."""
    return bytes((LEAD[INDEX[left]], TRAIL0 + INDEX[right]))


def decode_pair(code):
    """16-bit code -> (left, right), or None if it isn't a pair code."""
    lead, trail = code >> 8, code & 0xFF
    if lead not in LEAD or not 0 <= trail - TRAIL0 < len(CHARSET):
        return None
    return CHARSET[LEAD.index(lead)], CHARSET[trail - TRAIL0]


def compose(code):
    """Reference model of the patched lookup: the 30-byte, 15-row cell
    bitmap (row = 2 bytes, byte 0 = pixels 0-7 MSB first, byte 1 = 8-15)."""
    left, right = decode_pair(code)
    out = bytearray(30)
    for r, (a, b) in enumerate(zip(rows(left), rows(right))):
        row = (a << (16 - W - LEFT_X)) | (b << (16 - W - RIGHT_X))
        out[2 * (CELL_TOP + r)] = row >> 8
        out[2 * (CELL_TOP + r) + 1] = row & 0xFF
    return bytes(out)


def is_supported(ch):
    return ch in INDEX


def wide(ch):
    """A character the font doesn't have, as one full-width Shift-JIS cell
    (ASCII punctuation such as : / ( ) becomes its full-width form)."""
    if "!" <= ch <= "~":
        ch = chr(ord(ch) + 0xFEE0)
    b = ch.encode("cp932")
    if len(b) != 2:
        raise UnicodeEncodeError("cp932", ch, 0, 1, "not a full-width character")
    return b
