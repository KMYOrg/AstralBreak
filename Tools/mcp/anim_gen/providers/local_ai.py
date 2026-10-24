"""local_ai Provider — NVIDIA Kimodo(SOMA-RP v1.2) 텍스트 → 모션 (지침서 §4 · §14 Phase 5 · Docs/AIAnimation/LocalModelSurvey.md).

계획: 프롬프트 · 길이(프레임) · seed · 샘플 · 제약을 정해 계획에 고정한다 — 모델을 띄우지 않는다. seed 를 주지 않으면 지금 골라 고정한다
(보이는 것이 실행되는 것). 제약 파일(keep_pose 의 NPZ · kimodo_raw 의 JSON)은 ImportSourceRoots 아래만 받고 SHA-256 을 고정한다.
실행: <paths.kimodo_python> -I anim_gen/local_ai/kimodo_run.py args.json 을 Popen 으로 띄운다(서브프로세스 공통 — subprocess_step.py).
환경은 오프라인(HF_HUB_OFFLINE · LOCAL_CACHE, 캐시 = paths.kimodo_hf_cache) · 텍스트 인코더 CPU(VRAM < 3 GB, RAM 약 15 GB) — 실행에
HF 토큰이 필요 없다. 출력은 <ImportSourceRoots[0]>/LocalAI/<job_id>/A<n>/ 의 샘플별 NPZ + BVH(표준 T 포즈 SOMA77 · cm · 루트 트랙).

사슬: generate(local_ai) → convert(blender, BVH → FBX) → import → retarget → [direct_key] → validate.
BVH 는 계획 때 없으므로 변환 단계는 Kimodo 출력 규약(cm · +Y · 관절 78 · 30 fps)을 '예상'으로 두고 실행 때 정한다. 리타깃 소스 체인은
SOMA 수동 체인을 기본으로 채운다 — SOMA 의 LeftLeg 는 넓적다리라(HumanIK · Mixamo 는 정강이) 자동 캐릭터라이즈가 다리를 잘못 맞출 수 있다.
"""
from __future__ import annotations

import json
import pathlib
import secrets

from ..envelope import AnimGenError, diag, limitation
from ..local_ai import constraints as kc
from .base import PlanBlocked, PlanContext, RunContext, StepFailed, StepResult
from .subprocess_step import SubprocessProvider, child_env, file_sha256, import_roots, is_under

RUNNER = pathlib.Path(__file__).resolve().parents[1] / "local_ai" / "kimodo_run.py"
PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[2]
MODEL = "kimodo-soma-rp-v1.2"
MODEL_REPO = "nvidia/Kimodo-SOMA-RP-v1.2"
# 생성에 필요한 오프라인 캐시 — 체크포인트 + LLM2Vec(Llama 3 8B Instruct 게이트 + MIT 어댑터 2개)
REQUIRED_REPOS = (MODEL_REPO, "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp", "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised",
                  "meta-llama/Meta-Llama-3-8B-Instruct")
FPS = 30.0
MAX_FRAMES = 300            # 모델 카드: 최대 10초(300프레임 @ 30 fps)
DEFAULT_DURATION_S = 5.0    # kimodo_gen 기본값
# 실행 스크립트가 쓰는 BVH(표준 T 포즈) — 스파이크 실측: cm(키 176.4) · 정면 +Y · Root 래퍼 + SOMA77 · 30 fps
BVH_EXPECTED = {"unit": "cm", "facing": "+Y", "joints": 78, "fps": FPS}
SOMA_PELVIS = "Hips"
SOMA_FEET = ["LeftFoot", "RightFoot"]
# Vesper 자동 IK Rig 의 표준 체인 이름(FCharacterizationStandard) — 스파이크에서 수동 체인 PASSED(각속도 p99 비 0.98)
SOMA_CHAINS = [
    {"name": "Spine", "start": "Spine1", "end": "Chest"},
    {"name": "Neck", "start": "Neck1", "end": "Neck2"},
    {"name": "Head", "start": "Head", "end": "Head"},
    {"name": "LeftClavicle", "start": "LeftShoulder", "end": "LeftShoulder"},
    {"name": "LeftArm", "start": "LeftArm", "end": "LeftHand", "goal": "LeftHandIK"},
    {"name": "RightClavicle", "start": "RightShoulder", "end": "RightShoulder"},
    {"name": "RightArm", "start": "RightArm", "end": "RightHand", "goal": "RightHandIK"},
    {"name": "LeftLeg", "start": "LeftLeg", "end": "LeftToeBase", "goal": "LeftFootIK"},
    {"name": "RightLeg", "start": "RightLeg", "end": "RightToeBase", "goal": "RightFootIK"},
]
_RAW_MAX_BYTES = 8 << 20
_OFFLINE_ENV = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "LOCAL_CACHE": "true", "HF_HUB_DISABLE_TELEMETRY": "1",
                "GRADIO_ANALYTICS_ENABLED": "False", "TEXT_ENCODER_MODE": "local", "TEXT_ENCODER_DEVICE": "cpu", "TRANSFORMERS_VERBOSITY": "error"}


def repo_ref(cache: pathlib.Path, repo: str) -> pathlib.Path:
    return cache / ("models--" + repo.replace("/", "--")) / "refs" / "main"


class KimodoProvider(SubprocessProvider):
    label = "Kimodo"
    exit_prefix = "KIMODO"

    @staticmethod
    def paths(policy: dict | None) -> tuple[pathlib.Path | None, pathlib.Path | None]:
        p = (policy or {}).get("paths") or {}
        return (pathlib.Path(p["kimodo_python"]) if p.get("kimodo_python") else None,
                pathlib.Path(p["kimodo_hf_cache"]) if p.get("kimodo_hf_cache") else None)

    def installed(self, policy: dict) -> tuple[bool, str | None]:
        python, cache = self.paths(policy)
        if not python or not python.is_file():
            return False, f"kimodo_python not found: {python}"
        missing = [r for r in REQUIRED_REPOS if not cache or not repo_ref(cache, r).is_file()]
        if missing:
            return False, f"kimodo_hf_cache {cache} lacks {missing} — download them first (Llama 3 is gated: accept its license on Hugging Face)"
        return True, f"kimodo_python {python} · cache {cache}"

    @staticmethod
    def postprocess_available(python: pathlib.Path) -> bool:
        """Kimodo 발 미끄러짐 후처리(motion_correction C++ 확장)가 venv 에 설치됐는가 — 파일로 본다(그 venv 를 띄우지 않는다)."""
        pkg = python.parents[1] / "Lib" / "site-packages" / "motion_correction"
        return (pkg / "__init__.py").is_file() and any(pkg.glob("_motion_correction*"))

    @staticmethod
    def model_commit(cache: pathlib.Path | None) -> str | None:
        try:
            return repo_ref(cache, MODEL_REPO).read_text(encoding="utf-8").strip() if cache else None
        except OSError:
            return None

    # ---- 계획 (모델을 띄우지 않는다) ----
    def plan_generate(self, request: dict, pctx: PlanContext) -> dict:
        prompt = request["prompt"]
        if not prompt:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "MISSING_INPUT", "local_ai needs request.prompt — the English text the model reads "
                              "(description is only recorded)", missing=["prompt"])
        gen = request["generation"]
        duration = request["duration_seconds"] or DEFAULT_DURATION_S
        # 길이 = (프레임 − 1) / fps 가 요청 길이가 되게 한 프레임 더 만든다(최대 300)
        frames = min(int(round(duration * FPS)) + 1, MAX_FRAMES)
        if frames < 2:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "DURATION_TOO_SHORT", f"duration {duration}s is shorter than two frames at {FPS:g} fps")
        python, cache = self.paths(pctx.policy)
        postprocess = {"auto": None, "on": True, "off": False}[gen["postprocess"]]
        available = bool(python and python.is_file() and self.postprocess_available(python))
        if postprocess is None:
            postprocess = available
        elif postprocess and not available:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "POSTPROCESS_UNAVAILABLE", "generation.postprocess on, but motion_correction is not installed "
                              "in the Kimodo venv — use auto or off")
        try:
            specs = kc.convert(gen["constraints"], FPS, frames)
            files = self._pin_constraint_files(specs, pctx.settings, frames)
        except kc.ConstraintError as err:
            raise PlanBlocked("UNSUPPORTED_REQUEST", err.reason, err.message, **err.details) from None
        seed = gen["seed"]
        if seed is None:
            seed = secrets.randbelow(2 ** 31)
            pctx.diagnostics.append(diag("info", "SEED_PINNED", f"generation.seed not given — {seed} pinned so the plan reruns the same motion"))
        if not request["duration_seconds"]:
            pctx.diagnostics.append(diag("info", "DURATION_DEFAULTED", f"duration_seconds not given — {DEFAULT_DURATION_S:g}s (Kimodo default)"))
        risks = ["TEXT_ENCODER_CPU"]  # Llama 3 8B 인코더를 CPU 로 — 한 건 약 35초, RAM 약 15 GB (스파이크)
        if pctx.settings is None and files:
            risks.append("IMPORT_ROOTS_UNCHECKED")
        lims = [limitation("FINGERS_STATIC", "Kimodo 는 손가락 없는 30관절로 생성한다 — SOMA77 손은 고정 포즈(relaxed hands)", "provider")]
        if not postprocess:
            lims.append(limitation("POSTPROCESS_OFF", "Kimodo 발 미끄러짐 후처리(motion_correction)를 쓰지 않았다 — 발이 미끄러질 수 있다", "provider"))
        inputs = {"model": MODEL, "repo": MODEL_REPO, "model_commit": self.model_commit(cache), "prompt": prompt, "duration_seconds": duration,
                  "frames": frames, "fps": FPS, "seed": seed, "samples": gen["samples"], "pick": gen["pick"], "steps": gen["steps"],
                  "postprocess": postprocess, "constraints": specs, "constraint_files": files}
        return {"step": "generate", "provider": self.name, "tool": "kimodo_run.py (Kimodo venv)", "inputs": inputs,
                "output": "bvh", "bvh": dict(BVH_EXPECTED, frames=frames),
                "retarget_defaults": {"source_pelvis": SOMA_PELVIS, "source_chains": SOMA_CHAINS, "source_feet": SOMA_FEET},
                "risks": risks, "expected_limitations": lims, "measured": {"length": round((frames - 1) / FPS, 4), "frame_rate": FPS}}

    def _pin_constraint_files(self, specs: list[dict], settings: dict | None, frames: int) -> list[dict]:
        """keep_pose · kimodo_raw 파일 → 루트 검사 · SHA-256 고정(kimodo_raw 는 모양 · 프레임 범위도)."""
        files = []
        for spec in specs:
            key = {"keep_pose": "npz", "raw": "path"}.get(spec["kind"])
            if key is None:
                continue
            path = pathlib.Path(spec[key])
            self._check_root(path, settings)
            if not path.is_file():
                raise kc.ConstraintError("FILE_NOT_FOUND", f"{spec['source']}: no file at {path.as_posix()}")
            if spec["kind"] == "raw":
                if path.stat().st_size > _RAW_MAX_BYTES:
                    raise kc.ConstraintError("BAD_RAW_CONSTRAINTS", f"{spec['source']}: {path.name} is over {_RAW_MAX_BYTES >> 20} MB")
                try:
                    items = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise kc.ConstraintError("BAD_RAW_CONSTRAINTS", f"{spec['source']}: {path.name} is not JSON ({exc})") from None
                kc.check_raw(items, frames, spec["source"])
            files.append({"source": spec["source"], "path": path.as_posix(), "sha256": file_sha256(path)})
        return files

    @staticmethod
    def _check_root(path: pathlib.Path, settings: dict | None) -> None:
        if settings is None:
            return
        roots = import_roots(settings)
        if not any(is_under(path, root) for root in roots):
            raise AnimGenError("IMPORT_SOURCE_NOT_ALLOWED", f"{path.as_posix()} is outside [AnimGraphMcp] ImportSourceRoots — put constraint files under one",
                               reason="OUTSIDE_IMPORT_ROOTS", allowed=[r.as_posix() for r in roots])

    # ---- 실행 ----
    def run(self, ctx: RunContext) -> StepResult:
        python, cache = self.paths(ctx.policy)
        installed, note = self.installed(ctx.policy or {})
        if not installed:
            raise StepFailed("PROVIDER_UNAVAILABLE", "NOT_INSTALLED", note)
        settings = ctx.editor.status()
        if settings is None:
            raise StepFailed("PROVIDER_UNAVAILABLE", "EDITOR", "Editor unreachable — import roots come from get_editor_status and the next steps need it",
                             fatal=True)
        inputs = ctx.step["inputs"]
        for pinned in inputs["constraint_files"]:
            path = pathlib.Path(pinned["path"])
            try:
                self._check_root(path, settings)
            except AnimGenError as err:
                raise StepFailed(err.code, err.reason, err.message, fatal=True) from None
            if not path.is_file() or file_sha256(path) != pinned["sha256"]:
                raise StepFailed("UNSUPPORTED_REQUEST", "FILE_CHANGED", f"{pinned['source']}: {path.as_posix()} changed after planning — plan again",
                                 fatal=True)
        out_dir = import_roots(settings)[0] / "LocalAI" / ctx.job_id / f"A{ctx.attempt}"
        out_dir.mkdir(parents=True, exist_ok=True)
        report, log, args_path = out_dir / "report.json", out_dir / "kimodo.log", out_dir / "args.json"
        report.unlink(missing_ok=True)  # 같은 시도 폴더의 이전 report 가 '끝남'으로 읽히지 않게
        args = {"model": inputs["model"], "repo": inputs["repo"], "prompt": inputs["prompt"], "frames": inputs["frames"], "fps": inputs["fps"],
                "seed": inputs["seed"], "samples": inputs["samples"], "steps": inputs["steps"], "postprocess": inputs["postprocess"],
                "constraints": inputs["constraints"], "root_track": True, "out_dir": out_dir.as_posix(), "stem": "kimodo",
                "report": report.as_posix(), "package_dir": PACKAGE_DIR.as_posix()}
        args_path.write_text(json.dumps(args, ensure_ascii=False, indent=1), encoding="utf-8")
        cmd = [str(python), "-I", str(RUNNER), str(args_path)]
        env = child_env({**_OFFLINE_ENV, "HF_HUB_CACHE": str(cache)})
        handle = self.start(cmd, out_dir, log, ctx.policy, env, report=report.as_posix(), args=args_path.as_posix(), pick=inputs["pick"],
                            samples=inputs["samples"], frames=inputs["frames"], postprocess=inputs["postprocess"])
        return StepResult(pending=handle)

    def poll(self, ctx: RunContext, handle: dict) -> StepResult | None:
        report = self.await_report(handle)
        if report is None:
            return None
        if not report.get("ok"):
            error = report.get("error") or {}
            raise StepFailed("GENERATION_FAILED", error.get("code") or "KIMODO_FAILED", f"kimodo_run: {error.get('message')}{self.tail(handle)}")
        samples = report.get("samples") or []
        if len(samples) != handle["samples"]:
            raise StepFailed("GENERATION_FAILED", "NO_OUTPUT", f"Kimodo reported {len(samples)} sample(s), planned {handle['samples']}{self.tail(handle)}")
        missing = [s["bvh"] for s in samples if not pathlib.Path(s["bvh"]).is_file()]
        if missing:
            raise StepFailed("GENERATION_FAILED", "NO_OUTPUT", f"Kimodo reported success but {missing[0]} is missing{self.tail(handle)}")
        picked = samples[handle["pick"]]
        diagnostics = [diag("info", "KIMODO_GENERATED", f"{len(samples)} sample(s) in {report.get('seconds', {}).get('total')}s on "
                            f"{(report.get('device') or {}).get('gpu') or 'CPU'} — using sample {handle['pick']}: {picked['bvh']}",
                            files=[{k: s[k] for k in ("index", "bvh", "npz")} for s in samples])]
        diagnostics += [diag("warning", w["code"], w["message"]) for w in report.get("warnings", [])]
        root = picked.get("root") or {}
        generated = {"model": report.get("model"), "samples": [{k: s.get(k) for k in ("index", "bvh", "npz", "frames", "root")} for s in samples],
                     "pick": handle["pick"], "seconds": report.get("seconds"), "postprocess": report.get("postprocess"), "root": root}
        return StepResult(values={"file": picked["bvh"], "generated": generated}, diagnostics=diagnostics)
