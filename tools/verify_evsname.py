"""Check the EVS nickname converter (tools/evsname.py) in an emulator.

Runs the converter as patched into the name-entry module (Unicorn, MIPS32
LE) on many kana strings and compares what it writes with the Python model
in evsname.py. Non-kana input must reach the game's own strcpy, which is
taken from the EXE (sectors given).

usage: python tools/verify_evsname.py <module.bin> <exe.bin>
   module.bin: Disc 1 sectors 2038.. (>= 0xE000 bytes); exe.bin: the PS-X EXE
"""
import random
import sys

from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_RA, UC_MIPS_REG_SP

import evsname as E
import namepatch as NP

DST, SRC, RET = 0x80100000, 0x80100100, 0x80000100


def main(mod_path, exe_path):
    mod = NP.patch_module(open(mod_path, "rb").read()[:NP.SIZE])
    exe = open(exe_path, "rb").read()
    mu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 + UC_MODE_LITTLE_ENDIAN)
    mu.mem_map(0, 0x200000)
    mu.mem_write(0x15800, exe[0x800:0x800 + 0x57800])
    mu.mem_write(NP.BASE & 0x1FFFFFFF, mod)
    kana = ([bytes([0x82, b]) for b in range(0x9F, 0xF2)] + [bytes([0x83, b]) for b in range(0x40, 0x97)] +
            ["ー".encode("cp932"), "　".encode("cp932")])
    tests = ["ふぃあくん", "かれい", "しゅんちゃん", "まっちゃん", "ウィリアム", "おにいちゃん", "ルーシー",
             "あきらさん", "とてもながいなまえですよね"]
    cases = [t.encode("cp932") for t in tests]
    rnd = random.Random(7)
    for _ in range(20000):
        cases.append(b"".join(rnd.choice(kana) for _ in range(rnd.randrange(1, 9))))
    cases += [b"", b"\xa1\x40\xbb\x40", "ＡＢ".encode("cp932"), "漢字".encode("cp932")]
    for c in cases:
        src = c + b"\0"
        mu.mem_write(SRC & 0x1FFFFFFF, src + b"\0" * 32)
        mu.mem_write(DST & 0x1FFFFFFF, b"\xee" * 32)
        mu.reg_write(UC_MIPS_REG_A0, DST)
        mu.reg_write(UC_MIPS_REG_A1, SRC)
        mu.reg_write(UC_MIPS_REG_RA, RET)
        mu.reg_write(UC_MIPS_REG_SP, 0x801FF000)
        mu.emu_start(E.CODE, RET, count=20000)
        want = E.model(src)
        if want is None:
            want = src                     # strcpy
        got = bytes(mu.mem_read(DST & 0x1FFFFFFF, len(want)))
        assert got == want, (c.decode("cp932", "replace"), got.hex(" "), want.hex(" "))
        assert len(want) <= 15
    print("OK: %d strings; e.g. ふぃあくん -> %s" % (len(cases), E.model("ふぃあくん".encode("cp932") + b"\0").hex(" ")))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
