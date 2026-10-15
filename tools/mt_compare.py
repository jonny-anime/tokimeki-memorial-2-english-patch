"""Blind side-by-side page for a machine-translation run (tools/mt.py).

    python tools/mt_compare.py work/mt/NAME      (or: python tools/mt.py compare NAME)

Writes work/mt/NAME/compare.html: every scene of the run, message by
message, the Japanese next to each model's English. The models are shown as
A, B, C ... in a random order; pick the best version of each scene (saved in
your browser), then press "Reveal" to see which model is which, with the
tally, the problems the checker still finds, and cost. The page holds the
game's Japanese text: keep it to yourself (work/ is git-ignored).
"""
import glob
import html
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_translations as CT  # noqa: E402


def width(en):
    try:
        return 2 * CT.cells(CT.raw_of(en, True))[0]
    except (ValueError, UnicodeEncodeError):
        return None


def main(run_dir):
    run = json.load(open(os.path.join(run_dir, "run.json"), encoding="utf-8"))
    models = [m for m in run["models"] if os.path.isdir(os.path.join(run_dir, m))]
    names = {}
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(run_dir)))), "mt", "names.json")
    if os.path.exists(p):
        names = json.load(open(p, encoding="utf-8"))
    res, summ = {}, {}
    for m in models:
        d = os.path.join(run_dir, m)
        res[m] = {}
        for f in glob.glob(os.path.join(d, "*.json")):
            j = json.load(open(f, encoding="utf-8"))
            if "messages" in j:
                res[m][j["key"]] = j
        sp = os.path.join(d, "summary.json")
        summ[m] = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    rnd = random.Random()
    order = models[:]
    rnd.shuffle(order)
    letters = {m: chr(65 + i) for i, m in enumerate(order)}

    scenes = []
    for key in run["scenes"]:
        base = next((res[m][key] for m in order if key in res[m]), None)
        if base is None:
            continue
        msgs = []
        for i, msg in enumerate(base["messages"]):
            if not msg["lines"]:
                continue
            sp = msg.get("speaker")
            row = {"speaker": (names.get(sp["ja"], sp["ja"]) if sp else ""),
                   "ja": [l["ja"] for l in msg["lines"]], "en": {}}
            for m in order:
                wb = res[m].get(key)
                if not wb:
                    continue
                probs = (wb.get("mt") or {}).get("problems", {}).get(str(i), [])
                fb = (wb.get("mt") or {}).get("fallback") or {}
                row["en"][letters[m]] = {"lines": [[l["en"], width(l["en"]) if l["en"] else None]
                                                   for l in wb["messages"][i]["lines"]],
                                         "problems": probs,
                                         "fallback": i in fb.get("messages", [])}
            msgs.append(row)
        scene_probs = {letters[m]: (res[m][key].get("mt") or {}).get("problems", {}).get("scene", [])
                       for m in order if key in res[m]}
        scenes.append({"key": key, "kind": base["kind"], "messages": msgs, "scene_problems": scene_probs})

    data = {"run": os.path.basename(os.path.abspath(run_dir)), "time": run["time"],
            "letters": [letters[m] for m in order],
            "reveal": {letters[m]: {"name": m, "model": run["models"][m]["model"], "summary": summ[m]} for m in order},
            "all_ja_chars": run.get("all_ja_chars"), "all_scenes": run.get("all_scenes"),
            "scenes": scenes}
    out = os.path.join(run_dir, "compare.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(PAGE.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))
                .replace("{{TITLE}}", html.escape("MT compare: " + data["run"])))
    print("wrote %s (%d scenes, models as %s)" % (out, len(scenes), ", ".join(data["letters"])))
    return 0


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{--bg:#f7f6f3;--panel:#fff;--ink:#1d1d1f;--mute:#6b6b70;--line:#e4e2dc;--accent:#c2410c;--warn:#b91c1c;--warnbg:#fdecec;--pick:#fff4e8;--code:#eef0f6;--codeink:#3b4a7a}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--panel:#1d1d21;--ink:#ececee;--mute:#9a9aa2;--line:#2e2e34;--accent:#fb923c;--warn:#f87171;--warnbg:#3a1d1d;--pick:#2e2216;--code:#262a38;--codeink:#aab6e8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:17px;margin:0;font-weight:650}.meta{color:var(--mute);font-size:13px}
.sp{flex:1}button{font:inherit;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:8px;padding:6px 12px;cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
main{max-width:1500px;margin:0 auto;padding:16px 20px 80px}
.scene{background:var(--panel);border:1px solid var(--line);border-radius:12px;margin:18px 0;overflow:hidden}
.shead{display:flex;gap:12px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.shead h2{font-size:15px;margin:0;font-family:ui-monospace,Consolas,monospace}.tag{font-size:12px;color:var(--mute);border:1px solid var(--line);border-radius:99px;padding:1px 8px}
.pick{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--mute)}.pick label{border:1px solid var(--line);border-radius:7px;padding:2px 10px;cursor:pointer;color:var(--ink)}
.pick input{display:none}.pick input:checked+span{font-weight:700;color:var(--accent)}
.pick label:has(input:checked){border-color:var(--accent);background:var(--pick)}
table{width:100%;border-collapse:collapse;table-layout:fixed}td,th{vertical-align:top;padding:8px 12px;border-top:1px solid var(--line);text-align:left}
th{font-size:12px;color:var(--mute);font-weight:600;background:var(--bg)}
td.who{width:120px;color:var(--mute);font-size:13px}td.ja{font-size:15px}
.l{white-space:pre-wrap;display:flex;gap:8px;justify-content:space-between}.w{color:var(--mute);font-size:11px;font-variant-numeric:tabular-nums;flex:none}
.w.over{color:var(--warn);font-weight:700}.code{background:var(--code);color:var(--codeink);border-radius:4px;padding:0 3px;font-size:12px;font-family:ui-monospace,Consolas,monospace}
.prob{margin-top:4px;font-size:12px;color:var(--warn);background:var(--warnbg);border-radius:6px;padding:3px 7px}
.missing{color:var(--mute);font-style:italic}.fb{margin-top:4px;font-size:11px;color:var(--mute);border:1px dashed var(--line);border-radius:6px;padding:2px 7px;display:inline-block}
#reveal{display:none;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin-top:16px}
#reveal table td,#reveal table th{border-top:1px solid var(--line);font-variant-numeric:tabular-nums}
.note{color:var(--mute);font-size:13px;margin:6px 0 0}
@media (max-width:800px){td.who{width:70px}td,th{padding:6px}}
</style></head><body>
<header><h1 id="t"></h1><span class="meta" id="m"></span><span class="sp"></span>
<span class="meta" id="tally"></span><button id="exp">Copy picks</button><button class="primary" id="rev">Reveal models</button></header>
<main><div id="reveal"></div><p class="note">Pick the best version of each scene. Numbers next to a line are its width in letters (40 fit a row; codes count as their usual size). Red notes are problems the checker still finds. Your picks are kept in this browser.</p><div id="scenes"></div></main>
<script>
const D=/*DATA*/null;const KEY="mtpick:"+D.run;
let picks={};try{picks=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
const esc=s=>s.replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt=s=>esc(s).replace(/\{[^}]*\}/g,c=>'<span class="code">'+c+'</span>');
document.getElementById("t").textContent="Translation comparison: "+D.run;
document.getElementById("m").textContent=D.scenes.length+" scenes, models "+D.letters.join(" ")+" ("+D.time+")";
function save(){try{localStorage.setItem(KEY,JSON.stringify(picks))}catch(e){}tally()}
function tally(){const c={};D.letters.forEach(l=>c[l]=0);c.tie=0;Object.values(picks).forEach(v=>c[v]=(c[v]||0)+1);
document.getElementById("tally").textContent="Picks: "+D.letters.map(l=>l+" "+c[l]).join(" · ")+" · tie "+c.tie+" ("+Object.keys(picks).length+"/"+D.scenes.length+")";return c}
const S=document.getElementById("scenes");
D.scenes.forEach(sc=>{const el=document.createElement("section");el.className="scene";
let h='<div class="shead"><h2>'+esc(sc.key)+'</h2><span class="tag">'+sc.kind+'</span><span class="sp" style="flex:1"></span><div class="pick">Best:';
D.letters.concat(["tie"]).forEach(l=>{h+='<label><input type="radio" name="p_'+sc.key+'" value="'+l+'"'+(picks[sc.key]===l?" checked":"")+'><span>'+l+'</span></label>'});
h+='</div></div><table><thead><tr><th class="who" style="width:120px">Speaker</th><th>Japanese</th>'+D.letters.map(l=>"<th>"+l+"</th>").join("")+'</tr></thead><tbody>';
sc.messages.forEach(m=>{h+='<tr><td class="who">'+esc(m.speaker||"")+'</td><td class="ja">'+m.ja.map(x=>'<div class="l"><span>'+fmt(x)+'</span></div>').join("")+'</td>';
D.letters.forEach(l=>{const e=m.en[l];if(!e){h+='<td class="missing">no result</td>';return}
h+="<td>"+e.lines.map(([t,w])=>t?'<div class="l"><span>'+fmt(t)+'</span><span class="w'+(w>40?" over":"")+'">'+(w??"")+'</span></div>':'<div class="l missing">(empty)</div>').join("")+e.problems.map(p=>'<div class="prob">'+esc(p)+'</div>').join("")+(e.fallback?'<div class="fb">fixed by the fallback model</div>':'')+"</td>"});
h+="</tr>"});
const sp=D.letters.filter(l=>(sc.scene_problems[l]||[]).length);
if(sp.length){h+='<tr><td class="who">scene</td><td></td>'+D.letters.map(l=>'<td>'+(sc.scene_problems[l]||[]).map(p=>'<div class="prob">'+esc(p)+'</div>').join("")+'</td>').join("")+'</tr>'}
el.innerHTML=h+"</tbody></table>";
el.querySelectorAll("input").forEach(i=>i.addEventListener("change",()=>{picks[sc.key]=i.value;save()}));S.appendChild(el)});
tally();
const money=x=>x==null?"":"$"+Number(x).toFixed(x<1?3:2);
document.getElementById("rev").onclick=()=>{const c=tally();const R=document.getElementById("reveal");
let h='<h2 style="font-size:16px;margin:0 0 8px">Who is who</h2><table><thead><tr><th>Letter</th><th>Model</th><th>Picked best</th><th>Lines</th><th>Problems left</th><th>Repairs</th><th>Failed</th><th>Cost</th><th>Per 1,000 Japanese chars</th><th>Projected, all '+(D.all_scenes||"")+' scenes</th><th>API time</th></tr></thead><tbody>';
D.letters.forEach(l=>{const r=D.reveal[l],s=r.summary||{};h+="<tr><td><b>"+l+"</b></td><td>"+esc(r.name)+" <span class='meta'>"+esc(r.model)+"</span></td><td>"+c[l]+"</td><td>"+(s.lines_done??"")+"/"+(s.lines??"")+"</td><td>"+(s.problems_left??"")+"</td><td>"+(s.repairs??"")+"</td><td>"+(s.failed??"")+"</td><td>"+money(s.cost_all)+"</td><td>"+money(s.cost_per_1000_ja_chars)+"</td><td>"+money(s.projected_all)+"</td><td>"+(s.api_seconds??"")+"s</td></tr>"});
R.innerHTML=h+'</tbody></table><p class="note">Cost is what the replies cost when they were made (cached replies included). The projection scales that to every scene of the workbook folder the run read from.</p>';R.style.display="block";R.scrollIntoView({behavior:"smooth"})};
document.getElementById("exp").onclick=()=>{const t=JSON.stringify({run:D.run,picks,tally:tally()},null,1);navigator.clipboard&&navigator.clipboard.writeText(t);document.getElementById("exp").textContent="Copied"};
</script></body></html>
"""

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
