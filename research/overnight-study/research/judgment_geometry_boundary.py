"""Source-derived strip illustration, explicitly simulator hypothesis not gameplay."""
from pathlib import Path
import json,math
from PIL import Image,ImageDraw,ImageFont
B=Path('/Users/jesse/Projects/PhiChain/research/overnight-study/research');r=json.loads((B/'deep-recent/50-IN/case-data.json').read_text());h=r['windows'][0]['sustain_answer_witnesses'][0];im=Image.new('RGB',(1440,580),'#10141b');d=ImageDraw.Draw(im);font=ImageFont.truetype('/Users/jesse/Projects/PhiChain/phichain/assets/font/MiSans-Regular.ttf',18)
for k,title in enumerate(['Actual source head/current centers at70.000s','Phira local-x sustain strips: candidate shared touch']):
 ox=k*720;d.text((ox+16,12),title,font=font,fill='white');d.rectangle((ox+20,55,ox+700,510),outline='#55606c');
 def xy(p):return(ox+360+p[0]*680,282.5-p[1]*455)
 for i,n in enumerate(h['active_hold_positions_at_answer']):
  point=xy(n['world_contact_normalized']);color=['#6fc6ff','#ffbd69','#90dc92','#d998fa'][i]
  if k==0:d.ellipse((point[0]-8,point[1]-8,point[0]+8,point[1]+8),fill=color);d.text((point[0]+9,point[1]+8*i),f'hold line{n["line"]}',font=font,fill=color)
  elif n['line'] in [0,1]:d.rectangle((ox+354,55,ox+366,510),fill=color)
  else:d.rectangle((ox+20,point[1]-5,ox+700,point[1]+5),fill=color)
 if k==1:
  candidate=xy([0,1/12]);d.ellipse((candidate[0]-10,candidate[1]-10,candidate[0]+10,candidate[1]+10),fill='#ffffff');d.text((candidate[0]+15,candidate[1]-35),'one held touch candidate',font=font,fill='white')
 d.text((ox+16,530),'Source geometry; NOT official gameplay or validated finger assignment',font=font,fill='#b8c7d7')
im.save(B/'judgment-center-vs-strip.png')
