"""에디터 Provider — Phase 1 · 2 플러그인 Tool 조합 (지침서 §4 · §10).

- retarget (파이프): import_animation_file · create_ik_rig · create_ik_retargeter(match_existing) · retarget_animations
  Phase 8-1: select 단계 — 생성 후보(seed 별)를 모두 같은 RTG 로 리타깃 · validate_animation(profile_positions · body_clearance)으로 재서
  점수(selection.py)로 하나를 고르고, 최종 리타깃은 그 RTG 로 고른 후보만(결정적 — 잰 값 = 최종)
- existing_motion: search_animations(또는 명시 참조)로 소스를 고른다
- direct_key: apply_animation_edits (op 사전은 Phase 2 그대로)
쓰기는 모두 플러그인 가드(허용 목록 · 전역 더티 · 덮어쓰기 없음) 아래에서 일어난다. 여기서는 순서와 이름만 정한다.
"""
from __future__ import annotations

import pathlib

from .. import bvh, motion_metrics, selection, timing
from ..editor import EditorCallError, asset_name, package_path
from ..envelope import diag, limitation
from ..fallback import from_editor_error
from ..request import final_asset_path, root_motion_flag
from .base import PlanBlocked, PlanContext, Provider, RunContext, StepFailed, StepResult, wrap_limitations

def _warning_codes(obj) -> set[str]:
    """validate_animation 항목 안 모든 issues[] 의 warning 코드(하위 검사 포함)."""
    out: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "issues" and isinstance(value, list):
                out |= {i.get("code") for i in value if isinstance(i, dict) and i.get("level") == "warning" and i.get("code")}
            else:
                out |= _warning_codes(value)
    elif isinstance(obj, list):
        for value in obj:
            out |= _warning_codes(value)
    return out


# select 단계의 측정 본(대상) — 템플릿 체인(inspect_skeleton template_match)으로 정하고, 없으면 이 이름(SELECTION_BONES_DEFAULTED)
DEFAULT_BONES = {"hand_l": "hand_l", "hand_r": "hand_r", "hip_l": "thigh_l", "hip_r": "thigh_r", "foot_l": "foot_l", "foot_r": "foot_r",
                 "shoulder_l": "upperarm_l", "shoulder_r": "upperarm_r", "elbow_l": "lowerarm_l", "elbow_r": "lowerarm_r",
                 motion_metrics.HEAD_ROLE: "head"}
CANDIDATE_PREFIX = "Cand_"


def _measured_from_validation(item: dict | None) -> dict:
    numeric = (item or {}).get("numeric") or {}
    return {k: numeric.get(k) for k in ("length", "frame_rate", "frames", "loop") if k in numeric}


def apply_edits(ctx: RunContext, source: str, operations: list[dict], inputs: dict, step: str, source_name: str) -> StepResult:
    """apply_animation_edits 로 새 애셋(ctx.output_folder/output_name) — 편집(direct_key) · 흐느적 보정(timing) · 한 풀이(body_fit, Phase 8-4b)가
    같은 쓰기 규칙(가드 · 내장 검증 · 검증 실패면 미저장 애셋을 created 로)을 쓴다."""
    editor = ctx.editor
    out = f"{ctx.output_folder}/{ctx.output_name}"
    try:
        res = editor.require("apply_animation_edits", source=source, asset_path=out, operations=operations,
                             loop=inputs.get("loop"), root_motion=inputs.get("root_motion"), validate=True, save=ctx.save)
    except EditorCallError as err:
        created = [out] if err.code == "VALIDATION_FAILED" else []  # 검증 실패면 애셋은 미저장으로 남는다
        raise from_editor_error(step, err, created=created)
    asset = package_path(res["asset_path"])
    validation = res.get("validation")
    measured = {"length": res.get("length"), "frame_rate": res.get("frame_rate"), "frames": res.get("frames")}
    measured.update({k: v for k, v in _measured_from_validation((validation or {}).get("asset")).items() if k == "loop"})
    return StepResult(values={"asset": asset, "skeleton": ctx.request["target_skeleton"], "validation": validation, "measured": measured},
                      created=[asset], limitations=wrap_limitations(res.get("limitations"), source_name))


class ExistingMotion(Provider):
    """프로젝트 안의 기존 모션 — 계획 시점에 소스를 골라 고정한다(보이는 것이 실행되는 것)."""

    def plan_resolve(self, request: dict, pctx: PlanContext) -> dict:
        refs = request["reference_animations"]
        search = request["search"]
        if not refs and not search:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "NO_SOURCE_HINT", "existing_motion needs reference_animations or search")
        step = {"step": "resolve_source", "provider": self.name, "tool": "search_animations",
                "inputs": {"reference": refs[0] if refs else None, "search": search}, "resolved": None, "alternatives": []}
        if pctx.editor_ok:
            try:
                step["resolved"], step["alternatives"] = self.resolve(request, pctx.editor)
            except StepFailed as failed:
                raise PlanBlocked(failed.cause, failed.reason, failed.message, editor_error=failed.editor_error)
        return step

    def resolve(self, request: dict, editor) -> tuple[dict, list[dict]]:
        target = request["target_skeleton"]
        try:
            refs = request["reference_animations"]
            if refs:
                ref = refs[0]
                folder, name = ref.rsplit("/", 1)
                items = editor.require("search_animations", query=name, path_prefix=folder, limit=50, **{"class": "all"})["items"]
                items = [i for i in items if package_path(i["asset_path"]) == ref]
                if not items:
                    raise StepFailed("UNSUPPORTED_REQUEST", "NO_MATCH", f"reference animation not found: {ref}")
            else:
                params = {k: v for k, v in (request["search"] or {}).items() if v is not None and k != "asset_class"}
                params.setdefault("limit", 5)
                params["class"] = "AnimSequence"
                items = editor.require("search_animations", skeleton=target, **params)["items"]
                if not items:
                    # 대상 스켈레톤에 없으면 다른 스켈레톤 소스 → retarget 파이프
                    items = editor.require("search_animations", **params)["items"]
                if not items:
                    raise StepFailed("UNSUPPORTED_REQUEST", "NO_MATCH", f"search_animations found nothing for {params}")
        except EditorCallError as err:
            raise from_editor_error("resolve_source", err)
        top = items[0]
        if top.get("class") not in (None, "AnimSequence"):
            raise StepFailed("UNSUPPORTED_REQUEST", "NOT_A_SEQUENCE", f"{top['asset_path']} is a {top.get('class')} — Phase 3 handles AnimSequence")

        def item(i: dict) -> dict:
            return {"source": package_path(i["asset_path"]), "skeleton": package_path(i.get("skeleton")), "length": i.get("length"),
                    "frame_rate": i.get("frame_rate"), "loop": i.get("loop"), "root_motion": i.get("root_motion"), "score": i.get("score")}

        return item(top), [item(i) for i in items[1:5]]

    def run(self, ctx: RunContext) -> StepResult:
        resolved = ctx.step.get("resolved")
        if not resolved:
            # 계획 시점에 에디터가 없었다 — 같은 규칙으로 지금 고른다
            resolved, _ = self.resolve(ctx.request, ctx.editor)
        return StepResult(values={"source": resolved["source"], "skeleton": resolved["skeleton"],
                                  "source_measured": {k: resolved.get(k) for k in ("length", "frame_rate", "loop")}})


class DirectKey(Provider):
    """키 직접 편집 — 계획 시점에 소스가 대상 스켈레톤에 있으면 preview 로 op 를 미리 검사한다.

    Phase 8-3 timing 단계: 리타깃 뒤(또는 대상 스켈레톤의 기존 애셋) 시퀀스를 validate_animation profile 로 재서 timing.py 가 휘두름 가속 ·
    정지 머리/꼬리 트림 op(trim · time_warp — 매끈한 배율 곡선 + antialias, 8-3 후속)를 만들고 apply_animation_edits 로 새 애셋에 적용한다. 측정 본은
    select 와 같은 원천(selection_bones). 소스가 계획 때 대상 스켈레톤 위에 있고 에디터가 있으면 계획이 op 를 구해 미리보기까지 한다(보이는 것이 실행되는 것)."""

    TIMING_TOOL = "validate_animation(profile) → apply_animation_edits(trim · time_warp)"

    @staticmethod
    def timing_bones(bones: dict) -> dict:
        """selection_bones → {hands: [왼 · 오른 손목], body: 전신 정지 판정 본(측정 역할 본 + 머리)}."""
        body = sorted({bones[r] for r in motion_metrics.ROLES if bones.get(r)} | ({bones[motion_metrics.HEAD_ROLE]} if bones.get(motion_metrics.HEAD_ROLE) else set()))
        return {"from": bones.get("from"), "hands": [bones["hand_l"], bones["hand_r"]], "body": body}

    @staticmethod
    def measure_timing(editor, asset: str, skeleton: str, inputs: dict, step: str = "timing") -> tuple[dict, dict]:
        """대상 시퀀스 한 번 측정 → (timing.plan, timing.summary). inputs = 계획 단계 inputs(timing 설정 + bones)."""
        bones = inputs["bones"]
        try:
            item = (editor.require("validate_animation", assets=[asset], skeleton=skeleton, profile_bones=bones["body"]).get("assets") or [None])[0]
        except EditorCallError as err:
            raise from_editor_error(step, err)
        numeric = (item or {}).get("numeric") or {}
        profile = numeric.get("profile")
        if not profile or not numeric.get("frame_rate") or numeric.get("length") is None:
            raise StepFailed("VALIDATION_FAILED", "NO_PROFILE", f"validate_animation gave no speed profile for {asset}")
        args = {"hands": tuple(bones["hands"]), "body": bones["body"], "scale": (numeric.get("pelvis_height_cm") or 100.0) / 100.0,
                "fps": float(numeric["frame_rate"]), "length": float(numeric["length"]), "params": inputs}
        try:
            return timing.plan(profile, **args), timing.summary(profile, **args)
        except timing.TimingError as err:
            raise StepFailed("VALIDATION_FAILED", "NO_PROFILE", f"{asset}: {err.args[1] if len(err.args) > 1 else err}") from None

    def plan_timing(self, request: dict, source_on_target: str | None, pctx: PlanContext) -> dict:
        cfg = request["fix"]["timing"]
        step = {"step": "timing", "provider": self.name, "tool": self.TIMING_TOOL,
                "inputs": {**cfg, "loop": request["loop"], "root_motion": root_motion_flag(request), "bones": None}, "resolved": None}
        if not pctx.editor_ok:
            return step
        try:
            step["inputs"]["bones"] = self.timing_bones(RetargetPipe.selection_bones(pctx.editor, request["target_skeleton"], pctx.diagnostics, "timing"))
            if source_on_target:
                plan, before = self.measure_timing(pctx.editor, source_on_target, request["target_skeleton"], step["inputs"])
                env = pctx.editor.call("preview_animation_edits", source=source_on_target, operations=plan["ops"], asset_path=final_asset_path(request),
                                       loop=request["loop"], root_motion=root_motion_flag(request))
                if not env.get("ok") or not (env.get("result") or {}).get("valid", True):
                    err = EditorCallError("preview_animation_edits", env) if not env.get("ok") else None
                    raise PlanBlocked("UNSUPPORTED_REQUEST", "BAD_OPERATIONS", f"preview_animation_edits rejected the timing ops {plan['ops']}"
                                      + (f": {err.code}" if err else ""), planned=(env.get("result") or {}).get("planned"))
                preview = env["result"].get("result") or {}
                step["resolved"] = {**plan, "before": before,
                                    "preview": {"length": preview.get("length"), "frame_rate": preview.get("frame_rate"), "frames": preview.get("frames"),
                                                "seams": env["result"].get("seams"), "limitations": env["result"].get("limitations")}}
        except StepFailed as failed:
            raise PlanBlocked(failed.cause, failed.reason, failed.message, editor_error=failed.editor_error)
        return step

    def plan_edit(self, request: dict, source_on_target: str | None, pctx: PlanContext) -> dict:
        ops = request["edits"]["operations"]
        step = {"step": "edit", "provider": self.name, "tool": "apply_animation_edits",
                "inputs": {"operations": ops, "loop": request["loop"], "root_motion": root_motion_flag(request)}, "preview": None}
        if source_on_target and pctx.editor_ok:
            env = pctx.editor.call("preview_animation_edits", source=source_on_target, operations=ops,
                                   asset_path=final_asset_path(request), loop=request["loop"], root_motion=root_motion_flag(request))
            if not env.get("ok"):
                err = EditorCallError("preview_animation_edits", env)
                failed = from_editor_error("edit", err)
                raise PlanBlocked(failed.cause, failed.reason, f"preview_animation_edits rejected the operations: {err.code}",
                                  editor_error=failed.editor_error)
            preview = env["result"]
            if not preview.get("valid", True):
                raise PlanBlocked("UNSUPPORTED_REQUEST", "BAD_OPERATIONS", "preview_animation_edits: operations are not valid",
                                  planned=preview.get("planned"))
            result = preview.get("result") or {}
            step["preview"] = {"length": result.get("length"), "frame_rate": result.get("frame_rate"), "frames": result.get("frames"),
                               "seams": preview.get("seams"), "limitations": preview.get("limitations"),
                               "would_create": preview.get("would_create")}
        return step

    def run(self, ctx: RunContext) -> StepResult:
        if ctx.step["step"] == "timing":
            return self._timing(ctx)
        source = ctx.values.get("asset") or ctx.values["source"]
        inputs = ctx.step["inputs"]
        return self._apply(ctx, source, inputs["operations"], inputs, "edit")

    def _apply(self, ctx: RunContext, source: str, operations: list[dict], inputs: dict, step: str) -> StepResult:
        return apply_edits(ctx, source, operations, inputs, step, "direct_key")

    def _timing(self, ctx: RunContext) -> StepResult:
        """흐느적 보정(Phase 8-3) — 측정 → op(timing.plan) → apply_animation_edits → 새 애셋 다시 측정. 바꿀 것이 없어도 최종 이름의 애셋은 만든다
        (앞 단계는 Work 이름이었다 — 항등 trim). Job timing = 신호 · 구간 · op · warp · 전후 수치."""
        editor = ctx.editor
        target = ctx.request["target_skeleton"]
        source = ctx.values.get("asset") or ctx.values["source"]
        inputs = dict(ctx.step["inputs"])
        diagnostics: list[dict] = []
        if not inputs.get("bones"):
            inputs["bones"] = self.timing_bones(RetargetPipe.selection_bones(editor, target, diagnostics, "timing"))
        plan, before = self.measure_timing(editor, source, target, inputs)
        planned = (ctx.step.get("resolved") or {}).get("ops")
        if planned is not None and planned != plan["ops"]:
            diagnostics.append(diag("warning", "TIMING_CHANGED_SINCE_PLAN", f"{asset_name(source)} measures differently than at planning — running the "
                                    "ops measured now", planned=planned, now=plan["ops"]))
        result = self._apply(ctx, source, plan["ops"], inputs, "timing")
        _, after = self.measure_timing(editor, result.values["asset"], target, inputs)
        result.values["timing"] = {**plan, "source": source, "asset": result.values["asset"], "bones": inputs["bones"], "before": before, "after": after}
        result.diagnostics = diagnostics + result.diagnostics
        if plan["applied"]:
            result.diagnostics.append(diag("info", "TIMING_APPLIED", f"swing peak {before['peak_cm_s']} → {after['peak_cm_s']} cm/s (core ×{plan['rate']}, "
                                           f"recovery ×{plan['recovery_rate']}), length {before['length']} → {after['length']}s",
                                           ops=plan["ops"]))
            result.limitations.append(limitation(
                "TIMING_CHANGED_LENGTH", f"흐느적 보정(fix.timing)으로 길이 {before['length']} → {after['length']}초 — 휘두름 ×{plan['rate']} · 복귀 ×"
                f"{plan['recovery_rate']} · 정지 머리 {plan['cut']['head_s']}초 · 꼬리 {round(before['length'] - plan['cut']['tail_s'], 4)}초를 잘랐다. "
                "요청 길이(duration_seconds)와 다른 것은 의도된 결과다", "direct_key", length_before=before["length"], length_after=after["length"],
                rate=plan["rate"], recovery_rate=plan["recovery_rate"]))
        else:
            result.limitations.append(limitation(
                "TIMING_NOT_APPLIED", f"흐느적 보정을 하지 않았다({plan['reason']}) — 휘두름 정점 {before['peak_cm_s']} cm/s, 목표 "
                f"{inputs['target_peak_cm_s']:g}. 최종 애셋은 원래 시퀀스 그대로(항등 trim)", "direct_key", reason=plan["reason"]))
        return result


class RetargetPipe(Provider):
    """공통 리타깃 처리 (§10). 기존 IK Rig · RTG 는 요청이 명시할 때만 재사용하고 메시는 항상 명시한다.

    정면: FK 체인 op 는 전역 회전 델타라(FKChainsOp.cpp:343-350) 소스와 대상의 정면이 다르면 동작이 다른 평면으로 휜다 →
    두 스켈레톤 기준 포즈의 정면(발 영역 + 좌우 체인 교차 확인)을 재 계획에 고정하고, 다르면 create_ik_retargeter(facing_yaw_deg)로 맞춘다.
    """

    def plan_retarget(self, request: dict, source_skeleton: str | None, pctx: PlanContext, *, conditional: bool,
                      from_import: bool = False, source_faces_target: bool = False) -> tuple[dict, list[str]]:
        rt = request["retarget"]
        risks: list[str] = []
        clearance, clearance_from, clearance_lims = self.body_clearance(request, risks)
        inputs = {"target_mesh": request["target_mesh"], "source_mesh": rt.get("source_mesh"), "source_mesh_source": "argument" if rt.get("source_mesh") else None,
                  "existing_source_rig": rt.get("existing_source_rig"), "existing_target_rig": rt.get("existing_target_rig"),
                  "existing_retargeter": rt.get("existing_retargeter"), "source_pelvis": rt.get("source_pelvis"),
                  "source_chains": rt.get("source_chains"), "ops": rt.get("ops", "match_existing"),
                  "align_mode": rt.get("align_mode", "engine"), "body_clearance": clearance, "body_clearance_from": clearance_from}
        step = {"step": "retarget", "provider": self.name, "tool": "create_ik_rig → create_ik_retargeter → retarget_animations",
                "inputs": inputs, "conditional": conditional}
        source_info = None
        if source_faces_target:
            # blender 변환이 이미 대상 정면으로 돌렸다(motion_file.facing)
            inputs["facing"] = {"mode": "converted", "resolved": True, "yaw_deg": 0.0}
        elif source_skeleton and pctx.editor_ok:
            source_info = self._inspect(pctx.editor, source_skeleton, details=True)
            inputs["facing"] = self.resolve_facing(request, source_info, pctx.editor)
        else:
            inputs["facing"] = {"mode": rt.get("source_facing", "auto"), "resolved": False, "yaw_deg": 0.0}
        facing_risks, facing_lims = self.facing_notes(inputs["facing"], existing_retargeter=bool(rt.get("existing_retargeter")))
        risks += facing_risks
        step["expected_limitations"] = facing_lims + clearance_lims
        if not request["target_mesh"]:
            if conditional:
                step["blocked_if_needed"] = {"cause": "UNSUPPORTED_REQUEST", "reason": "MISSING_INPUT", "missing": ["target_mesh"]}
                risks.append("TARGET_MESH_REQUIRED_IF_RETARGET")
            else:
                raise PlanBlocked("UNSUPPORTED_REQUEST", "MISSING_INPUT", "target_mesh is required when the chain retargets (§9)",
                                  missing=["target_mesh"])
        if from_import:
            inputs["source_mesh_source"] = "import"
        elif not inputs["source_mesh"]:
            if source_skeleton and pctx.editor_ok:
                mesh, mesh_source = self._skeleton_mesh(pctx.editor, source_skeleton, source_info)
                if not mesh:
                    raise PlanBlocked("UNSUPPORTED_REQUEST", "MISSING_INPUT", f"no skeletal mesh found for {source_skeleton} — give retarget.source_mesh",
                                      missing=["retarget.source_mesh"])
                inputs["source_mesh"], inputs["source_mesh_source"] = mesh, mesh_source
            risks.append("SOURCE_MESH_IMPLICIT")
        return step, risks

    @staticmethod
    def body_clearance(request: dict, risks: list[str]) -> tuple[str, str, list[dict]]:
        """팔-몸통 관통 처리 → (모드, 근거, 예상 한계). 요청이 정했으면 그대로(request), 비웠으면 fix.body(auto)면 measure(body_fit — Phase 8-4b:
        뒤 한 풀이가 고친다), two_hand_weapon_grip 이면 measure(grip_flag — 모든 Provider: 위팔 보정이 양손을 벌리지 않게, 2026-10-26 E1), 아니면
        resolve(default — 개정 10 그대로). 파지 플래그 · fix.body 에 resolve 를 명시하면 위험."""
        mode = request["retarget"].get("body_clearance")
        grip = bool((request["constraints"] or {}).get("two_hand_weapon_grip"))
        body_fit = bool(((request.get("fix") or {}).get("body") or {}).get("mode") == "auto")
        if mode is not None:
            if grip and mode == "resolve":
                risks.append("CLEARANCE_MAY_BREAK_GRIP")
            if body_fit and mode == "resolve":
                risks.append("CLEARANCE_DOUBLE_FIX")
            return mode, "request", []
        if body_fit:
            # Phase 8-4b — 관통 보정 원천은 하나: 리타깃은 재기만 하고 body_fit 이 몸 전체 · 파지 · 발을 함께 푼다
            return "measure", "body_fit", [limitation(
                "CLEARANCE_BY_BODY_FIT", "관통 보정은 리타깃 뒤 한 풀이(fix.body — body_fit 단계)가 한다 — 리타깃 body_clearance 는 재기만(measure). 위팔만 "
                "돌리는 resolve 와 겹치면 같은 관통을 두 번 고친다", "retarget")]
        if grip:
            return "measure", "grip_flag", [limitation(
                "BODY_CLEARANCE_MEASURED_FOR_GRIP", "양손 파지 요청이라 팔-몸통 관통을 재기만 하고 위팔을 고치지 않았다(resolve 는 관통 프레임마다 위팔을 바깥으로 "
                "돌려 양손을 벌린다 — E1: 손목 간격 p50 +1.9 cm). 관통은 Job validation 의 body_clearance 로 본다. 파지를 지키며 관통을 없애는 것은 8-4",
                "retarget", constraint="two_hand_weapon_grip")]
        return "resolve", "default", []

    def plan_select(self, request: dict, spec: dict, retarget_inputs: dict, pctx: PlanContext) -> tuple[dict, list[str]]:
        """select 단계(Phase 8-1) — 후보 · 지표 · 가중치 · 기준 · 측정 본을 계획에 고정한다. 본은 대상 스켈레톤 템플릿 체인(에디터가 없으면 실행 때) —
        생성 단계가 자루 무기 간격을 풀며 이미 쟀으면(spec bones) 그 값. 자루 무기 띠(grip_spacing)는 생성 단계가 푼 그대로 싣는다(단일 원천)."""
        risks: list[str] = []
        bones = spec.get("bones")
        if bones is None and pctx.editor_ok:
            bones = self.selection_bones(pctx.editor, request["target_skeleton"], pctx.diagnostics)
        elif bones is None:
            risks.append("SELECTION_BONES_AT_RUN")
        flags = spec.get("flags") or []
        grip_on = bool((request["constraints"] or {}).get("two_hand_weapon_grip"))
        weights = selection.check_weights(spec.get("weights"))
        inputs = {"candidates": spec["candidates"], "metrics": ["grip", "stance", "swing", "attack", "clearance", "breakage", "cross", "head",
                                                                "non_grip · hand raise · jitter · hand contact (record only)"],
                  "weights": weights, "thresholds": dict(selection.THRESHOLDS), "metric_version": selection.METRIC_VERSION,
                  "grip_on": grip_on, "swing_on": request["motion_category"] == "weapon_action", "grip_window_s": spec.get("grip_window_s"),
                  "grip_spacing": spec.get("grip_spacing"),
                  "bones": bones, "body_clearance": retarget_inputs["body_clearance"], "refine_flags": flags,
                  "output": f"<work>/Candidates/{CANDIDATE_PREFIX}<import name>"}
        return {"step": "select", "provider": self.name, "tool": "retarget_animations(candidates) → validate_animation(profile_positions · body_clearance)",
                "inputs": inputs}, risks

    @staticmethod
    def selection_bones(editor, skeleton: str, diagnostics: list[dict], step: str = "select") -> dict:
        """대상 템플릿 체인의 LeftArm/RightArm 시작(어깨) · 끝(손목) · 손목의 부모(팔꿈치) · LeftLeg/RightLeg 시작(엉덩) · Head 시작(머리 — 없으면
        Neck 끝), 발은 foot_l/foot_r(없으면 다리 체인 끝). 못 찾으면 기본 이름. arm_dims = 그 어깨 · 팔꿈치 · 손목 본의 기준 포즈(ref_component)
        치수(motion_metrics.arm_dims — 자루 무기 간격 사상의 대상 쪽, 위치가 없으면 None). select · timing(Phase 8-3) 단계가 같은 측정 본을 쓴다."""
        try:
            info = editor.require("inspect_skeleton", skeleton=skeleton, details=True)
        except EditorCallError as err:
            raise from_editor_error(step, err)
        chains = {c.get("name"): c for c in ((info.get("template_match") or {}).get("chains") or [])}
        parents = {b.get("name"): b.get("parent") for b in info.get("bones") or []}
        names = set(parents)
        found = {"hand_l": (chains.get("LeftArm") or {}).get("end"), "hand_r": (chains.get("RightArm") or {}).get("end"),
                 "hip_l": (chains.get("LeftLeg") or {}).get("start"), "hip_r": (chains.get("RightLeg") or {}).get("start"),
                 "foot_l": "foot_l" if "foot_l" in names else (chains.get("LeftLeg") or {}).get("end"),
                 "foot_r": "foot_r" if "foot_r" in names else (chains.get("RightLeg") or {}).get("end"),
                 "shoulder_l": (chains.get("LeftArm") or {}).get("start"), "shoulder_r": (chains.get("RightArm") or {}).get("start"),
                 motion_metrics.HEAD_ROLE: (chains.get("Head") or {}).get("start") or (chains.get("Neck") or {}).get("end")}
        for side in ("l", "r"):
            # 팔꿈치 = 손목 본의 부모(아래팔 — 트위스트 본은 형제라 끼지 않는다)
            hand = found[f"hand_{side}"]
            found[f"elbow_{side}"] = parents.get(hand) if hand and parents.get(hand) != found[f"shoulder_{side}"] else None
        missing = [k for k, v in found.items() if not v]
        if missing:
            diagnostics.append(diag("warning", "SELECTION_BONES_DEFAULTED", f"{skeleton}: no template chain for {missing} — measuring "
                                    f"{[DEFAULT_BONES[k] for k in missing]}"))
        out = {"from": "template_chains" if not missing else "default", **{k: v or DEFAULT_BONES[k] for k, v in found.items()}}
        rest = {b.get("name"): (b.get("ref_component") or {}).get("t") for b in info.get("bones") or []}
        out["arm_dims"] = motion_metrics.arm_dims({k: v for k, v in rest.items() if v}, out)
        # Phase 8-3 — 다리 치수 · 골반 높이 · 기준 포즈(다리 보정의 대상 모델 foot_fix.target_model · 대상 측정 legs_on_target) · 무릎 = 발목 본의 부모
        knees = {"knee_l": parents.get(out["foot_l"]), "knee_r": parents.get(out["foot_r"]), "pelvis": parents.get(out["hip_l"])}
        out["leg_dims"] = motion_metrics.leg_dims({k: v for k, v in rest.items() if v}, {**out, **knees})
        if out["leg_dims"] and rest.get(knees["pelvis"]):
            # 대상 모델(foot_fix.target_model) — 골반 · 엉덩 관절 기준 포즈 위치(대상 엉덩 = s · 소스 골반 + 골반 회전 변화 · 이 오프셋)
            out["leg_dims"]["rest"] = {"pelvis": rest[knees["pelvis"]], "hip_l": rest.get(out["hip_l"]), "hip_r": rest.get(out["hip_r"])}
        out["knees"] = [knees["knee_l"], knees["knee_r"]]
        # 양손 겹침(기록) — 손 본 아래 자손(손가락 · 메타카팔)의 [부모, 자식] 쌍. 이름을 보지 않는다 — 없으면 빈 목록(지표 None)
        children: dict[str, list[str]] = {}
        for name, parent in parents.items():
            children.setdefault(parent, []).append(name)
        for side in ("l", "r"):
            pairs, stack = [], [out[f"hand_{side}"]]
            while stack:
                node = stack.pop()
                for child in sorted(children.get(node, [])):
                    pairs.append([node, child])
                    stack.append(child)
            out[f"hand_tree_{side}"] = pairs
        return out

    @staticmethod
    def _inspect(editor, skeleton: str, details: bool = False) -> dict:
        try:
            return editor.require("inspect_skeleton", skeleton=skeleton, details=details or None)
        except EditorCallError as err:
            raise from_editor_error("retarget", err)

    def _skeleton_mesh(self, editor, skeleton: str, info: dict | None = None) -> tuple[str | None, str | None]:
        r = info or self._inspect(editor, skeleton)
        return package_path(r.get("mesh")), r.get("mesh_source")

    # ---- 정면 ----
    @staticmethod
    def skeleton_facing(info: dict, chains: list[dict] | None) -> dict:
        """기준 포즈 정면 = 발 영역(bvh.facing). 좌우 체인(수동 체인 또는 템플릿 체인) 위치 차로 교차 확인 — 둘이 다르면 모른다고 본다."""
        bones = info.get("bones") or []
        feet = bvh.facing(bvh.skeleton_segments(bones)) if bones else {"axis": None, "reason": "NO_BONES"}
        lateral = bvh.lateral_facing(bvh.bone_positions(bones), chains or (info.get("template_match") or {}).get("chains") or [])
        if feet["axis"] and lateral["axis"] and feet["axis"] != lateral["axis"]:
            axis, reason = None, "FEET_LATERAL_DISAGREE"
        else:
            axis = feet["axis"] or lateral["axis"]
            reason = None if axis else feet.get("reason")
        return {"axis": axis, "reason": reason, "feet": feet, "lateral": lateral}

    def resolve_facing(self, request: dict, source_info: dict, editor) -> dict:
        """소스(측정 또는 retarget.source_facing) · 대상(측정)의 정면 → facing_yaw_deg (소스 정면을 대상 정면으로, UE +Z)."""
        rt = request["retarget"]
        mode = rt.get("source_facing", "auto")
        out = {"mode": mode, "resolved": True, "source": None, "target": None, "yaw_deg": 0.0}
        if mode == "keep":
            return out
        if mode == "auto":
            measured = self.skeleton_facing(source_info, rt.get("source_chains"))
            out.update(source=measured["axis"], source_detail=measured)
        else:
            out.update(source=mode, source_detail={"from": "request"})
        target = self.skeleton_facing(self._inspect(editor, request["target_skeleton"], details=True), None)
        out.update(target=target["axis"], target_detail=target)
        if out["source"] and out["target"]:
            out["yaw_deg"] = bvh.ue_yaw_deg(out["source"], out["target"])
        return out

    @staticmethod
    def facing_notes(facing: dict, existing_retargeter: bool) -> tuple[list[str], list[dict]]:
        """계획의 위험 코드 · 예상 한계 (정면이 다르면 맞춘다는 것, 못 재면 휠 수 있다는 것)."""
        if facing["mode"] in ("keep", "converted"):
            return [], []
        if not facing["resolved"]:
            return ["FACING_UNRESOLVED_AT_PLAN"], []
        if not (facing["source"] and facing["target"]):
            return ["FACING_UNKNOWN"], [limitation(
                "FACING_UNKNOWN", f"정면을 재지 못해 맞추지 않는다(소스 {facing['source']} · 대상 {facing['target']}) — 다르면 동작이 다른 평면으로 휜다. "
                "retarget.source_facing 에 소스가 보는 축을 주거나 keep", "retarget", source_axis=facing["source"], target_axis=facing["target"])]
        if not facing["yaw_deg"]:
            return [], []
        if existing_retargeter:
            return ["FACING_DIFFERS"], [limitation(
                "FACING_NOT_ALIGNED", f"소스 정면 {facing['source']} ≠ 대상 {facing['target']} 인데 기존 리타기터를 그대로 쓴다 — 그 애셋이 맞추지 않았으면 "
                "동작이 다른 평면으로 휜다", "retarget", source_axis=facing["source"], target_axis=facing["target"], yaw_deg=facing["yaw_deg"])]
        return ["FACING_DIFFERS"], [limitation(
            "FACING_ALIGNED", f"소스 정면 {facing['source']} ≠ 대상 {facing['target']} — 리타기터가 대상 루트를 {-facing['yaw_deg']:g}° 돌린 채 풀고 "
            "Additive Pose op 로 되돌린다(facing_yaw_deg). 루트 회전이 Yaw 뿐일 때 정확", "retarget",
            source_axis=facing["source"], target_axis=facing["target"], yaw_deg=facing["yaw_deg"])]

    def run(self, ctx: RunContext) -> StepResult:
        kind = ctx.step["step"]
        return self._import(ctx) if kind == "import" else self._select(ctx) if kind == "select" else self._retarget(ctx)

    def _import(self, ctx: RunContext) -> StepResult:
        editor = ctx.editor
        dest = f"{ctx.work_path}/Import"
        # 요청 frame_rate — Interchange 가 그 rate 로 굽는다(없으면 파일 rate). 생성 결과 변환은 실행 때 정한 값(앞 단계 values)
        rate = ctx.values["sample_rate"] if "sample_rate" in ctx.values else (ctx.step.get("inputs") or {}).get("sample_rate")
        rate = int(round(rate)) if rate else None
        created: list[str] = []
        rest = None
        # Phase 8-1 — 변환된 후보 여러 개: 기준 포즈 FBX 는 한 번(모든 후보가 같은 SOMA 표준 T 포즈), 동작 FBX 는 후보마다 그 스켈레톤에 애니만.
        # import_animation_file 은 빈 폴더에만 임포트한다(FBX 가 만들 이름을 미리 검사할 수 없다 — DEST_NOT_EMPTY, 하위 폴더는 보지 않음) → 후보마다 C<번호>/
        multi = bool(ctx.values.get("candidate_fbx"))
        candidates = ctx.values.get("candidate_fbx") or [{"index": 0, "fbx": ctx.values["file"]}]
        anims: list[str] = []
        res = {}
        try:
            if ctx.values.get("rest_file"):
                # 변환이 남긴 기준 포즈 FBX(첫 프레임 = 기준 포즈인 2프레임 애니)로 스켈레톤 · 메시 → 동작은 그 스켈레톤에 애니만. 동작 FBX 로
                # 바로 만들면 Interchange 가 깊은 본의 바인드 포즈를 무효로 보고 첫 프레임을 기준 포즈로 삼는다(bvh_to_fbx.export_rest_fbx)
                rest = editor.require("import_animation_file", file=ctx.values["rest_file"], dest_path=dest, save=ctx.save, sample_rate=rate)
                created += [package_path(p) for p in rest.get("imported", [])]
                for cand in candidates:
                    extra = {"name": pathlib.PurePath(cand["fbx"]).stem} if multi else {}
                    res = editor.require("import_animation_file", file=cand["fbx"], dest_path=f"{dest}/Motion" + (f"/C{cand['index']:02d}" if multi else ""),
                                         save=ctx.save, sample_rate=rate, skeleton=package_path(rest.get("skeleton")), **extra)
                    created += [package_path(p) for p in res.get("imported", [])]
                    anims.append(package_path(((res.get("animations") or [{}])[0]).get("asset")))
            else:
                res = editor.require("import_animation_file", file=ctx.values["file"], dest_path=dest, save=ctx.save, sample_rate=rate)
                created += [package_path(p) for p in res.get("imported", [])]
                anims.append(package_path(((res.get("animations") or [{}])[0]).get("asset")))
        except EditorCallError as err:
            raise from_editor_error("import", err, created=created)
        if not all(anims):
            raise StepFailed("IMPORT_FAILED", "NO_ANIMATION", f"{ctx.values['file']} produced no animation", created=created)
        source = rest or res
        values = {"asset": anims[0], "skeleton": package_path(source.get("skeleton")), "mesh": package_path(source.get("mesh"))}
        if ctx.values.get("candidate_fbx"):
            values["candidate_assets"] = [{**{k: c.get(k) for k in ("index", "seed", "review")}, "asset": a} for c, a in zip(candidates, anims)]
        return StepResult(values=values, created=created)

    def _rigs(self, ctx: RunContext, inputs: dict, source_mesh: str, facing: dict, created: list[str]) -> tuple[str | None, str]:
        """소스 · 대상 IK Rig + 리타기터(요청 재사용 또는 새로) → (대상 리그, 리타기터). select 단계와 최종 리타깃이 같은 규칙으로 만든다."""
        editor = ctx.editor
        target_rig = inputs.get("existing_target_rig")
        retargeter = inputs.get("existing_retargeter")
        if retargeter:
            return target_rig, retargeter
        source_rig = inputs.get("existing_source_rig")
        if not source_rig:
            manual = bool(inputs.get("source_chains"))
            r = editor.require("create_ik_rig", skeletal_mesh=source_mesh, asset_path=f"{ctx.work_path}/IK_Source",
                               mode="manual" if manual else "auto", pelvis=inputs.get("source_pelvis"),
                               chains=inputs.get("source_chains"), save=ctx.save)
            source_rig = package_path(r["asset_path"])
            created.append(source_rig)
        if not target_rig:
            r = editor.require("create_ik_rig", skeletal_mesh=inputs["target_mesh"], asset_path=f"{ctx.work_path}/IK_Target", save=ctx.save)
            target_rig = package_path(r["asset_path"])
            created.append(target_rig)
        r = editor.require("create_ik_retargeter", source_rig=source_rig, target_rig=target_rig, source_mesh=source_mesh,
                           target_mesh=inputs["target_mesh"], asset_path=f"{ctx.work_path}/RTG_Retarget", ops=inputs.get("ops", "match_existing"),
                           align_mode=inputs.get("align_mode", "engine"), facing_yaw_deg=facing["yaw_deg"] or None, save=ctx.save)
        retargeter = package_path(r["asset_path"])
        created.append(retargeter)
        return target_rig, retargeter

    def _retarget(self, ctx: RunContext) -> StepResult:
        editor = ctx.editor
        inputs = ctx.step["inputs"]
        blocked = ctx.step.get("blocked_if_needed")
        if blocked:
            raise StepFailed(blocked["cause"], blocked["reason"], "retarget is needed but target_mesh was not given", missing=blocked["missing"])
        source_anim = ctx.values.get("asset") or ctx.values["source"]
        source_mesh = ctx.values.get("mesh") or inputs.get("source_mesh")
        diagnostics, limitations = [], []
        facing = inputs.get("facing") or {"mode": "keep", "resolved": True, "yaw_deg": 0.0}
        source_info = None
        if not facing["resolved"]:
            # 계획 때 소스 스켈레톤을 몰랐다(임포트 · 에디터 없음) — 같은 규칙으로 지금 잰다
            source_info = self._inspect(editor, ctx.values["skeleton"], details=True)
            facing = self.resolve_facing(ctx.request, source_info, editor)
            _, limitations = self.facing_notes(facing, existing_retargeter=bool(inputs.get("existing_retargeter")))
            diagnostics.append(diag("info", "FACING_RESOLVED_AT_RUN", f"source faces {facing['source']}, target {facing['target']} → yaw {facing['yaw_deg']:g}°"))
        if not source_mesh:
            source_mesh, mesh_source = self._skeleton_mesh(editor, ctx.values["skeleton"], source_info)
            if not source_mesh:
                raise StepFailed("UNSUPPORTED_REQUEST", "MISSING_INPUT", f"no skeletal mesh for {ctx.values['skeleton']}", missing=["retarget.source_mesh"])
            diagnostics.append(diag("warning", "SOURCE_MESH_IMPLICIT", f"source mesh {source_mesh} ({mesh_source}) chosen at run time"))
        target_mesh = inputs["target_mesh"]
        clearance = inputs.get("body_clearance") or "resolve"
        created: list[str] = []
        try:
            if ctx.values.get("selection") and ctx.values.get("retargeter") and not inputs.get("existing_retargeter"):
                # select 단계가 만든 리그 · 리타기터 그대로 — 측정한 후보 = 이 결과(같은 RTG · 같은 관통 모드)
                target_rig, retargeter = ctx.values.get("target_rig"), ctx.values["retargeter"]
            else:
                target_rig, retargeter = self._rigs(ctx, inputs, source_mesh, facing, created)
            res = editor.require("retarget_animations", retargeter=retargeter, assets=[source_anim], source_mesh=source_mesh,
                                 target_mesh=target_mesh, output_path=ctx.output_folder,
                                 name_rule={"replace_from": asset_name(source_anim), "replace_to": ctx.output_name},
                                 include_referenced=False, validate=True, save=ctx.save,
                                 body_clearance=None if clearance == "off" else clearance)
        except EditorCallError as err:
            if err.code == "VALIDATION_FAILED":
                created.append(f"{ctx.output_folder}/{ctx.output_name}")
            raise from_editor_error("retarget", err, created=created)
        generated = [package_path(g["asset"]) for g in res.get("generated", [])]
        if not generated:
            raise StepFailed("RETARGET_FAILED", "NOTHING_GENERATED", "retarget_animations generated no asset", created=created)
        validation = res.get("validation")
        clearance_items = res.get("body_clearance") or []
        diagnostics += self.clearance_notes(clearance_items)
        if inputs.get("source_pelvis") and validation:
            body = None if clearance == "off" else {"mesh": target_mesh, **({"ik_rig": target_rig} if target_rig else {})}
            validation = self._revalidate(editor, generated[0], source_anim, ctx.request["target_skeleton"], inputs, validation, diagnostics, body,
                                          retargeter)
            if validation.get("status") == "FAILED":
                raise StepFailed("VALIDATION_FAILED", "FAILED", f"{generated[0]} fails validation against its source", created=created + generated)
        first = ((validation or {}).get("assets") or [None])[0]
        values = {"asset": generated[0], "skeleton": ctx.request["target_skeleton"], "validation": validation,
                  "measured": _measured_from_validation(first), "retargeter": retargeter, "source_mesh": source_mesh,
                  "facing": {k: facing.get(k) for k in ("mode", "source", "target", "yaw_deg")}, "body_clearance": clearance_items or None}
        if any(o.get("op") in ("stance_width", "foot_lock") for o in (ctx.request.get("fix") or {}).get("ops") or []):
            values["fix_target"] = self.legs_on_target(editor, generated[0], ctx.request["target_skeleton"], diagnostics)
        return StepResult(values=values, created=created + generated, diagnostics=diagnostics, limitations=limitations)

    @staticmethod
    def legs_on_target(editor, asset: str, skeleton: str, diagnostics: list[dict]) -> dict | None:
        """다리 보정(소스 골격)의 대상 쪽 결과 — 발 좌우 비 · 두 발 디딘 최대 · 접지 미끄러짐 · 무릎 간격(motion_metrics.legs_report — 소스 보고와 같은
        정의, 접지는 대상 발목 트랙으로 다시 판정). 측정 실패는 진단만(보정 결과물은 이미 있다)."""
        bones = RetargetPipe.selection_bones(editor, skeleton, diagnostics, "retarget")
        names = {"hip_l": bones["hip_l"], "hip_r": bones["hip_r"], "foot_l": bones["foot_l"], "foot_r": bones["foot_r"]}
        knees = bones.get("knees") or [None, None]
        try:
            item = (editor.require("validate_animation", assets=[asset], skeleton=skeleton, profile_bones=sorted(set(names.values()) | {k for k in knees if k}),
                                   profile_positions=True).get("assets") or [None])[0]
        except EditorCallError as err:
            diagnostics.append(diag("warning", "FIX_TARGET_NOT_MEASURED", f"validate_animation failed ({err.code}) — Job fix.target is empty"))
            return None
        numeric = (item or {}).get("numeric") or {}
        profile = numeric.get("profile") or {}
        pos = profile.get("position_cm") or {}
        tracks = {role: pos.get(bone) for role, bone in names.items()}
        dims = bones.get("leg_dims") or {}
        if not all(tracks.values()) or not dims:
            diagnostics.append(diag("warning", "FIX_TARGET_NOT_MEASURED", f"no hip/foot tracks or leg dimensions for {asset}"))
            return None
        scale = (numeric.get("pelvis_height_cm") or 100.0) / 100.0
        knee_tracks = (pos.get(knees[0]), pos.get(knees[1])) if all(knees) and pos.get(knees[0]) and pos.get(knees[1]) else None
        report = motion_metrics.legs_report(tracks, profile.get("times") or [], 2, dims["leg_cm"], scale, knees=knee_tracks)
        return {"bones": {**names, "knees": knees}, "leg_dims": dims, **report}

    def _select(self, ctx: RunContext) -> StepResult:
        """Phase 8-1 — 후보를 모두 같은 RTG 로 리타깃(<work>/Candidates) → validate_animation(소스 대비 · profile_positions · 관통 · 손가락) 한 번 →
        지표(motion_metrics) → 점수(selection) → 하나. 다음 retarget 단계는 그 RTG 로 고른 후보만 최종 이름으로 만든다."""
        editor = ctx.editor
        inputs = ctx.step["inputs"]
        rt = next(s for s in (ctx.steps or []) if s["step"] == "retarget")["inputs"]
        cands = ctx.values.get("candidate_assets") or [{"index": 0, "seed": None, "asset": ctx.values["asset"]}]
        seeds = {c["index"]: c.get("seed") for c in inputs["candidates"]}
        source_mesh = ctx.values.get("mesh") or rt.get("source_mesh")
        facing = rt.get("facing") or {"mode": "keep", "resolved": True, "yaw_deg": 0.0}
        diagnostics: list[dict] = []
        if not facing.get("resolved"):
            facing = self.resolve_facing(ctx.request, self._inspect(editor, ctx.values["skeleton"], details=True), editor)
        # 지표 버전 1 계획(역할 6개)도 돈다 — 없는 역할(어깨 · 팔꿈치)은 기본 이름
        bones = {**DEFAULT_BONES, **(inputs.get("bones") or self.selection_bones(editor, ctx.request["target_skeleton"], diagnostics))}
        # 자루 무기 띠 = 계획이 푼 대상 간격 ± 대상 허용(motion_metrics.grip_spacing). 버전 4 계획의 grip_spacing_cm(× pelvis scale 띠)은 쓰지 않는다
        spacing = inputs.get("grip_spacing")
        if spacing is None and inputs.get("grip_spacing_cm"):
            raise StepFailed("UNSUPPORTED_REQUEST", "PLAN_OUTDATED", "this plan's select step carries the old polearm band (grip_spacing_cm × pelvis scale, "
                             "metric version 4 — the target gap is not scaled that way) — plan again", fatal=True)
        center, tolerance = (spacing["target_cm"], spacing["tolerance_cm"]["target"]) if spacing else (None, motion_metrics.GRIP_TOL_CM)
        clearance = inputs.get("body_clearance") or "resolve"
        created: list[str] = []
        try:
            target_rig, retargeter = self._rigs(ctx, rt, source_mesh, facing, created)
            # 검증은 아래에서 한 번에(FAILED 후보는 빼고 고른다 — 내장 검증은 FAILED 면 호출 전체가 실패). resolve 는 검증과 무관하게 적용된다
            res = editor.require("retarget_animations", retargeter=retargeter, assets=[c["asset"] for c in cands], source_mesh=source_mesh,
                                 target_mesh=rt["target_mesh"], output_path=f"{ctx.work_path}/Candidates", name_rule={"prefix": CANDIDATE_PREFIX},
                                 include_referenced=False, validate=False, save=ctx.save, body_clearance=None if clearance == "off" else clearance)
            outputs = {package_path(g["source"]): package_path(g["asset"]) for g in res.get("generated", [])}
            created += list(outputs.values())
            missing = [c["asset"] for c in cands if c["asset"] not in outputs]
            if missing:
                raise StepFailed("RETARGET_FAILED", "NOTHING_GENERATED", f"retarget_animations made no candidate for {missing}", created=created)
            params = {"assets": [outputs[c["asset"]] for c in cands], "sources": [c["asset"] for c in cands], "skeleton": ctx.request["target_skeleton"],
                      "profile_bones": self.profile_bones(bones), "profile_positions": True, "fingers": {"retargeter": retargeter}}
            if rt.get("source_pelvis"):
                params["source_pelvis"] = rt["source_pelvis"]
            if rt.get("source_feet"):
                params["source_feet"] = rt["source_feet"]
            if clearance != "off":
                params["body_clearance"] = {"mesh": rt["target_mesh"], **({"ik_rig": target_rig} if target_rig else {})}
            validated = editor.require("validate_animation", **params).get("assets") or []
        except EditorCallError as err:
            raise from_editor_error("select", err, created=created)
        clearance_items = {package_path(i.get("asset")): i for i in res.get("body_clearance") or []}
        rows = []
        for c, item in zip(cands, validated):
            row = {"index": c["index"], "seed": c.get("seed", seeds.get(c["index"])), "source": c["asset"], "asset": outputs[c["asset"]],
                   "status": item.get("status", "PASSED"),
                   "metrics": self.candidate_metrics(item, bones, inputs.get("grip_window_s"), clearance_items.get(outputs[c["asset"]]),
                                                     center, tolerance)}
            rows.append(row)
        ranked = selection.rank(rows, inputs.get("weights"), grip_on=inputs["grip_on"], swing_on=inputs["swing_on"])
        ranked.update(bones=bones, body_clearance=clearance, retargeter=retargeter)
        picked = ranked["picked"]
        if picked is None:
            raise StepFailed("VALIDATION_FAILED", "ALL_CANDIDATES_FAILED", f"all {len(rows)} candidate(s) fail validation_animation", created=created)
        chosen = next(r for r in ranked["candidates"] if r["index"] == picked["index"])
        diagnostics.append(diag("info", "CANDIDATE_SELECTED", f"candidate {picked['index']} (seed {picked['seed']}) of {len(rows)}: {picked['reason']}",
                                ranking=[(r["index"], r["seed"], r["score"], r["rank"]) for r in ranked["candidates"]]))
        limitations = []
        grip = (chosen["metrics"].get("grip") or {}).get("grip_pct")
        if inputs["grip_on"] and grip is not None and grip < selection.THRESHOLDS["grip_reached_pct"]:
            band = (chosen["metrics"].get("grip") or {}).get("band_cm")
            basis = (f"자루 무기: 대상 간격 {center:g} ± {tolerance:g} cm — 생성 골격 허용 {motion_metrics.GRIP_TOL_CM:g} cm × 팔 길이 비" if spacing
                     else f"검 손잡이: ≤ {motion_metrics.GRIP_CM:g} cm × pelvis scale")
            limitations.append(limitation("GRIP_NOT_REACHED", f"고른 후보의 대상 양손 손목 간격이 파지 띠 {band} cm({basis}) 안인 프레임이 {grip}% — 파지 목표 "
                                          f"{selection.THRESHOLDS['grip_reached_pct']:g}% 미만", "retarget", grip_pct=grip, band_cm=band))
        values = {"asset": chosen["source"], "retargeter": retargeter, "target_rig": target_rig, "selection": ranked}
        review = next((c.get("review") for c in cands if c["index"] == picked["index"]), None)
        if review:
            values["review"] = review  # Job review = 고른 후보의 소스 골격 렌더
        return StepResult(values=values, created=created, diagnostics=diagnostics, limitations=limitations)

    @staticmethod
    def profile_bones(bones: dict) -> list[str]:
        """select 측정 본 — 역할 본 + 머리(손-머리 근접) + 손 아래 자손(양손 겹침 · 손-머리 근접, 계획에 있을 때)."""
        tree = {b for side in ("l", "r") for pair in bones.get(f"hand_tree_{side}") or [] for b in pair}
        head = {bones[motion_metrics.HEAD_ROLE]} if bones.get(motion_metrics.HEAD_ROLE) else set()
        return sorted({bones[k] for k in motion_metrics.ROLES} | head | tree)

    @staticmethod
    def candidate_metrics(item: dict, bones: dict, window, clearance_item: dict | None, spacing_cm: float | None = None,
                          tolerance_cm: float = motion_metrics.GRIP_TOL_CM) -> dict:
        """validate_animation 한 항목 → 후보 지표 {grip, stance, swing, attack, cross, head, clearance, non_grip, breakage, hand_contact} (motion_metrics
        — Kimodo 쪽과 같은 정의). spacing_cm · tolerance_cm = 대상 cm 의 자루 무기 간격 · 허용(계획의 grip_spacing target_cm · tolerance_cm.target —
        파지 판정 띠, motion_metrics.grip_band). 손-머리 근접의 손 점 = 손 트리 본."""
        numeric = item.get("numeric") or {}
        profile = numeric.get("profile") or {}
        positions = profile.get("position_cm") or {}
        times = profile.get("times") or []
        scale = (numeric.get("pelvis_height_cm") or 100.0) / 100.0
        tracks = {role: positions.get(bones[role]) for role in motion_metrics.ROLES}
        tracks[motion_metrics.HEAD_ROLE] = positions.get(bones.get(motion_metrics.HEAD_ROLE) or "")
        hand_points = [positions[b] for b in sorted({child for s in ("l", "r") for _, child in bones.get(f"hand_tree_{s}") or []}) if positions.get(b)]
        win = tuple(window) if window else None
        out = motion_metrics.measure(tracks, times, up=2, scale=scale, window=win, spacing_cm=spacing_cm, tolerance_cm=tolerance_cm, hand_points=hand_points)
        segs = {s: [(positions[a], positions[b]) for a, b in bones.get(f"hand_tree_{s}") or [] if positions.get(a) and positions.get(b)] for s in ("l", "r")}
        out["hand_contact"] = motion_metrics.hand_contact(segs["l"], segs["r"], times, scale) if segs["l"] and segs["r"] else None
        arms = ((item.get("body_clearance") or {}).get("arms")) or []
        worst = max(arms, key=lambda a: a.get("frames_over_penetration_pct") or 0, default=None)
        if clearance_item and clearance_item.get("before"):
            # resolve 면 보정 전(before)이 후보의 관통 — 점수는 보정 전 관통 %
            before = (clearance_item["before"].get("arms")) or []
            worst = max(before, key=lambda a: a.get("frames_over_penetration_pct") or 0, default=worst)
        out["clearance"] = None if worst is None else {"penetration_pct": worst.get("frames_over_penetration_pct"), "arm": worst.get("upper_arm"),
                                                       "depth_max": worst.get("depth_max"), "worst": worst.get("worst"),
                                                       "after_pct": max((a.get("frames_over_penetration_pct") or 0 for a in arms), default=None)}
        if out["clearance"] and tracks.get("hand_l") and tracks.get("hand_r"):
            out["non_grip"] = motion_metrics.non_grip(tracks["hand_l"], tracks["hand_r"], times, scale, out["clearance"]["penetration_pct"],
                                                      (out["clearance"].get("worst") or {}).get("time"), win, spacing_cm, tolerance_cm)
        # 깨짐 벌점 근거 — 상태를 만든 경고를 하위 검사(관통 · 손가락 · 상대 비교 …)까지 모으고, 관통 검사(body_clearance) 밖 경고만 점수에 센다
        # (관통은 clearance 가 센다 — 기록 Job c49a83 에서 관통 경고가 깨짐 0.5 로 이중 계산됐다)
        out["breakage"] = {"status": item.get("status"), "max_deg_per_frame": numeric.get("max_deg_per_frame"),
                           "warnings": sorted({i.get("code") for i in item.get("issues") or [] if i.get("level") == "warning"}),
                           "finger_warnings": sorted({i.get("code") for i in ((item.get("fingers") or {}).get("issues") or []) if i.get("level") == "warning"}),
                           "all_warnings": sorted(_warning_codes(item)),
                           "scored_warnings": sorted(_warning_codes({k: v for k, v in item.items() if k != "body_clearance"}))}
        missing = [bones[r] for r in motion_metrics.ROLES if not tracks.get(r)]
        if missing:
            out["missing_bones"] = missing
        return out

    @staticmethod
    def clearance_notes(items: list[dict]) -> list[dict]:
        """retarget_animations body_clearance(resolve) 결과 → 진단 — 팔마다 보정 프레임 · 최대 각과 관통 프레임 전 → 후, 플러그인 경고는 그대로."""
        notes = []
        for item in items:
            name = (item.get("asset") or "").rsplit("/", 1)[-1].split(".")[0]
            if item.get("skipped_reason"):
                notes.append(diag("warning", "BODY_CLEARANCE_SKIPPED", f"{name}: body clearance not applied ({item['skipped_reason']})"))
                continue
            before = {a["upper_arm"]: a for a in (item.get("before") or {}).get("arms", [])}
            after = {a["upper_arm"]: a for a in (item.get("after") or {}).get("arms", [])}
            parts = [f"{a['upper_arm']} {a['corrected_frames_pct']:g}% frames ≤ {a['deg_max']:g}° (penetration frames "
                     f"{(before.get(a['upper_arm']) or {}).get('frames_over_penetration_pct', '?')}% → {(after.get(a['upper_arm']) or {}).get('frames_over_penetration_pct', '?')}%)"
                     for a in item.get("arms", [])]
            if item.get("modified"):
                notes.append(diag("info", "BODY_CLEARANCE_RESOLVED", f"{name}: " + "; ".join(parts)))
            for issue in item.get("issues", []):
                if issue.get("level") == "warning":
                    notes.append(diag("warning", issue["code"], f"{name}: {issue['message']}"))
        return notes

    @staticmethod
    def _revalidate(editor, asset: str, source: str, target: str, inputs: dict, validation: dict, diagnostics: list[dict],
                    body_clearance: dict | None = None, retargeter: str | None = None) -> dict:
        """retarget_animations 의 내장 검증은 소스 골반 이름을 받지 않는다(기본 'pelvis' — BVH · SOMA 의 'Hips' 를 못 찾아 거리 비율을
        크기 보정하지 않는다, NO_PELVIS_SCALE). 소스 골반을 알면 validate_animation 으로 같은 소스 대비 검증을 다시 해 그 결과를 쓴다.
        body_clearance 면 그 재검증도 팔-몸통 관통을 잰다(내장 검증과 같은 대상 메시 · 리그). 손가락 검사(매핑 안 된 손가락 = 기준 포즈,
        굽힘 방향 · 끝 순서)도 내장 검증처럼 그 리타기터의 매핑으로 한다."""
        params = {"assets": [asset], "sources": [source], "skeleton": target, "source_pelvis": inputs["source_pelvis"]}
        if inputs.get("source_feet"):
            params["source_feet"] = inputs["source_feet"]
        if body_clearance:
            params["body_clearance"] = body_clearance
        if retargeter:
            params["fingers"] = {"retargeter": retargeter}
        try:
            res = editor.require("validate_animation", **params)
        except EditorCallError as err:
            diagnostics.append(diag("warning", "REVALIDATE_FAILED", f"validate_animation with source_pelvis failed ({err.code}) — keeping the "
                                    "retarget_animations validation"))
            return validation
        items = res.get("assets") or []
        order = ["PASSED", "PASSED_WITH_WARNINGS", "NEEDS_REVIEW", "FAILED"]
        status = res.get("status") or max((i.get("status", "PASSED") for i in items), key=lambda s: order.index(s) if s in order else 0, default=None)
        diagnostics.append(diag("info", "VALIDATED_WITH_SOURCE_PELVIS", f"relative checks against {source.rsplit('/', 1)[-1]} use source pelvis "
                                f"'{inputs['source_pelvis']}' — {validation.get('status')} → {status}"))
        return {"status": status, "assets": items}
