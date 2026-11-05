"""Build the offline cadence report after cadence.py."""
from html import escape
from cadence import ROOT, WINDOW, starts, chart, hashlib, json, np

rows=json.loads((ROOT/'cadence-windows.json').read_text())
assert len(rows)==344 and sum(r['counts'][0] for r in rows)==327041
assert all(len(s)==r['bins'] for r in rows for s in r['windows'].values())
def q(vals):
    return [round(float(v),2) for v in np.percentile(vals,[25,50,75])]
def mask(r,k):
    return np.frombuffer(r['windows'][k].encode(),dtype=np.uint8)==49
def table(head,rows):
    return '<table><thead><tr>'+''.join(f'<th>{x}</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{v}</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'
def spread(values,unit=''):
    lo,mid,hi=values
    return f'<b>{mid:g}{unit}</b> ({lo:g}–{hi:g}{unit})'
def rates(sets):
    return q([len(s)*120/r['bins'] for r,s in zip(rows,sets)])
def gaps(sets):
    return q([np.median(np.diff(s)*WINDOW) for s in sets if len(s)>=2])
def traces(r):
    svg='<svg viewBox="0 0 800 55" role="img" aria-label="{} time occupancy by row">'.format(escape(r['title']))
    for j,k in enumerate(['carrier_motion','background_motion','note_special']):
        a=mask(r,k);edges=np.flatnonzero(np.diff(np.r_[False,a,False])); color=['#427fab','#a35d31','#527744'][j]
        svg+=f'<rect x="0" y="{18*j}" width="800" height="14" fill="#e8e6df"/>'
        for start,end in zip(edges[::2],edges[1::2]):
            svg+=f'<rect x="{start*800/len(a):.2f}" y="{18*j}" width="{(end-start)*800/len(a):.2f}" height="14" fill="{color}"/>'
    return svg+'</svg>'
metrics={}
for k in rows[0]['windows']:
    sets=[mask(r,k) for r in rows]
    metrics[k]=dict(coverage=q([a.mean()*100 for a in sets]),charts=sum(bool(a.any()) for a in sets),
                    all_quarters=sum(all(part.any() for part in np.array_split(a,4)) for a in sets),
                    every_window=sum(bool(a.all()) for a in sets))
metrics['geometry']={'coverage':q([100*(mask(r,'travel')|mask(r,'turn')).mean() for r in rows])}
metrics['judging_conditional']={'coverage':q([100*mask(r,'judging_motion').sum()/mask(r,'judging').sum() for r in rows])}
episodes={}
for k in ['strong','note_special','carrier_strong','background_strong','sensitive','strict']:
    sets=[starts(mask(r,k)) for r in rows]
    episodes[k]=dict(rate=rates(sets),gap=gaps(sets),gap_charts=sum(len(s)>=2 for s in sets))
sets=[r['channel_entries'] for r in rows]
episodes['channel_entry']=dict(rate=rates(sets),gap=gaps(sets),gap_charts=sum(len(s)>=2 for s in sets))
cycles={}
for k in rows[0]['periods']:
    vals=[r['periods'][k][1] for r in rows if r['periods'][k][0]]
    cycles[k]=dict(charts=len(vals),period=q(vals))
note_shares={k:q([100*r['counts'][i]/r['counts'][den] for r in rows]) for k,i,den in
             [('downward_band',2,1),('sideward',3,1),('rising',4,1),('bend',5,1),('selected',6,1),('level',7,0),('hidden',8,0)]}
sens={str(gap):rates([starts(mask(r,'strong'),gap) for r in rows]) for gap in (0,1,2)}
summary=dict(charts=len(rows),windows=sum(r['bins'] for r in rows),note_counts=np.sum([r['counts'] for r in rows],axis=0).tolist(),
             counts_order=['all','screened','downward_band','sideward','rising','bend','selected_union','level','hidden','near_zero_speed','negative_speed'],
             note_share_percentiles=note_shares,window_metrics=metrics,episodes=episodes,periodic_examples=cycles,join_gap_sensitivity=sens)
p=ROOT.parent/'Xterfusion-Sol-20261102/export/chart.json'
mirror=chart(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),title='Xterfusion · Sol',difficulty='draft',id='independent'))
summary['independent_comparison']={k:round(100*mask(mirror,k).mean(),2) for k in ['motion','strong','note_special']}
(ROOT/'cadence-summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
html=['''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Judgment-line baseline and cadence</title><style>
body{background:#faf9f6;color:#262722;font:17px/1.55 system-ui;margin:auto;max-width:900px;padding:2rem 1rem 5rem}h1{font-size:clamp(2rem,5vw,3rem);line-height:1.1}h2{margin:2rem 0 .5rem}p{max-width:80ch}a{color:#19597b}table{border-collapse:collapse;width:100%;font-size:.92rem}th,td{text-align:left;vertical-align:top;padding:.5rem;border-bottom:1px solid #d5d4cc}th{background:#eae8df}svg{width:100%;height:auto;display:block}summary{cursor:pointer}small{color:#56584c}figure{margin:1.2rem 0}figcaption{margin-bottom:.3rem}@media(max-width:540px){th,td{padding:.25rem}table{font-size:.82rem}}</style>
<main><a href="index.html">Video pattern bank</a><h1>Judgment-line baseline and cadence</h1>
<p>Across 344 local official charts, some visible stroke activity occurred in every quarter of every playable span. Only 13 charts showed activity in every half-second window. A recurring movement vocabulary can carry a section while individual accents, formations and note paths enter or leave at different rates.</p>
<p>Results below use one vote per chart. Bold numbers are medians, with the middle half of charts in parentheses. The sample contains 327 IN charts and 17 selected AT charts. Chart-clock times below exclude the audio offset.</p>
<h2>What persists across a song</h2>''']
html.append(table(['Visible signal','Share of half-second windows','Charts with any'],[(label,spread(metrics[k]['coverage'],'%'),metrics[k].get('charts','—')) for k,label in [
    ('motion','Any visible travel, turn or opacity change'),('geometry','Travel or turn, excluding opacity-only activity'),('carrier_motion','Stroke on a line carrying notes somewhere in the song'),('background_motion','Stroke on a line empty for the entire song'),('travel','Travel normal to the stroke'),('turn','Stroke orientation changes'),('alpha','Opacity changes'),('strong','Any channel reaching the stronger threshold')]]))
html.append(f"<p>In windows containing a note head or continuing hold, the median share with visible activity on a line actually judging in that window was {spread(metrics['judging_conditional']['coverage'],'%')}. A note-carrying line can also perform when another line is receiving. The role-specific rows overlap.</p>")
html.append('''<p>60 charts had no detected activity on a wholly empty line. Some charts have brief rests, some sustain moving strokes for almost the whole track, and some hide a carrier while its notes travel. Requiring a decorative ensemble from beginning to end would miss these differences.</p><h2>What the notes themselves do</h2>''')
html.append(table(['Head or approach measure','Share within chart'],[(label,spread(note_shares[k],'%')) for k,label in [
    ('level','All heads landing within 10° of a horizontal line (either facing)'),('hidden','All heads on a line with opacity ≤1% at judgment'),('downward_band','Screened heads descending at least 0.12 screen heights within a narrow vertical band'),
    ('sideward','Screened heads with a sideways-dominant arrival'),('rising','Screened heads with an upward arrival'),('bend','Screened heads bending away from the start-to-landing segment'),('selected','Any of sideways, upward or bent')]]))
html.append('''<p>The head screen admitted 323,175 of 327,041 notes. The three selected shapes overlap. The remaining approaches include modest diagonals, briefer movement and speed effects. A narrow descending path can still change speed or ride a moving line.</p><h2>Three different clocks</h2>
<p><b>1. Repetition inside a phrase.</b> These are same-kind, same-line cycles found in runs of at least four regular pulses or peaks. Each reporting chart contributes its own median interval. The estimates measure recurring screen behavior. Audio or a transcription is needed to identify the instrument.</p>''')
html.append(table(['Repeated signal','Charts qualifying','Seconds per repetition'],[(label,cycles[k]['charts'],spread(cycles[k]['period'],' s')) for k,label in [
    ('carrier_dip','Downstroke trough on a nearly horizontal note-carrying line'),('carrier_flash','Opacity crosses from low to bright on a note-carrying line'),('bg_flash','Opacity crosses from low to bright on a wholly empty line'),('carrier_rock','Angular peak on a note-carrying line')]]))
html.append('''<p><b>2. A component of the formation changes.</b> A stroke begins showing strong travel, rotation or opacity activity after that channel had gone quiet. This can happen while another component continues. Simultaneous entries count once.</p><p><b>3. A new episode begins.</b> A stronger visible stroke run or a cluster of affected note heads starts after a break. Joining one empty half-second window prevents a brief dip within a response from splitting the phrase.</p>''')
html.append(table(['Entry detector','Starts per minute','Within-chart start-to-start gap','Charts with ≥2'],[(label,spread(episodes[k]['rate']),spread(episodes[k]['gap'],' s'),episodes[k]['gap_charts']) for k,label in [
    ('channel_entry','New strong channel within either line role'),('strong','Strong visible scene episode'),('note_special','Sideways, rising or bent note-head cluster')]]))
html.append('''<p>Start-to-start gaps include the preceding active run. Rates include charts with zero or one entry. Gaps use charts with at least two. A continuous spin can have one onset, many musical accents and thousands of exported events. Geometry alone cannot count changes of artistic theme.</p>
<h2>Source witnesses</h2><ul>
<li><a href="cases/B034.html">Non-Melodic Ragez IN · L2 · 3–6 s</a>. Ten visible entries from about 3.22 to 5.86 s, spaced by about 0.293 s, one chart beat at 205 BPM. These are repetitions of one strobe motif.</li>
<li><a href="cases/B022.html">Believe Light IN · L3 · 60–63 s</a>. The rocking stroke changes direction at about 60.33, 61.00, 61.67 and 62.33 s. The 0.667 s spacing is two chart beats at 180 BPM. Reversals and full cycles are different units.</li>
<li><a href="cases/B070.html">Stardust:RAY IN · L17–20 · 82–84.15 s</a>. Four empty lines sustain a moving comb. L17 stays visible through the passage. Translation supplies continuity without repeated flashes.</li>
<li><a href="cases/N091.html">A journey to the moonlight IN · L4 · 80.23–82.41 s</a>. A group of notes forms an arch. A special can be a shape read across several notes, even when no large visible rail movement signals its onset.</li></ul>
<h2>Whole-chart timelines</h2><p>Top row shows visible motion on note-carrying lines, middle row on wholly empty lines, bottom row a screened special note head at judgment. Time runs from first head to last head or hold end. Each strip is normalized to its own duration.</p>''')
for key in ['C046','C169','C032','C227','independent']:
    r=mirror if key=='independent' else next(r for r in rows if r['id']==key)
    html.append(f"<figure><figcaption><b>{escape(r['title'])}</b> · {r['difficulty']} · {r['first']:.1f}–{r['last']:.1f} s · any stroke activity in {mask(r,'motion').mean()*100:.0f}% of windows</figcaption>{traces(r)}</figure>")
html.append('''<p>The independent Xterfusion Sol draft is shown for comparison and excluded from the official statistics. Its exported chart has visible change in 6.7% of windows, all on the background pair. The median official chart has visible change in 91.4%. These are occupied windows rather than exact seconds spent moving.</p>
<h2>Measurement details</h2>
<p>All 344 frozen source hashes were checked. Each chart contributes full 0.5 s windows from the first note to the last judgment or hold end (93,056 windows total); any remaining fraction is omitted. The scan samples every 50 ms using the line’s local BPM. A visible stroke has opacity above 5% and an infinite centerline intersecting a 16:9 viewport. This approximation can include finite strokes outside the viewport, and sampling can miss short flashes and very fast turns. The original bank's native clips ground the worked examples; corpus totals are source reconstructions.</p>
<p>Within each window, sum absolute adjacent changes per line while visible: translation perpendicular to the stroke in screen-height units, shortest unoriented angular differences, and clamped opacity changes while the stroke intersects the screen. Visibility transitions contribute opacity even if only one endpoint exceeds 5%. The ordinary thresholds are 0.015 heights, 2° or 0.05 opacity. Strong thresholds are 0.12 heights, 18° or 0.30 opacity. A chart window counts once if any one eligible line passes one threshold. Along-line translation of a level stroke alone does not displace its visible centerline. Hidden carriers and offscreen strokes need separate note-path analysis.</p>
<p>At each note head, project the previous 1.5 s of approach at 20 Hz, including line transforms and integrated scroll speed. Require a contiguous on-screen final suffix of at least 0.149 s. Screen width is expressed in screen-height units. Sideward needs net horizontal travel ≥0.15 heights and at least as large as vertical travel. Rising needs net upward travel ≥0.15 heights. Bending needs a deviation ≥0.06 heights from the segment connecting endpoints. The descending band uses net descent >0.12 heights and horizontal span <0.05 heights. Holds are assessed at their heads. These proxies omit speed-only changes, hold-body choreography, between-note silhouettes and semantic motif changes.</p>
<p>Recurring cycles require three successive intervals between 0.15 and 2 s with spread ≤20% of their median (at least 51 ms allowance for sampling). Flashes require a rise from ≤0.10 to ≥0.25 opacity while geometrically on screen. Rocking peaks require a confirmed 5° rise and fall while visible; vertical troughs need 0.03 screen heights and orientation within 15° of horizontal. Intervals are deduplicated across overlapping runs on the same signal; synchronous lines can still represent one formation. A carrier dip detector establishes neither contact nor drum synchronization.</p>''')
html.append(f"<p>Lowering or raising all strong thresholds by 25% gives median strong coverage of {metrics['sensitive']['coverage'][1]:g}% and {metrics['strict']['coverage'][1]:g}%. Bridging zero, one or two empty windows gives {sens['0'][1]:g}, {sens['1'][1]:g} and {sens['2'][1]:g} strong episodes/min respectively. Use consistent definitions when comparing drafts. Short chart-level quiet gaps and simultaneous independent motions make these rates sensitive to segmentation.</p>")
html.append('''<p><a href="cadence-summary.json">Summary data</a> · <a href="cadence-windows.json">Per-chart masks and intervals</a> · <a href="cadence.py">Source scan</a> · <a href="cadence_report.py">Aggregation</a></p></main></html>''')
(ROOT/'cadence.html').write_text('\n'.join(html))
