"""Render transparent explanatory labels; native chart imagery is unchanged."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
OUT=Path(__file__).resolve().parent


def label(draw,x,y,text,color='white',size=13):
    font=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',size)
    box=draw.textbbox((0,0),text,font=font);width=box[2]-box[0]
    draw.rectangle((x-width/2-5,y-3,x+width/2+5,y+size+5),fill=(0,0,0,210))
    draw.text((x-width/2,y),text,font=font,fill=color)


base=Image.new('RGBA',(960,540));d=ImageDraw.Draw(base)
for x,text in zip([302,658],['DRUM PULSE','MAIN MELODY*']):label(d,x,445,text)
label(d,480,65,'*Melody estimate | Holds show sustain | Independent timings')
base.save(OUT/'voice-labels.png')
climax=Image.new('RGBA',(960,540));d=ImageDraw.Draw(climax)
label(d,480,88,'CLIMAX CANDIDATE - acoustic estimate','yellow',12)
climax.save(OUT/'climax-label.png')
