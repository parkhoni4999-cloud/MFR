"""동물 실사 영상을 여러 출처에서 최대한 모은다 (편성은 그대로, 소재 품질 극대화).

사용법:
  python3 find_footage.py <저장폴더> --en "platypus" --sci "Ornithorhynchus anatinus" \
      --must platypus,ornithorhynchus [--extra "platypus swimming,platypus underwater"] \
      [--avoid "beaver,otter"] [--photos 6]

하는 일:
  1) Pixabay 영상: 영어 이름 + 추가 검색어 여러 개로 검색, 태그에 --must 단어가 있어야 채택
  2) Wikimedia Commons 영상: 학명/영어 이름으로 검색, CC0·퍼블릭도메인·CC BY만(SA/NC/ND 제외)
  3) 실사 영상이 3개 미만이면 Pixabay 사진을 보충 (--photos 개수)
  4) 각 영상의 '움직임 점수'를 재서 가장 역동적인 구간(best_ss)을 찾음
  5) footage.json(목록·추천 시작초), credits.json(출처), sheet_all.png(미리보기) 저장
반드시 sheet_all.png 를 직접 보고 다른 종/부적절한 장면이 없는지 확인할 것.
"""
import argparse, json, os, re, subprocess, time, urllib.error, urllib.parse, urllib.request
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('out'); ap.add_argument('--en', required=True); ap.add_argument('--sci', default='')
ap.add_argument('--must', required=True); ap.add_argument('--extra', default=''); ap.add_argument('--avoid', default='')
ap.add_argument('--photos', type=int, default=6); ap.add_argument('--max', type=int, default=10)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
MUST = [m.strip().lower() for m in a.must.split(',') if m.strip()]
AVOID = [m.strip().lower() for m in a.avoid.split(',') if m.strip()] + [
    'ai generated', 'cartoon', '3d', 'animation', 'fantasy', 'monster', 'food', 'cooking', 'grill', 'star wars', 'toy', 'logo', 'sculpture', 'statue', 'carving', 'wooden', 'figurine', 'model', 'plush', 'drawing', 'illustration', 'painting', 'green screen', 'chroma']
UA_PX = {'User-Agent': 'Mozilla/5.0 (shorts-pipeline)'}
UA_WM = {'User-Agent': 'ShortsPipelineBot/0.2 (https://github.com/parkhoni4999-cloud/mfr; non-commercial animal shorts) python-urllib'}
WM_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'wm_cache'); os.makedirs(WM_CACHE, exist_ok=True)
KEY = os.environ.get('PIXABAY_API_KEY')
cred_path = os.path.join(a.out, 'credits.json')
cred = json.load(open(cred_path)) if os.path.exists(cred_path) else []
have = {c['key'] for c in cred}
found = []

def ok_text(t):
    t = t.lower()
    return any(m in t for m in MUST) and not any(b in t for b in AVOID)

class FetchError(Exception):
    pass

def get(url, headers, timeout=60, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                ra = e.headers.get('Retry-After')
                time.sleep(min(45, int(ra)) if ra and ra.isdigit() else 15 * (i + 1)); continue
            raise FetchError(f'HTTP {e.code} ({url.split("?")[0]})')  # 쿼리(키 포함)는 출력하지 않음
    return b''

# ---- 1) Pixabay videos ----
if KEY:
    seen = set()
    for q in [a.en] + [x.strip() for x in a.extra.split(',') if x.strip()]:
        d = json.loads(get('https://pixabay.com/api/videos/?' + urllib.parse.urlencode(
            {'key': KEY, 'q': q, 'per_page': 50, 'safesearch': 'true'}), UA_PX))
        for h in d.get('hits', []):
            if h['id'] in seen or not ok_text(h['tags']) or h['duration'] < 5: continue
            seen.add(h['id'])
            L_, M_ = h['videos'].get('large', {}), h['videos'].get('medium', {})
            v = L_ if L_.get('url') and L_.get('width', 0) <= 1920 else (M_ if M_.get('url') else L_)
            k = f"px_{h['id']}"; dst = os.path.join(a.out, k + '.mp4')
            if not os.path.exists(dst): open(dst, 'wb').write(get(v['url'], UA_PX, 180))
            if k not in have:
                cred.append({'key': k, 'file': f"Pixabay video {h['id']}", 'artist': h.get('user', ''), 'license': 'Pixabay Content License', 'page': h.get('pageURL', '')}); have.add(k)
            found.append({'key': k, 'src': 'pixabay', 'kind': 'video', 'path': dst, 'desc': h['tags'][:80]})
            if len([f for f in found if f['kind'] == 'video']) >= a.max: break
else:
    print('PIXABAY_API_KEY 없음: Pixabay 건너뜀')
print(f"Pixabay 영상 {len(found)}개", flush=True)

# ---- 2) Wikimedia Commons videos ----
def wm_search(q):
    url = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode({
        'action': 'query', 'format': 'json', 'generator': 'search', 'gsrsearch': q, 'gsrnamespace': 6, 'gsrlimit': 30,
        'prop': 'imageinfo', 'iiprop': 'url|size|extmetadata', 'iiextmetadatafilter': 'LicenseShortName|Artist|ImageDescription'})
    cp = os.path.join(WM_CACHE, re.sub(r'[^a-zA-Z0-9]+', '_', q)[:80] + '.json')
    if os.path.exists(cp) and time.time() - os.path.getmtime(cp) < 30 * 86400:
        return json.load(open(cp)).get('query', {}).get('pages', {}).values()
    try:
        raw = get(url, UA_WM, tries=4)
        d = json.loads(raw); json.dump(d, open(cp, 'w'))
        time.sleep(4)
        return d.get('query', {}).get('pages', {}).values()
    except Exception as e:
        print('Wikimedia 검색 건너뜀:', e); return []

def lic_ok(L):
    L = L.upper()
    return ('CC0' in L or 'PUBLIC DOMAIN' in L or L.startswith('CC BY')) and not any(x in L for x in ('SA', 'NC', 'ND'))

wm_seen = set()
WM_DEADLINE = time.time() + 240  # Wikimedia 단계는 최대 4분
print('Wikimedia 검색...', flush=True)
for q in [f'{a.sci} filetype:video' if a.sci else None, f'{a.en} filetype:video']:
    if not q or time.time() > WM_DEADLINE: continue
    for p in wm_search(q):
        if time.time() > WM_DEADLINE:
            print('Wikimedia 시간 초과로 중단', flush=True); break
        i = p['imageinfo'][0]; m = i.get('extmetadata', {}); L = m.get('LicenseShortName', {}).get('value', '')
        title = p['title'][5:]; desc = re.sub('<[^>]+>', '', m.get('ImageDescription', {}).get('value', ''))
        if p['pageid'] in wm_seen or not lic_ok(L) or not ok_text(title + ' ' + desc): continue
        if i.get('duration', 0) < 4 or i.get('duration', 0) > 600 or i.get('width', 0) < 640: continue
        wm_seen.add(p['pageid'])
        name = i['url'].rsplit('/', 1)[1]; path = i['url'].split('/wikipedia/commons/')[1]
        k = f"wm_{p['pageid']}"; dst = os.path.join(a.out, k + '.webm')
        if not os.path.exists(dst):
            for qual in ('720p.vp9.webm', '480p.vp9.webm', '1080p.vp9.webm'):
                try:
                    data = get(f'https://upload.wikimedia.org/wikipedia/commons/transcoded/{path}/{name}.{qual}', UA_WM, 300, tries=2)
                    if data[:4] == b'\x1aE\xdf\xa3': open(dst, 'wb').write(data); break
                except FetchError:
                    continue
            time.sleep(3)
        if not os.path.exists(dst): continue
        if k not in have:
            cred.append({'key': k, 'file': title, 'artist': re.sub('<[^>]+>', '', m.get('Artist', {}).get('value', ''))[:80],
                         'license': L, 'page': i.get('descriptionurl', '')}); have.add(k)
        found.append({'key': k, 'src': 'wikimedia', 'kind': 'video', 'path': dst, 'desc': title[:80]})
    time.sleep(5)

# ---- 3) 사진 보충 (실사 영상이 부족할 때) ----
n_vid = len([f for f in found if f['kind'] == 'video'])
if KEY and n_vid < 3 and a.photos > 0:
    d = json.loads(get('https://pixabay.com/api/?' + urllib.parse.urlencode(
        {'key': KEY, 'q': a.en, 'image_type': 'photo', 'per_page': 40, 'safesearch': 'true'}), UA_PX))
    for h in [h for h in d.get('hits', []) if ok_text(h['tags'])][:a.photos]:
        k = f"pximg_{h['id']}"; jpg = os.path.join(a.out, k + '.jpg'); mp4 = os.path.join(a.out, k + '.mp4')
        if not os.path.exists(jpg): open(jpg, 'wb').write(get(h['largeImageURL'], UA_PX, 120))
        if not os.path.exists(mp4):
            subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-loop', '1', '-i', jpg, '-t', '12', '-r', '30', '-vf',
                            "scale='if(gt(iw,ih),1920,-2)':'if(gt(iw,ih),-2,1920)',format=yuv420p", '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', mp4], check=True)
        if k not in have:
            cred.append({'key': k, 'file': f"Pixabay photo {h['id']}", 'artist': h.get('user', ''), 'license': 'Pixabay Content License', 'page': h.get('pageURL', '')}); have.add(k)
        found.append({'key': k, 'src': 'pixabay', 'kind': 'photo', 'path': mp4, 'desc': h['tags'][:80]})

json.dump(cred, open(cred_path, 'w'), ensure_ascii=False, indent=1)

# ---- 4) 움직임 점수 + 추천 구간 ----
def probe(f):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'stream=width,height:format=duration', '-of', 'json', f], capture_output=True, text=True)
    j = json.loads(r.stdout); s = j['streams'][0]
    return float(j['format'].get('duration', 0) or 0), s['width'], s['height']

for f in found:
    dur, w, h = probe(f['path']); f.update(duration=round(dur, 1), w=w, h=h, portrait=h > w)
    if f['kind'] == 'photo':
        f.update(motion=0.0, best_ss=0); continue
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-t', '120', '-i', f['path'], '-vf', 'fps=2,scale=96:54,format=gray', '-f', 'rawvideo', '-'], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 54, 96).astype(np.float32) if raw else np.zeros((1, 54, 96))
    diff = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2)) if len(fr) > 1 else np.zeros(1)
    win = 8  # 4초 창
    sc = np.convolve(diff, np.ones(win) / win, mode='valid') if len(diff) >= win else diff
    bi = int(np.argmax(sc)) if len(sc) else 0
    f.update(motion=round(float(diff.mean()), 2), best_ss=round(bi / 2, 1))

order = sorted(found, key=lambda f: (f['kind'] != 'video', -f['motion']))
json.dump(order, open(os.path.join(a.out, 'footage.json'), 'w'), ensure_ascii=False, indent=1)
for f in order:
    print(f"{f['key']:<16} {f['kind']:<5} {f['src']:<9} {f['duration']:>5}s {f['w']}x{f['h']} motion={f['motion']:<5} best_ss={f['best_ss']:<5} | {f['desc']}")
print(f"실사 영상 {len([f for f in order if f['kind']=='video'])}개, 사진 {len([f for f in order if f['kind']=='photo'])}개")

# ---- 5) 미리보기 시트 ----
rows = []
for n, f in enumerate(order):
    imgs = []
    for j in range(4):
        t = min(f['duration'] - 0.1, f['best_ss'] + j * 1.2) if f['kind'] == 'video' else 0
        pth = os.path.join(a.out, f'_s{n}_{j}.png')
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-ss', str(max(0, t)), '-i', f['path'], '-frames:v', '1', '-vf',
                        f"scale=300:169:force_original_aspect_ratio=decrease,pad=300:169:(ow-iw)/2:(oh-ih)/2,drawtext=text='{f['key']} @{t:.1f}':fontcolor=yellow:fontsize=15:x=4:y=4", pth])
        imgs.append(pth)
    r = os.path.join(a.out, f'_r{n}.png')
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *sum([['-i', p] for p in imgs], []), '-filter_complex', 'hstack=4', r]); rows.append(r)
if rows:
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *sum([['-i', r] for r in rows], []), '-filter_complex',
                    f'vstack={len(rows)}' if len(rows) > 1 else 'null', os.path.join(a.out, 'sheet_all.png')])
for p in os.listdir(a.out):
    if p.startswith('_'): os.remove(os.path.join(a.out, p))
print('sheet', os.path.join(a.out, 'sheet_all.png'))
