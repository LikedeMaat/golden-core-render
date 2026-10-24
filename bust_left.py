# python3 bust_left.py buste.png uit.png [shift]  -> 1920x1080, buste naar links, rechts zwart voor citaten
import sys
from PIL import Image
import numpy as np
sh=int(sys.argv[3]) if len(sys.argv)>3 else 200
im=Image.open(sys.argv[1]).convert('RGB').resize((1620,1080),Image.LANCZOS); a=np.asarray(im).astype(float)
bg=np.median(a[:150,1300:],axis=(0,1)); w=1620-sh
c=np.zeros((1080,1920,3)); c[:]=bg; c[:,:w]=a[:,sh:1620]
x0=w-160
for i in range(160):
    k=(i/160)**1.5; c[:,x0+i]=c[:,x0+i]*(1-k)+bg*k
Image.fromarray(c.astype(np.uint8)).save(sys.argv[2])
