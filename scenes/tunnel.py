import numpy as np, sys, os
from scipy.ndimage import gaussian_filter
from PIL import Image
W,H=1920,1080; FPS=24; T=24.0; NF=int(FPS*T)
CX,CY=W/2,H/2; F=H*0.62
GOLD=np.array([1.0,0.60,0.17]); DEEP=np.array([0.55,0.28,0.06])
NT=15; P=4.0; ZR=NT*P; TH=np.deg2rad(5.0)          # per loop: 1 laag vooruit + 5 graden draai -> naadloos
rng=np.random.default_rng(11)
n=1600
a0=rng.uniform(0,2*np.pi,n); r0=1.0+np.abs(rng.normal(0,0.18,n)); z0=rng.uniform(0,P,n)
b0=rng.uniform(0.25,1.0,n)**2; tw=rng.integers(1,4,n); tp=rng.uniform(0,2*np.pi,n)
# lichtring per laag: extra deeltjes op één diepte
m=260; ra=rng.uniform(0,2*np.pi,m); rr=1.0+np.abs(rng.normal(0,0.05,m)); rz=np.full(m,P*0.5)+rng.normal(0,0.04,m)
A=np.concatenate([a0,ra]); R=np.concatenate([r0,rr]); Zb=np.concatenate([z0,rz])
Bb=np.concatenate([b0,np.full(m,0.9)]); TWb=np.concatenate([tw,np.full(m,1)]); TPb=np.concatenate([tp,rng.uniform(0,2*np.pi,m)])
A=np.concatenate([A+k*TH for k in range(NT)]); Z0=np.concatenate([Zb+k*P for k in range(NT)])
R=np.tile(R,NT); B=np.tile(Bb,NT); TW=np.tile(TWb,NT); TP=np.tile(TPb,NT)
yy,xx=np.mgrid[0:H,0:W].astype(np.float32)
rad=np.sqrt((xx-CX)**2+(yy-CY)**2)/H
def frame(k):
    ph=(k%NF)/NF; tt=ph*2*np.pi
    Z=(Z0-ph*P)%ZR+0.35
    ang=A-ph*TH
    sx=CX+F*R*np.cos(ang)/Z; sy=CY+F*R*np.sin(ang)/Z
    fog=np.exp(-Z/6.5)
    near=np.clip((Z-0.35)/0.9,0,1)            # niet ploppen vlak voor de camera
    edge=np.clip(Z/(ZR-1.0)*-1+1,0,1)**0.5    # zachte inkomst in de verte
    br=B*(1+0.15*np.sin(TW*tt+TP))*fog*near*edge
    size=np.clip(5.5/Z,0.3,12)
    ok=(sx>=0)&(sx<W)&(sy>=0)&(sy<H)
    bins=np.digitize(size,[0.8,1.8,4.0])
    out=np.zeros((H,W),np.float32)
    for bi,(sig,gain) in enumerate([(0.7,55),(1.6,120),(3.4,260),(7.5,700)]):
        msk=ok&(bins==bi)
        acc=np.zeros((H,W),np.float32)
        fx,fy=sx[msk],sy[msk]; x0=np.floor(fx).astype(int); y0=np.floor(fy).astype(int); ax=fx-x0; ay=fy-y0; w=br[msk]*gain
        for dx,dy,ww in ((0,0,(1-ax)*(1-ay)),(1,0,ax*(1-ay)),(0,1,(1-ax)*ay),(1,1,ax*ay)):
            np.add.at(acc,(np.clip(y0+dy,0,H-1),np.clip(x0+dx,0,W-1)),w*ww)
        out+=gaussian_filter(acc,sig)
    glow=gaussian_filter(out,22)*0.9+gaussian_filter(out,60)*0.6
    img=(out[...,None]*GOLD+glow[...,None]*DEEP*1.3)*0.75
    # duister midden: extra verduistering in het centrum
    center=1-np.exp(-(rad/0.20)**2)*0.97
    img*=center[...,None]
    vig=np.clip(1.15-0.55*rad**2*2.2,0,1)
    img*=vig[...,None]
    img+=np.random.default_rng(1000+k).normal(0,0.004,(H,W,1))
    img=1-np.exp(-np.clip(img,0,None)*1.3)
    return (np.clip(img,0,1)**(1/1.05)*255).astype(np.uint8)
if __name__=='__main__':
    import subprocess
    a,b,out=int(sys.argv[1]),int(sys.argv[2]),sys.argv[3]
    p=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-c:v','libx264','-preset','medium','-b:v','16M','-maxrate','19M','-bufsize','34M','-tune','film','-pix_fmt','yuv420p',out],stdin=subprocess.PIPE)
    for k in range(a,b): p.stdin.write(frame(k).tobytes())
    p.stdin.close(); p.wait()