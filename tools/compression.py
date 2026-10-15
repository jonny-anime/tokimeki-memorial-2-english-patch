"""Tokimeki Memorial 2 (PS1) decompressors, reimplemented from the game's own code.

Both were checked against the original: lz1 by running the game's routine
(SLPM_863.55 @ 0x8002e950) in a MIPS emulator on the same input; lz2 by
decoding CDPACK00.BIN type-0x204 packets to exactly 16 KiB each.
Pure standard-library Python. See docs/game-internals.md.
"""

def lz1(src, pos=0, limit=4 << 20):
    """Konami-style LZ, SLPM_863.55 @ 0x8002e950.
    Header: u24 LE compressed size + 1 unused byte. 1 KiB ring buffer,
    zero-filled, write position starts at 0x3DE.
    Returns (data, bytes_consumed)."""
    size = src[pos] | src[pos + 1] << 8 | src[pos + 2] << 16
    p = pos + 4
    end = p + size
    if end > len(src):
        raise ValueError("compressed size runs past end of input")
    ring = bytearray(0x400)
    r = 0x3DE
    out = bytearray()
    flags = 0

    def put(c):
        nonlocal r
        out.append(c)
        ring[r] = c
        r = (r + 1) & 0x3FF

    while p < end:
        flags >>= 1
        if not flags & 0x100:            # 8 flag bits per byte, LSB first
            flags = src[p] | 0xFF00
            p += 1
            if p >= end:
                break
        if not flags & 1:                # literal
            put(src[p]); p += 1
            continue
        b = src[p]; p += 1
        if b < 0x80:                     # long copy from absolute ring position
            off = ((b & 3) << 8) | src[p]; p += 1
            for i in range((b >> 2) + 3):
                put(ring[(off + i) & 0x3FF])
        elif b < 0xC0:                   # short copy, 0-15 back
            back = b & 0xF
            for _ in range(((b >> 4) & 3) + 2):
                put(ring[(r - back) & 0x3FF])
        else:                            # literal run
            for _ in range((b & 0x3F) + 8):
                put(src[p]); p += 1
        if len(out) > limit:
            raise ValueError("output too large")
    return bytes(out), p - pos


def lz2(src, pos=0, limit=4 << 20):
    """Second LZ variant, SLPM_863.55 @ 0x8001a830. No header; the stream
    ends with a long reference of 0x0000. Returns (data, bytes_consumed)."""
    p = pos
    out = bytearray()
    bits = 0
    cnt = 1

    def bit():
        nonlocal bits, cnt, p
        cnt -= 1
        if cnt == 0:
            bits = src[p]; p += 1; cnt = 8
        b = bits & 1
        bits >>= 1
        return b

    while True:
        if not bit():                    # literal
            out.append(src[p]); p += 1
            continue
        if not bit():                    # long: 12-bit offset, 4-bit length
            w = (src[p] << 8) | src[p + 1]; p += 2
            if w == 0:
                break
            n = w & 0xF
            if n == 0:
                n = src[p] + 1; p += 1
            else:
                n += 2
            off = w >> 4
        else:                            # short: 2-5 bytes, 8-bit offset
            n = bit() << 1
            n = n + 2 + bit()
            off = src[p] or 0x100; p += 1
        if off > len(out):
            raise ValueError("reference before start of output")
        s = len(out) - off
        for i in range(n):
            out.append(out[s + i])
        if len(out) > limit:
            raise ValueError("output too large")
    return bytes(out), p - pos


def deobfuscate(data):
    """Code modules in CDPACK00.BIN are stored with every byte +0x64; the
    loader adds 0x9C (SLPM_863.55 @ 0x80025204, 0x800224e0)."""
    return data.translate(bytes(((i - 0x64) & 0xFF) for i in range(256)))
