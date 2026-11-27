# 매일 제작 런북 (예약 작업이 새 세션에서 따라 하는 절차)

채널: 사기캐 동물도감 (YouTube @사기캐동물도감1, channelId UC5QAseBqZ16d0qTXDHYLNHA)
기준 시간대: 한국(KST). 업로드 공개 시각: 매일 14:00 KST (하루 1편). 제작은 오전에 자동 시작.

## 0. 준비
1. `bash pipeline/setup.sh` (모델, 폰트, 패키지 설치)
2. `schedule.json`에서 오늘(KST 날짜) 항목을 찾는다. 없으면 PLAN.md 요일 테마로 새 동물을 골라 schedule.json에 추가한다.
3. `episodes_log.json`에 오늘 번호가 이미 `uploaded`면 아무것도 하지 말고 끝낸다.

## 1. 대본 (Claude)
- 웹 검색으로 사실을 확인한다. 확실한 사실만 쓰고, 출처 URL을 `episodes/NNN_동물/facts.md`에 남긴다.
- 구성 (총 30~40초, 문장 끝은 대화체 "~래요/~거든요"):
  1. 훅 1문장: 가장 충격적인 사실
  2. 스킬① ② ③: 각 1~2문장, 자막은 "스킬① 심장 3개" 형식
  3. 도감 카드 장면: "도감 등록 완료! ○○의 등급은... S!" (card: true)
  (다음 편 예고는 넣지 않는다. 도감 카드 장면으로 끝낸다.)
- `episodes/NNN_동물/script.json` 작성. 형식은 `pipeline/script_short01_el.json` + 아래 필드:
  - `series`: "사기캐 동물도감 · No.NNN", `dex_no`: "도감 No.NNN", `mascot`: 동물 이모지
  - `card`: {name, sub(학명 · 별명), rank(S/A/B), stats: [[라벨, 0~100] x4], skill(짧게), stamp_at: 1.6}
  - `voice_file`: "../../assets/voice/NNN.mp3" (script.json 기준 상대경로)

## 2. 영상 소재 (Pixabay)
- `python3 pipeline/fetch_pixabay.py "<en 검색어>" assets/px/NNN 6 --must <핵심 영단어>`
- 출력된 sheet 이미지를 Read로 직접 보고, 엉뚱한 영상(만화, 놀이기구 등)은 쓰지 않는다.
- 장면마다 `clip`(px_ID), `ss`(시작초), `cx`(가로 중심 0~1)를 정한다. 같은 클립을 2번 넘게 쓰지 않도록 한다.
- 가로 사진/영상에서 동물이 잘리면 장면에 "fit": true (전체 표시 + 흐린 배경). 실사 영상이 없으면 Wikimedia/Pixabay 사진을 ffmpeg로 12초 mp4로 만들어 사용. 다른 종(예: 태즈메이니아데빌, 유럽오소리, 송골매 검색에 섞인 독수리·황조롱이·말똥가리)이 섞이지 않았는지 꼭 확인. 영상이 없으면 Pixabay 사진 검색(image_type=photo)도 활용.
- 부족하거나 PIXABAY_API_KEY 환경변수가 이 세션에 없으면 Wikimedia Commons(CC0, CC BY만; 원본 대신 transcoded 720p/1080p URL 사용)로 대체하고 알림에 적는다.

## 3. 음성 (ElevenLabs 커넥터)
- 먼저 `account_get_usage`로 남은 크레딧 확인. 400 미만이면 ElevenLabs 대신 edge-tts(`voice`: "ko-KR-HyunsuMultilingualNeural", `voice_file` 제거)로 만들고 알림에 적는다.
- `creative_generate_speech`: voice_id `m3gJBS8OofDJfycyA2Ip`(Taehyung), model `eleven_v4`, generations_count 1, 감정 태그([excited] [curious] [amazed] [whispering] [cheerful]) 사용. 프롬프트 문장은 script.json의 text와 같게(태그만 추가).
- 완료되면 content_url을 curl로 `assets/voice/NNN.mp3`에 저장 (재시도로 다시 생성하지 말 것).

## 4. 편집
- `cd pipeline && python3 build.py ../episodes/NNN_동물/script.json ../assets/px/NNN ../output`
- 확인: 장면 경계가 맞는지 `python3 asr.py`로 타이밍 확인, 프레임 4장 이상 뽑아 Read로 직접 본다 (자막 잘림, 엉뚱한 화면, 카드).

## 5. 업로드 (vidIQ 커넥터) - 공개는 반드시 사용자 승인 후
1. `vidiq_video_upload` localFile -> 출력된 sh 명령 실행 -> uploadId로 ready 확인
2. `vidiq_social_post_draft_create`: YOUTUBE, platformAccountId UC5QAseBqZ16d0qTXDHYLNHA, categoryId 15,
   title "○○ [핵심 사실 한 줄] 🐙 #shorts" (100자 이내), 설명(요약+사실+해시태그+영상 출처+"음성: AI 내레이션"),
   tags, privacyStatus "public", publishAt 당일 14:00 KST (+09:00). 승인이 14:00 이후에 오면 publishAt 없이 바로 공개(public)로 초안을 고친 뒤 게시
3. PushNotification으로 사용자에게 알림: "도감 No.NNN ○○ 준비 완료, 확인 후 '올려'라고 답해주세요" + SendUserFile로 영상 전달 + 초안 요약(제목/공개시각).
4. 사용자가 이 세션에서 승인하면 `vidiq_social_post_publish`. 승인 전에는 절대 게시하지 않는다.
6. vidIQ 무료 플랜은 유튜브 업로드가 하루 3개까지(미국 태평양시 자정 = 한국 17:00 초기화). 한도 초과 오류가 나면 17:05 KST 이후로 send_later 재시도 예약.
5. 주의: 초안을 수정(draft_update)하면 예약 시각(scheduledFor)이 사라질 수 있다. 수정 후 결과의 scheduledFor를 꼭 확인하고, 비어 있으면 publishAt을 다시 넣는다.

## 6. 기록
- `episodes_log.json`에 {no, animal, date, status(drafted/uploaded), youtube_url, voice: elevenlabs|edge} 추가
- mp4/음성/영상소재를 제외한 변경(script.json, facts.md, schedule.json, log)을 커밋하고 push.

## 성과 반영 규칙 (No.001 분석, 2026-11-23: 계속 시청함 41%, 평균 조회율 56%)
- 첫 장면(훅): 2초 안에 끝나는 짧고 충격적인 질문/사실 한 문장. 예: "심장이 3개?!" 자막은 0프레임부터 크게 표시됨(build.py가 첫 장면을 자동 처리).
- 첫 장면에는 가장 강렬한 실사 화면(동물 얼굴 클로즈업, 움직임)을 쓴다. 우주/풍경 같은 간접 화면은 피한다.
- 전체 길이 30~35초 목표(스킬 3개 + 반전/보너스 1개 + 카드). 소개 장면은 짧게.
- 도감 카드: card에 "cta": "몇 등급일까요? 댓글로!", "cta_hl": "몇 등급" 넣고, 카드 내레이션 끝에 "여러분 생각엔 몇 등급일까요? 댓글로 알려주세요!"를 붙인다.
- 영상 공개 다음 날 사용자가 스튜디오 지표를 주면 episodes_log.json에 stayed/avg_view_pct 기록.

## 대본 자막 (2026-11-24 추가)
- build.py가 대본 전체를 한 줄 자막(최대 약 15자, 문장부호·띄어쓰기 기준)으로 자동 생성해 메인 자막 아래에 표시한다. ElevenLabs 음성은 글자 단위 시각으로 맞춘다.
- 내레이션은 숫자를 한글로 읽게 쓰므로(예: "영 점 오 밀리미터") 자막에 숫자로 보이게 하려면 장면에 "sub": "크기는 고작 0.5mm" 처럼 표시용 문장을 넣는다(이때는 장면 길이에 비례해 시간 배분).

## 실사 영상 우선 규칙 (2026-11-24, 편성은 그대로 유지)
- 소재 수집은 `python3 pipeline/find_footage.py assets/px/NNN --en "<영어명>" --sci "<학명>" --must <종 키워드들> --extra "<행동 검색어들>" --avoid "<헷갈리는 종>"` 를 먼저 쓴다.
  - Pixabay 영상(여러 검색어) + Wikimedia 영상(CC0/퍼블릭도메인/CC BY만)을 모으고, 실사 영상이 3개 미만일 때만 사진을 보충한다.
  - 각 영상의 움직임 점수로 가장 역동적인 4초 구간(best_ss)을 footage.json에 적어준다. 장면의 ss로 그대로 쓴다.
  - sheet_all.png 를 반드시 직접 보고 다른 종, 조각상·그림, 사체 등 부적절한 장면을 뺀다.
- 장면 배치: 첫 장면(훅)과 스킬 장면에는 실사 영상을 우선 배치하고, 사진은 반전/카드 장면 등에 쓴다. 같은 영상은 구간(ss)을 바꿔 여러 장면에 재사용해도 된다.
- Wikimedia는 이 서버에서 자주 요청 제한(429)이 걸린다. 건너뛰어도 제작은 계속한다.

- AI 생성으로 보이는 사진(태그에 표시가 없어도 조명·구도가 비현실적이거나 야생에서 찍기 불가능한 장면)은 가급적 쓰지 않고, 꼭 써야 하면 장면에 "label": "연출 이미지"를 넣고 설명란에 고지한다.

- Pixabay에 실사가 없으면 Wikimedia 사진도 검색한다(filetype:bitmap, CC0/PD/CC BY만). iNaturalist 관찰 사진(CC BY 4.0)이 많다. 다운로드는 upload.wikimedia.org 썸네일 주소로, 8초 이상 간격을 두고, JPEG 시작 바이트(FF D8)를 파이썬으로 확인한다.

## "아무도 몰랐던 사실" 규칙 (2026-11-27, 사용자 요청: 사람들이 정말 몰랐던 내용이어야 흥미가 생김)
- facts.md에 후보 사실을 6개 이상 모으고, 각 사실에 **지명도(상/중/하)**를 적는다.
  - 상: 한국어 검색 첫 화면·흔한 상식 퀴즈·기존 쇼츠에 자주 나오는 것 (예: 문어 심장 3개, 벌꿀오소리는 겁이 없다)
  - 중: 다큐·영문 기사에는 나오지만 한국에선 잘 모르는 것
  - 하: 논문·대학 보도자료·최근 10년 연구에서 나온 것
- 대본에 쓰는 스킬 3개 + 반전 중 **최소 3개는 '하' 또는 '중'**. '상'은 최대 1개만, 그것도 "○○는 다들 아시죠? 진짜는 지금부터예요" 식의 2초짜리 도입으로만 쓴다.
- 훅은 가장 낯선 사실(지명도 '하')로 만든다. 유명한 사실로 훅을 만들지 않는다.
- 출처 우선순위: 논문/대학·연구기관 보도자료 > 과학 매체(내셔널지오그래픽, 사이언스뉴스 등) > 백과사전. 블로그·잡학 사이트만 있는 사실은 쓰지 않는다.
- 최근 연구(10년 이내)에서 나온 사실을 편마다 1개 이상 넣고, 자막에 "2018년 연구"처럼 연도를 보여 신뢰감을 준다.
- 검증이 약한(한 출처뿐, 수치가 출처마다 크게 다름) 사실은 "~로 알려져 있어요"로 완화하거나 뺀다.

## 콘셉트 (2026-11-27 변경)
- schedule.json의 theme이 "친숙한 동물의 반전"이면: 누구나 아는 동물의 '처음 듣는' 사실 위주. 훅은 "○○가 ~한다고?" 형식으로 익숙함과 반전을 한 문장에.
- theme이 "진짜 신비한 동물"이면: 첫 장면에 그 동물의 가장 기묘한 모습(실사)을 보여주고 "이게 진짜 동물이라고?"류 훅.
- 길이 목표 25~30초 (스킬 2~3개, 카드 3초+질문). 대본 글자 수 약 220~260자.
- 카드 질문은 "다음엔 어떤 동물이 궁금하세요? 댓글로!"(cta) 고정. 내레이션은 "등급은... ○!"에서 끝낸다.
- 제목은 궁금증형("~의 정체", "~하는 진짜 이유", "~한다고?"), 동물 이름은 설명란 첫 줄에.
