"""대상 메시 캡처 파이프 (지침서 §13 시각 · §14 Phase 8 '8-2') — 최종 시퀀스를 대상 메시 모습으로 찍어 Persona 없이 판정할 근거를 남긴다.

- 플러그인 capture_animation(C++) 이 임시 프리뷰 월드에서 행(시각) × 뷰(정면 · 측면 정사영) PNG · 시트 · (render 가 있으면) 소스 골격 칸을
  붙인 비교 시트 · 연속 프레임을 ini CaptureOutputRoots 아래 <job_id>/A<n>/ 에 쓴다 — 애셋을 만들지 않는다(새 더티 0).
- 카메라 · 시트 규칙은 blender review.render(소스 골격)와 같다: 같은 셀 크기 상수(blender.REVIEW_RENDER)를 넘기고, render 가 있으면 그 시각을
  행으로 쓴다 — 두 시트가 같은 행이라 나란히 본다. 8-1 후보면 고른 후보의 프레임(values.review — select 가 바꿔 둔다).
- 연속 프레임은 여기서 APNG 한 장으로 잇는다(apng.py — 표준 라이브러리, 설치 없음).
- 캡처 실패(CAPTURE_FAILED · 설정 · 이미지 경로)는 생성 실패가 아니다 — 한계 REVIEW_NOT_CAPTURED 만 남긴다(blender 렌더 실패와 같은 규칙).
  가드(UNEXPECTED_DIRTY)와 에디터 연결 오류는 §7 대로 중단.
- 보이는 것은 시퀀스를 메시에 그대로 입힌 프리뷰다 — 옷/머리 물리 · 게임 AnimBP 레이어가 없다(REVIEW_CAPTURE_PREVIEW_ONLY). 요청 weapon(Phase 8-4c)이
  있으면 그 무기를 부착 소켓 · offset 그대로 붙여 찍는다(attachments — 런타임 왼손 IK 는 없다). 판정은 사람.
- 부분 프레이밍(Phase 9-5c — review.capture.focus[]): 손 · 손가락 · 머리를 본 캡처와 같은 행 · 뷰 · 시퀀스 · 부착물로 부위마다 한 번 더 찍는다(<dir>/focus_<이름>/).
  프리셋 본은 실행 때 대상 메시에서 푼다. 한 부위의 실패는 그 부위만 한계 — 본 캡처는 남는다.
"""
from __future__ import annotations

import pathlib

from .. import apng, body_fit, motion_metrics
from .. import weapon as weapon_mod
from ..editor import EditorCallError
from ..envelope import EDITOR_TRANSPORT_CODES, diag, limitation
from ..fallback import from_editor_error
from .base import PlanContext, Provider, RunContext, StepFailed, StepResult
from .blender import REVIEW_RENDER
from .builtin import RetargetPipe
from .integrate import final_sequence

TOOL = "capture_animation"
# 연결이 끊기거나 가드에 걸린 것만 중단 — 나머지(CAPTURE_FAILED · OUTPUT_PATH_NOT_ALLOWED(CAPTURE_ROOT) · 이미지 경로 · 메시 불일치)는 한계로
_FATAL = EDITOR_TRANSPORT_CODES | {"UNEXPECTED_DIRTY"}
LAYOUT_KEYS = ("cell_height_px", "max_aspect", "margin", "bounds_max_samples", "sheet_max_px")


def preview_limitation(weapon: bool = False) -> dict:
    if weapon:
        return limitation("REVIEW_CAPTURE_PREVIEW_ONLY", "대상 메시 캡처(review.capture)는 시퀀스를 메시에 그대로 입힌 프리뷰다 — 무기는 요청 weapon 의 부착 소켓 · "
                          "offset 그대로 붙였지만 옷/머리 물리 · 게임 AnimBP 레이어(런타임 왼손 IK · 조준)가 없고 조명은 프리뷰 조명이다. 동작 품질 판정은 사람"
                          "(캡처는 근거)", "review")
    return limitation("REVIEW_CAPTURE_PREVIEW_ONLY", "대상 메시 캡처(review.capture)는 시퀀스를 메시에 그대로 입힌 프리뷰다 — 무기 · 옷/머리 물리 · 게임 AnimBP "
                      "레이어(왼손 IK · 조준)가 없고 조명은 프리뷰 조명이다. 동작 품질 판정은 사람(캡처는 근거)", "review")


def not_captured(reason: str, message: str, **extra) -> dict:
    return limitation("REVIEW_NOT_CAPTURED", message, "review", reason=reason, **extra)


def capture_roots(settings: dict | None) -> list[str] | None:
    """ini CaptureOutputRoots(get_editor_status.generation.capture_output_roots) — 에디터가 없으면 None."""
    if settings is None:
        return None
    return list((settings.get("generation") or {}).get("capture_output_roots") or [])


def focus_bones(editor, request: dict, mesh: str, bones, notes: list[dict]) -> list[str]:
    """review.capture.focus bones → 본 이름. 이름을 추측하지 않는다: 손 · 손가락 = 대상 메시 손가락 체인 제안(샘플 전이 bundle_bones 와 같은 원천 — 비표준 메시도 된다),
    머리 = 측정 본 원천(RetargetPipe.request_bones — 대상 리그 또는 템플릿). 못 풀면 EditorCallError · BodyFitError · StepFailed."""
    if isinstance(bones, list):
        return list(bones)
    if bones == "head":
        return [RetargetPipe.request_bones(editor, request, notes, "capture")[motion_metrics.HEAD_ROLE]]
    info = editor.require("inspect_skeleton", skeletal_mesh=mesh, details=True, suggest_finger_chains=True)
    side = bones[-1]
    fingers = body_fit.bundle_bones([f"fingers_{side}"], info)["bones"]
    if bones.startswith("fingers_"):
        return fingers
    prefix = "Left" if side == "l" else "Right"
    hand = next((h.get("hand") for h in (info.get("finger_chain_suggestion") or {}).get("hands") or [] if h.get("side") == prefix), None)
    return ([hand] if hand else []) + fingers


class ReviewPipe(Provider):
    """review.capture → capture_animation (플러그인) → APNG."""

    def plan_capture(self, request: dict, steps: list[dict], pctx: PlanContext) -> tuple[dict | None, list[str], list[dict]]:
        """사슬 끝(validate 뒤)에 붙일 capture 단계 · 위험 · 예상 한계. 캡처할 수 없으면 단계 없이 REVIEW_NOT_CAPTURED."""
        review = request["review"] or {}
        cap = review.get("capture")
        if cap is None:
            return None, [], []
        mesh = cap["mesh"] or request["target_mesh"]
        if not mesh:
            return None, [], [not_captured("MISSING_MESH", "review.capture 는 대상 메시가 있어야 한다 — target_mesh 또는 review.capture.mesh")]
        roots = capture_roots(pctx.settings)
        if roots is not None and not roots:
            return None, [], [not_captured("CAPTURE_ROOTS_EMPTY", "ini [AnimGraphMcp] CaptureOutputRoots 가 비어 캡처하지 않는다(플러그인이 쓸 폴더가 없다)")]
        risks: list[str] = []
        lims = [preview_limitation(bool(request.get("weapon")))]
        convert = next((s for s in steps if s["step"] == "convert" and (s.get("inputs") or {}).get("review")), None)
        edits = any(s["step"] in ("edit", "timing") for s in steps)
        rows_from = "render" if convert is not None and not edits else "request"
        if review.get("render") and rows_from == "request":
            # render 가 없는 경로(재사용 · 편집) · 편집 · 흐느적 보정(timing, Phase 8-3)으로 시간축이 바뀐 경로 — 행은 같은 개수를 최종 클립에 고르게, 비교 칸 없음
            risks.append("CAPTURE_ROWS_NOT_RENDER" if not edits else "CAPTURE_COMPARE_SKIPPED_EDITS")
        render = review.get("render") or {}
        # count = render 시각을 못 쓸 때(렌더 없음 · 실패 · 편집 경로)의 행 수 — 요청 count, 아니면 render 행 수
        count = None if cap["times"] is not None else (cap["count"] or render.get("count") or len(render.get("times") or []) or 4)
        inputs = {"asset": "$asset", "mesh": mesh, "views": list(cap["views"]), "rows_from": rows_from,
                  "times": cap["times"], "count": count, "sequence": dict(cap["sequence"]) if cap["sequence"] else None,
                  "compare": bool(cap["compare"] and rows_from == "render"), "label": request.get("hero") or "target",
                  "layout": {k: REVIEW_RENDER[k] for k in LAYOUT_KEYS}, "dir": "<capture_root>/<job_id>/A<attempt>"}
        if request.get("weapon"):
            # Phase 8-4c — 요청 무기를 부착해 찍는다(capture_animation attachments — 부착 소켓 · offset 은 요청 그대로)
            inputs["attachments"] = [weapon_mod.attachment(request["weapon"])]
        if cap.get("focus"):
            inputs["focus"] = [dict(item) for item in cap["focus"]]
        facing = None
        if pctx.editor_ok:
            try:
                info = pctx.editor.require("inspect_skeleton", skeleton=request["target_skeleton"], details=True)
                facing = RetargetPipe.skeleton_facing(info, None)["axis"]
            except EditorCallError:
                facing = None
        if facing is None:
            risks.append("CAPTURE_FACING_RESOLVED_AT_RUN")
        inputs["facing"] = facing
        if roots is None:
            risks.append("CAPTURE_ROOTS_UNCHECKED")
        step = {"step": "capture", "provider": self.name, "tool": TOOL, "inputs": inputs}
        return step, risks, lims

    def run(self, ctx: RunContext) -> StepResult:
        inputs = ctx.step["inputs"]
        values = ctx.values
        editor = ctx.editor
        asset = final_sequence(values)
        notes: list[dict] = []

        def skipped(reason: str, message: str, **extra) -> StepResult:
            capture = {"ok": False, "shows": "target_mesh", "reason": reason, "message": message, **extra}
            return StepResult(values={"review_capture": capture}, limitations=[not_captured(reason, message, **extra)],
                              diagnostics=notes + [diag("warning", "REVIEW_NOT_CAPTURED", message, reason=reason)])

        if not asset:
            return skipped("NO_ASSET", "캡처할 최종 시퀀스가 없다")
        roots = capture_roots(editor.status())
        if not roots:
            return skipped("CAPTURE_ROOTS_EMPTY", "ini [AnimGraphMcp] CaptureOutputRoots 가 비어 있다")
        out_dir = (pathlib.Path(roots[0]) / ctx.job_id / f"A{ctx.attempt}").as_posix()
        facing = inputs.get("facing")
        if not facing:
            try:
                info = editor.require("inspect_skeleton", skeleton=ctx.request["target_skeleton"], details=True)
                facing = RetargetPipe.skeleton_facing(info, None)["axis"]
            except EditorCallError as err:
                if err.code in _FATAL:
                    raise from_editor_error("capture", err)
            if not facing:
                return skipped("FACING_UNKNOWN", "대상 스켈레톤의 정면을 재지 못했다 — 카메라 방향을 정할 수 없다")
        params = {"asset": asset, "mesh": inputs["mesh"], "facing": facing, "output_dir": out_dir, "views": inputs["views"],
                  "label": inputs.get("label"), **inputs["layout"]}
        render = values.get("review") if inputs.get("rows_from") == "render" else None
        rows_from = "request"
        if render and render.get("frames"):
            # 소스 골격 렌더의 시각 · 프레임 그대로 — 두 시트의 행이 같다
            rows = sorted({(f["row"], f["time"]) for f in render["frames"]})
            params["times"] = [t for _, t in rows]
            rows_from = "render"
            if inputs.get("compare"):
                views = [v for v in ("front", "side") if any(f["view"] == v for f in render["frames"])]
                by_key = {(f["row"], f["view"]): f["path"] for f in render["frames"]}
                params["compare"] = {"label": "source skeleton", "rows": [[by_key[(r, v)] for v in views if (r, v) in by_key] for r, _ in rows]}
        elif inputs.get("times"):
            params["times"] = inputs["times"]
        else:
            if inputs.get("rows_from") == "render":
                notes.append(diag("info", "CAPTURE_ROWS_FROM_COUNT", "the source-skeleton render has no frames (render failed or skipped) — capture rows "
                                  "are spread over the final clip and no compare sheet is made"))
            params["count"] = inputs.get("count") or 4
        if inputs.get("sequence"):
            params["sequence"] = dict(inputs["sequence"])
        if inputs.get("attachments"):
            params["attachments"] = [dict(a) for a in inputs["attachments"]]
        try:
            res = editor.require(TOOL, **params)
        except EditorCallError as err:
            if err.code in _FATAL:
                raise from_editor_error("capture", err)
            return skipped(err.details.get("reason") or err.code, f"{TOOL} failed: {err.code} {(err.envelope.get('error') or {}).get('message', '')[:300]}",
                           editor_error=err.summary())
        animation = None
        seq = res.get("sequence") or {}
        if seq.get("frames"):
            try:
                animation = apng.assemble(seq["frames"], pathlib.Path(out_dir) / "animation.png", float(seq.get("fps") or 15))
            except (apng.ApngError, OSError) as exc:
                code = getattr(exc, "code", type(exc).__name__)
                notes.append(diag("warning", "APNG_NOT_ASSEMBLED", f"the sequence frames could not be joined into an APNG ({code}: {exc}) — the frames stay",
                                  dir=seq.get("dir")))
        compare = res.get("compare") or None
        capture = {
            "ok": True, "shows": "target_mesh", "asset": asset, "mesh": res.get("mesh"), "facing": facing, "dir": res.get("dir"),
            "sheet": res.get("sheet"), "compare_sheet": compare.get("path") if compare else None, "rows_from": rows_from,
            "animation": animation, "frames": res.get("frames"), "sequence": {k: seq.get(k) for k in ("dir", "fps", "count", "size", "truncated")} if seq else None,
            "camera": res.get("camera"), "layout": res.get("layout"), "bounds": res.get("bounds"),
            "cells_touching_edge": res.get("cells_touching_edge"), "seconds": res.get("seconds"),
            "attachments": res.get("attachments") or [],   # 8-4d — 붙여 찍은 무기(요청 weapon — C++ 결과 그대로, 없으면 [])
        }
        paths = [p for p in (capture["compare_sheet"], capture["sheet"], (animation or {}).get("path")) if p]
        notes.append(diag("info", "REVIEW_CAPTURED", f"{len(res.get('frames') or [])} frame image(s) of {asset} on {res.get('mesh')} in {res.get('seconds')}s — "
                          f"show these to the user (the human judges): {', '.join(paths)}", sheet=capture["sheet"], compare=capture["compare_sheet"],
                          animation=(animation or {}).get("path")))
        limitations = [preview_limitation(bool(inputs.get("attachments")))]
        if inputs.get("focus"):
            capture["focus"] = self._capture_focus(ctx, inputs, params, out_dir, limitations, notes)
        return StepResult(values={"review_capture": capture}, limitations=limitations, diagnostics=notes)

    def _capture_focus(self, ctx: RunContext, inputs: dict, params: dict, out_dir: str, limitations: list[dict], notes: list[dict]) -> list[dict]:
        """review.capture.focus — 부위마다 capture_animation focus 한 번(본 캡처의 행 · 뷰 · 시퀀스 · 부착물, 비교 칸 없음). 연결 · 가드 오류만 중단."""
        out: list[dict] = []
        for item in inputs["focus"]:
            name = item["name"]

            def failed(reason: str, message: str, **extra) -> None:
                out.append({"ok": False, "name": name, "reason": reason, "message": message, **extra})
                limitations.append(not_captured(reason, message, focus=name, **extra))
                notes.append(diag("warning", "REVIEW_NOT_CAPTURED", message, reason=reason, focus=name))

            try:
                bones = focus_bones(ctx.editor, ctx.request, inputs["mesh"], item["bones"], notes)
                focus = {"bones": bones, **{k: item[k] for k in ("margin_cm", "near_cut") if k in item}}
                folder = f"{out_dir}/focus_{name}"
                call = {k: v for k, v in params.items() if k != "compare"}
                res = ctx.editor.require(TOOL, **{**call, "output_dir": folder, "focus": focus, "label": f"{params.get('label') or ''} {name}".strip()})
            except EditorCallError as err:
                if err.code in _FATAL:
                    raise from_editor_error("capture", err)
                failed(err.details.get("reason") or err.code, f"{TOOL} focus {name} failed: {err.code} {(err.envelope.get('error') or {}).get('message', '')[:300]}",
                       editor_error=err.summary())
                continue
            except StepFailed as err:
                if err.fatal:
                    raise
                failed(err.reason or err.cause, f"focus {name}: {err.message}")
                continue
            except body_fit.BodyFitError as err:
                failed(err.reason, f"focus {name}: {err.message}")
                continue
            animation = None
            seq = res.get("sequence") or {}
            if seq.get("frames"):
                try:
                    animation = apng.assemble(seq["frames"], pathlib.Path(folder) / "animation.png", float(seq.get("fps") or 15))
                except (apng.ApngError, OSError) as exc:
                    notes.append(diag("warning", "APNG_NOT_ASSEMBLED", f"focus {name}: the sequence frames could not be joined into an APNG "
                                      f"({getattr(exc, 'code', type(exc).__name__)}: {exc}) — the frames stay", dir=seq.get("dir")))
            info = res.get("focus") or {}
            if info.get("skinned_bones") == 0:
                notes.append(diag("warning", "CAPTURE_FOCUS_NOT_SKINNED", f"focus {name}: no vertex of {res.get('mesh')} follows {bones} — the part may live in another mesh"))
            if info.get("empty_cells"):
                notes.append(diag("warning", "CAPTURE_FOCUS_EMPTY", f"focus {name}: {info['empty_cells']} cell(s) show almost no mesh"))
            out.append({"ok": True, "name": name, "bones": bones, "dir": res.get("dir"), "sheet": res.get("sheet"), "animation": animation, "frames": res.get("frames"),
                        "camera": res.get("camera"), "focus": info, "seconds": res.get("seconds")})
            notes.append(diag("info", "REVIEW_FOCUS_CAPTURED", f"focus {name}: {len(res.get('frames') or [])} frame image(s) at "
                              f"{next(iter((res.get('camera') or {}).values()), {}).get('cm_per_px')} cm/px in {res.get('seconds')}s — show these to the user: "
                              f"{', '.join(p for p in (res.get('sheet'), (animation or {}).get('path')) if p)}", sheet=res.get("sheet"), animation=(animation or {}).get("path")))
        return out
