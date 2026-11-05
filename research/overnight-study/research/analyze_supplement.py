import json,pathlib,math,collections,bisect,statistics,re,html,unicodedata
P=pathlib.Path('../research/overnight-study/corpus');R=P.parent/'research';M=json.loads((P/'supplemental-manifest.json').read_text())
def norm(s):return re.sub(r'[^\w]','',unicodedata.normalize('NFKD',s)).casefold()
# Extract chart origin/rechart versions and metadata from preserved wiki responses.
rows={};version=None
for f in [R/'wiki-source-early.txt',R/'wiki-source-0.txt',R/'wiki-source-at.txt']:
 for line in f.read_text().splitlines():
  a=re.search(r'#accordion\((1[67]\.\d)',line)
  if a:version=float(a[1])
  a=re.search(r'\|\[\[(.*?)\]\]\|&color\([^)]*\)\{(IN|AT)\};\|(.*)',line)
  if a and version:
   title=html.unescape(a[1].split('>')[0]); fields=a[3].split('|')
   if len(fields)>=5:rows[(norm(title),a[2])]=dict(wiki_constant=version,wiki_origin_version=fields[-2],wiki_line=line.strip(),wiki_notes=int(re.sub(r'[^0-9]','',re.sub(r'&color\([^)]*\)|[{};\']','',fields[1]))) if fields[1] else None)
dates={}
for f in R.glob('updates-window-*.txt'):
 ver=None
 for line in f.read_text().splitlines():
  a=re.search(r':\s+\*(\d+\.\d+\.\d+(?:\.\d+)?)\s',line)
  if a:ver=a[1]
  a=re.search(r'(20\d\d)年(\d{1,2})月(\d{1,2})日',line)
  if a and ver and ver not in dates:dates[ver]='%s-%02d-%02d'%(a[1],int(a[2]),int(a[3]))
# Retrieve values of native linear event segments at real seconds.
def evval(events,t,second=False):
 if not events:return 0
 starts=[x['startTime'] for x in events];i=max(0,bisect.bisect_right(starts,t)-1);e=events[i];f=max(0,min(1,(t-e['startTime'])/(e['endTime']-e['startTime']))) if e['endTime']!=e['startTime'] else 1
 return e.get('start2' if second else 'start',0)+(e.get('end2' if second else 'end',0)-e.get('start2' if second else 'start',0))*f
out=[]
for m in M:
 row=rows.get((norm(m['title']),m['difficulty']),{})
 # Japanese wiki alias accent restoration.
 if not row:
  row=next((v for (k,d),v in rows.items() if d==m['difficulty'] and (k.startswith(norm(m['title']).split('迷宮')[0]) and len(k)>4)),{})
 m.update(row);
 if m['title'].strip() in ['Retribution','零號車輛','Retribution ~ Cycle of Redemption ~'] and m['difficulty']=='IN':m['wiki_constant']=16.2
 origin=m.get('wiki_origin_version');latest=re.search(r'Re:(\d+\.\d+\.\d+)',origin or '')
 v=latest[1] if latest else (origin or '').split('(')[0]
 m['latest_creation_or_rechart_version']=v or None;m['latest_creation_or_rechart_date']=dates.get(v);m['recent_three_years']=dates.get(v,'0000')>='2023-10-01' if v else None
 m['date_source']='https://wikiwiki.jp/phigros/アップデート履歴/3';m['level_source']='https://wikiwiki.jp/phigros/高レベル譜面定数(CC)表'
 if m['id'].startswith(('EntrancetotheChaos','ExoplanetaryMirage')):
  m['latest_creation_or_rechart_version']='4.0.0';m['latest_creation_or_rechart_date']='2026-09-25';m['recent_three_years']=True;m['availability_note']='Playable in v4.0.0 as of 2026-10-01; individual wiki pages provide IN/AT unlock conditions. Oct2 continuation concerns later finale.';m['level_source']='https://wikiwiki.jp/phigros/Chapter%209%20隠し曲%20'+('4' if m['id'].startswith('Entrance') else '5');m['wiki_constant']=m['constant']
 d=json.loads(pathlib.Path(m['chart']['path']).read_text());notes=[];events=collections.Counter();lineinfo=[]
 for li,l in enumerate(d['judgeLineList']):
  factor=1.875/l['bpm'];ncount=0
  for side in ['notesAbove','notesBelow']:
   for n in l.get(side,[]):
    t=n['time']*factor+d.get('offset',0);end=t+n.get('holdTime',0)*factor
    notes.append(dict(t=t,end=end,type=n['type'],x=n['positionX'],line=li,side=side,speed=n.get('speed',1))) ;ncount+=1
  counts={k:len(l.get(k,[])) for k in ['speedEvents','judgeLineMoveEvents','judgeLineRotateEvents','judgeLineDisappearEvents']};events.update(counts)
  lineinfo.append(dict(line=li,bpm=l['bpm'],notes=ncount,event_counts=counts,rotation_range=[min((e.get('start',0) for e in l.get('judgeLineRotateEvents',[])),default=0),max((e.get('end',0) for e in l.get('judgeLineRotateEvents',[])),default=0)]))
 notes.sort(key=lambda x:x['t']);types=collections.Counter(n['type'] for n in notes);groups=collections.defaultdict(list)
 for n in notes:groups[round(n['t'],4)].append(n)
 chords=collections.Counter(len(v) for v in groups.values());times=[n['t'] for n in notes];end=max(n['end'] for n in notes);windows=[]
 for s in range(0,math.ceil(end),8):
  ns=[n for n in notes if s<=n['t']<s+8]
  if ns:windows.append(dict(start=s,end=s+8,notes=len(ns),types=dict(collections.Counter(n['type'] for n in ns)),active_lines=len(set(n['line'] for n in ns)),onset_chord_max=max(len(groups[round(n['t'],4)]) for n in ns)))
 peak=max((bisect.bisect_left(times,t+1)-i for i,t in enumerate(times)),default=0)
 hold_active_peak=0;active=[]
 for t,ns in sorted(groups.items()):
  active=[e for e in active if e>t+.0001];hold_active_peak=max(hold_active_peak,len(active)+len(ns));active.extend(n['end'] for n in ns if n['type']==3)
 # Representative objective motifs. Timing strictly seconds after audio start.
 motifs=[]
 for t,ns in sorted(groups.items(),key=lambda kv:len(kv[1]),reverse=True)[:5]:motifs.append(dict(kind='largest_raw_onset_group',time=t,notes=len(ns),types=dict(collections.Counter(n['type'] for n in ns)),lines=sorted(set(n['line'] for n in ns))))
 for w in sorted(windows,key=lambda w:w['notes'],reverse=True)[:3]:motifs.append(dict(kind='dense_eight_seconds',**w))
 for li,l in enumerate(d['judgeLineList']):
  factor=1.875/l['bpm']
  for e in l.get('judgeLineRotateEvents',[]):
   if 0<=e['startTime']*factor<=end and abs(e.get('end',0)-e.get('start',0))>=60 and e['endTime']>e['startTime']:
    motifs.append(dict(kind='large_rotation_segment',line=li,start=round(e['startTime']*factor,4),end=round(e['endTime']*factor,4),degrees_from=e['start'],degrees_to=e['end']));break
  if len(motifs)>18:break
 metrics=dict(id=m['id'],title=m['title'],difficulty=m['difficulty'],constant=m['constant'],format_version=d.get('formatVersion'),offset=d.get('offset'),note_count=len(notes),types={['','tap','drag','hold','flick'][k]:types[k] for k in range(1,5)},line_count=len(d['judgeLineList']),note_bearing_lines=sum(l['notes']>0 for l in lineinfo),last_note_end_seconds=end,mean_notes_per_second=len(notes)/(end-min(times)),peak_notes_in_one_second=peak,raw_onset_chord_histogram=dict(chords),raw_note_objects_plus_active_holds_peak=hold_active_peak,event_counts=dict(events),line_summary=lineinfo,section_windows=windows,representative_motifs=motifs)
 out.append(metrics)
(P/'supplemental-manifest.json').write_text(json.dumps(M,ensure_ascii=False,indent=2));(P/'supplemental-metrics.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));(R/'supplemental-version-dates.json').write_text(json.dumps(dates,indent=2))
print('metrics',len(out),'recent',sum(bool(m['recent_three_years']) for m in M),'dates unknown',sum(not m['latest_creation_or_rechart_date'] for m in M))
for m in M:
 if not m.get('wiki_origin_version'):print('unmatched wiki',m['title'],m['difficulty'])
