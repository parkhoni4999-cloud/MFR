"""Wikimedia Commons 실사 사진 수집 (영상이 없는 동물용).

사용법:
  python3 wm_photos.py <저장폴더> --q "Pheropsophus jessoensis,Brachinus" [--max 14]

- Commons 사진 검색(filetype:bitmap), CC0·퍼블릭도메인·CC BY만(SA/NC/ND 제외)
- upload.wikimedia.org 1280px 썸네일로 8초 간격 다운로드, JPEG 시작 바이트 확인
- 각 사진을 12초 mp4(wmimg_ID.mp4)로 변환해 build.py의 clip으로 바로 사용
- credits.json에 출처 추가, wmlist.tsv 목록, sheet_photos.png 미리보기 저장
반드시 sheet_photos.png 를 직접 보고 다른 종·표본(핀 꽂힌 건조 표본)·그림을 뺄 것.
"""
import argparse, json, os, re, subprocess, time, urllib.error, urllib.parse, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument('out'); ap.add_argument('--q', required=True); ap.add_argument('--max', type=int, default=14)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
UA = {'User-Agent': 'ShortsPipelineBot/0.2 (https://github.com/parkhoni4999-cloud/mfr; non-commercial animal shorts) python-urllib'}


def get(url, timeout=60, tries=6):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                ra = e.headers.get('Retry-After')
                time.sleep(min(90, int(ra)) if ra and ra.isdigit() else 30 * (i + 1)); continue
            raise


def lic_ok(L):
    L = L.upper()
    return ('CC0' in L or 'PUBLIC DOMAIN' in L or L.startswith('CC BY')) and not any(x in L for x in ('SA', 'NC', 'ND'))


cred_path = os.path.join(a.out, 'credits.json')
cred = json.load(open(cred_path)) if os.path.exists(cred_path) else []
have = {c['key'] for c in cred}
rows, seen = [], set()
for q in [x.strip() for x in a.q.split(',') if x.strip()]:
    url = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode({
        'action': 'query', 'format': 'json', 'generator': 'search', 'gsrsearch': q + ' filetype:bitmap', 'gsrnamespace': 6,
        'gsrlimit': 50, 'prop': 'imageinfo', 'iiprop': 'url|size|extmetadata', 'iiurlwidth': 1280,
        'iiextmetadatafilter': 'LicenseShortName|Artist'})
    try:
        pages = json.loads(get(url)).get('query', {}).get('pages', {}).values()
    except Exception as e:
        print('검색 실패', q, e); continue
    for p in sorted(pages, key=lambda p: p.get('index', 0)):
        i = p['imageinfo'][0]; m = i.get('extmetadata', {}); L = m.get('LicenseShortName', {}).get('value', '')
        if p['pageid'] in seen or not lic_ok(L) or i.get('width', 0) < 800: continue
        if not p['title'].lower().endswith(('.jpg', '.jpeg')): continue
        seen.add(p['pageid'])
        rows.append({'key': f"wmimg_{p['pageid']}", 'thumb': i.get('thumburl', i['url']), 'license': L,
                     'artist': re.sub('<[^>]+>', '', m.get('Artist', {}).get('value', ''))[:80].strip(),
                     'file': p['title'][5:], 'page': i.get('descriptionurl', '')})
    time.sleep(5)
rows = rows[:a.max]
print('후보', len(rows), flush=True)

ok = []
for r in rows:
    jp = os.path.join(a.out, r['key'] + '.jpg')
    if not os.path.exists(jp):
        try:
            data = get(r['thumb'], 120)
        except Exception as e:
            print('다운로드 실패', r['key'], e); time.sleep(8); continue
        if data[:2] != b'\xff\xd8':
            print('JPEG 아님', r['key']); time.sleep(8); continue
        open(jp, 'wb').write(data); time.sleep(8)
    mp = os.path.join(a.out, r['key'] + '.mp4')
    if not os.path.exists(mp):
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-loop', '1', '-i', jp, '-t', '12', '-r', '30',
                        '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', '-pix_fmt', 'yuv420p', '-c:v', 'libx264', mp], check=True)
    if r['key'] not in have:
        cred.append({k: r[k] for k in ('key', 'file', 'artist', 'license', 'page')}); have.add(r['key'])
    ok.append(r)
json.dump(cred, open(cred_path, 'w'), ensure_ascii=False, indent=1)
with open(os.path.join(a.out, 'wmlist.tsv'), 'w') as f:
    for r in ok:
        f.write('\t'.join([r['key'], r['thumb'], r['license'], r['artist'], r['page']]) + '\n')

if ok:  # 미리보기 시트
    from PIL import Image, ImageDraw
    W, H, C = 400, 300, 4
    sheet = Image.new('RGB', (W * C, H * ((len(ok) + C - 1) // C)), 'black'); d = ImageDraw.Draw(sheet)
    for n, r in enumerate(ok):
        im = Image.open(os.path.join(a.out, r['key'] + '.jpg')).convert('RGB'); im.thumbnail((W, H - 20))
        x, y = (n % C) * W, (n // C) * H; sheet.paste(im, (x, y)); d.text((x + 4, y + H - 18), r['key'], fill='yellow')
    sheet.save(os.path.join(a.out, 'sheet_photos.png'))
print('사진', len(ok), '개 ->', os.path.join(a.out, 'sheet_photos.png'))
