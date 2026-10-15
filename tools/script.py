"""Tokimeki Memorial 2 scene-script bytecode: disassembler and text extraction.

Opcode operand lengths are taken from the interpreter in the script-engine
module (RAM 0x800c4084; opcode table at 0x800c0348, expression evaluator at
0x800c3d7c, string expander at 0x800c3758). See docs/game-internals.md §6.
"""
import struct

import font_en

SWAP = bytes(((i >> 4) | ((i & 15) << 4)) for i in range(256))


class ScriptError(Exception):
    pass


# ---------- strings (expander 0x800c3758) ----------
def read_string(b, p):
    """Return (end_offset_after_NUL, tokens). Tokens: ('text', str) or ('code', name)."""
    toks, buf = [], bytearray()

    def flush():
        if buf:
            out = []
            for i in range(0, len(buf), 2):          # every character is 2 bytes here
                pair = font_en.decode_pair(buf[i] << 8 | buf[i + 1])
                if pair:                              # English letter pair (patched game)
                    out.append(pair[0] + pair[1])
                    continue
                try:
                    out.append(bytes(buf[i:i + 2]).decode("cp932"))
                except UnicodeDecodeError as e:
                    raise ScriptError("bad Shift-JIS %r at %#x" % (bytes(buf[i:i + 2]), p)) from e
            toks.append(("text", "".join(out)))
            buf.clear()

    while True:
        if p >= len(b):
            raise ScriptError("unterminated string")
        c = SWAP[b[p]]
        if c == 0:
            flush()
            return p + 1, toks
        if c >= 0x80:
            buf += bytes((c, SWAP[b[p + 1]]))
            p += 2
        elif c >> 4 == 3:                      # 0x3X + argument byte: number variable
            flush(); toks.append(("code", "num%X:%02X" % (c & 15, SWAP[b[p + 1]]))); p += 2
        elif c >> 4 == 1 and c & 15 in (0xD, 0xE, 0xF):   # name strings (0x80075004/0b/12)
            flush(); toks.append(("code", {0xD: "name1", 0xE: "name2", 0xF: "name3"}[c & 15])); p += 1
        elif c >> 4 == 1:                      # 0x10-0x1C: the player as character N calls him
            flush(); toks.append(("code", "you:%02X" % c)); p += 1
        elif c in (0x2E, 0x2F):                # character name chosen by a variable (+ 1 byte)
            flush(); toks.append(("code", "char%X:%02X" % (c, SWAP[b[p + 1]]))); p += 2
        elif c >> 4 == 2:                      # 0x20-0x2D: a character's name
            flush(); toks.append(("code", "char:%02X" % c)); p += 1
        elif c == 0x0C:                        # next line continues on the same row
            flush(); toks.append(("code", "nobreak")); p += 1
        else:                                  # anything else: kept, nothing drawn
            flush(); toks.append(("code", "c%02X" % c)); p += 1


# ---------- expressions ----------
# Childhood engine: evaluator 0x800c3d7c (27 ops 0x40-0x5A).
# Main-game engine (Disc 2 module at sector 1559, RAM 0x800c0000):
# evaluator 0x800e4070, table 0x800c1504 (34 ops 0x40-0x61). The main
# engine is a superset for every opcode the childhood scripts use.
BINARY = set(range(0x41, 0x46)) | set(range(0x47, 0x4D)) | {0x58, 0x59, 0x5B}
NULLARY = set(range(0x54, 0x58)) | set(range(0x5C, 0x62))   # game date / state queries

def read_expr(b, p, depth=0):
    if depth > 64:
        raise ScriptError("expression too deep")
    op = b[p]; p += 1
    if op == 0x40:                              # prefix, re-read
        return read_expr(b, p, depth + 1)
    if op in BINARY:
        p = read_expr(b, p, depth + 1); return read_expr(b, p, depth + 1)
    if op in (0x46, 0x5A):                      # negate / logical not
        return read_expr(b, p, depth + 1)
    if op == 0x4D:                              # assignment: target byte + value
        sub = b[p]; p += 1
        if sub == 0x14:
            return p
        return read_expr(b, p, depth + 1)
    if op == 0x4E:                              # 16-bit constant
        return p + 2
    if op == 0x4F or 0x50 <= op <= 0x53:        # variable read / byte-argument queries
        return p + 1
    if op in NULLARY:
        return p
    raise ScriptError("unknown expression op %02X at %#x" % (op, p - 1))


# ---------- statements (main engine dispatcher 0x800e4940, table 0x800c1644) ----------
FIXED = {0x00: 0, 0x3E: 0, 0x17: 1, 0x1E: 2, 0x1F: 3, 0x20: 0, 0x21: 0, 0x22: 2, 0x23: 2,
         0x26: 0, 0x27: 0, 0x31: 2, 0x38: 0, 0x3F: 0, 0x80: 0, 0x81: 1, 0x82: 1, 0x83: 2,
         0x87: 0, 0x89: 0, 0x8A: 0, 0x90: 0, 0x98: 1, 0x99: 1, 0x9A: 1, 0x9B: 1,
         0xA3: 4, 0xA7: 1, 0xB0: 3, 0xB8: 1, 0xF0: 0, 0xF1: 0}
EXPR = {0x40, 0x88, 0xFD, 0xFE}
A0_SUB = {0x00: 2, 0x01: 4, 0x02: 2, 0x03: 2, 0x04: 2, 0x05: 2, 0x06: 3, 0x07: 1,
          0x08: 1, 0x09: 1, 0x0A: 1, 0x0B: 1, 0x20: 2}            # table 0x800c1a44
A2_SUB = {0x01: 5, 0x02: 3, 0x03: 3, 0x04: 3, 0x05: 3, 0x06: 3, 0x07: 1, 0x08: 1,
          0x09: 1, 0x0A: 1, 0x0B: 2, 0x0C: 1, 0x0D: 1, 0x0E: 1}   # table 0x800c1acc
A8_SUB = {0x00: 2, 0x02: 2, 0x06: 2, 0x07: 2, 0x08: 2, 0x01: 1, 0x03: 1, 0x10: 1,
          0x11: 1, 0x20: 1, 0x21: 1, 0x05: 4, 0x09: 3, 0x40: 6}   # table 0x800c1b0c


def step(b, p):
    """Decode one instruction at p. Returns (op, info, next_offset); info is the
    string tokens for 10/11/18, else None."""
    op = b[p]; p += 1
    if op in (0x10, 0x11, 0x18):
        p, toks = read_string(b, p)
        return op, toks, p
    if op == 0xFF: pass
    elif op in FIXED: p += FIXED[op]
    elif op in EXPR: p = read_expr(b, p)
    elif op == 0x30: p = read_expr(b, p) + 2            # if (expr) else jump s16
    elif op == 0xA0: p += 1 + A0_SUB.get(b[p], 0)
    elif op == 0xA2: p += 1 + A2_SUB.get(b[p], 0)
    elif op == 0xA8: p += 1 + A8_SUB.get(b[p], 0)
    elif op == 0xA1:                                     # 2 bytes, then expr if first == 0 else 1 byte
        first = b[p]; p += 2
        p = read_expr(b, p) if first == 0 else p + 1
    elif op == 0xAF:                                     # 1 byte, +1 if (b & 0xE0) == 0x40
        x = b[p]; p += 1 + (1 if x & 0xE0 == 0x40 else 0)
    else:
        raise ScriptError("unhandled opcode %02X at %#x" % (op, p - 1))
    return op, None, p


def disassemble(b, p, end=None):
    """Linear sweep from p until the first FF. Yields (offset, op, info)."""
    end = len(b) if end is None else end
    while p < end:
        at = p
        op, info, p = step(b, p)
        yield at, op, info
        if op == 0xFF:
            return
    raise ScriptError("ran past end without FF")


def walk(b, entry, lo=None, hi=None):
    """Follow control flow from entry: 30 (if) continues and branches, 31 (goto)
    branches only, FF ends a path. Returns {offset: (op, info, next_offset)}
    for every reachable instruction. Jump offsets are relative to the end of
    the instruction (checked: all 81,936 jumps on the five discs land on an
    instruction start)."""
    seen, todo = {}, [entry]
    while todo:
        p = todo.pop()
        while p not in seen:
            at = p
            op, info, nxt = step(b, p)
            seen[at] = (op, info, nxt)
            if op == 0xFF:
                break
            if op in (0x30, 0x31):
                tgt = nxt + struct.unpack_from("<h", b, nxt - 2)[0]
                if (lo is None or lo <= tgt) and (hi is None or tgt < hi):
                    todo.append(tgt)
                if op == 0x31:
                    break
            p = nxt
    return seen


def parse_block(b, off=0):
    """Script block: '85' magic, u16 bytecode offset, u16 n, u16 table[8], char id[8]."""
    if b[off:off + 4] != b"\x38\x35\x00\x00":
        raise ScriptError("bad magic")
    code_off, nsec = struct.unpack_from("<HH", b, off + 4)
    table = struct.unpack_from("<8H", b, off + 8)
    sid = b[off + 0x18:off + 0x20].decode("ascii")
    return dict(id=sid, code=off + code_off, nsec=nsec, table=table)


def messages(b, off=0):
    """Group text ops into messages: speaker (op 18) + lines (op 10/11), split at op 80/81."""
    blk = parse_block(b, off)
    out, cur = [], None
    code = walk(b, blk["code"], lo=off, hi=off + 0x10000)
    blk["end"] = max(code) + 1 - off
    blk["instructions"] = len(code)
    for at in sorted(code):
        op, info, _ = code[at]
        if op == 0x18:
            cur = dict(offset=at - off, speaker=info, lines=[])
            out.append(cur)
        elif op in (0x10, 0x11):
            if cur is None:
                cur = dict(offset=at - off, speaker=None, lines=[]); out.append(cur)
            cur["lines"].append(dict(offset=at - off, op=op, tokens=info))
        elif op in (0x80, 0x81, 0x82):     # end of message (wait for button); 81/82 hypothesis
            cur = None
    blk["messages"] = out
    return blk
