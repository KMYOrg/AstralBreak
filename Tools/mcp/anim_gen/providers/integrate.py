"""포장 · AnimBP 연결 파이프 (지침서 §12 · §14 Phase 7) — 생성물(또는 재사용 애셋) → additive · 몽타주 · BlendSpace → (요청 시에만) AnimBP 복제본 연결.

- 쓰기는 전부 기존 플러그인 Tool 의 옵트인 generation_guard 아래에서 한다(허용 목록 · 덮어쓰기 금지 · 전역 더티 비교 · 검사 뒤 저장 — 규칙의
  원천은 C++ AnimMcpGeneration::FWriteGuard). 여기서는 순서 · 이름 · 자리표시($asset · $montage · $blendspace)만 정한다.
- 운영 AnimBP 에는 쓰지 않는다: 복제본(<work>/<ABP>_Test_<job>)에 적용 · 컴파일 · 스모크 · 시나리오 → 운영 ABP 는 get_anim_blueprint_info(revision) ·
  preview_graph_operations(읽기)만 → Job anim_bp.apply_payload. 실제 적용은 사용자 승인 뒤 사람이 apply_graph_operations(expected_revision) 로 한다.
- 실패는 INTEGRATION_FAILED(폴백 없음 — 다른 Provider 도 같은 포장 · 연결을 한다). 가드 · 연결 오류(UNEXPECTED_DIRTY · EDITOR_GONE …)는 그대로 중단.
  이미 만든 시퀀스는 Job generated_assets 에 남는다(다시 할 때는 그 애셋을 reference_animations 로 — 독립 실행).
"""
from __future__ import annotations

import time

from ..editor import EditorCallError, asset_name, package_path
from ..envelope import EDITOR_TRANSPORT_CODES, FATAL_EDITOR_CODES, AnimGenError, diag, limitation
from ..fallback import from_editor_error
from ..request import bind_placeholders, placeholder_uses
from .base import PlanBlocked, PlanContext, Provider, RunContext, StepFailed, StepResult

INTEGRATION_FAILED = "INTEGRATION_FAILED"
PROMOTION_RULE = "/Game/Animation/Hero/<hero>/<family | Common>/<Locomotion | Actions>/<name>"
SMOKE_POLL_SECONDS = 120.0


def final_sequence(values: dict) -> str | None:
    """$asset — 최종 시퀀스. 만든 것(retarget · edit 결과)이 없으면 재사용 애셋(validate 가 적은 reused, 또는 resolve 의 source)."""
    return values.get("asset") or values.get("reused") or values.get("source")


def bindings_of(values: dict) -> dict:
    out = {"$asset": final_sequence(values)}
    if values.get("montage"):
        out["$montage"] = values["montage"]
    if values.get("blendspace"):
        out["$blendspace"] = values["blendspace"]
    return out


def _failed(step: str, err: EditorCallError, created: list[str] | None = None, reason: str | None = None, **details) -> StepFailed:
    """포장 · 연결 단계의 에디터 오류 → 가드 · 연결 문제는 그대로(중단), 그 밖은 INTEGRATION_FAILED(폴백 없음)."""
    if err.code in EDITOR_TRANSPORT_CODES or err.code in FATAL_EDITOR_CODES:
        return from_editor_error(step, err, created=created)
    message = (err.envelope.get("error") or {}).get("message", "")
    return StepFailed(INTEGRATION_FAILED, reason or err.details.get("reason") or err.code, f"{err.tool} failed in {step}: {err.code} {message[:300]}",
                      fatal=True, editor_error=err.summary(), created=created, **details)


def _find(editor, path: str) -> dict | None:
    """애셋 하나 찾기(레지스트리, 로드 없음) — {class, skeleton} 또는 None."""
    folder, name = path.rsplit("/", 1)
    try:
        items = editor.require("search_animations", query=name, path_prefix=folder, limit=50, **{"class": "all"})["items"]
    except EditorCallError:
        return None
    return next((i for i in items if package_path(i["asset_path"]) == path), None)


def _check_free(editor, path: str, what: str) -> None:
    """출력 이름이 비었는가 — 몽타주 · BlendSpace 도 덮어쓰지 않는다(list_animation_assets 는 BlendSpace 까지 본다)."""
    folder = path.rsplit("/", 1)[0]
    try:
        items = editor.require("list_animation_assets", path_prefix=folder, limit=5000, **{"class": "all"})["assets"]
    except EditorCallError:
        return
    if any(package_path(i["asset_path"]) == path for i in items):
        raise AnimGenError("ASSET_EXISTS", f"{path} already exists — {what} never overwrites; choose another name", reason="OUTPUT_EXISTS", asset=path)


class PackagePipe(Provider):
    """포장 — set_sequence_additive · create_anim_montage → set_montage_sections · create_blendspace (모두 generation_guard)."""

    @staticmethod
    def _skeleton_slots(editor, skeleton: str) -> list[str]:
        info = editor.require("inspect_skeleton", skeleton=skeleton)
        return sorted({s for g in info.get("slot_groups") or [] for s in g.get("slots") or []} | {"DefaultSlot"})

    def plan_steps(self, request: dict, pctx: PlanContext, reuse: str) -> tuple[list[dict], list[str], list[dict]]:
        """reuse: 'reused' | 'produced' | 'unknown' — 앞 사슬이 새 시퀀스를 만드는가(additive 는 제자리 편집이라 재사용 애셋에는 하지 않는다)."""
        pkg = request["package"] or {}
        target = request["target_skeleton"]
        out = request["output_path"]
        steps: list[dict] = []
        risks: list[str] = []
        lims: list[dict] = []
        if not pctx.editor_ok and pkg:
            risks.append("PACKAGE_UNCHECKED_AT_PLAN")
        if "additive" in pkg:
            add = pkg["additive"]
            if reuse == "reused":
                raise PlanBlocked("UNSUPPORTED_REQUEST", "ADDITIVE_ON_REUSED", "package.additive edits the sequence in place (set_sequence_additive) — on a "
                                  "reused asset that would change the original. Give edits (any op) so the chain makes a copy first")
            if reuse == "unknown":
                risks.append("ADDITIVE_TARGET_RESOLVED_AT_RUN")
            ref = add["ref_pose_sequence"]
            if ref and ref != "$asset" and pctx.editor_ok:
                info = _find(pctx.editor, ref)
                if info is None:
                    raise PlanBlocked("UNSUPPORTED_REQUEST", "NO_MATCH", f"additive base pose {ref} not found", missing=[ref])
                if package_path(info.get("skeleton")) != target:
                    raise PlanBlocked("UNSUPPORTED_REQUEST", "SKELETON_MISMATCH", f"additive base pose {ref} is on {package_path(info.get('skeleton'))}, "
                                      f"not {target}", asset=ref)
            steps.append({"step": "package_additive", "provider": self.name, "tool": "set_sequence_additive",
                          "inputs": {"asset": "$asset", **add}, "guard": "generation_guard"})
        if "montage" in pkg:
            mon = pkg["montage"]
            path = f"{out}/{mon['name']}"
            step = {"step": "package_montage", "provider": self.name, "tool": "create_anim_montage → set_montage_sections",
                    "inputs": {"animation": "$asset", "asset_path": path, "slot": mon["slot"], "blend_in": mon["blend_in"], "blend_out": mon["blend_out"],
                               "sections": mon["sections"], "preview_mesh": request["target_mesh"]}, "guard": "generation_guard"}
            if pctx.editor_ok:
                try:
                    slots = self._skeleton_slots(pctx.editor, target)
                except EditorCallError as err:
                    raise PlanBlocked("UNSUPPORTED_REQUEST", err.code, f"inspect_skeleton {target} failed: {err.code}", editor_error=err.summary())
                step["checked"] = {"skeleton_slots": slots}
                if mon["slot"] not in slots:
                    raise PlanBlocked("UNSUPPORTED_REQUEST", "SLOT_NOT_IN_SKELETON", f"slot '{mon['slot']}' is not registered in {target} — add_skeleton_slot "
                                      "edits the shared skeleton (/Game/Assets) and needs the user's approval", slot=mon["slot"], skeleton_slots=slots)
                _check_free(pctx.editor, path, "package.montage")
            steps.append(step)
            lims.append(limitation("NOTIFIES_NOT_ADDED", "몽타주에 프로젝트 노티파이(GameplayEvent 등)를 달지 않았다 — 승격 뒤 정식 몽타주에 astral-ue-montage 스킬로 "
                                   "단다(플러그인 · anim_gen 은 프로젝트 클래스를 모른다)", "package", asset=path))
        if "blendspace" in pkg:
            bs = pkg["blendspace"]
            path = f"{out}/{bs['name']}"
            if pctx.editor_ok:
                for k, sample in enumerate(bs["samples"]):
                    if sample["animation"] == "$asset":
                        continue
                    info = _find(pctx.editor, sample["animation"])
                    if info is None:
                        raise PlanBlocked("UNSUPPORTED_REQUEST", "NO_MATCH", f"blendspace sample {sample['animation']} not found", missing=[sample["animation"]])
                    if package_path(info.get("skeleton")) != target:
                        raise PlanBlocked("UNSUPPORTED_REQUEST", "SKELETON_MISMATCH", f"blendspace sample {k} {sample['animation']} is on "
                                          f"{package_path(info.get('skeleton'))}, not {target}", asset=sample["animation"])
                _check_free(pctx.editor, path, "package.blendspace")
            if not any(s["animation"] == "$asset" for s in bs["samples"]):
                risks.append("BLENDSPACE_WITHOUT_GENERATED_SAMPLE")
            steps.append({"step": "package_blendspace", "provider": self.name, "tool": "create_blendspace",
                          "inputs": {"asset_path": path, "skeleton": target, "dimensions": bs["dimensions"], "axes": bs["axes"], "samples": bs["samples"],
                                     "aim_offset": bs["aim_offset"], "preview_mesh": request["target_mesh"]}, "guard": "generation_guard"})
        return steps, risks, lims

    def run(self, ctx: RunContext) -> StepResult:
        kind = ctx.step["step"]
        inputs = ctx.step["inputs"]
        editor = ctx.editor
        values = ctx.values
        seq = final_sequence(values)
        package = dict(values.get("package") or {})
        if kind == "package_additive":
            if not values.get("asset"):
                raise StepFailed(INTEGRATION_FAILED, "ADDITIVE_ON_REUSED", f"package.additive would edit the reused asset {seq} in place — not done", fatal=True)
            ref = bind_placeholders(inputs.get("ref_pose_sequence"), bindings_of(values))
            try:
                res = editor.require("set_sequence_additive", asset_path=seq, additive_type=inputs["additive_type"], ref_pose_type=inputs["ref_pose_type"],
                                     ref_frame_index=inputs["ref_frame_index"], ref_pose_sequence=ref, save=ctx.save, generation_guard=True)
            except EditorCallError as err:
                raise _failed(kind, err)
            if not res.get("additive_valid"):
                raise StepFailed(INTEGRATION_FAILED, "ADDITIVE_INVALID", f"{seq} is not a valid additive after set_sequence_additive "
                                 f"({res.get('additive_type')} / {res.get('ref_pose_type')})", fatal=True)
            package["additive"] = {"asset": seq, **{k: res.get(k) for k in ("additive_type", "ref_pose_type", "ref_pose_sequence", "ref_frame_index",
                                                                              "additive_valid", "changed")}}
            return StepResult(values={"package": package})
        if kind == "package_montage":
            path = inputs["asset_path"]
            try:
                res = editor.require("create_anim_montage", asset_path=path, animation=seq, slot=inputs["slot"], blend_in=inputs.get("blend_in"),
                                     blend_out=inputs.get("blend_out"), preview_mesh=inputs.get("preview_mesh"), save=ctx.save, generation_guard=True)
            except EditorCallError as err:
                raise _failed(kind, err)
            montage = package_path(res["asset_path"])
            if inputs.get("sections"):
                try:
                    res = editor.require("set_montage_sections", asset_path=montage, sections=inputs["sections"], save=ctx.save, generation_guard=True)
                except EditorCallError as err:
                    raise _failed(kind, err, created=[montage])
            package["montage"] = {"asset": montage, "animation": seq, "slot": inputs["slot"], "length": res.get("length"),
                                  "sections": [{k: s.get(k) for k in ("name", "start", "next")} for s in res.get("sections") or []],
                                  "blend_in": res.get("blend_in"), "blend_out": res.get("blend_out")}
            return StepResult(values={"montage": montage, "package": package}, created=[montage], deliverables=[montage])
        if kind == "package_blendspace":
            samples = bind_placeholders(inputs["samples"], bindings_of(values))
            try:
                res = editor.require("create_blendspace", asset_path=inputs["asset_path"], skeleton=inputs["skeleton"], dimensions=inputs["dimensions"],
                                     axes=inputs["axes"], samples=samples, aim_offset=inputs["aim_offset"], preview_mesh=inputs.get("preview_mesh"),
                                     save=ctx.save, generation_guard=True)
            except EditorCallError as err:
                raise _failed(kind, err)
            blendspace = package_path(res["asset_path"])
            package["blendspace"] = {"asset": blendspace, "class": res.get("class"), "samples": samples, "sample_count": res.get("sample_count")}
            return StepResult(values={"blendspace": blendspace, "package": package}, created=[blendspace], deliverables=[blendspace])
        raise StepFailed("UNSUPPORTED_REQUEST", "NOT_ROUTABLE", f"package has no step '{kind}'")


class AnimBpPipe(Provider):
    """AnimBP 연결 — 복제본 검증(anim_bp_test) · 운영 AnimBP 미리보기(anim_bp_prepare). 운영 AnimBP 에는 쓰지 않는다."""

    def plan_steps(self, request: dict, pctx: PlanContext) -> tuple[list[dict], list[str], list[dict]]:
        abp = request["anim_bp"]
        target = request["target_skeleton"]
        ops = abp["operations"]
        risks: list[str] = []
        lims: list[dict] = []
        at_run = bool(placeholder_uses(ops))
        operational = {"asset_path": abp["asset_path"], "revision": None, "skeleton": None}
        preview = None
        if pctx.editor_ok:
            try:
                info = pctx.editor.require("get_anim_blueprint_info", asset_path=abp["asset_path"])
            except EditorCallError as err:
                reason = "ANIM_BP_NOT_FOUND" if err.code == "ASSET_NOT_FOUND" else err.code
                raise PlanBlocked("UNSUPPORTED_REQUEST", reason, f"anim_bp {abp['asset_path']}: {err.code}", editor_error=err.summary())
            skeleton = package_path(info.get("target_skeleton"))
            if skeleton != target:
                raise PlanBlocked("UNSUPPORTED_REQUEST", "SKELETON_MISMATCH", f"{abp['asset_path']} targets {skeleton}, the request {target}",
                                  anim_bp_skeleton=skeleton)
            operational.update(revision=info.get("revision"), skeleton=skeleton)
            if ops and not at_run:
                # 자리표시 없는 op 는 운영 AnimBP 로 지금 미리 본다(읽기 — 그래프 불변)
                env = pctx.editor.call("preview_graph_operations", asset_path=abp["asset_path"], operations=ops)
                if not env.get("ok"):
                    err = EditorCallError("preview_graph_operations", env)
                    raise PlanBlocked("UNSUPPORTED_REQUEST", "PREVIEW_INVALID", f"preview_graph_operations rejected the operations: {err.code}",
                                      editor_error=err.summary())
                result = env["result"]
                preview = {"valid": result.get("valid"), "planned": result.get("planned")}
                if not result.get("valid"):
                    raise PlanBlocked("UNSUPPORTED_REQUEST", "PREVIEW_INVALID", "preview_graph_operations: the operations are not valid on the AnimBP",
                                      planned=result.get("planned"))
        else:
            risks.append("ANIM_BP_UNCHECKED_AT_PLAN")
        if at_run:
            risks.append("ANIM_BP_OPS_RESOLVED_AT_RUN")
        scenario = abp["scenario"]
        if scenario and (scenario.get("expect") or {}).get("slots_active") and not scenario.get("montage"):
            risks.append("SCENARIO_SLOTS_WITHOUT_MONTAGE")
        name = asset_name(abp["asset_path"])
        steps = [
            {"step": "anim_bp_test", "provider": self.name,
             "tool": "duplicate_animation_blueprint → apply_graph_operations(compile) → run_automation_tests(smoke) → run_anim_scenario",
             "inputs": {"source": abp["asset_path"], "test_copy": f"<work>/{name}_Test_<job>", "operations": ops, "smoke": abp["smoke"],
                        "scenario": scenario, "mesh": request["target_mesh"]},
             "operational": operational, "preview": preview, "guard": "generation_guard"},
            {"step": "anim_bp_prepare", "provider": self.name, "tool": "get_anim_blueprint_info → preview_graph_operations (production AnimBP — read only)",
             "inputs": {"asset_path": abp["asset_path"], "operations": ops}, "operational": operational},
        ]
        if ops:
            lims.append(limitation("ANIM_BP_APPLY_PENDING", f"운영 AnimBP {abp['asset_path']} 는 바꾸지 않았다 — 복제본에서 검증한 연산을 Job anim_bp.apply_payload "
                                   "(expected_revision 포함)로 남긴다. 적용은 사용자 승인 뒤: 승격(promote_animation) → 바인딩을 정식 경로로 → "
                                   "apply_graph_operations(expected_revision)", "anim_bp", asset=abp["asset_path"]))
        return steps, risks, lims

    def run(self, ctx: RunContext) -> StepResult:
        if ctx.step["step"] == "anim_bp_prepare":
            return self._prepare(ctx)
        return self._test(ctx)

    # ---- 복제본 검증 ----
    def _test(self, ctx: RunContext) -> StepResult:
        editor = ctx.editor
        inputs = ctx.step["inputs"]
        source = inputs["source"]
        copy = f"{ctx.work_path}/{asset_name(source)}_Test_{ctx.job_id[-6:]}A{ctx.attempt}"
        bindings = bindings_of(ctx.values)
        try:
            dup = editor.require("duplicate_animation_blueprint", source_path=source, dest_path=copy, preserve_node_guids=True, save=ctx.save,
                                 generation_guard=True)
        except EditorCallError as err:
            raise _failed("anim_bp_test", err)
        copy = package_path(dup["asset_path"]) if dup.get("asset_path") else copy
        created = [copy]
        ops = bind_placeholders(inputs["operations"], bindings)
        test: dict = {"copy": copy, "source_revision": dup.get("source_revision"), "guard": dup.get("guard")}
        if ops:
            try:
                applied = editor.require("apply_graph_operations", asset_path=copy, operations=ops, compile=True, save=ctx.save, generation_guard=True)
            except EditorCallError as err:
                raise _failed("anim_bp_test", err, created=created, reason=err.details.get("reason") or ("BAD_OPERATIONS" if err.code == "BAD_REQUEST" else None))
            compiled = applied.get("compile") or {}
            test["apply"] = {"revision_before": applied.get("revision_before"), "revision_after": applied.get("revision_after"),
                             "applied": applied.get("applied"), "compile": {k: compiled.get(k) for k in ("ok", "num_errors", "num_warnings")},
                             "saved": applied.get("saved"), "guard": applied.get("guard")}
        else:
            try:
                # 연산 없음 = 재생 확인만 — 복제본(후보 경로)만 컴파일하고 Job save 를 따른다
                compiled = editor.require("compile_animation_blueprint", asset_path=copy, save_on_success=ctx.save)
            except EditorCallError as err:
                raise _failed("anim_bp_test", err, created=created)
            test["apply"] = None
            test["compile"] = {k: compiled.get(k) for k in ("ok", "num_errors", "num_warnings")}
        if not compiled.get("ok", False) or compiled.get("num_errors"):
            raise StepFailed(INTEGRATION_FAILED, "COMPILE_FAILED", f"{copy} does not compile ({compiled.get('num_errors')} error(s))", fatal=True, created=created,
                             messages=(compiled.get("messages") or [])[:20], test=test)
        if inputs.get("smoke", True):
            test["smoke"] = self._smoke(editor, copy, ctx.values.get("montage"), created, test)
        scenario = inputs.get("scenario")
        if scenario:
            params = bind_placeholders({k: v for k, v in scenario.items() if v is not None}, bindings)
            params.setdefault("mesh", inputs.get("mesh"))
            try:
                started = editor.require("run_anim_scenario", asset_path=copy, **params)
            except EditorCallError as err:
                raise _failed("anim_bp_test", err, created=created, test=test)
            handle = {"job_id": started.get("job_id"), "copy": copy, "test": test, "created": created, "bindings": bindings, "operations": ops,
                      "scenario": params}
            return StepResult(pending=handle, created=created)
        return self._test_result(ctx, copy, test, created, bindings, ops)

    def _smoke(self, editor, copy: str, montage: str | None, created: list[str], test: dict) -> list[dict]:
        """스모크 — 복제본 AnimBP(+ 만든 몽타주). 테스트 이름은 애셋 이름이라 복제본 이름에 Job 꼬리를 붙여 겹치지 않게 했다."""
        filters = [f"AnimGraphMcp.Smoke.AnimBlueprint.{asset_name(copy)}"] + ([f"AnimGraphMcp.Smoke.AnimMontage.{asset_name(montage)}"] if montage else [])
        out = []
        for flt in filters:
            try:
                res = editor.require("run_automation_tests", filter=flt, timeout=120)
                deadline = time.monotonic() + SMOKE_POLL_SECONDS
                while not res.get("done") and time.monotonic() < deadline:
                    time.sleep(1.0)
                    res = editor.require("poll_automation_tests", job_id=res["job_id"])
            except EditorCallError as err:
                raise _failed("anim_bp_test", err, created=created, test=test)
            item = {"filter": flt, "total": res.get("total"), "passed": res.get("passed"), "failed": res.get("failed"),
                    "warnings": [w for t in res.get("tests") or [] for w in t.get("warnings") or []][:10],
                    "errors": [e for t in res.get("tests") or [] for e in t.get("errors") or []][:10]}
            out.append(item)
            if not res.get("done"):
                raise StepFailed(INTEGRATION_FAILED, "SMOKE_TIMEOUT", f"{flt} did not finish in {SMOKE_POLL_SECONDS:g}s", fatal=True, created=created, test=test)
            if not res.get("total"):
                raise StepFailed(INTEGRATION_FAILED, "SMOKE_NOT_FOUND", f"no smoke test matches {flt} (is the copy under [AnimGraphMcp] SmokeTestPaths?)",
                                 fatal=True, created=created, test={**test, "smoke": out})
            if res.get("failed"):
                raise StepFailed(INTEGRATION_FAILED, "SMOKE_FAILED", f"{flt}: {item['errors'][:1]}", fatal=True, created=created, test={**test, "smoke": out})
        return out

    def poll(self, ctx: RunContext, handle: dict) -> StepResult | None:
        try:
            res = ctx.editor.require("poll_automation_tests", job_id=handle["job_id"])
        except EditorCallError as err:
            raise _failed("anim_bp_test", err, created=handle["created"], test=handle["test"])
        if not res.get("done"):
            return None
        tests = res.get("tests") or [{}]
        first = tests[0]
        scenario = {"job_id": handle["job_id"], "params": handle.get("scenario"), "ok": bool(res.get("ok")), "state": first.get("state"),
                    "observed": first.get("observed"), "errors": first.get("errors") or [], "warnings": (first.get("warnings") or [])[:10]}
        test = {**handle["test"], "scenario": scenario}
        if not res.get("ok"):
            raise StepFailed(INTEGRATION_FAILED, "SCENARIO_FAILED", f"run_anim_scenario on {handle['copy']}: {(scenario['errors'] or [first.get('state')])[0]}",
                             fatal=True, created=handle["created"], observed=scenario["observed"], test=test)
        return self._test_result(ctx, handle["copy"], test, handle["created"], handle["bindings"], handle["operations"])

    def _test_result(self, ctx: RunContext, copy: str, test: dict, created: list[str], bindings: dict, ops: list[dict]) -> StepResult:
        anim_bp = {"target": ctx.step["inputs"]["source"], "test_copy": copy, "bindings": bindings, "operations": ops, "test": test}
        return StepResult(values={"anim_bp": anim_bp}, created=created)

    # ---- 운영 AnimBP: revision · 미리보기(읽기만) → 적용 페이로드 ----
    def _prepare(self, ctx: RunContext) -> StepResult:
        editor = ctx.editor
        inputs = ctx.step["inputs"]
        source = inputs["asset_path"]
        anim_bp = dict(ctx.values.get("anim_bp") or {"target": source})
        planned_revision = (ctx.step.get("operational") or {}).get("revision")
        ops = anim_bp.get("operations")
        if ops is None:
            ops = bind_placeholders(inputs["operations"], bindings_of(ctx.values))
        try:
            info = editor.require("get_anim_blueprint_info", asset_path=source)
        except EditorCallError as err:
            raise _failed("anim_bp_prepare", err)
        revision = info.get("revision")
        diagnostics = []
        if planned_revision and revision != planned_revision:
            diagnostics.append(diag("warning", "ANIM_BP_CHANGED_SINCE_PLAN", f"{source} revision changed since the plan ({planned_revision} → {revision}) — "
                                    "the apply payload uses the current one"))
        operational = {"asset_path": source, "revision": revision, "revision_at_plan": planned_revision, "preview": None}
        if ops:
            try:
                preview = editor.require("preview_graph_operations", asset_path=source, operations=ops)
            except EditorCallError as err:
                raise _failed("anim_bp_prepare", err, reason="PREVIEW_INVALID")
            operational["preview"] = {"valid": preview.get("valid"), "planned": preview.get("planned")}
            if not preview.get("valid"):
                raise StepFailed(INTEGRATION_FAILED, "PREVIEW_INVALID", f"the operations validated on the copy are not valid on {source}", fatal=True,
                                 planned=preview.get("planned"))
            # 사람이 승인 뒤 그대로 부를 수 있는 모양 — 바인딩이 후보 경로를 가리키므로 승격 뒤에는 정식 경로로 바꿔 다시 미리 본다(§12)
            anim_bp["apply_payload"] = {"tool": "apply_graph_operations", "asset_path": source, "operations": ops, "expected_revision": revision,
                                        "compile": True, "save": True, "generation_guard": False, "rebind_after_promotion": True}
        anim_bp["operational"] = operational
        return StepResult(values={"anim_bp": anim_bp}, diagnostics=diagnostics)


def promotion_proposal(request: dict, generated: list[str], promotion_paths: list[str] | None) -> dict:
    """승격 제안(플러그인은 이름 규칙을 모른다 — §3.1-4). 규칙 .claude/plans/anim-asset-naming.md: idle · locomotion → Locomotion, 그 밖 Actions."""
    hero = request.get("hero")
    if not hero:
        return {"rule": PROMOTION_RULE, "assets": [], "note": "hero 가 없어 정식 경로를 제안하지 않는다"}
    root = ((promotion_paths or ["/Game/Animation/Hero/"])[0]).rstrip("/")
    purpose = "Locomotion" if request["motion_category"] in ("idle", "locomotion") else "Actions"
    folder = f"{root}/{hero}/{request.get('family') or 'Common'}/{purpose}"
    return {"rule": PROMOTION_RULE, "folder": folder, "assets": [{"source": a, "dest": f"{folder}/{asset_name(a)}"} for a in generated],
            "how": "promote_animation(assets, dry_run=true) → 사용자 확인 → confirm=true (한 번에 — 서로 참조하는 애셋은 같은 배치로)"}
