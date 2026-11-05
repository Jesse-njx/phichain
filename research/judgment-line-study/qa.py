"""Check artifacts, extract native frame evidence, and record coverage without editing sources."""
from publish import *
from PIL import Image, ImageDraw, ImageFont
import hashlib

def merge_receipts():
    values=[];seen=set()
    for path in [ROOT/'native-receipts.json',*sorted(ROOT.glob('native-receipts-part*.json'))]:
        if not path.exists():continue
        try:data=json.loads(path.read_text())
        except ValueError:continue
        for r in data:
            key=json.dumps(r,sort_keys=True)
            if key not in seen:values.append(r);seen.add(key)
    dump('native-receipts.json',values);return values

def frames_and_posters(bank,receipts):
    qa=ROOT/'qa';qa.mkdir(exist_ok=True);posters=ROOT/'posters';posters.mkdir(exist_ok=True);font=ImageFont.truetype('/System/Library/Fonts/Hiragino Sans GB.ttc',13)
    success=[];manifest=[]
    for c in bank:
        r=matching_receipt(c,receipts)
        if not r:continue
        video=Path(r['video']);duration=r['chart_seconds'][1]-r['chart_seconds'][0]
        for j,frac in enumerate([.1,.5,.9]):
            dest=qa/(c['id']+f'-{j}.jpg')
            if not dest.exists():subprocess.run(['ffmpeg','-v','error','-y','-ss',str(duration*frac),'-i',str(video),'-frames:v','1','-vf','scale=320:180','-q:v','3',str(dest)],check=True,capture_output=True)
        poster=posters/(c['id']+'.jpg')
        if not poster.exists():poster.write_bytes((qa/(c['id']+'-1.jpg')).read_bytes())
        success.append(c);manifest.append(dict(id=c['id'],video=str(video),source_sha256=c['source']['sha256'],mechanism=c['mechanism'],chart_seconds=r['chart_seconds'],audio=r['audio']))
    sheets=[]
    for k in range(0,len(success),5):
        group=success[k:k+5];sheet=Image.new('RGB',(960,len(group)*214),'#101419');draw=ImageDraw.Draw(sheet)
        for row,c in enumerate(group):
            label=f'{c["id"]} | {c["definition"]["name"]} | {c["source"]["title"]} {c["source"]["difficulty"]} | L{c["lines"]} | {c["start"]:.3f}-{c["end"]:.3f}s'
            draw.text((8,row*214+6),label,font=font,fill='white')
            for j in range(3):sheet.paste(Image.open(qa/(c['id']+f'-{j}.jpg')),(j*320,row*214+30))
        filename=f'native-sheet-{k//5+1:03}.jpg';sheet.save(qa/filename,quality=90);sheets.append(dict(path=str(qa/filename),ids=[c['id']for c in group]))
    dump('native-frame-sheets.json',sheets);dump('final-render-manifest.json',manifest);print('Native QA',len(success),'videos',len(sheets),'sheets',flush=True)

def verify(bank,receipts):
    inventory=json.loads((ROOT/'inventory.json').read_text())['charts'];issues=[];checks=collections.Counter()
    for r in inventory:
        if hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()!=r['sha256']:issues.append('source hash '+r['id'])
        checks['source_hashes']+=1
    for c in bank:
        d=json.loads(Path(c['source']['path']).read_text());e=json.loads((ROOT/'evidence'/(c['id']+'.json')).read_text())
        for line in e['lines']:
            for item in line['events']+line['notes']:
                v=d
                for key in item['pointer'].split('/')[1:]:v=v[int(key)] if isinstance(v,list) else v[key]
                if v!=item.get('event',item.get('note')):issues.append('pointer '+c['id']+item['pointer'])
                checks['exact_source_pointers']+=1
        if c['category']=='background':
            if any(d['judgeLineList'][i]['notesAbove']or d['judgeLineList'][i]['notesBelow'] for i in c['lines']):issues.append('background has notes '+c['id'])
            checks['background_cases_checked']+=1
        r=matching_receipt(c,receipts)
        if r:
            cp=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height,duration,nb_frames','-of','json',r['video']],capture_output=True,text=True)
            try:
                s=json.loads(cp.stdout)['streams'][0]
                if int(s['width'])!=960 or int(s['height'])!=540 or int(s.get('nb_frames',0))<2:issues.append('video format '+c['id'])
                if abs(float(s['duration'])-(r['chart_seconds'][1]-r['chart_seconds'][0]))>.2:issues.append('video duration '+c['id'])
                checks['native_videos_checked']+=1
            except (ValueError,KeyError,IndexError):issues.append('video unreadable '+c['id'])
        for p in [ROOT/'cases'/(c['id']+'.html'),ROOT/'evidence'/(c['id']+'.json')]:
            if not p.exists():issues.append('missing '+str(p))
    dump('verification.json',{'checks':dict(checks),'issues':issues,'recipe_count':len(bank),'mechanism_count':len(set(c['mechanism']for c in bank)),'native_missing':[c['id']for c in bank if not matching_receipt(c,receipts)],'scope':'Source integrity, exact pointers, background emptiness and native video metadata. Visual frame review and browser checks are recorded separately.'});print('Verification',dict(checks),'issues',issues,flush=True)

if __name__=='__main__':
    import sys
    b=json.loads((ROOT/'bank.json').read_text());r=merge_receipts()
    if '--verify-only'not in sys.argv:frames_and_posters(b,r)
    if '--frames-only'not in sys.argv:verify(b,r)
