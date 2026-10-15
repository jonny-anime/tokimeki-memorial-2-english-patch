"""Extract scene-script dialogue from a Tokimeki Memorial 2 disc image to JSON.

usage: python tools/extract_scripts.py <disc.bin> <out_dir>

Output is a copy of the game's script: keep it out of version control.
"""
import json, os, re, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import script

HDR = re.compile(rb"\x38\x35\x00\x00(..)(..).{16}([\x21-\x7e][\x20-\x7e]{0,7}\x00{0,7})(?<=.{32})", re.S)


def read_user_data(path):
    """MODE2/2352 image -> concatenated 2048-byte user data of every sector."""
    out = bytearray()
    with open(path, "rb") as f:
        while True:
            blk = f.read(2352 * 4096)
            if not blk:
                break
            for k in range(len(blk) // 2352):
                out += blk[k * 2352 + 24:k * 2352 + 2072]
    return bytes(out)


def fmt_tokens(toks):
    s = []
    for kind, v in toks:
        s.append(v if kind == "text" else "{%s}" % v)
    return "".join(s)


def main(img, outdir):
    data = read_user_data(img)
    os.makedirs(outdir, exist_ok=True)
    seen, report = {}, {"ok": 0, "failed": []}
    total_msgs = total_lines = 0
    for m in HDR.finditer(data):
        off = m.start()
        code_off, nsec = struct.unpack("<HH", m.group(1) + m.group(2))
        if not (0x20 <= code_off < 0x8000 and nsec < 16):
            continue
        sid = m.group(3).rstrip(b"\0").decode("ascii")
        n = seen.get(sid, 0); seen[sid] = n + 1
        key = "%s#%d" % (sid, n)
        try:
            blk = script.messages(data, off)
        except script.ScriptError as e:
            report["failed"].append({"block": key, "sector": off // 2048, "error": str(e)})
            continue
        report["ok"] += 1
        msgs = []
        for i, mm in enumerate(blk["messages"]):
            msgs.append({
                "id": "%s/%d" % (key, i),
                "speaker": fmt_tokens(mm["speaker"]) if mm["speaker"] else None,
                "lines": [fmt_tokens(l["tokens"]) for l in mm["lines"]],
                "offsets": [l["offset"] for l in mm["lines"]],
            })
        total_msgs += len(msgs); total_lines += sum(len(x["lines"]) for x in msgs)
        if msgs:
            with open(os.path.join(outdir, key.replace("#", "_") + ".json"), "w", encoding="utf-8") as f:
                json.dump({"block": key, "sector": off // 2048, "offset_in_sector": off % 2048,
                           "end": blk.get("end"), "messages": msgs}, f, ensure_ascii=False, indent=1)
    report.update(blocks=sum(seen.values()), messages=total_msgs, lines=total_lines,
                  ids=sorted(seen.items()))
    with open(os.path.join(outdir, "_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("blocks %d  parsed %d  failed %d  messages %d  lines %d" % (
        report["blocks"], report["ok"], len(report["failed"]), total_msgs, total_lines))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
