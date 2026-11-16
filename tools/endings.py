"""The ending modules of Tokimeki Memorial 2 (Disc 1): the confession scenes
and the epilogue narration.  docs/game-internals.md, section 16.

    python tools/endings.py report <disc1.bin> [--tl DIR ...]
        what is there, how much room each ending has and what the English
        in translations/ (or DIR) would do to it

Thirteen code modules (one per ending, loaded at 0x800C0000 through the
resource table at sector 541) hold their own text, outside the scene scripts:

  dialogue   NUL-terminated strings, each reached through one pointer word:
             "n01" + Shift-JIS text with line breaks (0x0A) and ASCII marks:
             tNNNN (wait until frame NNNN of the voice clip), wN, gN, sN, r.
             n01 picks the speaker's name from a table of the module.
  names      short strings, reached through pointer words (speaker labels,
             names put into the narration).
  narration  one bytecode script per module, run once into a buffer:
               >= 0x80  two-byte character, copied
               0x0A     line break, copied
               66 nn    call function nn of the table after the script; a
                        pointer result is a string to insert, anything else
                        is the condition for the next 7A
               7A s16   jump (relative to the byte after 7A) if the last
                        result was 0
               67 s16   jump
               00       end
             Any other byte is skipped, so English must be letter pairs.

The modules can't grow (their variables start right after them in memory),
so the English is packed into the space the Japanese used: every string that
is only reached through pointers can go anywhere in that space, and the
script is re-encoded with its jumps recomputed.  Nothing else in a module
changes, and an ending with no English stays byte-identical.

Workbooks (tools/translations.py init): G_ENDINGnn-<hash>, one per module,
with its dialogue, and G_ENDING_NARRATION-<hash> with every different piece
of narration once (most of it is shared between the endings).  Both are
"packed": the English may not take more bytes than the Japanese.
"""
import collections
import hashlib
import re
import struct

import font_en

SECTOR = 2048
RAM = 0x800C0000                 # load address of these modules
TOC_SECTOR = 541                 # resource table: (u32 read word, u32 sector)
MAX_SECTORS = 40
DIALOGUE_CELLS = 20              # longest Japanese dialogue line
NARRATION_CELLS = 18             # longest Japanese narration line (buffer rows hold 22)
NARRATION = "G_ENDING_NARRATION"
SPILL_MIN = 24                   # shortest narration text worth moving out of the script

# the narration interpreter tests its opcodes in this order (addiu v0, zero, imm)
_SIG = [0x24020066, 0x2402007A, 0x24020067]


def _words(m):
    return struct.unpack_from("<%dI" % (len(m) // 4), m, 0)


def find_interpreter(m):
    """Where the narration script of a module is: offsets of the script, of
    the lui/addiu that load its address and of the function table; None if
    this is not an ending module."""
    w = _words(m)
    for i, x in enumerate(w):
        if x != _SIG[0]:
            continue
        j = [k for k in range(i, min(i + 40, len(w))) if w[k] == _SIG[1]]
        if not j or _SIG[2] not in w[j[0]:j[0] + 32]:
            continue
        s0 = s4 = None
        hi = {}
        for k in range(max(0, i - 24), i):
            op, rs, rt, imm = w[k] >> 26, (w[k] >> 21) & 31, (w[k] >> 16) & 31, w[k] & 0xFFFF
            simm = imm - 0x10000 if imm & 0x8000 else imm
            if op == 15:
                hi[rt] = (imm << 16, k)
            elif op == 9 and rs in hi and rt == 16:
                s0 = ((hi[rs][0] + simm) & 0xFFFFFFFF, hi[rs][1], k)
            elif op == 9 and rs in hi and rt == 20:
                s4 = ((hi[rs][0] + simm) & 0xFFFFFFFF, hi[rs][1], k)
        if s0 and s4:
            return {"script": s0[0] - RAM, "lui": s0[1] * 4, "addiu": s0[2] * 4,
                    "funcs": s4[0] - RAM, "funcs_lui": s4[1] * 4, "funcs_addiu": s4[2] * 4}
    return None


def parse_script(m, p):
    """Narration bytecode at offset p -> ([(offset, token)], end offset).
    token: ("text", bytes) | ("call", n) | ("jz", target) | ("jmp", target) |
    ("skip", byte) | ("end",); targets are offsets in m.  A run of text is
    split wherever a jump lands inside it."""
    out = []
    while True:
        c = m[p]
        if c == 0:
            break
        if c >= 0x80 or c == 0x0A:
            q = p
            while m[q] >= 0x80 or m[q] == 0x0A:
                q += 2 if m[q] >= 0x80 else 1
            out.append((p, ("text", bytes(m[p:q]))))
            p = q
        elif c == 0x66:
            out.append((p, ("call", m[p + 1]))); p += 2
        elif c in (0x7A, 0x67):
            off = struct.unpack_from("<h", m, p + 1)[0]
            out.append((p, ("jz" if c == 0x7A else "jmp", p + 1 + off))); p += 3
        else:
            out.append((p, ("skip", c))); p += 1
    end = p + 1
    out.append((p, ("end",)))
    targets = sorted({t[1] for _, t in out if t[0] in ("jz", "jmp")})
    res = []
    for o, t in out:
        if t[0] == "text":
            for x in [x for x in targets if o < x < o + len(t[1])]:
                res.append((o, ("text", t[1][:x - o])))
                t = ("text", t[1][x - o:]); o = x
        res.append((o, t))
    return res, end


# --- text <-> bytes -----------------------------------------------------------

_TAG = re.compile(rb"t\d{4}|[wgs]\d|r")
_CODE = re.compile(r"(\{[^}]*\}|\n)")
TAG_RE = re.compile(r"\{(t\d{4}|[wgs]\d|r)\}")


def decode(raw):
    """Module text bytes -> the workbook's text: Shift-JIS characters, letter
    pairs as their two letters, line breaks, marks as {t0023} {w0} {g0} {s0}
    {r}, anything else as {bXX}."""
    out, p = [], 0
    while p < len(raw):
        c = raw[p]
        if c >= 0x80 and p + 1 < len(raw):
            pair = font_en.decode_pair(c << 8 | raw[p + 1])
            if pair:
                out.append(pair[0] + pair[1])
            else:
                try:
                    out.append(raw[p:p + 2].decode("cp932"))
                except UnicodeDecodeError:
                    out.append("{b%02X}{b%02X}" % (c, raw[p + 1]))
            p += 2
            continue
        m = _TAG.match(raw, p)
        if m:
            out.append("{%s}" % m.group().decode()); p = m.end()
        elif c in (0x0A, 0x20):
            out.append(chr(c)); p += 1
        else:
            out.append("{b%02X}" % c); p += 1
    return "".join(out)


def encode(text):
    """Workbook text -> module bytes (no NUL).  Characters of the English font
    go two to a cell; a mark that falls between the two letters of a cell is
    moved behind the cell, so that marks cost no blank half cells.  Other
    characters are full-width Shift-JIS cells."""
    out, pend, held = bytearray(), [], []

    def flush():
        if pend:
            out.extend(font_en.pair_code(pend[0], pend[1] if len(pend) > 1 else " "))
            pend.clear()
        for h in held:
            out.extend(h)
        held.clear()

    for tok in _CODE.split(text):
        if not tok:
            continue
        if tok == "\n":
            flush(); out.append(0x0A)
        elif tok.startswith("{"):
            m = TAG_RE.fullmatch(tok)
            b = re.fullmatch(r"\{b([0-9A-F]{2})\}", tok)
            if m:
                code = m.group(1).encode()
            elif b:
                code = bytes([int(b.group(1), 16)])
            else:
                raise ValueError("unknown code " + tok)
            if pend:
                held.append(code)          # after the cell the pending letter is in
            else:
                out.extend(code)
        else:
            for ch in tok:
                if font_en.is_supported(ch):
                    pend.append(ch)
                    if len(pend) == 2:
                        flush()
                else:
                    flush()
                    out.extend(font_en.wide(ch))
    flush()
    return bytes(out)


def cells(raw):
    """Width in cells of the longest line of encoded text."""
    best = n = p = 0
    while p < len(raw):
        c = raw[p]
        if c >= 0x80:
            n += 1; p += 2
        elif c == 0x0A:
            best = max(best, n); n = 0; p += 1
        else:
            m = _TAG.match(raw, p)
            p = m.end() if m else p + 1
    return max(best, n)


def _width(text):
    """Cells of one line of workbook text; an inserted string counts as 4."""
    return cells(encode(re.sub(r"\{ins:\d+\}", "XXXXXXXX", text)))


def wrap(text, width):
    """Break lines longer than `width` cells at spaces (narration)."""
    out = []
    for line in text.split("\n"):
        while _width(line) > width:
            cut = None
            for m in re.finditer(" ", line):
                if _width(line[:m.start()]) <= width:
                    cut = m.start()
                else:
                    break
            if not cut:
                break
            out.append(line[:cut]); line = line[cut + 1:]
        out.append(line)
    return "\n".join(out)


def split_lines(text):
    """'a\\n\\nb\\n' -> (['a', 'b'], ['', '\\n\\n', '\\n']): the lines a
    translator sees and the line breaks around them."""
    parts = re.split(r"(\n+)", text)
    lines, seps = [], [""]
    for i, x in enumerate(parts):
        if i % 2:
            seps[-1] = x
        elif x:
            lines.append(x); seps.append("")
        elif i == 0:
            pass
    if not lines:
        return [], ["".join(seps)]
    return lines, seps


def join_lines(lines, seps):
    out = seps[0]
    for l, s in zip(lines, seps[1:]):
        out += l + s
    return out


def _cells(b):
    out, p = [], 0
    while p < len(b):
        n = 2 if b[p] >= 0x80 else 1
        out.append(b[p:p + n]); p += n
    return out


def _best_phrase(texts, lo=5, hi=64):
    """The run of cells (as bytes) whose storing once saves the most bytes
    over all the texts, or None.  A use costs 2 bytes; the phrase costs its
    length + 1 and 16 bytes of function and table entry."""
    count = collections.Counter()
    for t in texts:
        c = _cells(t)
        for n in range(lo, min(hi, len(c)) + 1):
            for i in range(len(c) - n + 1):
                count[b"".join(c[i:i + n])] += 1
    best, gain = None, 8
    for b, k in count.items():
        if k < 2:
            continue
        k = sum(_count_at_cells(t, b) for t in texts)          # non-overlapping uses
        g = k * (len(b) - 2) - (len(b) + 17)
        if g > gain:
            best, gain = b, g
    return best


def _find_at_cell(t, b, start=0):
    """First position >= start where b occurs in t on a cell boundary, or -1."""
    p = start
    while True:
        p = t.find(b, p)
        if p < 0:
            return -1
        q = 0
        while q < p:
            q += 2 if t[q] >= 0x80 else 1
        if q == p:
            return p
        p += 1


def _count_at_cells(t, b):
    n, p = 0, _find_at_cell(t, b)
    while p >= 0:
        n += 1
        p = _find_at_cell(t, b, p + len(b))
    return n


def _replace_phrase(seq, b, n):
    """Every use of phrase b in the text tokens of seq becomes a call of
    function n.  A token's old offset (what jumps refer to) stays on its
    first piece."""
    out = []
    for o, t in seq:
        if t[0] != "text" or _find_at_cell(t[1], b) < 0:
            out.append((o, t)); continue
        text, p = t[1], 0
        while True:
            q = _find_at_cell(text, b, p)
            if q < 0:
                break
            if q > p:
                out.append((o, ("text", text[p:q]))); o = None
            out.append((o, ("call", n))); o = None
            p = q + len(b)
        if p < len(text):
            out.append((o, ("text", text[p:])))
    return out


def is_japanese(s):
    return bool(s) and all("　" <= ch <= "ヿ" or "一" <= ch <= "鿿" or
                           "＀" <= ch <= "￯" or ch in "『』「」…？！" for ch in s)


def ui_id(ja):
    """The id tools/uitext.py gives a menu string with this Japanese text."""
    return "ui-" + hashlib.sha1(ja.rstrip("　").encode("utf-8")).hexdigest()[:10]


# --- modules --------------------------------------------------------------------

class Str:
    def __init__(self, off, raw, slot, refs, movable, kind):
        self.off, self.raw, self.slot = off, raw, slot      # slot: bytes it owns, with NUL and padding
        self.refs, self.movable, self.kind = refs, movable, kind


class Unit:
    """A piece of narration between two branch points: text and inserted
    strings ({ins:N} = the string function N returns)."""
    def __init__(self, toks):
        self.toks = toks                      # [(offset, token)]
        self.off = toks[0][0]
        rep = b"".join(t[1] if t[0] == "text" else b"\x66" + bytes([t[1]]) for _, t in toks)
        self.id = int(hashlib.sha1(rep).hexdigest()[:7], 16)
        self.text = "".join(decode(t[1]) if t[0] == "text" else "{ins:%d}" % t[1] for _, t in toks)
        self.size = sum(len(t[1]) if t[0] == "text" else 2 for _, t in toks)


class Module:
    def __init__(self, n, sector, size, data):
        self.n, self.sector, self.size = n, sector, size
        self.m = bytes(data[sector * SECTOR:sector * SECTOR + size])
        self.scene = "G_ENDING%02d" % n
        self.key = "%s-%s" % (self.scene, hashlib.sha1(self.m).hexdigest()[:8])
        it = find_interpreter(self.m)
        self.script, self.funcs = it["script"], it["funcs"]
        self.lui, self.addiu = it["lui"], it["addiu"]
        self.funcs_lui, self.funcs_addiu = it["funcs_lui"], it["funcs_addiu"]
        self.tokens, self.script_end = parse_script(self.m, self.script)
        self._strings()
        self._units()
        self._speakers()

    def _strings(self):
        m, w = self.m, _words(self.m)
        ptr = collections.defaultdict(list)
        comp, hi = set(), {}
        for i, x in enumerate(w):
            if RAM <= x < RAM + len(m) and not self.script <= i * 4 < self.funcs:
                ptr[x - RAM].append(i * 4)
            # addresses built by code: lui r, hi ... addiu/ori r2, r, lo (r still
            # holding the lui's value)
            op, rs, rt, imm = x >> 26, (x >> 21) & 31, (x >> 16) & 31, x & 0xFFFF
            if op == 15:
                hi[rt] = (imm << 16, i)
            elif op in (9, 13) and rs in hi and i - hi[rs][1] <= 8:
                comp.add((hi[rs][0] + (imm - 0x10000 if imm & 0x8000 and op == 9 else imm)) & 0xFFFFFFFF)
                hi.pop(rt, None)
            elif op == 0:
                hi.pop((x >> 11) & 31, None)
            elif op == 3:                             # jal: v0, v1 and the argument registers change
                for r in (2, 3, 4, 5, 6, 7):
                    hi.pop(r, None)
            elif 8 <= op <= 14 or 32 <= op <= 38:     # other immediates and loads write rt
                hi.pop(rt, None)
        self.dialogue, self.names = [], []
        for p in sorted(ptr):
            if p >= self.script or p % 4 or m[p] == 0 or (p and m[p - 1]):
                continue
            e = m.index(b"\0", p)
            raw = m[p:e]
            slot = e + 1
            while slot % 4 and m[slot] == 0:
                slot += 1
            movable = (RAM + p) not in comp
            if re.match(rb"n\d\d", raw):
                if "{b" in decode(raw[3:]):
                    continue
                self.dialogue.append(Str(p, raw, slot - p, ptr[p], movable, "dialogue"))
            elif len(raw) <= 24 and len(raw) % 2 == 0:
                try:
                    s = raw.decode("cp932")
                except UnicodeDecodeError:
                    continue
                if is_japanese(s):
                    self.names.append(Str(p, raw, slot - p, ptr[p], movable, "name"))

    def _units(self):
        targets = {t[1] for _, t in self.tokens if t[0] in ("jz", "jmp")}
        self.units, cur = [], []
        toks = self.tokens
        for i, (o, t) in enumerate(toks):
            insert = t[0] == "call" and toks[i + 1][1][0] != "jz"
            if t[0] == "text" or insert:
                if cur and o in targets:
                    self.units.append(Unit(cur)); cur = []
                cur.append((o, t))
            elif cur:
                self.units.append(Unit(cur)); cur = []
        self.units = [u for u in self.units if any(t[0] == "text" for _, t in u.toks)]

    def _speakers(self):
        """n-number -> Japanese name, from the table the dialogue routine
        indexes (lui/addiu a0 after the test for 'n')."""
        m, w = self.m, _words(self.m)
        self.speakers = {}
        for i, x in enumerate(w):
            if x != 0x2402006E:
                continue
            hi = None
            for k in range(i, min(i + 16, len(w))):
                op, rs, rt, imm = w[k] >> 26, (w[k] >> 21) & 31, (w[k] >> 16) & 31, w[k] & 0xFFFF
                if op == 15 and rt == 4:
                    hi = imm << 16
                elif op == 9 and rs == 4 and rt == 4 and hi is not None:
                    tab = (hi + (imm - 0x10000 if imm & 0x8000 else imm)) - RAM
                    for n in range(40):
                        if not 0 <= tab + 4 * n < len(m) - 4:
                            break
                        p = w[(tab + 4 * n) // 4] - RAM
                        if 0 <= p < self.script and m[p]:
                            try:
                                s = m[p:m.index(b"\0", p)].decode("cp932")
                            except UnicodeDecodeError:
                                continue
                            if is_japanese(s):
                                self.speakers[n] = s
                    return

    # workbooks ------------------------------------------------------------------
    def at(self, s, i):
        return s.off * 32 + i

    def workbook(self, disc):
        msgs = []
        for s in self.dialogue:
            lines, _ = split_lines(decode(s.raw[3:]))
            name = self.speakers.get(int(s.raw[1:3]))
            msgs.append({"speaker": {"at": None, "ja": name, "en": ""} if name else None,
                         "lines": [{"at": self.at(s, i), "ja": l, "en": ""} for i, l in enumerate(lines)]})
        return {"scene": self.scene, "key": self.key, "kind": "packed",
                "found": {disc: [self.sector]}, "messages": msgs}

    # rebuilding -----------------------------------------------------------------
    def rebuild(self, tl, narration, ui, report):
        """The module with English: tl {at: en} for its dialogue, narration
        {at: en} for the narration units, ui {ui id: en} for names.  Returns
        the new bytes (the old ones if nothing is translated); problems go to
        report (a list of strings)."""
        m = self.m
        new_str = {}                               # Str -> new bytes without NUL
        for s in self.dialogue:
            lines, seps = split_lines(decode(s.raw[3:]))
            en = [tl.get(str(self.at(s, i)), "") for i in range(len(lines))]
            if not any(en):
                continue
            if not all(en):
                report.append("%s/%d: only some lines have English (kept in Japanese)" % (self.key, self.at(s, 0)))
                continue
            try:
                body = encode(join_lines(en, seps))
            except (ValueError, KeyError, UnicodeEncodeError) as e:
                report.append("%s/%d: can't encode: %s (kept in Japanese)" % (self.key, self.at(s, 0), e))
                continue
            if cells(body) > DIALOGUE_CELLS:
                report.append("warning: %s/%d: a line is %d cells (the Japanese never exceeds %d)"
                              % (self.key, self.at(s, 0), cells(body), DIALOGUE_CELLS))
            new_str[s] = s.raw[:3] + body
        for s in self.names:
            en = ui.get(ui_id(s.raw.decode("cp932")))
            if not en:
                continue
            try:
                new_str[s] = b"" if en == "{none}" else encode(en)
            except (ValueError, KeyError, UnicodeEncodeError) as e:
                report.append("%s name at %x: can't encode %r" % (self.key, s.off, en))
        new_units = {}                             # unit offset -> [token]
        for u in self.units:
            lines, seps = split_lines(u.text)
            en = [narration.get(str(u.id * 32 + i), "") for i in range(len(lines))]
            if not any(en):
                continue
            where = "%s/%d (in %s)" % (NARRATION, u.id * 32, self.scene)
            if not all(en):
                report.append("%s: only some lines have English (kept in Japanese)" % where); continue
            text = join_lines(en, seps)
            ins_ja = sorted(re.findall(r"\{ins:\d+\}", u.text))
            if sorted(re.findall(r"\{ins:\d+\}", text)) != ins_ja:
                report.append("%s: the {ins:N} codes differ from the Japanese (kept in Japanese)" % where); continue
            toks = []
            try:
                for part in re.split(r"(\{ins:\d+\})", wrap(text, NARRATION_CELLS)):
                    if part.startswith("{ins:"):
                        toks.append(("call", int(part[5:-1])))
                    elif part:
                        b = encode(part)
                        if _TAG.search(re.sub(rb"[\x80-\xff].", b"", b)):
                            raise ValueError("dialogue marks can't be used in narration")
                        toks.append(("text", b))
            except (ValueError, KeyError, UnicodeEncodeError) as e:
                report.append("%s: can't encode: %s (kept in Japanese)" % (where, e)); continue
            new_units[u.off] = (len(u.toks), toks)
        if not new_str and not new_units:
            return m

        # the script, with its jumps recomputed
        seq, i, toks = [], 0, self.tokens              # [(old offset or None, token)]
        while i < len(toks):
            o, t = toks[i]
            if o in new_units:
                n, repl = new_units[o]
                seq += [(o if k == 0 else None, r) for k, r in enumerate(repl)]
                i += n
            else:
                seq.append((o, t)); i += 1
        def assemble(seq):
            size = {"text": lambda t: len(t[1]), "call": lambda t: 2, "jz": lambda t: 3,
                    "jmp": lambda t: 3, "skip": lambda t: 1, "end": lambda t: 1}
            pos, p = {}, 0
            for o, t in seq:
                if o is not None:
                    pos[o] = p
                p += size[t[0]](t)
            out = bytearray()
            for o, t in seq:
                if t[0] == "text":
                    out += t[1]
                elif t[0] == "call":
                    out += bytes([0x66, t[1]])
                elif t[0] in ("jz", "jmp"):
                    out += bytes([0x7A if t[0] == "jz" else 0x67]) + struct.pack("<h", pos[t[1]] - (len(out) + 1))
                elif t[0] == "skip":
                    out.append(t[1])
                else:
                    out.append(0)
            return out

        script = assemble(seq)
        plain_seq = list(seq)
        # the space: every movable string's slot and the script's
        strs = self.dialogue + self.names
        free = [[s.off, s.off + s.slot] for s in strs if s.movable]
        free.append([self.script, self.funcs])
        free.sort()
        merged = []
        for a, b in free:
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        total = sum(b - a for a, b in merged)
        out = bytearray(m)
        for a, b in merged:
            out[a:b] = bytes(b - a)

        # Too much text: phrases that occur several times in the narration are
        # stored once, each behind a new function of (a copy of) the table
        # that returns its address; the interpreter copies a returned string
        # into the text.  Then, if the script still doesn't fit its own block,
        # its longest pieces of text move out the same way.  Safe only
        # because every 7A directly follows its own 66.
        spill = []                                  # texts stored outside the script, in table order
        nfun = 1 + max(t[1] for _, t in toks if t[0] == "call")
        room = self.funcs - self.script
        fixed = sum(len(b) + 1 for b in {new_str.get(s, s.raw) for s in strs if s.movable})

        def over():
            extra = sum(len(b) + 1 for b in spill) + (4 * (nfun + len(spill)) + 12 * len(spill) + 3 if spill else 0)
            return max(len(script) - room, len(script) + fixed + extra - total)

        targets = {t[1] for _, t in toks if t[0] in ("jz", "jmp")}
        plain = all(toks[k - 1][1][0] == "call" and o not in targets
                    for k, (o, t) in enumerate(toks) if t[0] == "jz")
        while plain and over() > 0 and nfun + len(spill) < 255:
            b = _best_phrase([t[1] for _, t in seq if t[0] == "text"])
            if b is None:
                break
            spill.append(b)
            seq = _replace_phrase(seq, b, nfun + len(spill) - 1)
            script = assemble(seq)
        if plain and len(script) > room:
            for b in sorted({t[1] for _, t in seq if t[0] == "text" and len(t[1]) >= SPILL_MIN},
                            key=lambda b: -len(b)):
                if len(script) <= room or nfun + len(spill) > 255:
                    break
                spill.append(b)
                seq = _replace_phrase(seq, b, nfun + len(spill) - 1)
                script = assemble(seq)

        def take(n, prefer=None, align=1):
            order = sorted(merged, key=lambda iv: (iv[0] != prefer, iv[1] - iv[0]))
            for iv in order:
                a = -(-iv[0] // align) * align
                if iv[1] - a >= n:
                    iv[0] = a + n
                    return a
            return None

        need = len(script) + sum(len(b) + 1 for b in
                                 {new_str.get(s, s.raw) for s in strs if s.movable} | set(spill))
        if spill:
            need += 4 * (nfun + len(spill)) + 12 * len(spill) + 3
        spos = take(len(script), prefer=self.script)
        if spos is None:
            report.append("%s: the narration takes %d bytes, the largest free block is %d (kept in Japanese)"
                          % (self.key, len(script), max(b - a for a, b in merged)))
            return m
        out[spos:spos + len(script)] = script

        def set_address(lui, addiu, addr):
            lo = addr & 0xFFFF
            struct.pack_into("<H", out, lui, ((addr - (lo - 0x10000 if lo & 0x8000 else lo)) >> 16) & 0xFFFF)
            struct.pack_into("<H", out, addiu, lo)

        if spos != self.script:
            set_address(self.lui, self.addiu, RAM + spos)
        placed = {}
        fail = lambda: report.append(
            "%s: the English takes %d bytes, the module has %d: %d too many (kept in Japanese)"
            % (self.key, need, total, max(1, need - total)))
        if spill:
            tab = take(4 * (nfun + len(spill)) + 12 * len(spill), align=4)
            if tab is None:
                fail(); return m
            out[tab:tab + 4 * nfun] = m[self.funcs:self.funcs + 4 * nfun]
            stub = tab + 4 * (nfun + len(spill))
            for k, b in enumerate(spill):
                a = take(len(b) + 1)
                if a is None:
                    fail(); return m
                out[a:a + len(b)] = b
                placed[b] = a
                addr = RAM + a
                lo = addr & 0xFFFF
                hi = ((addr - (lo - 0x10000 if lo & 0x8000 else lo)) >> 16) & 0xFFFF
                # lui v0, hi ; jr ra ; addiu v0, v0, lo
                struct.pack_into("<III", out, stub + 12 * k, 0x3C020000 | hi, 0x03E00008, 0x24420000 | lo)
                struct.pack_into("<I", out, tab + 4 * (nfun + k), RAM + stub + 12 * k)
            set_address(self.funcs_lui, self.funcs_addiu, RAM + tab)
        for s in sorted((s for s in strs if s.movable), key=lambda s: -len(new_str.get(s, s.raw))):
            b = new_str.get(s, s.raw)
            if b not in placed:
                a = take(len(b) + 1)
                if a is None:
                    fail(); return m
                out[a:a + len(b)] = b
                placed[b] = a
            for r in s.refs:
                struct.pack_into("<I", out, r, RAM + placed[b])
        for s in strs:
            if not s.movable and s in new_str:
                b = new_str[s]
                if len(b) + 1 > s.slot:
                    report.append("%s name at %x: %d bytes, %d fit (kept in Japanese)" % (self.key, s.off, len(b), s.slot - 1))
                    continue
                out[s.off:s.off + s.slot] = b + bytes(s.slot - len(b))
        self.last = {"need": need, "total": total, "script": len(script), "script_at": spos,
                     "spilled": len(spill), "plain_seq": plain_seq}
        return bytes(out)


def toc_sectors(data):
    t = data[TOC_SECTOR * SECTOR:(TOC_SECTOR + 1) * SECTOR]
    out = set()
    for o in range(0, len(t) - 7, 8):
        w0, sec = struct.unpack_from("<II", t, o)
        if w0 & 0x7FFFFF == RAM & 0x7FFFFF and 0 < sec < len(data) // SECTOR:
            out.add(sec)
    return sorted(out)


def _sizes(data, secs):
    """Module sizes from the EXE's table (u32 bytes each, in table order)."""
    gaps = [b - a for a, b in zip(secs, secs[1:])]
    for s in range(16, 64):
        if data[s * SECTOR:s * SECTOR + 8] == b"PS-X EXE":
            exe = data[s * SECTOR:s * SECTOR + 0x60000]
            w = _words(exe)
            for i in range(len(w) - len(secs)):
                v = w[i:i + len(secs)]
                if all(x and x % SECTOR == 0 and x // SECTOR <= MAX_SECTORS for x in v) and \
                        all(x // SECTOR == g for x, g in zip(v, gaps)):
                    return list(v)
    return None


def find(data):
    """The ending modules of a disc ([] on a disc without them)."""
    secs = [s for s in toc_sectors(data)
            if find_interpreter(data[s * SECTOR:(s + MAX_SECTORS) * SECTOR])]
    if not secs:
        return []
    sizes = _sizes(data, secs)
    if sizes is None:
        raise ValueError("ending modules found but not their size table in the EXE")
    return [Module(i + 1, s, sizes[i], data) for i, s in enumerate(secs)]


def narration_workbook(mods, disc):
    """Every different piece of narration once, in order of appearance."""
    seen, msgs = {}, []
    for mod in mods:
        for u in mod.units:
            if u.id in seen:
                assert seen[u.id] == u.text
                continue
            seen[u.id] = u.text
            lines, _ = split_lines(u.text)
            msgs.append({"speaker": None,
                         "lines": [{"at": u.id * 32 + i, "ja": l, "en": ""} for i, l in enumerate(lines)]})
    h = hashlib.sha1("\n".join(seen[k] for k in seen).encode("utf-8")).hexdigest()[:8]
    return {"scene": NARRATION, "key": "%s-%s" % (NARRATION, h), "kind": "packed",
            "found": {disc: [mods[0].sector]}, "messages": msgs}


def workbooks(data, disc):
    mods = find(data)
    return ([m.workbook(disc) for m in mods] + [narration_workbook(mods, disc)]) if mods else []


def name_strings(mods):
    """{Japanese: [module numbers]} of the names in the modules."""
    out = collections.defaultdict(list)
    for mod in mods:
        for s in mod.names:
            out[s.raw.decode("cp932")].append(mod.n)
    return out


def apply(data, tl, ui, put):
    """Patch the ending modules of a disc: put(byte offset, bytes) for every
    module that changes.  Returns (modules patched, problems)."""
    mods = find(data)
    if not mods:
        return 0, []
    nkey = narration_workbook(mods, "1")["key"]
    narr = tl.get(nkey, {})
    report, n = [], 0
    for mod in mods:
        new = mod.rebuild(tl.get(mod.key, {}), narr, ui, report)
        if new != mod.m:
            assert len(new) == len(mod.m)
            verify(mod, new)
            put(mod.sector * SECTOR, new)
            n += 1
    return n, report


def check_disc(old_data, new_data, tl, ui):
    """After a build: the patched disc's ending modules are exactly what
    rebuilding the original ones gives, and each passes verify()."""
    mods = find(old_data)
    narr = tl.get(narration_workbook(mods, "1")["key"], {})
    for mod in mods:
        want = mod.rebuild(tl.get(mod.key, {}), narr, ui, [])
        got = bytes(new_data[mod.sector * SECTOR:mod.sector * SECTOR + mod.size])
        assert got == want, "%s: the disc doesn't hold the rebuilt module" % mod.key
        if want != mod.m:
            verify(mod, got)


def verify(mod, new):
    """A rebuilt module differs from the original only in its text space, its
    pointers to it and the script address; every pointer leads to a string
    that parses; the script has the same branch structure."""
    old = mod.m
    strs = mod.dialogue + mod.names
    ok = bytearray(len(old))
    for s in strs:
        ok[s.off:s.off + s.slot] = b"\1" * s.slot
        for r in s.refs:
            ok[r:r + 4] = b"\1" * 4
    ok[mod.script:mod.funcs] = b"\1" * (mod.funcs - mod.script)
    ok[mod.lui:mod.lui + 2] = b"\1\1"
    ok[mod.addiu:mod.addiu + 2] = b"\1\1"
    ok[mod.funcs_lui:mod.funcs_lui + 2] = b"\1\1"
    ok[mod.funcs_addiu:mod.funcs_addiu + 2] = b"\1\1"
    bad = [i for i in range(len(old)) if old[i] != new[i] and not ok[i]]
    assert not bad, "bytes changed outside the text space: %x" % bad[0]
    it = find_interpreter(new)
    assert it and it["lui"] == mod.lui and it["funcs_lui"] == mod.funcs_lui
    nfun = 1 + max(t[1] for _, t in mod.tokens if t[0] == "call")
    assert new[it["funcs"]:it["funcs"] + 4 * nfun] == old[mod.funcs:mod.funcs + 4 * nfun], "function table damaged"
    assert it["funcs"] == mod.funcs or ok[it["funcs"]], "function table outside the text space"
    toks, _ = parse_script(new, it["script"])
    # conditions and jumps in the same order (inserts may move inside their unit)
    cond = lambda ts: [("call", t[1]) if t[0] == "call" else t[0] for i, (_, t) in enumerate(ts)
                       if t[0] in ("jz", "jmp", "end") or (t[0] == "call" and ts[i + 1][1][0] == "jz")]
    assert cond(toks) == cond(mod.tokens), "narration branch structure changed"
    starts = {o for o, _ in toks}
    assert all(t[1] in starts for _, t in toks if t[0] in ("jz", "jmp")), "a jump lands inside a token"
    lo, hi_ = min(s.off for s in strs), len(new)
    for s in strs:
        for r in s.refs:
            p = struct.unpack_from("<I", new, r)[0] - RAM
            assert 0 <= p < len(new) and ok[p], "pointer outside the text space"
            e = new.index(b"\0", p)
            if s.kind == "dialogue":
                assert new[p:p + 3] == s.raw[:3] and "{b" not in decode(new[p + 3:e]), "dialogue string damaged"


def main(argv):
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import extract_scripts as X
    import translations
    if len(argv) < 2 or argv[0] != "report":
        sys.exit(__doc__)
    dirs = [argv[i + 1] for i, a in enumerate(argv) if a == "--tl"]
    data = X.read_user_data(argv[1])
    mods = find(data)
    if not mods:
        sys.exit("no ending modules on this disc (they are on Disc 1)")
    tl, names, ui = translations.load(dirs or [translations.DEFAULT], with_ui=True)
    nwb = narration_workbook(mods, "1")
    narr = tl.get(nwb["key"], {})
    print("narration: %s, %d pieces, %d with English" % (nwb["key"], len(nwb["messages"]), sum(
        all(str(l["at"]) in narr for l in m["lines"]) for m in nwb["messages"])))
    for mod in mods:
        rep = []
        new = mod.rebuild(tl.get(mod.key, {}), narr, ui, rep)
        st = "unchanged"
        if new != mod.m:
            verify(mod, new)
            st = "English: %d of %d bytes used" % (mod.last["need"], mod.last["total"])
        print("%s  sector %d  %d dialogue strings, %d names, %d narration pieces, script %d bytes: %s"
              % (mod.key, mod.sector, len(mod.dialogue), len(mod.names), len(mod.units),
                 mod.script_end - mod.script, st))
        for r in rep:
            print("   ", r)


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
