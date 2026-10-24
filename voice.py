"""Golden Core stem + mix (recept 4-7 okt 2026).
Cartesia Isla, sonic-3, speed 0.9, volume 0.75, emotion calm, elke zin een eigen generatie.
Pauzes x1.5, max 1 s schuiven weg van beatpieken, 10 s intro, compressor, stem -19.4 LUFS / beat -17.3 LUFS premix,
eindmix -14 LUFS met limiter 0.89. Nooit volume per zin, geen galm.
"""
import json, os, subprocess, hashlib, time, urllib.request, urllib.error
import numpy as np

SR = 44100; INTRO = 10; PF = 1.5; MAXS = 1.0
VOICE = "eef47c0d-cb49-4160-a4a0-6b97ed4c81e6"


def lufs(path):
    out = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', path, '-af', 'ebur128', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    val = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('I:') and 'LUFS' in line:
            val = float(line.split()[1])
    return val


def tts(text, key, cache):
    f = os.path.join(cache, 't_' + hashlib.md5(text.encode()).hexdigest()[:10] + '.raw')
    if os.path.exists(f) and os.path.getsize(f) > 1000:
        return f
    body = {"model_id": "sonic-3", "transcript": text, "voice": {"mode": "id", "id": VOICE}, "language": "en",
            "generation_config": {"speed": 0.9, "volume": 0.75, "emotion": "calm"},
            "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": SR}}
    for attempt in range(5):
        try:
            r = urllib.request.Request("https://api.cartesia.ai/tts/bytes", data=json.dumps(body).encode(),
                                       headers={"X-API-Key": key, "Cartesia-Version": "2025-04-16",
                                                "Content-Type": "application/json"})
            data = urllib.request.urlopen(r, timeout=90).read()
            if len(data) < 1000:
                raise RuntimeError('lege audio')
            open(f, 'wb').write(data)
            return f
        except urllib.error.HTTPError as e:
            msg = e.read()[:300]
            if e.code in (401, 402, 403):
                raise RuntimeError(f'Cartesia {e.code}: {msg}')
            time.sleep(5 * (attempt + 1))
        except Exception:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError('Cartesia faalt na 5 pogingen: ' + text[:60])


def cleanclip(path):
    a = np.fromfile(path, dtype=np.int16).astype(float)
    Bk = 220
    env = np.array([np.abs(a[k:k + Bk]).max() for k in range(0, len(a) - Bk, Bk)])
    pk = env.max()
    on = np.argmax(env > pk * 0.12) * Bk
    end_i = (len(env) - np.argmax(env[::-1] > pk * 0.005)) * Bk
    s = max(0, on - int(0.010 * SR)); e = min(len(a), end_i + int(0.02 * SR))
    seg = a[s:e].copy()
    fi = on - s
    if fi > 0:
        seg[:fi] *= np.linspace(0, 1, fi) ** 2
    fo = int(0.010 * SR)
    seg[-fo:] *= np.linspace(1, 0, fo)
    return seg


def beat_profile(path, off, blen):
    """kortetermijn-luidheid per 0,5 s, om OFF/BLEN te kiezen als ze niet gegeven zijn"""
    dur = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path]).decode())
    return dur


def auto_off_blen(path):
    """start na de stille intro, eind voor een dip/outro (zoals handmatig gedaan)"""
    b = np.frombuffer(subprocess.check_output(['ffmpeg', '-loglevel', 'error', '-i', path, '-ac', '1', '-ar', '8000', '-f', 's16le', '-']), dtype=np.int16).astype(float)
    win = 8000  # 1 s
    rms = np.array([np.sqrt((b[k:k + win] ** 2).mean()) for k in range(0, len(b) - win, win)])
    db = 20 * np.log10(rms + 1e-9)
    ref = np.median(db)
    ok = db > ref - 6
    start = int(np.argmax(ok)) + 2
    # eind: laatste punt waarna geen dip >8 dB meer volgt in de laatste 40 s
    end = len(db) - 2
    for i in range(len(db) - 1, max(start + 60, len(db) - 45), -1):
        if db[i] < ref - 8:
            end = i - 2
    return float(start), float(max(60, end - start))


def make_audio(paragraphs, beat_path, key, workdir, off=None, blen=None, vx=3.0, bx=0.0):
    os.makedirs(workdir, exist_ok=True)
    cache = os.path.join(workdir, 'clips'); os.makedirs(cache, exist_ok=True)
    L = [(p['text'], float(p['pause_after_sec'])) for p in paragraphs]
    files = [tts(t, key, cache) for t, _ in L]
    clips = [cleanclip(f) for f in files]
    total = INTRO + sum(len(c) / SR + p * PF for c, (_, p) in zip(clips, L)) + len(L) * MAXS + 15
    if off is None or blen is None:
        off, blen = auto_off_blen(beat_path)
    bp = os.path.join(workdir, 'beatprep.wav')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(off), '-t', str(blen), '-i', beat_path,
                    '-af', f'aresample={SR},aloop=loop=-1:size=2e9,atrim=0:{total}', '-ac', '2', '-c:a', 'pcm_s16le', bp], check=True)
    b = np.frombuffer(subprocess.check_output(['ffmpeg', '-loglevel', 'error', '-i', bp, '-ac', '1', '-f', 's16le', '-']), dtype=np.int16).astype(float)
    Hs = int(0.05 * SR)
    rms = np.array([np.sqrt((b[k:k + Hs] ** 2).mean()) for k in range(0, len(b) - Hs, Hs)])
    db = 20 * np.log10(rms + 1e-9); loud = db > np.percentile(db, 80)

    def cost(t0, dur):
        i0 = int(t0 / 0.05); i1 = int((t0 + dur) / 0.05) + 1; seg = loud[i0:i1]
        return (seg.mean() if len(seg) else 0) + (2.0 if loud[i0:i0 + 3].any() else 0)

    t = INTRO; place = []
    for c, (_, p) in zip(clips, L):
        dur = len(c) / SR
        best = min(np.arange(-MAXS, MAXS + 0.001, 0.05), key=lambda s: (cost(t + s, dur), abs(s)))
        if place and t + best < place[-1][0] + len(place[-1][1]) / SR + 0.8:
            best = max(best, place[-1][0] + len(place[-1][1]) / SR + 0.8 - t)
        place.append((t + best, c)); t = t + best + dur + p * PF
    end = t + 6
    starts = [round(p[0], 2) for p in place]
    ends = [round(p[0] + len(p[1]) / SR, 2) for p in place]
    v = np.zeros(int((end + 1) * SR))
    for st, c in place:
        i = int(st * SR); v[i:i + len(c)] += c
    tr = os.path.join(workdir, 'timed.raw'); np.clip(v, -32767, 32767).astype(np.int16).tofile(tr)
    tc = os.path.join(workdir, 'timed_comp.wav')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 's16le', '-ar', str(SR), '-ac', '1', '-i', tr,
                    '-af', 'acompressor=threshold=-24dB:ratio=2.5:attack=15:release=300:knee=4', '-c:a', 'pcm_s16le', tc], check=True)
    gv = vx - 22.4 - lufs(tc); gb = bx - 17.3 - lufs(bp)
    fc = (f"[1:a]atrim=0:{end},volume={gb:.2f}dB,afade=t=in:d=3,afade=t=out:st={end - 5}:d=5[b];"
          f"[0:a]volume={gv:.2f}dB,pan=stereo|c0=c0|c1=c0[v];[v][b]amix=inputs=2:duration=longest:normalize=0[m]")
    pm = os.path.join(workdir, 'premix.wav')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', tc, '-i', bp, '-filter_complex', fc, '-map', '[m]', '-c:a', 'pcm_f32le', pm], check=True)
    g = -14 - lufs(pm)
    out = os.path.join(workdir, 'audio.wav')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', pm, '-af', f'volume={g:.2f}dB,alimiter=limit=0.89:level=false',
                    '-ar', str(SR), '-c:a', 'pcm_s16le', out], check=True)
    info = {'starts': starts, 'ends': ends, 'end': round(end, 2), 'off': off, 'blen': blen, 'final_lufs': lufs(out),
            'chars': sum(len(t) for t, _ in L)}
    json.dump(info, open(os.path.join(workdir, 'audio.json'), 'w'))
    return out, info
