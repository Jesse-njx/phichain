"""L2: blind user review. The only layer that can pass a candidate.

    python3 l2_review.py build MANIFEST.json OUT_DIR [--seed N]
    python3 l2_review.py ingest OUT_DIR RATINGS.json

Manifest:
    {"title": "...",
     "clips": [{"id": "...", "condition": "...", "role": "candidate",
                "video": "path.mp4", "start": 0, "end": 13, "chart": "optional/chart.json"}]}

Clips get captions, progress bar, combo and score masked, because they reveal the source. Check a frame
of every clip for other identifying text before handing a session to the user.

Roles: candidate, anchor_official, anchor_rejected. Anchors are mixed in unmarked. If the
official anchor does not outscore the rejected anchor, that session is flagged as miscalibrated.

`build` writes OUT_DIR/review (safe to view, contains no identities) and OUT_DIR/sealed/key.json.
`ingest` unblinds, summarizes by condition and writes labels for the backtest.
"""
import argparse
from collections import defaultdict
import hashlib
import html
import json
from pathlib import Path
import random
from statistics import median
import subprocess

HERE = Path(__file__).resolve().parent
ROLES = {"candidate", "anchor_official", "anchor_rejected"}
DIMENSIONS = [
    ("hand_action", "Hand action", "Is the movement satisfying and purposeful to play?"),
    ("rhythm_fit", "Rhythm fit", "Do the notes follow what you hear?"),
    ("line_performance", "Line performance", "Do the lines perform the music, without noise?"),
    ("readability", "Readability", "Is it clear which line each note belongs to and where to hit?"),
]
VERDICTS = [
    ("keep", "Keep", "Good enough to build on as it is."),
    ("fix", "Fix", "Good idea, needs specific changes."),
    ("reject", "Reject", "Start over."),
]
# Renders burn captions such as "Official IN reference" into the bottom of the frame, and the
# progress bar, combo and score reveal a slice of a full song against a standalone excerpt.
CAPTION_MASK = ",".join(
    f"drawbox=x=iw*{x}:y=ih*{y}:w=iw*{w}:h=ih*{h}:color=black:t=fill"
    for x, y, w, h in ((0, 0.90, 1, 0.10), (0, 0, 1, 0.015), (0.43, 0, 0.14, 0.16), (0.82, 0, 0.18, 0.10))
)
SCALE = "1 terrible · 2 bad · 3 passable · 4 good · 5 official-level"


def cut(source, start, end, target):
    """Re-encode so that no source name, metadata or keyframe offset reaches the page."""
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(source)]
    if end is not None:
        cmd += ["-t", str(end - (start or 0))]
    cmd += [
        "-map_metadata", "-1", "-map_chapters", "-1", "-fflags", "+bitexact",
        "-vf", f"{CAPTION_MASK},scale=-2:720", "-r", "60", "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target),
    ]
    subprocess.run(cmd, check=True)


def page(title, session, labels):
    rows = "".join(
        f"""<fieldset data-dim="{key}"><legend>{name}<span>{hint}</span></legend><div class="scale">"""
        + "".join(f'<label><input type="radio" value="{v}"><b>{v}</b></label>' for v in range(1, 6))
        + "</div></fieldset>"
        for key, name, hint in DIMENSIONS
    )
    verdicts = "".join(f'<label title="{hint}"><input type="radio" value="{key}"><b>{name}</b></label>' for key, name, hint in VERDICTS)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Blind Chart Review</title>
<style>
:root{{--bg:#f6f5f2;--panel:#fff;--ink:#1d1d1b;--mute:#6b6a65;--line:#dcdad4;--accent:#2f5d8a;--on:#fff}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151514;--panel:#1f1f1d;--ink:#ecebe6;--mute:#a09f98;--line:#3a3935;--accent:#8fb8de;--on:#10202e}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,sans-serif}}
main{{max-width:1120px;margin:auto;padding:24px 16px 72px}}h1{{font-size:22px;margin:0 0 4px}}
p{{margin:0;color:var(--mute)}}nav{{display:flex;flex-wrap:wrap;gap:6px;margin:20px 0}}
nav button{{min-width:44px;min-height:44px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:6px;font:inherit;cursor:pointer}}
nav button.done{{background:var(--accent);color:var(--on);border-color:var(--accent)}}nav button.here{{outline:2px solid var(--ink);outline-offset:1px}}
.grid{{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(300px,1fr);gap:20px;align-items:start}}@media(max-width:800px){{.grid{{grid-template-columns:minmax(0,1fr)}}}}
video{{width:100%;background:#000;border-radius:6px;display:block}}h2{{font-size:17px;margin:0 0 10px}}
fieldset{{border:0;padding:0;margin:0 0 18px;min-width:0}}legend{{padding:0;font-weight:600}}legend span{{display:block;font-weight:400;font-size:14px;color:var(--mute)}}
.scale,.verdict{{display:flex;gap:6px;margin-top:8px}}.scale label,.verdict label{{flex:1;min-width:0;cursor:pointer}}input[type=radio]{{position:absolute;opacity:0}}
label b{{display:flex;align-items:center;justify-content:center;min-height:44px;border:1px solid var(--line);border-radius:6px;background:var(--panel);font-weight:500}}
input:checked+b{{background:var(--accent);color:var(--on);border-color:var(--accent)}}input:focus-visible+b{{outline:2px solid var(--ink)}}
textarea{{width:100%;min-height:72px;margin-top:8px;padding:8px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--ink);font:inherit}}
.bar{{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap;align-items:center}}.bar button{{min-height:44px;padding:0 16px;border-radius:6px;border:1px solid var(--line);background:var(--panel);color:var(--ink);font:inherit;cursor:pointer}}
.bar .go{{background:var(--accent);color:var(--on);border-color:var(--accent)}}#status{{color:var(--mute);font-size:14px}}
</style></head><body><main>
<h1>{html.escape(title)}</h1><p>{SCALE}. Clips are in random order and some are reference clips. Judge what you see and hear.</p>
<nav id="nav"></nav>
<div class="grid"><div><video id="video" controls playsinline preload="metadata"></video></div>
<form id="form" onsubmit="return false"><h2 id="heading"></h2>{rows}
<fieldset data-dim="verdict"><legend>Verdict</legend><div class="verdict">{verdicts}</div></fieldset>
<fieldset><legend>What is wrong or right?<span>Optional. Name the moment if you can.</span></legend><textarea id="note"></textarea></fieldset>
<div class="bar"><button class="go" id="next" type="button">Next clip</button><button id="export" type="button">Download ratings</button><span id="status"></span></div>
</form></div></main>
<script>
const session={json.dumps(session)},labels={json.dumps(labels)},storeKey='blind-review-'+session;
let ratings={{}},here=0;
try{{ratings=JSON.parse(localStorage.getItem(storeKey))||{{}}}}catch(e){{}}
const save=()=>{{try{{localStorage.setItem(storeKey,JSON.stringify(ratings))}}catch(e){{}}}};
const required={json.dumps([d[0] for d in DIMENSIONS] + ["verdict"])};
const complete=l=>required.every(k=>ratings[l]&&ratings[l][k]!=null);
function drawNav(){{const n=document.getElementById('nav');n.textContent='';labels.forEach((l,i)=>{{const b=document.createElement('button');b.type='button';b.textContent=i+1;b.setAttribute('aria-label','Clip '+(i+1));if(complete(l))b.className='done';if(i===here)b.className+=' here';b.onclick=()=>show(i);n.append(b)}});
const c=labels.filter(complete).length;document.getElementById('status').textContent=c+' of '+labels.length+' rated'}}
function show(i){{here=i;const l=labels[i],r=ratings[l]||{{}};const v=document.getElementById('video');v.src='clips/'+l+'.mp4';document.getElementById('heading').textContent='Clip '+(i+1);
document.querySelectorAll('fieldset[data-dim]').forEach(f=>{{f.querySelectorAll('input').forEach(x=>{{x.name=f.dataset.dim;x.checked=String(r[f.dataset.dim])===x.value}})}});
document.getElementById('note').value=r.note||'';drawNav()}}
document.getElementById('form').addEventListener('change',e=>{{const l=labels[here];ratings[l]=ratings[l]||{{}};if(e.target.type==='radio')ratings[l][e.target.name]=/^\\d$/.test(e.target.value)?+e.target.value:e.target.value;save();drawNav()}});
document.getElementById('note').addEventListener('input',e=>{{const l=labels[here];ratings[l]=ratings[l]||{{}};ratings[l].note=e.target.value;save()}});
document.getElementById('next').onclick=()=>show((here+1)%labels.length);
document.getElementById('export').onclick=()=>{{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({{session,ratings}},null,1)],{{type:'application/json'}}));a.download='ratings-'+session+'.json';a.click()}};
show(0);
</script></body></html>"""


def build(manifest_path, out, seed):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    clips = manifest["clips"]
    roles = {c["role"] for c in clips}
    if roles - ROLES:
        raise SystemExit(f"unknown roles {roles - ROLES}")
    if len({c["id"] for c in clips}) != len(clips):
        raise SystemExit("clip ids must be unique")
    if not {"anchor_official", "anchor_rejected"} <= roles:
        raise SystemExit("a session needs one anchor_official and one anchor_rejected clip")
    out = Path(out)
    review, sealed = out / "review", out / "sealed"
    (review / "clips").mkdir(parents=True, exist_ok=True)
    sealed.mkdir(parents=True, exist_ok=True)
    rng = random.SystemRandom() if seed is None else random.Random(seed)
    order = list(clips)
    rng.shuffle(order)
    session = hashlib.sha256(f"{manifest_path.resolve()}{rng.random()}".encode()).hexdigest()[:10]
    labels = [f"c{rng.randrange(16 ** 6):06x}" for _ in order]
    if len(set(labels)) != len(labels):
        raise SystemExit("label collision; run again")
    key = {}
    for label, clip in zip(labels, order):
        source = (manifest_path.parent / clip["video"]).resolve()
        cut(source, clip.get("start"), clip.get("end"), review / "clips" / f"{label}.mp4")
        key[label] = clip
    (review / "index.html").write_text(page(manifest.get("title", "Blind chart review"), session, labels))
    (sealed / "key.json").write_text(json.dumps({"session": session, "title": manifest.get("title"), "key": key}, indent=1, ensure_ascii=False))
    print(review / "index.html")


def to_axis(score):
    return "pass" if score >= 4 else "fail" if score <= 2 else None


def ingest(out, ratings_path):
    out = Path(out)
    sealed = json.loads((out / "sealed" / "key.json").read_text())
    doc = json.loads(Path(ratings_path).read_text())
    if doc["session"] != sealed["session"]:
        raise SystemExit(f"ratings are for session {doc['session']}, not {sealed['session']}")
    rows = []
    missing = []
    for label, clip in sealed["key"].items():
        rating = doc["ratings"].get(label)
        if not rating or any(rating.get(d[0]) is None for d in DIMENSIONS) or not rating.get("verdict"):
            missing.append(clip["id"])
            continue
        rows.append({**clip, "label": label, **rating})

    def mean_score(row):
        return sum(row[d[0]] for d in DIMENSIONS) / len(DIMENSIONS)

    official = [mean_score(r) for r in rows if r["role"] == "anchor_official"]
    rejected = [mean_score(r) for r in rows if r["role"] == "anchor_rejected"]
    calibrated = bool(official and rejected) and min(official) > max(rejected)

    by_condition = defaultdict(list)
    for row in rows:
        if row["role"] == "candidate":
            by_condition[row.get("condition", "unspecified")].append(row)
    conditions = {}
    for name, items in by_condition.items():
        verdicts = [r["verdict"] for r in items]
        conditions[name] = {
            "clips": len(items),
            "keep_rate": round(verdicts.count("keep") / len(items), 3),
            "reject_rate": round(verdicts.count("reject") / len(items), 3),
            "median": {d[0]: median(r[d[0]] for r in items) for d in DIMENSIONS},
            "worst": {d[0]: min(r[d[0]] for r in items) for d in DIMENSIONS},
        }

    result = {"session": sealed["session"], "title": sealed.get("title"), "calibrated": calibrated, "missing": missing, "conditions": conditions, "rows": rows}
    (out / "results.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))

    cases = []
    if calibrated and not missing:
        for row in rows:
            if row["role"] != "candidate" or not row.get("chart"):
                continue
            cases.append({
                "id": f"l2-{sealed['session']}-{row['id']}",
                "path": row["chart"],
                "start": row.get("chart_start"),
                "end": row.get("chart_end"),
                "hand": to_axis(row["hand_action"]),
                "line": to_axis(row["line_performance"]),
                "overall": {"keep": "pass", "reject": "fail"}.get(row["verdict"]),
                "evidence": f"Blind L2 session {sealed['session']}",
            })
    if cases:
        target = HERE.parent / "backtest" / "labels.d"
        target.mkdir(exist_ok=True)
        (target / f"{sealed['session']}.json").write_text(json.dumps({"cases": cases}, indent=1, ensure_ascii=False))

    print(json.dumps({k: result[k] for k in ("calibrated", "missing", "conditions")}, indent=1, ensure_ascii=False))
    if not calibrated:
        print("Not calibrated: the official anchor did not outscore the rejected anchor. No labels written.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("manifest")
    b.add_argument("out")
    b.add_argument("--seed", type=int)
    i = sub.add_parser("ingest")
    i.add_argument("out")
    i.add_argument("ratings")
    args = parser.parse_args()
    if args.command == "build":
        build(args.manifest, args.out, args.seed)
    else:
        ingest(args.out, args.ratings)


if __name__ == "__main__":
    main()
