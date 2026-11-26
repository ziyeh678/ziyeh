#!/usr/bin/env bash
# 新会话第一次用音乐功能前运行（已装过会跳过）。
#   bash .claude/skills/music-clip/scripts/setup.sh          # 搜歌/下载依赖（几秒）
#   bash .claude/skills/music-clip/scripts/setup.sh vocal    # 另外装去人声（约 1.4GB，3-5 分钟）
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="$HOME/.cache/ziyeh-music"
mkdir -p "$BASE"
if [ ! -f "$BASE/pylib/.ok" ]; then
  pip install -q --disable-pip-version-check --upgrade --target "$BASE/pylib" -r "$HERE/../requirements.txt" qrcode pillow pycryptodomex requests
  touch "$BASE/pylib/.ok"
fi
echo "music deps ok"
if [ "$1" = "vocal" ] && [ ! -f "$BASE/vocal/.ok" ]; then
  python3 -m venv "$BASE/vocal"
  "$BASE/vocal/bin/pip" install -q --disable-pip-version-check torch torchaudio --index-url https://download.pytorch.org/whl/cpu
  "$BASE/vocal/bin/pip" install -q --disable-pip-version-check "audio-separator[cpu]" audioread librosa
  "$BASE/vocal/bin/python" -c "from audio_separator.separator import Separator"
  touch "$BASE/vocal/.ok"
  echo "vocal ok"
fi
