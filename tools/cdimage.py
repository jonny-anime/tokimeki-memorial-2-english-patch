"""MODE2/2352 sector I/O with EDC/ECC regeneration (ECMA-130 / "Yellow Book").

Sector layout: 12 sync, 4 header, 8 subheader, 2048 user data (Form 1),
4 EDC, 276 ECC (P then Q parity). Independent implementation; verified by
reproducing the stored EDC/ECC of untouched sectors (see verify()).
"""
SECTOR = 2352
DATA = 0x18

# EDC: CRC-32 with polynomial 0x8001801B, reflected (table form)
_EDC = []
for i in range(256):
    r = i
    for _ in range(8):
        r = (r >> 1) ^ (0xD8018001 if r & 1 else 0)
    _EDC.append(r)

# GF(2^8) with primitive polynomial x^8+x^4+x^3+x^2+1 (0x11D)
_F = bytearray(256)   # multiply by alpha
_B = bytearray(256)   # inverse helper
for i in range(256):
    j = ((i << 1) ^ (0x11D if i & 0x80 else 0)) & 0xFF
    _F[i] = j
    _B[i ^ j] = i


def edc(buf):
    c = 0
    for x in buf:
        c = (c >> 8) ^ _EDC[(c ^ x) & 0xFF]
    return c


def _parity(src, majors, minors, mmul, minc):
    size = majors * minors
    out = bytearray(2 * majors)
    for major in range(majors):
        idx = (major >> 1) * mmul + (major & 1)
        a = b = 0
        for _ in range(minors):
            t = src[idx]
            idx += minc
            if idx >= size:
                idx -= size
            a ^= t; b ^= t
            a = _F[a]
        a = _B[_F[a] ^ b]
        out[major] = a
        out[major + majors] = a ^ b
    return out


def fix_form1(sec):
    """Recompute EDC+ECC of a Mode 2 Form 1 sector (bytearray, in place)."""
    sec[0x818:0x81C] = edc(sec[0x10:0x818]).to_bytes(4, "little")
    hdr = bytes(sec[0x0C:0x10])
    sec[0x0C:0x10] = b"\0\0\0\0"            # Mode 2: header excluded from ECC
    sec[0x81C:0x8C8] = _parity(sec[0x0C:0x81C], 86, 24, 2, 86)   # P
    sec[0x8C8:0x930] = _parity(sec[0x0C:0x8C8], 52, 43, 86, 88)  # Q
    sec[0x0C:0x10] = hdr


def is_form1(sec):
    return sec[0x0F] == 2 and not (sec[0x12] & 0x20)


def verify(path, lbas):
    with open(path, "rb") as f:
        for lba in lbas:
            f.seek(lba * SECTOR)
            s = bytearray(f.read(SECTOR))
            orig = bytes(s)
            fix_form1(s)
            if bytes(s) != orig:
                return lba
    return None


def write_user_data(f, lba, data):
    """Overwrite the user data of consecutive Form 1 sectors starting at lba
    with `data` (len must be a multiple of 2048) and fix EDC/ECC."""
    assert len(data) % 2048 == 0
    for k in range(len(data) // 2048):
        f.seek((lba + k) * SECTOR)
        s = bytearray(f.read(SECTOR))
        if not is_form1(s):
            raise ValueError("sector %d is not Mode 2 Form 1" % (lba + k))
        s[DATA:DATA + 2048] = data[k * 2048:(k + 1) * 2048]
        fix_form1(s)
        f.seek((lba + k) * SECTOR)
        f.write(s)


def read_user_data(f, lba, count):
    """User data (2048 B each) of `count` consecutive sectors from lba."""
    f.seek(lba * SECTOR)
    raw = f.read(count * SECTOR)
    return b"".join(raw[i * SECTOR + DATA:i * SECTOR + DATA + 2048] for i in range(count))


def root_files(f):
    """{name: (lba, size)} for the files in the ISO 9660 root directory."""
    pvd = read_user_data(f, 16, 1)
    assert pvd[1:6] == b"CD001", "no ISO 9660 volume descriptor"
    lba, size = int.from_bytes(pvd[158:162], "little"), int.from_bytes(pvd[166:170], "little")
    d = read_user_data(f, lba, (size + 2047) // 2048)
    out, p = {}, 0
    while p < len(d):
        n = d[p]
        if n == 0:                           # records don't cross sectors
            p = (p // 2048 + 1) * 2048
            continue
        name = d[p + 33:p + 33 + d[p + 32]].decode("ascii", "replace").split(";")[0]
        out[name] = (int.from_bytes(d[p + 2:p + 6], "little"), int.from_bytes(d[p + 10:p + 14], "little"))
        p += n
    return out


def write_changed(f, lba, old, new):
    """Write the sectors of `new` that differ from `old` (same length,
    starting at lba). Returns the list of LBAs written."""
    assert len(old) == len(new) and len(new) % 2048 == 0
    done = []
    for k in range(len(new) // 2048):
        a, b = old[k * 2048:(k + 1) * 2048], new[k * 2048:(k + 1) * 2048]
        if a != b:
            write_user_data(f, lba + k, b)
            done.append(lba + k)
    return done


def make_form1(lba, data):
    """A new Mode 2 Form 1 sector (2352 bytes) at lba holding data (2048 B):
    sync, BCD MSF header, zero subheader (as the game's own padding sectors),
    EDC/ECC."""
    assert len(data) == 2048
    bcd = lambda x: (x // 10) << 4 | x % 10
    a = lba + 150
    s = bytearray(SECTOR)
    s[0:12] = b"\x00" + b"\xff" * 10 + b"\x00"
    s[12:16] = bytes((bcd(a // 4500), bcd(a // 75 % 60), bcd(a % 75), 2))
    s[DATA:DATA + 2048] = data
    fix_form1(s)
    return bytes(s)
