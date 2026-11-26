"""한 명령 — 컨셉 후보 → (사람이 고름) → 글자 참고판 → run → 요약 (설계 §11 'Phase 3 설계' ⑤, Phase 3-3).

    make_screen.py <fixture> [--text "화면 설명"] [--candidates 2] [--style-ref <png>]   후보를 만들고 **멈춘다**(종료 코드 4) — 그림을 사람이 본다
    make_screen.py <fixture> --pick N                                                    고른 후보를 원본 아트로 → 참고판 → run → 요약
    make_screen.py <fixture> --pick current                                              이미 고른 concept.png 로(codex 0 — 시안에서 오린 화면 등)

fixture = fixtures/ 아래 폴더 이름(또는 경로). inputs.yaml 은 사람이 쓴다(계약은 요청이 정한다). 후보 = make_concept.py --only art(codex 1 회씩, 글자가 그려지면 2 회),
work/_candidates/<fixture>/<n>/. 고르기는 자동으로 하지 않는다. 참고판은 <fixture>/text_ref_layout.yaml 이 있으면 엔진 글꼴로 그리고(codex 0) 없으면 codex 편집 1 회.
승격은 하지 않는다(사람이 compare.png 를 본 뒤 promote_widget → promote_screen.py record).
종료 코드: 0 통과 · 1 실패 · 2 미완 · 3 codex 한도 · 4 고르기를 기다림.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from core import config  # noqa: E402

EXIT_PASS, EXIT_FAIL, EXIT_PICK = 0, 1, 4
FIXTURES = config.UIGEN_DIR / "fixtures"
ART_FILES = ("concept.png", "concept.json")


def say(msg: str) -> None:
    print(msg, flush=True)


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="uigen — one command: concept candidates, a person picks, then text reference + run + summary")
    ap.add_argument("fixture", help="folder under Tools/uigen/fixtures (or a path) holding inputs.yaml")
    ap.add_argument("--text", help="screen description for the concept prompt (default <fixture>/concept_prompt.md)")
    ap.add_argument("--candidates", type=int, default=2, help="how many concept candidates to draw (default 2)")
    ap.add_argument("--style-ref", action="append", default=[], help="style reference picture (our own art) passed to make_concept.py")
    ap.add_argument("--pick", help="candidate number to use, or 'current' for the concept.png already in the fixture")
    ap.add_argument("--replace", action="store_true", help="with --pick N: replace the concept.png already in the fixture")
    ap.add_argument("--until", help="passed to run_pipeline.py")
    ap.add_argument("--work-root", help="override paths.work_root")
    ap.add_argument("--config", help="pipeline.yaml to use")
    return ap.parse_args(argv)


def fixture_dir(name: str) -> pathlib.Path:
    p = pathlib.Path(name)
    return p if p.is_absolute() or (p / "inputs.yaml").is_file() else FIXTURES / name


def _work(opts) -> pathlib.Path:
    return pathlib.Path(opts.work_root) if opts.work_root else config.repo_path(config.load_pipeline(opts.config)["paths"]["work_root"])


def _common(opts) -> list[str]:
    return (["--config", opts.config] if opts.config else []) + (["--work-root", opts.work_root] if opts.work_root else [])


def make_candidates(opts, fx: pathlib.Path, root: pathlib.Path, concept_main) -> int:
    prompt = fx / "concept_prompt.md"
    root.mkdir(parents=True, exist_ok=True)
    if opts.text:
        prompt = root / "concept_prompt.md"
        prompt.write_text(opts.text.strip() + "\n", encoding="utf-8", newline="\n")
    if not prompt.is_file():
        say(f"{fx.name}: no concept_prompt.md and no --text")
        return EXIT_FAIL
    done = []
    first = 1 + max([int(p.name) for p in root.iterdir() if p.is_dir() and p.name.isdigit()] or [0])      # 예전 후보는 그대로 둔다
    for n in range(first, first + max(1, opts.candidates)):
        out = root / str(n)
        argv = ["--out-dir", str(out), "--prompt-file", str(prompt), "--only", "art", "--inputs", str(fx / "inputs.yaml")]
        argv += [x for r in opts.style_ref for x in ("--style-ref", r)] + _common(opts)
        code = concept_main(argv)
        if code not in (0, None) or not (out / "concept.png").is_file():
            say(f"candidate {n}: make_concept.py failed (exit {code})")
            return code or EXIT_FAIL
        done.append(n)
        say(f"candidate {n}: {config.repo_rel(out / 'concept.png')}")
    say(f"pick one by eye, then: make_screen.py {opts.fixture} --pick <{', '.join(map(str, done))}>")
    return EXIT_PICK


def use_candidate(opts, fx: pathlib.Path, root: pathlib.Path) -> str | None:
    """고른 후보를 fixture 로 — 이미 있으면 --replace 없이는 안 바꾼다. → 못 하는 이유."""
    src = root / str(opts.pick)
    if not (src / "concept.png").is_file():
        return f"no candidate {opts.pick} in {config.repo_rel(root)}"
    if (fx / "concept.png").is_file() and not opts.replace:
        return f"{config.repo_rel(fx / 'concept.png')} exists — use --pick current, or --replace to take candidate {opts.pick} instead"
    for f in ART_FILES:
        if (src / f).is_file():
            shutil.copyfile(src / f, fx / f)
    return None


def summary(report: pathlib.Path) -> dict:
    """run 의 한 눈 요약 — 사람이 볼 그림 경로까지. '통과'는 '컨셉과 똑같다'가 아니다(오류 · 근사 · 사람 눈을 따로 적는다)."""
    rep = json.loads(report.read_text(encoding="utf-8"))
    gates = rep.get("gates") or []
    diag = ((rep.get("recorded") or {}).get("diagnosis") or {}).get("summary") or {}
    out = {"run_id": rep.get("run_id"), "status": rep.get("status"), "gates": f"{sum(1 for g in gates if g.get('pass'))}/{len(gates)}",
           "failed": [g["name"] for g in gates if not g.get("pass")], "errors": diag.get("errors"), "approx": diag.get("approx"), "attempts": len(rep.get("attempts") or []),
           "compare": config.repo_rel(report.parent / "compare.png") if (report.parent / "compare.png").is_file() else None, "eye_check": "not yet — look at compare.png",
           **({"message": rep["message"]} if rep.get("message") else {})}
    return out


def main(argv=None, *, concept_main=None, pipeline_main=None) -> int:
    opts = parse_args(argv)
    fx = fixture_dir(opts.fixture)
    if not (fx / "inputs.yaml").is_file():
        say(f"{fx.as_posix()} has no inputs.yaml")
        return EXIT_FAIL
    if concept_main is None:
        import make_concept
        concept_main = make_concept.main
    if pipeline_main is None:
        import run_pipeline
        pipeline_main = run_pipeline.main
    work = _work(opts)
    root = work / "_candidates" / fx.name
    if not opts.pick:
        if (fx / "concept.png").is_file():
            say(f"note: {config.repo_rel(fx / 'concept.png')} is already there — new candidates do not replace it (--pick N --replace does)")
        return make_candidates(opts, fx, root, concept_main)
    if opts.pick != "current":
        why = use_candidate(opts, fx, root)
        if why:
            say(why)
            return EXIT_FAIL
    if not (fx / "concept.png").is_file():
        say(f"{config.repo_rel(fx)} has no concept.png — make candidates first (no --pick)")
        return EXIT_FAIL
    inputs = config.load_yaml(fx / "inputs.yaml")
    if inputs.get("concept_text_ref"):
        layout = fx / "text_ref_layout.yaml"
        # 배치 yaml 로 그리는 참고판은 늘 다시 그린다(결정적 · codex 0 — yaml 과 어긋난 옛 그림으로 돌지 않게). codex 참고판은 그림이 그대로면 있는 것을 쓴다
        if layout.is_file() or opts.pick != "current" or not (fx / inputs["concept_text_ref"]).is_file():
            argv2 = ["--out-dir", str(fx), "--only", "text_ref", "--inputs", str(fx / "inputs.yaml"), "--force"] + (["--draw", str(layout)] if layout.is_file() else []) + _common(opts)
            code = concept_main(argv2)
            if code not in (0, None):
                say(f"the text reference failed (exit {code})")
                return code
    before = {p.name for p in work.glob("R*") if p.is_dir()} if work.is_dir() else set()
    code = pipeline_main(["--inputs", str(fx / "inputs.yaml")] + (["--until", opts.until] if opts.until else []) + _common(opts))
    new = sorted(p for p in work.glob(f"R*_{inputs['screen_id']}") if p.name not in before and (p / "report.json").is_file()) if work.is_dir() else []
    if new:
        say(json.dumps(summary(new[-1] / "report.json"), ensure_ascii=False))
    return int(code or 0)


if __name__ == "__main__":
    sys.exit(main())
