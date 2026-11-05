"""Build a local, self-contained research index with relative media links."""
import os,json,html,hashlib,shutil,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ['MPLCONFIGDIR']=str(ROOT/'mpl-cache')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from analyze_librosa import SONGS
from importlib.metadata import version

COPY={
'crush-beta':[
 ('Release, reduction, rebuild',
  'The mix falls 9.4 dB relative to the preceding eight chart beats. The separated drum estimate falls 14.3 dB and the bass estimate nearly disappears, while accompaniment remains. The middle third is the quietest; percussive texture rises again in the final third. All-In-One does not mark the start of this local change: it keeps a chorus label until 110.40 s.',
  'At 100–103 s, taps, flicks and broad hold bodies float within a rectangular line frame. By 106.50 s the sampled scene has reduced to a single yellow note. The lower frame and approaching notes return before the first judgment at 110.10 s.',
  'The visual population thins with the arrangement, then prepares the return. The choreography has its own reduction and rebuilding arc inside a section the model treats as one block.')],
'aphrodites-child':[
 ('A rhythmic passage handed to the visuals',
  'All-In-One places a break boundary at 62.34 s. The gap is 4.7 dB quieter than the preceding eight beats, but detected onset rate rises from 4.27 to 6.96 per second. Drum and bass estimates soften; the sound is still articulated. Gameplay resumes at 70.78 s while the model continues to label the music a break.',
  'The normal horizontal layout clears. Individual blue notes drift across the field; a stepped group of yellow notes appears around 67.75 s. Near 70.43 s a rectangular frame returns and the scattered notes begin resolving into play.',
  'The chart chooses to show musical articulation as spatial movement. A break label does not require empty audio, and the no-hit interval need not occupy the entire musical section.'),
 ('An outro with a delayed final gesture',
  'The model places the outro at 152.34 s, shortly after the gap begins. Average mix level falls 12.6 dB from the preceding passage; afterward it falls further. The final notes do not announce another energetic section.',
  'After the held-note ending, lines gather into a rotating radial figure. Two yellow notes appear close to the end and are judged at 163.48 s; the line figure continues beyond them.',
  'A late pair of judgments can act as punctuation within a decaying ending. The animation supplies continuity while the player waits.')],
'frozen-heart':[
 ('The foreground continues while percussion withdraws',
  'The drum estimate falls about 12.0 dB, while the vocal estimate is almost unchanged (−16.77 to −16.74 dBFS). The model marks a chorus entrance at 33.08 s, almost exactly the next chart judgment at 33.081 s. This is a change in the balance of layers, not silence.',
  'The first part of the gap uses sparse lines; a small snowflake-like group of playable notes appears later, visible around 29.11 s. It travels across the diagonal-line field. Ordinary approaches return near the chorus entrance.',
  'The chart gives attention to the continuing foreground through a light visual motif, then restores physical activity with the structural return.'),
 ('A line drawing takes over the ending',
  'The model marks an outro at 175.78 s. During the gap the mix becomes 6.3 dB quieter than the preceding passage; in the following window the drum estimate is extremely low while the vocal estimate remains present.',
  'The preceding notes disappear and the judge lines assemble into a star-like drawing. Yellow notes only re-enter near 184.86 s. The star here is primarily line geometry, distinct from the earlier note snowflake.',
  'A related visual vocabulary can return in a different medium and musical role: first a note motif, later a line-led coda.')],
'brain-hacker':[
 ('A change of foreground, followed by a restrained return',
  'All-In-One places a boundary at 62.28 s, matching the gap start. Demucs shifts energy toward its bass and vocal-like components while the drum estimate falls 8.2 dB. After the gap, the mix is quieter still, but detected onset rate rises from 2.88 to 5.27 per second. Stem names are estimates, particularly for processed electronic sounds.',
  'Large sideways hold bodies cross vertical lines, followed by a column of red flick notes. The column separates and clears; the frame and ordinary approaches return around 74.43 s.',
  'The chart presents a musical figure as a graphic object. It resumes hitting for renewed articulation, without waiting for a loudness peak or the next model section at 85.06 s.')],
'ranbu':[
 ('A melodic foreground with only a few visual objects',
  'The whole mix falls only 2.7 dB. The separated accompaniment estimate becomes 4.4 dB stronger while bass and drums recede; the onset detector remains active. All-In-One retains a solo label across the passage, with a boundary at 51.42 s.',
  'Isolated yellow notes travel along sweeping judge lines, alternating with nearly empty line-only views. Samples at 53.5–59.5 s show this sparse sequence. The return at 61.84 s comes within the model-labelled solo passage.',
  'The musical foreground can become more prominent while playable activity disappears. A small number of objects can carry the phrase without filling the screen.'),
 ('An ending that leaves room around the final notes',
  'The model marks an outro at 110.20 s, matching the gap start. The mix falls 10.2 dB and the drum estimate falls 15.0 dB. Accompaniment persists through the gap; the post-gap window is quieter again.',
  'Two yellow notes form a small cross near 111.20 s, followed by crossed lines and an almost empty view at 117.48 s. Four final yellow notes then enter on diagonals and are judged around 121.22 s. They resolve the scene rather than restarting a dense chart.',
  'The absence of play and the absence of visible notes can overlap deliberately. The arrival of the final group gains emphasis from the space before it.')]
}

def esc(x):return html.escape(str(x))
def para(label,text):return f'<p><b>{label}.</b> {esc(text)}</p>'
def stem_plot(key,lib,aio,stems):
 z=np.load(ROOT/'librosa'/f'{key}.npz')
 fig,axes=plt.subplots(3,1,figsize=(14,6.4),sharex=True,gridspec_kw={'height_ratios':[.65,2,1.5]})
 colors={'intro':'#e0bc67','verse':'#73b5d4','chorus':'#e98787','break':'#b9a0e8','outro':'#9fabc2','inst':'#83c4a5','solo':'#b3c882','start':'#ddd','end':'#ddd'}
 for s in aio['segments']:
  axes[0].axvspan(s['start'],s['end'],color=colors.get(s['label'],'#ddd'),alpha=.8)
  if s['end']-s['start']>4:axes[0].text((s['start']+s['end'])/2,.5,s['label'],ha='center',va='center',fontsize=8)
 axes[0].set_yticks([]);axes[0].set_ylabel('Model',rotation=0,labelpad=27)
 for name,values in stems['stems'].items():
  axes[1].plot([v['seconds'] for v in values],[v['rms_dbfs'] for v in values],label=name,lw=.9)
 axes[1].set_ylim(-65,-5);axes[1].set_ylabel('Stem RMS / dBFS');axes[1].legend(ncol=4,loc='lower left')
 from scipy.ndimage import gaussian_filter1d
 axes[2].plot(z['time'],gaussian_filter1d(z['onset'],8),color='#694a99',lw=.9);axes[2].set_ylabel('Onset strength');axes[2].set_xlabel('Audio seconds')
 for ax in axes:
  for g in lib['gaps']:ax.axvspan(g['from'],g['to'],color='#00bac7',alpha=.15)
  ax.grid(alpha=.16)
 axes[2].set_xlim(0,lib['duration']);fig.suptitle(lib['title']+' — cyan spans mark no-hit intervals');fig.tight_layout();fig.savefig(ROOT/'librosa'/f'{key}-flow.png',dpi=130);plt.close(fig)

def main():
 stems=json.loads((ROOT/'stem-analysis.json').read_text())
 versions={x:version(x) for x in ['allin1','librosa','demucs','torch','torchaudio','natten','madmom']}
 provenance={'model':'harmonix-fold0','versions':versions,'songs':[],'note':'All-In-One full songs, CPU inference; upstream HTDemucs on MPS. Original reference charts converted without easing fitting for native render review. No claims of human playtesting.'}
 chunks=['''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Song flow & Override — PhiChain study</title>
<style>:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#10151c;color:#e6e8ec;font:16px/1.65 system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:52px 28px}h1{font-size:clamp(34px,5vw,56px);line-height:1.08;letter-spacing:-.035em;margin:12px 0 24px}h2{font-size:29px;margin:42px 0 12px}h3{font-size:22px;margin:28px 0 10px}p{max-width:88ch}a{color:#9ddbec}small,.muted{color:#aab5c5}.eyebrow{font:12px monospace;letter-spacing:.13em;color:#8ed0c2}video,img{max-width:100%;border-radius:9px}video{width:100%;background:#000}figure{margin:22px 0}figcaption{font-size:13px;color:#aab5c5;margin-top:7px}.card{border:1px solid #34404c;border-radius:14px;padding:24px;margin:22px 0;background:#151d27}.chips{display:flex;gap:9px;flex-wrap:wrap;margin:18px 0}button,.chip{border:1px solid #465362;border-radius:24px;padding:8px 14px;background:#202c39;color:#e6e8ec;font:inherit;cursor:pointer}.chip{text-decoration:none}button:hover,a.chip:hover{background:#324455}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:9px 10px;border-bottom:1px solid #34404c}th{color:#aab5c5}details{margin:18px 0}summary{cursor:pointer;color:#9ddbec}code{font:13px monospace}hr{border:0;border-top:1px solid #34404c;margin:46px 0}.callout{border-left:3px solid #81c8ba;padding:2px 0 2px 20px}nav{display:flex;flex-wrap:wrap;gap:16px;margin:24px 0}footer{margin:45px 0;color:#aab5c5;font-size:13px}</style><main>
<div class="eyebrow">PHICHAIN · LOCAL RESEARCH & AUTHORING · 22 OCTOBER 2026</div><h1>When the hands stop,<br>the phrase keeps moving.</h1>
<p>Five reference charts, eight extended no-hit passages, and a new full-song Override visual study. The analysis separates measured audio changes, observed chart motion, and artistic interpretation.</p>
<nav><a href="#override">Override chart</a><a href="#findings">What changed my understanding</a><a href="#references">Reference passages</a><a href="#method">Methods & evidence</a></nav>
<section id="override"><h2>Override — Fractured Symmetry</h2><p>A brisk, orderly surface that opens into angled motion, then gathers into a rotating note figure. This is a visual chart draft, not a rated difficulty or a claim of finished playability.</p>
<video id="override-video" controls preload="metadata" src="override-full.mp4"></video>
<div class="chips"><button data-time="0">Opening</button><button data-time="12.1">Sparse vocal texture</button><button data-time="37.9">First return</button><button data-time="59">Instrumental ring</button><button data-time="88.2">Refrain return</button><button data-time="108.2">Final refrain</button><button data-time="129">Closing motif</button></div>
<p><a href="override-full.mp4">Full video · 720p / 60 fps / 2:18.53</a> · <a href="override-emotion/chart.json">Native chart</a> · <a href="override-emotion/meta.json">Project metadata</a></p>
<p><b>393 playable notes · 16 lines · maximum two simultaneous judgments.</b> Eight ordinary playable notes form the ring, rotate while their approach is suspended, then separate into two-note pairs. The later copy of the motif stays out of view during the first scene. The final hit is at 136.524 s.</p>
<p>The original <code>Music/PhiChain/Override-opening</code> project is preserved. The new chart was edited and saved through the running editor’s guarded bridge, with shared undo entries. Its project folder is <code>../research/music-flow-study/override-emotion</code>.</p>
<h3>How the music guided this draft</h3>
<p>All-In-One finds major returns at 39.14, 88.56 and 108.57 s. The chart places the corresponding paired accents at 39.172, 88.583 and 108.583 s on the existing 204 BPM grid. The model hears a 102 BPM pulse; that is compatible with the chart’s doubled grid. I retained the established 348 ms offset. Detected audio attacks align with that half-beat grid throughout the song, without accumulating drift.</p>
<p>The separated vocal track is nearly absent during the opening and around 59–68 s and 128–138 s. Those instrumental areas give the repeated visual motif a reason to exist. In the sparse vocal passages, the frame is quieter and movement is tighter. The refrains widen the frame and increase the line angles; the final refrain enlarges that gesture.</p>
<p>The emotional interpretation is mine: bright, insistent motion with tension beneath its symmetry. The creator’s interview describes the song’s uptempo sound alongside its darker atmosphere, and his emphasis on the impact of the refrain. <a href="https://withnews.jp/article/f0240521000qq000000000000000W07n10201qq000026919A">Creator interview</a>.</p>
<figure><img src="librosa/override-flow.png" alt="Override section estimates, separated stem levels and onset strength"><figcaption>Section labels are model predictions. The stem plot reveals instrumental passages that those labels merge into larger sections.</figcaption></figure></section>
<section id="findings"><h2>What changed my understanding</h2><div class="callout"><p><b>The useful question is which musical layer carries the passage, and what role the player should have during it.</b> Overall loudness and note density alone are not enough.</p></div>
<ol><li><b>A no-hit passage can remain rhythmically active.</b> Aphrodite’s Child and Ranbu retain frequent attacks. Their charts transfer attention to moving shapes.</li><li><b>Layer changes are more revealing than total energy.</b> Frozen Heart’s first gap reduces the estimated drums by about 12 dB while the vocal estimate remains almost unchanged.</li><li><b>The return can happen inside a musical section.</b> BRAIN HACKER and Aphrodite’s Child resume play before the next major model boundary. Re-entry can follow a local articulation rather than a chorus.</li><li><b>Endings use a different grammar.</b> The later gaps often resolve into a few final notes while the music continues to thin. They do not need a large final burst.</li><li><b>Analysis is evidence, not an instruction.</b> All-In-One misses Crush BETA’s local reduction and merges Override’s instrumental passage into a chorus. Librosa and separated stems help expose those distinctions.</li></ol></section>
<section id="references"><h2>Reference passages</h2><p>All times are audio seconds. The before/after comparison windows each span eight chart beats. No-hit intervals exclude ongoing hold tails; a note drawn early is still playable later. Cyan spans in the plots mark the measured intervals.</p>''']
 for title,filename,index,gaps in SONGS:
  key=title.lower().replace(' ','-').replace("'",'');stem=Path(filename).stem
  lib=json.loads((ROOT/'librosa'/f'{key}.json').read_text());aio=json.loads((ROOT/'allin1'/f'{stem}.json').read_text())
  stem_plot(key,lib,aio,stems[key])
  provenance['songs'].append({'title':title,'audio_sha256':lib['sha256'],'audio_path':lib['path'],'allin1':f'allin1/{stem}.json','librosa':f'librosa/{key}.json'})
  if index is None:continue
  src=ROOT/'references'/key/'source-official.json';shutil.copyfile(f'/tmp/phigros-research-{index}.json',src)
  provenance['songs'][-1]['chart_sha256']=hashlib.sha256(src.read_bytes()).hexdigest()
  chunks.append(f'<article class="card"><h2>{esc(title if key!="ranbu" else "亂★舞 / Ranbu")}</h2><figure><img loading="lazy" src="librosa/{key}-flow.png" alt="{esc(title)} music flow"><figcaption>Predicted sections above, separated stem levels in the middle, onset strength below.</figcaption></figure>')
  for j,(a,b) in enumerate(gaps):
   heading,music,visual,meaning=COPY[key][j]
   chunks.append(f'<h3>{a:.2f}–{b:.2f} s · {b-a:.2f} s without hits</h3><p class="eyebrow">{esc(heading.upper())}</p>'+para('Measured music',music)+para('Observed animation',visual)+para('Interpretation',meaning))
   chunks.append(f'<video controls preload="none" src="references/{key}/gap-{j+1}.mp4" poster="references/{key}/gap-{j+1}-frame-2.png"></video><p class="muted">Clip starts at {max(0,a-1):.3f} s in the song and includes one second before and after the gap.</p>')
   g=lib['gaps'][j];st=stems[key]['gap_comparisons'][j]
   chunks.append('<details><summary>Measurements and sampled frames</summary><table><tr><th>Window</th><th>Mix dBFS</th><th>Drum estimate dBFS</th><th>Detected attacks / s</th></tr>')
   for label in ['before','gap','after']:
    w=g['windows'][label];chunks.append(f'<tr><td>{label}</td><td>{w["rms_dbfs"]:.2f}</td><td>{st["windows"][label]["drums"]:.2f}</td><td>{w["detected_onsets_per_second"]:.2f}</td></tr>')
   chunks.append(f'</table><img loading="lazy" src="references/{key}/gap-{j+1}-sheet.jpg" alt="Six native rendered frames across the passage"></details>')
  chunks.append(f'<details><summary>All-In-One output and raw evidence</summary><p><a href="allin1/{esc(stem)}.json">All-In-One JSON</a> · <a href="librosa/{key}.json">Librosa measurements</a> · <a href="references/{key}/source-official.json">Original reference chart</a></p><table><tr><th>Start</th><th>End</th><th>Predicted label</th></tr>')
  for s in aio['segments']:chunks.append(f'<tr><td>{s["start"]:.2f}</td><td>{s["end"]:.2f}</td><td>{esc(s["label"])}</td></tr>')
  chunks.append('</table></details></article>')
 chunks.append('''</section><section id="method"><h2>Methods and limits</h2>
<p><a href="https://github.com/mir-aidj/all-in-one">All-In-One</a> ran on all six complete songs with the upstream <code>harmonix-fold0</code> pretrained model. This is a single fold, not the eight-model ensemble. HTDemucs source separation ran on the Mac GPU and attention inference on the CPU. The first ensemble attempt was stopped in favor of this practical local configuration; its partial work is not reported as a result.</p>
<p><a href="https://librosa.org/doc/0.11.0/">Librosa 0.11.0</a> measured RMS, harmonic/percussive texture, spectral centroid, chroma, onset strength and candidate feature-change boundaries at 22,050 Hz, a 2,048-sample FFT and a 256-sample hop. The candidate boundaries compare two-second windows. Onset counts are detector output, not counts of instruments or playable notes. Median HPSS separates textures; Demucs’ four stems are model estimates and can contain leakage.</p>
<p>Reference chart data came from <a href="https://github.com/ggmolly/phigros-tools">phigros-tools</a>; audio came from the <a href="https://github.com/7aGiven/Phigros_Resource/tree/music">Phigros_Resource music branch</a>. Native PhiChain renders were inspected at sampled times, including the transitions into and out of the gaps. The report offers the continuous clips for listening and visual review. Emotional descriptions are interpretations of these observations, not labels produced by the audio models.</p>
<p>Override was reviewed in native rendered frames at the opening, major returns, both note figures and the end. Structural checks confirm finite events, notes within the audio duration, no overlapping events within a carrier channel, and at most two simultaneous judgments. This is not a human playtest or a comprehensive ergonomic validation.</p>
<p><a href="provenance.json">Versions, hashes and source paths</a> · <a href="stem-analysis.json">Separated-stem measurements</a> · <a href="validation.json">Final chart validation</a> · <a href="analyze_allin1.py">All-In-One run script</a> · <a href="analyze_librosa.py">Librosa run script</a></p></section>
<footer>All charts, audio, model caches and renders remain local under the ignored study folder. No repository source code was edited and nothing was published.</footer>
<script>document.querySelectorAll('[data-time]').forEach(b=>b.addEventListener('click',()=>{const v=document.getElementById('override-video');v.currentTime=Number(b.dataset.time);v.scrollIntoView({behavior:'smooth',block:'center'});}));</script></main></html>''')
 (ROOT/'provenance.json').write_text(json.dumps(provenance,indent=2,ensure_ascii=False))
 (ROOT/'index.html').write_text('\n'.join(chunks))
 print(ROOT/'index.html')
if __name__=='__main__':main()
