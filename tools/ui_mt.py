"""Machine translation for entries of the menu file, through tools/mt.py.

tools/mt.py works on scene workbooks; the menu and system strings
(<workbook_dir>/_ui.json) are normally filled in by hand. This turns a
selection of them into small workbooks mt.py can run, and copies the result
back:

    py tools/ui_mt.py export <workbook_dir> <out_dir> --where TEXT [--all]
        one workbook per menu entry whose "where" contains TEXT (a module
        name such as GRAD or OV5) and whose English is empty (--all: every
        such entry). Each is a "packed" scene of one line, so mt.py holds
        the English to the entry's own size (1 letter = 1 byte, a Japanese
        character = 2) and sends lines that are too long back to the model.
    py tools/mt.py run <out_dir> --run NAME --models argon --all
    py tools/ui_mt.py import work/mt/NAME/<model> <workbook_dir> [--overwrite]
        the English into <workbook_dir>/_ui.json (only empty entries unless
        --overwrite). Then: check_translations.py, translations.py pack.

The entries go to the model in the order of their addresses, small ones
together in one request, with no speaker and no scene context.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import translations as T  # noqa: E402


def _addr(v, text):
    for w in v.get("where", []):
        if text in w:
            m = re.search(r"@([0-9a-fA-F]+)$", w)
            return (w.split("@")[0], int(m.group(1), 16) if m else 0)
    return None


def export(src, out, text, all_):
    ui = T.load_json(os.path.join(src, T.UI))
    picked = []
    for k, v in ui.items():
        a = _addr(v, text)
        if a and (all_ or not v.get("en")) and re.fullmatch(r"ui-[0-9a-f]{10}", k):
            picked.append((a, k, v))
    picked.sort()
    os.makedirs(out, exist_ok=True)
    tag = re.sub(r"[^A-Za-z0-9]", "", text).upper() or "UI"
    for n, (a, k, v) in enumerate(picked):
        wb = {"scene": "UI_%s_%03d" % (tag, n + 1), "key": "UI_%s_%03d-%s" % (tag, n + 1, k[3:]),
              "kind": "packed", "found": {},
              "messages": [{"speaker": None,
                            "lines": [{"at": int(k[3:], 16), "ja": v["ja"], "en": v.get("en", "")}]}]}
        T.dump_json(os.path.join(out, wb["key"] + ".json"), wb)
    print("%d menu entries with %r in \"where\" written to %s" % (len(picked), text, out))
    if picked:
        print("next:  py tools/mt.py run \"%s\" --run NAME --models argon --all" % out)


def import_(src, dst, overwrite):
    up = os.path.join(dst, T.UI)
    ui = T.load_json(up)
    n = skipped = 0
    for p in sorted(glob.glob(os.path.join(src, "UI_*.json"))):
        wb = T.load_json(p)
        for m in wb.get("messages", []):
            for l in m["lines"]:
                k = "ui-%010x" % l["at"]
                if not l.get("en") or k not in ui:
                    continue
                if ui[k].get("en") and not overwrite:
                    skipped += 1
                    continue
                ui[k]["en"] = l["en"]
                n += 1
    T.dump_json(up, ui)
    print("%d entries written into %s%s" % (n, up, " (%d already had English: --overwrite replaces them)" % skipped
                                             if skipped else ""))
    print("next:  py tools/check_translations.py \"%s\"   then   py tools/translations.py pack \"%s\"" % (dst, dst))


def main(a):
    flags = {x for x in a if x.startswith("--")}
    if len(a) >= 3 and a[0] == "export" and "--where" in a:
        text = a[a.index("--where") + 1]
        export(a[1], a[2], text, "--all" in flags)
    elif len(a) >= 3 and a[0] == "import":
        import_(a[1], a[2], "--overwrite" in flags)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
