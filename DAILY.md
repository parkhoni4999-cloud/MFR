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
- 가로 사진/영상에서 동물이 잘리면 장면에 "fit": true (전체 표시 + 흐린 배경). 실사 영상이 없으면 Wikimedia/Pixabay 사진을 ffmpeg로 12초 mp4로 만들어 사용. 다른 종(예: 태즈메이니아데빌, 유럽오소리)이 섞이지 않았는지 꼭 확인.
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
