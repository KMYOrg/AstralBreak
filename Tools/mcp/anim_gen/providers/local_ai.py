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

from .. import body_model as bm, motion_metrics, segments, weapon as weapon_mod
from ..soma import SOMA_ARMS, SOMA_CHAINS, SOMA_FEET, SOMA_PELVIS, retarget_defaults  # noqa: F401 — 다시 내보냄(통합 테스트 · pytest)
from ..envelope import AnimGenError, diag, limitation
from ..local_ai import constraints as kc
from ..local_ai import refine as kr
from . import key_pose as key_pose_step
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
# 확산 한 번 더 할 때마다 기한에 더하는 초 — 스파이크(2026-10-26, 에디터 띄운 채) 확산 + 후처리 20 ~ 27초
DIFFUSION_EXTRA_S = 25.0
# Phase 9-3b — 키 2차의 자유 손 고정 창(pass1 키 프레임 ± 프레임, 0.5초 @ 30 fps). E0: 키가 키운 자유 손목 비틀기는 키 10 프레임 앞(0.86초)
HOLD_WINDOW_FRAMES = 15
_RAW_MAX_BYTES = 8 << 20
_OFFLINE_ENV = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "LOCAL_CACHE": "true", "HF_HUB_DISABLE_TELEMETRY": "1",
                "GRADIO_ANALYTICS_ENABLED": "False", "TEXT_ENCODER_MODE": "local", "TEXT_ENCODER_DEVICE": "cpu", "TRANSFORMERS_VERBOSITY": "error"}


def repo_ref(cache: pathlib.Path, repo: str) -> pathlib.Path:
    return cache / ("models--" + repo.replace("/", "--")) / "refs" / "main"


class KimodoProvider(SubprocessProvider):
    label = "Kimodo"
    exit_prefix = "KIMODO"
    takes_segments = True   # Phase 9-2 — 요청 segments 를 받는 Provider(라우터가 나머지를 SEGMENTS_UNSUPPORTED 로 뺀다)

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
        segs = request.get("segments")
        if not prompt and not segs:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "MISSING_INPUT", "local_ai needs request.prompt — the English text the model reads "
                              "(description is only recorded)", missing=["prompt"])
        gen = request["generation"]
        duration = request["duration_seconds"] or DEFAULT_DURATION_S
        # 길이 = (프레임 − 1) / fps 가 요청 길이가 되게 한 프레임 더 만든다(최대 300)
        frames = min(int(round(duration * FPS)) + 1, MAX_FRAMES)
        seg_plan = None
        mixed = None
        if segs and segments.is_mixed(segs):
            # Phase 9-3c — 기존 애셋 구간을 섞은 세그먼트: Kimodo 는 생성 덩어리만(기존 이웃 쪽은 겹침 K 프레임만큼 늘린다), 잇기는 join 단계
            mixed = self._plan_mixed(request, segs, pctx)
            segs = [segs[i] for i in mixed["layout"]["generated"]]
            seg_plan = segments.mixed_frames([s["duration_seconds"] for s in segs], mixed["layout"]["lead"] is not None,
                                             mixed["layout"]["trail"] is not None, mixed["overlap_frames"], FPS)
            frames = seg_plan["total_frames"]
            duration = seg_plan["length_s"]
            if frames > MAX_FRAMES:
                raise PlanBlocked("UNSUPPORTED_REQUEST", "DURATION_OVER_MAX", f"the generated segments make {frames} frames with the seam overlaps — "
                                  f"Kimodo makes up to {MAX_FRAMES} ({(MAX_FRAMES - 1) / FPS:.3f}s at {FPS:g} fps)")
        elif segs:
            # Phase 9-2 — 세그먼트마다 round(길이 × fps), 마지막만 + 1 → 합 = 이은 클립 프레임(Kimodo _multiprompt). 자르지 않고 넘으면 막는다
            seg_plan = segments.plan_frames([s["duration_seconds"] for s in segs], FPS)
            frames = seg_plan["total_frames"]
            duration = seg_plan["length_s"]
            if frames > MAX_FRAMES:
                raise PlanBlocked("UNSUPPORTED_REQUEST", "DURATION_OVER_MAX", f"segments make {frames} frames — Kimodo makes up to {MAX_FRAMES} "
                                  f"({(MAX_FRAMES - 1) / FPS:.3f}s at {FPS:g} fps)")
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
            if mixed and mixed["seam_keys"]:
                # Phase 9-3c — 이음매 자동 키(앞 이웃 끝 → 프레임 0 ~ K origin · 뒤 이웃 첫 → 끝 K + 1 프레임 pass1) — key_pose 단계가 역리타깃한다
                auto = segments.seam_key_constraints(mixed["neighbours"]["lead"], mixed["neighbours"]["trail"], frames, mixed["overlap_frames"], FPS)
                for c, spec in zip(auto, kc.convert(auto, FPS, frames)):
                    specs.append({**spec, "source": c["source"], "seam": True})
        except kc.ConstraintError as err:
            raise PlanBlocked("UNSUPPORTED_REQUEST", err.reason, err.message, **err.details) from None
        # Phase 9-3 — 대상 애셋 키 포즈: 생성 앞 key_pose 단계(역리타깃 → 제약 파일). pass1 배치면 같은 seed 로 한 번 더 만든다
        key_specs = [s for s in specs if s["kind"] == "key_pose"]
        key_step = None
        if key_specs:
            key_step, key_risks, key_lims = key_pose_step.plan(request, key_specs, pctx, python)
            if any(s["placement"] == "pass1" for s in key_specs) and gen["samples"] > 1:
                raise PlanBlocked("UNSUPPORTED_REQUEST", "KEY_POSE_WITH_SAMPLES", "key poses placed on pass 1 regenerate the same seed (one sample) — "
                                  "use generation.candidates instead of samples, or placement origin")
        seed = gen["seed"]
        if seed is None:
            seed = secrets.randbelow(2 ** 31)
            pctx.diagnostics.append(diag("info", "SEED_PINNED", f"generation.seed not given — {seed} pinned so the plan reruns the same motion"))
        if not request["duration_seconds"] and not mixed:
            pctx.diagnostics.append(diag("info", "DURATION_DEFAULTED", f"duration_seconds not given — {DEFAULT_DURATION_S:g}s (Kimodo default)"))
        risks = ["TEXT_ENCODER_CPU"]  # Llama 3 8B 인코더를 CPU 로 — 한 건 약 35초, RAM 약 15 GB (스파이크)
        if pctx.settings is None and files:
            risks.append("IMPORT_ROOTS_UNCHECKED")
        lims = [limitation("FINGERS_STATIC", "Kimodo 는 손가락 없는 30관절로 생성한다 — SOMA77 손은 고정 포즈(relaxed hands)라 결과 손가락도 "
                           "그 포즈를 따른다(손 체인 매핑)", "provider")]
        # Phase 8-1 — 플래그 → 2차 생성 제약 · seed 후보
        spacing, bones = self._grip_spacing(request, pctx)
        handle = self._grip_handle(request, pctx, spacing)
        try:
            refine = kr.plan(request["constraints"], gen["refine"], frames=frames, fps=FPS,
                             requested_root=any(c["type"] == "root_path" for c in gen["constraints"]), spacing=spacing, handle=handle)
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
        if seg_plan:
            self._plan_segments(inputs, segs, seg_plan, gen["transition_frames"], lims)
        if mixed:
            inputs["mixed"] = self._mixed_inputs(mixed, seg_plan, lims)
        if handle:
            # Phase 9-3b — 생성 파지 규칙(운영 부착 자루)의 손 방향 대응을 생성 앞에서 잰다(key_pose 단계가 있으면 그 단계에, 없으면 hand_basis 단계)
            key_step, basis_lims = key_pose_step.plan_hand_basis(request, key_step, pctx, python, handle["bone"])
            lims += basis_lims
        if key_specs:
            inputs["key_pose"] = self._plan_key_pose(inputs, key_specs, seg_plan, refine)
            risks += key_risks
            lims += key_lims
            hold = inputs["key_pose"].get("hold_free_hands")
            if hold:
                lims.append(limitation("KEY_POSE_HANDS_HELD", f"키가 묶지 않은 손 {hold['hands']} 을 2차에서 1차(같은 seed · 키 없이) 손 위치 · 회전에 "
                                       f"{hold['keyframe_step']} 프레임마다 묶었다 — 키가 자유 팔을 1차보다 더 비틀지 않게(9-3b E0: 왼손목 비틀기 −105 → −128°). "
                                       "1차부터 있던 자세는 그대로 남는다", "provider", hands=hold["hands"]))
        step = {"step": "generate", "provider": self.name, "tool": "kimodo_run.py (Kimodo venv)", "inputs": inputs,
                "output": "bvh", "bvh": dict(BVH_EXPECTED, frames=frames),
                "retarget_defaults": retarget_defaults(),
                "risks": risks, "expected_limitations": lims, "measured": {"length": round((frames - 1) / FPS, 4), "frame_rate": FPS}}
        if key_step:
            step["pre_steps"] = [key_step]   # 라우터가 생성 앞에 둔다
        if gen["candidates"] > 1 or refine["passes"] == 2:
            self._plan_candidates(step, request, refine, pctx, spacing, bones)
        return step

    @staticmethod
    def _plan_key_pose(inputs: dict, key_specs: list[dict], seg_plan: dict | None, refine: dict) -> dict:
        """Phase 9-3 — 계획에 키 포즈 항목(생성 프레임 · 배치)과 패스 수. pass1 배치가 있으면 1차(키 없이) 뒤 같은 seed 2차 — 확산 한 번(× 세그먼트)
        만큼 기한을 늘린다(후보 계획이 있으면 그쪽이 다시 센다). 9-3b — 그 2차에서 키 · 파지가 묶지 않은 손(hold_free_hands)은 1차 손에 묶는다:
        전신 키가 있으면(모든 손을 묶는다) · 양손 파지 2차가 손을 맡으면 없다."""
        pass1 = [s["source"] for s in key_specs if s["placement"] == "pass1"]
        # 키 둘레 떨림(확산 쪽 키 조건 — 8-1 수정안 A 와 같은 원인, 9-3 실측: 성긴 전신 키 3개에서 Vesper 손 속도 톱니) → 최종 출력에 같은 σ 스무딩
        # (사용자 결정 2026-11-01). 파지 · 발 2차가 이미 스무딩하면 한 번만
        out = {"from_step": "key_pose", "passes": 2 if pass1 else 1, "pass1_items": pass1, "smooth_sigma_frames": kr.SMOOTH_SIGMA_FRAMES,
               "items": [{"source": s["source"], "asset": s["asset"], "part": s["part"], "frames": s["frame_indices"], "placement": s["placement"]}
                         for s in key_specs]}
        parts = {s["part"] for s in key_specs}
        grip = any(r["flag"] == "two_hand_weapon_grip" for r in refine["rules"])
        hold = [h for h in ("left_hand", "right_hand") if h not in parts] if pass1 and "full" not in parts and not grip else []
        if hold:
            # 키 둘레만(± HOLD_WINDOW_FRAMES) — 클립 전체를 묶으면 키 뒤 동작까지 1차로 끌려 바뀐다(9-3b 실측)
            out["hold_free_hands"] = {"hands": hold, "keyframe_step": refine["keyframe_step"], "window_frames": HOLD_WINDOW_FRAMES,
                                      "around_frames": sorted({f for s in key_specs if s["placement"] == "pass1" for f in s["frame_indices"]}),
                                      "target": "pass-1 hand (position + rotation, general end-effector) — the keys do not twist a free arm further"}
        if pass1:
            inputs["timeout_extra_s"] = inputs.get("timeout_extra_s", 0.0) + DIFFUSION_EXTRA_S * max(1, len((seg_plan or {}).get("frames") or []))
        return out

    @staticmethod
    def _plan_segments(inputs: dict, segs: list[dict], seg_plan: dict, transition: int, lims: list[dict]) -> None:
        """Phase 9-2 — 계획에 세그먼트(프롬프트 · 프레임 · 생성 타임라인 시작 · 끝) · 전이 프레임 · 경계 시각 · swing 창(fix.timing 정점 탐색)."""
        inputs.update(prompt=None, transition_frames=transition, boundaries_s=seg_plan["boundaries_s"],
                      segments=[{"index": i, "name": s["name"], "prompt": s["prompt"], "duration_seconds": s["duration_seconds"], "frames": n,
                                 "start_frame": f0, "start_s": a, "end_s": b, "swing": s["swing"]}
                                for i, (s, n, f0, a, b) in enumerate(zip(segs, seg_plan["frames"], seg_plan["start_frame"], seg_plan["starts_s"],
                                                                         seg_plan["ends_s"]))],
                      swing_window_s=segments.swing_window(segs, seg_plan["starts_s"], seg_plan["ends_s"], transition, FPS),
                      timeout_extra_s=DIFFUSION_EXTRA_S * (len(segs) - 1))   # 세그먼트마다 확산 한 번 — 후보 계획이 있으면 그쪽이 덮는다
        if len(segs) < 2:
            return   # 9-3c — 섞은 세그먼트의 생성 덩어리가 하나면 Kimodo 안 전이가 없다
        lims.append(limitation("SEGMENT_TRANSITIONS", f"세그먼트 {len(segs)}개를 한 Kimodo 실행으로 이었다 — 둘째부터 처음 {transition} 프레임"
                               f"({transition / FPS:.2f}초)에 앞 세그먼트 끝 자세(전신 + 손발)를 제약으로 걸어 다시 만든다. 경계 {seg_plan['boundaries_s']}초. "
                               "분해했다고 연결이 자연스럽다는 보장은 없다 — 이음매 수치(Job segments)와 사람 판정으로 본다", "provider",
                               boundaries_s=seg_plan["boundaries_s"], transition_frames=transition))

    @staticmethod
    def _plan_mixed(request: dict, segs: list[dict], pctx: PlanContext) -> dict:
        """Phase 9-3c — 기존 세그먼트를 계획 때 잰다(대상 스켈레톤 · fps · 길이 → 구간 고정). 생성 덩어리 앞 · 뒤 이웃은 이음매 자동 키의 원천."""
        if not pctx.editor_ok:
            raise PlanBlocked("PROVIDER_UNAVAILABLE", "EDITOR", "segments with existing clips read those clips (skeleton · length · fps) when planning — "
                              "plan again with the editor running")
        target = request["target_skeleton"]
        overlap = segments.overlap_frames(request["generation"]["transition_frames"])
        lay = segments.layout(segs)
        pieces, cache = [], {}
        for k, s in enumerate(segs):
            if s["source"] == "generate":
                if k == lay["generated"][0]:
                    pieces.append({"source": "generated", "segments": [segs[i]["name"] for i in lay["generated"]], "indices": lay["generated"]})
                continue
            where = f"segments[{k}]"
            info = cache.get(s["asset"]) or key_pose_step._source_info(pctx.editor, s["asset"], where)
            cache[s["asset"]] = info
            if info["skeleton"] and info["skeleton"] != target:
                raise PlanBlocked("UNSUPPORTED_REQUEST", "SAMPLE_SKELETON_MISMATCH", f"{where}.asset is on {info['skeleton']} — existing segments must be on "
                                  f"the target skeleton {target} (retarget them first)", skeleton=info["skeleton"])
            length = float(info["length"] or (info["frames"] - 1) / info["frame_rate"])
            end = length if s["end"] is None else s["end"]
            if end > length + 0.5 / info["frame_rate"] or s["start"] >= end:
                raise PlanBlocked("UNSUPPORTED_REQUEST", "CONSTRAINT_OUT_OF_RANGE", f"{where}: range {s['start']:g} ~ {end:g}s is outside "
                                  f"{s['asset'].rsplit('/', 1)[-1]} (0 ~ {length:g}s)", length=length)
            end = min(end, length)
            if end - s["start"] < overlap / FPS + 1.0 / info["frame_rate"] - 1e-9:
                raise PlanBlocked("UNSUPPORTED_REQUEST", "DURATION_TOO_SHORT", f"{where}: {end - s['start']:g}s is shorter than the seam overlap "
                                  f"({overlap} frames at {FPS:g} fps)")
            pieces.append({"source": "existing", "index": k, "name": s["name"], "asset": s["asset"], "start": round(s["start"], 6), "end": round(end, 6),
                           "length_s": round(end - s["start"], 4), "frame_rate": info["frame_rate"], "asset_length_s": round(length, 4)})
        by_index = {p.get("index"): p for p in pieces if p["source"] == "existing"}
        neighbours = {side: ({k: by_index[i][k] for k in ("index", "asset", "start", "end")} if i is not None else None)
                      for side, i in (("lead", lay["lead"]), ("trail", lay["trail"]))}
        return {"layout": lay, "overlap_frames": overlap, "seam_keys": request["generation"]["seam_keys"], "pieces": pieces, "neighbours": neighbours,
                "names": [s["name"] for s in segs]}

    @staticmethod
    def _mixed_inputs(mixed: dict, seg_plan: dict, lims: list[dict]) -> dict:
        """계획에 섞은 세그먼트(조각 · 겹침 · 생성 덩어리 프레임 · 자동 키) — join · seams 단계가 이것을 읽는다."""
        lay, overlap = mixed["layout"], mixed["overlap_frames"]
        gen = next(p for p in mixed["pieces"] if p["source"] == "generated")
        gen.update(frames=seg_plan["total_frames"], length_s=seg_plan["length_s"], lead_overlap_frames=overlap if lay["lead"] is not None else 0,
                   trail_overlap_frames=overlap if lay["trail"] is not None else 0)
        joined = sum(p["length_s"] for p in mixed["pieces"]) - (len(mixed["pieces"]) - 1) * overlap / FPS
        out = {"names": mixed["names"], "pieces": mixed["pieces"], "overlap_frames": overlap, "blend_s": round(overlap / FPS, 6), "gen_fps": FPS,
               "seam_keys": mixed["seam_keys"], "lead": lay["lead"], "trail": lay["trail"], "joined_length_s": round(joined, 4), "align": "pelvis"}
        seams = [n for n in (lay["lead"], lay["trail"]) if n is not None]
        lims.append(limitation("SEGMENTS_JOINED", f"기존 세그먼트 {[mixed['names'][i] for i in seams]} 와 생성 덩어리를 join 단계가 잇는다 — 이음매마다 {overlap} "
                               f"프레임({overlap / FPS:.3f}초)을 겹쳐 크로스페이드, 붙는 조각은 골반 수평 위치 · 몸 방향(엉덩 관절 선)으로 맞춘다(루트 본이 아니라 — 운영 "
                               "애니 루트는 골반과 1.7 ~ 19 cm 떨어진다, 9-3c E0). " + (
                                   f"이음매 자세는 이웃의 끝 · 첫 {overlap + 1} 프레임을 생성 전신 키로 줬다(앞 origin · 뒤 pass1 — key_pose 단계 역리타깃)" if mixed["seam_keys"]
                                   else "seam_keys false — 이음매 키 없이 크로스페이드만(대조)") + ". 보정(fix.timing · fix.body · select)은 생성 부분만, 기존 이웃 쪽 "
                               "끝은 시간 보정 정지 트림을 하지 않는다", "provider", overlap_frames=overlap, seam_keys=mixed["seam_keys"]))
        return out

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

    @staticmethod
    def _grip_handle(request: dict, pctx: PlanContext, spacing: dict | None) -> dict | None:
        """Phase 9-3b — generation.refine.grip.handle weapon(사용자 결정 ③): 요청 weapon 의 운영 부착 자루를 부착 본(대상 주 손) 공간 cm 로 — 자루 방향 ·
        손목에서 가장 가까운 자루 점(anchor) · 자루 범위(anchor 기준 선 좌표). 무기 · 대상 메시는 select 기록과 같은 풀이(RetargetPipe.select_hands —
        weapon.resolve). 생성 손(SOMA)으로의 대응은 실행 때 hand_basis 단계가, 체형 비(SOMA → 대상 팔 길이)는 간격 사상(gap_map)이 준다. handle 이
        없거나 wrist_line 이면 None(지금 규칙 그대로 — 계획 비트 같음)."""
        g = request["generation"]["refine"]["grip"]
        if g.get("handle", "wrist_line") != "weapon":
            return None
        field = "generation.refine.grip.handle"
        weapon = request.get("weapon")
        off = weapon_mod.off_grip(weapon)
        if off is None or off.get("runtime_ik"):
            raise PlanBlocked("UNSUPPORTED_REQUEST", "GRIP_HANDLE_NEEDS_WEAPON", f"{field} weapon follows the request weapon's attached handle — give "
                              "weapon{mesh, attach, grips[{hand: the support hand, segment | socket}]}")
        if request["generation"]["refine"]["mode"] == "off" or not (request["constraints"] or {}).get("two_hand_weapon_grip"):
            raise PlanBlocked("UNSUPPORTED_REQUEST", "GRIP_HANDLE_NEEDS_GRIP", f"{field} weapon shapes the two-hand grip pass — set "
                              "constraints.two_hand_weapon_grip (generation.refine.mode auto)")
        if spacing is None:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "GRIP_HANDLE_NEEDS_SPACING", f"{field} weapon puts the support palm on the handle at the grip gap — give "
                              "generation.refine.grip.target_spacing_cm (or spacing_cm)")
        if weapon["lead_hand"] != g["lead_hand"]:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "CONFLICTING_FIELDS", f"weapon.lead_hand {weapon['lead_hand']} differs from generation.refine.grip.lead_hand "
                              f"{g['lead_hand']} — the weapon hangs on the lead hand")
        if not pctx.editor_ok:
            raise PlanBlocked("PROVIDER_UNAVAILABLE", "EDITOR", f"{field} weapon reads the weapon and target meshes when planning — plan again with the editor running")
        diags: list[dict] = []
        _, resolved = RetargetPipe.select_hands(pctx.editor, request, request["target_mesh"], diags)
        if not resolved:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "HANDLE_NOT_MEASURED", f"{field}: " + ("; ".join(d["message"] for d in diags) or "no handle line"))
        ratio = spacing["map"]["arm_ratio"]
        x = tuple(tuple(v) for v in resolved["local"])
        h = resolved["handle"]
        p = bm.transform_point(x, h["point"])
        d = bm._sub(bm.transform_point(x, bm._add(h["point"], h["dir"])), p)
        d = bm._scale(d, 1.0 / bm._norm(d))
        t0 = bm._dot(p, d)
        anchor = bm._sub(p, bm._scale(d, t0))   # 부착 본 원점(손목)에서 가장 가까운 자루 점
        lo, hi = h["extent_cm"]
        return {"from": "weapon", "mesh": resolved["mesh"], "bone": resolved["bone"], "lead": resolved["lead"], "dir_bone": [round(v, 6) for v in d],
                "anchor_bone_cm": [round(v, 3) for v in anchor], "extent_cm": [round(t0 + lo, 2), round(t0 + hi, 2)], "arm_ratio": round(ratio, 5),
                "wrist_cap_deg": kr.HANDLE_WRIST_CAP_DEG, "basis": "measured at run (hand_basis — the attach bone with SOMA in its T pose)"}

    def _plan_candidates(self, step: dict, request: dict, refine: dict, pctx: PlanContext, spacing: dict | None = None, bones: dict | None = None) -> None:
        """seed 후보 · 2차 생성 — 계획에 seed 목록 · 규칙 · 기한을 보이고, 라우터에 select 단계와 처리한 플래그를 알린다(모델을 띄우지 않는다).
        spacing · bones = _grip_spacing 결과 — select 가 같은 대상 띠 · 측정 본을 쓴다(대상을 다시 재지 않는다)."""
        gen, inputs = request["generation"], step["inputs"]
        seeds = [inputs["seed"] + i for i in range(gen["candidates"])]
        # Phase 9-2 — 세그먼트마다 확산을 따로 돈다(Kimodo _multiprompt). 9-3 — pass1 배치 키는 파지 · 발 2차가 없어도 2 패스
        passes = max(refine["passes"], (inputs.get("key_pose") or {}).get("passes", 1))
        diffusions = len(seeds) * passes * max(1, len(inputs.get("segments") or []))
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
            refine = inputs["refine"]
            if any(r.get("handle") for r in refine["rules"]):
                # Phase 9-3b — 운영 부착 자루 규칙: 앞 hand_basis(또는 key_pose) 단계가 잰 손 방향 대응을 규칙에 싣는다
                basis = ctx.values.get("hand_basis")
                if not basis or not basis.get("rotation"):
                    raise StepFailed("GENERATION_FAILED", "HAND_BASIS_MISSING", "the grip handle rule needs the hand basis the hand_basis step measures", fatal=True)
                refine = {**refine, "rules": [{**r, "handle": {**r["handle"], "basis": basis}} if r.get("handle") else r for r in refine["rules"]]}
            args.update(candidates_mode=True, seeds=inputs["seeds"], refine=refine, metric_window=inputs["metric_window"])
        if inputs.get("segments"):
            # Phase 9-2 — 프롬프트 · 프레임 목록(Kimodo multi_prompt) · 전이 프레임 · 경계(소스 이음매 수치)
            args.update(prompts=[s["prompt"] for s in inputs["segments"]], segment_frames=[s["frames"] for s in inputs["segments"]],
                        transition_frames=inputs["transition_frames"], boundaries_s=inputs["boundaries_s"])
        if inputs.get("key_pose"):
            # Phase 9-3 — 앞 key_pose 단계의 제약 파일(실행 때 생긴다 — 그 단계가 적은 SHA-256 으로 확인)
            rec = ctx.values.get("key_pose") or {}
            path = pathlib.Path(rec.get("file") or "")
            if not rec.get("file") or not path.is_file() or file_sha256(path) != rec.get("sha256"):
                raise StepFailed("GENERATION_FAILED", "KEY_POSE_FILE_MISSING", f"the key_pose step left no (or a changed) constraint file: {rec.get('file')}",
                                 fatal=True)
            args["key_pose_file"] = path.as_posix()
            args["key_pose_smooth"] = inputs["key_pose"].get("smooth_sigma_frames")
            if inputs["key_pose"].get("hold_free_hands"):
                args["key_pose_hold"] = inputs["key_pose"]["hold_free_hands"]   # 9-3b — 키 2차의 자유 손 고정
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
        if report.get("segments"):
            # Phase 9-2 — 세그먼트 실행 기록 · 샘플별 소스 이음매 수치
            generated["segments"] = report["segments"]
            for g, s in zip(generated["samples"], samples):
                g["segments"] = s.get("segments")
        if report.get("key_pose"):
            self._key_pose_result(generated, report, samples, diagnostics)
        return StepResult(values={"file": picked["bvh"], "generated": generated}, diagnostics=diagnostics)

    @staticmethod
    def _key_pose_result(generated: dict, report: dict, samples: list[dict], diagnostics: list[dict]) -> None:
        """Phase 9-3 — 키 포즈 배치 · 추종 기록(샘플 · 후보마다) + 진단 한 줄(첫 샘플)."""
        generated["key_pose"] = report["key_pose"]
        rows = generated.get("candidates") or generated["samples"]
        for g, s in zip(rows, samples):
            g["key_pose"] = s.get("key_pose")
            if s.get("pass1_npz"):
                g["pass1_npz"] = s["pass1_npz"]
        first = (samples[0].get("key_pose") or {}).get("follow") or []
        if first:
            diagnostics.append(diag("info", "KEY_POSE_FOLLOWED", "; ".join(
                f"{r.get('part', r['type'])} × {r['keys']}: position p50 {(r.get('position_cm') or {}).get('p50')} · max {(r.get('position_cm') or {}).get('max')} cm"
                + (f", rotation max {r['rotation_deg']['max']}°" if r.get("rotation_deg") else "") + f", jitter p95 {r.get('jitter_p95')}"
                for r in first) + " (sample 0)"))

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
            if s.get("segments"):
                entry["segments"] = s["segments"]   # Phase 9-2 — 소스 이음매 수치 · 세그먼트별 1차 ↔ 2차 차이
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
        if report.get("segments"):
            generated["segments"] = report["segments"]
        if report.get("key_pose"):
            self._key_pose_result(generated, report, samples, diagnostics)
        files = [{k: s.get(k) for k in ("index", "seed", "bvh", "npz")} for s in samples]
        return StepResult(values={"file": samples[0]["bvh"], "candidate_files": files, "generated": generated}, diagnostics=diagnostics)
