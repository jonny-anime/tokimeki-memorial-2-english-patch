"""How many bytes each scene's English may add, by the builder's own rules.

    python tools/limits.py <out.json> <disc.bin> [<disc.bin> ...]

Writes {scene key: bytes} (1 letter = 1 byte, a full-width character or a
number code 2, other codes 1; the same unit as the checker's "grows by"):

  scene in a group (main game)  its event module's buffer (tools/groups.py
                                `cap` sectors) minus the scene's size
  other file scene              the free bytes left in its last sector
  bundle / pack part            the free bytes left in the bundle's sectors
                                (shared with the other parts)
  packed                        0

A scene found on several discs gets the smallest value. tools/mt.py reads
the file (--limits) and makes the model shorten scenes that go over.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_scripts as X  # noqa: E402
import groups as GR  # noqa: E402
import scenes  # noqa: E402

MARGIN = 4          # pad4 of rebuilt parts


def limits(data):
    variants = GR.variant_of(GR.find_groups(data))
    out = {}
    for b in scenes.scan(data):
        s = b.off // 2048
        if b.kind == "file" and s in variants and b.off % 2048 == 0:
            g = variants[s][0]
            room = g.cap * 2048 - b.size
        elif b.kind in ("file", "bundle", "pack"):
            room = b.room
        else:
            room = 0
        room = max(0, room - MARGIN)
        out[b.key] = min(room, out.get(b.key, room))
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    allv = {}
    for d in argv[1:]:
        for k, v in limits(X.read_user_data(d)).items():
            allv[k] = min(v, allv.get(k, v))
        print("%s: %d scenes" % (os.path.basename(d), len(allv)))
    with open(argv[0], "w", encoding="utf-8") as f:
        json.dump(dict(sorted(allv.items())), f, indent=0)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
