"""The translation files: translations/ (the source, in the repo) and
workbooks (one file per scene, for the tools that need them).

translations/ (edit these: "en" only)
-------------------------------------
    translations/<character>/disc<N>.json   scenes where that girl talks most,
                                            by the first disc they are on
    translations/others/disc<N>.json        scenes no single girl leads
    translations/childhood.json             the childhood prologue (Disc 1)
    translations/phone_calls.json           phone calls
    translations/endings.json               graduation-day endings
    translations/misc.json                  dates, exams, other system scenes
    translations/menus.json                 menus, system text, place names
    translations/speaker_names.json         speaker labels ({"陽ノ下": "Hikari"})

A scene file:
    {"about": "...",
     "scenes": [
      {"key": "G014000-b6f2d9d6", "location": "...", "kind": "file", "room": 120,
       "found": {"2": [207328]},
       "messages": [
        {"at": [484, 504, 512], "speaker": "Miyuki", "speaker_ja": "寿",
         "ja": "そうなんだー……。\\n……。\\n美幸、用を思い出したから帰るね。",
         "en": "Oh, I see~…\\n…\\nMiyuki remembered an errand, so bye!"}]}]}

One message is one text box. "\\n" separates its lines: the English needs
exactly as many lines as the Japanese (one per "at"). An empty "en" keeps
the Japanese. "key" is `<scene ID>-<first 8 hex digits of the SHA-1 of the
original block>`, stable across discs; "at" are the byte offsets of the
lines in it. "room" is how many bytes the scene's English may add
(tools/limits.py; 0 for packed scenes, which can't grow). "speaker" is only
for reading: labels are translated in speaker_names.json. A scene can be
moved to another file: the tools only look at "key".

menus.json: {"ui-1a2b3c4d5e": {"ja": "振動設定", "en": "Vibration",
             "max_bytes": 19, "where": ["2:OV5@8013dd54"]}}
Each Japanese string appears once (ignoring full-width-space padding); the
English replaces it everywhere and must fit max_bytes (1 byte per letter, 2
per full-width character). "where" is disc:module@address, or
disc:SCENE:<scene key>@offset for a place name shown in a scene.

Workbooks (work/..., for tools/mt.py and the checker's --disc mode)
--------------------------------------------------------------------
    <dir>/<key>.json   {"scene", "key", "kind", "found", "messages": [
                         {"speaker": {"at", "ja", "en"}, "lines": [{"at", "ja", "en"}]}]}
    <dir>/_names.json  <dir>/_ui.json  <dir>/_limits.json

usage:
  python tools/translations.py unpack <workbook_dir> [--from translations]
      workbooks from translations/ (no disc needed)
  python tools/translations.py pack <workbook_dir> [--to translations]
      workbooks back into translations/ (scenes keep their file; new ones
      are placed by who talks most). `save` is the same command.
  python tools/translations.py init <workbook_dir> <disc.bin> [<disc.bin> ...] [--from translations]
      workbooks from your discs, with the English of translations/ filled in
"""
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, "translations")
NAMES = "_names.json"            # workbook names
UI = "_ui.json"
LIMITS = "_limits.json"
NAMES_FILE = "speaker_names.json"  # translations/ names
UI_FILE = "menus.json"

# speaker label -> folder; the order breaks ties
GIRLS = [("陽ノ下", "hikari"), ("水無月", "kotoko"), ("寿", "miyuki"), ("一文字", "akane"),
         ("白雪", "miho"), ("真帆", "miho"), ("赤井", "homura"), ("八重", "kaori"),
         ("佐倉", "kaede"), ("伊集院", "mei"), ("麻生", "kasumi")]
# N of {you:1N} / {char:2N} -> folder, for scenes where no girl has a label
CODES = {"1": "kasumi", "2": "hikari", "3": "kotoko", "4": "miyuki", "5": "akane", "6": "miho",
         "7": "homura", "8": "kaori", "9": "kaede", "A": "mei", "B": "miho"}
FULL_NAMES = {"hikari": "Hikari Hinomoto", "kotoko": "Kotoko Minazuki", "miyuki": "Miyuki Kotobuki",
              "akane": "Akane Ichimonji", "miho": "Miho Shirayuki (and her twin Maho)",
              "homura": "Homura Akai", "kaori": "Kaori Yae", "kaede": "Kaedeko Sakura",
              "mei": "Mei Ijuin", "kasumi": "Kasumi Asou"}
SINGLE = {"childhood.json": "The childhood prologue (Disc 1): the player and Hikari as children.",
          "phone_calls.json": "Phone calls: calling the girls, and their calls to the player.",
          "endings.json": "Graduation day: the confessions and endings.",
          "misc.json": "Dates, exams, the festival and other scenes run by the game's system modules."}
EDIT_NOTE = ("Edit only \"en\". One entry is one text box; \\n separates its lines, and the English "
             "needs as many lines as the Japanese. See the README, 'Helping improve the translation'.")


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dump_json(p, obj):
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def _j(v):
    return json.dumps(v, ensure_ascii=False)


def dump_scene_file(p, about_, scenes_):
    """A translations/ scene file, laid out for reading and for small diffs:
    one line for a scene's header, and per message one line for at/speaker,
    one for "ja" and one for "en"."""
    out = ["{", ' "about": %s,' % _j(about_), ' "scenes": [']
    for si, sc in enumerate(scenes_):
        head = ", ".join("%s: %s" % (_j(k), _j(v)) for k, v in sc.items() if k != "messages")
        out.append('  {%s,' % head)
        out.append('   "messages": [')
        msgs = sc["messages"]
        for mi, m in enumerate(msgs):
            first = ", ".join("%s: %s" % (_j(k), _j(m[k])) for k in ("at", "speaker", "speaker_ja") if k in m)
            rest = ["%s: %s" % (_j(k), _j(m[k])) for k in ("ja", "en") if k in m]
            body = [first] + rest
            out.append("    {" + (",\n     ".join(body)) + "}" + ("," if mi < len(msgs) - 1 else ""))
        out.append("   ]}" + ("," if si < len(scenes_) - 1 else ""))
    out += [" ]", "}", ""]
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out))


def dump_ui_file(p, ui):
    out = ["{"]
    items = list(ui.items())
    for i, (k, v) in enumerate(items):
        out.append(" %s: {%s}%s" % (_j(k), ", ".join("%s: %s" % (_j(a), _j(b)) for a, b in v.items()),
                                     "," if i < len(items) - 1 else ""))
    out += ["}", ""]
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out))


def json_files(d):
    """Every .json under d (or d itself if it is a file)."""
    if os.path.isfile(d):
        return [d]
    return sorted(glob.glob(os.path.join(d, "**", "*.json"), recursive=True))


def strings(wb):
    """Every string entry of a workbook."""
    for m in wb["messages"]:
        if m["speaker"]:
            yield m["speaker"]
        yield from m["lines"]


# --- translations/ <-> workbooks ---------------------------------------------

def scene_to_workbook(sc):
    """A scene of a translations/ file as a workbook. Also returns problems
    with its messages ([(at, text)]): line counts that don't match."""
    msgs, probs = [], []
    for m in sc["messages"]:
        label = m.get("speaker_ja", m.get("speaker"))
        sp = {"at": None, "ja": label, "en": ""} if label else None
        ats = m.get("at", [])
        ja = m.get("ja", "").split("\n") if ats else []
        en = m.get("en", "")
        en_lines = en.split("\n") if en else [""] * len(ats)
        if len(ja) != len(ats):
            probs.append((ats[0] if ats else "?", "the Japanese has %d lines but there are %d \"at\" offsets: "
                          "don't edit \"ja\" or \"at\"" % (len(ja), len(ats))))
            ja = (ja + [""] * len(ats))[:len(ats)]
        if en and len(en_lines) != len(ats):
            probs.append((ats[0], "the English has %d line(s), the Japanese %d: keep one \\n-separated "
                          "line per Japanese line" % (len(en_lines), len(ats))))
            en_lines = [""] * len(ats)                 # keep the Japanese
        elif en and not all(l.strip() for l in en_lines):
            probs.append((ats[0], "line %d of the English is empty (the Japanese would show there)"
                          % (1 + [bool(l.strip()) for l in en_lines].index(False))))
        msgs.append({"speaker": sp, "lines": [{"at": a, "ja": j, "en": e}
                                              for a, j, e in zip(ats, ja, en_lines)]})
    wb = {"scene": sc["key"].rsplit("-", 1)[0], "key": sc["key"], "kind": sc.get("kind", "file"),
          "found": sc.get("found", {}), "messages": msgs}
    if sc.get("location"):
        wb["location"] = sc["location"]
    return wb, probs


def workbook_to_scene(wb, names, location=None, room=None):
    out = {"key": wb["key"]}
    if location:
        out["location"] = location
    out["kind"] = wb["kind"]
    if room is not None:
        out["room"] = room
    out["found"] = wb["found"]
    msgs = []
    for m in wb["messages"]:
        e = {"at": [l["at"] for l in m["lines"]]}
        sp = m.get("speaker")
        if sp:
            e["speaker"] = sp["en"] or names.get(sp["ja"]) or sp["ja"]
            if e["speaker"] != sp["ja"]:
                e["speaker_ja"] = sp["ja"]
        if m["lines"]:
            e["ja"] = "\n".join(l["ja"] for l in m["lines"])
            en = [l["en"] for l in m["lines"]]
            e["en"] = "\n".join(en) if any(en) else ""
        msgs.append(e)
    out["messages"] = msgs
    return out


def read_dir(src):
    """Everything in a translations/ directory (or one file of it):
    ({key: (workbook, file, problems)}, names, ui)."""
    scenes_, names, ui = {}, {}, {}
    for p in json_files(src):
        j = load_json(p)
        base = os.path.basename(p)
        if base == NAMES_FILE:
            names.update(j)
        elif base == UI_FILE:
            ui.update(j)
        elif isinstance(j, dict) and "scenes" in j:
            for sc in j["scenes"]:
                wb, probs = scene_to_workbook(sc)
                wb["_room"] = sc.get("room")
                scenes_[sc["key"]] = (wb, p, probs)
    return scenes_, names, ui


def main_folder(wb):
    """Where a new scene goes: translations/<folder>/disc<N>.json or a single file."""
    sid = wb["scene"]
    if sid.startswith("YG"):
        return "childhood.json"
    if sid.startswith("G_TEL"):
        return "phone_calls.json"
    if sid.startswith("G_END"):
        return "endings.json"
    if not re.match(r"G\d", sid):
        return "misc.json"
    by_label = dict(GIRLS)
    lines = collections.Counter()
    for m in wb["messages"]:
        sp = m.get("speaker")
        if sp and sp["ja"] in by_label:
            lines[by_label[sp["ja"]]] += max(1, len(m["lines"]))
    if not lines:
        for m in wb["messages"]:
            for l in m["lines"]:
                for n in re.findall(r"\{(?:char:2|you:1)([0-9A-F])\}", l["ja"]):
                    if n in CODES:
                        lines[CODES[n]] += 1
    order = [f for _, f in GIRLS]
    folder = max(lines, key=lambda f: (lines[f], -order.index(f))) if lines else "others"
    disc = min(int(d) for d in wb["found"]) if wb["found"] else 1
    return "%s/disc%d.json" % (folder, disc)


def about(rel):
    if rel in SINGLE:
        return SINGLE[rel] + " " + EDIT_NOTE
    folder, disc = rel.split("/")
    disc = disc[4:-5]
    if folder == "others":
        what = "Scenes no single girl leads (the player with his friends, teachers, narration)"
    else:
        what = "Scenes where %s talks most" % FULL_NAMES[folder]
    return "%s, first found on Disc %s (a scene on several discs is listed under the first). %s" % (
        what, disc, EDIT_NOTE)


def ui_for_repo(ui):
    """menus.json entries: ja and en first; a place name's long list of scenes
    becomes a count (each scene's "location" shows it)."""
    out = {}
    for k, v in ui.items():
        e = {"ja": v["ja"], "en": v.get("en", ""), "max_bytes": v["max_bytes"]}
        where = [w for w in v.get("where", []) if ":SCENE:" not in w]
        n = len(v.get("where", [])) - len(where) + v.get("scenes", 0)
        e["where"] = where
        if n:
            e["scenes"] = n
        out[k] = e
    return out


def scene_places(ui):
    places = collections.defaultdict(list)
    for v in ui.values():
        for w in v.get("where", []):
            m = re.search(r"SCENE:([^@]+)@", w)
            if m:
                t = v.get("en") or v["ja"]
                if t not in places[m.group(1)]:
                    places[m.group(1)].append(t)
    return places


def pack(src, dst):
    """Workbooks -> translations/."""
    names = load_json(os.path.join(src, NAMES)) if os.path.exists(os.path.join(src, NAMES)) else {}
    ui = load_json(os.path.join(src, UI)) if os.path.exists(os.path.join(src, UI)) else {}
    lp = os.path.join(src, LIMITS)
    limits = load_json(lp) if os.path.exists(lp) else {}
    old, _, _ = read_dir(dst) if os.path.isdir(dst) else ({}, {}, {})
    places = scene_places(ui)
    files = collections.defaultdict(list)
    n = 0
    for p in sorted(glob.glob(os.path.join(src, "*.json"))):
        if os.path.basename(p).startswith("_"):
            continue
        wb = load_json(p)
        if "messages" not in wb:
            continue
        key = wb["key"]
        if key in old:
            rel = os.path.relpath(old[key][1], dst).replace(os.sep, "/")
            room = limits.get(key, old[key][0].get("_room"))
        else:
            rel = main_folder(wb)
            room = limits.get(key)
        loc = wb.get("location") or " / ".join(places.get(key, [])) or None
        files[rel].append(workbook_to_scene(wb, names, loc, room))
        n += 1
    written = set()
    for rel, scs in sorted(files.items()):
        scs.sort(key=lambda s: s["key"])
        dump_scene_file(os.path.join(dst, rel), about(rel), scs)
        written.add(os.path.normpath(os.path.join(dst, rel)))
    dump_json(os.path.join(dst, NAMES_FILE), names)
    dump_ui_file(os.path.join(dst, UI_FILE), ui_for_repo(ui))
    written |= {os.path.normpath(os.path.join(dst, f)) for f in (NAMES_FILE, UI_FILE)}
    stale = [p for p in json_files(dst) if os.path.normpath(p) not in written]
    print("packed %d scenes into %d files in %s" % (n, len(files), dst))
    if stale:
        print("%d other .json file(s) in %s are not translation files any more (e.g. %s): delete them"
              % (len(stale), dst, stale[0]))


def unpack(src, dst):
    """translations/ -> workbooks."""
    scenes_, names, ui = read_dir(src)
    os.makedirs(dst, exist_ok=True)
    limits = {}
    for key, (wb, p, probs) in scenes_.items():
        room = wb.pop("_room", None)
        if room is not None:
            limits[key] = room
        for prob in probs:
            print("%s %s at %s: %s" % (p, key, prob[0], prob[1]))
        dump_json(os.path.join(dst, key + ".json"), wb)
    dump_json(os.path.join(dst, NAMES), names)
    dump_json(os.path.join(dst, UI), ui)
    dump_json(os.path.join(dst, LIMITS), dict(sorted(limits.items())))
    print("%d workbooks in %s, with %s, %s and %s" % (len(scenes_), dst, NAMES, UI, LIMITS))


# --- what the builder reads --------------------------------------------------

def load(dirs, with_ui=False, problems=None):
    """{key: {at: en}} plus the names table (and the UI table if with_ui),
    from translations/ directories or files, workbook directories, or the
    older {"key", "en"} files. Later directories win. Messages whose line
    count doesn't match are skipped (listed in `problems` if given)."""
    tl, names, ui = {}, {}, {}

    def ui_en(v):
        return v["en"] if isinstance(v, dict) else v

    for d in dirs:
        for p in json_files(d):
            j = load_json(p)
            base = os.path.basename(p)
            if base in (NAMES, NAMES_FILE):
                names.update({k: v for k, v in j.items() if v})
                continue
            if base in (UI, UI_FILE):
                ui.update({k: ui_en(v) for k, v in j.items() if ui_en(v)})
                continue
            if not isinstance(j, dict):
                continue
            if "scenes" in j:
                for sc in j["scenes"]:
                    wb, probs = scene_to_workbook(sc)
                    if problems is not None:
                        problems += ["%s %s at %s: %s" % (p, sc["key"], a, t) for a, t in probs]
                    en = {str(s["at"]): s["en"] for s in strings(wb) if s.get("en") and s["at"] is not None}
                    if en:
                        tl.setdefault(sc["key"], {}).update(en)
                continue
            if "messages" in j:
                en = {str(s["at"]): s["en"] for s in strings(j) if s.get("en")}
            elif "en" in j and "key" in j:
                en = {k: v for k, v in j["en"].items() if v}
            else:
                continue
            if en:
                tl.setdefault(j["key"], {}).update(en)
    return (tl, names, ui) if with_ui else (tl, names)


# --- workbooks from the discs ------------------------------------------------

def workbook(b, disc):
    import extract_scripts as X
    msgs = []
    for m in b.messages:
        sp = None
        if m["speaker"]:
            sp = {"at": m["offset"], "ja": X.fmt_tokens(m["speaker"]), "en": ""}
        lines = [{"at": l["offset"], "ja": X.fmt_tokens(l["tokens"]), "en": ""} for l in m["lines"]]
        if lines or sp:
            msgs.append({"speaker": sp, "lines": lines})
    return {"scene": b.sid, "key": b.key, "kind": b.kind, "found": {disc: [b.off // 2048]},
            "messages": msgs}


def disc_number(path):
    m = re.search(r"Disc (\d)", os.path.basename(path))
    return m.group(1) if m else os.path.basename(path)


def init(out, discs, src_dirs):
    import extract_scripts as X
    import scenes
    import uitext
    os.makedirs(out, exist_ok=True)
    tl, names, uitl = load(src_dirs, with_ui=True)
    books, labels, ui = {}, {}, {}
    for path in discs:
        d = disc_number(path)
        data = X.read_user_data(path)
        blocks = scenes.scan(data)
        for u in uitext.scan(data, path) + uitext.scene_places(data, blocks):
            e = ui.setdefault(u.id, {"ja": u.text, "en": "", "max_bytes": u.max_bytes, "where": []})
            e["max_bytes"] = min(e["max_bytes"], u.max_bytes)
            w = "%s:%s" % (d, u.where)
            if w not in e["where"]:
                e["where"].append(w)
        for b in blocks:
            if not b.messages:
                continue
            wb = books.get(b.key)
            if wb is None:
                books[b.key] = wb = workbook(b, d)
            else:
                wb["found"].setdefault(d, [])
                if b.off // 2048 not in wb["found"][d]:
                    wb["found"][d].append(b.off // 2048)
            for m in wb["messages"]:
                if m["speaker"] and "{" not in m["speaker"]["ja"]:
                    labels[m["speaker"]["ja"]] = labels.get(m["speaker"]["ja"], 0) + 1
    n_en = 0
    for key, wb in books.items():
        p = os.path.join(out, key + ".json")
        old = {}
        if os.path.exists(p):                      # keep work in progress
            old = {str(s["at"]): s["en"] for s in strings(load_json(p)) if s["en"]}
        old.update({k: v for k, v in tl.get(key, {}).items() if k not in old})
        for s in strings(wb):
            s["en"] = old.get(str(s["at"]), "")
            n_en += bool(s["en"])
        dump_json(p, wb)
    np_ = os.path.join(out, NAMES)
    cur = load_json(np_) if os.path.exists(np_) else {}
    for k in sorted(labels, key=lambda k: -labels[k]):
        cur.setdefault(k, names.get(k, ""))
    dump_json(np_, cur)
    up = os.path.join(out, UI)
    old = load_json(up) if os.path.exists(up) else {}
    for k, e in ui.items():
        e["en"] = (old.get(k) or {}).get("en") or uitl.get(k, "")
    dump_json(up, ui)
    print("%d workbooks in %s (%d strings already translated), %d speaker labels in %s, %d menu/system strings in %s"
          % (len(books), out, n_en, len(cur), NAMES, len(ui), UI))


def main(a):
    def opt(name, default):
        if name in a:
            i = a.index(name)
            v = a[i + 1]
            del a[i:i + 2]
            return v
        return default
    if a[:1] == ["init"]:
        src = opt("--from", DEFAULT)
        init(a[1], a[2:], [src] if os.path.exists(src) else [])
    elif a[:1] in (["pack"], ["save"]):
        pack(a[1], opt("--to", DEFAULT))
    elif a[:1] == ["unpack"]:
        src = opt("--from", DEFAULT)
        unpack(src, a[1])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
