# python3 thumb.py bron.png "DEEP|FOCUS" "Regel 1|Regel 2" uit.jpg  -> 1280x720, buste links, gouden tekst rechts
import sys,os
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np
D=os.environ.get('GC_FONTS',os.path.dirname(os.path.abspath(__file__)))
src=Image.open(sys.argv[1]).convert('RGB'); w,h=src.size
t=int((h-w*9/16)*0.4); src=src.crop((0,t,w,t+int(w*9/16))).resize((1280,720),Image.LANCZOS)
src=ImageEnhance.Brightness(src).enhance(1.08)
F=ImageFont.truetype(D+'/Cormorant-700.ttf',150); S=ImageFont.truetype(D+'/Cormorant-600.ttf',26)
GOLD=(240,186,100); lines=sys.argv[3].split('|')
lab=' '.join(sys.argv[2].upper())+'    '+' '.join('RITUAL')
im=src.convert('RGBA'); txt=Image.new('RGBA',im.size,(0,0,0,0)); d=ImageDraw.Draw(txt)
R=1220; lh=150; asc,desc=F.getmetrics(); y0=(720-len(lines)*lh)//2-30
for i,l in enumerate(lines):
    d.text((R-d.textlength(l,font=F),y0+i*lh),l,font=F,fill=GOLD+(255,))
yl=y0+(len(lines)-1)*lh+asc+desc+14
d.text((R-d.textlength(lab,font=S),yl),lab,font=S,fill=(205,172,118,255))
g=np.array(txt.filter(ImageFilter.GaussianBlur(14))); g[...,3]=(g[...,3]*0.55).astype(np.uint8)
im.alpha_composite(Image.fromarray(g)); im.alpha_composite(txt); im.convert('RGB').save(sys.argv[4],quality=95)
