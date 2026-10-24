"""Golden Core – volledige render op GitHub Actions.
Invoer: job-JSON (env JOB_FILE of JOB). Uitvoer: video privé op YouTube via Publer + callback naar Make.
"""
import json, os, sys, subprocess, math, time, base64, hashlib, re, shutil, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get('GC_WORK', os.path.join(ROOT, 'work'))
os.makedirs(WORK, exist_ok=True)
CORES = os.cpu_count() or 2
PUBLER_WS = '6ac92661e73f366e1cbf06bd'
PUBLER_YT = '6ac9268cd50a326640634e3c'
REPO = os.environ.get('GITHUB_REPOSITORY', 'LikedeMaat/golden-core-render')
ENC = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-tune', 'film', '-pix_fmt', 'yuv420p', '-r', '24', '-g', '48',
       '-an', '-video_track_timescale', '12288']


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def http(url, data=None, headers=None, method=None, timeout=120):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


# ---------- bestanden ----------
def drive_download(fid, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    url = f'https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t'
    for i in range(4):
        try:
            sh(['curl', '-sSL', '--fail', '-o', path, url])
            head = open(path, 'rb').read(200)
            if b'<html' in head.lower() or b'<!doctype' in head.lower():
                raise RuntimeError('Drive gaf een HTML-pagina (bestand niet gedeeld?)')
            return path
        except Exception as e:
            log('download mislukt', fid, e); time.sleep(5 * (i + 1))
    raise RuntimeError(f'Kan Drive-bestand {fid} niet downloaden')


def fonts():
    d = os.path.join(WORK, 'fonts'); os.makedirs(d, exist_ok=True)
    if all(os.path.exists(os.path.join(d, f'Cormorant-{w}.ttf')) for w in (500, 600, 700)):
        return d
    var = os.path.join(d, 'var.ttf')
    for u in ['https://github.com/google/fonts/raw/main/ofl/cormorant/Cormorant%5Bwght%5D.ttf',
              'https://github.com/google/fonts/raw/main/ofl/cormorantgaramond/CormorantGaramond%5Bwght%5D.ttf']:
        try:
            sh(['curl', '-sSL', '--fail', '-o', var, u]); break
        except Exception:
            continue
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    for w in (500, 600, 700):
        f = TTFont(var)
        instancer.instantiateVariableFont(f, {'wght': w}, inplace=True)
        f.save(os.path.join(d, f'Cormorant-{w}.ttf'))
    return d


# ---------- codescène (gecachet als release-asset) ----------
def gh(*args, check=True):
    return subprocess.run(['gh', *args, '-R', REPO], capture_output=True, text=True, check=check)


def codescene(name):
    out = []
    names = [f'{name}-deel1.mp4', f'{name}-deel2.mp4']
    paths = [os.path.join(WORK, n) for n in names]
    if all(os.path.exists(p) for p in paths):
        return paths
    r = gh('release', 'view', 'loops-v1', check=False)
    if r.returncode != 0:
        gh('release', 'create', 'loops-v1', '--title', 'Codescène-loops', '--notes', 'Gecachete 24s-loops (2 helften).', check=False)
    have = gh('release', 'view', 'loops-v1', '--json', 'assets', '-q', '.assets[].name', check=False).stdout.split()
    if all(n in have for n in names):
        gh('release', 'download', 'loops-v1', '-p', f'{name}-deel*.mp4', '-D', WORK, '--clobber')
        return paths
    log('codescène renderen:', name)
    script = os.path.join(ROOT, 'scenes', f'{name}.py')
    procs = []
    for (a, b), p in zip([(0, 288), (288, 576)], paths):
        procs.append(subprocess.Popen([sys.executable, script, str(a), str(b), p], cwd=WORK))
    for pr in procs:
        if pr.wait() != 0:
            raise RuntimeError('codescène render faalt')
    gh('release', 'upload', 'loops-v1', *paths, '--clobber', check=False)
    return paths


# ---------- script ----------
def norm(s):
    return re.sub(r'[^a-z0-9 ]', '', s.lower().replace('’', "'")).strip()


def split_sentences(text):
    parts = re.split(r'(?<=[.;?!])\s+(?=[A-Z"“])', text.strip())
    return [p.strip() for p in parts if p.strip()]


def prepare_script(job):
    P = [dict(p) for p in job['script']['paragraphs']]
    fixes = {int(f['n']): f['text'] for f in job['script'].get('fixes', []) if f.get('text')}
    for p in P:
        if int(p['n']) in fixes:
            p['text'] = fixes[int(p['n'])]
    oq = job.get('opening_quote')
    if oq:
        P[0]['text'] = '"' + oq.strip().strip('"“”') + '"'
    passage = job.get('closing_passage')
    cl = [norm(x) for x in job['script'].get('closing_quote_lines', [])]
    if passage:
        sents = split_sentences(passage)
        cljoin = ' '.join(cl) + ' ' + norm(passage)
        lo = max(1, len(P) - 16)
        idx = [i for i in range(lo, len(P)) if len(norm(P[i]['text'])) >= 12 and norm(P[i]['text']) in cljoin]
        if idx:  # alleen het laatste aaneengesloten blok
            run = [idx[-1]]
            for i in reversed(idx[:-1]):
                if run[0] - i <= 1:
                    run.insert(0, i)
                else:
                    break
            idx = run
        if idx:
            a, b = min(idx), max(idx)
            last_pause = P[b]['pause_after_sec']
            block = []
            for k, s in enumerate(sents):
                block.append({'n': 0, 'section': P[a]['section'], 'text': s, 'pause_after_sec': 1.2 if k < len(sents) - 1 else last_pause})
            P = P[:a] + block + P[b + 1:]
        else:
            tail = P[-2:] if len(P) > 2 else []
            head = P[:-2] if len(P) > 2 else P
            name = job.get('philosopher', 'He').split()[-1]
            block = [{'n': 0, 'section': 'closing', 'text': f'{name} said it like this.', 'pause_after_sec': 2}]
            for k, s in enumerate(sents):
                block.append({'n': 0, 'section': 'closing', 'text': s, 'pause_after_sec': 1.2 if k < len(sents) - 1 else 4})
            P = head + block + tail
            a = len(head) + 1; b = a + len(sents) - 1
        sents_idx = list(range(a, a + len(sents)))
        # aanhalingstekens rond de passage
        P[sents_idx[0]]['text'] = '"' + P[sents_idx[0]]['text'].lstrip('"“')
        P[sents_idx[-1]]['text'] = P[sents_idx[-1]]['text'].rstrip('"”') + '"'
    else:
        sents = []; sents_idx = []
    for i, p in enumerate(P):
        p['n'] = i + 1
    return P, sents, sents_idx


# ---------- plan ----------
SECTION_MAP = {'hook': 'B', 'story': 'S', 'arrival': 'D', 'recognition': 'D', 'acceptance': 'S', 'application': 'D',
               'commitment': 'T', 'turning_point': 'T', 'execution': 'E', 'decision': 'E', 'closing': 'B'}


def plan(P, starts, end, closing_idx, n_story, has_e, first_end=0.0):
    """Bepaal beeldsegmenten (letter, start, aantal 12s-loops) op een 12 s-raster."""
    marks = []  # (letter, tijd)
    for i, p in enumerate(P):
        let = 'B' if p['section'] == P[0]['section'] and (not marks or marks[-1][0] == 'B') else SECTION_MAP.get(p['section'], 'D')
        if let == 'E' and not has_e:
            let = 'D'
        if closing_idx and i >= closing_idx[0] - 1:
            let = 'B'
        if not marks or marks[-1][0] != let:
            marks.append((let, 0.0 if i == 0 else starts[i] - 0.5))
    total = int(math.ceil((end + 0.5) / 12) * 12)
    segs = []
    min_after_b = int(math.ceil((first_end + 2.5) / 12) * 12)
    for let, t in marks:
        s = int(round(t / 12) * 12)
        if len(segs) == 1:
            s = max(s, min_after_b)
        if segs:
            s = max(s, segs[-1][1] + 12)
            if s >= total:
                break
        if segs and segs[-1][0] == let:
            continue
        segs.append([let, s])
    if closing_idx:
        # slot-buste moet uiterlijk 6 s voor de eerste slotcitaatregel beginnen
        cs = int(math.floor((starts[closing_idx[0]] - 6) / 12) * 12)
        if segs[-1][0] == 'B' and len(segs) > 1 and cs > segs[-2][1]:
            segs[-1][1] = min(segs[-1][1], cs)
    out = []
    for k, (let, s) in enumerate(segs):
        e = segs[k + 1][1] if k + 1 < len(segs) else total
        n = (e - s) // 12
        if n <= 0:
            continue
        if let == 'S' and n_story >= 2 and n >= 2:
            h = n // 2
            out.append(('S1', s, h)); out.append(('S2', s + 12 * h, n - h))
        else:
            out.append(('S1' if let == 'S' else let, s, n))
    return out, total


def build_pieces(segs, src, ov, fade_end):
    pieces = []
    for si, (s, t0, n) in enumerate(segs):
        for j in range(n):
            S = t0 + 12 * j; vf = []
            if j == 0:
                vf.append(f"fade=t=in:st=0:d={3 if si == 0 else 0.8}")
            if j == n - 1 and si < len(segs) - 1:
                vf.append('fade=t=out:st=11.2:d=0.8')
            if S <= fade_end < S + 12:
                vf.append(f'fade=t=out:st={fade_end - S:.2f}:d=5')
            if S >= fade_end + 5:
                vf.append('fade=t=out:st=0:d=0.1')
            o = []
            for png, ti, to in ov:
                if ti - 0.3 < S + 12 and (to is None or to + 1.5 > S):
                    st = ti - 0.3 - S; f = 'format=rgba'
                    if st + 1.6 > 0:
                        f += f",fade=t=in:st={max(st, 0):.2f}:d={min(1.6, 1.6 + st):.2f}:alpha=1"
                    if to is not None and to < S + 12:
                        f += f",fade=t=out:st={max(to - S, 0):.2f}:d=1.5:alpha=1"
                    o.append((png, f))
            key_src = s
            if s == 'T' and j % 2 == 1:
                key_src = 'U'
            key = hashlib.md5(json.dumps([key_src, src[key_src], vf, o]).encode()).hexdigest()[:12]
            pieces.append((key, src[key_src], vf, o))
    return pieces


def render_piece(pc):
    key, srcf, vf, o = pc
    out = os.path.join(WORK, 'pieces', f'p_{key}.mp4')
    if os.path.exists(out):
        return out
    ins = ['-i', srcf]; fc = f"[0:v]{','.join(vf) if vf else 'null'}[b];"; last = 'b'
    for k, (png, f) in enumerate(o):
        ins += ['-loop', '1', '-t', '12', '-i', png]
        fc += f"[{k + 1}:v]{f}[q{k}];[{last}][q{k}]overlay=0:0:shortest=1[o{k}];"; last = f'o{k}'
    fc += f"[{last}]null[v]"
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-threads', '2', *ins, '-filter_complex', fc, '-map', '[v]', '-t', '12', *ENC, out + '.tmp.mp4'])
    os.replace(out + '.tmp.mp4', out)
    return out


# ---------- Publer ----------
def publer(method, path, body=None):
    key = os.environ['PUBLER_KEY']
    h = {'Authorization': f'Bearer-API {key}', 'Publer-Workspace-Id': PUBLER_WS, 'Accept': 'application/json',
         'Content-Type': 'application/json'}
    st, data = http('https://app.publer.com/api/v1' + path, data=json.dumps(body).encode() if body is not None else None,
                    headers=h, method=method)
    return json.loads(data or b'{}')


def publer_job(job_id, max_wait=1800):
    t0 = time.time()
    while time.time() - t0 < max_wait:
        time.sleep(20)
        r = publer('GET', f'/job_status/{job_id}')
        d = r.get('data', r)
        if d.get('status') == 'complete':
            return d
        if d.get('status') == 'failed':
            raise RuntimeError('Publer job faalt: ' + json.dumps(d)[:500])
    raise RuntimeError('Publer job duurt te lang')


def upload_youtube(video, job):
    tag = f"run-{job['row']}-{int(time.time())}"
    gh('release', 'create', tag, video, '--title', tag, '--notes', 'tijdelijk voor Publer')
    url = f'https://github.com/{REPO}/releases/download/{tag}/{os.path.basename(video)}'
    try:
        r = publer('POST', '/media/from-url', {'media': [{'url': url, 'name': os.path.basename(video)}], 'type': 'single',
                                                 'direct_upload': False, 'in_library': False})
        d = publer_job(r['job_id'])
        payload = d.get('payload') or d.get('result', {}).get('payload')
        mid = payload[0]['id']
        body = {'bulk': {'state': 'scheduled', 'posts': [{'networks': {'youtube': {
            'type': 'video', 'title': job['title'], 'privacy': 'private', 'category': '27', 'text': job['description'],
            'media': [{'id': mid, 'type': 'video', 'title': job['title']}]}}, 'accounts': [{'id': PUBLER_YT}]}]}}
        r = publer('POST', '/posts/schedule/publish', body)
        d = publer_job(r['job_id'])
        payload = d.get('payload') or d.get('result', {}).get('payload')
        post = payload[0].get('post', {})
        if post.get('error'):
            raise RuntimeError('Publer post-fout: ' + str(post.get('error')))
        link = post.get('post_link')
        for _ in range(12):
            if link:
                break
            time.sleep(20)
            link = (publer('GET', f"/posts/{post.get('id')}") or {}).get('post_link')
        return link
    finally:
        gh('release', 'delete', tag, '--yes', '--cleanup-tag', check=False)


def callback(job, payload):
    url = job.get('callback_url')
    if not url:
        return
    try:
        http(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST', timeout=60)
    except Exception as e:
        log('callback faalt', e)


# ---------- job normaliseren (Make levert script_raw + plan) ----------
BUST_PROMPT = ("Photographic close-up of an ancient white marble bust of the philosopher {name}, true to known portraits. "
               "Three-quarter view. The face is clearly and fully lit by one warm golden key light from the front left, eyes and "
               "features detailed and visible, soft falloff into deep shadow on the far side. Pure near-black background with lots "
               "of empty dark space. Cinematic, premium, 85mm lens, shallow depth of field, subtle film grain, no text, no logo.")
THUMB_PROMPT = ("Photographic portrait of an ancient dark marble bust of the philosopher {name}, true to known portraits, intense "
                "calm gaze. Three-quarter view, bust placed on the left third of the frame. The whole face is clearly and brightly lit "
                "by a strong warm golden key light from the front, eyes, nose and brow sharp and well visible, gentle rim light. "
                "Near-black background, large empty dark space on the right two thirds for text. Premium, high contrast, 85mm lens, "
                "subtle film grain, no text, no logo.")


def normalize(job):
    if 'script_raw' not in job:
        return job
    sr = job['script_raw']
    if isinstance(sr, str):
        sr = json.loads(sr)
    sc = sr.get('script', sr)
    fc = sr.get('factcheck') or {}
    plan_ = job.get('plan') or {}
    if isinstance(plan_, str):
        plan_ = json.loads(plan_) if plan_.strip() else {}
    job['script'] = {'paragraphs': sc['paragraphs'], 'closing_quote_lines': sc.get('closing_quote_lines', []),
                     'fixes': fc.get('fixes', [])}
    job['philosopher'] = plan_.get('philosopher') or sc.get('philosopher', '')
    job['format'] = plan_.get('format') or job.get('format', 'Deep')
    job['title'] = plan_.get('title') or sc.get('title')
    job['thumb_text'] = plan_.get('thumb_text') or (sc.get('thumbnail') or {}).get('text_overlay', '')
    job['code_scene'] = plan_.get('code_scene') or 'kern'
    if plan_.get('quote'):
        job['opening_quote'] = plan_['quote']
    if plan_.get('closing_passage'):
        job['closing_passage'] = plan_['closing_passage']
    src = plan_.get('source', ''); tr = plan_.get('translation', '')
    job['quote_source'] = plan_.get('source_line') or (f"{job['philosopher']}, {src}" + (f" (tr. {tr})" if tr else ''))
    desc = ((sc.get('youtube') or {}).get('description') or '').strip()
    if job.get('opening_quote'):
        lines = desc.split('\n')
        q = '"' + job['opening_quote'].strip().strip('"“”') + '"'
        if lines and lines[0].startswith(('"', '“')):
            lines[0] = q
        else:
            lines = [q, ''] + lines
        desc = '\n'.join(lines)
    job['description'] = desc
    imgs = plan_.get('images') or {}
    scenes = sc.get('scenes', [])
    story = imgs.get('story') or [s['image_prompt'] for s in scenes if s.get('section') in ('story', 'acceptance')]
    desk = imgs.get('desk') or [s['image_prompt'] for s in scenes if s.get('section') not in ('story', 'acceptance')]
    if not story and desk:
        story = desk[1:2]
    nmax = 2 if job['format'] == 'Deep' else 1
    job['image_prompts'] = {'bust': BUST_PROMPT.format(name=job['philosopher']),
                            'thumb': THUMB_PROMPT.format(name=job['philosopher']),
                            'story': story[:nmax], 'desk': desk[:nmax] or story[:1]}
    return job


def openai_image(prompt, path, quality='medium'):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    body = {'model': 'gpt-image-2', 'prompt': prompt.replace('"', ''), 'size': '1536x1024', 'quality': quality, 'n': 1}
    for i in range(4):
        try:
            st, data = http('https://api.openai.com/v1/images/generations', data=json.dumps(body).encode(),
                            headers={'Authorization': 'Bearer ' + os.environ['OPENAI_KEY'], 'Content-Type': 'application/json'},
                            method='POST', timeout=300)
            open(path, 'wb').write(base64.b64decode(json.loads(data)['data'][0]['b64_json']))
            return path
        except Exception as e:
            log('beeld mislukt', i, str(e)[:200]); time.sleep(10 * (i + 1))
    raise RuntimeError('OpenAI-beeld faalt: ' + prompt[:60])


def make_images(job, A):
    ip = job['image_prompts']
    tasks = [('bust', ip['bust'], 'medium'), ('thumb', ip['thumb'], 'high')]
    tasks += [(f'story{k}', p, 'medium') for k, p in enumerate(ip['story'])]
    tasks += [(f'desk{k}', p, 'medium') for k, p in enumerate(ip['desk'])]
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda t: openai_image(t[1], os.path.join(A, t[0] + '.png'), t[2]), tasks))
    out = {'story': [], 'desk': []}
    for (name, _, _), path in zip(tasks, res):
        if name in ('bust', 'thumb'):
            out[name] = path
        else:
            out[name.rstrip('0123456789')].append(path)
    return out


# ---------- hoofdprogramma ----------
def main():
    job = json.load(open(os.environ['JOB_FILE'])) if os.environ.get('JOB_FILE') else json.loads(os.environ['JOB'])
    job = normalize(job)
    row = job['row']; fmt = job.get('format', 'Deep')
    sys.path.insert(0, ROOT)
    import voice
    fd = fonts(); os.environ['GC_FONTS'] = fd

    # downloads
    A = os.path.join(WORK, 'assets'); os.makedirs(A, exist_ok=True)
    beat = drive_download(job['beat']['id'], os.path.join(A, 'beat' + os.path.splitext(job['beat'].get('name', 'b.mp3'))[1]))
    if job.get('image_prompts'):
        im = make_images(job, A)
        bust, thumbsrc, story, desk = im['bust'], im['thumb'], im['story'], im['desk']
    else:
        imgs = job['images']
        bust = drive_download(imgs['bust'], os.path.join(A, 'bust.png'))
        thumbsrc = drive_download(imgs.get('thumb', imgs['bust']), os.path.join(A, 'thumb.png'))
        story = [drive_download(i, os.path.join(A, f'story{k}.png')) for k, i in enumerate(imgs.get('story', []))]
        desk = [drive_download(i, os.path.join(A, f'desk{k}.png')) for k, i in enumerate(imgs.get('desk', []))]
    log('beelden klaar', len(story), 'verhaal', len(desk), 'bureau')
    hook_v = drive_download(job['hook']['video'], os.path.join(A, 'hook_v.mp4'))
    hook_a = drive_download(job['hook']['audio'], os.path.join(A, 'hook_a.wav')) if job['hook'].get('audio') else None

    # script + stem (parallel met animaties)
    P, sents, sidx = prepare_script(job)
    json.dump(P, open(os.path.join(WORK, 'script_final.json'), 'w'), indent=1, ensure_ascii=False)
    log('script regels', len(P), 'slotpassage', len(sents))

    log('animaties starten')
    anim = os.path.join(ROOT, 'animate.py')
    env = dict(os.environ, MODE='ai', NP='260', DUST='0.4')
    jobs_anim = []
    bl = os.path.join(A, 'bust_left.png'); sh([sys.executable, os.path.join(ROOT, 'bust_left.py'), bust, bl])
    todo = [('B', bl)] + [(f'S{k + 1}', p) for k, p in enumerate(story)] + [('D' if k == 0 else 'E', p) for k, p in enumerate(desk)]
    for let, p in todo:
        out = os.path.join(WORK, f'loop_{let}.mp4')
        jobs_anim.append((let, out, subprocess.Popen([sys.executable, anim, p, out], env=env, cwd=WORK)))

    scene_name = job.get('code_scene', 'kern')
    with ThreadPoolExecutor(1) as ex:
        fut_scene = ex.submit(codescene, scene_name)
        wav, info = voice.make_audio(P, beat, os.environ['CARTESIA_KEY'], os.path.join(WORK, 'audio'),
                                     off=job['beat'].get('off'), blen=job['beat'].get('blen'))
        scene_paths = fut_scene.result()
    log('audio klaar', info['end'], 's, LUFS', info['final_lufs'])
    src = {}
    for let, out, pr in jobs_anim:
        if pr.wait() != 0:
            raise RuntimeError('animatie faalt: ' + let)
        src[let] = out
    src['T'], src['U'] = scene_paths
    if 'S1' not in src:
        src['S1'] = src.get('D', src['B'])
    if 'D' not in src:
        src['D'] = src.get('S1', src['B'])
    log('animaties klaar')

    # overlays
    starts, ends, end = info['starts'], info['ends'], info['end']
    src_line = job.get('quote_source', '')
    cfg = {'prefix': os.path.join(WORK, 'q'), 'source': src_line,
           'opening': P[0]['text'].strip('"“”'), 'closing': []}
    if sents:
        if len(sents) > 1:
            cfg['closing'] = [' '.join(sents[:-1]).strip('"“”'), sents[-1].strip('"“”')]
        else:
            cfg['closing'] = [sents[0].strip('"“”')]
    json.dump(cfg, open(os.path.join(WORK, 'q.json'), 'w'))
    sh([sys.executable, os.path.join(ROOT, 'quotes.py'), os.path.join(WORK, 'q.json')])
    ov = [(os.path.join(WORK, 'q_q_open.png'), starts[0], ends[0] + 0.8)]
    if sents:
        ov.append((os.path.join(WORK, 'q_q1.png'), starts[sidx[0]] - 0.2, None))
        if len(sents) > 1:
            ov.append((os.path.join(WORK, 'q_q2.png'), starts[sidx[-1]] - 0.2, None))

    segs, total = plan(P, starts, end, sidx, len(story), 'E' in src, first_end=ends[0])
    log('plan', segs)
    fade_end = end - 5
    pieces = build_pieces(segs, src, ov, fade_end)
    os.makedirs(os.path.join(WORK, 'pieces'), exist_ok=True)
    uniq = {}
    for pc in pieces:
        uniq.setdefault(pc[0], pc)
    log('stukken', len(pieces), 'uniek', len(uniq))
    with ThreadPoolExecutor(max(1, CORES // 2)) as ex:
        list(ex.map(render_piece, uniq.values()))
    lst = os.path.join(WORK, 'list.txt')
    open(lst, 'w').write(''.join(f"file '{os.path.join(WORK, 'pieces', 'p_' + p[0] + '.mp4')}'\n" for p in pieces))
    main_mp4 = os.path.join(WORK, 'main.mp4')
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-i', wav, '-map', '0:v', '-map', '1:a',
        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '2', '-shortest', main_mp4])

    # hook vooraan
    hk = os.path.join(WORK, 'hook_va.mp4')
    if hook_a:
        sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', hook_v, '-i', hook_a, '-map', '0:v', '-map', '1:a',
            '-vf', 'scale=1920:1080:flags=lanczos,fps=24,format=yuv420p', *[x for x in ENC if x != '-an'],
            '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '2', '-shortest', hk])
    else:
        sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', hook_v, '-vf', 'scale=1920:1080:flags=lanczos,fps=24,format=yuv420p',
            *[x for x in ENC if x != '-an'], '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '2', hk])
    open(os.path.join(WORK, 'hl.txt'), 'w').write(f"file '{hk}'\nfile '{main_mp4}'\n")
    video = os.path.join(WORK, f"{row}-golden-core.mp4")
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', os.path.join(WORK, 'hl.txt'), '-c', 'copy',
        '-movflags', '+faststart', video])
    dur = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', video]).decode())
    size = os.path.getsize(video)
    log('video klaar', round(dur), 's', round(size / 1e6), 'MB')

    # controle-stills
    sheet = os.path.join(WORK, 'check.jpg')
    ts = [3, 9, 20, starts[len(starts) // 3] + 7, starts[len(starts) * 2 // 3] + 7, dur - 15]
    for k, t in enumerate(ts):
        sh(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{t:.1f}', '-i', video, '-frames:v', '1', '-vf', 'scale=480:270', os.path.join(WORK, f'c{k}.jpg')])
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', os.path.join(WORK, 'c%d.jpg'), '-vf', 'tile=2x3', '-frames:v', '1', sheet])

    # thumbnail
    th = os.path.join(WORK, 'thumbnail.jpg')
    sh([sys.executable, os.path.join(ROOT, 'thumb.py'), thumbsrc, fmt.lower(), job.get('thumb_text', ''), th])

    # upload
    link = upload_youtube(video, job) if not job.get('no_upload') else None
    log('YouTube', link)
    callback(job, {'row': row, 'status': 'ok', 'post_link': link or '', 'title': job['title'], 'duration_sec': round(dur),
                   'size_mb': round(size / 1e6), 'chars': info['chars'], 'final_lufs': info['final_lufs'],
                   'thumb_b64': base64.b64encode(open(th, 'rb').read()).decode(),
                   'check_b64': base64.b64encode(open(sheet, 'rb').read()).decode(),
                   'shared_ids': job.get('shared_ids', []),
                   'run_url': f"https://github.com/{REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"})
    shutil.copy(th, os.path.join(WORK, 'out_thumbnail.jpg')); shutil.copy(sheet, os.path.join(WORK, 'out_check.jpg'))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log('FOUT', repr(e))
        try:
            job = json.load(open(os.environ['JOB_FILE'])) if os.environ.get('JOB_FILE') else json.loads(os.environ['JOB'])
            callback(job, {'row': job.get('row'), 'status': 'error', 'message': str(e)[:800], 'shared_ids': job.get('shared_ids', []),
                           'run_url': f"https://github.com/{REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"})
        except Exception:
            pass
        raise
