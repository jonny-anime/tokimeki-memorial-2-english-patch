"""How much room each scene has for longer (English) text.

    python tools/space_report.py <disc.bin> [<disc.bin> ...] [--json out.json]

English text takes about 1 byte per letter, Japanese 2 bytes per character;
a translation usually needs 1.1-1.5 times the bytes of the Japanese. For
each disc this prints how many scenes of each container kind (see
tools/scenes.py) could take that growth in place.
"""
import json
import sys

import extract_scripts as X
import scenes

RATIOS = (1.2, 1.5)


def report(path):
    data = X.read_user_data(path)
    blocks = [b for b in scenes.scan(data) if b.text_bytes()]
    rows = []
    for b in blocks:
        t = b.text_bytes()
        rows.append(dict(key=b.key, sid=b.sid, sector=b.off // 2048, kind=b.kind, text=t,
                         room=b.room, fits={str(r): b.room >= (r - 1) * t for r in RATIOS}))
    return rows


def summary(rows):
    out = {}
    for kind in ("file", "bundle", "pack", "packed"):
        rs = [r for r in rows if r["kind"] == kind]
        out[kind] = dict(scenes=len(rs), text_bytes=sum(r["text"] for r in rs),
                         **{"fit_x%s" % k: sum(r["fits"][k] for r in rs) for k in map(str, RATIOS)})
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    js = None
    if "--json" in args:
        i = args.index("--json"); js = args[i + 1]; del args[i:i + 2]
    allrows = {}
    for p in args:
        rows = report(p)
        allrows[p] = rows
        print(p)
        for kind, s in summary(rows).items():
            print("  %-7s %5d scenes  %8d text bytes   fit at x1.2: %5d   x1.5: %5d"
                  % (kind, s["scenes"], s["text_bytes"], s["fit_x1.2"], s["fit_x1.5"]))
    if js:
        json.dump(allrows, open(js, "w"), ensure_ascii=False, indent=0)
