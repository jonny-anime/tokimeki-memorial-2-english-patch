"""Machine translation of the scene workbooks through LLM APIs.

    python tools/mt.py ping [--models opus,astra,argon]
    python tools/mt.py run <workbook_dir> --run NAME [--models a,b] [--scenes FILE | --all]
                           [--budget DOLLARS] [--jobs 4] [--batch 120] [--repairs 2]
                           [--fallback MODEL [--fallback-rounds 2]] [--limits FILE] [--estimate]
    python tools/mt.py apply work/mt/NAME/<model> <workbook_dir> [--overwrite]
    python tools/mt.py compare NAME            (writes work/mt/NAME/compare.html)

Setup (mt/):
  models.json   the models: provider, model id, prices, options (tools/llm.py)
  prompt.md     the translation brief every request starts with (style,
                names, codes, room) - edit it to change how lines come out
  names.json    speaker labels -> who they are, shown to the model as context
  pilot.txt     a list of scene keys for comparison runs
API keys: .env in the repository root (git-ignored): CLAUDE_KEY=...,
OPENAI_KEY=..., GEMINI_KEY=...

`run` sends each model the same requests: scenes (whole, small ones grouped
into one request of at most --batch lines) as JSON, the reply is JSON of
line id -> English. Every reply is checked with the same checks as
tools/check_translations.py (codes, characters the font lacks, 20-cell
rows, 4-row boxes, packed scenes that must not grow); messages with problems
go back to the model with the problems listed, up to --repairs times, and
the better version of each message is kept. With --fallback, what is
still wrong after that goes to a second model (e.g. --models argon
--fallback opus), with the problems listed, up to --fallback-rounds times;
the files record which messages came from it. Scene size limits
(tools/limits.py; --limits, default <workbook_dir>/_limits.json) make a
scene that would not fit on the disc go back to be shortened.

Output, per model: work/mt/NAME/<model>/<scene key>.json (the workbook with
"en" filled in; speakers are left to _names.json), log.jsonl (every request
with tokens, cost and seconds) and summary.json. Replies are cached in
work/mt/cache by their exact request, so running again (after a crash, a
stop, or with more models) only pays for what is new. --budget (optional,
off by default) is in US$ per model for this run; a model stops starting
requests when it reaches it.
Workbooks come from translations/: `translations.py unpack work/tl`; run,
then `apply` copies a model's English into them (only empty "en" unless
--overwrite) and `translations.py pack work/tl` writes translations/ again.
"""
import collections
import concurrent.futures as cf
import copy
import glob
import hashlib
import json
import os
import re
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_translations as CT  # noqa: E402
import llm  # noqa: E402

ROOT = llm.ROOT
MT = os.path.join(ROOT, "mt")
OUT = os.path.join(ROOT, "work", "mt")
CACHE = os.path.join(OUT, "cache")

CLEAN = [("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("—", "-"),
         ("–", "-"), ("　", " "), ("...", "…"), ("……", "…")]


def say(*a):
    print(*a, flush=True)


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def models_cfg():
    return {k: v for k, v in load_json(os.path.join(MT, "models.json")).items() if not k.startswith("_")}


def pick_models(arg):
    allm = models_cfg()
    names = [n for n in arg.split(",") if n] if arg else [n for n, c in allm.items() if c.get("provider") != "mock"]
    for n in names:
        if n not in allm:
            raise SystemExit("no model %r in mt/models.json (have: %s)" % (n, ", ".join(allm)))
    return [(n, allm[n]) for n in names]


def system_prompt():
    with open(os.path.join(MT, "prompt.md"), encoding="utf-8") as f:
        return f.read()


def speaker_names():
    p = os.path.join(MT, "names.json")
    return {k: v for k, v in load_json(p).items() if not k.startswith("_")} if os.path.exists(p) else {}


def clean(s):
    for a, b in CLEAN:
        s = s.replace(a, b)
    return s.rstrip()


def ja_chars(wb):
    return sum(len(CT.CODE_RE.sub("", l["ja"])) for m in wb["messages"] for l in m["lines"])


# --- requests -------------------------------------------------------------

INTRO = ("Translate the scenes below. Reply with JSON only, no other text: an object "
         "mapping each scene key to an object mapping every line id to its English.\n\n")
INTRO_FIX = ("Your translation of some messages below has problems (listed with each message, "
             "or for the whole scene). Rewrite the messages marked \"rewrite\": true so the "
             "problems go away, following the brief; the other messages are the rest of the "
             "scene as translated so far, for context. Reply with JSON only: an object mapping "
             "each scene key to an object mapping every line id of the rewritten messages to "
             "its new English.\n\n")
BEFORE = 8          # messages of context before a chunk of a long scene

CONTEXT = {"chars": {}, "by_speaker": {}, "by_code": {}, "places": {}, "limits": {}, "names": {}}


def load_context(src, limits=None):
    """Character notes (mt/characters.json), scene places (<src>/_ui.json)
    and how much each scene may grow (tools/limits.py output)."""
    CONTEXT["limits"] = load_json(limits) if limits else {}
    np_ = os.path.join(src, "_names.json")       # English speaker labels: they take room too
    CONTEXT["names"] = {k: v for k, v in load_json(np_).items() if v} if os.path.exists(np_) else {}
    p = os.path.join(MT, "characters.json")
    chars = {k: v for k, v in load_json(p).items() if not k.startswith("_")} if os.path.exists(p) else {}
    CONTEXT["chars"] = chars
    CONTEXT["by_speaker"] = {sp: k for k, c in chars.items() for sp in c.get("speakers", [])}
    CONTEXT["by_code"] = {n: k for k, c in chars.items() for n in c.get("codes", [])}
    places = collections.defaultdict(list)
    up = os.path.join(src, "_ui.json")
    if os.path.exists(up):
        for v in load_json(up).values():
            for w in v.get("where", []):
                m = re.search(r"SCENE:([^@]+)@", w)
                if m and v["ja"] not in places[m.group(1)]:
                    places[m.group(1)].append(v["ja"])
    CONTEXT["places"] = dict(places)


def characters_in(wb, idx):
    ids = []
    for i in idx:
        m = wb["messages"][i]
        sp = m.get("speaker")
        found = [CONTEXT["by_speaker"].get(sp["ja"])] if sp else []
        for l in m["lines"]:
            found += [CONTEXT["by_code"].get(n) for n in re.findall(r"\{(?:char:2|you:1)([0-9A-F])\}", l["ja"])]
        for k in found:
            if k and k not in ids:
                ids.append(k)
    return ids


def notes_text(chunks):
    ids = []
    for wb, idx in chunks:
        for k in characters_in(wb, idx):
            if k not in ids:
                ids.append(k)
    if not ids:
        return ""
    out = ["Notes on the characters in these scenes:"]
    for k in ids:
        c = CONTEXT["chars"][k]
        out.append("- %s: %s" % (c["name"], c["notes"]))
    return "\n".join(out) + "\n\n"


def speaker_of(m, names):
    sp = m.get("speaker")
    if not sp:
        return None
    ja = sp["ja"]
    return names.get(ja, ja)


def scene_head(wb, idx):
    e = {"kind": wb["kind"]}
    pl = CONTEXT["places"].get(wb["key"]) or ([wb["location"]] if wb.get("location") else None)
    if pl:
        e["location"] = (pl[0] if len(pl) == 1 else
                         " / ".join(pl) + " (the same scene is used at each of these places)")
    lim = CONTEXT["limits"].get(wb["key"])
    if wb["kind"] == "packed":
        e["note"] = ("packed scene: its English must not take more bytes than the Japanese "
                     "(about %d letters in all for these lines)" % packed_room(wb, idx))
    elif lim is not None and len(idx) == len(wb["messages"]):
        ja = packed_room(wb, idx)
        for m in wb["messages"]:                # English speaker labels use some of the room
            sp = m.get("speaker")
            if sp and CONTEXT["names"].get(sp["ja"]):
                lim -= len(CT.raw_of(CONTEXT["names"][sp["ja"]], True)) - len(CT.raw_of(sp["ja"], False))
        if lim < ja:
            e["note"] = ("tight scene: the game has room for about %d letters in all for these "
                         "lines; keep the English concise" % (ja + lim))
    return e


def before_context(wb, idx, names):
    """The Japanese of the messages just before a chunk of a long scene."""
    first = min(idx)
    if first == 0:
        return None
    out = []
    for m in wb["messages"][max(0, first - BEFORE):first]:
        if m["lines"]:
            out.append([speaker_of(m, names), " ".join(l["ja"] for l in m["lines"])])
    return out


def scene_entry(wb, idx, names):
    msgs = []
    for i in idx:
        m = wb["messages"][i]
        if not m["lines"]:
            continue
        e = {"speaker": speaker_of(m, names), "lines": [[str(l["at"]), l["ja"]] for l in m["lines"]]}
        msgs.append(e)
    e = scene_head(wb, idx)
    b = before_context(wb, idx, names)
    if b:
        e["earlier_in_scene"] = b
    e["messages"] = msgs
    return e


def packed_room(wb, idx):
    n = 0
    for i in idx:
        for l in wb["messages"][i]["lines"]:
            n += len(CT.raw_of(l["ja"], False))
    return n


def request_text(chunks, names):
    body = {"scenes": {wb["key"]: scene_entry(wb, idx, names) for wb, idx in chunks}}
    return INTRO + notes_text(chunks) + dumps(body)


def fix_text(items, names):
    """items: [(wb, [msg indices of the chunk], {msg index: [problems]}, [scene problems], en)]:
    the messages with problems are to be rewritten, the rest of the chunk is context."""
    sc = {}
    for wb, idx, probs, scene_probs, en in items:
        msgs = []
        for i in idx:
            m = wb["messages"][i]
            if not m["lines"]:
                continue
            e = {"speaker": speaker_of(m, names),
                 "lines": [[str(l["at"]), l["ja"], en.get(l["at"], "")] for l in m["lines"]]}
            if i in probs:
                e["rewrite"] = True
                e["problems"] = probs[i]
            msgs.append(e)
        e = scene_head(wb, idx)
        if scene_probs:
            e["scene_problems"] = scene_probs
        e["messages"] = msgs
        sc[wb["key"]] = e
    return INTRO_FIX + notes_text([(wb, idx) for wb, idx, _, _, _ in items]) + dumps({"fix": True, "scenes": sc})


def dumps(body):
    """JSON with one message per line: compact but easy to follow."""
    def c(x):
        return json.dumps(x, ensure_ascii=False, separators=(", ", ": "))
    out = []
    for k, sc in body["scenes"].items():
        head = ",\n  ".join("%s: %s" % (c(a), c(b)) for a, b in sc.items() if a != "messages")
        msgs = ",\n    ".join(c(m) for m in sc["messages"])
        out.append("  %s: {%s%s\"messages\": [\n    %s]}" % (c(k), head, ",\n  " if head else "", msgs))
    pre = '"fix": true, ' if body.get("fix") else ""
    return "{%s\"scenes\": {\n%s}}" % (pre, ",\n".join(out))


WIDTH_RE = re.compile(r"(\d+) cells \(holds (\d+)\)")


def parse_reply(text):
    """The JSON object(s) in a reply. Tolerates code fences, text around the
    JSON and several objects one after another (merged)."""
    t = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(t)
    except ValueError:
        pass
    dec, out, p, found = json.JSONDecoder(), {}, 0, False
    while True:
        a = t.find("{", p)
        if a < 0:
            break
        try:
            obj, p = dec.raw_decode(t, a)
        except ValueError:
            p = a + 1
            continue
        if isinstance(obj, dict):
            found = True
            for k, v in obj.items():
                if isinstance(v, dict) and isinstance(out.get(k), dict):
                    out[k].update(v)
                else:
                    out[k] = v
    if not found:
        raise ValueError("no JSON object in the reply: %r" % text[:200])
    return out


# --- checking ---------------------------------------------------------------

def check(wb, idx, en, whole):
    """({msg index: [problems]}, [scene problems]) for messages idx with English en {at: str}."""
    w = copy.deepcopy(wb)
    at_msg = {}
    probs = collections.defaultdict(list)
    for i, m in enumerate(w["messages"]):
        if m.get("speaker"):
            m["speaker"]["en"] = CONTEXT["names"].get(m["speaker"]["ja"], "")
            at_msg[m["speaker"]["at"]] = i
        for l in m["lines"]:
            at_msg[l["at"]] = i
            l["en"] = en.get(l["at"], "") if i in idx else ""
            if i in idx and not l["en"]:
                probs[i].append("line %s has no English" % l["at"])
    rep = CT.Report()
    lim = CONTEXT["limits"].get(wb["key"])
    if whole and wb["kind"] == "packed":
        room = ("packed", 0)
    elif whole and lim is not None:
        room = ("packed", lim)          # a hard limit, like packed scenes
    else:
        room = None
    CT.check_scene(rep, w, room)
    scene_probs = []
    for it in rep.items:
        key, _, ats = it["where"].partition("/")
        msg = it["msg"]
        if not ats:
            scene_probs.append(msg.replace("container", "place on the disc")
                               + " (1 letter = 1 byte, other characters 2): shorten the English")
            continue
        msg = WIDTH_RE.sub(lambda m: "about %d characters (at most %d fit)" % (2 * int(m.group(1)), 2 * int(m.group(2))), msg)
        first = int(ats.split("+")[0])
        i = at_msg.get(first)
        if i is not None and i in idx:
            probs[i].append("line%s %s: %s" % ("s" if "+" in ats else "", ats.replace("+", " + "), msg))
    return dict(probs), scene_probs


def n_issues(probs, scene_probs):
    return sum(len(v) for v in probs.values()) + len(scene_probs)


# --- one model ----------------------------------------------------------------

class ModelRun:
    def __init__(self, name, cfg, run_dir, budget, system):
        self.name, self.cfg, self.budget, self.system = name, cfg, budget, system
        self.dir = os.path.join(run_dir, name)
        os.makedirs(self.dir, exist_ok=True)
        self.lock = threading.Lock()
        self.spent = 0.0          # money spent in this run (cache hits are free)
        self.cost_all = 0.0       # what all replies cost when they were made
        self.usage = collections.Counter()
        self.requests = self.cached = self.failed = 0
        self.seconds = 0.0
        self.stopped = False
        self.en = {}              # key -> {at: English}
        self.left = {}            # key -> remaining problems
        self.repairs = 0
        self.fallback = None      # a ModelRun that repairs what this model couldn't
        self.fallback_rounds = 0
        self.fallback_fixes = 0
        self.by_fallback = {}     # key -> message indices whose English came from the fallback

    def over(self):
        with self.lock:
            if self.budget is not None and self.spent >= self.budget:
                self.stopped = True
            return self.stopped

    def cache_path(self, user):
        cfg = self.cfg
        h = hashlib.sha256(json.dumps([cfg["provider"], cfg["model"], cfg.get("extra", {}),
                                       cfg.get("max_tokens"), self.system, user],
                                      ensure_ascii=False).encode("utf-8")).hexdigest()
        return os.path.join(CACHE, h[:2], h + ".json")

    def ask_json(self, user, kind, tries=3):
        """ask() and parse the reply; a reply that isn't usable JSON, or a
        failed request, is asked again (the bad reply is dropped from the
        cache), up to `tries` times."""
        for t in range(tries):
            try:
                return parse_reply(self.ask(user, kind))
            except (llm.LLMError, ValueError) as e:
                if os.path.exists(self.cache_path(user)):
                    os.remove(self.cache_path(user))
                if t == tries - 1:
                    raise
                self.log({"kind": "retry", "error": str(e)[:300]})

    def ask(self, user, kind):
        cfg = self.cfg
        cp = self.cache_path(user)
        if os.path.exists(cp):
            c = load_json(cp)
            with self.lock:
                self.cached += 1
                self.cost_all += c["cost"]
            self.log({"kind": kind, "cached": True, "cost": 0, "orig_cost": c["cost"], "usage": c["usage"]})
            return c["text"]
        r = llm.call(cfg, self.system, user, log=lambda s: say("[%s]%s" % (self.name, s)))
        save_json(cp, {"model": cfg["model"], "text": r.text, "usage": r.usage, "cost": r.cost,
                       "seconds": r.seconds, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        with self.lock:
            self.requests += 1
            self.spent += r.cost
            self.cost_all += r.cost
            self.usage.update(r.usage)
            self.seconds += r.seconds
        self.log({"kind": kind, "cached": False, "cost": r.cost, "usage": r.usage,
                  "seconds": round(r.seconds, 1)})
        return r.text

    def log(self, rec):
        rec = dict(rec, time=time.strftime("%H:%M:%S"))
        with self.lock, open(os.path.join(self.dir, "log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def take(self, reply, chunks, only=None):
        """Merge reply JSON into self.en; returns {key: {at: en}} of what came back."""
        got = {}
        for wb, idx in chunks:
            d = reply.get(wb["key"]) if isinstance(reply, dict) else None
            if not isinstance(d, dict):
                continue
            ats = {l["at"] for i in (only[wb["key"]] if only else idx) for l in wb["messages"][i]["lines"]}
            g = got[wb["key"]] = {}
            for k, v in d.items():
                try:
                    at = int(k)
                except ValueError:
                    continue
                if at in ats and isinstance(v, str) and v.strip():
                    g[at] = clean(v)
        return got

    def batch(self, chunks, names, repairs):
        """chunks: [(workbook, [message indices], whole scene?)]"""
        if self.over():
            return "skipped (budget)"
        pairs = [(wb, idx) for wb, idx, _ in chunks]
        try:
            got = self.take(self.ask_json(request_text(pairs, names), "translate"), pairs)
        except (llm.LLMError, ValueError) as e:
            with self.lock:
                self.failed += 1
            self.log({"kind": "error", "error": str(e)[:500], "scenes": [w["key"] for w, _ in pairs]})
            return "FAILED: %s" % str(e)[:300]
        en = {wb["key"]: {**self.en.get(wb["key"], {}), **got.get(wb["key"], {})} for wb, _, _ in chunks}
        state = {wb["key"]: check(wb, set(idx), en[wb["key"]], whole) for wb, idx, whole in chunks}
        before = sum(n_issues(*s) for s in state.values())
        rounds = [(self, "repair")] * repairs
        if self.fallback:
            rounds += [(self.fallback, "fallback")] * self.fallback_rounds
        fixed_by_fb = {}
        for rnd, (asker, kind) in enumerate(rounds):
            todo = [(wb, idx, whole) for wb, idx, whole in chunks if n_issues(*state[wb["key"]])]
            if not todo or asker.over():
                if kind == "repair" and todo and self.fallback:
                    continue                             # out of budget: still let the fallback try
                break
            items, only = [], {}
            for wb, idx, whole in todo:
                probs, sp = state[wb["key"]]
                if sp:                                   # scene-level: send every message
                    probs = {i: probs.get(i, []) for i in idx if wb["messages"][i]["lines"]}
                items.append((wb, idx, probs, sp, en[wb["key"]]))
                only[wb["key"]] = sorted(probs)
            try:
                got = self.take(asker.ask_json(fix_text(items, names), kind, tries=2),
                                [(wb, idx) for wb, idx, _ in todo], only)
            except (llm.LLMError, ValueError) as e:
                self.log({"kind": "error", "error": str(e)[:500], "repair": rnd + 1, "by": asker.name})
                if kind == "repair" and self.fallback:
                    continue
                break
            with self.lock:
                if kind == "repair":
                    self.repairs += 1
                else:
                    self.fallback_fixes += 1
            for wb, idx, whole in todo:
                k = wb["key"]
                old_p, old_s = state[k]
                new_en = {**en[k], **got.get(k, {})}
                new_p, new_s = check(wb, set(idx), new_en, whole)
                if old_s:
                    # a scene-level problem (packed scene too long): take the
                    # new version as a whole if it is no worse overall
                    if n_issues(new_p, new_s) <= n_issues(old_p, old_s):
                        en[k] = new_en
                        if kind == "fallback":
                            fixed_by_fb.setdefault(k, set()).update(only[k])
                else:
                    # keep, per message, whichever version has fewer problems
                    merged = dict(en[k])
                    for i in only[k]:
                        if len(new_p.get(i, [])) <= len(old_p.get(i, [])):
                            for l in wb["messages"][i]["lines"]:
                                if l["at"] in new_en:
                                    merged[l["at"]] = new_en[l["at"]]
                            if kind == "fallback":
                                fixed_by_fb.setdefault(k, set()).add(i)
                    en[k] = merged
                state[k] = check(wb, set(idx), en[k], whole)
        after = sum(n_issues(*s) for s in state.values())
        with self.lock:
            for wb, idx, whole in chunks:
                k = wb["key"]
                self.en.setdefault(k, {}).update(en[k])
                fb = self.by_fallback.setdefault(k, set())
                fb.difference_update(idx)
                fb.update(fixed_by_fb.get(k, ()))
                p, sp = state[k]
                self.left.setdefault(k, {})
                for i in idx:
                    self.left[k].pop(i, None)
                self.left[k].update(p)
                if whole:
                    self.left[k]["scene"] = sp
                elif sp:
                    self.left[k].setdefault("scene", []).extend(sp)
        for wb, _, _ in chunks:
            self.write(wb)
        nfb = sum(len(v) for v in fixed_by_fb.values())
        return "%d issue(s)%s%s" % (after, " (%d before repair)" % before if before != after else "",
                                    ", %d message(s) by %s" % (nfb, self.fallback.cfg["model"]) if nfb else "")

    def write(self, wb):
        w = copy.deepcopy(wb)
        en = self.en.get(w["key"], {})
        for m in w["messages"]:
            for l in m["lines"]:
                l["en"] = en.get(l["at"], "")
        left = self.left.get(w["key"], {})
        w["mt"] = {"model": self.name, "problems": {str(k): v for k, v in left.items() if v}}
        fb = sorted(self.by_fallback.get(w["key"], ()))
        if fb:
            w["mt"]["fallback"] = {"model": self.fallback.cfg["model"], "messages": fb}
        save_json(os.path.join(self.dir, w["key"] + ".json"), w)


# --- commands -------------------------------------------------------------------

def plan_batches(wbs, batch, split=200):
    """[[(wb, [msg idx], whole)]]: whole scenes grouped up to `batch` lines per
    request; a scene of more than `split` lines is cut by messages."""
    out, cur, n = [], [], 0
    for wb in wbs:
        sizes = [len(m["lines"]) for m in wb["messages"]]
        total = sum(sizes)
        if total == 0:
            continue
        if total > split:
            idx, c = [], 0
            for i, s in enumerate(sizes):
                if c + s > batch and idx:
                    out.append([(wb, idx, False)])
                    idx, c = [], 0
                idx.append(i)
                c += s
            out.append([(wb, idx, False)])
            continue
        if n + total > batch and cur:
            out.append(cur)
            cur, n = [], 0
        cur.append((wb, list(range(len(wb["messages"]))), True))
        n += total
    if cur:
        out.append(cur)
    return out


def load_workbooks(src, scenes_file, all_):
    paths = {os.path.basename(p)[:-5]: p for p in glob.glob(os.path.join(src, "*.json"))
             if not os.path.basename(p).startswith("_")}
    if all_:
        keys = sorted(paths)
    else:
        if not scenes_file:
            raise SystemExit("give --scenes FILE (scene keys, one per line) or --all")
        keys = []
        for line in open(scenes_file, encoding="utf-8"):
            k = line.split("#")[0].strip()
            if k:
                keys.append(k)
        missing = [k for k in keys if k not in paths]
        if missing:
            raise SystemExit("not in %s: %s" % (src, " ".join(missing)))
    return [load_json(paths[k]) for k in keys], [load_json(p) for p in paths.values()]


def estimate(name, cfg, batches, system, names):
    sys_t = len(system) / 3.0
    t_in = t_out = 0
    for b in batches:
        user = request_text([(wb, idx) for wb, idx, _ in b], names)
        t_in += sys_t + len(user) / 1.6
        t_out += sum(ja_chars(wb) for wb, _, _ in b) * 1.0 + 12 * sum(len(wb["messages"]) for wb, _, _ in b)
    t_out *= cfg.get("est_output_factor", 1.5)       # thinking / reasoning, a guess
    c = llm.cost_of(cfg, {"input": t_in, "output": t_out})
    say("  %-8s %3d requests  ~%7.0fk in  ~%7.0fk out  ~$%.2f  (+ repairs; reasoning output is a guess)"
        % (name, len(batches), t_in / 1000, t_out / 1000, c))


def cmd_run(a):
    if not a.run:
        raise SystemExit("give --run NAME")
    wbs, all_wbs = load_workbooks(a.src, a.scenes, a.all)
    models = pick_models(a.models)
    system, names = system_prompt(), speaker_names()
    lp = a.limits or os.path.join(a.src, "_limits.json")
    load_context(a.src, lp if os.path.exists(lp) else None)
    if CONTEXT["limits"]:
        say("scene size limits from %s" % lp)
    batches = plan_batches(wbs, a.batch)
    nlines = sum(len(m["lines"]) for wb in wbs for m in wb["messages"])
    say("%d scenes, %d lines, %d Japanese characters, %d requests per model"
        % (len(wbs), nlines, sum(map(ja_chars, wbs)), len(batches)))
    if a.estimate:
        for n, c in models:
            estimate(n, c, batches, system, names)
        return 0
    run_dir = os.path.join(OUT, a.run)
    os.makedirs(run_dir, exist_ok=True)
    save_json(os.path.join(run_dir, "run.json"), {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"), "src": os.path.abspath(a.src),
        "scenes": [wb["key"] for wb in wbs], "lines": nlines, "ja_chars": sum(map(ja_chars, wbs)),
        "all_ja_chars": sum(map(ja_chars, all_wbs)), "all_scenes": len(all_wbs),
        "prompt_sha": hashlib.sha256(system.encode("utf-8")).hexdigest()[:12],
        "models": {n: c for n, c in models}})
    runs = [ModelRun(n, c, run_dir, a.budget, system) for n, c in models]
    if a.fallback:
        (fname, fcfg), = pick_models(a.fallback)
        for r in runs:
            if fname != r.name:
                r.fallback = ModelRun("fallback-" + fname, fcfg, r.dir, a.budget, system)
                r.fallback_rounds = a.fallback_rounds
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=a.jobs * len(runs)) as ex:
        futs = {}
        for b_i, b in enumerate(batches):
            for r in runs:
                futs[ex.submit(r.batch, b, names, a.repairs)] = (r, b_i, b)
        for f in cf.as_completed(futs):
            r, b_i, b = futs[f]
            try:
                res = f.result()
            except Exception as e:          # a bug, not an API problem: report and go on
                res = "CRASHED: %r" % e
            say("[%s] request %d/%d (%s): %s  -  $%.3f so far"
                % (r.name, b_i + 1, len(batches), ", ".join(wb["scene"] for wb, _, _ in b)[:60], res, r.spent))
    say("")
    for r in runs:
        s = summarize(r, wbs, run_dir)
        say("%-8s %5d/%d lines  %3d problems left  %3d requests (+%d cached, %d failed, %d repairs)  "
            "$%.3f now ($%.3f all replies)  ~$%.0f for all %d scenes%s"
            % (r.name, s["lines_done"], nlines, s["problems_left"], r.requests, r.cached, r.failed,
               r.repairs, r.spent, r.cost_all, s["projected_all"], len(all_wbs),
               "  STOPPED AT BUDGET" if r.stopped else ""))
        if r.fallback:
            f = r.fallback
            say("         fallback %s: %d message(s) taken, %d requests (+%d cached), $%.3f now ($%.3f all replies)"
                % (f.cfg["model"], s["fallback"]["messages"], f.requests, f.cached, f.spent, f.cost_all))
    say("\n%.0fs. Results in %s; compare with: python tools/mt.py compare %s"
        % (time.time() - t0, run_dir, a.run))
    return 0


def summarize(r, wbs, run_dir):
    done = sum(1 for wb in wbs for m in wb["messages"] for l in m["lines"] if r.en.get(wb["key"], {}).get(l["at"]))
    left = sum(len(v) for d in r.left.values() for v in d.values())
    jc = sum(ja_chars(wb) for wb in wbs if r.en.get(wb["key"]))
    run = load_json(os.path.join(run_dir, "run.json"))
    per = r.cost_all / jc if jc else 0
    s = {"model": r.name, "model_id": r.cfg["model"], "lines": sum(len(m["lines"]) for wb in wbs for m in wb["messages"]),
         "lines_done": done, "problems_left": left, "requests": r.requests, "cached": r.cached,
         "failed": r.failed, "repairs": r.repairs, "spent": round(r.spent, 4), "cost_all": round(r.cost_all, 4),
         "usage": dict(r.usage), "api_seconds": round(r.seconds, 1), "ja_chars_done": jc,
         "cost_per_1000_ja_chars": round(per * 1000, 4), "projected_all": round(per * run["all_ja_chars"], 2),
         "stopped_at_budget": r.stopped}
    if r.fallback:
        f = r.fallback
        s["fallback"] = {"model": f.cfg["model"], "messages": sum(len(v) for v in r.by_fallback.values()),
                         "requests": f.requests, "cached": f.cached, "spent": round(f.spent, 4),
                         "cost_all": round(f.cost_all, 4), "usage": dict(f.usage)}
        s["cost_all_with_fallback"] = round(r.cost_all + f.cost_all, 4)
        s["projected_all"] = round((r.cost_all + f.cost_all) / jc * run["all_ja_chars"], 2) if jc else 0
    save_json(os.path.join(r.dir, "summary.json"), s)
    return s


def cmd_ping(a):
    for n, c in pick_models(a.models):
        try:
            r = llm.call(c, "You are a test endpoint.", 'Reply with exactly this JSON: {"ok": true}', tries=2)
            say("%-8s %-24s ok  %.1fs  %s tokens  $%.5f  reply: %s"
                % (n, c["model"], r.seconds, dict(r.usage), r.cost, r.text.strip()[:60]))
        except llm.LLMError as e:
            say("%-8s %-24s FAILED: %s" % (n, c["model"], e))
    return 0


def cmd_apply(a):
    n = files = 0
    for p in sorted(glob.glob(os.path.join(a.src, "*.json"))):
        if os.path.basename(p) in ("summary.json",):
            continue
        mt = load_json(p)
        if "messages" not in mt:
            continue
        dst = os.path.join(a.dst, os.path.basename(p))
        if not os.path.exists(dst):
            say("no workbook %s, skipped" % dst)
            continue
        wb = load_json(dst)
        en = {l["at"]: l["en"] for m in mt["messages"] for l in m["lines"] if l["en"]}
        k = 0
        for m in wb["messages"]:
            for l in m["lines"]:
                if l["at"] in en and (a.overwrite or not l["en"]):
                    l["en"] = en[l["at"]]
                    k += 1
        if k:
            save_json(dst, wb)
            n += k
            files += 1
    say("%d lines written into %d workbooks in %s" % (n, files, a.dst))
    return 0


def cmd_compare(a):
    import mt_compare
    return mt_compare.main(os.path.join(OUT, a.run))


def main(argv):
    import argparse
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ping")
    p.add_argument("--models")
    p = sub.add_parser("run")
    p.add_argument("src")
    p.add_argument("--run")
    p.add_argument("--models")
    p.add_argument("--scenes")
    p.add_argument("--all", action="store_true")
    p.add_argument("--budget", type=float, default=None)
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--batch", type=int, default=120)
    p.add_argument("--repairs", type=int, default=2)
    p.add_argument("--fallback")
    p.add_argument("--limits")
    p.add_argument("--fallback-rounds", type=int, default=2)
    p.add_argument("--estimate", action="store_true")
    p = sub.add_parser("apply")
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--overwrite", action="store_true")
    p = sub.add_parser("compare")
    p.add_argument("run")
    a = ap.parse_args(argv)
    return {"ping": cmd_ping, "run": cmd_run, "apply": cmd_apply, "compare": cmd_compare}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
