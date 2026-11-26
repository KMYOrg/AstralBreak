"""codex 생성기 (설계 §7) — 공식 codex CLI 의 built-in `image_gen` 으로 이미지 1장을 만든다.

규칙(설계 §7 · §9, 1b 브리프):
  - 공식 CLI(`codex exec`)만 · built-in `image_gen` 만 — 프롬프트가 CLI 대체 경로(`scripts/image_gen.py` · API 키)를 금한다.
    환경에서 `OPENAI_API_KEY` 류를 뺀다(유료 API 폴백 차단). `--dangerously-bypass-*` 는 어떤 경로로도 넣지 않는다.
  - **한 번에 하나** — 결과 파일이 `$CODEX_HOME/generated_images/<thread_id>/` 에만 생기고 저장 위치를 고를 수 없어서,
    동시에 돌면 어느 파일이 어느 요청 것인지 모른다. 전역 잠금 `work/.codex.lock`(pid — 죽은 잠금은 넘겨받음).
  - stdin 은 닫는다(DEVNULL) — [P0 결과] stdin 이 열려 있으면 'Reading additional input from stdin...' 에서 기다릴 수 있다.
  - 결과 찾기: `--json` 첫 이벤트 `thread.started.thread_id` 폴더 → 없으면 실행 전후 generated_images 차이 → 없으면 cwd 의 새 PNG.
  - 한도(A3): 출력에서 식별자(`usage_limit_reached` · `quota_exceeded` · `usage_not_included` · `rate_limit_exceeded` · `Try again at`)를
    찾으면 `CodexQuota`(파이프라인은 멈추고 나중에 재개). 식별자가 없어도 연속 실패가 `suspect_quota_after_failures` 번이면 한도로 추정.
    걸리면 이벤트 원문(events.jsonl) · 종료 코드를 그대로 남긴다(채록).
  - run 당 호출 상한(`limits.codex_calls_per_run`) — 실패한 호출도 플랜을 쓰므로 센다(`CallBudget`).
  - npm 설치의 `codex` 는 `.cmd` 래퍼다 — cmd.exe 가 프롬프트의 `&` `%` `^` `|` `<` `>` 를 해석하지 않게 `node codex.js` 로 직접 부른다(`resolve_cli`).
  - `~/.codex/auth.json` · 토큰 파일은 읽지 않는다. 로그인 확인은 `codex login status` 출력으로만 한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import struct
import subprocess
import time

from core import config
from core.proc import pid_alive

QUOTA_MARKERS = ("usage_limit_reached", "quota_exceeded", "usage_not_included", "rate_limit_exceeded", "try again at")
DEFAULT_STRIP_ENV = ("OPENAI_API_KEY", "CODEX_API_KEY", "AZURE_OPENAI_API_KEY")
FORBIDDEN_ARGS = ("--dangerously-bypass-approvals-and-sandbox", "--dangerously-bypass-hook-trust", "--approve-for-me")

WRAPPER = (
    "Use your built-in image_gen tool exactly once to create the image described below.\n"
    "- Built-in image_gen only: do not use the scripts/image_gen.py CLI fallback, any API key, or any other image path.\n"
    "- Do not read SKILL.md or any other files and do not run shell commands — the request below is complete.\n"
    "- Do not copy, move or rename the result; leaving it in the default generated_images folder is correct.\n"
    "- When done, reply with one short line.\n"
    "{refs}"
    "\nImage request:\n{prompt}\n"
)
REFS_NOTE = ("- The attached image(s) are references only ({purpose}). Match what they show for that purpose; "
             "do not copy any text, watermark or background from them.\n")
# 1b 후속 A — 컨셉에서 따오기(source_mode: extract). [실측 A-1] `-i` 첨부는 대화에 보이는 그림이라 built-in image_gen 편집 대상이 된다
# (SKILL.md 'Built-in edit semantics') — 모양 · 장식 · 위치를 지키고(중심 차 ≤ 0.5 px · 크기 비 ≤ 0.5 %) 출력 캔버스 비율을 입력에 맞춘다.
EDIT_WRAPPER = (
    "Use your built-in image_gen tool exactly once to EDIT the attached image (edit mode: the attached image is the edit target, not a style reference).\n"
    "- Built-in image_gen only: do not use the scripts/image_gen.py CLI fallback, any API key, or any other image path.\n"
    "- The attached image is already visible to you. Do not read SKILL.md or any other files and do not run shell commands — the request below is complete.\n"
    "- Do not copy, move or rename the result; leaving it in the default generated_images folder is correct.\n"
    "- When done, reply with one short line.\n"
    "{refs}"
    "\nEdit request:\n{prompt}\n"
)
EDIT_NOTE = "- Preserve invariants aggressively: {purpose}.\n"


class CodexError(Exception):
    def __init__(self, code: str, message: str, **details):
        self.code = code
        self.details = details
        super().__init__(f"{code}: {message}")


class CodexQuota(CodexError):
    """플랜 한도 — 파이프라인은 멈추고(on_quota: pause) 나중에 재개한다."""


def codex_cfg(cfg: dict) -> dict:
    c = cfg.get("codex")
    if not isinstance(c, dict):
        raise CodexError("CODEX_CONFIG", "pipeline.yaml: 'codex' section is missing")
    return c


def resolve_cli(cdx: dict) -> list[str]:
    """설정의 CLI. auto = PATH 의 codex — `.exe` 면 그대로, npm 래퍼(.cmd/.ps1/셸 스크립트)면 node + codex.js."""
    cli = cdx.get("cli", "auto")
    if cli and cli != "auto":
        return [cli] if isinstance(cli, str) else [str(c) for c in cli]
    found = shutil.which("codex")
    if not found:
        raise CodexError("CODEX_NOT_FOUND", "codex is not on PATH (npm i -g @openai/codex@<pinned>)")
    p = pathlib.Path(found)
    if p.suffix.lower() == ".exe":
        return [str(p)]
    js = p.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    if not js.is_file():
        raise CodexError("CODEX_NOT_FOUND", f"{p} is a wrapper but {js} does not exist — set codex.cli in pipeline.yaml")
    node = p.parent / "node.exe"
    node_cmd = str(node) if node.is_file() else shutil.which("node")
    if not node_cmd:
        raise CodexError("CODEX_NOT_FOUND", "node is not on PATH (needed to run the npm codex.js without cmd.exe)")
    return [node_cmd, str(js)]


def default_cli(cdx: dict) -> list[str]:
    """실제 CLI — pytest 는 conftest 가 이 함수를 막는다(가짜 codex 만)."""
    return resolve_cli(cdx)


def codex_home(cdx: dict) -> pathlib.Path:
    if os.environ.get("CODEX_HOME"):
        return pathlib.Path(os.environ["CODEX_HOME"])
    if cdx.get("home"):
        return pathlib.Path(cdx["home"]).expanduser()
    return pathlib.Path.home() / ".codex"


def _env(cdx: dict) -> dict:
    strip = set(cdx.get("strip_env") or DEFAULT_STRIP_ENV) | set(DEFAULT_STRIP_ENV)
    return {k: v for k, v in os.environ.items() if k not in strip}


def _kill_tree(proc: subprocess.Popen) -> None:
    """node 래퍼 아래 codex.exe 까지 끝낸다 — Windows 는 부모를 죽여도 자식이 남는다."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, stdin=subprocess.DEVNULL, check=False)
    else:   # pragma: no cover
        proc.kill()


def _run(cli: list[str], args: list[str], cdx: dict, *, cwd: pathlib.Path | None = None, timeout: float = 60.0) -> tuple[int, str, str]:
    full = [*cli, *args]
    bad = [a for a in full if a in FORBIDDEN_ARGS]
    if bad:
        raise CodexError("CODEX_FORBIDDEN_ARG", f"refusing to run codex with {bad}")
    try:
        proc = subprocess.Popen(full, cwd=str(cwd) if cwd else None, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", env=_env(cdx))
    except OSError as exc:
        raise CodexError("CODEX_LAUNCH", f"{full[0]}: {exc}") from exc
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _kill_tree(proc)
        out, err = proc.communicate()
        raise CodexError("CODEX_TIMEOUT", f"codex {' '.join(args[:1])} did not finish within {timeout:g}s", stdout=out[-2000:], stderr=err[-2000:]) from exc
    return proc.returncode, out, err


def preflight(cfg: dict, *, cli: list[str] | None = None) -> dict:
    """run(또는 컨셉 생성) 시작 검사 — 버전 기록(기대 버전과 다르면 표시만) · ChatGPT 로그인 확인(API 키 로그인 = 유료 경로 → 거부)."""
    cdx = codex_cfg(cfg)
    cli = cli or default_cli(cdx)
    code, out, err = _run(cli, ["--version"], cdx)
    words = (out.strip() or err.strip()).split()
    version = words[-1] if words else ""
    if code != 0 or not version:
        raise CodexError("CODEX_LAUNCH", f"codex --version failed (exit {code}): {err.strip()[:200]}")
    code, out, err = _run(cli, ["login", "status"], cdx)
    text = (out + "\n" + err).strip()
    expected = cdx.get("expected_version")
    info = {"version": version, "expected_version": expected, "version_match": expected is None or str(expected) == version,
            "login": text.splitlines()[0][:80] if text else ""}
    low = text.lower()
    if "api key" in low:
        raise CodexError("CODEX_AUTH_METHOD", "codex is logged in with an API key — refusing the paid path (log in with ChatGPT)", **info)
    if code != 0 or "logged in using chatgpt" not in low:
        raise CodexError("CODEX_NOT_LOGGED_IN", "codex is not logged in with ChatGPT — run `codex login` once", **info)
    return info


class CodexLock:
    """work/.codex.lock — codex 호출은 한 번에 하나(파이프라인 run · 컨셉 생성 도구 사이에서도)."""

    def __init__(self, work_root: pathlib.Path, owner: str):
        self.path = pathlib.Path(work_root) / ".codex.lock"
        self.owner = owner
        self.taken_over: dict | None = None
        self._held = False

    def __enter__(self) -> "CodexLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps({"pid": os.getpid(), "owner": self.owner, "started": time.strftime("%Y-%m-%dT%H:%M:%S")})
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    held = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    held = {}
                if pid_alive(int(held.get("pid", 0) or 0)):
                    raise CodexError("CODEX_LOCKED", f"another codex call holds {self.path}: {held}", holder=held)
                self.taken_over = held
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
            self._held = True
            return self
        raise CodexError("CODEX_LOCKED", f"could not take {self.path}")

    def __exit__(self, *exc) -> None:
        if self._held:
            try:
                held = json.loads(self.path.read_text(encoding="utf-8"))
                if held.get("pid") == os.getpid() and held.get("owner") == self.owner:
                    self.path.unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
            self._held = False


class CallBudget:
    """run 당 codex 호출 상한 · 연속 실패 — 기록은 JSONL(호출마다 한 줄, 실패 포함)."""

    def __init__(self, path: pathlib.Path, limit: int, suspect_after: int = 2):
        self.path = pathlib.Path(path)
        self.limit = int(limit)
        self.suspect_after = int(suspect_after)

    def records(self) -> list[dict]:
        if not self.path.is_file():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def used(self) -> int:
        return len(self.records())

    def consecutive_failures(self) -> int:
        n = 0
        for r in reversed(self.records()):
            if r.get("ok"):
                break
            n += 1
        return n

    def check(self) -> None:
        if self.used() >= self.limit:
            raise CodexError("CODEX_CALL_LIMIT", f"codex call limit reached ({self.used()}/{self.limit} this run)", used=self.used(), limit=self.limit)

    def add(self, rec: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _snapshot(root: pathlib.Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*.png")} if root.is_dir() else set()


def _png_info(path: pathlib.Path) -> dict:
    """크기 · 색 형식(IHDR) · 투명 픽셀 비율(표본) — 큰 그림도 빨리."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise CodexError("CODEX_BAD_IMAGE", f"{path} is not a PNG")
    w, h, depth, ctype = struct.unpack(">IIBB", data[16:26])
    info = {"size": [w, h], "bit_depth": depth, "color_type": ctype, "has_alpha_channel": ctype in (4, 6), "transparent_ratio": None}
    if ctype in (4, 6) and depth == 8:
        try:
            from core import png
            _, _, rgba = png.decode(data)
            step = max(1, (w * h) // 200_000)
            alphas = rgba[3::4][::step]
            info["transparent_ratio"] = round(sum(1 for a in alphas if a == 0) / max(1, len(alphas)), 4)
        except Exception as exc:  # noqa: BLE001 — 기록만(크기는 IHDR 로 이미 있음)
            info["alpha_error"] = str(exc)[:200]
    return info


def _parse_events(stdout: str) -> dict:
    """--json 이벤트(JSONL) 요약 — thread_id · 사용량 · 오류 · 에이전트 메시지 · 셸 명령 수."""
    ev = {"thread_id": None, "usage": None, "errors": [], "agent_messages": [], "commands": 0, "types": {}}
    for line in stdout.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        t = str(obj.get("type"))
        ev["types"][t] = ev["types"].get(t, 0) + 1
        if t == "thread.started" and not ev["thread_id"]:
            ev["thread_id"] = obj.get("thread_id")
        elif t == "turn.completed":
            ev["usage"] = obj.get("usage")
        elif t in ("error", "turn.failed"):
            err = obj.get("error") if isinstance(obj.get("error"), dict) else {}
            ev["errors"].append(str(obj.get("message") or err.get("message") or obj)[:500])
        elif t.startswith("item."):
            item = obj.get("item") or {}
            kind = item.get("type") or item.get("item_type")
            if t == "item.completed" and kind == "agent_message":
                ev["agent_messages"].append(str(item.get("text") or "")[:500])
            elif t == "item.started" and kind == "command_execution":
                ev["commands"] += 1
    return ev


def build_args(prompt: str, gen_dir: pathlib.Path, cdx: dict, refs: list[pathlib.Path] | None = None) -> list[str]:
    """exec 인자 — 프롬프트는 `exec` 바로 뒤(값이 여러 개인 `-i` 가 맨 끝이라 뒤의 위치 인자를 삼키지 않게)."""
    args = ["exec", prompt, "-C", str(gen_dir), "--skip-git-repo-check", "-s", str(cdx.get("sandbox") or "workspace-write"),
            "--json", "-o", str(gen_dir / "last.txt")]
    if refs:
        args += ["-i", *[str(r) for r in refs]]
    return args


def generate(prompt: str, dest: pathlib.Path, gen_dir: pathlib.Path, cfg: dict, *, budget: CallBudget, refs: list[pathlib.Path] | None = None,
             ref_purpose: str = "style and shape", meta: dict | None = None, cli: list[str] | None = None, edit: bool = False) -> dict:
    """codex exec 한 번 → dest(PNG). gen_dir 에 prompt.txt · events.jsonl · stderr.txt · last.txt · result.json 을 남긴다.
    edit=True 면 첫 첨부 그림을 편집 대상으로 넘기는 틀(EDIT_WRAPPER — 1b 후속 A)이고, ref_purpose 는 지킬 것을 적는다.
    잠금은 부르는 쪽이 `CodexLock` 으로 잡는다(여러 장을 한 잠금 안에서). 실패는 CodexError / CodexQuota."""
    cdx = codex_cfg(cfg)
    budget.check()
    cli = cli or default_cli(cdx)
    gen_dir = pathlib.Path(gen_dir).resolve()
    gen_dir.mkdir(parents=True, exist_ok=True)
    refs = [pathlib.Path(r).resolve() for r in (refs or [])]
    for r in refs:
        if not r.is_file():
            raise CodexError("CODEX_REF_MISSING", f"reference image {r} does not exist")
    if edit and not refs:
        raise CodexError("CODEX_REF_MISSING", "edit mode needs the image to edit (-i)")
    if edit:
        full_prompt = EDIT_WRAPPER.format(prompt=prompt.strip(), refs=EDIT_NOTE.format(purpose=ref_purpose))
    else:
        full_prompt = WRAPPER.format(prompt=prompt.strip(), refs=REFS_NOTE.format(purpose=ref_purpose) if refs else "")
    (gen_dir / "prompt.txt").write_text(full_prompt, encoding="utf-8")
    root = codex_home(cdx) / "generated_images"
    before = _snapshot(root)
    cwd_before = {p.name for p in gen_dir.glob("*.png")}
    t0 = time.monotonic()
    rec = {"ok": False, "dest": pathlib.Path(dest).as_posix(), "gen_dir": gen_dir.as_posix(), "refs": [r.as_posix() for r in refs],
           "mode": "edit" if edit else "generate", **(meta or {})}
    try:
        code, out, err = _run(cli, build_args(full_prompt, gen_dir, cdx, refs), cdx, cwd=gen_dir, timeout=float(cdx.get("timeout_s") or 600))
    except CodexError as exc:
        rec.update(error=exc.code, duration_s=round(time.monotonic() - t0, 2))
        budget.add(rec)
        raise
    dur = round(time.monotonic() - t0, 2)
    (gen_dir / "events.jsonl").write_text(out, encoding="utf-8")
    (gen_dir / "stderr.txt").write_text(err, encoding="utf-8")
    ev = _parse_events(out)
    rec.update(exit_code=code, duration_s=dur, thread_id=ev["thread_id"], usage=ev["usage"], commands=ev["commands"], event_types=ev["types"])
    blob = (out + "\n" + err).lower()
    hits = [m for m in QUOTA_MARKERS if m in blob]
    if hits:
        rec.update(error="CODEX_QUOTA", quota_markers=hits, errors=ev["errors"][:3])
        budget.add(rec)
        raise CodexQuota("CODEX_QUOTA", f"codex usage limit (markers {hits}, exit {code}) — events kept in {gen_dir / 'events.jsonl'}",
                         markers=hits, exit_code=code, errors=ev["errors"][:3], gen_dir=gen_dir.as_posix())
    source, how = None, None
    if ev["thread_id"]:
        tdir = root / str(ev["thread_id"])
        pngs = sorted(tdir.glob("*.png"), key=lambda p: p.stat().st_mtime) if tdir.is_dir() else []
        if pngs:
            source, how = pngs[-1], "thread_id"
    if source is None:
        new = sorted((root / rel for rel in _snapshot(root) - before), key=lambda p: p.stat().st_mtime)
        if new:
            source, how = new[-1], "generated_images_diff"
    if source is None:
        new_cwd = sorted((p for p in gen_dir.glob("*.png") if p.name not in cwd_before), key=lambda p: p.stat().st_mtime)
        if new_cwd:
            source, how = new_cwd[-1], "cwd"
    if source is None:
        rec.update(error="CODEX_NO_IMAGE", errors=ev["errors"][:3], agent=(ev["agent_messages"] or [""])[-1][:200])
        budget.add(rec)
        failures = budget.consecutive_failures()
        if failures >= budget.suspect_after:
            raise CodexQuota("CODEX_QUOTA_SUSPECTED", f"{failures} codex calls in a row produced no image (exit {code}) — treating it as a usage limit",
                             exit_code=code, errors=ev["errors"][:3], gen_dir=gen_dir.as_posix())
        raise CodexError("CODEX_NO_IMAGE", f"codex finished (exit {code}) without an image: {(ev['errors'] or ev['agent_messages'] or [''])[-1][:200]}",
                         exit_code=code, errors=ev["errors"][:3], gen_dir=gen_dir.as_posix())
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    info = _png_info(dest)
    rec.update(ok=True, found_by=how, source=source.as_posix(), sha256=hashlib.sha256(dest.read_bytes()).hexdigest(), **info)
    budget.add(rec)
    (gen_dir / "result.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def work_root(cfg: dict) -> pathlib.Path:
    return config.repo_path(cfg["paths"]["work_root"])
