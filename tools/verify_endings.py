"""Checks of tools/endings.py against your Disc 1 image.

    python tools/verify_endings.py <disc1.bin>

1. With no English every ending module is rebuilt byte-identical.
2. With the Japanese itself put through the English encoder (and every name
   replaced), every dialogue string is still reached through its pointers,
   and the game's own narration routine, run in a MIPS emulator (Unicorn)
   with random answers from the game-state functions, writes the same text
   from the rebuilt script as from the original.
3. The same with text made longer, which makes the builder move pieces of
   narration out of the script behind new table functions (run as real code).
Needs: pip install unicorn
"""
import os, random, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import endings as E
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import *

STRCPY, STRLEN = 0x8005A074, 0x8005A0C4


def run_interp(m, results, inserts):
    """Run the module's own narration interpreter. results: {n: value} for
    condition functions; inserts: {n: bytes} strings returned by pointer."""
    w = E._words(m)
    i = next(k for k, x in enumerate(w) if x == 0x24020066 and 0x2402007A in w[k:k + 40])
    while (w[i] & 0xFFFF8000) != 0x27BD8000:
        i -= 1
    entry = E.RAM + i * 4
    it = E.find_interpreter(m)
    uc = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 + UC_MODE_LITTLE_ENDIAN)
    uc.mem_map(0, 0x200000)                  # KSEG0 is the low 2 MB
    P = lambda a: a & 0x1FFFFFFF
    uc.mem_write(P(0x800C0000), bytes(m))
    STUB, STRS, OUT, STACK, RET = 0x80100000, 0x80104000, 0x80108000, 0x8011F000, 0x80103000
    nfun = 128
    spos = STRS
    saddr = {}
    for n, b in inserts.items():
        uc.mem_write(P(spos), b + b"\0"); saddr[n] = spos; spos += len(b) + 1
    JR = struct.pack("<II", 0x03E00008, 0)
    for n in range(nfun):
        if n in results or n in inserts:      # the game's own functions; new ones run as they are
            uc.mem_write(P(E.RAM + it["funcs"] + 4 * n), struct.pack("<I", STUB + 16 * n))
        uc.mem_write(P(STUB + 16 * n), JR)
    uc.mem_write(P(STRCPY), JR); uc.mem_write(P(STRLEN), JR)
    calls = []

    def hook(uc, addr, size, ud):
        if STUB <= addr < STUB + 16 * nfun and (addr - STUB) % 16 == 0:
            n = (addr - STUB) // 16
            calls.append(n)
            v = saddr[n] if n in saddr else results.get(n, 0)
            uc.reg_write(UC_MIPS_REG_V0, v)
        elif addr == STRCPY:
            d, s = uc.reg_read(UC_MIPS_REG_A0), uc.reg_read(UC_MIPS_REG_A1)
            b = bytes(uc.mem_read(P(s), 8192)); b = b[:b.index(0) + 1]
            uc.mem_write(P(d), b)
            uc.reg_write(UC_MIPS_REG_V0, d)
        elif addr == STRLEN:
            s = uc.reg_read(UC_MIPS_REG_A0)
            b = bytes(uc.mem_read(P(s), 8192))
            uc.reg_write(UC_MIPS_REG_V0, b.index(0))
    uc.hook_add(UC_HOOK_CODE, hook)
    uc.reg_write(UC_MIPS_REG_SP, STACK)
    uc.reg_write(UC_MIPS_REG_RA, RET)
    uc.reg_write(UC_MIPS_REG_A0, OUT)
    try:
        uc.emu_start(entry, RET, count=2000000)
    except Exception as e:
        raise RuntimeError("%s at pc %x ra %x entry %x" % (e, uc.reg_read(UC_MIPS_REG_PC), uc.reg_read(UC_MIPS_REG_RA), entry))
    assert uc.reg_read(UC_MIPS_REG_PC) == RET, "interpreter did not return"
    out = bytes(uc.mem_read(P(OUT), 0x10000))
    return out[:out.index(0)], calls


import zlib


def grow(ja):
    """A fake translation: a third of the lines get a cell 'ab' in front."""
    return "ab" + ja if zlib.crc32(ja.encode("utf-8")) % 3 == 0 else ja


def same(ja):
    """The Japanese itself, through the English encoder."""
    return ja


def fake(mod, nwb, f, with_dialogue=True):
    narr = {str(l["at"]): f(l["ja"]) for m in nwb["messages"] for l in m["lines"]}
    wb = mod.workbook("1")
    tl = {str(l["at"]): f(l["ja"]) for m in wb["messages"] for l in m["lines"]} if with_dialogue else {}
    ui = {E.ui_id(s.raw.decode("cp932")): "Xy" for s in mod.names}
    rep = []
    new = mod.rebuild(tl, narr, ui, rep)
    return new, [r for r in rep if not r.startswith("warning")]


def narration_runs(mod, new, rng, n, check):
    cc = {t[1] for i, (_, t) in enumerate(mod.tokens) if t[0] == "call" and mod.tokens[i + 1][1][0] == "jz"}
    ci = {t[1] for i, (_, t) in enumerate(mod.tokens) if t[0] == "call" and mod.tokens[i + 1][1][0] != "jz"}
    for trial in range(n):
        p = rng.choice([0.1, 0.5, 0.9])
        res = {k: int(rng.random() < p) for k in cc}
        ins = {k: ("<%d>" % k).encode() for k in ci}
        a, ca = run_interp(mod.m, res, ins)
        b, cb = run_interp(new, res, ins)
        assert ca == cb and check(a, b), "%s trial %d: narration differs" % (mod.key, trial)
    return n


def _norm(x):
    """Text without marks and blanks, and the marks in order (a mark between
    the two letters of a cell moves behind the cell)."""
    s = E.decode(x)
    return re.sub(r"\{[^}]*\}| ", "", s), re.findall(r"\{[^}]*\}", s)


def text_equal(a, b):
    return _norm(a) == _norm(b)


def grown_equal(a, b):
    ta, tb = _norm(a), _norm(b)
    return ta[0] == tb[0].replace("ab", "") and ta[1] == tb[1]


def main(path):
    data = open(path, "rb").read() if path.endswith(".ud") else __import__("extract_scripts").read_user_data(path)
    mods = E.find(data)
    assert len(mods) == 13
    nwb = E.narration_workbook(mods, "1")
    rng = random.Random(1)
    for mod in mods:
        rep = []
        assert mod.rebuild({}, {}, {}, rep) == mod.m and not rep
    print("1. no English: 13 modules byte-identical")
    runs = 0
    for mod in mods:
        new, errs = fake(mod, nwb, same)
        assert new != mod.m and not errs, errs
        E.verify(mod, new)
        runs += narration_runs(mod, new, rng, 60, text_equal)
        # every dialogue pointer: the fake line, in the order of the original table
        for s in mod.dialogue:
            for r in s.refs:
                p = struct.unpack_from("<I", new, r)[0] - E.RAM
                got = new[p:new.index(b"\0", p)]
                assert text_equal(s.raw[3:], got[3:]) and got[:3] == s.raw[:3]
    print("2. the Japanese re-encoded as if it were English, names replaced, in all 13: strings reached through every pointer, %d interpreter runs equal" % runs)
    runs = fits = 0
    for mod in mods:
        new, errs = fake(mod, nwb, grow)
        if new == mod.m:
            new, errs = fake(mod, nwb, grow, with_dialogue=False)
        if new == mod.m:
            continue
        fits += 1
        E.verify(mod, new)
        runs += narration_runs(mod, new, rng, 30, grown_equal)
        for s in mod.dialogue:
            for r in s.refs:
                p = struct.unpack_from("<I", new, r)[0] - E.RAM
                assert grown_equal(s.raw, new[p:new.index(b"\0", p)])
        print("   %s script %d bytes at %x, %d texts moved out, %d of %d bytes used" % (mod.key, mod.last["script"], mod.last["script_at"], mod.last["spilled"], mod.last["need"], mod.last["total"]))
    print("3. longer fake English (fits in %d modules): %d interpreter runs equal" % (fits, runs))


if __name__ == "__main__":
    main(sys.argv[1])
