"""Make xdelta patches (VCDIFF, RFC 3284) from your original and English discs.

    py tools/make_xdelta.py <original discs> <English discs> [-o patches]

Both arguments are folders (or .cue/.bin files), as for patch.py: discs are
matched by disc number. For each disc it writes

    patches/Tokimeki Memorial 2 (Japan) (Disc N) (Rev 1) [English].xdelta

and patches/checksums.txt (CRC32, MD5 and SHA-1 of every original and English
image), then checks each patch by applying it to the original and comparing
the result with the English image byte for byte.

The patches are plain VCDIFF with an Adler-32 checksum per window (the
xdelta3 extension), so xdelta3, Delta Patcher, xdeltaUI and Rom Patcher JS
can apply them; applied to the wrong image, xdelta3 stops with a checksum
error. Only the changed bytes are stored (uncompressed; a .zip of the patches
is much smaller). Needs numpy (requirements.txt).
"""
import hashlib
import os
import sys
import zlib

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

MAGIC = b"\xd6\xc3\xc4\x00"
VCD_SOURCE, VCD_ADLER32 = 0x01, 0x04
WINDOW = 4 << 20          # target bytes per window (xdelta3 decodes up to 16 MiB)
GAP = 16                  # equal runs shorter than this are stored, not copied
ADD0, COPY0 = 1, 19       # default code table: ADD / COPY mode 0 with the size given separately


def varint(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def read_varint(b, p):
    n = 0
    while True:
        c = b[p]
        p += 1
        n = (n << 7) | (c & 0x7F)
        if not c & 0x80:
            return n, p


def segments(src, tgt, t, end):
    """[(copy?, start, length)] covering tgt[t:end]; copies come from src at the same offset."""
    over = max(0, min(end, len(src)) - t)
    segs = []
    if over:
        diff = np.flatnonzero(src[t:t + over] != tgt[t:t + over])
        pos = 0
        if len(diff):
            # runs of differing bytes, joined across short equal gaps
            breaks = np.flatnonzero(np.diff(diff) > GAP)
            starts = np.concatenate(([diff[0]], diff[breaks + 1]))
            ends = np.concatenate((diff[breaks], [diff[-1]])) + 1
            for a, b in zip(starts.tolist(), ends.tolist()):
                if a > pos:
                    segs.append((True, pos, a - pos))
                segs.append((False, a, b - a))
                pos = b
        if pos < over:
            segs.append((True, pos, over - pos))
    if t + over < end:
        segs.append((False, over, end - t - over))
    return segs, over


def encode(src, tgt, out):
    """Write the VCDIFF delta from src to tgt (numpy uint8 arrays) to file out."""
    out.write(MAGIC + b"\x00")
    for t in range(0, len(tgt), WINDOW):
        end = min(t + WINDOW, len(tgt))
        segs, over = segments(src, tgt, t, end)
        data, inst, addr = bytearray(), bytearray(), bytearray()
        copies = False
        for copy, a, n in segs:
            if copy:
                copies = True
                inst += bytes([COPY0]) + varint(n)
                addr += varint(a)            # mode 0 (VCD_SELF): offset in the source segment
            else:
                inst += bytes([ADD0]) + varint(n)
                data += tgt[t + a:t + a + n].tobytes()
        body = (varint(end - t) + b"\x00" + varint(len(data)) + varint(len(inst)) + varint(len(addr))
                + (zlib.adler32(tgt[t:end].tobytes()) & 0xFFFFFFFF).to_bytes(4, "big")
                + bytes(data) + bytes(inst) + bytes(addr))
        if copies:
            head = bytes([VCD_SOURCE | VCD_ADLER32]) + varint(over) + varint(t)
        else:
            head = bytes([VCD_ADLER32])
        out.write(head + varint(len(body)) + body)


def decode(src, patch, out):
    """Apply a patch made by encode() (only the instructions it writes). Raises on any mismatch."""
    p = patch
    assert p[:4] == MAGIC and p[4] == 0, "not a plain VCDIFF file"
    i = 5
    while i < len(p):
        ind = p[i]
        i += 1
        spos = ssize = 0
        if ind & VCD_SOURCE:
            ssize, i = read_varint(p, i)
            spos, i = read_varint(p, i)
        blen, i = read_varint(p, i)
        j = i
        tsize, j = read_varint(p, j)
        assert p[j] == 0
        j += 1
        dlen, j = read_varint(p, j)
        ilen, j = read_varint(p, j)
        alen, j = read_varint(p, j)
        ck = int.from_bytes(p[j:j + 4], "big") if ind & VCD_ADLER32 else None
        j += 4 if ind & VCD_ADLER32 else 0
        data, inst, addr = j, j + dlen, j + dlen + ilen
        dend, iend = inst, addr
        win = bytearray()
        while inst < iend:
            code = p[inst]
            n, inst = read_varint(p, inst + 1)
            if code == ADD0:
                win += p[data:data + n]
                data += n
            elif code == COPY0:
                a, addr = read_varint(p, addr)
                assert a + n <= ssize
                chunk = src[spos + a:spos + a + n]
                win += chunk.tobytes() if hasattr(chunk, "tobytes") else chunk
            else:
                raise ValueError("instruction %d not written by this tool" % code)
        assert data == dend and len(win) == tsize, "bad window"
        if ck is not None and zlib.adler32(bytes(win)) & 0xFFFFFFFF != ck:
            raise ValueError("checksum mismatch: wrong original image?")
        out.write(win)
        i += blen


def sums(path):
    c, m, s = 0, hashlib.md5(), hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            c = zlib.crc32(b, c)
            m.update(b)
            s.update(b)
    return "%08X" % (c & 0xFFFFFFFF), m.hexdigest(), s.hexdigest()


class Compare:
    """A file-like sink that compares what is written with a file."""
    def __init__(self, path):
        self.f = open(path, "rb")
        self.ok = True

    def write(self, b):
        if self.ok and self.f.read(len(b)) != bytes(b):
            self.ok = False

    def done(self):
        ok = self.ok and self.f.read(1) == b""
        self.f.close()
        return ok


def main(argv):
    import patch as P
    out, args = os.path.join(ROOT, "patches"), []
    i = 0
    while i < len(argv):
        if argv[i] == "-o":
            out = argv[i + 1]; i += 2
        else:
            args.append(argv[i]); i += 1
    if len(args) != 2:
        print(__doc__)
        return 2
    orig = {d: b for d, b, _ in P.find_discs([args[0]])}
    eng = {d: b for d, b, _ in P.find_discs([args[1]])}
    pairs = sorted(set(orig) & set(eng))
    if not pairs:
        print("no matching discs in %s and %s" % (args[0], args[1]))
        return 1
    os.makedirs(out, exist_ok=True)
    ck = os.path.join(out, "checksums.txt")
    rows = {}                                  # (disc, image) -> line; kept for discs not done now
    if os.path.exists(ck):
        for line in open(ck, encoding="utf-8"):
            f = line.split()
            if len(f) == 5 and f[0].isdigit():
                rows[(int(f[0]), f[1])] = line.rstrip("\n")
    failed = []
    for d in pairs:
        o, e = orig[d], eng[d]
        name = os.path.splitext(os.path.basename(o))[0] + " [English].xdelta"
        dst = os.path.join(out, name)
        print("Disc %d: %s" % (d, name))
        src = np.memmap(o, dtype=np.uint8, mode="r")
        tgt = np.memmap(e, dtype=np.uint8, mode="r")
        with open(dst, "wb") as f:
            encode(src, tgt, f)
        cmp = Compare(e)
        with open(dst, "rb") as f:
            decode(src, f.read(), cmp)
        ok = cmp.done()
        print("  %.1f MB, %s" % (os.path.getsize(dst) / 1e6, "checked: rebuilds the English image exactly"
                                 if ok else "CHECK FAILED"))
        if not ok:
            failed.append(d)
        for label, path in (("original", o), ("English", e)):
            rows[(d, label)] = "%-6d %-9s %s %s %s" % ((d, label) + sums(path))
        del src, tgt
    lines = ["Tokimeki Memorial 2 English patch: the images the patches apply to and produce.",
             "Originals: Tokimeki Memorial 2 (Japan) (Rev 1), one .bin per disc (MODE2/2352).",
             "", "%-6s %-9s %-8s %-32s %s" % ("disc", "image", "CRC32", "MD5", "SHA-1")]
    lines += [rows[k] for k in sorted(rows, key=lambda k: (k[0], k[1] != "original"))]
    with open(ck, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("\nPatches and checksums.txt in %s" % out)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
