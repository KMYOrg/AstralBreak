"""컨셉아트 1장 만들기 (Phase 1b 준비 — 설계 §11 '1b 착수 때 정한 것'). codex built-in image_gen 으로 화면 컨셉을 만들어 fixture 로 둔다.

원래 text 모드(Phase 3)의 목업 단계 성격이다. 1b 는 이 그림을 concept 입력으로 쓰고, 나중에 사람이 그린 컨셉으로 바꿔 같은 파이프라인을 다시 돌린다.

    Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/make_concept.py --out-dir Tools/uigen/fixtures/m4_combat_hud_concept
    (+ --prompt-file <md> · --force(있는 concept.png 를 덮음) · --max-calls N(기본 1))

출력: <out-dir>/concept.png · concept.json(출처 — codex 버전 · thread_id · 프롬프트 sha256 · 크기 · 시각), 호출 기록 · 이벤트 원문은
work/_concept/<시각>/ (git 무시). codex 호출은 한 번에 하나(work/.codex.lock) · ChatGPT 로그인 확인 · stdin 닫음 · API 키 환경 변수 제거(gen/codex.py).
종료 코드: 0 = 생성 · 1 = 실패 · 3 = 한도(나중에 다시).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from core import config  # noqa: E402
from gen import codex  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_QUOTA = 0, 1, 3


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="make one screen concept image with codex built-in image_gen (Phase 1b input)")
    ap.add_argument("--out-dir", required=True, help="fixture folder — concept_prompt.md is read from here unless --prompt-file")
    ap.add_argument("--prompt-file", help="prompt text (default <out-dir>/concept_prompt.md)")
    ap.add_argument("--force", action="store_true", help="replace an existing concept.png")
    ap.add_argument("--max-calls", type=int, default=1, help="codex calls allowed in this invocation (default 1 — plan usage)")
    ap.add_argument("--config", help="pipeline.yaml to use")
    ap.add_argument("--work-root", help="override paths.work_root")
    return ap.parse_args(argv)


def _rel(p: pathlib.Path) -> str:
    """저장소 기준 상대 경로(커밋되는 concept.json 에 로컬 절대 경로를 남기지 않게)."""
    try:
        return pathlib.Path(p).resolve().relative_to(config.REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return pathlib.Path(p).name


def main(argv=None, *, cli: list[str] | None = None) -> int:
    opts = parse_args(argv)
    cfg = config.load_pipeline(opts.config)
    out_dir = pathlib.Path(opts.out_dir)
    prompt_file = pathlib.Path(opts.prompt_file) if opts.prompt_file else out_dir / "concept_prompt.md"
    dest = out_dir / "concept.png"
    if dest.exists() and not opts.force:
        print(f"make_concept: {dest} already exists — pass --force to replace it", file=sys.stderr)
        return EXIT_FAIL
    try:
        prompt = prompt_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(f"make_concept: {prompt_file}: {exc}", file=sys.stderr)
        return EXIT_FAIL
    work_root = pathlib.Path(opts.work_root) if opts.work_root else codex.work_root(cfg)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    gen_dir = work_root / "_concept" / stamp
    budget = codex.CallBudget(gen_dir / "codex_calls.jsonl", opts.max_calls, int(codex.codex_cfg(cfg).get("suspect_quota_after_failures", 2)))
    tmp = gen_dir / "concept.png"
    try:
        with codex.CodexLock(work_root, f"make_concept:{stamp}"):
            info = codex.preflight(cfg, cli=cli)
            rec = codex.generate(prompt, tmp, gen_dir / "call_001", cfg, budget=budget, meta={"purpose": "concept"}, cli=cli)
    except codex.CodexQuota as exc:
        print(json.dumps({"status": "quota", "code": exc.code, "message": str(exc), "gen_dir": gen_dir.as_posix()}, ensure_ascii=False))
        return EXIT_QUOTA
    except codex.CodexError as exc:
        print(json.dumps({"status": "fail", "code": exc.code, "message": str(exc), "gen_dir": gen_dir.as_posix()}, ensure_ascii=False))
        return EXIT_FAIL
    out_dir.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(tmp.read_bytes())
    meta = {"schema_version": 1, "kind": "concept", "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "generator": "codex built-in image_gen",
            "codex_version": info["version"], "thread_id": rec.get("thread_id"), "found_by": rec.get("found_by"),
            "prompt_file": prompt_file.name, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "file": dest.name, "sha256": rec["sha256"], "size": rec["size"], "has_alpha_channel": rec.get("has_alpha_channel"),
            "duration_s": rec.get("duration_s"), "usage": rec.get("usage"), "commands": rec.get("commands"), "record": _rel(gen_dir),
            "note": "AI-generated stand-in for a hand-made concept (Phase 1b) — replace concept.png with a person's art and rerun"}
    (out_dir / "concept.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "file": dest.as_posix(), "size": rec["size"], "thread_id": rec.get("thread_id"),
                      "duration_s": rec.get("duration_s")}, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
