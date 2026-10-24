import numpy as np, sys
from scipy.ndimage import gaussian_filter
from PIL import Image
W,H=1920,1080; FPS=24; T=24.0; NF=int(FPS*T)
CX,CY=W/2,H/2; RS=H*0.165                       # straal van de kern
GOLD=np.array([1.0,0.60,0.17]); WARM=np.array([1.0,0.70,0.33]); DEEP=np.array([0.55,0.28,0.06])
yy,xx=np.mgrid[0:H,0:W].astype(np.float32)
DXp=(xx-CX)/RS; DYp=(yy-CY)/RS; RR=np.sqrt(DXp**2+DYp**2)
rad=np.sqrt((xx-CX)**2+(yy-CY)**2)/H
inside=RR<1.0
nz=np.sqrt(np.clip(1-RR**2,0,1)); nx=DXp; ny=DYp
# lichtrichting: linksboven-voor
L=np.array([-0.45,-0.55,0.70]); L/=np.linalg.norm(L)
ndl=np.clip(nx*L[0]+ny*L[1]+nz*L[2],0,1)
hv=L+np.array([0,0,1.0]); hv/=np.linalg.norm(hv)
spec=np.clip(nx*hv[0]+ny*hv[1]+nz*hv[2],0,1)**60
fres=(1-nz)**3
lat0=np.arcsin(np.clip(-ny,-1,1)); lonb=np.arctan2(nx,nz)
rng=np.random.default_rng(5)
# vloeiende textuur: harmonischen m veelvoud van 4 -> draai 90 graden per loop is naadloos
HARM=[(4,2,1,rng.uniform(0,6.3)),(8,3,-1,rng.uniform(0,6.3)),(4,5,2,rng.uniform(0,6.3)),(12,1,1,rng.uniform(0,6.3)),(8,6,-2,rng.uniform(0,6.3))]
def rings_setup():
    rs=[]
    for (Rr,tilt,yaw,spd,npt,br) in [(1.62,np.deg2rad(72),np.deg2rad(18),1,1440,1.0),(1.95,np.deg2rad(64),np.deg2rad(-32),-1,1728,0.75),(2.35,np.deg2rad(80),np.deg2rad(4),1,2016,0.45)]:
        # vlak van de ring: kantelen rond x, dan draaien rond z
        ct,st=np.cos(tilt),np.sin(tilt); cy,sy=np.cos(yaw),np.sin(yaw)
        u=np.array([cy,sy,0.0]); v=np.array([-sy*ct,cy*ct,st])
        th=np.arange(npt)/npt*2*np.pi
        tick=(np.arange(npt)%(npt//24)<2).astype(float)       # 24 streepjes, als een astrolabium
        rs.append((Rr,u,v,th,tick,spd,br))
    return rs
RINGS=rings_setup()
nd=1100
d_a=rng.uniform(0,2*np.pi,nd); d_u=rng.uniform(0,1,nd); d_b=rng.uniform(0.25,1.0,nd)**2
d_sw=rng.normal(0.35,0.12,nd); d_tw=rng.integers(1,4,nd); d_tp=rng.uniform(0,2*np.pi,nd); d_sz=rng.uniform(0,1,nd)*0.9+0.0
nb=140
b_x=rng.uniform(0,W,nb); b_y=rng.uniform(0,H,nb); b_b=rng.uniform(0.1,0.5,nb)**2; b_tp=rng.uniform(0,2*np.pi,nb)
def splat(out,sx,sy,w,sig):
    ok=(sx>=0)&(sx<W-1)&(sy>=0)&(sy<H-1)
    fx,fy,w=sx[ok],sy[ok],w[ok]
    acc=np.zeros((H,W),np.float32)
    x0=np.floor(fx).astype(int); y0=np.floor(fy).astype(int); ax=fx-x0; ay=fy-y0
    for dx,dy,ww in ((0,0,(1-ax)*(1-ay)),(1,0,ax*(1-ay)),(0,1,(1-ax)*ay),(1,1,ax*ay)):
        np.add.at(acc,(y0+dy,x0+dx),w*ww)
    out+=gaussian_filter(acc,sig) if sig>0 else acc
def frame(k):
    ph=(k%NF)/NF; tt=ph*2*np.pi
    breathe=1+0.06*np.sin(tt)
    img=np.zeros((H,W,3),np.float32)
    # achtergrond: diepe gouden nevel
    img+=(np.exp(-(rad/0.55)**2)*0.035)[...,None]*DEEP
    # verre bokeh, heel zacht twinkelend
    bk=np.zeros((H,W),np.float32)
    splat(bk,b_x,b_y,b_b*60*(1+0.17*np.sin(tt+b_tp)),2.2)
    img+=bk[...,None]*DEEP*0.9
    # ---- kern: gesmolten goud ----
    lon=lonb+tt/4
    latw=lat0*2.2+0.7*np.sin(4*lon+tt)            # vervormd veld -> vloeiende vlekken i.p.v. strepen
    lonw=lon+0.35*np.sin(3*lat0*2.2-tt)
    N=np.zeros((H,W),np.float32)
    for m,n,j,p in HARM: N+=np.sin(m*lonw+n*latw*0.8+j*tt+p)
    N/=len(HARM)
    flow=0.5+0.5*np.tanh(N*1.9)                   # 0 = afkoelende korst, 1 = vloeibaar
    veins=np.exp(-(N*6.0)**2)                     # dunne heldere aders
    CRUST=np.array([0.20,0.085,0.015])
    surf=CRUST[None,None,:]*(1-flow[...,None])+GOLD[None,None,:]*0.72*flow[...,None]
    light=0.18+0.95*ndl**1.3
    emis=(0.16*flow+0.45*veins+0.06)*breathe
    col=(surf*light[...,None] + emis[...,None]*WARM*0.5 + spec[...,None]*np.array([1.0,0.86,0.58])*1.1 + fres[...,None]*GOLD*0.55)
    col*=(0.35+0.65*nz**0.4)[...,None]
    aa=np.clip((1.0-RR)*RS/1.5,0,1)               # zachte rand
    img=img*(1-aa[...,None])+col*aa[...,None]
    # gloed rond de kern
    halo=np.exp(-np.clip(RR-0.97,0,None)/0.30)*0.42+np.exp(-np.clip(RR-1,0,None)/1.4)*0.14
    halo*=(1-0.85*aa)
    img+=(halo*breathe)[...,None]*GOLD
    # ---- ringen ----
    rfront=np.zeros((H,W),np.float32); rglow=np.zeros((H,W),np.float32)
    for (Rr,u,v,th,tick,spd,br) in RINGS:
        a=th+spd*tt/6                             # 60 graden per loop; 24 streepjes -> naadloos
        p=(Rr*np.cos(a))[:,None]*u+(Rr*np.sin(a))[:,None]*v
        persp=1/(1-p[:,2]*0.06)
        sx=CX+p[:,0]*RS*persp; sy=CY+p[:,1]*RS*persp
        hidden=(p[:,2]<0)&((p[:,0]**2+p[:,1]**2)<1.0)
        depth=0.55+0.45*(p[:,2]/Rr+1)/2
        w=br*(0.9+2.2*tick)*depth*(~hidden)*breathe
        splat(rfront,sx,sy,w*1.6,0.6)
        splat(rglow,sx,sy,w,3.0)
    img+=(rfront[...,None]*WARM*0.9+rglow[...,None]*GOLD*0.9)
    # ---- stof dat wegdrijft (wat niet van jou is) ----
    f=(d_u+ph)%1.0
    r=RS*(1.15+f*3.6)
    ang=d_a+d_sw*f*1.2
    sx=CX+r*np.cos(ang); sy=CY+r*np.sin(ang)*0.92
    env=np.sin(np.pi*f)**1.5*np.clip(f/0.08,0,1)
    w=d_b*env*(1+0.16*np.sin(d_tw*tt+d_tp))*(1-0.65*f)
    dust=np.zeros((H,W),np.float32)
    small=d_sz<0.75
    splat(dust,sx[small],sy[small],w[small]*55,0.7)
    splat(dust,sx[~small],sy[~small],w[~small]*150,1.6)
    dust+=0.3*gaussian_filter(dust,10)
    img+=dust[...,None]*GOLD
    # bloom
    lum=img.mean(-1)
    bl=gaussian_filter(np.clip(lum-0.35,0,None),18)*0.7+gaussian_filter(np.clip(lum-0.2,0,None),55)*0.5
    img+=bl[...,None]*GOLD
    vig=np.clip(1.18-0.6*rad**2*2.2,0,1)
    img*=vig[...,None]
    img+=np.random.default_rng(1000+k).normal(0,0.004,(H,W,1))
    img=1-np.exp(-np.clip(img,0,None)*1.25)
    return (np.clip(img,0,1)**(1/1.05)*255).astype(np.uint8)
if __name__=='__main__':
    if sys.argv[1]=='still':
        for k in map(int,sys.argv[2:]): Image.fromarray(frame(k)).save(f'still_{k}.png')
        sys.exit()
    import subprocess
    a,b,out=int(sys.argv[1]),int(sys.argv[2]),sys.argv[3]
    p=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-c:v','libx264','-preset','medium','-b:v','16M','-maxrate','19M','-bufsize','34M','-tune','film','-pix_fmt','yuv420p',out],stdin=subprocess.PIPE)
    for k in range(a,b): p.stdin.write(frame(k).tobytes())
    p.stdin.close(); p.wait()