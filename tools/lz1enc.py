"""lz1 compressor (the inverse of compression.lz1, the game's decoder at
SLPM_863.55 0x8002E950). Optimal parsing over the format's four tokens:

  literal       flag 0, 1 byte                       (9 bits)
  short copy    flag 1, 0x80-0xBF: 2-5 bytes, 1-15 back   (9 bits)
  long copy     flag 1, 0x00-0x7F + byte: 3-34 bytes from a ring position (17 bits)
  literal run   flag 1, 0xC0-0xFF: 8-71 literal bytes      (9 + 8n bits)

The ring buffer is 1 KiB, zero-filled, output position j lands at ring
index (0x3DE + j) & 0x3FF, so a long copy may reach back up to 1024 bytes
(and overlap forwards). Output: u24 LE size + 1 zero byte, then the stream.
"""
import collections

RING0 = 0x3DE


def compress(data):
    n = len(data)
    # candidate match lengths: for each position, best length per distance class
    INF = 1 << 60
    cost = [INF] * (n + 1)
    choice = [None] * (n + 1)
    cost[n] = 0
    # hash of 3-byte prefixes -> positions
    heads = collections.defaultdict(list)
    for i in range(n - 2):
        heads[data[i:i + 3]].append(i)

    def matches(j):
        """[(length, src)] best long-copy length per source, and short ones."""
        out = []
        if j + 2 <= n:
            for back in range(1, 16):
                s = j - back
                if s < 0:
                    break
                L = 0
                while L < 5 and j + L < n and data[s + L] == data[j + L]:
                    L += 1
                if L >= 2:
                    out.append(("s", L, back))
        if j + 3 <= n:
            for s in reversed(heads.get(data[j:j + 3], ())):
                if s >= j:
                    continue
                if j - s > 1024:
                    break
                L = 0
                while L < 34 and j + L < n and data[s + L] == data[j + L]:
                    L += 1
                if L >= 3:
                    out.append(("l", L, s))
        return out

    # positions list per prefix must be ascending for the reversed scan
    for k in heads:
        heads[k].sort()
    for j in range(n - 1, -1, -1):
        best, bc = 9 + cost[j + 1], ("lit",)
        for kind, L, ref in matches(j):
            for l in range(2 if kind == "s" else 3, L + 1):
                c = (9 if kind == "s" else 17) + cost[j + l]
                if c < best:
                    best, bc = c, (kind, l, ref)
        for r in range(8, min(71, n - j) + 1):
            c = 9 + 8 * r + cost[j + r]
            if c < best:
                best, bc = c, ("run", r)
        cost[j], choice[j] = best, bc
    # emit
    out = bytearray()
    flags_pos, nbits, flags = None, 8, 0
    j = 0

    def token(flag, payload):
        nonlocal flags_pos, nbits, flags
        if nbits == 8:
            if flags_pos is not None:
                out[flags_pos] = flags
            flags_pos = len(out)
            out.append(0)
            nbits, flags = 0, 0
        flags |= flag << nbits
        nbits += 1
        out.extend(payload)

    while j < n:
        c = choice[j]
        if c[0] == "lit":
            token(0, data[j:j + 1]); j += 1
        elif c[0] == "s":
            _, l, back = c
            token(1, bytes((0x80 | ((l - 2) << 4) | back,))); j += l
        elif c[0] == "l":
            _, l, s = c
            off = (RING0 + s) & 0x3FF
            token(1, bytes((((l - 3) << 2) | (off >> 8), off & 0xFF))); j += l
        else:
            _, r = c
            token(1, bytes((0xC0 | (r - 8),)) + data[j:j + r]); j += r
    if flags_pos is not None:
        out[flags_pos] = flags
    size = len(out)
    return bytes((size & 0xFF, size >> 8 & 0xFF, size >> 16 & 0xFF, 0)) + bytes(out)
