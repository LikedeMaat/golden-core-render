import numpy as np, sys
from scipy.ndimage import gaussian_filter
from PIL import Image
W,H=1920,1080; FPS=24; T=24.0; NF=int(FPS*T)
CX,CY=W/2,H*0.62; R=W*0.30; TILT=0.30
GOLD=np.array([1.0,0.60,0.17]); WARM=np.array([1.0,0.72,0.36]); DEEP=np.array([0.55,0.28,0.06])
yy,xx=np.mgrid[0:H,0:W].astype(np.float32)
U=(xx-CX)/R; V=(yy-CY)/(R*TILT); RR=np.sqrt(U**2+V**2)
inside=np.clip((1-RR)*R*TILT/2.0,0,1)          # zachte rand (in schermpixels)
rad=np.sqrt(((xx-W/2)/W)**2+((yy-H/2)/H)**2)
DROPS=[(2.0,0.0,0.0),(13.5,-0.12,0.10)]        # (tijd, u, v)
LIFE=9.5
def height(t):
    h=np.zeros((H,W),np.float32)
    for td,du,dv in DROPS:
        for off in (0,-T,T):
            age=t-td-off
            if 0<age<LIFE:
                r=np.sqrt((U-du)**2+(V-dv)**2)
                front=age*0.16
                env=np.exp(-((r-front)/(0.10+0.03*age))**2)*np.exp(-age*0.42)*(1-age/LIFE)**2
                h+=env*np.sin((r-front)*38)*0.014/(0.25+r)
    return h
rng=np.random.default_rng(3)
nd=420; px=rng.uniform(-0.9,0.9,nd)*W*0.45+W/2; py0=rng.uniform(0,1,nd); pb=rng.uniform(0.2,1,nd)**2; pt=rng.uniform(0,6.28,nd); sp=rng.integers(1,3,nd)
def splat(out,sx,sy,w,sig):
    ok=(sx>=0)&(sx<W-1)&(sy>=0)&(sy<H-1); fx,fy,w=sx[ok],sy[ok],w[ok]
    acc=np.zeros((H,W),np.float32); x0=np.floor(fx).astype(int); y0=np.floor(fy).astype(int); ax=fx-x0; ay=fy-y0
    for dx,dy,ww in ((0,0,(1-ax)*(1-ay)),(1,0,ax*(1-ay)),(0,1,(1-ax)*ay),(1,1,ax*ay)): np.add.at(acc,(y0+dy,x0+dx),w*ww)
    out+=gaussian_filter(acc,sig)
def frame(k):
    t=(k%NF)/FPS; tt=2*np.pi*t/T
    breathe=1+0.05*np.sin(tt)
    img=np.zeros((H,W,3),np.float32)
    # lichtbron boven (buiten beeld) -> zachte straal
    dxs=(xx-CX)/W
    beam=np.exp(-(dxs/0.07)**2)*np.clip(1-yy/(CY),0,1)**1.5*0.10*breathe
    img+=beam[...,None]*GOLD
    img+=(np.exp(-(rad/0.5)**2)*0.03)[...,None]*DEEP
    # wateroppervlak
    h=height(t)
    gy,gx=np.gradient(h)
    gx*=R; gy*=R*TILT
    # spiegeling van de lichtbron: heldere vlek die verschuift met de helling
    su=U+gx*6.0; sv=V+gy*6.0
    refl=np.exp(-((su)**2/0.012+(sv+0.05)**2/0.16))*1.1*breathe + np.exp(-(su**2+ (sv+0.05)**2)/0.35)*0.30
    shade=0.03+0.07*(1-RR**2).clip(0)                     # diep goud in het midden
    glint=np.clip(-(gx*0.6+gy*1.0)*12,0,None)**1.5*0.5    # lichtjes op de kammen
    surf=(shade+refl+glint)[...,None]*GOLD+(refl*0.25)[...,None]*WARM
    surf*=(0.75+0.25*np.clip(1-RR,0,1))[...,None]
    img=img*(1-inside[...,None])+surf*inside[...,None]
    # rand: dunne gouden ring
    ring=np.exp(-((RR-1.0)*R*TILT/1.6)**2)*(0.55+0.45*np.clip(-V*1.2+0.4,0,1))
    img+=(ring*0.9)[...,None]*WARM
    ring2=np.exp(-((RR-0.93)*R*TILT/1.0)**2)*0.18*inside
    img+=ring2[...,None]*GOLD
    # spiegeling van de ring onder de rand (zacht)
    # vallende druppel
    for td,du,dv in DROPS:
        for off in (0,-T,T):
            a=t-td-off
            if -0.6<a<0:
                fy=CY+dv*R*TILT - (-a/0.6)**2*CY*0.95; fx=CX+du*R
                d=np.exp(-((xx-fx)/3.0)**2-((yy-fy)/9.0)**2)*1.6
                img+=d[...,None]*WARM
            if 0<=a<0.6:   # flits bij inslag
                fl=np.exp(-(((xx-CX-du*R)/40)**2+((yy-CY-dv*R*TILT)/14)**2))*(1-a/0.6)*0.7
                img+=fl[...,None]*WARM
    # zwevend stof, traag omhoog, naadloos
    yv=(py0-t/T*sp)%1.0
    sy=H*(1-yv)*0.95; sx=px+np.sin(tt*sp+pt)*6
    env=np.sin(np.pi*yv)
    w=pb*env*(1+0.15*np.sin(2*tt+pt))
    iu=(sx-CX)/R; iv=(sy-CY)/(R*TILT); w*=np.where(iu**2+iv**2<1.1,0.25,1.0)
    dust=np.zeros((H,W),np.float32); splat(dust,sx,sy,w*70,1.0)
    img+=dust[...,None]*GOLD
    lum=img.mean(-1); bl=gaussian_filter(np.clip(lum-0.3,0,None),20)*0.7+gaussian_filter(np.clip(lum-0.15,0,None),60)*0.45
    img+=bl[...,None]*GOLD
    vig=np.clip(1.15-0.6*rad**2*2.2,0,1); img*=vig[...,None]
    img+=np.random.default_rng(1000+k%NF).normal(0,0.004,(H,W,1))
    img=1-np.exp(-np.clip(img,0,None)*1.3)
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