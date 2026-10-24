import numpy as np, sys, os, subprocess
from scipy.ndimage import gaussian_filter
from PIL import Image
W,H=1920,1080; FPS=24; T=12.0; NF=int(FPS*T)
src_path,out_mp4=sys.argv[1],sys.argv[2]
imc=Image.open(src_path).convert('RGB')
r=max(W/imc.width,H/imc.height); imc=imc.resize((round(imc.width*r),round(imc.height*r)),Image.LANCZOS)
l=(imc.width-W)//2; t=int((imc.height-H)*float(os.environ.get('VY','0.5'))); imc=imc.crop((l,t,l+W,t+H))
RGB=np.asarray(imc,np.float32)/255; L=RGB.mean(2)
if os.environ.get('MODE')=='ai':
    base=np.clip(RGB,0,1)**1.05*1.05
else:
    Lg=np.clip((L-0.04)/0.96,0,1)**float(os.environ.get('GAMMA','1.9'))*float(os.environ.get('GAIN','0.8'))
    SH=np.array([0.012,0.010,0.009]); HI=np.array([1.0,0.80,0.50])
    base=SH+(HI-SH)*Lg[...,None]
yy,xx=np.mgrid[0:H,0:W].astype(np.float32)
vig=np.clip(1.18-0.75*(((xx-W/2)/W)**2*2.2+((yy-H/2)/H)**2*1.6),0,1)[...,None]
GOLD=np.array([1.0,0.62,0.20]); WARM=np.array([1.0,0.72,0.38])
Lblur=gaussian_filter(L,25)
ly,lx=np.unravel_index(np.argmax(gaussian_filter(L,40)),L.shape)   # lichtste plek
d=np.sqrt((xx-lx)**2+(yy-ly)**2)
glow=np.exp(-(d/60)**2)*0.18+np.exp(-(d/220)**2)*0.12+np.exp(-(d/520)**2)*0.05
rng=np.random.default_rng(5); N=int(os.environ.get('NP','450'))
px=rng.uniform(0,W,N); py=rng.uniform(0,H*0.95,N)
ax=rng.uniform(8,40,N); ay=rng.uniform(10,55,N)
f1=rng.integers(1,3,N); f2=rng.integers(1,3,N); p1=rng.uniform(0,2*np.pi,N); p2=rng.uniform(0,2*np.pi,N)
depth=rng.uniform(0,1,N)**1.6
twf=rng.integers(1,4,N); twp=rng.uniform(0,2*np.pi,N); bri=rng.uniform(0.3,1.0,N)
def frame(k):
    tt=(k%NF)/NF*2*np.pi; br=1+0.10*np.sin(tt)
    img=base*(1+0.04*np.sin(tt+1.0))+glow[...,None]*WARM*br
    x=px+ax*np.sin(f1*tt+p1); y=py+ay*np.sin(f2*tt+p2)-ay*0.3*np.cos(f2*tt+p2)
    xi=np.clip(x.astype(int),0,W-1); yi=np.clip(y.astype(int),0,H-1)
    b=bri*(1+0.5*np.sin(twf*tt+twp))*(0.35+1.4*Lblur[yi,xi])
    out=np.zeros((H,W),np.float32)
    for lo,hi,sig,g in [(0,0.35,0.8,40),(0.35,0.7,2.2,110),(0.7,1.01,5.5,380)]:
        m=(depth>=lo)&(depth<hi); acc=np.zeros((H,W),np.float32); np.add.at(acc,(yi[m],xi[m]),b[m]*g); out+=gaussian_filter(acc,sig)
    out+=gaussian_filter(out,12)*0.5
    img=(img+out[...,None]*GOLD*float(os.environ.get('DUST','0.55')))*vig
    img=img+np.random.default_rng(2000+k).normal(0,0.010,(H,W,1))
    img=1-np.exp(-np.clip(img,0,None)*1.25)
    return (np.clip(img,0,1)**(1/1.05)*255).astype(np.uint8)
if len(sys.argv)>3 and sys.argv[3]=='still':
    Image.fromarray(frame(0)).save(out_mp4); sys.exit()
p=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-c:v','libx264','-preset','medium','-b:v','11M','-pix_fmt','yuv420p',out_mp4],stdin=subprocess.PIPE)
for k in range(NF): p.stdin.write(frame(k).tobytes())
p.stdin.close(); p.wait()
