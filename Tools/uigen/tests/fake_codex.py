"""가짜 codex CLI — gen/codex.py 시험용. argv · cwd · 환경 일부를 FAKE_CODEX_LOG(JSON 줄)에 남기고 FAKE_CODEX_MODE 대로 답한다.

이벤트 모양은 [P0 결과](설계 §7 — thread.started.thread_id · turn.completed.usage · item.* agent_message/command_execution)를 따른다.
결과 이미지는 $CODEX_HOME/generated_images/<thread_id>/exec-<n>.png 에 쓴다(실제 codex 와 같은 자리).
모드: ok · opaque(투명 픽셀 없는 그림) · other_dir(다른 폴더 이름 — generated_images 차이로 찾기) · cwd(cwd 에만) · no_image · quota(식별자 + 종료 1) ·
fail(이미지 없이 turn.failed) · sleep
`--version` · `login status` 는 FAKE_CODEX_VERSION · FAKE_CODEX_LOGIN 으로 답한다.
"""
import json
import os
import pathlib
import sys
import time
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import png  # noqa: E402

argv = sys.argv[1:]
if argv[:1] == ["--version"]:
    print(f"codex-cli {os.environ.get('FAKE_CODEX_VERSION', '0.166.0')}")
    sys.exit(0)
if argv[:2] == ["login", "status"]:
    text = os.environ.get("FAKE_CODEX_LOGIN", "Logged in using ChatGPT")
    print(text, file=sys.stderr if os.environ.get("FAKE_CODEX_LOGIN_STDERR") else sys.stdout)
    sys.exit(0 if text.startswith("Logged in") else 1)

mode = os.environ.get("FAKE_CODEX_MODE", "ok")
log = os.environ.get("FAKE_CODEX_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "has_openai_key": "OPENAI_API_KEY" in os.environ,
                            "has_codex_key": "CODEX_API_KEY" in os.environ, "stdin_empty": (sys.stdin.read() == "") if sys.stdin else None},
                           ensure_ascii=False) + "\n")
home = pathlib.Path(os.environ["CODEX_HOME"])
tid = str(uuid.uuid4())


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def image(path: pathlib.Path, opaque: bool = False):
    w, h = 8, 4
    rgba = bytearray()
    for y in range(h):
        for x in range(w):
            rgba += bytes((232, 181, 74, 0 if x in (0, w - 1) and not opaque else 255))
    png.write_rgba(path, w, h, rgba)


emit({"type": "thread.started", "thread_id": tid})
emit({"type": "turn.started"})
if mode == "sleep":
    time.sleep(10)
if mode == "quota":
    emit({"type": "error", "message": "You've hit your usage limit (usage_limit_reached). Try again at 3:05 PM."})
    emit({"type": "turn.failed", "error": {"message": "usage_limit_reached"}})
    sys.exit(1)
if mode == "fail":
    emit({"type": "turn.failed", "error": {"message": "stream disconnected"}})
    sys.exit(1)
if mode == "ok":
    image(home / "generated_images" / tid / "exec-1.png")
elif mode == "opaque":                                       # 1b 후속 I — 투명을 요청했는데 투명 픽셀 없이 온 그림
    image(home / "generated_images" / tid / "exec-1.png", opaque=True)
elif mode == "other_dir":
    image(home / "generated_images" / "elsewhere" / "exec-2.png")
elif mode == "cwd":
    image(pathlib.Path(os.getcwd()) / "copied.png")
emit({"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "Generated the image."}})
emit({"type": "turn.completed", "usage": {"input_tokens": 1200, "cached_input_tokens": 800, "output_tokens": 40}})
if "-o" in argv:
    pathlib.Path(argv[argv.index("-o") + 1]).write_text("Generated the image.", encoding="utf-8")
