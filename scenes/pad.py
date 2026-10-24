import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from PIL import Image
W,H=1920,1080; FPS=24; T=24.0          # loopduur (s) v2: twee keer zo traag
HOR=int(H*0.62); CX=W/2; F=W*0.55; CAMH=1.0
GOLD=np.array([1.0,0.60,0.17]); WARM=np.array([1.0,0.70,0.33])
rng=np.random.default_rng(7)
NT=4; n=2400; N=n*NT                       # 3 identieke lagen -> camera hoeft maar 1/3 diepte per loop te reizen (rustiger)
ZR=69.0; P=ZR/NT
x=rng.normal(0,1,n)*np.where(rng.random(n)<0.6,2.5,9.0)
y=np.where(rng.random(n)<0.8,np.abs(rng.normal(0,1,n))*0.7,np.abs(rng.normal(0,1,n))*2.2)+0.05
z=rng.uniform(0,P,n); b=rng.uniform(0.3,1.0,n)**2
tw=rng.integers(1,4,n); tp=rng.uniform(0,2*np.pi,n)
X=np.tile(x,NT); Y=np.tile(y,NT); B=np.tile(b,NT); TW=np.tile(tw,NT); TP=np.tile(tp,NT)
Z0=np.concatenate([z+k*P for k in range(NT)])
yy,xx=np.mgrid[0:H,0:W].astype(np.float32)
def statics():
    # achtergrond + gloed rond horizon
    dx=(xx-CX)/W; dy=(yy-HOR)/H
    bg=np.zeros((H,W,3),np.float32)
    haze=np.exp(-(dx**2/0.02+dy**2/0.008))*0.18
    bg+=haze[...,None]*GOLD
    return bg,dx,dy
BG,DX,DY=statics()
# pad (trapezium) masker
def path_mask():
    half_bottom=W*0.27
    t=np.clip((yy-HOR)/(H-HOR),0,1)
    half=half_bottom*t
    return ((np.abs(xx-CX)<half)&(yy>HOR)).astype(np.float32), t
PM,PT=path_mask()
def frame(k):
    ph=k/(FPS*T); tt=ph*2*np.pi
    img=BG.copy()
    breathe=1+0.05*np.sin(tt)
    # lichtbron + verticale straal + horizontale flare
    core=np.exp(-((DX*W)**2+(DY*H)**2)/(2*12**2))*3.0
    halo=np.exp(-((DX*W)**2+(DY*H)**2)/(2*70**2))*0.9
    up=np.clip(-DY,0,None)
    beam=np.exp(-(DX*W)**2/(2*(18+up*H*0.10)**2))*np.exp(-up*2.2)*(yy<HOR)*0.9
    flare=np.exp(-(DY*H)**2/(2*6**2))*np.exp(-np.abs(DX)*7)*0.5
    light=(core+halo+beam+flare)*breathe
    img+=light[...,None]*WARM
    # deeltjes naar de camera toe, naadloos (diepte wikkelt rond na één loop)
    Z=(Z0-ph*P)%ZR+1.5
    sx=CX+F*X/Z; sy=HOR-F*(Y-CAMH)/Z+ (0)
    sy=HOR-F*(Y)/Z*0.9-F*0.0/Z
    br=B*(1+0.18*np.sin(TW*tt+TP))*np.clip(1.3-Z/60,0,1)*np.clip(Z/4,0,1)
    size=np.clip(9/Z,0.4,6)
    acc=[np.zeros((H,W),np.float32) for _ in range(3)]; refl=np.zeros((H,W),np.float32)
    ok=(sx>=0)&(sx<W)&(sy>=0)&(sy<HOR)
    bins=np.digitize(size,[0.9,2.2])
    for b in range(3):
        m=ok&(bins==b)
        fx,fy=sx[m],sy[m]; x0=np.floor(fx).astype(int); y0=np.floor(fy).astype(int); ax=fx-x0; ay=fy-y0; w=br[m]*[60,140,320][b]
        for ddx,ddy,ww in ((0,0,(1-ax)*(1-ay)),(1,0,ax*(1-ay)),(0,1,(1-ax)*ay),(1,1,ax*ay)):
            np.add.at(acc[b],(np.clip(y0+ddy,0,H-1),np.clip(x0+ddx,0,W-1)),w*ww)
    parts=gaussian_filter(acc[0],0.8)+gaussian_filter(acc[1],2.0)+gaussian_filter(acc[2],5.0)
    parts+=0.35*gaussian_filter(parts,14)
    img+=parts[...,None]*GOLD
    sky=img*(yy<HOR)[...,None]
    # water: spiegeling van de lucht met golfjes (periodiek -> naadloze loop)
    d=np.clip(yy-HOR,0,None)
    freq=0.35/(1+d*0.02)
    ripple=(np.sin(d*freq*6+tt*2)*0.45+np.sin(xx*0.011+d*0.05-tt)*0.3)*(0.8+d*0.012)
    src_y=np.clip(HOR-1-d*1.7,0,HOR-1)
    src_x=np.clip(xx+ripple,0,W-1)
    refl=np.stack([map_coordinates(gaussian_filter(sky[...,c],(14,1.2)),[src_y,src_x],order=1) for c in range(3)],-1)
    fade=(0.45*np.exp(-d/260)+0.10)*(yy>HOR)
    glint=0.85+0.15*np.sin(d*freq*9-tt*3+xx*0.003)
    water_img=refl*(fade*glint)[...,None]+np.array([0.008,0.007,0.006])
    img=np.where((yy>HOR)[...,None],water_img,img)
    # pad: donker en nat, met gedempte spiegeling
    tex=0.85+0.15*np.sin(xx*0.05+d*0.3)*np.sin(d*0.11-tt)
    pathcol=np.array([0.030,0.028,0.026])*(0.7+0.6*PT[...,None])*tex[...,None]
    img=img*(1-PM[...,None]*0.75)+PM[...,None]*pathcol
    # glanzende lichtstreep over het natte pad (reflectie van de bron)
    streak=np.exp(-((xx-CX-ripple*0.6)/(3+d*0.035))**2)*np.exp(-d/520)*(0.85+0.15*np.sin(d*0.08-tt*3))*(yy>HOR)*breathe
    img+=streak[...,None]*WARM*1.1
    # vignet + korrel + tonemap
    vig=np.clip(1.25-0.9*((xx-CX)/W)**2*2-0.6*((yy-H/2)/H)**2*2,0,1)
    img*=vig[...,None]
    img+=np.random.default_rng(k).normal(0,0.004,(H,W,1))
    img=1-np.exp(-img*1.35)          # zachte tonemap
    return (np.clip(img,0,1)**(1/1.05)*255).astype(np.uint8)
if __name__=='__main__':
    import sys,os,subprocess
    a,bnd,out=int(sys.argv[1]),int(sys.argv[2]),sys.argv[3]
    p=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-c:v','libx264','-preset','medium','-b:v','16M','-maxrate','19M','-bufsize','34M','-tune','film','-pix_fmt','yuv420p',out],stdin=subprocess.PIPE)
    for k in range(a,bnd): p.stdin.write(frame(k).tobytes())
    p.stdin.close(); p.wait()