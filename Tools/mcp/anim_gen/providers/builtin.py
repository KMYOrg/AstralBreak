"""에디터 Provider — Phase 1 · 2 플러그인 Tool 조합 (지침서 §4 · §10).

- retarget (파이프): import_animation_file · create_ik_rig · create_ik_retargeter(match_existing) · retarget_animations
- existing_motion: search_animations(또는 명시 참조)로 소스를 고른다
- direct_key: apply_animation_edits (op 사전은 Phase 2 그대로)
쓰기는 모두 플러그인 가드(허용 목록 · 전역 더티 · 덮어쓰기 없음) 아래에서 일어난다. 여기서는 순서와 이름만 정한다.
"""
from __future__ import annotations

from .. import bvh
from ..editor import EditorCallError, asset_name, package_path
from ..envelope import diag, limitation
from ..fallback import from_editor_error
from ..request import final_asset_path, root_motion_flag
from .base import PlanBlocked, PlanContext, Provider, RunContext, StepFailed, StepResult, wrap_limitations


def _measured_from_validation(item: dict | None) -> dict:
    numeric = (item or {}).get("numeric") or {}
    return {k: numeric.get(k) for k in ("length", "frame_rate", "frames", "loop") if k in numeric}


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
    """키 직접 편집 — 계획 시점에 소스가 대상 스켈레톤에 있으면 preview 로 op 를 미리 검사한다."""

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
        editor = ctx.editor
        source = ctx.values.get("asset") or ctx.values["source"]
        out = f"{ctx.output_folder}/{ctx.output_name}"
        inputs = ctx.step["inputs"]
        try:
            res = editor.require("apply_animation_edits", source=source, asset_path=out, operations=inputs["operations"],
                                 loop=inputs.get("loop"), root_motion=inputs.get("root_motion"), validate=True, save=ctx.save)
        except EditorCallError as err:
            created = [out] if err.code == "VALIDATION_FAILED" else []  # 검증 실패면 애셋은 미저장으로 남는다
            raise from_editor_error("edit", err, created=created)
        asset = package_path(res["asset_path"])
        validation = res.get("validation")
        measured = {"length": res.get("length"), "frame_rate": res.get("frame_rate"), "frames": res.get("frames")}
        measured.update({k: v for k, v in _measured_from_validation((validation or {}).get("asset")).items() if k == "loop"})
        return StepResult(values={"asset": asset, "skeleton": ctx.request["target_skeleton"], "validation": validation, "measured": measured},
                          created=[asset], limitations=wrap_limitations(res.get("limitations"), "direct_key"))


class RetargetPipe(Provider):
    """공통 리타깃 처리 (§10). 기존 IK Rig · RTG 는 요청이 명시할 때만 재사용하고 메시는 항상 명시한다.

    정면: FK 체인 op 는 전역 회전 델타라(FKChainsOp.cpp:343-350) 소스와 대상의 정면이 다르면 동작이 다른 평면으로 휜다 →
    두 스켈레톤 기준 포즈의 정면(발 영역 + 좌우 체인 교차 확인)을 재 계획에 고정하고, 다르면 create_ik_retargeter(facing_yaw_deg)로 맞춘다.
    """

    def plan_retarget(self, request: dict, source_skeleton: str | None, pctx: PlanContext, *, conditional: bool,
                      from_import: bool = False, source_faces_target: bool = False) -> tuple[dict, list[str]]:
        rt = request["retarget"]
        risks: list[str] = []
        inputs = {"target_mesh": request["target_mesh"], "source_mesh": rt.get("source_mesh"), "source_mesh_source": "argument" if rt.get("source_mesh") else None,
                  "existing_source_rig": rt.get("existing_source_rig"), "existing_target_rig": rt.get("existing_target_rig"),
                  "existing_retargeter": rt.get("existing_retargeter"), "source_pelvis": rt.get("source_pelvis"),
                  "source_chains": rt.get("source_chains"), "ops": rt.get("ops", "match_existing")}
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
        step["expected_limitations"] = facing_lims
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
        return self._import(ctx) if ctx.step["step"] == "import" else self._retarget(ctx)

    def _import(self, ctx: RunContext) -> StepResult:
        editor = ctx.editor
        dest = f"{ctx.work_path}/Import"
        rate = (ctx.step.get("inputs") or {}).get("sample_rate")  # 요청 frame_rate — Interchange 가 그 rate 로 굽는다(없으면 파일 rate)
        try:
            res = editor.require("import_animation_file", file=ctx.values["file"], dest_path=dest, save=ctx.save,
                                 sample_rate=int(round(rate)) if rate else None)
        except EditorCallError as err:
            raise from_editor_error("import", err)
        anims = res.get("animations") or []
        if not anims:
            raise StepFailed("IMPORT_FAILED", "NO_ANIMATION", f"{ctx.values['file']} produced no animation",
                             created=[package_path(p) for p in res.get("imported", [])])
        return StepResult(values={"asset": package_path(anims[0]["asset"]), "skeleton": package_path(res.get("skeleton")),
                                  "mesh": package_path(res.get("mesh"))},
                          created=[package_path(p) for p in res.get("imported", [])])

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
        created: list[str] = []
        try:
            retargeter = inputs.get("existing_retargeter")
            if not retargeter:
                source_rig = inputs.get("existing_source_rig")
                if not source_rig:
                    manual = bool(inputs.get("source_chains"))
                    r = editor.require("create_ik_rig", skeletal_mesh=source_mesh, asset_path=f"{ctx.work_path}/IK_Source",
                                       mode="manual" if manual else "auto", pelvis=inputs.get("source_pelvis"),
                                       chains=inputs.get("source_chains"), save=ctx.save)
                    source_rig = package_path(r["asset_path"])
                    created.append(source_rig)
                target_rig = inputs.get("existing_target_rig")
                if not target_rig:
                    r = editor.require("create_ik_rig", skeletal_mesh=target_mesh, asset_path=f"{ctx.work_path}/IK_Target", save=ctx.save)
                    target_rig = package_path(r["asset_path"])
                    created.append(target_rig)
                r = editor.require("create_ik_retargeter", source_rig=source_rig, target_rig=target_rig, source_mesh=source_mesh,
                                   target_mesh=target_mesh, asset_path=f"{ctx.work_path}/RTG_Retarget", ops=inputs.get("ops", "match_existing"),
                                   facing_yaw_deg=facing["yaw_deg"] or None, save=ctx.save)
                retargeter = package_path(r["asset_path"])
                created.append(retargeter)
            res = editor.require("retarget_animations", retargeter=retargeter, assets=[source_anim], source_mesh=source_mesh,
                                 target_mesh=target_mesh, output_path=ctx.output_folder,
                                 name_rule={"replace_from": asset_name(source_anim), "replace_to": ctx.output_name},
                                 include_referenced=False, validate=True, save=ctx.save)
        except EditorCallError as err:
            if err.code == "VALIDATION_FAILED":
                created.append(f"{ctx.output_folder}/{ctx.output_name}")
            raise from_editor_error("retarget", err, created=created)
        generated = [package_path(g["asset"]) for g in res.get("generated", [])]
        if not generated:
            raise StepFailed("RETARGET_FAILED", "NOTHING_GENERATED", "retarget_animations generated no asset", created=created)
        validation = res.get("validation")
        first = ((validation or {}).get("assets") or [None])[0]
        return StepResult(values={"asset": generated[0], "skeleton": ctx.request["target_skeleton"], "validation": validation,
                                  "measured": _measured_from_validation(first), "retargeter": retargeter, "source_mesh": source_mesh,
                                  "facing": {k: facing.get(k) for k in ("mode", "source", "target", "yaw_deg")}},
                          created=created + generated, diagnostics=diagnostics, limitations=limitations)
