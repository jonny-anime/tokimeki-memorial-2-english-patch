"""Build a patched (English) disc image from an original disc and translations.

    python tools/build_patch.py <original.bin> <out.bin> [--tl DIR ...] [--no-exe]

  * copies the original image (never modified) to out.bin and writes a .cue;
  * patches the EXE with the letter-pair glyph code (tools/glyphpatch.py);
  * re-encodes every translated scene (tools/translations.py formats; the
    --tl directories default to translations/ and are read in order, later
    ones winning) and writes it back into its container:
      file    - main-game scene variant: grows up to the end of its last
                sector; beyond that, the scene's group is rewritten after the
                end of the disc with a new offset table (tools/groups.py), up to
                the size its event module is known to load;
      bundle  - grows into the spare bytes of the bundle's last sector, later
                parts move up, the size table is rewritten;
      pack    - same, plus the pack's offset table;
      packed  - must not grow (shorter text is zero-padded);
  * fixes EDC/ECC of every written sector.

A scene that doesn't fit is left in Japanese and reported with the number of
bytes it is over. Text-box rows (lines joined by {nobreak}) wider than 20 cells are reported
as warnings.
"""
import collections
import json
import os
import shutil
import struct
import sys

import cdimage
import extract_scripts as X
import glyphpatch
import namepatch
import evsgrid
import datepatch
import strpack
import pictures
import groups as GR
import overlays as OV
import rebuild
import scenes
import script
import translations
import uitext

ROW_CELLS = 20          # cells in a text-box row after the speaker label (columns 4-23)
# assumed widths of inserted strings (full-width cells)
CODE_CELLS = {"name": 4, "you": 6, "char": 4, "num": 2}


def cells(raw):
    """(cells, continues) for one encoded string (un-swapped, without NUL):
    approximate width, and whether it ends with {nobreak}."""
    n, p, cont = 0, 0, False
    while p < len(raw):
        c = raw[p]
        cont = c == 0x0C
        if c >= 0x80:
            n += 1; p += 2
        elif c >> 4 == 3:
            n += CODE_CELLS["num"]; p += 2
        elif c in (0x1D, 0x1E, 0x1F):
            n += CODE_CELLS["name"]; p += 1
        elif c >> 4 == 1:
            n += CODE_CELLS["you"]; p += 1
        elif c in (0x2E, 0x2F):
            n += CODE_CELLS["char"]; p += 2
        elif c >> 4 == 2:
            n += CODE_CELLS["char"]; p += 1
        else:
            p += 1
    return n, cont


def row_warnings(b, edits):
    """Rows (lines joined by {nobreak}) of translated messages that are wider
    than a text-box row."""
    out = []
    for m in b.messages:
        row, w, touched = [], 0, False
        for l in m["lines"]:
            at = l["offset"]
            if at in edits:
                raw = rebuild.encode_en(edits[at]).translate(script.SWAP)[:-1]
                touched = True
            else:
                raw = rebuild.encode(X.fmt_tokens(l["tokens"])).translate(script.SWAP)[:-1]
            n, cont = cells(raw)
            w += n; row.append(at)
            if not cont:
                if touched and w > ROW_CELLS:
                    out.append("%s/%s: row is %d cells (holds %d)" % (b.key, "+".join(map(str, row)), w, ROW_CELLS))
                row, w, touched = [], 0, False
    return out


def edits_for(b, tl, names):
    en = dict(tl.get(b.key, {}))
    for m in b.messages:
        if m["speaker"]:
            at = str(m["offset"])
            ja = X.fmt_tokens(m["speaker"])
            if at not in en and ja in names:
                en[at] = names[ja]
    return {int(k): v for k, v in en.items()}


def pad4(b):
    return b + b"\0" * (-len(b) % 4)


class Builder:
    def __init__(self, data, groups=None, overlays=()):
        self.data = bytearray(data)    # the disc with in-place edits (pre) applied
        self.sectors = {}          # sector -> new 2048 bytes
        self.errors, self.warnings, self.done = [], [], []
        self.groups = groups or {}
        self.variants = GR.variant_of(self.groups)
        self.base_lba = len(data) // 2048
        self.append = []           # new sectors after the end of the image
        self.moved = []            # (group sector, new first sector)
        self.force_move = set()    # group sectors to move even if they fit (testing)
        self.overlays = list(overlays)
        self.ovmap = OV.block_map(self.overlays)
        self.exe_words = {}        # EXE RAM address -> new u32 (overlay sizes)
        self.moved_overlays = []

    def block_end(self, off):
        """Bytes a script block at disc offset off occupies (reachable code)."""
        return script.messages(self.data, off)["end"]

    def put(self, off, body):
        """Overlay body at byte offset off (any alignment)."""
        p = 0
        while p < len(body):
            sec, o = divmod(off + p, 2048)
            if sec not in self.sectors:
                self.sectors[sec] = bytearray(self.data[sec * 2048:sec * 2048 + 2048])
            n = min(2048 - o, len(body) - p)
            self.sectors[sec][o:o + n] = body[p:p + n]
            p += n

    def pre(self, off, body):
        """An in-place edit made before scenes are rebuilt (menu text, place
        names): blocks and overlays that get rebuilt or moved carry it along."""
        self.data[off:off + len(body)] = body
        self.put(off, body)

    def new_block(self, b, edits):
        block = self.data[b.off:b.off + b.end]
        try:
            return rebuild.rebuild(block, edits, english=True)
        except Exception as e:                       # report and keep Japanese
            self.errors.append("%s (sector %d): %s" % (b.key, b.off // 2048, e))
            return None

    def build(self, blocks, tl, names):
        bundles = collections.defaultdict(dict)       # base sector -> {(part, pack idx): new bytes}
        grouped = collections.defaultdict(dict)       # group sector -> {variant sector: (block, new bytes)}
        ovch = collections.defaultdict(dict)          # overlay index -> {(pack, idx): (block, new bytes)}
        for b in blocks:
            edits = edits_for(b, tl, names)
            if not edits:
                continue
            valid = {m["offset"] for m in b.messages if m["speaker"]} | \
                    {l["offset"] for m in b.messages for l in m["lines"]}
            bad = [a for a in edits if a not in valid]
            if bad:
                self.errors.append("%s: no string at offset(s) %s" % (b.key, bad))
                continue
            self.warnings += row_warnings(b, edits)
            new = self.new_block(b, edits)
            if new is None:
                continue
            if b.kind == "file" and b.off // 2048 in self.variants:
                grouped[self.variants[b.off // 2048][0].sector][b.off // 2048] = (b, new)
            elif b.kind == "file":
                tail = self.data[b.off + b.end:b.off + b.size]
                body = new + tail
                limit = b.size + b.room
                if len(body) > limit:
                    self.errors.append("%s (sector %d): %d bytes over its sector" % (b.key, b.off // 2048, len(body) - limit))
                    continue
                self.put(b.off, body + b"\0" * (limit - len(body)))
                self.done.append(b.key)
            elif b.kind in ("bundle", "pack"):
                bundles[b.bundle[0]][(b.bundle[1], b.pack)] = (b, new)
            elif b.off in self.ovmap:
                ov, pk, i = self.ovmap[b.off]
                ovch[ov.index][(pk, i)] = (b, new)
            else:
                if len(new) > b.end:
                    self.errors.append("%s (sector %d): %d bytes too long; its container can't grow yet"
                                       % (b.key, b.off // 2048, len(new) - b.end))
                    continue
                self.put(b.off, new + b"\0" * (b.end - len(new)))
                self.done.append(b.key)
        for base, changes in bundles.items():
            self.rebuild_bundle(base, changes)
        for gs, changes in grouped.items():
            self.rebuild_group(self.groups[gs], changes)
        for oi, changes in ovch.items():
            self.rebuild_overlay([o for o in self.overlays if o.index == oi][0], changes)

    def rebuild_overlay(self, ov, changes):
        """Script packs inside a code overlay. Each changed pack is laid out
        again from its first block, tightly; blocks that no longer fit
        before the pack's old end go after the end of the overlay (the
        pack's offsets are rewritten). If anything went there, the whole
        overlay is written after the end of the disc with a new sector
        (resource table) and size (EXE)."""
        data = self.data
        buf = bytearray(data[ov.start:ov.start + ov.size])
        base = (ov.size + 3) & ~3
        tail = bytearray()
        keys = [b.key for b, _ in changes.values()]
        bymark = collections.defaultdict(dict)
        for (p, i), (b, new) in changes.items():
            bymark[p][i] = (b, new)
        for p, ch in bymark.items():
            offs = ov.packs[p]
            n = len(offs)
            last_end = offs[-1] + self.block_end(ov.start + p + offs[-1])
            bodies = []
            for i in range(n):
                if i in ch:
                    bodies.append(pad4(ch[i][1]))
                else:
                    e = offs[i + 1] if i + 1 < n else last_end
                    bodies.append(pad4(bytes(buf[p + offs[i]:p + e])))
            region, cur = (p + offs[0], p + last_end), p + offs[0]
            new_offs = []
            for body in bodies:
                if cur + len(body) <= region[1]:
                    buf[cur:cur + len(body)] = body
                    new_offs.append(cur - p); cur += len(body)
                else:
                    new_offs.append(base + len(tail) - p); tail += body
            buf[cur:region[1]] = b"\0" * (region[1] - cur)
            struct.pack_into("<%dI" % n, buf, p + 4, *new_offs)
        if not tail:
            self.put(ov.start, bytes(buf))
            self.done.extend(keys)
            return
        body = bytes(buf) + b"\0" * (base - ov.size) + bytes(tail)
        new_size = -(-len(body) // 2048) * 2048
        if new_size > ov.max_size():
            self.errors.append("overlay %d (sector %d: %s): %d bytes over the memory known to be free"
                               % (ov.index, ov.sector, ", ".join(sorted(set(keys))), new_size - ov.max_size()))
            return
        body += b"\0" * (new_size - len(body))
        lba = self.base_lba + len(self.append)
        for k in range(new_size // 2048):
            self.append.append(body[k * 2048:(k + 1) * 2048])
        self.put(ov.toc_off + 4, struct.pack("<I", lba))
        self.exe_words[ov.size_addr] = new_size
        self.moved_overlays.append((ov, lba, new_size))
        self.done.extend(keys)

    def rebuild_group(self, g, changes):
        """Variants of a main-game scene group. In place when every changed
        variant still fits its sectors; otherwise the group's variants are
        rewritten after the end of the disc and its offset table updated."""
        data, new_data, move = self.data, {}, False
        keys = [b.key for b, _ in changes.values()]
        for s, (b, new) in changes.items():
            l = g.e[[i for i in range(g.n) if g.sector + g.e[i] == s][0] + 1] - (s - g.sector)
            rest = data[b.off + b.size:(s + l) * 2048].rstrip(b"\0")
            if rest.strip(b"\xff") or len(rest) > 8:
                self.errors.append("%s (sector %d): variant holds more than its script" % (b.key, s))
                return
            # FF end markers can spill into the next sector when the script
            # ends at a sector boundary: they go along with the script
            body = new + data[b.off + b.end:b.off + b.size] + rest
            nl = max(l, -(-len(body) // 2048))
            if nl > l:
                if nl > g.cap:
                    self.errors.append("%s (sector %d): needs %d sectors, its event module is only known to load %d"
                                       % (b.key, s, nl, g.cap))
                    return
                move = True
            new_data[s] = body + b"\0" * (nl * 2048 - len(body))
        if not move and g.sector not in self.force_move:
            for s, body in new_data.items():
                self.put(s * 2048, body)
            self.done.extend(keys)
            return
        start = self.base_lba + len(self.append)
        e_new, cur = [], start - g.sector
        for i in range(g.n):
            e_new.append(cur)
            if g.e[i + 1] > g.e[i]:
                s, l = g.sector + g.e[i], g.e[i + 1] - g.e[i]
                body = new_data.get(s, data[s * 2048:(s + l) * 2048])
                for k in range(len(body) // 2048):
                    self.append.append(body[k * 2048:(k + 1) * 2048])
                cur += len(body) // 2048
        e_new.append(cur)
        head = bytearray(data[g.sector * 2048:(g.sector + 1) * 2048])
        struct.pack_into("<%dI" % (g.n + 1), head, 4, *e_new)
        self.put(g.sector * 2048, bytes(head))
        self.moved.append((g.sector, start))
        self.done.extend(keys)

    def rebuild_bundle(self, base_sector, changes):
        data, base = self.data, base_sector * 2048
        n, sizes, starts = scenes.read_bundle(data, base)
        total = 4 + 4 * n + sum(sizes)
        nsec = -(-total // 2048)
        parts = []
        for k, (p, x) in enumerate(zip(starts, sizes)):
            part = data[p:p + x]
            if (k, None) in changes:
                part = pad4(changes[(k, None)][1])
            elif any(c[0] == k for c in changes):
                offs = scenes.read_pack(data, p, x)
                bodies = [part[o:(offs[i + 1] if i + 1 < len(offs) else x)] for i, o in enumerate(offs)]
                for (kk, i), (b, new) in changes.items():
                    if kk == k:
                        bodies[i] = pad4(new)
                hdr = len(part[:offs[0]])
                out, cur = bytearray(part[:hdr]), hdr
                new_offs = []
                for body in bodies:
                    new_offs.append(cur); out += body; cur += len(body)
                struct.pack_into("<%dI" % len(offs), out, 4, *new_offs)
                part = pad4(bytes(out))
            parts.append(part)
        out = struct.pack("<I", n) + struct.pack("<%dI" % n, *[len(p) for p in parts]) + b"".join(parts)
        keys = [c[0].key for c in changes.values()]
        if len(out) > nsec * 2048:
            self.errors.append("bundle at sector %d (%s): %d bytes over its %d sectors"
                               % (base_sector, ", ".join(sorted(set(keys))), len(out) - nsec * 2048, nsec))
            return
        out += data[base + len(out):base + nsec * 2048]     # keep the rest of the last sector
        self.put(base, out)
        self.done.extend(keys)


def main(argv):
    args, tl_dirs, exe, force = [], [], True, set()
    pic_dir = os.path.join(translations.ROOT, "pictures")
    pic_dir = pic_dir if os.path.isdir(pic_dir) else None
    i = 0
    while i < len(argv):
        if argv[i] == "--tl":
            tl_dirs.append(argv[i + 1]); i += 2
        elif argv[i] == "--pictures":
            pic_dir = argv[i + 1]; i += 2
        elif argv[i] == "--no-exe":
            exe = False; i += 1
        elif argv[i] == "--move-group":          # testing: relocate this group anyway
            force.add(int(argv[i + 1])); i += 2
        else:
            args.append(argv[i]); i += 1
    src, dst = args
    if os.path.exists(dst) and os.path.samefile(src, dst):
        sys.exit("refusing to overwrite the original image")
    tl_problems = []
    tl, names, ui = translations.load(tl_dirs or [translations.DEFAULT], with_ui=True, problems=tl_problems)
    print("translations: %d scenes, %d speaker names, %d menu/system strings" % (len(tl), len(names), len(ui)))

    shutil.copyfile(src, dst)
    cue = os.path.splitext(src)[0] + ".cue"
    if os.path.exists(cue):
        txt = open(cue).read().replace(os.path.basename(src), os.path.basename(dst))
        open(os.path.splitext(dst)[0] + ".cue", "w").write(txt)
    if exe:
        name, secs = glyphpatch.patch_image(dst)
        print("EXE %s patched (sectors %s)" % (name, secs))

    data = X.read_user_data(src)
    blocks = scenes.scan(data)
    with open(src, "rb") as f:
        _, elba, esize = glyphpatch.find_exe(f)
        exe = cdimage.read_user_data(f, elba, -(-esize // 2048))
    bld = Builder(data, GR.find_groups(data), OV.find(data, exe))
    bld.force_move = force
    n_ui = 0
    if ui:          # menu/system text and place names, in place, before scenes are rebuilt
        for u in uitext.scan(data, src) + uitext.scene_places(data, blocks):
            if u.id not in ui or strpack.covers(u.module, u.addr):
                continue
            try:
                b = uitext.encode(ui[u.id], u.ja, u.cells)
            except (KeyError, UnicodeEncodeError) as e:
                bld.errors.append("%s %s: can't encode %r" % (u.id, u.where, ui[u.id])); continue
            if len(b) > u.max_bytes:
                bld.errors.append("%s %s: %r takes %d bytes, at most %d fit%s" % (
                    u.id, u.where, ui[u.id], len(b), u.max_bytes,
                    " (the game draws %d cells there)" % u.cells if u.cells else ""))
                continue
            body = b + b"\0" * (u.field - len(b))
            if u.obf:                              # the EVS module is stored + 0x64
                body = bytes((x + u.obf) & 0xFF for x in body)
            bld.pre(u.off, body)
            if u.count_off is not None:
                bld.pre(u.count_off, bytes([len(b) // 2]))
            n_ui += 1
        print("menu/system strings and place names replaced: %d" % n_ui)
        packed, notes = strpack.apply(data, src, ui, bld.pre)   # name tables with more room
        if packed:
            print("name tables rewritten: %s" % ", ".join(packed))
        for n in notes:
            print("note: name table", n)
    bld.build(blocks, tl, names)
    written = []
    with open(dst, "r+b") as f:
        for sec in sorted(bld.sectors):
            new = bytes(bld.sectors[sec])
            if new != data[sec * 2048:sec * 2048 + 2048]:
                cdimage.write_user_data(f, sec, new)
                written.append(sec)
        if bld.exe_words:                          # overlay sizes in the EXE
            old = cdimage.read_user_data(f, elba, -(-esize // 2048))
            new = bytearray(old)
            for addr, v in bld.exe_words.items():
                struct.pack_into("<I", new, 0x800 + addr - OV.EXE_BASE, v)
            written += cdimage.write_changed(f, elba, old, bytes(new))
        if bld.append:
            f.seek(0, 2)
            assert f.tell() == bld.base_lba * cdimage.SECTOR
            for k, sec in enumerate(bld.append):
                f.write(cdimage.make_form1(bld.base_lba + k, sec))
    if exe:                                        # after the sector writes, which start from
        secs = namepatch.patch_image(dst)          # the original bytes (the prompts share its sector)
        if secs:
            print("name entry patched (sectors %s)" % secs)
        secs = evsgrid.patch_image(dst)            # the same for the E.V.S. module's messages
        if secs:
            print("EVS reading grid patched (sectors %s)" % secs)
    # pictures last: whole-sector writes above must not undo them
    pics, pic_err = pictures.apply_manifest(dst, pic_dir) if pic_dir else ([], [])
    if pics:
        print("pictures patched: %s" % ", ".join(pics))
    if exe:                                        # the date box tiles go with main_stats_hands.png
        secs, notes = datepatch.patch_image(dst)
        if secs:
            print("date box patched (sectors %s)" % secs)
        for n in notes:
            print("note:", n)
    # check: the patched disc has the same blocks in the same containers,
    # and every patched block parses
    new_data = X.read_user_data(dst)
    after = [b for b in scenes.scan(new_data) if b.off < len(data)]
    assert [(b.sid, b.kind) for b in after] == [(b.sid, b.kind) for b in blocks], "block layout changed"
    regroup = GR.find_groups(new_data)
    for gs, start in bld.moved:                    # moved groups: every variant parses
        g = regroup[gs]
        assert g.sector + g.e[0] >= start
        for i, s, l in g.variants():
            if new_data[s * 2048:s * 2048 + 4] == b"\x38\x35\0\0":
                script.messages(new_data, s * 2048)
    for ov, lba, size in bld.moved_overlays:      # moved overlays: every pack block parses
        buf = new_data[lba * 2048:lba * 2048 + size]
        for p in ov.packs:
            n = struct.unpack_from("<H", buf, p + 2)[0]
            for o in struct.unpack_from("<%dI" % n, buf, p + 4):
                assert buf[p + o:p + o + 4] == b"\x38\x35\0\0"
                script.messages(buf, p + o)
    print("scenes patched: %d instances (%d keys), sectors written: %d, groups moved: %d, overlays moved: %d (%d sectors added)"
          % (len(bld.done), len(set(bld.done)), len(written), len(bld.moved), len(bld.moved_overlays), len(bld.append)))
    for w in bld.warnings:
        print("warning:", w)
    bld.errors += pic_err + ["%s (kept in Japanese)" % p for p in tl_problems]
    for e in bld.errors:
        print("NOT PATCHED:", e)
    return 1 if bld.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
