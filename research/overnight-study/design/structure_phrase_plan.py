"""Convert prose study plan to structured proposal records; does NOT author notes."""
import pathlib,json,re,math
R=pathlib.Path(__file__).resolve().parents[1]
text=(R/'design/proposed-original-at-plan.md').read_text()
c=json.loads((R/'corpus/chart/RetributionCycleofRedemption.ArdolfvsDaily天利.0/IN.json').read_text())
ns=[dict(beat=n['time']/32,kind=n['type'],tail=n['time']/32+n['holdTime']/32) for l in c['judgeLineList'] for side in ['notesAbove','notesBelow'] for n in l[side]]
blocks=json.loads((R/'design/audio-four-bar-evidence.json').read_text())
rows=[]
for line in text.splitlines():
 if not re.match(r'^\|\d',line):continue
 fields=line.strip('|').split('|');beats=fields[0].split('–');start,end=map(float,beats)
 selected=[n for n in ns if start<=n['beat']<end]
 energy=[b for b in blocks if b['beat_start']<end and b['beat_start']+16>start]
 rows.append(dict(status='PROPOSED_STUDY_ONLY_NOT_AUTHORED',beat_start=start,beat_end=end,time_start_s=start*60/225,time_end_s=end*60/225,source_observation=fields[2],proposed_roles=fields[3],proposed_cosmetic_and_recovery=fields[4],source_head_count=len(selected),source_types={str(k):sum(n['kind']==k for n in selected) for k in range(1,5)},source_holds_active_at_start=sum(n['kind']==3 and n['beat']<start<n['tail'] for n in ns),overlapping_audio_four_bar_blocks=[b['four_bar'] for b in energy],instrument_labels='provisional',playing_line_policy='one main playing line; carrier heads resolve onto it; held contacts remain fixed'))
out=dict(status='STUDY_PLAN_GATE_ACTIVE',song='Retribution ~ Cycle of Redemption ~',composer='Ardolf vs. Daily天利',bpm_evidence=225,offset_evidence_s=0,audio_duration_s=173.79120181405895,original_notes_authored=0,sections=rows)
(R/'design/proposed-phrase-map.json').write_text(json.dumps(out,indent=2,ensure_ascii=False))
print('sections',len(rows),'last_s',rows[-1]['time_end_s'],'original notes authored',0)
