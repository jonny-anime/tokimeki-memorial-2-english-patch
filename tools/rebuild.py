"""Rebuild a script block with replaced strings (lines may change length).

Japanese text goes through encode(), English through encode_en().

Jumps (opcodes 30/31, s16 relative to the end of the instruction) are
re-targeted. Header values are checked not to point past the first edit.
"""
import re, struct, bisect
import script
import font_en

CODES = {"name1": 0x1D, "name2": 0x1E, "name3": 0x1F}


def _code(tok):
    """A {code} of the text syntax (tools/script.py read_string) -> raw string
    bytes (before the nibble swap)."""
    name = tok[1:-1]
    if name in CODES:
        return bytes((CODES[name],))
    if name == "nobreak":
        return b"\x0c"
    m = re.fullmatch(r"you:(1[0-9A-C])", name)
    if m:
        return bytes((int(m.group(1), 16),))
    m = re.fullmatch(r"char:(2[0-9A-D])", name)
    if m:
        return bytes((int(m.group(1), 16),))
    m = re.fullmatch(r"char(2[EF]):([0-9A-F]{2})", name)
    if m:
        return bytes((int(m.group(1), 16), int(m.group(2), 16)))
    m = re.fullmatch(r"num([0-9A-F]):([0-9A-F]{2})", name)
    if m:
        return bytes((0x30 | int(m.group(1), 16), int(m.group(2), 16)))
    m = re.fullmatch(r"c([0-9A-F]{2})", name)
    if m:
        return bytes((int(m.group(1), 16),))
    raise ValueError("unknown code " + tok)


def encode(text):
    """'{name2}ちゃん、' -> raw nibble-swapped bytes with terminating 00."""
    out = bytearray()
    for tok in re.split(r"(\{[^}]*\})", text):
        if not tok:
            continue
        out += _code(tok) if tok.startswith("{") else tok.encode("cp932")
    out.append(0)
    return bytes(out).translate(script.SWAP)


def encode_en(text):
    """English text -> raw nibble-swapped bytes with terminating 00.

    Characters of font_en.CHARSET go two to a cell as letter-pair codes (a
    lone letter before a code, a full-width character or the end is paired
    with a space). {codes} as in encode(). Any other character becomes a
    full-width Shift-JIS cell (e.g. ♪ or a Japanese name)."""
    out, pend = bytearray(), []

    def flush():
        if pend:
            out.extend(font_en.pair_code(pend[0], pend[1] if len(pend) > 1 else " "))
            pend.clear()

    for tok in re.split(r"(\{[^}]*\})", text):
        if not tok:
            continue
        if tok.startswith("{"):
            flush()
            out += _code(tok)
            continue
        for ch in tok:
            if font_en.is_supported(ch):
                pend.append(ch)
                if len(pend) == 2:
                    flush()
            else:
                flush()
                out += font_en.wide(ch)
    flush()
    out.append(0)
    return bytes(out).translate(script.SWAP)


def rebuild(block, edits, english=False):
    """block: bytes of one script block (starting at its 85 magic).
    edits: {line_offset (of the 10/11/18 opcode): new_text}.
    english: encode the new texts with encode_en (letter pairs).
    Returns new bytes."""
    blk = script.parse_block(block, 0)
    code = script.walk(block, blk["code"], lo=0, hi=len(block))
    spans = []                                   # (start, old_end, new_bytes)
    for at, text in sorted(edits.items()):
        op, info, nxt = code[at]
        assert op in (0x10, 0x11, 0x18), "edit target is not a string op"
        spans.append((at + 1, nxt, (encode_en if english else encode)(text)))
    first = spans[0][0]
    # offset fields: bytecode offset (+4), section table (+8, 8 x u16), +0x22 (3 x u16)
    hdr = struct.unpack_from("<H", block, 4) + struct.unpack_from("<8H", block, 8) + struct.unpack_from("<3H", block, 0x22)
    assert all(v <= first for v in hdr), "header offset %s points past an edit" % [hex(v) for v in hdr]

    starts = [s for s, e, n in spans]
    deltas, acc = [], 0
    for s, e, n in spans:
        acc += len(n) - (e - s); deltas.append(acc)

    def remap(x):
        k = bisect.bisect_right(starts, x - 1) - 1   # edits starting before x
        if k >= 0:
            s, e, n = spans[k]
            assert not (s < x < e), "jump into an edited string"
        return x + (deltas[k] if k >= 0 else 0)

    out, pos = bytearray(), 0
    for s, e, n in spans:
        out += block[pos:s] + n; pos = e
    out += block[pos:]
    for at, (op, info, nxt) in code.items():
        if op in (0x30, 0x31):
            tgt = nxt + struct.unpack_from("<h", block, nxt - 2)[0]
            nn, nt = remap(nxt), remap(tgt)
            struct.pack_into("<h", out, nn - 2, nt - nn)
    # verify: parse again and compare the text
    new = bytes(out)
    script.messages(new, 0)
    return new
