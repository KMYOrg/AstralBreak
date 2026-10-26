"""local_ai Provider — NVIDIA Kimodo(SOMA-RP v1.2) 텍스트 → 모션 (지침서 §4 · §14 Phase 5 · Docs/AIAnimation/LocalModelSurvey.md).

계획: 프롬프트 · 길이(프레임) · seed · 샘플 · 제약을 정해 계획에 고정한다 — 모델을 띄우지 않는다. seed 를 주지 않으면 지금 골라 고정한다
(보이는 것이 실행되는 것). 제약 파일(keep_pose 의 NPZ · kimodo_raw 의 JSON)은 ImportSourceRoots 아래만 받고 SHA-256 을 고정한다.
실행: <paths.kimodo_python> -I anim_gen/local_ai/kimodo_run.py args.json 을 Popen 으로 띄운다(서브프로세스 공통 — subprocess_step.py).
환경은 오프라인(HF_HUB_OFFLINE · LOCAL_CACHE, 캐시 = paths.kimodo_hf_cache) · 텍스트 인코더 CPU(VRAM < 3 GB, RAM 약 15 GB) — 실행에
HF 토큰이 필요 없다. 출력은 <ImportSourceRoots[0]>/LocalAI/<job_id>/A<n>/ 의 샘플별 NPZ + BVH(표준 T 포즈 SOMA77 · cm · 루트 트랙).

사슬: generate(local_ai) → convert(blender, BVH → FBX) → import → retarget → [direct_key] → validate.
BVH 는 계획 때 없으므로 변환 단계는 Kimodo 출력 규약(cm · +Y · 관절 78 · 30 fps)을 '예상'으로 두고 실행 때 정한다. 리타깃 소스 체인은
SOMA 수동 체인을 기본으로 채운다 — SOMA 의 LeftLeg 는 넓적다리라(HumanIK · Mixamo 는 정강이) 자동 캐릭터라이즈가 다리를 잘못 맞출 수 있다.

Phase 8-1: 요청 플래그(two_hand_weapon_grip · foot_contact)를 2차 생성 제약으로 바꾸고(local_ai/refine.py — 계획에 규칙 · 프레임 · 목표를 보인다),
generation.candidates 개의 seed(seed, seed+1, …)를 한 Kimodo 실행으로 만든다. 그 둘 중 하나라도 있으면 사슬에 select 단계(retarget 파이프 —
후보를 모두 Vesper 로 리타깃 · 측정해 점수로 하나를 고른다)가 끼고, 기한은 확산 횟수만큼 늘린다(DIFFUSION_EXTRA_S).
"""
from __future__ import annotations

import json
import pathlib
import secrets

from .. import motion_metrics
from ..envelope import AnimGenError, diag, limitation
from ..local_ai import constraints as kc
from ..local_ai import refine as kr
from .base import PlanBlocked, PlanContext, RunContext, StepFailed, StepResult
from .builtin import RetargetPipe
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
# 생성 골격의 어깨 관절 폭 · 팔 길이(motion_metrics.arm_dims 정의) — 자루 무기 간격 사상(gap_map)의 소스 쪽. SOMA77 은 고정 골격이라 상수:
# Kimodo BVH 표준 T 포즈 오프셋(기록 Job job_20261026_192555_f991aa kimodo_00.bvh, 2026-10-26)에서 LeftArm ↔ RightArm 32.96 cm,
# LeftArm → LeftForeArm 28.74 + → LeftHand 27.09 · 오른팔 28.74 + 27.13(평균 55.85 — NPZ 관절 위치의 위팔 길이와 0.05 cm 안). 대상 쪽은 계획이 잰다
SOMA_ARMS = {"shoulder_width_cm": 32.96, "arm_cm": 55.85}
# 확산 한 번 더 할 때마다 기한에 더하는 초 — 스파이크(2026-10-26, 에디터 띄운 채) 확산 + 후처리 20 ~ 27초
DIFFUSION_EXTRA_S = 25.0


def _soma_hand_chains(side: str) -> list[dict]:
    """SOMA77 손가락은 Hand{F}1(손목에서 2.9~4.0 cm, 메타카팔) → 2 · 3 · 4 → End(끝점), 엄지는 Thumb1~3 → End. 대상에 손가락 체인이
    없으면 자동 정렬이 꺼진 op 의 퍼지 매핑을 따라 손가락을 꺾었고(2026-10-24), 자동 캐릭터라이즈는 SOMA 를 Mixamo 로 잡아 Index1~3
    (메타카팔부터 한 마디 밀림)을 손가락으로 맞춘다. 같은 체인을 범용 제안기(create_ik_rig finger_chain_suggestion)도 낸다."""
    chains = [{"name": f"{side}Thumb", "start": f"{side}HandThumb1", "end": f"{side}HandThumb3"}]
    for finger in ("Index", "Middle", "Ring", "Pinky"):
        chains += [{"name": f"{side}{finger}Metacarpal", "start": f"{side}Hand{finger}1", "end": f"{side}Hand{finger}1"},
                   {"name": f"{side}{finger}", "start": f"{side}Hand{finger}2", "end": f"{side}Hand{finger}4"}]
    return chains


# Vesper 자동 IK Rig 의 표준 체인 이름(FCharacterizationStandard) — 스파이크에서 수동 체인 PASSED(각속도 p99 비 0.98). 손은 _soma_hand_chains
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
] + _soma_hand_chains("Left") + _soma_hand_chains("Right")
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
        lims = [limitation("FINGERS_STATIC", "Kimodo 는 손가락 없는 30관절로 생성한다 — SOMA77 손은 고정 포즈(relaxed hands)라 결과 손가락도 "
                           "그 포즈를 따른다(손 체인 매핑)", "provider")]
        # Phase 8-1 — 플래그 → 2차 생성 제약 · seed 후보
        spacing, bones = self._grip_spacing(request, pctx)
        try:
            refine = kr.plan(request["constraints"], gen["refine"], frames=frames, fps=FPS,
                             requested_root=any(c["type"] == "root_path" for c in gen["constraints"]), spacing=spacing)
        except kr.RefineError as err:
            raise PlanBlocked("UNSUPPORTED_REQUEST", err.code, f"generation.refine: {err.message}") from None
        if refine["passes"] == 2 and gen["samples"] > 1:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "REFINE_WITH_SAMPLES", "generation.refine makes one sample per seed (pass 2 is built from pass 1) — "
                              "use generation.candidates instead of samples, or refine.mode off", flags=refine["flags"])
        if "foot_contact" in refine["flags"] and refine["passes"] == 2 and not postprocess:
            if gen["postprocess"] == "auto" and available:
                postprocess = True
            else:
                lims.append(limitation("FOOT_CONTACT_WITHOUT_POSTPROCESS", "foot_contact 를 2차 생성 발 제약으로 바꿨지만 Kimodo 후처리(접지 정리)가 꺼져 있다 — "
                                       "발 위치는 1차를 따르되 접지 중 미끄러질 수 있다", "provider", constraint="foot_contact"))
        if not postprocess:
            lims.append(limitation("POSTPROCESS_OFF", "Kimodo 발 미끄러짐 후처리(motion_correction)를 쓰지 않았다 — 발이 미끄러질 수 있다", "provider"))
        inputs = {"model": MODEL, "repo": MODEL_REPO, "model_commit": self.model_commit(cache), "prompt": prompt, "duration_seconds": duration,
                  "frames": frames, "fps": FPS, "seed": seed, "samples": gen["samples"], "pick": gen["pick"], "steps": gen["steps"],
                  "postprocess": postprocess, "constraints": specs, "constraint_files": files}
        step = {"step": "generate", "provider": self.name, "tool": "kimodo_run.py (Kimodo venv)", "inputs": inputs,
                "output": "bvh", "bvh": dict(BVH_EXPECTED, frames=frames),
                "retarget_defaults": {"source_pelvis": SOMA_PELVIS, "source_chains": SOMA_CHAINS, "source_feet": SOMA_FEET},
                "risks": risks, "expected_limitations": lims, "measured": {"length": round((frames - 1) / FPS, 4), "frame_rate": FPS}}
        if gen["candidates"] > 1 or refine["passes"] == 2:
            self._plan_candidates(step, request, refine, pctx, spacing, bones)
        return step

    @staticmethod
    def _grip_spacing(request: dict, pctx: PlanContext) -> tuple[dict | None, dict | None]:
        """자루 무기 간격(generation.refine.grip.spacing_cm = 생성 골격 · target_spacing_cm = 대상 메시) → (motion_metrics.grip_spacing — 생성 ·
        대상 간격 · 허용 · 띠 · 사상, 잰 대상 측정 본). 사상은 두 골격의 기준 포즈 치수(SOMA_ARMS · 대상 — RetargetPipe.selection_bones arm_dims)로
        계획에서 한 번 — generate 규칙(생성 간격: 목표 · 소스 띠)과 select(대상 띠)가 이 한 값을 쓴다. 파지 플래그 · refine · 간격 요청 중 하나라도
        없으면 (None, None) — 검 손잡이는 지금 그대로."""
        refine = request["generation"]["refine"]
        g = refine["grip"]
        if refine["mode"] == "off" or not (request["constraints"] or {}).get("two_hand_weapon_grip") or (g["spacing_cm"] is None and g["target_spacing_cm"] is None):
            return None, None
        field = "generation.refine.grip." + ("spacing_cm" if g["spacing_cm"] is not None else "target_spacing_cm")
        if not pctx.editor_ok:
            raise PlanBlocked("PROVIDER_UNAVAILABLE", "EDITOR", f"{field}: a polearm grip gap differs between the generation skeleton and the target mesh — "
                              "the plan measures the target arms (inspect_skeleton) to map it; plan again with the editor running")
        bones = RetargetPipe.selection_bones(pctx.editor, request["target_skeleton"], pctx.diagnostics)
        dims = bones.get("arm_dims")
        if not dims:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "TARGET_ARMS_UNKNOWN", f"{field}: no reference-pose position for the target's shoulder · elbow · wrist "
                              f"bones {[bones[k] for k in ('shoulder_l', 'elbow_l', 'hand_l', 'shoulder_r', 'elbow_r', 'hand_r')]} — the gap cannot be mapped")
        try:
            spacing = motion_metrics.grip_spacing(motion_metrics.gap_map(SOMA_ARMS, dims), source_cm=g["spacing_cm"], target_cm=g["target_spacing_cm"])
        except motion_metrics.GripSpacingError as err:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "GRIP_SPACING_OUT_OF_RANGE", f"{field}: {err}") from None
        reach = SOMA_ARMS["shoulder_width_cm"] + SOMA_ARMS["arm_cm"] * (kr.REACH["lead"] + kr.REACH["support"])
        if spacing["source_cm"] > reach:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "GRIP_SPACING_OUT_OF_RANGE", f"{field}: {spacing['target_cm']:g} cm on the target is "
                              f"{spacing['source_cm']:g} cm on the generation skeleton — beyond both arms' reach ({reach:.1f} cm)")
        return spacing, bones

    def _plan_candidates(self, step: dict, request: dict, refine: dict, pctx: PlanContext, spacing: dict | None = None, bones: dict | None = None) -> None:
        """seed 후보 · 2차 생성 — 계획에 seed 목록 · 규칙 · 기한을 보이고, 라우터에 select 단계와 처리한 플래그를 알린다(모델을 띄우지 않는다).
        spacing · bones = _grip_spacing 결과 — select 가 같은 대상 띠 · 측정 본을 쓴다(대상을 다시 재지 않는다)."""
        gen, inputs = request["generation"], step["inputs"]
        seeds = [inputs["seed"] + i for i in range(gen["candidates"])]
        diffusions = len(seeds) * refine["passes"]
        extra = DIFFUSION_EXTRA_S * (diffusions - 1)
        grip_rule = next((r for r in refine["rules"] if r["flag"] == "two_hand_weapon_grip"), None)
        window = [grip_rule["frames"]["from"] / FPS, grip_rule["frames"]["to"] / FPS] if grip_rule else None
        inputs.update(seeds=seeds, candidates=len(seeds), refine=refine, metric_window=window, timeout_extra_s=extra,
                      timeout_s=self.timeout_s(pctx.policy) + extra, diffusions=diffusions)
        step["select"] = {"candidates": [{"index": i, "seed": s} for i, s in enumerate(seeds)], "flags": refine["flags"], "grip_window_s": window,
                          "grip_spacing": spacing if grip_rule else None, "weights": gen["select"]["weights"]}
        if bones and grip_rule:
            step["select"]["bones"] = bones
        step["handles_constraints"] = refine["flags"] if refine["passes"] == 2 else []
        lims = step["expected_limitations"]
        if refine["passes"] == 2:
            step["risks"].append("REFINE_RESOLVED_AT_RUN")
            if "two_hand_weapon_grip" in refine["flags"]:
                lims.append(limitation("GRIP_POSITION_ONLY", "양손 파지는 손목 위치만 맞춘다(2차 생성 end-effector — 손잡이 축 = 1차 두 손목 방향, 간격 = 계획이 정한 생성 간격 또는 주 손 너클 폭 + 1 cm). 손 회전은 "
                                       "1차 손목 굽힘을 지킬 뿐 두 손을 손잡이에 나란히 맞추지 않는다(양손 방향 차 ≈ 1차 수준) — 손 방향 · 손가락 · 무기 소켓은 "
                                       "8-4, FK 리타깃은 양손 상대 위치를 보존하지 않는다(대상 측정은 select 단계)", "provider",
                                       constraint="two_hand_weapon_grip"))
            if spacing and grip_rule:
                m = spacing["map"]
                lims.append(limitation("GRIP_SPACING_MAPPED", f"자루 무기 간격을 두 골격 기준 포즈 치수로 바꿨다 — 생성 {spacing['source_cm']:g} cm ↔ 대상 "
                                       f"{spacing['target_cm']:g} cm(대상 = {m['target_shoulder_cm']:g} + {m['arm_ratio']:g} × (생성 − {m['source_shoulder_cm']:g}): "
                                       "어깨 관절은 그 폭대로, 팔 부분은 팔 길이 비 — 파지선이 어깨선과 나란하다는 근사, 2026-10-26 기록 오차 ≤ 1 cm · 파지선이 세로에 "
                                       f"가까우면 대상 간격이 몇 cm 넓게 나온다). 파지 띠: 생성 {spacing['source_band_cm']} · 대상 {spacing['target_band_cm']} cm — 대상 "
                                       "간격은 select 가 리타깃 결과에서 직접 잰다", "provider", constraint="two_hand_weapon_grip",
                                       source_cm=spacing["source_cm"], target_cm=spacing["target_cm"]))
        lims.append(limitation("SELECTED_BY_NUMBERS", f"후보 {len(seeds)}개 중 하나를 수치(양손 간격 · 발 간격 · 휘두름 정점 · 궤적 폭 · 관통 · 깨짐 · 팔 꼬임 · 손-머리 근접)로 골랐다 — "
                               "시각 판정이 아니다. Persona 에서 보고 판정한다(Job selection 에 근거)", "provider", candidates=len(seeds)))

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
        candidates = "seeds" in inputs
        if candidates:
            # Phase 8-1 — seed 후보 · 2차 생성(한 실행 · 모델 1회 적재)
            args.update(candidates_mode=True, seeds=inputs["seeds"], refine=inputs["refine"], metric_window=inputs["metric_window"])
        args_path.write_text(json.dumps(args, ensure_ascii=False, indent=1), encoding="utf-8")
        cmd = [str(python), "-I", str(RUNNER), str(args_path)]
        env = child_env({**_OFFLINE_ENV, "HF_HUB_CACHE": str(cache)})
        handle = self.start(cmd, out_dir, log, ctx.policy, env, extra_timeout_s=inputs.get("timeout_extra_s", 0.0), report=report.as_posix(),
                            args=args_path.as_posix(), pick=inputs["pick"], samples=len(inputs["seeds"]) if candidates else inputs["samples"],
                            frames=inputs["frames"], postprocess=inputs["postprocess"], candidates=candidates,
                            refine_flags=(inputs.get("refine") or {}).get("flags") if candidates and inputs["refine"]["passes"] == 2 else [])
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
        if handle.get("candidates"):
            return self._candidates_result(report, samples, handle)
        picked = samples[handle["pick"]]
        diagnostics = [diag("info", "KIMODO_GENERATED", f"{len(samples)} sample(s) in {report.get('seconds', {}).get('total')}s on "
                            f"{(report.get('device') or {}).get('gpu') or 'CPU'} — using sample {handle['pick']}: {picked['bvh']}",
                            files=[{k: s[k] for k in ("index", "bvh", "npz")} for s in samples])]
        diagnostics += [diag("warning", w["code"], w["message"]) for w in report.get("warnings", [])]
        root = picked.get("root") or {}
        generated = {"model": report.get("model"), "samples": [{k: s.get(k) for k in ("index", "bvh", "npz", "frames", "root")} for s in samples],
                     "pick": handle["pick"], "seconds": report.get("seconds"), "postprocess": report.get("postprocess"), "root": root}
        return StepResult(values={"file": picked["bvh"], "generated": generated}, diagnostics=diagnostics)

    def _candidates_result(self, report: dict, samples: list[dict], handle: dict) -> StepResult:
        """seed 후보(Phase 8-1) — 모든 후보 BVH 를 다음 단계(blender 한 실행으로 변환 → select)로. 소스 수치 · 제약 추종은 generated.candidates 에."""
        flags = handle.get("refine_flags") or []
        diagnostics = [diag("info", "KIMODO_GENERATED", f"{len(samples)} candidate(s) (seeds {[s['seed'] for s in samples]}) in "
                            f"{report.get('seconds', {}).get('total')}s on {(report.get('device') or {}).get('gpu') or 'CPU'}"
                            f"{' — two passes each (refine ' + ', '.join(flags) + ')' if flags else ''}",
                            files=[{k: s.get(k) for k in ("index", "seed", "bvh", "npz", "pass1_npz")} for s in samples])]
        diagnostics += [diag("warning", w["code"], w["message"]) for w in report.get("warnings", [])]
        cands = []
        for s in samples:
            metrics = s.get("metrics") or {}
            refine = s.get("refine") or {}
            follow = refine.get("follow") or {}
            entry = {k: s.get(k) for k in ("index", "seed", "bvh", "npz", "pass1_npz", "frames", "root")}
            entry["source_metrics"] = metrics
            if refine:
                entry["refine"] = {"constraints": refine.get("constraints"), "fk_check_m": refine.get("fk_check_m"), "follow": follow, "smooth": refine.get("smooth"),
                                   "grip": {k: v for k, v in (refine.get("grip") or {}).items() if k not in ("frames", "targets")} or None,
                                   "foot": {side: {"keyframes": len(v.get("frames") or []), "contact_pct": v.get("contact_pct")}
                                            for side, v in (refine.get("foot") or {}).items()} or None}
                grip1, grip2 = ((metrics.get("pass1") or {}).get("grip") or {}), ((metrics.get("pass2") or {}).get("grip") or {})
                if refine.get("grip"):
                    diagnostics.append(diag("info", "REFINE_GRIP", f"seed {s['seed']}: source wrist gap p50 {(grip1.get('gap_cm') or {}).get('p50')} → "
                                            f"{(grip2.get('gap_cm') or {}).get('p50')} cm, grip frames {grip1.get('grip_pct')} → {grip2.get('grip_pct')}% "
                                            f"(target {refine['grip'].get('target')}, spacing {refine['grip'].get('spacing_cm')} cm, wrist target error "
                                            f"{follow.get('grip_target_error_cm')})"))
                if refine.get("foot"):
                    diagnostics.append(diag("info", "FOOT_CONTACT_CONSTRAINED", f"seed {s['seed']}: pass-1 contact feet held — left "
                                            f"{follow.get('foot_hold_left_cm')} · right {follow.get('foot_hold_right_cm')} cm from pass 1"))
            cands.append(entry)
        generated = {"model": report.get("model"), "samples": [{k: s.get(k) for k in ("index", "bvh", "npz", "frames", "root")} for s in samples],
                     "pick": 0, "seconds": report.get("seconds"), "postprocess": report.get("postprocess"), "root": samples[0].get("root") or {},
                     "candidates": cands, "refine_flags": flags}
        files = [{k: s.get(k) for k in ("index", "seed", "bvh", "npz")} for s in samples]
        return StepResult(values={"file": samples[0]["bvh"], "candidate_files": files, "generated": generated}, diagnostics=diagnostics)
