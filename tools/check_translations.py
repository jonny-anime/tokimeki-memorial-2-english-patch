"""Check translations before building: what would break or look wrong.

    python tools/check_translations.py [translations | FILE.json | <workbook_dir>]
                                       [--disc D.bin ...] [--json out.json] [--quiet]

With no argument it checks all of translations/; give one file
(translations/miyuki/disc2.json) to check just that. No disc is needed: the
room each scene has is in its file. --disc measures it on your discs instead.
Reports, per scene and line ("<scene key>/<at>"):

  ERROR  the builder would refuse it or the game would show garbage
         - unknown or misspelt {code}
         - menu text longer than its max_bytes
         - a message whose English has a different number of lines than
           the Japanese, or an empty line
         - a scene whose English grows by more bytes than its "room"
  WARN   it builds, but will look wrong
         - a text-box row wider than 20 cells (the game wraps it, maybe
           mid-word), or a box that then needs more than 4 rows
         - a speaker label wider than 3 cells (6 letters)
         - {nobreak} not at the end of a line
         - a {code} of the Japanese missing in the English, or one added
         - characters that are probably accidental: typographic quotes and
           dashes (’ “ ” — –), accented letters (é); they'd be drawn full width
         - (with --disc) a scene that grows past the room in its sector; the
           builder may still fit it by moving the scene, it says so
  INFO   coverage: lines translated per scene and in all

Widths count inserted text at its usual English size: {name1}/{name2} and
{you:NN} 3 cells (6 letters), {char:NN} 5 cells ("Ichimonji"), numbers 2.
Exit status 1 if there are errors.
"""
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import font_en  # noqa: E402
import rebuild  # noqa: E402
import script  # noqa: E402
import uitext  # noqa: E402

ROW_CELLS, BOX_ROWS, LABEL_CELLS = 20, 4, 3
CODE_CELLS = {"name": 3, "you": 3, "char": 5, "num": 2}
CODE_RE = re.compile(r"\{[^}]*\}")
CODE_ONLY = re.compile(r"\{[^}]*\}|\s")


def cells(raw):
    """(width in cells, ends with {nobreak}) of an encoded string (un-swapped, no NUL)."""
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


def raw_of(text, english):
    b = (rebuild.encode_en if english else rebuild.encode)(text)
    return b.translate(script.SWAP)[:-1]


def unsupported(text):
    """Characters that are probably there by accident and would be drawn as
    full-width cells: typographic quotes and dashes, accented letters and the
    like (machine translation produces them). Deliberate full-width marks
    (: / ( ) ♪ ♥ ○ ...) are not reported."""
    t = CODE_RE.sub("", text)
    return sorted({ch for ch in t if not font_en.is_supported(ch) and ch != "\n" and
                   (0x2000 <= ord(ch) < 0x2070 or (0x80 <= ord(ch) < 0x250 and ch.isalpha()) or ch in "\t`|<>")})


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, where, msg):
        self.items.append({"level": level, "where": where, "msg": msg})

    def count(self, level):
        return sum(i["level"] == level for i in self.items)


def check_line(rep, where, ja, en):
    try:
        raw_of(en, True)
    except (ValueError, UnicodeEncodeError) as e:
        rep.add("ERROR", where, "can't encode: %s" % e)
        return False
    if "{nobreak}" in en and not en.endswith("{nobreak}"):
        rep.add("WARN", where, "{nobreak} is not at the end of the line")
    cj = collections.Counter(c for c in CODE_RE.findall(ja) if c != "{nobreak}")
    ce = collections.Counter(c for c in CODE_RE.findall(en) if c != "{nobreak}")
    if cj - ce:
        rep.add("WARN", where, "code(s) of the Japanese missing: %s" % " ".join(sorted((cj - ce).elements())))
    if ce - cj:
        rep.add("WARN", where, "code(s) not in the Japanese: %s" % " ".join(sorted((ce - cj).elements())))
    bad = unsupported(en)
    if bad:
        rep.add("WARN", where, "not in the English font (drawn full width): %s" % " ".join(bad))
    return True


def check_scene(rep, wb, room=None, names=None):
    key = wb["key"]
    total = done = 0
    grow = 0
    names = names or {}
    for m in wb["messages"]:
        sp = m.get("speaker")
        if sp:
            total += 1
            # an empty label is filled from _names.json by the builder; a label
            # that is only codes ({name1}) needs no English at all
            en = sp["en"] or names.get(sp["ja"]) or ""
            sp_at = sp["at"] if sp.get("at") is not None else (m["lines"][0]["at"] if m["lines"] else 0)
            if not en and sp["ja"] and not CODE_ONLY.sub("", sp["ja"]):
                done += 1
            elif en:
                done += 1
                if check_line(rep, "%s/%s" % (key, sp_at), sp["ja"], en):
                    w, _ = cells(raw_of(en, True))
                    if w > LABEL_CELLS:
                        rep.add("WARN", "%s/%s" % (key, sp_at),
                                "speaker label is %d cells (fits %d, 6 letters)" % (w, LABEL_CELLS))
                    grow += len(raw_of(en, True)) - len(raw_of(sp["ja"], False))
        rows, row, width, touched, ok = 0, [], 0, False, True
        nrows_ja, wja, any_en = 0, 0, False
        for l in m["lines"]:
            total += 1
            text, eng = (l["en"], True) if l["en"] else (l["ja"], False)
            if l["en"]:
                done += 1
                ok = check_line(rep, "%s/%s" % (key, l["at"]), l["ja"], l["en"]) and ok
                touched = True
            try:
                raw = raw_of(text, eng)
            except (ValueError, UnicodeEncodeError):
                raw = raw_of(l["ja"], False)
            if l["en"]:
                try:
                    grow += len(raw) - len(raw_of(l["ja"], False))
                except (ValueError, UnicodeEncodeError):
                    pass
            n, cont = cells(raw)
            width += n
            any_en = any_en or bool(l["en"])
            try:
                wja += cells(raw_of(l["ja"], False))[0]
            except (ValueError, UnicodeEncodeError):
                pass
            row.append(l["at"])
            if not cont:
                extra = max(0, -(-width // ROW_CELLS) - 1)
                rows += 1 + extra
                nrows_ja += 1 + max(0, -(-wja // ROW_CELLS) - 1)
                wja = 0
                if touched and width > ROW_CELLS:
                    rep.add("WARN", "%s/%s" % (key, "+".join(map(str, row))),
                            "row is %d cells (holds %d): the game wraps it" % (width, ROW_CELLS))
                row, width, touched = [], 0, False
        if any_en and rows > max(BOX_ROWS, nrows_ja):
            rep.add("WARN", "%s/%s" % (key, m["lines"][0]["at"]),
                    "text box needs %d rows after wrapping (holds %d)" % (rows, BOX_ROWS))
    if room is not None and done:
        kind, spare = room
        if kind in ("packed", "limit") and grow > spare:
            rep.add("ERROR", key, ("grows by %d bytes but its container can't grow" % grow) if not spare
                    else "grows by %d bytes, at most %d fit" % (grow, spare))
        elif grow > spare:
            rep.add("WARN", key, "grows by %d bytes, %d spare in place (the builder may move it)" % (grow, spare))
    return total, done


def check_ui(rep, ui):
    import strpack
    for k, v in ui.items():
        if not isinstance(v, dict) or not v.get("en"):
            continue
        where = "%s (%s)" % (k, v["ja"])
        en = v["en"]
        try:
            b = uitext.encode(en, v["ja"])
        except (KeyError, UnicodeEncodeError) as e:
            rep.add("ERROR", where, "can't encode %r: %s" % (en, e))
            continue
        places = [re.fullmatch(r"[^:]+:(\w+)@([0-9a-fA-F]+)", w) for w in v.get("where", [])]
        pooled = bool(places) and not v.get("scenes") and all(m and strpack.covers(m.group(1), int(m.group(2), 16)) for m in places)
        if len(b) > v["max_bytes"] and not pooled:
            rep.add("ERROR", where, "%r takes %d bytes, at most %d fit" % (en, len(b), v["max_bytes"]))
        bad = unsupported(en.replace("{none}", ""))
        if bad:
            rep.add("WARN", where, "not in the English font (drawn full width): %s" % " ".join(bad))


def rooms(discs):
    import extract_scripts as X
    import scenes
    out = {}
    for d in discs:
        for b in scenes.scan(X.read_user_data(d)):
            out.setdefault(b.key, (b.kind, b.room))
    return out


def main(argv):
    import translations as T
    args, discs, out_json, quiet = [], [], None, False
    i = 0
    while i < len(argv):
        if argv[i] == "--disc":
            discs.append(argv[i + 1]); i += 2
        elif argv[i] == "--json":
            out_json = argv[i + 1]; i += 2
        elif argv[i] == "--quiet":
            quiet = True; i += 1
        else:
            args.append(argv[i]); i += 1
    if len(args) > 1:
        print(__doc__)
        return 2
    src = args[0] if args else T.DEFAULT
    rep = Report()
    total = done = scenes_done = 0
    per_scene = []
    file_of = {}
    workbook_dir = os.path.isdir(src) and any(
        os.path.basename(p) == T.NAMES for p in glob.glob(os.path.join(src, "*.json")))
    if workbook_dir:                              # work/... from translations.py unpack / init
        names, ui, scenes_ = {}, {}, []
        for p in sorted(glob.glob(os.path.join(src, "*.json"))):
            j = json.load(open(p, encoding="utf-8"))
            if os.path.basename(p) == T.NAMES:
                names = j
            elif os.path.basename(p) == T.UI:
                ui = j
            elif "messages" in j:
                scenes_.append((j, None))
        lp = os.path.join(src, T.LIMITS)
        limits = json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else {}
        room = {wb["key"]: ("packed" if wb["kind"] == "packed" else "limit", limits[wb["key"]])
                for wb, _ in scenes_ if wb["key"] in limits}
    else:                                         # translations/ or one file of it
        found, names, ui = T.read_dir(src)
        if os.path.isfile(src):                   # one scene file: names and menus from its folder
            top = os.path.dirname(os.path.abspath(src))
            while top != os.path.dirname(top) and not os.path.exists(os.path.join(top, T.NAMES_FILE)):
                top = os.path.dirname(top)
            p = os.path.join(top, T.NAMES_FILE)
            if os.path.exists(p) and not names:
                names = json.load(open(p, encoding="utf-8"))
        scenes_, room = [], {}
        for key, (wb, p, probs) in found.items():
            file_of[key] = os.path.relpath(p)
            for at, msg in probs:
                rep.add("ERROR", "%s/%s" % (key, at), msg)
            r = wb.pop("_room", None)
            if r is not None:
                room[key] = ("packed" if wb["kind"] == "packed" else "limit", r)
            scenes_.append((wb, p))
        scenes_.sort(key=lambda t: (t[1] or "", t[0]["key"]))
    if discs:
        room = rooms(discs)
    if ui:
        check_ui(rep, ui)
    for ja, en in names.items():
        if en and cells(raw_of(en, True))[0] > LABEL_CELLS:
            rep.add("WARN", "speaker name %s" % ja, "label %r is wider than 6 letters" % en)
    for wb, _ in scenes_:
        t, d = check_scene(rep, wb, room.get(wb["key"]), names)
        total += t; done += d
        if d:
            scenes_done += 1
        per_scene.append((wb["key"], d, t))
    if not quiet:
        last = None
        for it in rep.items:
            f = file_of.get(it["where"].split("/")[0])
            if f and f != last:
                print("\n%s" % f)
                last = f
            print("%-5s %s: %s" % (it["level"], it["where"], it["msg"]))
        if rep.items:
            print()
    print("%d errors, %d warnings; %d of %d strings translated (%.1f%%) in %d scenes"
          % (rep.count("ERROR"), rep.count("WARN"), done, total, 100.0 * done / max(1, total), scenes_done))
    if out_json:
        json.dump({"items": rep.items, "translated": done, "strings": total,
                   "scenes": [{"key": k, "done": d, "strings": t} for k, d, t in per_scene]},
                  open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 1 if rep.count("ERROR") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
