"""Tokimeki Memorial 2 script text: Shift-JIS with each byte's nibbles swapped.

Verified on Disc 1 with two DuckStation save states (RAM) and on the disc
itself; see docs/game-internals.md section 5. Control-code meanings are
partly hypotheses and marked as such there.
"""
SWAP = bytes(((i >> 4) | ((i & 15) << 4)) for i in range(256))

def unswap(data: bytes) -> bytes:
    """Script bytes -> plain Shift-JIS bytes (the transform is its own inverse)."""
    return data.translate(SWAP)

swap = unswap

def _is_lead(c):
    return 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEA

def render(data: bytes) -> str:
    """Debug view: decoded characters, other bytes as {xx} (raw, un-swapped)."""
    s = unswap(data)
    out, p = [], 0
    while p < len(s):
        if _is_lead(s[p]) and p + 1 < len(s):
            try:
                out.append(s[p:p + 2].decode("cp932")); p += 2; continue
            except UnicodeDecodeError:
                pass
        out.append("{%02x}" % data[p]); p += 1
    return "".join(out)
