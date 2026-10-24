# python3 quotes.py config.json  -> <prefix>_q_open.png, <prefix>_q1.png, <prefix>_q2.png (1920x1080 RGBA)
# config: {"prefix":"e10","source":"Author, Work (tr. X)","opening":"...","closing":["deel 1","deel 2"]}
import json,sys,os
from PIL import Image, ImageDraw, ImageFont
D=os.environ.get('GC_FONTS',os.path.dirname(os.path.abspath(__file__)))
F=ImageFont.truetype(D+'/Cormorant-600.ttf',54); S=ImageFont.truetype(D+'/Cormorant-500.ttf',34)
X=1010; MAXW=780; LH=68
def wrap(t,f):
    out=[];cur=''
    for w in t.split():
        c=(cur+' '+w).strip()
        if f.getlength(c)>MAXW and cur: out.append(cur); cur=w
        else: cur=c
    out.append(cur); return out
def make(fn,text,y,src=None,center=False):
    im=Image.new('RGBA',(1920,1080),(0,0,0,0)); d=ImageDraw.Draw(im)
    L=wrap(text,F); h=len(L)*LH+(70 if src else 0)
    if center: y=(1080-h)//2
    for i,l in enumerate(L): d.text((X,y+i*LH),l,font=F,fill=(236,182,98,255))
    if src: d.text((X,y+len(L)*LH+22),src,font=S,fill=(199,170,121,255))
    im.save(fn); return y+h
c=json.load(open(sys.argv[1])); p=c['prefix']
make(p+'_q_open.png',c['opening'],0,c['source'],center=True)
cl=c['closing']
if len(cl)==1: make(p+'_q1.png',cl[0],0,c['source'],center=True)
else:
    n1=len(wrap(cl[0],F)); n2=len(wrap(cl[1],F)); tot=(n1+n2)*LH+50+70
    e=make(p+'_q1.png',cl[0],max(80,(1080-tot)//2)); make(p+'_q2.png',cl[1],e+50,c['source'])
