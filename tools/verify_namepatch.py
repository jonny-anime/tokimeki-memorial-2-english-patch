"""Check the name-entry patch (tools/namepatch.py) in an emulator.

Runs the patched append and backspace routines (Unicorn, MIPS32 LE) on a
name field for many random key sequences, and compares the field and the
cursor after every key with a Python model of the intended behaviour. The
model of non-letter keys is the original game code (read from the
module): it is run too, unpatched, for sequences of Japanese characters,
and must give the same result as the patched routine.

usage: python tools/verify_namepatch.py <module.bin>   (Disc 1 sectors 2038.., >= 0xE000 bytes)
"""
import random
import struct
import sys

from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_S0,
                                UC_MIPS_REG_SP, UC_MIPS_REG_RA)

import font_en
import namepatch as NP

STATE = 0x800F97B0
CELL, ROW = 0x80100000, 0x80100100
SOUND_HIT = []


def make(mod):
    mu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 + UC_MODE_LITTLE_ENDIAN)
    mu.mem_map(0, 0x200000)
    mu.mem_write(NP.BASE & 0x1FFFFFFF, mod)
    mu.mem_write(NP.SOUND & 0x1FFFFFFF, bytes.fromhex("0800e003" "00000000"))   # jr ra; nop
    return mu


def run_append(mu, field, ch):
    """One key on field 0 (surname) or 1: ch = 2-byte code."""
    mu.mem_write(ROW & 0x1FFFFFFF, struct.pack(">H", ch) + b"\0\0")
    mu.mem_write(CELL & 0x1FFFFFFF, b"\0" * 0x20)
    mu.mem_write((CELL + 4) & 0x1FFFFFFF, struct.pack("<I", ROW))
    mu.reg_write(UC_MIPS_REG_S0, STATE)
    mu.reg_write(UC_MIPS_REG_A1, STATE + 7 * field)
    mu.reg_write(UC_MIPS_REG_A2, CELL)
    mu.reg_write(UC_MIPS_REG_SP, 0x801FF000)
    mu.reg_write(UC_MIPS_REG_RA, 0x80000000)
    mu.emu_start(NP.APPEND_AT, NP.APPEND_EXIT, count=2000)


def run_bs(mu, field):
    mu.reg_write(UC_MIPS_REG_A2, STATE)
    mu.reg_write(UC_MIPS_REG_A0, STATE + 7 * field)
    mu.emu_start(NP.BS_AT, NP.BS_EXIT, count=2000)


def get(mu, field):
    f = bytes(mu.mem_read((STATE + 7 * field) & 0x1FFFFFFF, 7))
    pos = struct.unpack("<h", bytes(mu.mem_read((STATE + 0x1FC) & 0x1FFFFFFF, 2)))[0]
    return f, pos


def reset(mu):
    mu.mem_write(STATE & 0x1FFFFFFF, b"\0" * 0x200)


# --- model -------------------------------------------------------------
def is_pair(b0):
    return 0xA0 <= b0 <= 0xDF or 0xEB <= b0 <= 0xEF


def letter(ch):
    if 0x8260 <= ch <= 0x8279:
        return "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[ch - 0x8260]
    if 0x8281 <= ch <= 0x829A:
        return "abcdefghijklmnopqrstuvwxyz"[ch - 0x8281]
    return {0x8144: ".", 0x8166: "'", 0x817C: "-", 0x815B: "-", 0x8140: " "}.get(ch)


def model_append(f, pos, ch):
    f = bytearray(f)
    L = letter(ch)
    if L is not None:
        last = pos if f[2 * pos] else pos - 1
        if last >= 0 and is_pair(f[2 * last]) and f[2 * last + 1] == 0x40:
            f[2 * last + 1] = 0x40 + font_en.INDEX[L]
            return bytes(f), pos
        b = font_en.pair_code(L, " ")
    else:
        b = struct.pack(">H", ch)
    f[2 * pos:2 * pos + 3] = b + b"\0"
    return bytes(f), (pos if pos == 2 else pos + 1)


def model_bs(f, pos):
    f = bytearray(f)
    k = 0 if pos == 0 else (2 if pos == 2 and f[4] else pos - 1)
    if is_pair(f[2 * k]) and f[2 * k + 1] != 0x40:
        f[2 * k + 1] = 0x40
        return bytes(f), pos
    f[2 * k] = 0
    return bytes(f), k


KEYS = ([0x8260 + i for i in range(26)] + [0x8281 + i for i in range(26)] +
        [0x8144, 0x8166, 0x817C, 0x815B, 0x8140] + [0x82A0, 0x8341, 0x8393, 0x889F])


def main(path):
    orig = open(path, "rb").read()[:NP.SIZE]
    new = NP.patch_module(orig)
    mu, mo = make(new), make(orig)
    rnd = random.Random(1)
    n = 0
    for trial in range(3000):
        field = rnd.randrange(2)
        reset(mu)
        reset(mo)
        f, pos = bytes(7), 0
        jp = trial % 5 == 0                       # Japanese only: must match the original
        for _ in range(rnd.randrange(1, 16)):
            if rnd.random() < 0.3:
                run_bs(mu, field)
                if jp:
                    run_bs(mo, field)
                f, pos = model_bs(f, pos)
            else:
                ch = rnd.choice(KEYS[-4:] if jp else KEYS)
                run_append(mu, field, ch)
                if jp:
                    run_append(mo, field, ch)
                f, pos = model_append(f, pos, ch)
            got = get(mu, field)
            assert got == (f, pos), (trial, got, (f, pos))
            if jp:
                assert get(mo, field) == got, (trial, get(mo, field), got)
            n += 1
    # a full name
    reset(mu)
    for ch in "Kaitos":
        run_append(mu, 0, {c: k for k in KEYS if (c := letter(k))}[ch])
    f, pos = get(mu, 0)
    text = "".join("".join(font_en.decode_pair(f[i] << 8 | f[i + 1])) for i in range(0, 6, 2))
    assert text == "Kaitos" and f[6] == 0, (f, text)
    print("OK: %d keys checked; 'Kaitos' fills the 7-byte field as %s" % (n, f.hex(" ")))


if __name__ == "__main__":
    main(sys.argv[1])
