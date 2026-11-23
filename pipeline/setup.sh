#!/usr/bin/env bash
# 새 서버에서 한 번 실행: 필요한 도구/모델/폰트 설치
set -e
cd "$(dirname "$0")"
pip install -q edge-tts "sherpa-onnx==1.10.46" numpy pillow
mkdir -p models fonts
if [ ! -d models/sherpa-onnx-zipformer-korean-2024-06-24 ]; then
  curl -sL https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-zipformer-korean-2024-06-24.tar.bz2 | tar xj -C models
fi
if [ ! -f fonts/Pretendard-Black.ttf ]; then
  (cd /tmp && npm pack pretendard@1.3.9 -q >/dev/null && tar xzf pretendard-1.3.9.tgz)
  for w in Black ExtraBold Bold; do cp /tmp/package/dist/public/static/alternative/Pretendard-$w.ttf fonts/; done
fi
echo "setup ok"
