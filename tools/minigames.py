"""The scripts inside the festival minigame modules.

    python tools/minigames.py report <disc.bin> [--tl DIR ...]
        where they are, how much room each has and what the English in
        translations/ (or DIR) would take

Two code modules (Discs 1, 2 and 4; loaded at 0x800C0000) each carry one
small script of their own: the stall owner's explanations and questions.
It looks like a scene script (tools/script.py: the same instructions, the
same nibble-swapped text), but its header starts with 37 35 instead of
38 35 and it sits in the middle of the module, so tools/scenes.py does not
find it:

    +0x00  37 35 00 00
    +0x04  u16 offset of the first instruction (0x20)
    +0x18  "DEFAULT"
    +0x20  instructions, ending with FF; FF up to the next multiple of 4

The module's own data follows directly, so the script can't grow: the
English must fit in the bytes the Japanese used ("packed" scenes,
G_MINIGAMEn-<hash>).  Jumps (30/31) are recomputed, so single lines may
change length as long as the whole does not.  Speaker labels come from
speaker_names.json as everywhere else.
"""
import hashlib
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_scripts as X  # noqa: E402
import rebuild as RB  # noqa: E402
import script  # noqa: E402

MAGIC = re.compile(rb"\x37\x35\x00\x00.{20}DEFAULT\x00", re.S)
MAX = 0x4000                     # a script is far shorter than this
TEXT = (0x10, 0x11, 0x18)


class Block:
    def __init__(self, n, data, off):
        self.n, self.off = n, off
        b = data[off:off + MAX]
        code = struct.unpack_from("<H", b, 4)[0]
        reach = script.walk(b, code, lo=0, hi=len(b))
        last, p, self.ins = max(reach), code, []
        while True:                               # every instruction, also unreached ones
            op, info, nxt = script.step(b, p)
            self.ins.append((p, op, info, nxt))
            p = nxt
            if op == 0xFF and p > last:
                break
        assert set(reach) <= {i[0] for i in self.ins}, "script doesn't parse in one sweep"
        self.end = p
        assert off % 4 == 0
        self.room = -(-p // 4) * 4               # the module's data starts at the next word
        assert set(b[p:self.room]) <= {0xFF}
        starts = {i[0] for i in self.ins}
        for at, op, info, nxt in self.ins:
            if op in (0x30, 0x31):
                assert nxt + struct.unpack_from("<h", b, nxt - 2)[0] in starts, "jump into an instruction"
        self.raw = bytes(b[:self.room])
        self.scene = "G_MINIGAME%d" % n
        self.key = "%s-%s" % (self.scene, hashlib.sha1(self.raw).hexdigest()[:8])
        self.messages, cur = [], None             # as script.messages
        for at, op, info, nxt in self.ins:
            if op == 0x18:
                cur = {"offset": at, "speaker": info, "lines": []}
                self.messages.append(cur)
            elif op in (0x10, 0x11):
                if cur is None:
                    cur = {"offset": at, "speaker": None, "lines": []}
                    self.messages.append(cur)
                cur["lines"].append({"offset": at, "tokens": info})
            elif op in (0x80, 0x81, 0x82):
                cur = None

    def workbook(self, disc):
        msgs = []
        for m in self.messages:
            sp = {"at": m["offset"], "ja": X.fmt_tokens(m["speaker"]), "en": ""} if m["speaker"] else None
            lines = [{"at": l["offset"], "ja": X.fmt_tokens(l["tokens"]), "en": ""} for l in m["lines"]]
            if sp or lines:
                msgs.append({"speaker": sp, "lines": lines})
        return {"scene": self.scene, "key": self.key, "kind": "packed",
                "found": {disc: [self.off // 2048]}, "messages": msgs}

    def rebuild(self, tl, names, report):
        """The block with English: tl {at: en}, names {Japanese label: en}.
        Returns bytes of the same length (the original ones if nothing is
        translated or the English doesn't fit); problems go to report."""
        edits = dict(tl)
        if not edits:
            return self.raw
        for m in self.messages:                   # labels only where something is translated
            if m["speaker"]:
                ja = X.fmt_tokens(m["speaker"])
                if str(m["offset"]) not in edits and ja in names:
                    edits[str(m["offset"])] = names[ja]
        text_at = {at for at, op, info, nxt in self.ins if op in TEXT}
        out, pos = bytearray(self.raw[:self.ins[0][0]]), {}
        for at, op, info, nxt in self.ins:
            pos[at] = len(out)
            en = edits.get(str(at))
            if en and at in text_at:
                try:
                    out += bytes([op]) + RB.encode_en(en)
                    continue
                except (ValueError, KeyError, UnicodeEncodeError) as e:
                    report.append("%s/%d: can't encode: %s (kept in Japanese)" % (self.key, at, e))
            out += self.raw[at:nxt]
        for k in edits:
            if int(k) not in text_at:
                report.append("%s/%s: no text line at this offset" % (self.key, k))
        for at, op, info, nxt in self.ins:        # jumps: s16 from the end of the instruction
            if op in (0x30, 0x31):
                tgt = nxt + struct.unpack_from("<h", self.raw, nxt - 2)[0]
                end = pos[at] + (nxt - at)
                struct.pack_into("<h", out, end - 2, pos[tgt] - end)
        self.need = len(out)
        if len(out) > self.room:
            report.append("%s: the English takes %d bytes, %d fit: %d too many (kept in Japanese)"
                          % (self.key, len(out), self.room, len(out) - self.room))
            return self.raw
        new = bytes(out) + b"\xFF" * (self.room - len(out))
        verify(self, new, edits)
        return new


def verify(blk, new, edits):
    """The rebuilt block parses to the same instructions, with the same jump
    targets and the new text."""
    b = Block(blk.n, new + b"\xFF" * 8, 0)
    assert [(op) for _, op, _, _ in b.ins] == [(op) for _, op, _, _ in blk.ins]
    index = {at: k for k, (at, _, _, _) in enumerate(b.ins)}
    old_index = {at: k for k, (at, _, _, _) in enumerate(blk.ins)}
    for (at, op, info, nxt), (at0, op0, info0, nxt0) in zip(b.ins, blk.ins):
        if op in (0x30, 0x31):
            t = nxt + struct.unpack_from("<h", new, nxt - 2)[0]
            t0 = nxt0 + struct.unpack_from("<h", blk.raw, nxt0 - 2)[0]
            assert index[t] == old_index[t0], "jump target moved"
        elif op in TEXT:
            en = edits.get(str(at0))
            want = RB.encode_en(en) if en else blk.raw[at0 + 1:nxt0]
            assert new[at + 1:nxt] == want
        else:
            assert new[at:nxt] == blk.raw[at0:nxt0]


def find(data):
    """The minigame scripts of a disc ([] on a disc without them)."""
    return [Block(i + 1, data, m.start()) for i, m in enumerate(MAGIC.finditer(data))]


def workbooks(data, disc):
    return [b.workbook(disc) for b in find(data)]


def apply(data, tl, names, put):
    """put(byte offset, bytes) for every script that changes.  Returns
    (scripts patched, problems)."""
    report, n = [], 0
    for b in find(data):
        new = b.rebuild(tl.get(b.key, {}), names, report)
        if new != b.raw:
            put(b.off, new)
            n += 1
    return n, report


def check_disc(old_data, new_data, tl, names):
    for b in find(old_data):
        want = b.rebuild(tl.get(b.key, {}), names, [])
        assert bytes(new_data[b.off:b.off + b.room]) == want, "%s: the disc doesn't hold the rebuilt script" % b.key


def main(argv):
    import translations as T
    if len(argv) < 2 or argv[0] != "report":
        print(__doc__)
        return 2
    dirs = [argv[i + 1] for i, a in enumerate(argv) if a == "--tl"] or [T.DEFAULT]
    tl, names = T.load(dirs)
    blocks = find(X.read_user_data(argv[1]))
    if not blocks:
        print("no minigame scripts on this disc")
    for b in blocks:
        lines = sum(len(m["lines"]) for m in b.messages)
        rep = []
        new = b.rebuild(tl.get(b.key, {}), names, rep)
        print("%s  sector %d + %#x  %d lines in %d text boxes, %d bytes (%d used)"
              % (b.key, b.off // 2048, b.off % 2048, lines, len(b.messages), b.room, b.end))
        if tl.get(b.key):
            print("   English: %d bytes -> %s" % (b.need, "fits" if new != b.raw else "NOT applied"))
        for r in rep:
            print("   " + r)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
