"""lz2 compressor (the inverse of compression.lz2, the game's decoder at
SLPM_863.55 0x8001A830). Optimal parsing over the format's tokens; control
bits are read LSB first from flag bytes that sit in the stream where the
decoder needs the next bit:

  literal      0, byte                                   (9 bits)
  long copy    1 0, u16 BE w = off << 4 | (n - 2)       n 3-17, off 1-4095 (18 bits)
               1 0, u16 BE w = off << 4, byte n - 1     n 1-256           (26 bits)
  short copy   1 1, b1, b0, byte off (0 = 256)          n = 2 + 2*b1 + b0 (2-5), off 1-256 (12 bits)
  end          1 0, u16 0

Copies come from the output so far (no preset window) and may overlap.
"""
import collections


def compress(data):
    n = len(data)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    choice = [None] * (n + 1)
    cost[n] = 0
    heads = collections.defaultdict(list)
    for i in range(n - 1):
        heads[data[i:i + 2]].append(i)

    for j in range(n - 1, -1, -1):
        best, bc = 9 + cost[j + 1], ("lit",)
        if j + 2 <= n:
            seen_len = 0
            for s in reversed(heads.get(data[j:j + 2], ())):
                if s >= j:
                    continue
                off = j - s
                if off > 4095:
                    break
                L = 0
                lim = min(256, n - j)
                while L < lim and data[s + L] == data[j + L]:
                    L += 1
                if L <= seen_len and off > 256:
                    continue
                seen_len = max(seen_len, L)
                done = L == lim
                for l in range(2, L + 1):
                    if l <= 5 and off <= 256:
                        c = 12
                    elif 3 <= l <= 17:
                        c = 18
                    else:
                        c = 26
                    c += cost[j + l]
                    if c < best:
                        best, bc = c, ("cp", l, off)
                if done and off <= 256:
                    break
        cost[j], choice[j] = best, bc

    out = bytearray()
    state = {"pos": None, "used": 8}

    def bit(b):
        if state["used"] == 8:
            state["pos"] = len(out)
            out.append(0)
            state["used"] = 0
        out[state["pos"]] |= b << state["used"]
        state["used"] += 1

    j = 0
    while j < n:
        c = choice[j]
        if c[0] == "lit":
            bit(0)
            out.append(data[j])
            j += 1
            continue
        _, l, off = c
        if l <= 5 and off <= 256:
            bit(1); bit(1)
            k = l - 2
            bit(k >> 1); bit(k & 1)
            out.append(off & 0xFF)
        elif 3 <= l <= 17:
            bit(1); bit(0)
            w = off << 4 | (l - 2)
            out += bytes((w >> 8, w & 0xFF))
        else:
            bit(1); bit(0)
            w = off << 4
            out += bytes((w >> 8, w & 0xFF, l - 1))
        j += l
    bit(1); bit(0)
    out += b"\0\0"
    return bytes(out)
