"""Pixabay에서 동물 영상을 검색해 내려받고, 확인용 미리보기(contact sheet)를 만든다.
사용법: python3 fetch_pixabay.py "<영어 검색어>" <저장폴더> [개수=6] [--must 태그단어]
- 키: 환경변수 PIXABAY_API_KEY (출력/커밋 금지)
- --must: 태그에 이 단어가 있는 결과만 사용 (예: --must octopus). 기본은 검색어의 첫 단어.
결과: <저장폴더>/px_<id>.mp4, <저장폴더>/credits.json(추가), <저장폴더>/sheet_<검색어>.png
"""
import json, os, subprocess, sys, urllib.error, urllib.parse, urllib.request

argv = sys.argv[1:]
must = None
if '--must' in argv:
    i = argv.index('--must'); must = argv[i + 1].lower(); del argv[i:i + 2]
q, out = argv[0], argv[1]
n = int(argv[2]) if len(argv) > 2 else 6
must = must or q.split()[0].lower()
key = os.environ.get('PIXABAY_API_KEY')
if not key:
    raise SystemExit('PIXABAY_API_KEY 환경변수가 없습니다 (환경 설정에 추가 후 새 세션 필요)')
os.makedirs(out, exist_ok=True)
url = 'https://pixabay.com/api/videos/?' + urllib.parse.urlencode({'key': key, 'q': q, 'per_page': 50, 'safesearch': 'true', 'order': 'popular'})
UA = {'User-Agent': 'Mozilla/5.0 (shorts-pipeline)'}
try:
    data = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30))
except urllib.error.HTTPError as e:
    raise SystemExit(f'Pixabay 검색 실패: HTTP {e.code}')  # URL(키 포함)은 출력하지 않음
BAD = ('ai generated', 'cartoon', '3d', 'animation', 'fantasy', 'monster', 'food', 'cooking', 'grill')
hits = [h for h in data.get('hits', []) if must in h['tags'].lower() and h['duration'] >= 6 and not any(b in h['tags'].lower() for b in BAD)]
hits.sort(key=lambda h: (-(h['videos'].get('large', {}).get('width', 0) >= 1920), -h.get('likes', 0)))
cred_path = os.path.join(out, 'credits.json')
cred = json.load(open(cred_path)) if os.path.exists(cred_path) else []
have = {c['key'] for c in cred}
got = []
for h in hits[:n]:
    v = h['videos'].get('large') or h['videos'].get('medium')
    if not v or not v.get('url'):
        v = h['videos'].get('medium')
    k = f"px_{h['id']}"
    dst = os.path.join(out, k + '.mp4')
    if not os.path.exists(dst):
        with urllib.request.urlopen(urllib.request.Request(v['url'], headers=UA), timeout=120) as r, open(dst, 'wb') as fo:
            fo.write(r.read())
    if k not in have:
        cred.append({'key': k, 'file': f"Pixabay video {h['id']}", 'artist': h.get('user', ''), 'license': 'Pixabay Content License',
                     'page': h.get('pageURL', ''), 'tags': h['tags'], 'duration': h['duration']})
    got.append((k, h['duration'], v.get('width'), v.get('height'), h['tags']))
json.dump(cred, open(cred_path, 'w'), ensure_ascii=False, indent=1)
for g in got:
    print(*g, sep=' | ')
# 미리보기: 각 영상에서 4장씩
rows = []
for k, d, *_ in got:
    f = os.path.join(out, k + '.mp4'); imgs = []
    for j in range(1, 5):
        p = os.path.join(out, f'_{k}_{j}.png')
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-ss', str(d * j / 5), '-i', f, '-frames:v', '1', '-vf',
                        f"scale=320:180:force_original_aspect_ratio=decrease,pad=320:180,drawtext=text='{k} @{d*j/5:.1f}':fontcolor=yellow:fontsize=18:x=4:y=4", p])
        imgs.append(p)
    r = os.path.join(out, f'_{k}_row.png')
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *sum([['-i', p] for p in imgs], []), '-filter_complex', 'hstack=4', r]); rows.append(r)
if rows:
    sheet = os.path.join(out, f"sheet_{q.replace(' ', '_')}.png")
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *sum([['-i', r] for r in rows], []), '-filter_complex', f'vstack={len(rows)}' if len(rows) > 1 else 'null', sheet])
    for p in os.listdir(out):
        if p.startswith('_'): os.remove(os.path.join(out, p))
    print('sheet', sheet)
