"""규칙 표 라우터 (지침서 §5, 개정 6). 점수 모델이 아니라 요청 유형 × 정책 모드 × Provider 가용성의 표다.

계획은 실행하지 않는다: 읽기 전용 에디터 호출(get_editor_status · inspect_skeleton · search_animations ·
preview_animation_edits)로 고른 소스·메시를 계획에 고정해 보여 주고, 유료 호출은 하지 않는다.
"""
from __future__ import annotations

from .editor import EditorCallError, is_under, package_path
from .envelope import AnimGenError, diag, limitation
from .policy import FREE_FIRST, QUALITY_FIRST, paid_block_reason, resolve_mode
from .providers.base import PlanBlocked, PlanContext
from .request import CONSTRAINT_LIMITATIONS, final_asset_path
from .store import new_id, now_iso

_STANDARD = {
    FREE_FIRST: ["existing_motion", "local_ai", "external.meshy"],
    QUALITY_FIRST: ["existing_motion", "external.meshy", "local_ai"],
}
# 모드별 순서. FREE_ONLY 는 FREE_FIRST 순서를 쓰고 유료 Provider 는 제외 목록으로 간다
ORDERS = {
    "idle": _STANDARD,
    "locomotion": _STANDARD,
    "weapon_action": _STANDARD,
    "full_body_new": {
        FREE_FIRST: ["local_ai", "external.meshy", "existing_motion"],
        QUALITY_FIRST: ["external.meshy", "local_ai", "existing_motion"],
    },
}
# 이 요청 유형에서 기존 모션은 근사 후보다
APPROXIMATE = {"full_body_new": {"existing_motion"}}
EXISTING_CHAIN = {"existing_motion", "direct_key"}


def provider_order(category: str, mode: str, explicit: str, motion_file: bool = False) -> list[str]:
    """motion_file 이 있으면 그 파일을 쓰는 blender 가 맨 앞(요청이 소스를 준 것) — 없으면 표 그대로(Phase 4)."""
    if explicit and explicit != "auto":
        return [explicit]
    order = list(ORDERS[category][QUALITY_FIRST if mode == QUALITY_FIRST else FREE_FIRST])
    return ["blender", *order] if motion_file else order


def _dedupe(items: list[dict]) -> list[dict]:
    """같은 코드는 하나만 (요청 유형과 제약이 같은 한계를 낼 수 있다). 처리 못 하는 제약은 제약마다 하나."""
    seen, out = set(), []
    for item in items:
        key = (item["code"], item.get("constraint")) if item["code"] == "CONSTRAINT_UNSUPPORTED" else item["code"]
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def expected_limitations(request: dict, provider, *, reuse: bool, resolved: dict | None, has_edit: bool, preview: dict | None) -> list[dict]:
    out: list[dict] = []
    category = request["motion_category"]
    if category == "weapon_action":
        out.append(limitation("GRIP_NOT_VALIDATED", "무기 파지 오차 검증·보정은 Phase 8 — 손 위치를 사람이 확인해야 한다", "router"))
        if provider.generates:
            out.append(limitation("DRAFT_NEEDS_CLEANUP", "AI 생성 무기 동작은 초안 — 보정 전에는 정식 애셋으로 쓰지 않는다", "router"))
    if provider.name in APPROXIMATE.get(category, ()):
        out.append(limitation("NOT_NEW_MOTION", "새 전신 동작을 만들지 않고 가장 가까운 기존 모션을 쓴다", "router"))
        out.append(limitation("SEGMENTED_PLAN_SUGGESTED", "품질이 부족하면 세그먼트 방식(Phase 8)으로 나눠 만든다", "router"))
    for name, on in (request["constraints"] or {}).items():
        if not on:
            continue
        code = CONSTRAINT_LIMITATIONS.get(name)
        if code:
            out.append(limitation(code, f"제약 '{name}' 은 검증·보정하지 않는다(Phase 8)", "router", constraint=name))
        else:
            out.append(limitation("CONSTRAINT_UNSUPPORTED", f"제약 '{name}' 을 처리하는 Provider 가 없다", "router", constraint=name))
    if reuse:
        out.append(limitation("REUSED_EXISTING", "대상 스켈레톤의 기존 애셋을 그대로 쓴다 — 새 애셋을 만들지 않는다", "router"))
    if request["root_motion_mode"] != "auto" and not has_edit:
        out.append(limitation("ROOT_MOTION_UNCHANGED", "root_motion_mode 는 direct_key 단계에서만 쓴다 — 소스 설정 그대로", "router"))
    # 계획 시점에 알 수 있는 길이·fps 차이 (실행 후 측정값으로 다시 적는다)
    measured = preview if preview else (resolved if resolved and not has_edit else None)
    if measured:
        frame_rate = measured.get("frame_rate")
        if request["frame_rate"] and frame_rate and abs(frame_rate - request["frame_rate"]) > 0.01:
            out.append(limitation("FRAME_RATE_MISMATCH", f"출력 fps = 주 소스 {frame_rate} (요청 {request['frame_rate']})", "router"))
        length = measured.get("length")
        if request["duration_seconds"] and length and abs(length - request["duration_seconds"]) > 1.0 / (frame_rate or 30.0) + 1e-6:
            out.append(limitation("DURATION_MISMATCH", f"길이 {length}초 (요청 {request['duration_seconds']}초) — retime op 로 맞출 수 있다", "router",
                                  length=length, requested=request["duration_seconds"]))
    return _dedupe(out)


def _without_convert(request: dict, name: str) -> list[dict]:
    """변환 단계(blender)가 없는 경로 — 보정 op 는 돌 곳이 없어 후보를 막고, 렌더 비교는 하지 않는다는 한계를 단다."""
    ops = [o["op"] for o in request["fix"]["ops"]]
    if ops:
        raise PlanBlocked("UNSUPPORTED_REQUEST", "UNSUPPORTED_FIX_OP", f"fix ops {ops} run in the blender convert step — the {name} route has none",
                          ops=ops)
    if request["review"]:
        return [limitation("REVIEW_NOT_RENDERED", "프레임 렌더 비교(review.render)는 blender 변환 단계에서만 한다 — 이 경로는 렌더하지 않는다", "router")]
    return []


def _validate_step(reuse: bool) -> dict:
    return {"step": "validate", "provider": "validation",
            "tool": "validate_animation" if reuse else "validation of the producing step (retarget_animations / apply_animation_edits)"}


def _chain(name: str, request: dict, registry, pctx: PlanContext) -> tuple[list[dict], list[str], list[dict]]:
    provider = registry.get(name)
    retarget = registry.get("retarget")
    direct_key = registry.get("direct_key")
    target = request["target_skeleton"]
    risks: list[str] = []
    if name in EXISTING_CHAIN:
        if name == "direct_key" and not (request["edits"] and request["reference_animations"]):
            raise PlanBlocked("UNSUPPORTED_REQUEST", "MISSING_INPUT", "provider direct_key needs edits.operations and a source "
                              "(edits.source or reference_animations)", missing=["edits", "reference_animations"])
        no_review = _without_convert(request, name)
        resolve = registry.get("existing_motion").plan_resolve(request, pctx)
        steps = [resolve]
        resolved = resolve["resolved"]
        needs_retarget = None if resolved is None else resolved["skeleton"] != target
        if resolved is None:
            risks.append("UNRESOLVED_AT_PLAN")
        elif request["search"] and not request["reference_animations"]:
            risks.append("SEARCH_PICKED_TOP")
        retarget_lims: list[dict] = []
        if needs_retarget is not False:
            step, r = retarget.plan_retarget(request, resolved["skeleton"] if resolved else None, pctx, conditional=needs_retarget is None)
            retarget_lims = step.pop("expected_limitations", [])
            steps.append(step)
            risks += r
        preview = None
        if request["edits"]:
            step = direct_key.plan_edit(request, resolved["source"] if needs_retarget is False else None, pctx)
            preview = step.get("preview")
            if preview is None:
                risks.append("EDITS_NOT_PREVIEWED")
            steps.append(step)
        reuse = needs_retarget is False and not request["edits"]
        steps.append(_validate_step(reuse))
        lims = expected_limitations(request, provider, reuse=reuse, resolved=resolved, has_edit=bool(request["edits"]), preview=preview)
        return steps, risks, _dedupe(lims + retarget_lims + no_review)
    converts = hasattr(provider, "plan_convert")
    if provider.generates or converts:
        # 생성(AI) 또는 파일 변환(blender) → FBX → import → retarget 파이프
        first = provider.plan_convert(request, pctx) if converts else provider.plan_generate(request, pctx)
        steps = [first]
        last = first
        if first.pop("output", None) == "bvh":
            # 생성 결과가 BVH(local_ai) — Phase 4 blender 변환을 잇는다(대상 정면 · 바닥 · 더미 스킨 메시). 파일은 실행 때 생긴다
            blender = registry.get("blender")
            state = blender.state(pctx.policy) if pctx.policy is not None else {"available": True}
            if not state["available"]:
                why = state["unavailable_reason"]
                raise PlanBlocked("PROVIDER_UNAVAILABLE", "DEPENDS_ON_BLENDER", f"{name} writes BVH and the blender converter is not available "
                                  f"({why['reason']})", blender=why)
            last = blender.plan_convert_generated(request, first.pop("bvh"), pctx)
            steps.append(last)
        no_review = [] if converts or last is not first else _without_convert(request, name)
        # 리샘플 rate: 변환 단계가 정한 값(프레임 경계에 맞춘 경우만) 또는 요청 frame_rate
        rate = last.pop("sample_rate") if "sample_rate" in last else request["frame_rate"]
        steps.append({"step": "import", "provider": "retarget", "tool": "import_animation_file", "inputs": {"dest": "<work>/Import", "sample_rate": rate}})
        # blender 는 변환 단계에서 대상 정면으로 돌린다 — 생성 결과(FBX)는 임포트 뒤에 정면을 잰다
        step, r = retarget.plan_retarget(request, None, pctx, conditional=False, from_import=True, source_faces_target=converts or last is not first)
        defaults = first.pop("retarget_defaults", None) or {}
        filled = [k for k, v in defaults.items() if not step["inputs"].get(k)]
        for key in filled:
            # 생성 Provider 는 자기 스켈레톤을 안다(SOMA 수동 체인 · 골반 · 발) — 요청이 주지 않은 것만 채운다
            step["inputs"][key] = defaults[key]
        if filled:
            step["inputs"]["defaults_from"] = {"provider": name, "keys": filled}
        retarget_lims = step.pop("expected_limitations", [])
        steps.append(step)
        risks += first.pop("risks", []) + (last.pop("risks", []) if last is not first else []) + r
        if request["edits"]:
            steps.append(direct_key.plan_edit(request, None, pctx))
            risks.append("EDITS_NOT_PREVIEWED")
        steps.append(_validate_step(False))
        lims = expected_limitations(request, provider, reuse=False, resolved=first.pop("measured", None), has_edit=bool(request["edits"]), preview=None)
        lims = _dedupe(lims + first.pop("expected_limitations", []) + (last.pop("expected_limitations", []) if last is not first else [])
                       + retarget_lims + no_review)
        return steps, risks, lims
    raise PlanBlocked("UNSUPPORTED_REQUEST", "NOT_ROUTABLE", f"{name} is not a generation route (pipe or post-process only)")


def _reuse_state(steps: list[dict]) -> str:
    """앞 사슬이 새 시퀀스를 만드는가 — 'produced' | 'reused'(대상 스켈레톤의 기존 애셋 그대로) | 'unknown'(계획 때 소스를 몰라 리타깃이 조건부)."""
    if any(s["step"] in ("edit", "import", "generate", "convert") or (s["step"] == "retarget" and not s.get("conditional")) for s in steps):
        return "produced"
    return "unknown" if any(s["step"] == "retarget" for s in steps) else "reused"


def _integrate(request: dict, registry, pctx: PlanContext, steps: list[dict], risks: list[str], lims: list[dict],
               cache: dict) -> tuple[list[dict], list[str], list[dict]]:
    """Phase 7 — 모든 후보의 검증 뒤에 공통으로 붙는 포장(package_*) · AnimBP 연결(anim_bp_test · anim_bp_prepare) 단계.
    integrate_anim_bp 가 거짓이면 anim_bp 단계가 없다(AnimBP 호출 0). 같은 계획 안에서는 결과를 한 번만 계산한다(후보마다 같다)."""
    if not (request["package"] or request["anim_bp"]):
        return steps, risks, lims
    reuse = _reuse_state(steps)
    key = ("package", reuse)
    if key not in cache:
        try:
            cache[key] = registry.get("package").plan_steps(request, pctx, reuse) if request["package"] else ([], [], [])
        except PlanBlocked as blocked:
            cache[key] = blocked
    if "anim_bp" not in cache:
        try:
            cache["anim_bp"] = registry.get("anim_bp").plan_steps(request, pctx) if request["anim_bp"] else ([], [], [])
        except PlanBlocked as blocked:
            cache["anim_bp"] = blocked
    out_steps, out_risks, out_lims = list(steps), list(risks), list(lims)
    for part in (cache[key], cache["anim_bp"]):
        if isinstance(part, PlanBlocked):
            raise part
        s, r, lm = part
        out_steps += [dict(x) for x in s]
        out_risks += r
        out_lims += lm
    return out_steps, out_risks, _dedupe(out_lims)


def _chain_names(steps: list[dict]) -> list[str]:
    names: list[str] = []
    for s in steps:
        if s["provider"] != "validation" and s["provider"] not in names:
            names.append(s["provider"])
    return names


def check_output(request: dict, settings: dict | None, editor, editor_ok: bool, diagnostics: list[dict]) -> list[str] | None:
    """출력 경로를 ini 허용 목록(get_editor_status.generation.output_paths)으로 미리 검사한다. 최종 기준은 C++."""
    if not settings:
        diagnostics.append(diag("warning", "OUTPUT_PATH_UNCHECKED", "Editor unreachable — output_path is checked at generation time"))
        return None
    roots = (settings.get("generation") or {}).get("output_paths") or []
    if not is_under(request["output_path"], roots):
        raise AnimGenError("OUTPUT_PATH_NOT_ALLOWED", f"output_path {request['output_path']} is outside [AnimGraphMcp] GenerationOutputPaths",
                           reason="OUTSIDE_ALLOW_LIST", allowed=roots)
    if editor_ok:
        final = final_asset_path(request)
        try:
            items = editor.require("search_animations", query=request["animation_name"], path_prefix=request["output_path"], limit=50,
                                   **{"class": "all"})["items"]
        except EditorCallError:
            items = []
        if any(package_path(i["asset_path"]) == final for i in items):
            raise AnimGenError("ASSET_EXISTS", f"{final} already exists — generation never overwrites; choose another animation_name",
                               reason="OUTPUT_EXISTS", asset=final)
    return roots


def build_plan(request: dict, policy: dict, registry, editor, diagnostics: list[dict]) -> dict:
    unknown = sorted(name for name in request["generation"]["options"] if not registry.has(name))
    if unknown:
        raise AnimGenError("BAD_REQUEST", f"request.generation.options names unknown provider(s) {unknown}", reason="UNKNOWN_PROVIDER",
                           field="generation.options", known=registry.names())
    mode, mode_diags = resolve_mode(policy, request["generation_policy"])
    diagnostics += mode_diags
    block = paid_block_reason(policy, mode)
    settings = editor.status()
    editor_ok = settings is not None
    if not editor_ok:
        diagnostics.append(diag("warning", "EDITOR_UNAVAILABLE", "Editor unreachable — sources are resolved when the job runs"))
    output_paths = check_output(request, settings, editor, editor_ok, diagnostics)
    explicit = request["provider"] if request["provider"] != "auto" else None
    if explicit:
        provider = registry.get(explicit)
        if provider.manifest.get("role") == "pipe":
            raise AnimGenError("BAD_REQUEST", f"'{explicit}' is a pipe, not a provider", reason="PIPE_NOT_PROVIDER")
        diagnostics.append(diag("info", "FALLBACK_DISABLED_EXPLICIT_PROVIDER", f"provider '{explicit}' was requested — no fallback to others"))
    order = provider_order(request["motion_category"], mode, request["provider"], motion_file=bool(request["motion_file"]))
    pctx = PlanContext(editor=editor, editor_ok=editor_ok, request=request, diagnostics=diagnostics, settings=settings, policy=policy)
    candidates, excluded = [], []
    integration_cache: dict = {}
    for name in order:
        provider = registry.get(name)
        state = provider.state(policy)

        def exclude(cause: str, reason: str | None, message: str, **details):
            excluded.append({"provider": name, "cause": cause, "reason": reason, "message": message, "state": state, **details})

        if provider.paid and block:
            exclude("APPROVAL_REQUIRED", block, f"{name} is paid and the policy blocks paid providers ({block})")
            continue
        if not state["available"]:
            why = state["unavailable_reason"]
            exclude(why["cause"], why["reason"], f"{name} is not available ({why['reason']})")
            continue
        max_duration = provider.manifest.get("max_duration_seconds")
        if max_duration and request["duration_seconds"] and request["duration_seconds"] > max_duration:
            exclude("UNSUPPORTED_REQUEST", "DURATION_OVER_MAX", f"{name} supports up to {max_duration}s")
            continue
        estimate = provider.estimate(request, policy)
        if provider.paid and not estimate["cost_known"]:
            exclude("COST_UNKNOWN", estimate.get("basis"), f"{name}: the cost cannot be confirmed, so it is never run (§6)")
            continue
        try:
            steps, risks, lims = _chain(name, request, registry, pctx)
            steps, risks, lims = _integrate(request, registry, pctx, steps, risks, lims, integration_cache)
        except PlanBlocked as blocked:
            exclude(blocked.cause, blocked.reason, blocked.message, **blocked.details)
            continue
        candidates.append({
            "index": len(candidates), "provider": name, "role": "approximate" if name in APPROXIMATE.get(request["motion_category"], ()) else "primary",
            "chain": _chain_names(steps), "steps": steps, "paid": provider.paid, "cost_known": estimate["cost_known"],
            "estimated_cost_usd": estimate["estimate_usd"], "estimate_basis": estimate.get("basis"), "needs_approval": provider.paid,
            **({"estimated_credits": estimate["credits"]} if estimate.get("credits") is not None else {}),
            "risks": risks, "expected_limitations": lims,
        })
    return {
        "plan_id": new_id("plan"), "created_at": now_iso(), "request": request,
        "policy": {"mode": policy["mode"], "effective_mode": mode, "paid_allowed": block is None, "paid_block_reason": block,
                   "allow_fallback": policy["execution"]["allow_fallback"], "max_generation_attempts": policy["execution"]["max_generation_attempts"]},
        "order": order, "fallback": explicit is None, "candidates": candidates, "excluded": excluded,
        "executable": bool(candidates), "editor_checked": editor_ok, "output_paths": output_paths,
        "final_asset": final_asset_path(request),
        # Phase 7 — 승격 제안의 루트(ini PromotionPaths, get_editor_status). 이동은 promote_animation 을 사용자 확인 뒤에
        "promotion_paths": ((settings or {}).get("generation") or {}).get("promotion_paths"),
    }
