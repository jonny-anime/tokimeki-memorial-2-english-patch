"""Find every scene-script block on a disc and work out where it lives.

Each block is a `38 35 00 00` script (docs/game-internals.md section 6).
Blocks live in one of four kinds of container (docs/game-internals.md section 10):

  file    the block starts a sector and is followed only by zero padding to
          the end of its last sector (the main game, Discs 2-5). The game
          reads whole sectors, so the block can grow up to that sector end.
  bundle  the block is a whole part of a bundle (`u32 count, u32 sizes[]`,
          parts back to back; the childhood scenes). It can grow into the
          stale bytes after the bundle in its last sector; later parts move
          up and the size table is rewritten (verified, experiments 2b, 4).
  pack    one of several blocks in a script pack (`80 35`, u16 count, u32
          offsets[count]) that is itself a bundle part (YGROUP00). Grows
          like a bundle part; the pack's offset table is rewritten.
  packed  anything else: packs in unknown containers (YGROUP01-04), blocks
          inside code modules or call lists (G_TELG, G_DATE ...).
          How the game finds them isn't known yet, so they must keep their
          size (shorter text is padded back).
"""
import hashlib
import struct

import extract_scripts as X
import script

SECTOR = 2048


class Block:
    def __init__(self, sid, off, blk):
        self.sid = sid
        self.off = off                 # byte offset in the disc's user data
        self.end = blk["end"]          # end of the reachable bytecode, relative to off
        self.messages = blk["messages"]
        self.kind = "packed"
        self.size = self.end           # bytes the block occupies (incl. trailing bytes)
        self.room = 0                  # bytes it may grow by
        self.bundle = None             # (sector, part index) for bundles and packs
        self.pack = None               # index inside the pack
        self.sha1 = None

    @property
    def key(self):
        return "%s-%s" % (self.sid, self.sha1[:8])

    def text_bytes(self):
        """Bytes of display text (lines and speaker labels), without NULs."""
        n = 0
        for m in self.messages:
            if m["speaker"]:
                n += _string_len(m["speaker"])
            n += sum(_string_len(l["tokens"]) for l in m["lines"])
        return n


def _string_len(tokens):
    n = 0
    for kind, v in tokens:
        n += 2 * len(v) if kind == "text" else (2 if v.startswith("num") else 1)
    return n


def read_bundle(data, base):
    """(n, sizes, part start offsets) of a bundle at byte offset base, or None."""
    if base < 0 or base + 8 > len(data):
        return None
    n = struct.unpack_from("<I", data, base)[0]
    if not 1 <= n <= 64:
        return None
    sizes = struct.unpack_from("<%dI" % n, data, base + 4)
    if any(x == 0 or x > 0x200000 for x in sizes):
        return None
    starts, p = [], base + 4 + 4 * n
    for x in sizes:
        starts.append(p); p += x
    return n, sizes, starts


def read_pack(data, p, size):
    """Offsets of the blocks in a script pack (`80 35`, u16 count, u32
    offsets[count] relative to the pack) occupying data[p:p+size], or None."""
    if data[p:p + 2] != b"\x80\x35":
        return None
    n = struct.unpack_from("<H", data, p + 2)[0]
    if not 1 <= n <= 255 or 4 + 4 * n > size:
        return None
    offs = struct.unpack_from("<%dI" % n, data, p + 4)
    if list(offs) != sorted(offs) or offs[0] < 4 + 4 * n or offs[-1] >= size:
        return None
    return list(offs)


def _classify(data, b):
    """Set b.kind / b.size / b.room / b.bundle / b.pack for a block."""
    s0 = b.off - b.off % SECTOR
    for back in range(96):
        base = s0 - back * SECTOR
        bund = read_bundle(data, base)
        if not bund:
            continue
        n, sizes, starts = bund
        for k, (p, x) in enumerate(zip(starts, sizes)):
            if not p <= b.off < p + x:
                continue
            total = 4 + 4 * n + sum(sizes)
            if p == b.off and b.end <= x and not data[b.off + b.end:p + x].strip(b"\0\xff"):
                b.kind, b.bundle, b.size = "bundle", (base // SECTOR, k), x
                b.room = -total % SECTOR
                return
            offs = read_pack(data, p, x)
            if offs and b.off - p in offs:
                i = offs.index(b.off - p)
                nxt = offs[i + 1] if i + 1 < len(offs) else x
                b.kind, b.bundle, b.pack = "pack", (base // SECTOR, k), i
                b.size = nxt - (b.off - p)
                b.room = -total % SECTOR
            return
    if b.off % SECTOR == 0:
        e = b.off + b.end
        se = -(-e // SECTOR) * SECTOR
        tail = data[e:se].rstrip(b"\0")
        if len(tail) <= 4:                          # FF end markers, then zeros
            b.kind, b.size = "file", b.end + len(tail)
            b.room = se - e - len(tail)


def scan(data):
    """All script blocks of a disc's user data, classified."""
    out = []
    for m in X.HDR.finditer(data):
        off = m.start()
        code_off, nsec = struct.unpack("<HH", m.group(1) + m.group(2))
        if not (0x20 <= code_off < 0x8000 and nsec < 16):
            continue
        sid = m.group(3).rstrip(b"\0").decode("ascii")
        try:
            blk = script.messages(data, off)
        except script.ScriptError:
            continue
        b = Block(sid, off, blk)
        _classify(data, b)
        b.sha1 = hashlib.sha1(data[off:off + b.end]).hexdigest()
        out.append(b)
    return out
