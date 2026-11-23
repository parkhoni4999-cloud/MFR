# 유튜브 쇼츠 자동 제작 파이프라인 (동물 신기한 사실)

## 구조
- pipeline/build.py : 대본 JSON -> 음성 -> 배경영상 -> 자막/그래픽 -> mp4 + 업로드 설명문
- pipeline/script_*.json : 편별 대본/장면 설계
- pipeline/setup.sh : 새 서버에서 도구 설치
- assets/clips : 배경 영상 + credits.json(출처)
- assets/voice : ElevenLabs 내레이션

## 실행
    bash pipeline/setup.sh
    cd pipeline && python3 build.py script_short01_el.json ../assets/clips ../output

## 현재 결정사항
- 형식: 쇼츠 / 주제: 동물 신기한 사실
- 음성: ElevenLabs (Taehyung, voice_id m3gJBS8OofDJfycyA2Ip, model eleven_v4, 감정 태그 사용) - Claude 커넥터로 생성
- 영상: Pixabay (키: 환경변수 PIXABAY_API_KEY) / 보조: Wikimedia Commons(CC0, CC BY만)
- 네트워크 허용: speech.platform.bing.com, commons/upload.wikimedia.org, pixabay.com, cdn.pixabay.com, elevenlabsusercontent.com
- 채널: 사기캐 동물도감, 프로필 branding/profile_final.png, 상세 플랜은 PLAN.md
- 남은 일: Pixabay 연동 -> 유튜브 자동 업로드(OAuth) -> 매일 예약 실행

## 유튜브 업로드 (vidIQ 커넥터)
- 채널: 사기캐동물도감 (@사기캐동물도감1), channelId UC5QAseBqZ16d0qTXDHYLNHA - vidIQ에 연결 완료
- 순서: vidiq_video_upload(localFile) -> 출력된 sh 명령 실행 -> vidiq_social_post_draft_create(YOUTUBE, categoryId 15) -> 사용자 승인 -> vidiq_social_post_publish
- 업로드 비용 0 크레딧. 공개 전 반드시 사용자 승인. 1~2주차는 private.
- 시험 업로드 완료: https://www.youtube.com/watch?v=4CSRfsKc6Ac (private, 문어 로고 버전)

## 저장 위치 (GitHub)
- 저장소: parkhoni4999-cloud/MFR 의 `youtube-shorts` 분기 (MFR 기본 분기는 건드리지 않음)
- 복구: `git clone --branch youtube-shorts --single-branch https://github.com/parkhoni4999-cloud/mfr /home/user/youtube-shorts && bash /home/user/youtube-shorts/pipeline/setup.sh`
- 매일 기록 후: `git push origin main:youtube-shorts`
- 주의: MFR은 공개 저장소이므로 API 키, 비밀번호, 개인 정보는 절대 커밋하지 않는다.
