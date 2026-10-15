"""Rebuild the English pictures in pictures/ from your own discs.

The PNGs in pictures/ are what the patch builder uses (pictures/pictures.json);
this script shows how each was made and can make them again: it reads the
original Japanese picture from the disc image, applies the edit in
tools/art/ and writes the PNG (keeping the palette of an existing PNG, else
a grey ramp; only the indices matter to the game).

usage:
  python tools/make_pictures.py --disc1 "Disc 1.bin" --disc2 "Disc 2.bin" [--check] [--only NAME ...]
--check compares with the PNGs in pictures/ instead of writing them.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_scripts as X  # noqa: E402
import pictures  # noqa: E402
from art import date_tiles, file_select, name_buttons, stat_labels, title_menu  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pictures")


def recipes(get):
    """{png name: function() -> indices}; get(disc, chunk) reads an original."""
    def stats():
        return stat_labels.apply(get(2, "966:1472"))

    def hands():
        ja = get(2, "966:1472")
        return date_tiles.apply(stat_labels.with_record(get(2, "r11403:516"), ja, stat_labels.apply(ja)))

    def title(side):
        return lambda: title_menu.apply(get(2, "728:1988"), get(2, "730:1820"))[side]

    return {
        "name_buttons.png": lambda: name_buttons.apply(get(1, "s2067:952")),
        "name_buttons_packet.png": lambda: name_buttons.apply(get(1, "73751:1416")),
        "main_stats.png": stats,
        "main_stats_hands.png": hands,
        "file_select_date.png": lambda: file_select.buttons(file_select.date_box(get(2, "968:1440")), file_select.NEW_LOAD),
        "file_select_copy.png": lambda: file_select.buttons(get(2, "967:1880"), file_select.COPY_ERASE),
        "file_select_save.png": lambda: file_select.buttons(get(2, "s966:152"), file_select.SAVE),
        "file_select_rebuild.png": lambda: file_select.buttons(get(2, "969:360"), file_select.REBUILD),
        "title_menu_left.png": title(0),
        "title_menu_right.png": title(1),
    }


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--disc1")
    ap.add_argument("--disc2")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args(argv)
    paths = {1: a.disc1, 2: a.disc2}
    data, cache = {}, {}

    def get(disc, name):
        if not paths[disc]:
            raise LookupError("needs --disc%d" % disc)
        if disc not in data:
            data[disc] = X.read_user_data(paths[disc])
        if (disc, name) not in cache:
            c = pictures._chunk_at(data[disc], name)
            cache[disc, name] = pictures.pixels(c, 64, 4)
        return cache[disc, name].copy()

    bad = 0
    for png, make in recipes(get).items():
        if a.only and png not in a.only:
            continue
        try:
            px = make()
        except LookupError as e:
            print("%-26s skipped (%s)" % (png, e))
            continue
        dst = os.path.join(OUT, png)
        if a.check:
            old = np.array(Image.open(dst)) if os.path.exists(dst) else None
            same = old is not None and old.shape == px.shape and (old == px).all()
            n = "missing" if old is None else "same" if same else "%d pixels differ" % int((old != px).sum())
            print("%-26s %s" % (png, n))
            bad += not same
            continue
        im = Image.fromarray(px.astype(np.uint8), "P")
        im.putpalette(Image.open(dst).getpalette() if os.path.exists(dst)
                      else [v * 17 for v in range(16) for _ in range(3)])
        im.save(dst)
        print("%-26s written" % png)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
