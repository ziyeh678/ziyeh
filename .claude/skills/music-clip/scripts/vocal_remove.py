#!/usr/bin/env python3
"""去人声（做伴奏）：只在用户明确要求时使用。用 UVR-MDX-NET-Inst_HQ_3 模型，CPU 运行。

用法（必须用去人声专用 Python）：
  ~/.cache/ziyeh-music/vocal/bin/python vocal_remove.py <原曲> --out <目录> --request "用户原话"
输出：<目录>/<原曲名>-伴奏.mp3（320k），并写 <同名>.json 记录（原曲/成品 sha256、时长、模型）。
不保证完美去除人声；原曲不改动；已存在的成品不覆盖。

安装（新会话第一次用时）：
  python3 -m venv ~/.cache/ziyeh-music/vocal
  ~/.cache/ziyeh-music/vocal/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
  ~/.cache/ziyeh-music/vocal/bin/pip install "audio-separator[cpu]"
"""
import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MODEL = "UVR-MDX-NET-Inst_HQ_3.onnx"
CACHE = Path(os.environ.get("VOCAL_CACHE", str(Path.home() / ".cache" / "ziyeh-music" / "vocal-models")))


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def duration(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]).strip())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--request", required=True, help="用户要求去人声的原话（不能编）")
    a = ap.parse_args()
    if not a.request.strip():
        sys.exit(json.dumps({"error": "需要用户明确要求才去人声"}, ensure_ascii=False))
    src = a.source.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    target = a.out / f"{src.stem}-伴奏.mp3"
    receipt = target.with_suffix(".json")
    if target.exists():
        if receipt.exists():
            r = json.loads(receipt.read_text(encoding="utf-8"))
            if r.get("source_sha256") == sha(src) and r.get("output_sha256") == sha(target):
                print(json.dumps({"status": "reused", **r}, ensure_ascii=False, indent=2))
                return
        sys.exit(json.dumps({"error": f"已存在，不覆盖：{target.name}"}, ensure_ascii=False))
    src_hash = sha(src)
    import torch
    torch.set_num_threads(max(1, os.cpu_count() or 4))
    from audio_separator.separator import Separator
    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        sep = Separator(log_level=logging.WARNING, model_file_dir=str(CACHE), output_dir=tmp, output_format="WAV",
                        output_single_stem="Instrumental", normalization_threshold=0.95)
        sep.load_model(model_filename=MODEL)
        sep.separate(str(src), {"Instrumental": "instrumental"})
        wavs = list(Path(tmp).glob("*.wav"))
        if len(wavs) != 1:
            sys.exit(json.dumps({"error": f"分离结果数量不对：{[w.name for w in wavs]}"}, ensure_ascii=False))
        tmp_mp3 = Path(tmp) / "out.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-n", "-i", str(wavs[0]), "-map", "0:a:0", "-c:a", "libmp3lame", "-b:a", "320k", str(tmp_mp3)], check=True)
        d0, d1 = duration(src), duration(tmp_mp3)
        if abs(d0 - d1) > 0.2:
            sys.exit(json.dumps({"error": f"伴奏时长 {d1:.2f}s 与原曲 {d0:.2f}s 不符"}, ensure_ascii=False))
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(tmp_mp3), "-f", "null", "-"], check=True)
        os.replace(tmp_mp3, target)
    r = {"status": "ok", "output": str(target), "source": str(src), "source_sha256": src_hash, "output_sha256": sha(target),
         "model": MODEL, "request": a.request, "duration": round(duration(target), 2), "decode": "通过", "note": "AI 去人声不保证完美，请试听"}
    receipt.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
