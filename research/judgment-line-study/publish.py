"""Build an offline searchable HTML research atlas and per-case diagnostic pages."""
from build_bank import *
import csv, subprocess

STYLE='''
:root{color-scheme:dark;--bg:#101419;--panel:#191f26;--ink:#edf2f5;--muted:#afbac4;--accent:#8ee0c6;--border:#35414d;--warm:#f3bf78}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,-apple-system,sans-serif}main{max-width:1280px;margin:auto;padding:42px 32px 80px}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}h1,h2,h3{line-height:1.2;letter-spacing:-.02em}h1{font-size:clamp(30px,4vw,54px);max-width:950px;margin:16px 0 24px}h2{font-size:30px;margin:56px 0 20px}h3{font-size:21px;margin:30px 0 12px}.lead{font-size:21px;max-width:940px;color:#d3dee7}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.13em;color:var(--accent)}p,li{max-width:1000px}p{margin:15px 0}.muted,small{color:var(--muted)}.toc,.links,.controls,.metrics{display:flex;flex-wrap:wrap;gap:14px 22px}.toc{border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:18px 0;margin:30px 0}.metrics{margin:28px 0}.metric{min-width:155px}.metric b{font-size:30px;display:block}.metric span{color:var(--muted);font-size:14px}.formula{padding:22px;background:var(--panel);overflow:auto;border-left:3px solid var(--accent);font:15px/1.7 ui-monospace,monospace}.findings li{margin:16px 0}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid var(--border);padding:12px}th{color:var(--muted)}.essay{max-width:1050px}details{border-bottom:1px solid var(--border);padding:12px 0}summary{cursor:pointer}.filterbar{position:sticky;top:0;background:rgba(16,20,25,.98);z-index:5;padding:20px 0;border-bottom:1px solid var(--border)}input,select,button{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--border);border-radius:5px;padding:9px 12px}input[type=search]{width:min(100%,510px)}input[type=range]{padding:0;flex:1;min-width:180px}button{cursor:pointer}button:hover{border-color:var(--accent)}label{font-size:14px;color:var(--muted)}.controls{align-items:center;gap:10px}.count{margin:12px 0 0;font-size:14px;color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:34px 24px;margin-top:24px}.card{min-width:0;padding-bottom:24px;border-bottom:1px solid var(--border)}.card h3{font-size:20px;margin:10px 0}.card p{font-size:14px;margin:7px 0}.card .variant{min-height:42px;color:var(--muted)}video,canvas{width:100%;aspect-ratio:16/9;background:#07090c;display:block}video{object-fit:contain}.badge{font:12px ui-monospace,monospace;color:var(--warm)}.source{font-weight:600}.card .links{font-size:13px;gap:8px 15px;margin-top:12px}.mechanism-index{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:9px 24px;margin:20px 0}.mechanism-index button{font-size:14px;text-align:left;background:transparent;padding:5px 0;border:0;color:var(--accent)}.player{max-width:1050px}.player .controls{padding:12px 0}.notice{background:var(--panel);border-left:3px solid var(--warm);padding:16px 20px;margin:22px 0;font-size:14px}.recipe-grid{display:grid;grid-template-columns:1fr 1fr;gap:28px}.recipe-grid p{margin-top:0}.trace{width:100%;display:block;max-width:1050px}.evidence{font:13px/1.6 ui-monospace,monospace;overflow:auto;max-height:300px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}@media(max-width:650px){main{padding:24px 18px}.cards{display:block}.card{margin:24px 0}.recipe-grid{display:block}.filterbar{position:static}h2{font-size:26px}table{font-size:12px}td,th{padding:8px}}
'''
STYLE += 'table{display:block;max-width:100%;overflow-x:auto}code{overflow-wrap:anywhere}'

def shell(title,body,script=''):
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+'</style></head><body><main>'+body+'</main>'+script+'</body></html>'

def matching_receipt(c,receipts):
    return next((r for r in reversed(receipts) if r.get('success') and Path(r.get('video','')).is_file() and r['source_sha256']==c['source']['sha256'] and r['mechanism']==c['mechanism'] and abs(r['chart_seconds'][0]-max(0,c['start']-.25))<1e-5 and abs(r['chart_seconds'][1]-(c['end']+.4))<1e-5),None)

def diagnostic(c):
    d,ls=load_chart(c['source']['path']);ts=np.linspace(c['start'],c['end'],max(30,int((c['end']-c['start'])*30)+1));frames=[{'t':round(float(t),5),'lines':[],'notes':[]} for t in ts]
    focus={(r['line'],r['side'],r['index']) for r in c.get('ensemble',[])}
    if 'note'in c:focus.add((c['lines'][0],c['note']['side'],c['note']['index']))
    traces=[]
    for li,l in enumerate(ls):
        p=l.pose(ts);selected=li in c['lines'];floor=l.floor(ts)
        for k in range(len(ts)):frames[k]['lines'].append([li,*[round(float(p[j][k]),5) for j in range(4)],selected])
        future=[n for n in l.notes if n['end']>=c['start']]
        if not future:continue
        floors=l.floor([n['t'] for n in future]);a=np.deg2rad(p[2]);co=np.cos(a);si=np.sin(a)
        for ni,n in enumerate(future):
            dd=(floors[ni]-floor)*.6*(1 if n['type']==3 else n['speed']);front=dd>=-1e-6
            if n['type']==3:dd=np.maximum(dd,0)
            dd*=1 if n['side']=='notesAbove' else -1
            x=p[0]+n['positionX']/18*co-dd*9/16*si;y=p[1]+n['positionX']/18*16/9*si+dd*co
            visible=(ts<=n['end']+1e-5)&(x>=-.08)&(x<=1.08)&(y>=-.08)&(y<=1.08)&front
            marked=(li,n['side'],n['index'])in focus
            if marked:traces.append({'label':f'L{li}/{n["side"]}/{n["index"]}','points':[[round(float(x[k]),5),round(float(y[k]),5)] for k in range(len(ts)) if visible[k]],'hold':n['type']==3})
            for k in np.where(visible)[0]:frames[k]['notes'].append([li,n['type'],round(float(x[k]),5),round(float(y[k]),5),round(float(p[2][k]),4),marked])
    primary=ls[c['lines'][0]].pose(ts)
    return {'frames':frames,'traces':traces,'primary':[[round(float(v),5) for v in channel] for channel in primary],'offset':d.get('offset',0),'selected_lines':c['lines']}

PLAYER_JS='''
<script>
const D=DIAGNOSTIC_DATA;
const cv=document.getElementById('scene'),ctx=cv.getContext('2d'),slider=document.getElementById('scrub'),timeLabel=document.getElementById('time-label'),play=document.getElementById('play'),speed=document.getElementById('rate'),context=document.getElementById('context'),paths=document.getElementById('paths');
let index=0,running=false,last=0,elapsed=0;
slider.max=D.frames.length-1;
function draw(){const f=D.frames[index],W=cv.width,H=cv.height;ctx.fillStyle='#090d12';ctx.fillRect(0,0,W,H);ctx.save();ctx.beginPath();ctx.rect(0,0,W,H);ctx.clip();
if(paths.checked){for(const tr of D.traces){ctx.beginPath();let first=true;for(const p of tr.points){if(first){ctx.moveTo(p[0]*W,(1-p[1])*H);first=false;}else ctx.lineTo(p[0]*W,(1-p[1])*H);}ctx.strokeStyle=tr.hold?'#edb46d':'#6d9f96';ctx.lineWidth=2;ctx.stroke();}}
for(const l of f.lines){const [id,x,y,r,alpha,selected]=l;if(!context.checked&&!selected)continue;const a=-r*Math.PI/180,cx=x*W,cy=(1-y)*H,dx=Math.cos(a)*W*8,dy=Math.sin(a)*W*8;ctx.globalAlpha=selected?Math.max(.22,Math.min(1,alpha)):Math.max(0,Math.min(.3,alpha*.3));ctx.setLineDash(alpha<=.01&&selected?[7,6]:[]);ctx.strokeStyle=selected?'#8ee0c6':'#6d7782';ctx.lineWidth=selected?2.5:1;ctx.beginPath();ctx.moveTo(cx-dx,cy-dy);ctx.lineTo(cx+dx,cy+dy);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1;if(selected&&cx>=0&&cx<W&&cy>=0&&cy<H){ctx.fillStyle='#8ee0c6';ctx.beginPath();ctx.arc(cx,cy,4,0,Math.PI*2);ctx.fill();ctx.font='16px monospace';ctx.fillText('L'+id+' α='+alpha.toFixed(2),Math.max(8,Math.min(W-170,cx+9)),Math.max(18,Math.min(H-10,cy-10)));}}
for(const n of f.notes){const [li,type,x,y,r,marked]=n;if(!context.checked&&!marked)continue;ctx.save();ctx.translate(x*W,(1-y)*H);ctx.rotate(-r*Math.PI/180);ctx.globalAlpha=marked?1:.35;ctx.strokeStyle=marked?(type===3?'#edb46d':'#8ee0c6'):'#9aa4ae';ctx.lineWidth=marked?4:2;if(type===3){ctx.strokeRect(-10,-7,20,14);}else{ctx.beginPath();ctx.moveTo(-12,0);ctx.lineTo(12,0);ctx.stroke();}if(marked){ctx.beginPath();ctx.arc(0,0,5,0,Math.PI*2);ctx.stroke();}ctx.restore();}ctx.restore();ctx.globalAlpha=1;slider.value=index;timeLabel.textContent=f.t.toFixed(3)+' s chart · '+(f.t+D.offset).toFixed(3)+' s audio';}
function tick(now){if(running){if(last){elapsed+=(now-last)/1000*Number(speed.value);const start=D.frames[0].t,end=D.frames[D.frames.length-1].t;const t=start+elapsed;if(t>=end){index=D.frames.length-1;running=false;play.textContent='Play';}else index=Math.min(D.frames.length-1,Math.round((t-start)/(end-start)*(D.frames.length-1)));draw();}last=now;requestAnimationFrame(tick);}}
play.onclick=()=>{running=!running;play.textContent=running?'Pause':'Play';if(running){if(index===D.frames.length-1){index=0;elapsed=0;}else elapsed=D.frames[index].t-D.frames[0].t;last=0;requestAnimationFrame(tick);}};
slider.oninput=()=>{index=Number(slider.value);elapsed=D.frames[index].t-D.frames[0].t;draw();};context.onchange=draw;paths.onchange=draw;draw();
</script>
'''

def sparklines(c,data):
    W,H=1000,300;chunks=[f'<svg class="trace" viewBox="0 0 {W} {H}" role="img" aria-label="Primary carrier event traces: x, y, rotation, alpha and speed">']
    for j,(label,unit) in enumerate([('x','viewport width'),('y','viewport height'),('rotation','degrees'),('alpha','raw'),('scroll speed','source units')]):
        a=np.array(data['primary'][j]);lo=float(min(a));hi=float(max(a));span=hi-lo or 1;yy=j*59
        points=' '.join(f'{210+k/(len(a)-1)*770:.2f},{yy+46-(v-lo)/span*34:.2f}' for k,v in enumerate(a))
        chunks += [f'<text x="0" y="{yy+20}" fill="#afbac4" font-size="14">{label} ({unit})</text>',f'<text x="0" y="{yy+40}" fill="#edf2f5" font-size="13">{lo:.3f} → {hi:.3f}</text>',f'<path d="M210 {yy+47} H980" stroke="#35414d"/>',f'<polyline points="{points}" stroke="#8ee0c6" fill="none" stroke-width="2"/>']
    chunks.append('</svg>');return ''.join(chunks)

def make_details(bank,receipts):
    folder=ROOT/'cases';folder.mkdir(exist_ok=True)
    cache=ROOT/'diagnostics';cache.mkdir(exist_ok=True)
    for k,c in enumerate(bank):
        cached=cache/(c['id']+'.json')
        if cached.exists():data=json.loads(cached.read_text())
        else:
            data=diagnostic(c);cached.write_text(json.dumps(data,separators=(',',':'),ensure_ascii=False))
        r=matching_receipt(c,receipts);f=c['features'];esc=html.escape;src=c['source'];defn=c['definition'];audio=[c['start']+data['offset'],c['end']+data['offset']]
        body=f'<p><a href="../index.html#bank">← Search the atlas</a></p><p class="eyebrow">{c["id"]} · {c["category"]} performance</p><h1>{esc(defn["name"])}</h1><p class="lead">{esc(flavor(c))}</p><p class="source">{esc(src["title"])} · {src["difficulty"]} · source {src["id"]}</p><p>Chart {c["start"]:.6f}–{c["end"]:.6f}s · Audio {audio[0]:.6f}–{audio[1]:.6f}s · Lines {", ".join(map(str,c["lines"]))} (zero-based)</p>'
        if r:
            rel='../'+str(Path(r['video']).relative_to(ROOT));body+=f'<h2>Native example</h2><video controls preload="metadata" playsinline src="{rel}"></video><p class="muted">Full source scene · {esc(r["audio"])} · native clip begins at chart {r["chart_seconds"][0]:.6f}s. Selected effect window begins {c["start"]-r["chart_seconds"][0]:.3f}s into the clip.</p>'
        else:body+='<div class="notice">Native render is not available for this entry. The exact source events and diagnostic center geometry are below; no native verification is claimed.</div>'
        body+=f'<div class="recipe-grid"><div><h2>How it is made</h2><p>{esc(defn["construction"])}</p></div><div><h2>Possible compositional use</h2><p>{esc(defn["use"])}</p><p class="muted">Design interpretation, not a claim about the original charter’s intent.</p></div></div><div class="notice">{esc(defn["boundary"])}</div>'
        body+='<h2>Isolate the mechanism</h2><p>Center geometry at 30 Hz. Mint highlights selected carriers and notes; dashed strokes expose invisible carriers. Gray shows the rest of the source scene. Hold centers are shown without body/tail geometry. This is an analytical reconstruction, not a replacement for the native video.</p><div class="player"><canvas id="scene" width="960" height="540" aria-label="Source-derived carrier and note-center animation"></canvas><div class="controls"><button id="play" type="button">Play</button><label>Rate <select id="rate"><option value=".25">0.25×</option><option value=".5">0.5×</option><option value="1" selected>1×</option></select></label><input id="scrub" type="range" min="0" value="0" aria-label="Chart time"><label><input id="context" type="checkbox" checked> Context</label><label><input id="paths" type="checkbox" checked> Traces</label></div><div id="time-label" class="muted" aria-live="off"></div></div>'
        body+='<h2>Primary carrier channels</h2><p class="muted">Each row uses its own vertical range. Ranges describe this excerpt; they are not an easing-function reconstruction or perceptual score.</p>'+sparklines(c,data)
        body+='<h2>Measured recipe</h2><table><tbody>'
        rows=[('Carrier x span',f'{f["x_span"]:.6f} viewport widths'),('Carrier y span',f'{f["y_span"]:.6f} viewport heights'),('Rotation range',f'{f["rotation_span"]:.3f}°'),('Net rotation',f'{f["rotation_delta"]:.3f}°'),('Alpha range',f'{f["alpha_min"]:.4f} to {f["alpha_max"]:.4f}'),('Speed range',f'{f["speed_min"]:.6f} to {f["speed_max"]:.6f}'),('Source line role','No notes anywhere in each highlighted line' if c['whole_line_empty'] else 'Playable carrier / note formation'),('Other detected components',', '.join(c['tags']))]
        if 'note'in c:
            n=c['note'];rows+=[('Exact exemplar note',f'L{c["lines"][0]} / {n["side"]} / {n["index"]}'),('Note local x / speed',f'{n["positionX"]:.6f} / {n["speed"]:.6f}'),('Full note timing',f'{n["t"]:.6f}–{n["end"]:.6f}s')]
        if 'mining_window'in c:rows.append(('Original discovery window',str(c['mining_window'])+'; final interval narrowed to the actual formation'))
        for label,value in rows:body+=f'<tr><th>{esc(label)}</th><td>{esc(value)}</td></tr>'
        body+='</tbody></table>'
        body+='<h2>Pose checkpoints for reconstruction</h2><p class="muted">Five samples per highlighted carrier. x/y are viewport fractions, angle is degrees, speed is the source scroll value. Intermediate events remain essential: these checkpoints are a reading guide, not a lossless replacement for the source.</p><table><thead><tr><th>Line</th><th>Chart s</th><th>x</th><th>y</th><th>Angle</th><th>Alpha</th><th>Speed</th></tr></thead><tbody>'
        _,source_lines=load_chart(src['path']);sample_times=np.linspace(c['start'],c['end'],5)
        for li in c['lines']:
            poses=source_lines[li].pose(sample_times)
            for k,t in enumerate(sample_times):
                body+=f'<tr><td>L{li}</td><td>{t:.4f}</td>'+''.join(f'<td>{float(ch[k]):.4f}</td>' for ch in poses)+'</tr>'
        body+='</tbody></table>'
        body+=f'<h2>Source evidence</h2><p><a href="../evidence/{c["id"]}.json">Exact events, note pointers, beats and ticks</a> · <a href="../sources/{src["id"]}.json">Frozen original chart JSON</a> · <a href="{esc(src["source_url"],quote=True)}">Original acquisition URL</a></p><p class="muted">SHA256 <code>{src["sha256"]}</code></p><p class="muted">Source event pointers are zero-based. The frozen bytes are authoritative for reproducing this entry. Floating upstream URLs can change. Diagnostic events use right-continuous selection; the native inclusive evaluator can differ at a discontinuous shared boundary.</p>'
        script=PLAYER_JS.replace('DIAGNOSTIC_DATA',json.dumps(data,separators=(',',':'),ensure_ascii=False).replace('</','<\\/'))
        (folder/(c['id']+'.html')).write_text(shell(c['id']+' · '+defn['name'],body,script))
        if k%30==0:print('Detail pages',k+1,flush=True)

def make_index(bank,receipts):
    esc=html.escape;stats=json.loads((ROOT/'chart-statistics.json').read_text());counts=collections.Counter(c['category'] for c in bank);families=sorted(set(c['mechanism'] for c in bank));native=sum(bool(matching_receipt(c,receipts)) for c in bank)
    hidden=sum(s['hidden_at_judgment']for s in stats);notes=sum(s['notes']for s in stats);lines=sum(s['lines']for s in stats);empty=sum(s['empty_lines']for s in stats)
    metrics=''.join(f'<div class="metric"><b>{v}</b><span>{label}</span></div>' for v,label in [(len(stats),'source charts'),(f'{notes:,}','playable objects'),(f'{lines:,}','line objects'),(len(bank),'recipe entries'),(len(families),'mechanism families'),(native,'native short videos')])
    intro=(ROOT/'analysis-fragment.html').read_text().replace('<div id="corpus-metrics"></div>','<div class="metrics">'+metrics+'</div>'+f'<p><strong>{empty:,} of {lines:,} lines ({empty/lines:.1%}) contain no notes at all.</strong> {hidden:,} of {notes:,} note heads ({hidden/notes:.1%}) occur while their own carrier has alpha ≤ 0.01. These are whole-corpus structural counts, not estimates of visual quality or the prevalence of every motif.</p>')
    studies={
        'N001':'Archidoxen keeps the target near its stationary pivot while its carrier accumulates more than five turns in the excerpt. This is the geometric reason elaborate rotational approach can coexist with a stable hit station.',
        'N019':'FULi AUTO BUSTER combines roughly 783 degrees of rotation with a carrier translation spanning half the viewport width. The resulting entrance is a travelling-pivot composition, not just a vertical fall drawn at an angle.',
        'N087':'GOODWORLD moves the carrier by roughly 0.513 viewport widths while the selected judgment x positions span only about 0.032. Changing local positions compensates the carrier movement; this is distinct from placing every note at a stationary pivot.',
        'N091':'A journey to the moonlight forms a smooth left–right–left arch from successive local positions on a stable carrier. The silhouette curves while the individual approach routes remain straight.',
        'B034':'Non-Melodic Ragez uses a note-free line with a flashing visibility envelope. Widely spaced stills can all catch its off phases; a targeted frame at chart 3.25 seconds confirms the stroke on screen. Temporal sampling matters.',
        'B070':'Stardust:RAY supplies four wholly note-free lines as a moving stripe field. The example is restricted to 82.00–84.15 seconds, where the audited parallel structure holds, instead of labeling the whole later transition a comb.',
        'B072':'Aphrodite’s Child uses four note-free carriers around a shared radial structure. The geometry and its flashing visibility are separate layers: the fan does not cease to be a geometric construction during every brief alpha-off phase.'
    }
    case_lookup={c['id']:c for c in bank};study_html='<h2 id="source-studies">Concrete lessons from the sources</h2>'
    for cid,text in studies.items():
        if cid not in case_lookup:continue
        c=case_lookup[cid];study_html+=f'<h3><a href="cases/{cid}.html">{cid} · {esc(c["source"]["title"])} {c["source"]["difficulty"]}</a></h3><p>{esc(text)}</p><p class="muted">{c["start"]:.3f}–{c["end"]:.3f}s chart · Lines {", ".join(map(str,c["lines"]))}.</p>'
    intro=intro.replace('<h2 id="construction">',study_html+'<h2 id="construction">')
    body=intro+f'<section id="bank"><p class="eyebrow">Video index · {counts["note"]} note recipes · {counts["background"]} background recipes</p><h2>Query the effect bank</h2><p>{len(bank)} source-specific recipes organized into {len(families)} mechanism families. Related variants differ in measured carrier geometry, timing envelope, visibility, or grouping; they are not {len(bank)} unrelated primitives. Click “Recipe & diagnostics” for exact construction and evidence.</p><details><summary>Browse the mechanism index</summary><div class="mechanism-index">'
    voc=vocabulary()
    for tag in families:body+=f'<button type="button" data-family="{tag}">{esc(voc[tag]["name"])} <small>({sum(c["mechanism"]==tag for c in bank)})</small></button>'
    body+='</div></details><div class="filterbar"><div class="controls"><label class="sr-only" for="query">Search recipes</label><input id="query" type="search" placeholder="Search effect, chart, ID… or chart:Shadow line:17"><label>Use <select id="category"><option value="">All</option><option value="note">Note performance</option><option value="background">Background lines</option></select></label><label>Family <select id="family"><option value="">All mechanisms</option>'
    body+=''.join(f'<option value="{t}">{esc(voc[t]["name"])}</option>' for t in families)
    body+='</select></label><label>Level <select id="difficulty"><option value="">All</option><option>IN</option><option>AT</option></select></label><label>Audio <select id="audio"><option value="">All</option><option value="original">Source audio</option><option value="silent">Silent</option></select></label><button id="clear" type="button">Clear</button></div><p class="count" id="result-count" role="status"></p><p class="count">Query fields: <code>chart:</code>, <code>kind:</code>, <code>family:</code>, <code>line:</code>, <code>id:</code>. Words combine with AND; quote multiword values. Videos are paused until played. <a href="index.csv">CSV index</a> · <a href="bank.json">JSON index</a></p></div><div id="cards" class="cards"></div></section>'
    dataset=[]
    for c in bank:
        r=matching_receipt(c,receipts);src=c['source'];dataset.append(dict(id=c['id'],name=c['definition']['name'],variant=flavor(c),category=c['category'],family=c['mechanism'],chart=src['title'],difficulty=src['difficulty'],lines=c['lines'],start=round(c['start'],6),end=round(c['end'],6),construction=c['definition']['construction'],tags=c['tags'],video=str(Path(r['video']).relative_to(ROOT)) if r else None,poster='posters/'+c['id']+'.jpg' if (ROOT/'posters'/(c['id']+'.jpg')).exists() else None,audio=('original' if r and r['audio'].startswith('matching') else 'silent') if r else '',native=bool(r)))
    script='''<script>
const CASES=INDEX_DATA;const els={q:document.getElementById('query'),category:document.getElementById('category'),family:document.getElementById('family'),difficulty:document.getElementById('difficulty'),audio:document.getElementById('audio'),cards:document.getElementById('cards'),count:document.getElementById('result-count')};
function element(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function tokens(q){return (q.match(/(?:[^\\s"]+|"[^"]*")+/g)||[]).map(s=>s.replaceAll('"','').toLowerCase());}
function matches(c){if(els.category.value&&c.category!==els.category.value||els.family.value&&c.family!==els.family.value||els.difficulty.value&&c.difficulty!==els.difficulty.value||els.audio.value&&c.audio!==els.audio.value)return false;const all=[c.id,c.name,c.variant,c.chart,c.difficulty,c.family,c.category,...c.tags].join(' ').toLowerCase();return tokens(els.q.value).every(t=>{const colon=t.indexOf(':');if(colon<0)return all.includes(t);const k=t.slice(0,colon),v=t.slice(colon+1);if(k==='line')return c.lines.includes(Number(v));const fields={chart:c.chart,kind:c.category,family:c.family+' '+c.name,id:c.id};return fields[k]===undefined?all.includes(t):String(fields[k]).toLowerCase().includes(v);});}
function render(){els.cards.querySelectorAll('video').forEach(v=>v.pause());els.cards.replaceChildren();const selected=CASES.filter(matches);els.count.textContent=selected.length+' recipes · '+new Set(selected.map(c=>c.family)).size+' families · '+new Set(selected.map(c=>c.chart)).size+' source titles';for(const c of selected){const card=element('article','card');card.id=c.id;card.append(element('div','badge',c.id+' · '+c.category.toUpperCase()));card.append(element('h3','',c.name));card.append(element('p','variant',c.variant));if(c.video){const v=element('video');v.controls=true;v.preload='none';v.playsInline=true;v.src=c.video;v.setAttribute('aria-label',c.name+' from '+c.chart+' '+c.difficulty);if(c.poster)v.poster=c.poster;v.addEventListener('play',()=>document.querySelectorAll('video').forEach(other=>{if(other!==v)other.pause();}));card.append(v);}else card.append(element('p','notice','Native video unavailable; source evidence and diagnostics are available.'));card.append(element('p','source',c.chart+' · '+c.difficulty));card.append(element('p','muted',c.start.toFixed(3)+'–'+c.end.toFixed(3)+' s chart · L'+c.lines.join(', L')+' · '+(c.audio==='original'?'source audio':'silent')));card.append(element('p','',c.construction));const links=element('div','links');for(const [name,url]of [['Recipe & diagnostics','cases/'+c.id+'.html'],['Exact events','evidence/'+c.id+'.json']]){const a=element('a','',name);a.href=url;links.append(a);}card.append(links);els.cards.append(card);}const state={q:els.q.value,category:els.category.value,family:els.family.value,difficulty:els.difficulty.value,audio:els.audio.value};try{localStorage.setItem('judgment-line-atlas-query',JSON.stringify(state));}catch{}}
for(const e of [els.q,els.category,els.family,els.difficulty,els.audio])e.addEventListener('input',render);document.getElementById('clear').onclick=()=>{for(const e of [els.q,els.category,els.family,els.difficulty,els.audio])e.value='';render();};document.querySelectorAll('[data-family]').forEach(b=>b.onclick=()=>{els.family.value=b.dataset.family;els.category.value='';els.q.value='';render();document.getElementById('bank').scrollIntoView();});try{const s=JSON.parse(localStorage.getItem('judgment-line-atlas-query')||'null');if(s)for(const k of ['q','category','family','difficulty','audio'])if(s[k]!==undefined)els[k].value=s[k];}catch{}render();
</script>'''.replace('INDEX_DATA',json.dumps(dataset,ensure_ascii=False,separators=(',',':')).replace('</','<\\/'))
    (ROOT/'index.html').write_text(shell('Judgment-line performance atlas',body,script));dump('search-index.json',dataset)
    with (ROOT/'index.csv').open('w',newline='')as stream:
        writer=csv.DictWriter(stream,fieldnames=['id','name','variant','category','family','chart','difficulty','lines','start','end','audio','video']);writer.writeheader();writer.writerows({k:(';'.join(map(str,c[k])) if k=='lines' else c[k])for k in writer.fieldnames} for c in dataset)
    print('Index built',len(bank),'recipes',native,'videos',flush=True)

if __name__=='__main__':
    import sys
    bank=json.loads((ROOT/'bank.json').read_text());receipts=json.loads((ROOT/'native-receipts.json').read_text())
    if '--index-only'not in sys.argv:make_details(bank,receipts)
    make_index(bank,receipts)
