"""Patch Tokimeki Memorial 2 (PS1, Japan, Rev 1) into English.

    py patch.py "path/to/your/game folder"
    py patch.py "path/to/Disc 1.cue" "path/to/Disc 2.cue" ...

Give the folder that holds your .cue/.bin files (or the files themselves).
Every disc found is patched into a new folder next to them, named after the
game with " [English]" added; your original files are never changed. The
new folder also gets an .m3u playlist: open it in DuckStation to play all
five discs with disc switching.

Options:
  -o FOLDER    write the patched discs to FOLDER instead
  -f           replace the output folder's discs if they already exist
  --tl DIR     use these translations instead of translations/ (repeatable)
"""
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def cue_files(cue):
    """The files a .cue refers to, in order."""
    out = []
    for line in open(cue, encoding="utf-8", errors="replace"):
        m = re.match(r'\s*FILE\s+"?(.*?)"?\s+(BINARY|MOTOROLA|WAVE|MP3|AIFF)\s*$', line, re.I)
        if m:
            out.append(os.path.join(os.path.dirname(cue), m.group(1)))
    return out


def find_discs(paths):
    """[(disc number, data .bin, .cue or None)] for the given folders/files."""
    import glyphpatch
    found, seen = [], set()
    cands = []
    for p in paths:
        if os.path.isdir(p):
            cands += sorted(os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith(".cue"))
            cues = {os.path.normcase(f) for c in cands for f in cue_files(c)}
            cands += sorted(os.path.join(p, f) for f in os.listdir(p)
                            if f.lower().endswith(".bin") and os.path.normcase(os.path.join(p, f)) not in cues)
        else:
            cands.append(p)
    for p in cands:
        cue = p if p.lower().endswith(".cue") else None
        bins = cue_files(p) if cue else [p]
        if not bins or not os.path.exists(bins[0]):
            print("skipped %s: its .bin isn't there" % p)
            continue
        b = os.path.abspath(bins[0])
        if b in seen:
            continue
        seen.add(b)
        try:
            with open(b, "rb") as f:
                name, _, _ = glyphpatch.find_exe(f)
        except Exception:
            print("skipped %s: not a Tokimeki Memorial 2 disc image (BIN, MODE2/2352)" % p)
            continue
        disc = int(name[-1]) - 4                  # SLPM_863.55 .. .59
        found.append((disc, b, os.path.abspath(cue) if cue else None))
    return sorted(found)


def main(argv):
    import build_patch
    out, force, tl, paths = None, False, [], []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "-o":
            out = argv[i + 1]; i += 2
        elif a == "-f":
            force = True; i += 1
        elif a == "--tl":
            tl.append(argv[i + 1]); i += 2
        elif a in ("-h", "--help"):
            print(__doc__); return 0
        else:
            paths.append(a); i += 1
    if not paths:
        print(__doc__)
        return 2
    discs = find_discs(paths)
    if not discs:
        print("no Tokimeki Memorial 2 disc images found in %s" % ", ".join(paths))
        return 1
    nums = [d for d, _, _ in discs]
    dup = sorted({n for n in nums if nums.count(n) > 1})
    if dup:
        print("Disc %s is there more than once: give the files you want" % ", ".join(map(str, dup)))
        return 1
    first = discs[0][1]
    game = re.sub(r"\s*\(Disc \d\)", "", os.path.splitext(os.path.basename(first))[0]) or "Tokimeki Memorial 2"
    out = out or os.path.join(os.path.dirname(first), game + " [English]")
    os.makedirs(out, exist_ok=True)
    print("patching disc(s) %s into %s\n" % (", ".join(map(str, nums)), out))
    failed, cues = [], []
    for disc, b, cue in discs:
        dst = os.path.join(out, os.path.basename(b))
        if os.path.exists(dst) and not force:
            print("Disc %d: %s exists; add -f to replace it" % (disc, dst))
            failed.append(disc)
            continue
        print("=== Disc %d ===" % disc)
        args = [b, dst] + sum((["--tl", t] for t in tl), [])
        rc = build_patch.main(args)
        if cue:                                    # the builder writes <dst>.cue from <bin>.cue;
            extra = cue_files(cue)[1:]             # copy any other tracks
            for e in extra:
                shutil.copyfile(e, os.path.join(out, os.path.basename(e)))
            want = os.path.join(out, os.path.basename(cue))
            made = os.path.splitext(dst)[0] + ".cue"
            if os.path.exists(made) and os.path.normcase(made) != os.path.normcase(want):
                shutil.move(made, want)
        c = os.path.join(out, os.path.basename(cue) if cue else os.path.splitext(os.path.basename(b))[0] + ".cue")
        if not os.path.exists(c):
            with open(c, "w") as f:
                f.write('FILE "%s" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n' % os.path.basename(dst))
        cues.append(os.path.basename(c))
        if rc:
            failed.append(disc)
        print()
    if len(cues) > 1:
        with open(os.path.join(out, game + ".m3u"), "w") as f:
            f.write("\n".join(cues) + "\n")
    if failed:
        print("Done, with problems on disc(s) %s (see above). The rest is in %s"
              % (", ".join(map(str, failed)), out))
        return 1
    print("Done. Open %s in your emulator." % (
        os.path.join(out, game + ".m3u") if len(cues) > 1 else os.path.join(out, cues[0])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
