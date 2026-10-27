"""blender Provider — headless Blender 로 BVH → FBX (지침서 §4 · §14 Phase 4).

계획: BVH 헤더를 Python 으로 읽어(bvh.py) 단위 · 정면 회전 · 범위 · fps 를 정하고 계획에 고정한다 — Blender 를 띄우지 않는다.
실행: blender -b --factory-startup -P anim_gen/blender/bvh_to_fbx.py -- args.json 을 Popen 으로 띄우고 pending 핸들을 돌려준다
(서브프로세스 공통 — subprocess_step.py). 출력은 ini ImportSourceRoots 아래만(<첫 루트>/Blender/<job_id>/A<n>/) — 그 FBX 를
retarget 파이프의 import 단계가 받는다.

생성 Provider 의 BVH(Phase 5 local_ai): 계획 때 파일이 아직 없다 → plan_convert_generated 가 그 Provider 가 아는 값(단위 · 정면 ·
관절 수)을 '예상'으로 고정하고, 실행 때 앞 단계 결과 파일로 같은 규칙(resolve)을 돌려 다르면 진단으로 남긴다.

프레임 렌더 비교(Phase 5 review.render): 같은 Blender 실행이 FBX 를 내보낸 뒤 (시각 × 뷰) PNG 와 비교 시트 한 장을 <시도 폴더>/frames/ 에
쓴다(blender/review_render.py). 보이는 것은 변환된 소스 골격(기둥 더미 메시)이지 Vesper 가 아니다(REVIEW_IS_SOURCE_SKELETON).
렌더가 실패해도 변환은 성공이다(REVIEW_NOT_RENDERED).

보정 단계(fix.ops — Phase 8-3): 사전 · 기본값 · 순서는 anim_gen/fix_ops.py(smooth · stance_width · foot_lock), Blender 안 실행은 blender/fix_legs.py.
리타깃 전 소스 골격에서 돈다 — 발 간격은 대상 메시 기준(max_ratio)을 두 골격 다리 치수로 소스 간격에 사상한다(대상 치수는 이 단계가 잰다). 다리 본은
retarget 단계의 LeftLeg/RightLeg 체인 · source_feet 에서(파일이 계획 때 있으면 계획이, 없으면 실행이 정한다). SOMA77 BVH(저장된 Kimodo 결과)를
motion_file 로 주면 local_ai 와 같은 리타깃 기본값을 채운다 — 다시 생성하지 않고 보정만 다시 할 수 있다.
"""
from __future__ import annotations

import json
import pathlib
import re

from .. import bvh, fix_ops, soma
from ..editor import EditorCallError
from ..envelope import AnimGenError, diag, limitation
from ..fallback import from_editor_error
from ..request import MOTION_FILE_DEFAULTS
from .base import PlanBlocked, PlanContext, RunContext, StepFailed, StepResult
from .builtin import RetargetPipe
from .subprocess_step import SubprocessProvider, child_env, file_sha256, import_roots, is_under

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "blender" / "bvh_to_fbx.py"
PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[2]
FPS_SNAP = 0.05           # 120.0048 fps(Frame Time 0.008333) 같은 반올림 오차는 정수 fps 로 맞춘다
PROXY_MESH = {"min_width_cm": 0.5, "width_ratio": 0.08}
# 렌더 비교 설정 — 셀 높이 고정, 폭은 포즈 범위 비율(최대 max_aspect 배). 범위는 전 프레임(최대 bounds_max_samples 개를 고르게).
# 시트는 긴 변 sheet_max_px 안으로 줄인다(12행 × 뷰 2 + 레퍼런스 4 면 원래 4344 × 6222 · 10.7 MB — 프레임 PNG 는 원래 크기 그대로)
REVIEW_RENDER = {"cell_height_px": 512, "max_aspect": 2.0, "margin": 0.08, "bounds_max_samples": 600, "sheet_max_px": 3000}
# 보정 op 사전: 이름 → 인자 검사(계획 때 — 기본값을 채운 op 를 돌려준다, 틀리면 fix_ops.FixOpError → BAD_REQUEST). 실행은 bvh_to_fbx.apply_fixes
# (blender/fix_legs.py). Phase 8-3 — fix_ops.OPS 한 곳에서
FIX_OPS: dict = {name: fix_ops.normalize_op for name in fix_ops.OPS}
_NAME = re.compile(r"[^A-Za-z0-9_]")
_TOOL = "blender -b -P anim_gen/blender/bvh_to_fbx.py"


def fix_limitation(ops: list[dict]) -> dict:
    names = [o["op"] for o in ops]
    legs = [n for n in names if n in fix_ops.LEG_OPS]
    return limitation("FIX_ON_SOURCE_SKELETON", f"보정 {names} 은 리타깃 전 소스 골격에서 했다" + (
        " — 대상 메시의 발 위치는 다리 치수 사상(엉덩 관절 폭 · 다리 길이 비)으로 옮긴 근사다(대상 수치는 Job fix.target). 대상 쪽 정확한 접지 · 몸 관통은 8-4"
        if legs else ""), "provider", ops=names)


def review_limitation() -> dict:
    return limitation("REVIEW_IS_SOURCE_SKELETON", "프레임 렌더 비교(review.render)는 변환된 소스 골격(본마다 기둥 더미 메시)이다 — Vesper 의 모습이 "
                      "아니다. 리타깃 결과는 Persona · PIE 에서 보고, Vesper 캡처는 Phase 8", "provider")


def spread(count: int, duration: float | None) -> list[float]:
    """count 개 시각을 클립에 고르게 — 첫 · 끝 프레임 포함."""
    if count == 1 or not duration:
        return [0.0]
    return [round(i * duration / (count - 1), 4) for i in range(count)]


class BlenderProvider(SubprocessProvider):
    label = "Blender"
    exit_prefix = "BLENDER"

    @staticmethod
    def executable(policy: dict | None) -> str | None:
        return ((policy or {}).get("paths") or {}).get("blender_executable")

    def installed(self, policy: dict) -> tuple[bool, str | None]:
        exe = self.executable(policy)
        found = bool(exe) and pathlib.Path(exe).is_file()
        return found, f"blender_executable {'found' if found else 'not found'}: {exe}"

    # ---- 계획 (Blender 를 띄우지 않는다) ----
    def plan_convert(self, request: dict, pctx: PlanContext) -> dict:
        mf = request.get("motion_file")
        if not mf:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "MISSING_INPUT", "blender converts request.motion_file (a .bvh under ImportSourceRoots) — none given",
                              missing=["motion_file"])
        try:
            resolved = self.resolve(mf, request, pctx.settings, pctx.editor if pctx.editor_ok else None)
        except StepFailed as failed:
            raise PlanBlocked(failed.cause, failed.reason, failed.message, editor_error=failed.editor_error)
        risks = []
        if pctx.settings is None:
            risks.append("IMPORT_ROOTS_UNCHECKED")
        if not resolved["facing"]["resolved"]:
            risks.append("FACING_UNRESOLVED_AT_PLAN")
        if not (request["retarget"] or {}).get("source_chains"):
            # BVH 스켈레톤은 대개 템플릿과 일부만 맞는다 — 실패하면 RETARGET_FAILED(본 계층 보존) 뒤 bvh.joints 로 체인을 정해 다시 계획
            risks.append("SOURCE_CHAINS_UNVERIFIED")
        for w in resolved["bvh"]["warnings"]:
            pctx.diagnostics.append(diag("warning", w["code"], f"{pathlib.Path(resolved['file']).name}: {w['message']}"))
        rng = resolved["range"]
        if rng["trimmed_frames"]:
            pctx.diagnostics.append(diag("info", "RANGE_ALIGNED", f"last {rng['trimmed_frames']} source frame(s) dropped so the clip ends on a "
                                         f"{rng['aligned_to']:g} fps frame — keeps the source frames exact (Interchange would otherwise "
                                         "snap the length by up to half a frame, LENGTH_SNAPPED)"))
        review = self.plan_review(request, pctx.settings, rng["duration"])
        ops = self.check_fix(request, pctx.diagnostics)
        step = {"step": "convert", "provider": self.name, "tool": _TOOL, "inputs": {**mf, "review": review, "fix": {"ops": ops}},
                "resolved": resolved, "risks": risks + (["FIX_RESOLVED_AT_RUN"] if ops else []), "sample_rate": resolved["sample_rate"],
                "expected_limitations": self.limitations(resolved) + ([review_limitation()] if review else []) + ([fix_limitation(ops)] if ops else []),
                "measured": {"length": rng["duration"], "frame_rate": resolved["sample_rate"] or resolved["fps"]["output"]}}
        if soma.is_soma(j["name"] for j in resolved["bvh"]["joints"]):
            # 저장된 Kimodo 결과(SOMA77) — local_ai 와 같은 리타깃 기본값(요청이 비운 것만 라우터가 채운다 — defaults_from)
            step["retarget_defaults"] = soma.retarget_defaults()
            pctx.diagnostics.append(diag("info", "SOMA_BVH_DEFAULTS", f"{pathlib.Path(resolved['file']).name} is a SOMA77 skeleton — the retarget step "
                                         "gets local_ai's SOMA pelvis · chains · feet where the request leaves them empty"))
        return step

    def plan_convert_generated(self, request: dict, expected: dict, pctx: PlanContext | None = None) -> dict:
        """앞 단계(생성)가 만들 BVH 의 변환 — 파일이 아직 없으니 생성 Provider 가 아는 값만 '예상'으로 고정하고 실행 때 정한다.

        expected: {unit, facing, joints, fps, frames} — unit 은 motion_file.unit 으로 그대로 쓰고, 나머지는 실행 때 잰 값과 비교한다.
        """
        mf = {**MOTION_FILE_DEFAULTS, "unit": expected.get("unit", "auto")}
        rate = request["frame_rate"]
        # 생성 fps 와 같으면 리샘플하지 않는다. 다르면 실행 때 범위를 그 rate 의 경계에 맞추고 import 가 그 값으로 굽는다(값은 앞 단계 결과로)
        sample_rate = rate if rate and expected.get("fps") and abs(rate - expected["fps"]) > 0.01 else None
        frames, fps = expected.get("frames"), expected.get("fps")
        review = self.plan_review(request, pctx.settings if pctx else None, (frames - 1) / fps if frames and fps else None)
        ops = self.check_fix(request, pctx.diagnostics if pctx else None)
        step = {"step": "convert", "provider": self.name, "tool": _TOOL,
                "inputs": {**mf, "path": None, "from_step": "generate", "review": review, "fix": {"ops": ops}},
                "resolved": None, "expected": dict(expected), "risks": ["CONVERT_RESOLVED_AT_RUN"] + (["FIX_RESOLVED_AT_RUN"] if ops else []),
                "sample_rate": sample_rate}
        lims = ([review_limitation()] if review else []) + ([fix_limitation(ops)] if ops else [])
        if lims:
            step["expected_limitations"] = lims
        return step

    def plan_fix_legs(self, step: dict, retarget_inputs: dict, request: dict, pctx: PlanContext) -> None:
        """다리 op 가 있으면 다리 본(retarget 체인 · 발 — 요청 또는 기본값이 채워진 뒤)과 대상 다리 치수를 계획에 싣는다. 파일이 계획 때 없으면(생성 결과)
        본은 실행 때. 체인으로 엉덩 → 무릎 → 발목을 못 찾으면 이 후보를 막는다(FIX_LEGS_UNKNOWN)."""
        fix = step["inputs"]["fix"]
        if not any(o["op"] in fix_ops.LEG_OPS for o in fix["ops"]):
            return
        fix["legs"], fix["target_dims"] = None, None
        if step.get("resolved"):
            try:
                fix["legs"] = fix_ops.legs_from(step["resolved"]["bvh"]["joints"], retarget_inputs.get("source_chains"), retarget_inputs.get("source_feet"))
            except fix_ops.FixOpError as err:
                raise PlanBlocked("UNSUPPORTED_REQUEST", "FIX_LEGS_UNKNOWN", err.args[1]) from None
        if pctx.editor_ok:
            try:
                fix["target_dims"] = RetargetPipe.selection_bones(pctx.editor, request["target_skeleton"], pctx.diagnostics, "convert").get("leg_dims")
            except StepFailed as failed:
                raise PlanBlocked(failed.cause, failed.reason, failed.message, editor_error=failed.editor_error) from None

    def plan_review(self, request: dict, settings: dict | None, duration: float | None) -> dict | None:
        """review.render → 렌더할 시각(초, 변환된 클립 기준) · 뷰 · 레퍼런스 이미지. count 는 지금 펼쳐 보여 주고 실행 때 잰 길이로 다시 펼친다.
        이미지는 루트 · 존재만 본다(디코딩은 Blender). duration 을 모르면(계획 때 길이 미상) 시각 범위는 실행 때 Blender 가 끝 프레임으로 자른다."""
        render = (request.get("review") or {}).get("render")
        if render is None:
            return None
        times = list(render["times"]) if render["times"] is not None else spread(render["count"], duration)
        late = [t for t in times if duration is not None and t > duration + 1e-6]
        if late:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "REVIEW_TIME_OUT_OF_RANGE", f"review.render.times {late} are past the end of the converted clip "
                              f"({duration:g}s)", duration=duration)
        refs = []
        for path in map(pathlib.Path, render["reference_images"]):
            self.check_root(path, settings, "reference images")
            if not path.is_file():
                raise PlanBlocked("UNSUPPORTED_REQUEST", "FILE_NOT_FOUND", f"review.render.reference_images: no file at {path.as_posix()}")
            refs.append(path.as_posix())
        return {"times": times, "count": render["count"], "views": list(render["views"]), "reference_images": refs}

    @staticmethod
    def check_fix(request: dict, diagnostics: list[dict] | None = None) -> list[dict]:
        """fix.ops 를 op 사전으로 검사 → 기본값을 채워 정해진 순서로(smooth → 다리 풀이). 모르는 op 가 하나라도 있으면 이 후보를 막는다(무시하고 변환하지
        않는다), 인자가 틀리면 요청 오류(BAD_REQUEST)."""
        ops = (request.get("fix") or {}).get("ops") or []
        unknown = [o["op"] for o in ops if o["op"] not in FIX_OPS]
        if unknown:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "UNSUPPORTED_FIX_OP", f"fix ops {unknown} are not available — the blender fix dictionary is "
                              f"{sorted(FIX_OPS)}", ops=unknown, available=sorted(FIX_OPS))
        out = []
        for i, op in enumerate(ops):
            try:
                checked = FIX_OPS[op["op"]](op)
            except fix_ops.FixOpError as err:
                field = err.args[0].replace("fix.ops[0]", f"fix.ops[{i}]", 1)
                raise AnimGenError("BAD_REQUEST", f"request.{field}: {err.args[1]}", reason="BAD_FIELD", field=field) from None
            out.append(checked if isinstance(checked, dict) else op)
        try:
            out, moved = fix_ops.ordered(out)
        except fix_ops.FixOpError as err:
            raise AnimGenError("BAD_REQUEST", f"request.{err.args[0]}: {err.args[1]}", reason="DUPLICATE_FIX_OP", field=err.args[0]) from None
        if moved and diagnostics is not None:
            diagnostics.append(diag("info", "FIX_OPS_REORDERED", f"fix ops run as {[o['op'] for o in out]} (smooth first, then one leg solve)"))
        return out

    def resolve(self, mf: dict, request: dict, settings: dict | None, editor) -> dict:
        """BVH → 계획에 고정할 값. settings 가 없으면 루트 검사를, editor 가 없으면 대상 정면 측정을 미룬다."""
        path = pathlib.Path(mf["path"])
        if path.suffix.lower() != ".bvh":
            raise PlanBlocked("UNSUPPORTED_REQUEST", "UNSUPPORTED_FORMAT", f"blender converts .bvh — got '{path.suffix or path.name}'")
        self.check_root(path, settings)
        if not path.is_file():
            raise PlanBlocked("UNSUPPORTED_REQUEST", "FILE_NOT_FOUND", f"no file at {path.as_posix()}")
        try:
            info = bvh.read(path)
            segments = bvh.rest_segments(info, mf["axis_forward"], mf["axis_up"])
            unit = bvh.resolve_unit(mf["unit"], bvh.height(segments))
            fps = info.fps
            out_fps = float(round(fps)) if abs(fps - round(fps)) <= FPS_SNAP else round(fps, 6)
            frames = bvh.align_to_rate(bvh.frame_range(info, mf["range"]), out_fps, request["frame_rate"])
        except bvh.BvhError as err:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "BAD_MOTION_FILE", f"{path.name}: {err.message}", bvh_reason=err.reason, **err.details) from None
        # 임포트 리샘플: 프레임 경계에 맞춘 요청 rate, 맞출 수 없으면 소스 rate 그대로(FRAME_RATE_MISMATCH 는 측정값으로 남는다)
        sample_rate = None if frames["unaligned"] else request["frame_rate"]
        return {"file": path.as_posix(), "bytes": path.stat().st_size, "sha256": file_sha256(path), "bvh": bvh.summary(info), "unit": unit,
                "range": frames, "sample_rate": sample_rate, "fps": {"source": round(fps, 4), "output": out_fps, "snapped": abs(out_fps - fps) > 1e-9},
                "facing": self.facing(mf["facing"], segments, request["target_skeleton"], editor),
                "name": "BVH_" + _NAME.sub("_", path.stem)}

    @staticmethod
    def check_root(path: pathlib.Path, settings: dict | None, what: str = "the motion file") -> None:
        if settings is None:
            return
        roots = import_roots(settings)
        if not any(is_under(path, root) for root in roots):
            raise AnimGenError("IMPORT_SOURCE_NOT_ALLOWED", f"{path.as_posix()} is outside [AnimGraphMcp] ImportSourceRoots — put {what} under one",
                               reason="OUTSIDE_IMPORT_ROOTS", allowed=[r.as_posix() for r in roots])

    @staticmethod
    def facing(mode: str, segments, target_skeleton: str, editor) -> dict:
        """FK 체인 op 는 전역 회전 델타라(FKChainsOp.cpp) 소스와 대상의 정면이 다르면 동작이 다른 평면으로 휜다 → 대상 정면으로 돌린다."""
        source = bvh.facing(segments)
        out = {"mode": mode, "source": source["axis"], "source_detail": source, "target": None, "target_from": None, "rotate_z_deg": 0.0,
               "resolved": True}
        if mode == "keep":
            return out
        if mode == "auto":
            if editor is None:
                out["resolved"] = False
                return out
            try:
                bones = editor.require("inspect_skeleton", skeleton=target_skeleton, details=True)["bones"]
            except EditorCallError as err:
                raise from_editor_error("convert", err)
            target = bvh.facing(bvh.skeleton_segments(bones))
            out.update(target=target["axis"], target_from=target_skeleton, target_detail=target)
        else:
            out.update(target=mode, target_from="request")
        if out["source"] and out["target"]:
            out["rotate_z_deg"] = bvh.blender_rotation_deg(out["source"], out["target"])
        return out

    @staticmethod
    def limitations(resolved: dict) -> list[dict]:
        out = []
        unit = resolved["unit"]
        if unit["normalized"]:
            out.append(limitation("SCALE_NORMALIZED", f"BVH 단위를 알 수 없어 기준 포즈 키를 {unit['rest_height_cm']}cm 로 맞췄다(cm/단위 {unit['cm_per_unit']}) — "
                                  "리타기터가 골반 높이 비로 이동을 맞추므로 동작 크기 영향은 작다. 실제 단위를 알면 motion_file.unit 로 준다", "provider",
                                  cm_per_unit=unit["cm_per_unit"]))
        facing = resolved["facing"]
        if facing["mode"] != "keep" and facing["resolved"] and not (facing["source"] and facing["target"]):
            out.append(limitation("FACING_UNKNOWN", f"정면을 재지 못해 돌리지 않았다(소스 {facing['source']} · 대상 {facing['target']}) — 다르면 리타깃 동작이 틀어진다. "
                                  "motion_file.facing 에 대상 축을 주거나 keep", "provider", source_axis=facing["source"], target_axis=facing["target"]))
        return out

    @staticmethod
    def unexpected(resolved: dict, expected: dict) -> list[str]:
        """생성 Provider 가 예상한 값과 실행 때 잰 값의 차이 — 다르면 그 Provider 의 출력 규약이 바뀐 것이다."""
        out = []
        if expected.get("unit") not in (None, "auto") and resolved["unit"]["normalized"]:
            out.append(f"unit normalized (expected {expected['unit']})")
        if expected.get("facing") and resolved["facing"]["source"] != expected["facing"]:
            out.append(f"faces {resolved['facing']['source']} (expected {expected['facing']})")
        if expected.get("joints") and resolved["bvh"]["joint_count"] != expected["joints"]:
            out.append(f"{resolved['bvh']['joint_count']} joints (expected {expected['joints']})")
        if expected.get("fps") and abs(resolved["fps"]["output"] - expected["fps"]) > 0.01:
            out.append(f"{resolved['fps']['output']} fps (expected {expected['fps']})")
        return out

    # ---- 실행 ----
    def run(self, ctx: RunContext) -> StepResult:
        exe = self.executable(ctx.policy)
        if not exe or not pathlib.Path(exe).is_file():
            raise StepFailed("PROVIDER_UNAVAILABLE", "NOT_INSTALLED", f"blender_executable not found: {exe}")
        settings = ctx.editor.status()
        if settings is None:
            raise StepFailed("PROVIDER_UNAVAILABLE", "EDITOR", "Editor unreachable — import roots come from get_editor_status and the next steps need it",
                             fatal=True)
        mf, resolved = self._resolve_at_run(ctx, settings)
        notes = []
        if ctx.step.get("expected"):
            off = self.unexpected(resolved, ctx.step["expected"])
            if off:
                notes.append(diag("warning", "GENERATED_BVH_UNEXPECTED", f"{pathlib.Path(resolved['file']).name}: {'; '.join(off)} — converted with the measured values"))
        out_dir = import_roots(settings)[0] / "Blender" / ctx.job_id / f"A{ctx.attempt}"
        out_dir.mkdir(parents=True, exist_ok=True)
        # rest_fbx — 첫 프레임이 기준 포즈인 FBX: 스켈레톤은 이것으로 만든다(bvh_to_fbx.export_rest_fbx — 깊은 본이 있으면 Interchange 가
        # 바인드 포즈를 무효로 보고 애니 첫 프레임을 기준 포즈로 삼는다)
        paths = {name: out_dir / file for name, file in (("fbx", f"{resolved['name']}.fbx"), ("rest_fbx", f"{resolved['name']}_Rest.fbx"),
                                                          ("report", "report.json"), ("log", "blender.log"), ("args", "args.json"))}
        paths["report"].unlink(missing_ok=True)  # 같은 시도 폴더의 이전 report 가 '끝남'으로 읽히지 않게
        inputs = ctx.step["inputs"]
        args = {"bvh": resolved["file"], "fbx": paths["fbx"].as_posix(), "rest_fbx": paths["rest_fbx"].as_posix(), "report": paths["report"].as_posix(),
                "cm_per_unit": resolved["unit"]["cm_per_unit"],
                "axis_forward": mf["axis_forward"], "axis_up": mf["axis_up"], "rotate_z_deg": resolved["facing"]["rotate_z_deg"],
                "first": resolved["range"]["first"], "last": resolved["range"]["last"], "fps": resolved["fps"]["output"], "proxy_mesh": PROXY_MESH,
                "fix": list((inputs.get("fix") or {}).get("ops") or []),
                "review": self._review_args(inputs.get("review"), resolved, settings, out_dir / "frames", notes),
                "package_dir": PACKAGE_DIR.as_posix()}
        if any(o["op"] in fix_ops.LEG_OPS for o in args["fix"]):
            args["fix_legs"] = self._fix_legs(ctx, resolved, notes)
        items = self._candidate_items(ctx, resolved, args, settings, out_dir, notes) if ctx.values.get("candidate_files") else None
        if items:
            args["items"] = [{k: v for k, v in item.items() if k not in ("index", "seed")} for item in items]
        paths["args"].write_text(json.dumps(args, ensure_ascii=False, indent=1), encoding="utf-8")
        cmd = [exe, "-b", "--factory-startup", "--python-exit-code", "3", "-P", str(SCRIPT), "--", str(paths["args"])]
        handle = self.start(cmd, out_dir, paths["log"], ctx.policy, child_env(),
                            **{name: p.as_posix() for name, p in paths.items() if name != "log"},
                            resolved={k: resolved[k] for k in ("file", "sha256", "unit", "range", "fps", "facing", "name", "sample_rate")},
                            joint_count=resolved["bvh"]["joint_count"], deferred=bool(inputs.get("from_step")), notes=notes,
                            review_requested=args["review"] is not None, items=items)
        return StepResult(pending=handle)

    @staticmethod
    def _fix_legs(ctx: RunContext, resolved: dict, notes: list[dict]) -> dict:
        """다리 풀이 인자 — 계획이 정한 다리 본 · 대상 치수, 없으면 지금(retarget 단계 체인 · 발 + 지금 잰 BVH 계층, 대상 스켈레톤 기준 포즈)."""
        planned = ctx.step["inputs"].get("fix") or {}
        legs, dims = planned.get("legs"), planned.get("target_dims")
        if legs is None:
            rt = next((s["inputs"] for s in ctx.steps or [] if s["step"] == "retarget"), {})
            try:
                legs = fix_ops.legs_from(resolved["bvh"]["joints"], rt.get("source_chains"), rt.get("source_feet"))
            except fix_ops.FixOpError as err:
                raise StepFailed("UNSUPPORTED_REQUEST", "FIX_LEGS_UNKNOWN", err.args[1]) from None
        if dims is None:
            dims = RetargetPipe.selection_bones(ctx.editor, ctx.request["target_skeleton"], notes, "convert").get("leg_dims")
            if dims is None:
                notes.append(diag("warning", "FIX_TARGET_DIMS_UNKNOWN", "target leg dimensions unknown — stance_width max_ratio is read on the source skeleton"))
        return {"legs": legs, "target_dims": dims}

    def _candidate_items(self, ctx: RunContext, resolved: dict, args: dict, settings: dict, out_dir: pathlib.Path, notes: list[dict]) -> list[dict]:
        """생성 후보 BVH 여럿(Phase 8-1) → 한 Blender 실행의 items. 변환 규칙은 첫 후보로 잰 값을 같이 쓴다(같은 생성기 · 같은 프레임 수) — 관절 ·
        프레임 수가 다른 후보는 경고로 남긴다. 기준 포즈 FBX 는 첫 후보만(모두 같은 표준 T 포즈), 렌더 비교는 후보마다 frames/c<번호>/."""
        items = []
        for k, cand in enumerate(ctx.values["candidate_files"]):
            path = pathlib.Path(cand["bvh"])
            try:
                self.check_root(path, settings)
            except AnimGenError as err:
                raise StepFailed(err.code, err.reason, err.message, fatal=True) from None
            if not path.is_file():
                raise StepFailed("GENERATION_FAILED", "NO_OUTPUT", f"candidate {cand.get('index')} BVH is missing: {path.as_posix()}")
            if k:
                try:
                    info = bvh.summary(bvh.read(path))
                except bvh.BvhError as err:
                    raise StepFailed("UNSUPPORTED_REQUEST", "BAD_MOTION_FILE", f"{path.name}: {err.message}") from None
                if info["joint_count"] != resolved["bvh"]["joint_count"] or info.get("frames") != resolved["bvh"].get("frames"):
                    notes.append(diag("warning", "GENERATED_BVH_UNEXPECTED", f"{path.name}: {info['joint_count']} joints · {info.get('frames')} frames — "
                                      f"candidate 0 has {resolved['bvh']['joint_count']} · {resolved['bvh'].get('frames')}; converted with candidate 0's values"))
            name = "BVH_" + _NAME.sub("_", path.stem)
            review = None
            if args["review"]:
                review = {**args["review"], "dir": (out_dir / "frames" / f"c{cand.get('index', k):02d}").as_posix()}
            items.append({"index": cand.get("index", k), "seed": cand.get("seed"), "bvh": path.as_posix(), "fbx": (out_dir / f"{name}.fbx").as_posix(),
                          "rest_fbx": (out_dir / f"{name}_Rest.fbx").as_posix() if k == 0 else None, "review": review})
        return items

    def _review_args(self, review: dict | None, resolved: dict, settings: dict, frames_dir: pathlib.Path, notes: list[dict]) -> dict | None:
        """계획의 review → Blender 인자. count 는 지금 잰 길이로 다시 펼친다(생성 BVH 는 계획 때 길이가 예상값). 계획 뒤 사라진 레퍼런스는 빼고 알린다."""
        if not review:
            return None
        times = review["times"] if review.get("count") is None else spread(review["count"], resolved["range"]["duration"])
        refs = []
        for path in map(pathlib.Path, review["reference_images"]):
            try:
                self.check_root(path, settings, "reference images")
            except AnimGenError as err:
                raise StepFailed(err.code, err.reason, err.message, fatal=True) from None
            if path.is_file():
                refs.append(path.as_posix())
            else:
                notes.append(diag("warning", "REVIEW_REFERENCE_MISSING", f"{path.as_posix()} is gone since planning — left out of the sheet"))
        return {"times": times, "views": review["views"], "reference_images": refs, "dir": frames_dir.as_posix(), **REVIEW_RENDER}

    def _resolve_at_run(self, ctx: RunContext, settings: dict) -> tuple[dict, dict]:
        """계획 값을 그대로 쓰되, 파일이 바뀌었으면 멈춘다. 계획 때 에디터가 없어 못 정한 값(루트 · 대상 정면)과
        생성 결과 파일(from_step — 앞 단계 values.file)은 지금 정한다."""
        inputs = ctx.step["inputs"]
        planned = ctx.step.get("resolved")
        if inputs.get("from_step"):
            mf = {**{k: inputs[k] for k in MOTION_FILE_DEFAULTS if k in inputs}, "path": ctx.values.get("file")}
            if not mf["path"]:
                raise StepFailed("GENERATION_FAILED", "NO_OUTPUT", f"the {inputs['from_step']} step left no motion file to convert")
        else:
            mf = ctx.request["motion_file"]
        try:
            if planned is None or not planned["facing"]["resolved"]:
                resolved = self.resolve(mf, ctx.request, settings, ctx.editor)
            else:
                path = pathlib.Path(planned["file"])
                self.check_root(path, settings)
                if not path.is_file():
                    raise PlanBlocked("UNSUPPORTED_REQUEST", "FILE_NOT_FOUND", f"no file at {path.as_posix()}")
                resolved = dict(planned, sha256=file_sha256(path))
        except AnimGenError as err:
            raise StepFailed(err.code, err.reason, err.message, fatal=True) from None
        except PlanBlocked as blocked:
            raise StepFailed(blocked.cause, blocked.reason, blocked.message) from None
        if planned is not None and resolved["sha256"] != planned["sha256"]:
            raise StepFailed("UNSUPPORTED_REQUEST", "FILE_CHANGED", f"{planned['file']} changed after planning — plan again (what was shown is what runs)",
                             fatal=True)
        return mf, resolved

    def poll(self, ctx: RunContext, handle: dict) -> StepResult | None:
        report = self.await_report(handle)
        if report is None:
            return None
        if not report.get("ok"):
            error = report.get("error") or {}
            raise StepFailed("GENERATION_FAILED", error.get("code") or "BLENDER_FAILED", f"bvh_to_fbx: {error.get('message')}{self.tail(handle)}")
        for key in ("fbx",) + (("rest_fbx",) if report.get("rest_fbx") else ()):
            if not pathlib.Path(handle[key]).is_file():
                raise StepFailed("GENERATION_FAILED", "NO_OUTPUT", f"Blender reported success but {handle[key]} is missing{self.tail(handle)}")
        if handle.get("items"):
            return self._items_result(handle, report)
        return self._result(handle, report)

    def _items_result(self, handle: dict, report: dict) -> StepResult:
        """후보 여럿의 변환(Phase 8-1) — 첫 후보 값은 지금처럼(file · rest_file · converted · review) + candidate_fbx[] (후보별 FBX · 변환 · 렌더)."""
        items = report.get("items") or []
        if len(items) != len(handle["items"]):
            raise StepFailed("GENERATION_FAILED", "NO_OUTPUT", f"Blender converted {len(items)} of {len(handle['items'])} candidates{self.tail(handle)}")
        result = self._result(handle, {**report, "review": items[0].get("review")})
        cands = []
        for planned, item in zip(handle["items"], items):
            if not pathlib.Path(planned["fbx"]).is_file():
                raise StepFailed("GENERATION_FAILED", "NO_OUTPUT", f"Blender reported success but {planned['fbx']} is missing{self.tail(handle)}")
            values: dict = {}
            if handle.get("review_requested"):
                self._review_result(handle, item, values, [], [])
            cands.append({"index": planned["index"], "seed": planned["seed"], "fbx": planned["fbx"], "bones": item.get("bones"),
                          "frames": item.get("frames"), "seconds": item.get("seconds"), "review": values.get("review")})
        result.values["candidate_fbx"] = cands
        result.diagnostics.append(diag("info", "BLENDER_CANDIDATES_CONVERTED", f"{len(cands)} candidate BVH → FBX in one Blender run "
                                       f"({report.get('seconds')}s)", files=[c["fbx"] for c in cands]))
        return result

    def _result(self, handle: dict, report: dict) -> StepResult:
        resolved = handle["resolved"]
        converted = {k: report.get(k) for k in ("blender", "bones", "roots", "rest_height_cm", "ground_lift_cm", "rotate_z_deg", "frames",
                                                 "root_path", "fbx_bytes", "fix", "seconds")}
        converted["facing"] = (report.get("facing") or {}).get("axis")
        diagnostics = list(handle.get("notes") or [])
        diagnostics.append(diag("info", "BLENDER_CONVERTED", f"{pathlib.Path(resolved['file']).name} → {pathlib.Path(handle['fbx']).name}: "
                                f"{report.get('bones')} bones, {(report.get('frames') or {}).get('keys')} keys, {report.get('seconds')}s"))
        target = resolved["facing"].get("target")
        if target and converted["facing"] != target:
            diagnostics.append(diag("warning", "FACING_MISMATCH", f"converted skeleton faces {converted['facing']}, the target faces {target}"))
        if report.get("bones") != handle["joint_count"]:
            diagnostics.append(diag("warning", "BONE_COUNT_MISMATCH", f"{report.get('bones')} bones from {handle['joint_count']} BVH joints"))
        values = {"file": handle["fbx"], "converted": converted}
        applied = (report.get("fix") or {}).get("applied") or []
        if applied:
            # Phase 8-3 — 소스 골격 보정 기록(Job fix.source)
            values["fix_source"] = applied
            legs = next((a for a in applied if a.get("op") == "legs"), None)
            if legs:
                raised = legs.get("pelvis_raise") or {}
                diagnostics.append(diag("info", "FIX_LEGS_APPLIED", f"source stance ratio p90 {legs['before']['ratio']['p90']} → {legs['after']['ratio']['p90']}, "
                                        f"planted slide p95 L/R {legs['before']['slide_p95']} → {legs['after']['slide_p95']}, IK error ≤ "
                                        f"{legs['ik']['error_max_cm']} cm"
                                        + (f", pelvis raised p50 {raised['space_cm']['p50']} · max {raised['space_cm']['max']} cm (keep_knee_bend)"
                                           if raised.get("applied") else "")))
        if report.get("rest_fbx"):
            # import 단계가 이 파일로 스켈레톤 · 메시를 만들고 동작은 그 스켈레톤에 애니만 가져온다
            values["rest_file"] = handle["rest_fbx"]
        if handle.get("deferred"):
            # 생성 결과의 변환 — 임포트 리샘플 rate 는 지금 정한 값(계획 때는 파일이 없었다)
            values["sample_rate"] = resolved.get("sample_rate")
        limitations = self.limitations(resolved)
        if handle.get("review_requested"):
            self._review_result(handle, report, values, limitations, diagnostics)
        return StepResult(values=values, limitations=limitations, diagnostics=diagnostics)

    @staticmethod
    def _review_result(handle: dict, report: dict, values: dict, limitations: list[dict], diagnostics: list[dict]) -> None:
        """report.review → values.review{frames[], sheet, …}(Job 의 review 로도 남는다). 렌더 실패는 변환 실패가 아니다 — 한계로 남긴다."""
        review = report.get("review") or {}
        if not review.get("ok"):
            error = review.get("error") or {"code": "NO_REVIEW", "message": "the report has no review"}
            diagnostics.append(diag("warning", "REVIEW_RENDER_FAILED", f"{error.get('code')}: {error.get('message')} — the FBX is fine, the frames were "
                                    f"not rendered{SubprocessProvider.tail(handle)}"))
            limitations.append(limitation("REVIEW_NOT_RENDERED", f"프레임 렌더 비교가 실패했다({error.get('code')}) — 변환 · 리타깃은 그대로 진행했다", "provider",
                                          reason=error.get("code")))
            return
        values["review"] = {"shows": "source_skeleton", **{k: review.get(k) for k in ("frames", "sheet", "layout", "colors", "camera", "seconds")}}
        diagnostics.append(diag("info", "BLENDER_REVIEW_RENDERED", f"{len(review.get('frames') or [])} frame image(s) + sheet {review.get('sheet')} in "
                                f"{review.get('seconds')}s ({report.get('seconds')}s with the conversion, timeout {handle.get('timeout_s', 0):.0f}s) — the "
                                f"converted SOURCE skeleton ({review.get('colors', {}).get('legend')}), not Vesper", sheet=review.get("sheet"),
                                frames=[f["path"] for f in review.get("frames") or []]))
        limitations.append(review_limitation())
