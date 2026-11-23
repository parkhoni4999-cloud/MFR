"""쇼츠 1편 빌드: script_<id>.json -> 음성(edge-tts) -> 실사 배경(Wikimedia 클립) -> 자막/그래픽 합성 -> mp4 + 업로드용 설명문.
사용법: python3 build.py script_short01.json <clips_dir> <out_dir>
"""
import asyncio, json, math, os, subprocess, sys, wave
import numpy as np
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SCRIPT, CLIPS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.environ.get('SHORTS_FONT_DIR', os.path.join(HERE, 'fonts'))
EMOJI = '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'
W, H, FPS, SR, GAP = 1080, 1920, 30, 24000, 0.22
os.makedirs(OUT, exist_ok=True)
S = json.load(open(SCRIPT))
sc = S['scenes']
TMP = os.path.join(OUT, 'tmp'); os.makedirs(TMP, exist_ok=True)

def run(*a):
    subprocess.run(a, check=True)

# ---------------- 1. voice ----------------
async def tts():
    proxy = os.environ.get('HTTPS_PROXY')
    for i, s in enumerate(sc):
        await edge_tts.Communicate(s['text'], S['voice'], rate=S.get('rate', '+0%'), proxy=proxy).save(f'{TMP}/v{i}.mp3')
if S.get('voice_file'):
    # 외부(ElevenLabs) 내레이션 1개 파일 -> 무음 구간을 찾아 장면 경계 추정
    import re
    vf_ = os.path.join(os.path.dirname(os.path.abspath(SCRIPT)), S['voice_file'])
    run('ffmpeg', '-loglevel', 'error', '-y', '-i', vf_, '-ac', '1', '-ar', str(SR), '-f', 's16le', f'{TMP}/vall.raw')
    vall = np.fromfile(f'{TMP}/vall.raw', np.int16).astype(np.float32) / 32768
    det = subprocess.run(['ffmpeg', '-i', vf_, '-af', 'silencedetect=noise=-35dB:d=0.18', '-f', 'null', '-'], capture_output=True, text=True).stderr
    sil = [(float(a), float(b)) for a, b in zip(re.findall(r'silence_start: ([\d.]+)', det), re.findall(r'silence_end: ([\d.]+)', det))]
    mids = [(a + b) / 2 for a, b in sil]
    dur_all = len(vall) / SR
    # 무음으로 자른 조각을 음성인식 -> 대본 문장과 글자 유사도로 순서대로 매칭(DP)
    import difflib, sherpa_onnx
    AM = os.environ.get('SHORTS_ASR_DIR', os.path.join(HERE, 'models', 'sherpa-onnx-zipformer-korean-2024-06-24'))
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(encoder=f'{AM}/encoder-epoch-99-avg-1.int8.onnx', decoder=f'{AM}/decoder-epoch-99-avg-1.onnx',
                                                       joiner=f'{AM}/joiner-epoch-99-avg-1.int8.onnx', tokens=f'{AM}/tokens.txt', num_threads=4)
    bnd = [0.0] + mids + [dur_all]
    A, AT = [], []  # 인식된 글자와 각 글자의 시각
    for a0, b0 in zip(bnd[:-1], bnd[1:]):
        st = rec.create_stream(); st.accept_waveform(SR, vall[int(a0 * SR):int(b0 * SR)]); rec.decode_stream(st)
        for tok, ts in zip(st.result.tokens, st.result.timestamps):
            for ch in re.sub(r'[^가-힣0-9a-zA-Z]', '', tok.replace('▁', '')):
                A.append(ch); AT.append(a0 + ts)
    norm = lambda s_: re.sub(r'[^가-힣0-9a-zA-Z]', '', s_)
    T = ''; starts = []
    for x in sc: starts.append(len(T)); T += norm(x['text'])
    mp = {}
    for blk in difflib.SequenceMatcher(None, T, ''.join(A), autojunk=False).get_matching_blocks():
        for q in range(blk.size): mp[blk.a + q] = blk.b + q
    cuts = [0.0]
    for st0 in starts[1:]:
        k = next((mp[q] for q in range(st0, len(T)) if q in mp), None)
        t0 = AT[k] - 0.12 if k is not None else cuts[-1] + 1
        near = [m for m in mids if abs(m - t0) < 0.35]  # 근처에 쉼이 있으면 쉼 위치로 스냅
        cuts.append(max(cuts[-1] + 0.5, min(near, key=lambda m: abs(m - t0)) if near else t0))
    cuts.append(dur_all)
    for i, x in enumerate(sc):
        x['start'], x['end'] = cuts[i], cuts[i + 1]
    print('cuts', [round(c, 2) for c in cuts], 'silences', [round(m, 2) for m in mids])
    parts, t = [vall], dur_all
else:
    asyncio.run(tts())
    parts, t = [], 0.0
    for i, s in enumerate(sc):
        run('ffmpeg', '-loglevel', 'error', '-y', '-i', f'{TMP}/v{i}.mp3', '-ac', '1', '-ar', str(SR), '-f', 's16le', f'{TMP}/v{i}.raw')
        x = np.fromfile(f'{TMP}/v{i}.raw', np.int16).astype(np.float32) / 32768
        s['start'] = t; t += len(x) / SR; s['end'] = t; t += GAP
        parts += [x, np.zeros(int(SR * GAP), np.float32)]
voice = np.concatenate(parts)
TOTAL = t + 0.8
N = int(TOTAL * FPS)
print('voice', round(TOTAL, 1), 's')

# ---------------- 2. background clips (9:16 crop) ----------------
bg_frames = []  # per scene raw file + frame count
for i, s in enumerate(sc):
    nxt = sc[i + 1]['start'] if i + 1 < len(sc) else TOTAL
    dur = nxt - s['start']
    src = next((os.path.join(CLIPS, s['clip'] + e) for e in ('', '.mp4', '.webm') if os.path.isfile(os.path.join(CLIPS, s['clip'] + e))), None)
    if src is None: raise SystemExit(f"clip not found: {s['clip']}")
    x0 = f"max(0\\,min(iw-ih*9/16\\,iw*{s['cx']}-ih*9/32))"
    vf = f"crop=ih*9/16:ih:{x0}:0,scale={W}:{H}:flags=lanczos,fps={FPS},eq=contrast=1.06:saturation=1.15"
    if s.get('tint') == 'blue':
        vf += ",colorchannelmixer=rr=0.55:gg=0.8:bb=1.25:bg=0.15"
    run('ffmpeg', '-loglevel', 'error', '-y', '-stream_loop', '-1', '-ss', str(s['ss']), '-i', src, '-t', f'{dur:.3f}',
        '-vf', vf, '-an', '-pix_fmt', 'rgb24', '-f', 'rawvideo', f'{TMP}/bg{i}.raw')
    s['bg_n'] = os.path.getsize(f'{TMP}/bg{i}.raw') // (W * H * 3)

# ---------------- 3. graphics ----------------
f_cap = ImageFont.truetype(f'{FONT}/Pretendard-Black.ttf', 100)
f_title = ImageFont.truetype(f'{FONT}/Pretendard-ExtraBold.ttf', 64)
f_tag = ImageFont.truetype(f'{FONT}/Pretendard-Bold.ttf', 38)
f_emoji = ImageFont.truetype(EMOJI, 109)
def emoji_img(e, size):
    im = Image.new('RGBA', (160, 140), (0, 0, 0, 0)); ImageDraw.Draw(im).text((0, 0), e, font=f_emoji, embedded_color=True)
    im = im.crop(im.getbbox()); r = size / im.height
    return im.resize((int(im.width * r), size), Image.LANCZOS)
MASCOT = emoji_img(S.get('mascot', '🐙'), 120)

# static overlay: top/bottom shade + header
shade = np.zeros((H, W, 4), np.uint8)
yy = np.arange(H)[:, None]
a = np.clip((yy - H * 0.52) / (H * 0.3), 0, 1) * 200 + np.clip((H * 0.16 - yy) / (H * 0.16), 0, 1) * 120
shade[..., 3] = a.astype(np.uint8)
STATIC = Image.fromarray(shade, 'RGBA')
d = ImageDraw.Draw(STATIC)
d.rounded_rectangle([70, 150, W - 70, 318], 34, fill=(0, 0, 0, 215))
# 채널 로고(원형 + 금색 테두리)를 헤더 왼쪽에 고정
LOGO_PATH = os.path.join(HERE, '..', 'branding', 'profile_final.png')
tx0 = 70
if os.path.exists(LOGO_PATH):
    LS = 136
    lg = Image.open(LOGO_PATH).convert('RGBA').resize((LS, LS), Image.LANCZOS)
    mk = Image.new('L', (LS * 4, LS * 4), 0); ImageDraw.Draw(mk).ellipse([0, 0, LS * 4, LS * 4], fill=255)
    lg.putalpha(mk.resize((LS, LS), Image.LANCZOS))
    ring = Image.new('RGBA', (LS + 12, LS + 12), (0, 0, 0, 0)); ImageDraw.Draw(ring).ellipse([0, 0, LS + 11, LS + 11], fill=(255, 194, 26, 255))
    STATIC.alpha_composite(ring, (88, 234 - (LS + 12) // 2)); STATIC.alpha_composite(lg, (94, 234 - LS // 2))
    tx0 = 88 + LS + 12
cx_txt = (tx0 + W - 70) / 2; avail = (W - 70) - tx0 - 40
fs = 64
while fs > 40 and d.textlength(S['title'], font=ImageFont.truetype(f'{FONT}/Pretendard-ExtraBold.ttf', fs)) > avail: fs -= 2
f_title2 = ImageFont.truetype(f'{FONT}/Pretendard-ExtraBold.ttf', fs)
d.text((cx_txt - d.textlength(S['series'], font=f_tag) / 2, 170), S['series'], font=f_tag, fill=(255, 224, 61))
d.text((cx_txt - d.textlength(S['title'], font=f_title2) / 2, 228 + (64 - fs) // 2), S['title'], font=f_title2, fill='white')

def ease_back(t):
    t = min(max(t, 0), 1); c = 1.7
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2

CAP_CACHE = {}
def caption_layer(s):
    key = s['caption']
    if key in CAP_CACHE: return CAP_CACHE[key]
    lines = s['caption'].split('\n'); lh = 124
    im = Image.new('RGBA', (W, lh * len(lines) + 40), (0, 0, 0, 0)); dd = ImageDraw.Draw(im)
    for i, line in enumerate(lines):
        hl = s.get('hl')
        segs = [(p, c) for p, c in ((line.split(hl, 1)[0], 0), (hl, 1), (line.split(hl, 1)[1], 0))] if hl and hl in line else [(line, 0)]
        x = (W - sum(dd.textlength(p, font=f_cap) for p, _ in segs)) / 2
        for p, c in segs:
            dd.text((x, 10 + i * lh), p, font=f_cap, fill=(255, 224, 61) if c else 'white', stroke_width=11, stroke_fill=(8, 10, 22))
            x += dd.textlength(p, font=f_cap)
    CAP_CACHE[key] = im
    return im

CARD_CACHE = {}
f_cname = ImageFont.truetype(f'{FONT}/Pretendard-Black.ttf', 96)
f_csub = ImageFont.truetype(f'{FONT}/Pretendard-Bold.ttf', 36)
f_cstat = ImageFont.truetype(f'{FONT}/Pretendard-ExtraBold.ttf', 44)
f_crank = ImageFont.truetype(f'{FONT}/Pretendard-Black.ttf', 150)
f_csmall = ImageFont.truetype(f'{FONT}/Pretendard-Bold.ttf', 28)
CX0, CY0, CX1, CY1 = 90, 400, W - 90, 1560  # 도감 카드 영역

def card_base(c):
    """도감 카드의 고정 부분(패널, 이름, 스킬, 능력치 라벨)."""
    key = c['name']
    if key in CARD_CACHE: return CARD_CACHE[key]
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([CX0, CY0, CX1, CY1], 44, fill=(11, 18, 40, 236), outline=(255, 194, 26), width=8)
    d.text((CX0 + 50, CY0 + 40), S.get('dex_no', ''), font=f_csub, fill=(255, 224, 61))
    d.text((CX0 + 50, CY0 + 100), c['name'], font=f_cname, fill='white')
    d.text((CX0 + 54, CY0 + 220), c.get('sub', ''), font=f_csub, fill=(159, 198, 255))
    y = CY0 + 330
    for lab, _ in c['stats']:
        d.text((CX0 + 50, y), lab, font=f_cstat, fill='white')
        d.rounded_rectangle([CX0 + 250, y + 10, CX1 - 150, y + 46], 18, fill=(255, 255, 255, 40)); y += 100
    sk = '고유 스킬  ' + c.get('skill', '')
    d.rounded_rectangle([CX0 + 40, CY1 - 250, CX1 - 40, CY1 - 110], 24, fill=(0, 0, 0, 150), outline=(255, 194, 26), width=3)
    d.text((CX0 + 70, CY1 - 212), sk[:30], font=f_cstat, fill=(255, 224, 61))
    d.text(((W - d.textlength('※ 능력치는 재미로 보는 점수입니다', font=f_csmall)) / 2, CY1 - 80), '※ 능력치는 재미로 보는 점수입니다', font=f_csmall, fill=(200, 210, 230))
    CARD_CACHE[key] = im
    return im

def draw_card(im, c, ls):
    k = ease_back(ls / 0.35)  # 카드가 아래에서 올라옴
    base = card_base(c)
    off = int((1 - k) * 500)
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0)); layer.alpha_composite(base, (0, off))
    d = ImageDraw.Draw(layer); y = CY0 + 330 + off
    for j, (lab, val) in enumerate(c['stats']):
        pr = min(max((ls - 0.4 - j * 0.12) / 0.7, 0), 1); pr = 1 - (1 - pr) ** 3
        x1 = CX0 + 250 + (CX1 - 150 - CX0 - 250) * val / 100 * pr
        if pr > 0: d.rounded_rectangle([CX0 + 250, y + 10, int(max(x1, CX0 + 290)), y + 46], 18, fill=(255, 194, 26))
        d.text((CX1 - 125, y), str(int(round(val * pr))), font=f_cstat, fill=(255, 224, 61)); y += 100
    im.alpha_composite(layer)
    st = (ls - c.get('stamp_at', 1.3)) / 0.25  # 등급 도장
    if st > 0:
        sc = 2.2 - 1.2 * min(st, 1); r = int(120 * sc)
        stamp = Image.new('RGBA', (r * 2 + 20, r * 2 + 20), (0, 0, 0, 0)); sd = ImageDraw.Draw(stamp)
        sd.ellipse([10, 10, r * 2 + 10, r * 2 + 10], fill=(255, 194, 26), outline=(11, 18, 40), width=max(4, int(12 * sc)))
        fr = ImageFont.truetype(f'{FONT}/Pretendard-Black.ttf', int(150 * sc))
        tw = sd.textlength(c['rank'], font=fr); sd.text((r + 10 - tw / 2, r + 10 - int(108 * sc)), c['rank'], font=fr, fill=(11, 18, 40))
        stamp = stamp.rotate(-10, resample=Image.BICUBIC, expand=True)
        a = min(st * 2, 1); stamp.putalpha(stamp.getchannel('A').point(lambda v: int(v * a)))
        im.alpha_composite(stamp, (CX1 - 140 - stamp.width // 2, CY0 + 150 - stamp.height // 2 + off))
    if os.path.exists(LOGO_PATH):  # 도감 박사(마스코트)가 카드 아래에서 등장
        mp = ease_back((ls - 0.6) / 0.4)
        if mp > 0:
            ms = 230; m = Image.open(LOGO_PATH).convert('RGBA').resize((ms, ms), Image.LANCZOS)
            mk = Image.new('L', (ms, ms), 0); ImageDraw.Draw(mk).ellipse([0, 0, ms, ms], fill=255); m.putalpha(mk)
            im.alpha_composite(m, (CX0 - 30, CY1 - 120 + int((1 - mp) * 300)))
    return im

def compose(i, bg, s):
    t = i / FPS
    ls = t - s['start']; dur = s['bg_n'] / FPS
    z0, z1 = s.get('zoom', [1, 1.1]); z = z0 + (z1 - z0) * min(max(ls / max(dur, .1), 0), 1)
    if abs(z - 1) > 1e-3:
        cw, ch = W / z, H / z
        bg = bg.resize((W, H), Image.BILINEAR, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))
    im = bg.convert('RGBA')
    if ls < 0.12:  # flash on cut
        im = Image.blend(im, Image.new('RGBA', (W, H), (255, 255, 255, 255)), 0.35 * (1 - ls / 0.12))
    im.alpha_composite(STATIC)
    if s.get('card'):
        im = Image.alpha_composite(im, Image.new('RGBA', (W, H), (0, 0, 0, 110)))
        im = draw_card(im, S['card'], ls)
        return im.convert('RGB')
    cap = caption_layer(s)
    p = ease_back(ls / 0.3)
    sc_ = 0.6 + 0.4 * p
    cr = cap.resize((max(1, int(cap.width * sc_)), max(1, int(cap.height * sc_))), Image.BILINEAR)
    im.alpha_composite(cr, (int((W - cr.width) / 2), int(1330 - cr.height / 2)))
    d = ImageDraw.Draw(im)
    prog = min(t / TOTAL, 1)
    d.rounded_rectangle([70, 1700, W - 70, 1720], 10, fill=(255, 255, 255, 90))
    d.rounded_rectangle([70, 1700, int(70 + (W - 140) * prog) + 20, 1720], 10, fill=(255, 224, 61))
    im.alpha_composite(MASCOT, (int(40 + (W - 180) * prog), 1585 + int(7 * math.sin(t * 4))))
    return im.convert('RGB')

# ---------------- 4. audio mix ----------------
L = int(TOTAL * SR); mix = np.zeros(L, np.float32); mix[:len(voice)] += voice
tt = np.arange(L) / SR
chords = [[220, 261.6, 329.6], [174.6, 220, 261.6], [261.6, 329.6, 392], [196, 246.9, 293.7]]
bgm = np.zeros(L, np.float32)
for k in range(int(TOTAL / 4) + 1):
    a0, b0 = int(k * 4 * SR), min(L, int((k + 1) * 4 * SR))
    if a0 >= L: break
    seg = tt[a0:b0] - k * 4
    env = np.minimum(1, seg / .8) * np.minimum(1, (4 - seg) / .8)
    for f in chords[k % 4]:
        bgm[a0:b0] += env * (np.sin(2 * np.pi * f * tt[a0:b0]) + .5 * np.sin(2 * np.pi * f * 1.003 * tt[a0:b0])) / 6
    for j in range(8):
        s0, n = a0 + int(j * .5 * SR), int(.4 * SR)
        if s0 + n < L:
            bgm[s0:s0 + n] += .12 * np.sin(2 * np.pi * chords[k % 4][j % 3] * 2 * np.arange(n) / SR) * np.exp(-np.arange(n) / SR * 7)
mix += bgm * 0.13
for s in sc:
    s0, n = int(s['start'] * SR), int(.25 * SR)
    if s0 + n < L:
        k = np.arange(n) / SR
        mix[s0:s0 + n] += .10 * np.random.default_rng(1).standard_normal(n) * np.exp(-k * 18) * np.sin(np.pi * np.minimum(k / .25, 1))
for s in sc:  # 도감 카드 등급 도장 '쾅'
    if s.get('card'):
        s0 = int((s['start'] + S['card'].get('stamp_at', 1.3)) * SR); n = int(.5 * SR)
        if s0 + n < L:
            k = np.arange(n) / SR
            mix[s0:s0 + n] += .5 * np.sin(2 * np.pi * (90 - 40 * k) * k) * np.exp(-k * 9) + .12 * np.random.default_rng(2).standard_normal(n) * np.exp(-k * 30)
f = int(SR); mix[-f:] *= np.linspace(1, 0, f)
mix = np.clip(mix / max(1, np.abs(mix).max() / .95), -1, 1)
with wave.open(f'{TMP}/mix.wav', 'wb') as o:
    o.setnchannels(1); o.setsampwidth(2); o.setframerate(SR); o.writeframes((mix * 32767).astype(np.int16).tobytes())

# ---------------- 5. encode ----------------
out = os.path.join(OUT, f"{S['id']}.mp4")
enc = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                        '-i', f'{TMP}/mix.wav', '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-b:a', '160k', '-ar', '44100', '-shortest', '-movflags', '+faststart', out], stdin=subprocess.PIPE)
fi = 0
for si, s in enumerate(sc):
    nxt = sc[si + 1]['start'] if si + 1 < len(sc) else TOTAL
    with open(f'{TMP}/bg{si}.raw', 'rb') as fh:
        last = None
        while fi < min(N, int(round(nxt * FPS))):
            buf = fh.read(W * H * 3)
            if len(buf) == W * H * 3: last = Image.frombytes('RGB', (W, H), buf)
            enc.stdin.write(compose(fi, last, s).tobytes()); fi += 1
enc.stdin.close(); enc.wait()

# ---------------- 6. upload metadata ----------------
cred = {c['key']: c for c in json.load(open(os.path.join(CLIPS, 'credits.json')))}
used = sorted({s['clip'] for s in sc})
lines = [S['title'] + ' #shorts', '', *[s['text'] for s in sc], '', '#문어 #동물 #신기한사실 #동물상식 #shorts', '', '영상 출처 (Wikimedia Commons):']
for u in used:
    c = cred[u]; lines.append(f"- \"{c['file']}\" by {c['artist']}, {c['license']} - {c['page']}")
lines.append('음성: AI 내레이션 / 배경음악: 자체 제작')
open(os.path.join(OUT, f"{S['id']}_description.txt"), 'w').write('\n'.join(lines) + '\n')
json.dump(sc, open(os.path.join(OUT, f"{S['id']}_timing.json"), 'w'), ensure_ascii=False, indent=1)
print('done', out, round(TOTAL, 1), 's')
