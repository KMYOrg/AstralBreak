"""한 풀이 파이프 (Phase 8-4b — 지침서 §14 Phase 8 '8-4') — control_rig 비활성 자리를 대신한다(Provider 수 그대로).

리타깃 · 흐느적 보정(timing) 뒤 대상 시퀀스(또는 같은 스켈레톤의 기존 Vesper 애니)를:
  ① 플러그인 validate_animation(profile · body_clearance{parts all, hands, model}) 로 잰다 — 몸 모델(대상 메시 스킨 · 반경 지도 · 포즈)의 한 원천.
  ② anim_gen/body_fit.py(순수 Python)가 관통(손 · 아래팔 ↔ 몸통 · 넓적다리 · 머리목 · 반대 손) · 파지 keep · 위팔 '안 깊어짐' · 지시 목표를 한 풀이로
     → 본별 부모 공간 회전 델타. 원본이 루프(① 측정의 numeric.loop)면 시간 처리를 순환으로(첫 · 끝 델타가 같다).
  ③ apply_animation_edits bone_deltas 로 새 애셋(원본은 그대로 — 재사용 경로도 새 애셋).
  ④ 같은 측정으로 다시 잰다 — 모델 예측과 C++ 실측을 Job fix.body 에 함께 남긴다.
측정 · 판정 기준은 C++ 하나(Python 은 그 모델을 읽어 푼다). 수치는 판정 근거이고 품질 합격은 사람이 본다(§16-9).
"""
from __future__ import annotations

import copy
import time

from .. import body_fit, motion_metrics, timing
from .. import weapon as weapon_mod
from ..body_model import BodyModel, ModelError
from ..editor import EditorCallError
from ..envelope import diag, limitation
from ..fallback import from_editor_error
from ..request import root_motion_flag
from .base import PlanBlocked, PlanContext, Provider, RunContext, StepFailed, StepResult
from .builtin import RetargetPipe, apply_edits

TOOL = ("validate_animation(profile · body_clearance{parts all, hands, model}) → body_fit.solve → apply_animation_edits(bone_deltas) → "
        "validate_animation(body_clearance parts · hands · per_frame)")
ARM_TARGET_PARTS = ("hand", "forearm")      # 관통 목표 쌍(정정 ① — 위팔 쌍은 '전보다 나빠지지 않음'만)
STILL_BODY = ("hip_l", "hip_r", "foot_l", "foot_r", "elbow_l", "elbow_r", "shoulder_l", "shoulder_r")
PREDICT_PCT_TOL, PREDICT_P95_TOL_CM = 1.0, 0.3   # 기준 5 — 모델 예측 vs C++ 실측


def approximate_limitation() -> dict:
    return limitation("BODY_FIT_APPROXIMATE", "몸 전체 보정(fix.body)은 대상 메시 반경 지도(축 둘레 별 모양 근사 — 오목한 면은 바깥 면으로 메운다)와 스킨 점으로 "
                      "잰 관통을 푼다. 옷 · 머리카락 물리 · 코트 자락(기록만)은 모른다 — 판정은 사람(전후 캡처)", "body_fit")


def runtime_ik_limitation(hand: str) -> dict:
    return limitation("GRIP_RUNTIME_IK", f"{hand} 손은 게임에서 런타임 IK(무기 액터 LeftHandGripSocket — ABP TwoBoneIK)가 무기 소켓으로 덮는다 — 애니의 파지는 "
                      "원래 관계(keep)만 지킨다(weapon 모드 아님)", "body_fit", hand=hand)


def weapon_error_cause(reason: str) -> str:
    """무기 · 목표 오류의 cause — 요청이 빠뜨린 것(무기 끝 · 효과기)은 BAD_REQUEST, 메시에 없는 것(소켓 · 손가락 체인)은 UNSUPPORTED_REQUEST."""
    return "BAD_REQUEST" if reason in ("UNKNOWN_EFFECTOR", "WEAPON_TIP_UNKNOWN") else "UNSUPPORTED_REQUEST"


class BodyFitPipe(Provider):
    """fix.body → body_fit 단계."""

    # ---- 계획 ----
    def plan_body(self, request: dict, source_on_target: str | None, pctx: PlanContext) -> tuple[dict, list[str], list[dict]]:
        cfg = request["fix"]["body"]
        if not request["target_mesh"]:
            raise PlanBlocked("UNSUPPORTED_REQUEST", "BODY_FIT_NO_MESH", "fix.body needs target_mesh — the body model is skinned from it",
                              missing=["target_mesh"])
        produces = cfg["mode"] == "auto"
        inputs = {**copy.deepcopy(cfg), "mesh": request["target_mesh"], "loop": request["loop"], "root_motion": root_motion_flag(request),
                  "bones": None, "produces": produces}
        # 무기(8-4c) — 파지 모드는 요청 grip.mode + 요청 weapon 으로 정한다(무기가 없으면 지금 그대로)
        weapon = request.get("weapon")
        try:
            inputs["grip_mode"] = body_fit.grip_mode(cfg["grip"], weapon)
            if any(t["effector"] == "weapon_tip" for t in cfg["targets"]) and not (weapon and weapon.get("tip")):
                raise body_fit.BodyFitError("fix.body.targets", "weapon_tip needs the request weapon with tip {socket} | {point_cm}", "WEAPON_TIP_UNKNOWN")
        except body_fit.BodyFitError as err:
            raise PlanBlocked(weapon_error_cause(err.reason), err.reason, f"{err.field}: {err.message}", field=err.field)
        lims = [approximate_limitation()]
        if weapon:
            inputs["weapon"] = copy.deepcopy(weapon)
            inputs["weapon_resolved"] = None
            g = weapon_mod.off_grip(weapon)
            if g is not None and g["runtime_ik"]:
                lims.append(runtime_ik_limitation(g["hand"]))
        # 손가락 뿌리(8-4c 후속 — 파지 프레임 보조 손목 굽힘 상한): 대상 메시 손가락 체인 제안의 {Side}Middle 시작. None = 아직 안 풂(실행 때), {} = 체인 없음(끈다)
        inputs["fingers"] = None
        step = {"step": "body_fit", "provider": self.name, "tool": TOOL, "inputs": inputs, "resolved": None}
        risks = ["BODY_FIT_RESOLVED_AT_RUN"] if produces else []
        if pctx.editor_ok:
            try:
                inputs["bones"] = RetargetPipe.selection_bones(pctx.editor, request["target_skeleton"], pctx.diagnostics, "body_fit")
                target_info = self.inspect_target(pctx.editor, request) if self.needs_target_info(inputs) else None
                if target_info is not None:
                    inputs["fingers"] = weapon_mod.finger_roots(target_info)
                if weapon:
                    inputs["weapon_resolved"] = self.resolve_weapon(pctx.editor, request, target_info=target_info)
                if source_on_target:
                    step["resolved"] = self.preview(pctx.editor, source_on_target, request, inputs)
            except StepFailed as failed:
                raise PlanBlocked(failed.cause, failed.reason, failed.message, editor_error=failed.editor_error)
            except body_fit.BodyFitError as err:
                raise PlanBlocked(weapon_error_cause(err.reason), err.reason, f"fix.body: {err.field}: {err.message}", field=err.field)
        if weapon and inputs["weapon_resolved"] is None:
            risks.append("WEAPON_RESOLVED_AT_RUN")
        if cfg["targets"] and step["resolved"] is None:
            risks.append("TARGETS_RESOLVED_AT_RUN")
        return step, risks, lims

    @staticmethod
    def needs_target_info(inputs: dict) -> bool:
        """대상 메시 inspect 가 필요한가 — 무기를 풀거나(소켓 · 손가락 체인) 파지 프레임 보조 손목 굽힘 상한(손가락 뿌리)을 둘 때(애셋을 만들고 파지가 켜짐)."""
        return bool(inputs.get("weapon")) or (inputs["produces"] and (inputs.get("grip_mode") or inputs["grip"]["mode"]) != "off")

    @staticmethod
    def inspect_target(editor, request: dict, step: str = "body_fit") -> dict:
        """대상 메시 inspect_skeleton(details · suggest_finger_chains — 동기, 폴링 없음) — 부착 소켓 · 손가락 체인 제안."""
        try:
            return editor.require("inspect_skeleton", skeletal_mesh=request["target_mesh"], details=True, suggest_finger_chains=True)
        except EditorCallError as err:
            raise from_editor_error(step, err)

    @classmethod
    def resolve_weapon(cls, editor, request: dict, step: str = "body_fit", target_info: dict | None = None) -> dict:
        """요청 weapon 을 메시 사실로 푼다 — 대상 메시(부착 소켓 · 손가락 체인 제안 — target_info 가 없으면 inspect) · 무기 메시(소켓 · 기하)
        inspect_skeleton(동기 — 폴링 없음). 소켓 · 체인이 없으면 BodyFitError(WEAPON_* — 후보를 막는다)."""
        weapon = request["weapon"]
        target = target_info if target_info is not None else cls.inspect_target(editor, request, step)
        try:
            info = editor.require("inspect_skeleton", skeletal_mesh=weapon["mesh"], details=True, geometry=True)
        except EditorCallError as err:
            raise from_editor_error(step, err)
        try:
            return weapon_mod.resolve(weapon, target, info)
        except weapon_mod.WeaponError as err:
            raise body_fit.BodyFitError(err.field, err.message, err.reason) from None

    @staticmethod
    def weapon_rig(rig, inputs: dict) -> body_fit.WeaponRig | None:
        resolved = inputs.get("weapon_resolved")
        if not resolved:
            return None
        return body_fit.WeaponRig(rig, resolved, mode=inputs["grip_mode"], wrist_bend_max_deg=inputs["grip"]["wrist_bend_max_deg"])

    def preview(self, editor, source: str, request: dict, inputs: dict) -> dict:
        """기존 애셋(대상 스켈레톤) — 계획 때 재서 보인다: 전 수치 · 사건(초) · 목표를 풀어(사건 → 프레임 · 부위 → 본 · 몸 기준틀 오프셋 → 목표 위치).
        사건을 못 찾거나 클립 밖이면 BodyFitError(EVENT_NOT_FOUND · TARGET_OUT_OF_RANGE) — 후보를 막는다."""
        item = self.measure(editor, source, request, inputs, model=bool(inputs["targets"]))
        bc = item.get("body_clearance") or {}
        out = {"source": source, "before": self.summary(item, inputs), "events": None, "targets": []}
        if inputs["targets"]:
            model = self.model_of(bc)
            rig = body_fit.Rig(model)
            out["events"] = self.events(item, inputs["bones"])
            targets = body_fit.resolve_targets(rig, inputs["targets"], out["events"], inputs["joints"], self.weapon_rig(rig, inputs))
            for t in targets:
                if t.get("skipped"):
                    raise body_fit.BodyFitError(f"targets.{t['id']}.at", t["skipped"]["message"], t["skipped"]["reason"])
                out["targets"].append(self.target_preview(model, t))
        return out

    @staticmethod
    def target_preview(model: BodyModel, t: dict) -> dict:
        fa, fb = t["frames"]
        mid = (fa + fb) // 2
        spec = t["spec"]
        out = {"id": t["id"], "note": t["note"], "effector": t["effector"], "bone": t["bone_name"], "kind": t["kind"], "priority": t["priority"],
               "window_s": t["window_s"], "frames": t["frames"], "ease_frames": t["ease_frames"], "dof": sorted({model.bones[b] for b, _ in t["dof"]}),
               "position": None, "rotation": spec.get("rotation")}
        if mid in t["pos"]:
            out["position"] = {**spec["position"], "at_frame": mid, "from_cm": [round(v, 2) for v in body_fit._target_point(t, model.poses[mid])],
                               "to_cm": [round(v, 2) for v in t["pos"][mid]]}
        elif t.get("away"):
            out["position"] = {**spec["position"], "from_bone": model.bones[t["away"]["bone"]]}
        return out

    # ---- 측정 ----
    @staticmethod
    def spec(inputs: dict, *, model: bool = False, per_frame: bool = False, ik_rig: str | None = None) -> dict:
        c = inputs["clearance"]
        out = {"mesh": inputs["mesh"], "parts": "all"}
        if ik_rig:
            out["ik_rig"] = ik_rig
        if c["hands"]:
            out["hands"] = True
        if c["legs"]:
            out["legs"] = True
        if c["secondary"] == "record":
            out["include_secondary"] = True
        if per_frame:
            out["per_frame"] = True
        if model:
            out["model"] = True
        return out

    @staticmethod
    def profile_bones(bones: dict) -> list[str]:
        knees = [k for k in bones.get("knees") or [] if k]
        return sorted(set(RetargetPipe.profile_bones(bones)) | set(knees))

    def measure(self, editor, asset: str, request: dict, inputs: dict, *, model: bool = False, per_frame: bool = False,
                ik_rig: str | None = None, step: str = "body_fit") -> dict:
        try:
            res = editor.require("validate_animation", assets=[asset], skeleton=request["target_skeleton"], profile_bones=self.profile_bones(inputs["bones"]),
                                 profile_positions=True, body_clearance=self.spec(inputs, model=model, per_frame=per_frame, ik_rig=ik_rig))
        except EditorCallError as err:
            raise from_editor_error(step, err)
        item = (res.get("assets") or [None])[0]
        bc = (item or {}).get("body_clearance") or {}
        if not item or bc.get("skipped_reason"):
            raise StepFailed("VALIDATION_FAILED", "BODY_NOT_MEASURED", f"body clearance of {asset} not measured ({bc.get('skipped_reason')})")
        return item

    @staticmethod
    def model_of(bc: dict) -> BodyModel:
        try:
            return BodyModel(bc.get("model") or {})
        except (ModelError, KeyError, TypeError) as err:
            raise StepFailed("VALIDATION_FAILED", "BAD_BODY_MODEL", f"the body model from body_clearance cannot be read ({err})") from None

    @staticmethod
    def events(item: dict, bones: dict) -> dict:
        num = item.get("numeric") or {}
        prof = num.get("profile") or {}
        scale = (num.get("pelvis_height_cm") or 100.0) / 100.0
        try:
            return timing.events(prof, hands=(bones["hand_l"], bones["hand_r"]), body=[bones[k] for k in STILL_BODY], feet=(bones["foot_l"], bones["foot_r"]),
                                 scale=scale, fps=float(num["frame_rate"]), length=float(num["length"]),
                                 leg_cm=(bones.get("leg_dims") or {}).get("leg_cm") or 90.0)
        except (timing.TimingError, KeyError) as err:
            return {"reason": f"NO_PROFILE ({err})", "both_planted": []}

    @staticmethod
    def pairs(bc: dict) -> dict:
        """C++ parts(+ hands) 쌍 → {"s|part|body": {pen_pct, contact_pct, depth_p95, depth_max}}."""
        parts = bc.get("parts") or {}
        items = list(parts.get("pairs") or []) + list((parts.get("hands") or {}).get("pairs") or [])
        return {f"{p['side']}|{p['arm_part']}|{p['body_part']}": {"pen_pct": p["frames_over_penetration_pct"], "contact_pct": p["frames_over_contact_pct"],
                                                                 "depth_p95": p["depth_p95"], "depth_max": p["depth_max"]} for p in items}

    def summary(self, item: dict, inputs: dict, contacts: dict | None = None) -> dict:
        """판정 근거 수치 — 쌍(손 · 아래팔 목표 · 위팔 기록 · 손끼리) · 머리 · 파지 · 발 · 떨림 · 꼬임 · 손목 굽힘 · 휘두름 · 궤적 폭 · 코트 자락."""
        bc = item.get("body_clearance") or {}
        num = item.get("numeric") or {}
        prof = num.get("profile") or {}
        pos, times = prof.get("position_cm") or {}, prof.get("times") or []
        scale = (num.get("pelvis_height_cm") or 100.0) / 100.0
        bones = inputs["bones"]
        pairs = self.pairs(bc)
        hands = {k: v for k, v in pairs.items() if k.split("|")[2].startswith(("hand_", "forearm_"))}
        target = {k: v for k, v in pairs.items() if k.split("|")[1] in ARM_TARGET_PARTS and k not in hands}
        grip = inputs["grip"]
        tol = grip["tolerance_cm"] if grip["tolerance_cm"] is not None else motion_metrics.GRIP_TOL_CM
        m = RetargetPipe.candidate_metrics(item, bones, grip["window"], None, grip["spacing_cm"], tol)
        over = {**target, **{k: v for k, v in hands.items() if k.split("|")[1] in ARM_TARGET_PARTS}}
        out = {"status": item.get("status"), "pairs_over_penetration": sorted(([k, v["pen_pct"], v["depth_max"]] for k, v in over.items() if v["pen_pct"] > 0),
                                                                              key=lambda r: -r[2]),
               "target_pen_pct_max": max((v["pen_pct"] for v in target.values()), default=0.0),
               "target_depth_max": max((v["depth_max"] for v in target.values()), default=0.0),
               "head_neck": {"pen_pct": max((v["pen_pct"] for k, v in target.items() if k.endswith("|head_neck")), default=0.0),
                             "depth_max": max((v["depth_max"] for k, v in target.items() if k.endswith("|head_neck")), default=0.0)},
               "hands_pen_pct_max": max((v["pen_pct"] for v in hands.values()), default=0.0),
               "hands_depth_max": max((v["depth_max"] for v in hands.values()), default=0.0),
               "hands": {k: v for k, v in hands.items() if v["contact_pct"] > 0 or v["depth_max"] > 0},
               "upper_arm": {k: v for k, v in pairs.items() if k.split("|")[1] == "upper_arm" and v["contact_pct"] > 0},
               "head_near": m.get("head"), "grip": {k: (m.get("grip") or {}).get(k) for k in ("grip_pct", "gap_cm", "band_cm")},
               "swing_peak_cm_s": (m.get("swing") or {}).get("peak_cm_s"), "attack_width": (m.get("attack") or {}).get("width_arm_ratio"),
               "cross_pct": (m.get("cross") or {}).get("crossed_pct"), "wrist_bend": m.get("wrist_bend"),
               "zigzag_max": motion_metrics.zigzag([t for b, t in pos.items() if t], times, scale)["max"] if pos else None,
               "loop_boundary_max_deg": num.get("loop_boundary_max_deg")}
        legs = {"hip_l": pos.get(bones["hip_l"]), "hip_r": pos.get(bones["hip_r"]), "foot_l": pos.get(bones["foot_l"]), "foot_r": pos.get(bones["foot_r"])}
        if all(legs.values()):
            leg_cm = (bones.get("leg_dims") or {}).get("leg_cm") or 90.0
            if contacts is None:
                contacts = {s: motion_metrics.detect_contacts(legs[f"foot_{s}"], times, 2, leg_cm) for s in ("l", "r")}
            rep = motion_metrics.legs_report(legs, times, 2, leg_cm, scale, contacts=contacts)
            out["feet"] = {"planted_ratio_max": rep["ratio"]["planted_max"], "slide_p95": rep["slide_p95"]}
            out["_contacts"] = contacts
        secondary = bc.get("secondary_arms")
        if secondary:
            out["secondary"] = [[a.get("upper_arm"), a.get("frames_over_penetration_pct"), a.get("depth_max")] for a in secondary]
        return out

    # ---- 실행 ----
    def run(self, ctx: RunContext) -> StepResult:
        editor = ctx.editor
        request, inputs = ctx.request, dict(ctx.step["inputs"])
        source = ctx.values.get("asset") or ctx.values["source"]
        diagnostics: list[dict] = []
        t0 = time.time()
        if not inputs.get("bones"):
            inputs["bones"] = RetargetPipe.selection_bones(editor, request["target_skeleton"], diagnostics, "body_fit")
        ik_rig = ctx.values.get("target_rig")
        before_item = self.measure(editor, source, request, inputs, model=inputs["produces"], per_frame=False, ik_rig=ik_rig)
        before = self.summary(before_item, inputs)
        contacts = before.pop("_contacts", None)
        seconds = {"measure": round(time.time() - t0, 2)}
        # 루프 여부의 한 원천 = 원본 측정의 numeric.loop(C++ bLoop) — 요청 loop 는 새 애셋에 쓸 값이라 쓰지 않는다
        loop = bool((before_item.get("numeric") or {}).get("loop"))
        record = {"version": body_fit.VERSION, "mode": inputs["mode"], "source": source, "before": before, "seconds": seconds,
                  "loop": {"source": loop}}
        if not inputs["produces"]:
            record["note"] = "mode measure — 측정만(애셋 없음)"
            return StepResult(values={"body_fit": record}, diagnostics=diagnostics)
        bc = before_item.get("body_clearance") or {}
        model = self.model_of(bc)
        rig = body_fit.Rig(model)
        events = self.events(before_item, inputs["bones"])
        # 무기(8-4c) · 손가락 뿌리(보조 손목 굽힘 상한) — 계획 때 못 풀었으면(에디터 없음) 여기서 메시 사실로 푼다
        mode = inputs.get("grip_mode") or inputs["grip"]["mode"]
        try:
            need_weapon = bool(inputs.get("weapon")) and not inputs.get("weapon_resolved")
            if need_weapon or (inputs.get("fingers") is None and self.needs_target_info(inputs)):
                target_info = self.inspect_target(editor, request)
                if inputs.get("fingers") is None:
                    inputs["fingers"] = weapon_mod.finger_roots(target_info)
                if need_weapon:
                    inputs["weapon_resolved"] = self.resolve_weapon(editor, request, target_info=target_info)
            wrig = self.weapon_rig(rig, {**inputs, "grip_mode": mode})
        except body_fit.BodyFitError as err:
            raise StepFailed(weapon_error_cause(err.reason), err.reason, f"{err.field}: {err.message}", fatal=True) from None
        grip = body_fit.grip_weights(rig, {**inputs["grip"], "mode": mode}, model.scale, wrig)
        try:
            targets = body_fit.resolve_targets(rig, inputs["targets"], events, inputs["joints"], wrig)
        except body_fit.BodyFitError as err:
            raise StepFailed("BAD_REQUEST", err.reason, f"fix.body {err.field}: {err.message}", fatal=True) from None
        limitations = [approximate_limitation()]
        g = weapon_mod.off_grip(inputs.get("weapon"))
        if g is not None and g["runtime_ik"]:
            limitations.append(runtime_ik_limitation(g["hand"]))
        for t in targets:
            if t.get("skipped"):
                limitations.append(limitation("TARGET_NOT_REACHED", f"지시 목표 '{t['id']}' 를 건너뛰었다 — {t['skipped']['message']}", "body_fit", id=t["id"],
                                              reason=t["skipped"]["reason"], blocked_by=[]))
        t1 = time.time()
        solved = body_fit.solve(model, inputs, grip=grip, targets=targets, loop=loop, weapon=wrig, fingers=inputs.get("fingers"))
        seconds["solve"] = round(time.time() - t1, 2)
        op = body_fit.bone_deltas_op(solved)
        t2 = time.time()
        result = apply_edits(ctx, source, [op] if op else [{"op": "trim"}], inputs, "body_fit", "body_fit")
        seconds["write"] = round(time.time() - t2, 2)
        asset = result.values["asset"]
        t3 = time.time()
        after_item = self.measure(editor, asset, request, inputs, ik_rig=ik_rig)
        after = self.summary(after_item, inputs, contacts)
        after.pop("_contacts", None)
        seconds["verify"] = round(time.time() - t3, 2)
        predicted = solved["predicted"]["pairs"]
        cpp_after = self.pairs(after_item.get("body_clearance") or {})
        compare = {}
        for key, pv in predicted.items():
            av = cpp_after.get(key)
            if av is None or (pv["frames_over_penetration_pct"] == 0 and av["pen_pct"] == 0 and pv["depth_p95"] == 0 and av["depth_p95"] == 0):
                continue
            compare[key] = {"pen_pct": [pv["frames_over_penetration_pct"], av["pen_pct"]], "depth_p95": [pv["depth_p95"], av["depth_p95"]],
                            "depth_max": [pv["depth_max"], av["depth_max"]],
                            "ok": abs(pv["frames_over_penetration_pct"] - av["pen_pct"]) <= PREDICT_PCT_TOL and abs(pv["depth_p95"] - av["depth_p95"]) <= PREDICT_P95_TOL_CM}
        n = solved["frames"]
        radius = int(round(inputs["smooth_s"] * model.fps))
        changed = solved["changed_frames"]
        record.update({
            "asset": asset, "after": after, "seconds": seconds,
            "model": {"mesh": model.raw.get("mesh"), "frames": n, "points": len(model.points), "maps": sorted(model.maps), "bones": len(model.bones),
                      "seconds": model.raw.get("seconds"), "bytes": model.raw.get("b64_bytes")},
            "events": events,
            "grip": {"mode": grip["mode"], "lead": grip["lead"], "band_cm": grip["band_cm"], "runs_s": grip["runs_s"], "frames": len(grip["frames"]),
                     "keep": solved["keep"], "wrist_bend": solved["wrist_bend"], "fingers": inputs.get("fingers")},
            "predicted": {"pairs": {k: v for k, v in predicted.items() if v["depth_max"] > 0}},
            "predicted_vs_after": {"pairs": compare, "ok": all(c["ok"] for c in compare.values())},
            "deltas": {k: v for k, v in solved["deltas"].items() if k != "bones"} | {"bones": [b["bone"] for b in solved["deltas"]["bones"]]},
            "joints_moved_cm": {"max": round(max(solved["moved_cm"]), 3) if solved["moved_cm"] else 0.0,
                                "outside_max": round(max((m for f, m in enumerate(solved["moved_cm"]) if not any(abs(f - c) <= 2 * radius for c in changed)),
                                                         default=0.0), 3)},
            "passes": solved["passes"], "stats": solved["stats"], "targets": solved["targets"],
            # 지시 목표 블록(완급 > 0 — 그 밖은 목표 없는 해 그대로) · 블록 재검사 패스 · 블록 풀이 수. 목표 없으면 None
            "target_region": solved.get("region"),
            # 루프 이음매 — 풀이의 첫 · 끝 델타 차(°, 루프면 0) · C++ 첫 · 끝 포즈 차(전 → 후)
            "loop": {"source": loop, "seam_deg": solved["loop"]["seam_deg"],
                     "boundary_max_deg": [before.get("loop_boundary_max_deg"), after.get("loop_boundary_max_deg")]},
        })
        if wrig is not None:
            # 무기(8-4c) — 푼 값(무기 메시 공간) · 파지 오차(전 · 후 — 모델) · 무기-몸 관통 기록(모델 지도, 제약 아님)
            res = inputs["weapon_resolved"]
            record["weapon"] = {k: res.get(k) for k in ("mesh", "bone", "socket", "socket_rel", "offset", "lead", "grip", "tip", "tip_from", "hand", "handle")}
            record["weapon"]["points"] = len(res.get("points") or [])
            record["grip"]["weapon"] = solved["weapon"]["grip"]
            record["grip"].update({k: grip.get(k) for k in ("weapon_runs_s", "near_cm", "band_far_frames", "dist_cm")})
            record["grip"]["weapon_frames"] = len(grip.get("weapon_frames") or [])
            record["weapon_body"] = solved["weapon"]["body"]
        # ---- 한계 ----
        remains = self.remains(after, predicted, solved)
        record["remains"] = remains
        if remains:
            limitations.append(limitation("BODY_PENETRATION_REMAINS", "보정 뒤에도 관통(깊이 > penetration_cm)이 남은 쌍 — "
                                          + ", ".join(f"{r['pair']} {r['pen_pct']}% · {r['depth_max']} cm ({r['reason']})" for r in remains[:6]), "body_fit",
                                          pairs=remains))
        keep = solved["keep"]
        if keep["frames"] and (keep["pos_cm_max"] or 0.0) > model.scale:
            limitations.append(limitation("GRIP_RELAXED", f"파지 프레임의 보조 손 상대 위치가 최대 {keep['pos_cm_max']} cm · {keep['deg_max']}° 바뀌었다(p95 "
                                          f"{keep['pos_cm_p95']} cm · {keep['deg_p95']}°) — 관통(손끼리 포함)이 keep 보다 앞서고, 시간 매끈화가 두 팔 짝을 조금 "
                                          "어긋나게 한다", "body_fit", keep=keep))
        bend = solved["wrist_bend"]
        if not bend["on"] and grip["frames"]:
            diagnostics.append(diag("warn", "GRIP_WRIST_BEND_OFF", f"파지 프레임 {len(grip['frames'])} 개 — 대상 메시 손가락 체인 제안에 {{Side}}Middle 이 없어 보조 손목 "
                                    "'원래보다 더 굽히지 않음' 상한을 껐다(fingers " + str(inputs.get("fingers")) + ")"))
        wg = ((solved.get("weapon") or {}).get("grip") or {}).get("after")
        if wg and wg["frames"] and ((wg["dist_cm_p95"] or 0.0) > model.scale or (wg["dist_cm_max"] or 0.0) > 2.0 * model.scale):
            limitations.append(limitation("GRIP_NOT_REACHED", f"무기 파지 — 보조 손바닥 점 ↔ 손잡이 p95 {wg['dist_cm_p95']} / 최대 {wg['dist_cm_max']} cm "
                                          f"(기준 1 · 2 cm × scale) — 관통 · 손목 굽힘 상한 · 관절 상한이 앞선다(쥠 축 p95 {wg['axis_deg_p95']}° 는 기록)", "body_fit",
                                          grip=wg))
        if wrig is not None and wrig.grip is not None and not wrig.active:
            # 무기 파지는 옵트인 — auto 는 keep(띠 안), 손잡이 거리 · 두 손 선 각도만 기록
            allf = ((((solved.get("weapon") or {}).get("grip") or {}).get("before")) or {}).get("all_frames") or {}
            limitations.append(limitation("GRIP_NOT_APPLICABLE", f"무기 파지는 옵트인(fix.body.grip.mode: weapon) — 이 Job 은 {grip['mode']} 로 풀고 손잡이 관계만 쟀다: 보조 "
                                          f"손바닥 점 ↔ 손잡이 p50 {allf.get('dist_cm_p50')} cm · 두 손 선 ∠ 손잡이 p50 {allf.get('hands_line_deg_p50')}°(무기 부착 방향과 "
                                          "동작의 주 손 방향이 어긋나면 크다 — 생성 쪽 후속)", "body_fit", reason="OPT_IN", dist_cm_p50=allf.get("dist_cm_p50"),
                                          hands_line_deg_p50=allf.get("hands_line_deg_p50")))
        if grip.get("band_far_frames"):
            far = ((solved.get("weapon") or {}).get("grip") or {}).get("before") or {}
            allf = far.get("all_frames") or {}
            limitations.append(limitation("GRIP_NOT_APPLICABLE", f"무기 파지 — 파지 띠 프레임 {grip['band_far_frames']} 개는 보조 손이 손잡이에서 멀어(원래 거리 p50 "
                                          f"{allf.get('dist_cm_p50')} cm > {grip['near_cm']} cm) 붙이지 않고 keep 했다(붙이면 보정이 아니라 재배치). 두 손 선 ∠ 손잡이 p50 "
                                          f"{allf.get('hands_line_deg_p50')}° — 무기 부착(소켓 · offset) 방향과 동작의 주 손 방향이 어긋난다 → 생성 쪽 후속", "body_fit",
                                          reason="OFF_HAND_FAR", frames=grip["band_far_frames"], dist_cm=grip.get("dist_cm"),
                                          hands_line_deg_p50=allf.get("hands_line_deg_p50")))
        wb = ((solved.get("weapon") or {}).get("body") or {}).get("after")
        if wb and any(p["frames_over_penetration_pct"] > 0 for p in wb["pairs"].values()):
            limitations.append(limitation("WEAPON_BODY_RECORDED", "무기-몸 관통(무기 기하 단면 근사 ↔ 몸 지도)은 재기만 했다(제약 아님 — 날 단면은 상자로 채워 "
                                          f"과대일 수 있다), 최악 {wb['worst']}", "body_fit",
                                          pairs={k: v for k, v in wb["pairs"].items() if v["frames_over_penetration_pct"] > 0}))
        for t in solved["targets"]:
            if not t["reached"]:
                limitations.append(limitation("TARGET_NOT_REACHED", f"지시 목표 '{t['id']}' 오차 p95 {t['achieved']['error_cm_p95']} cm · "
                                              f"{t['achieved']['error_deg_p95']}° — 막은 것 {t['blocked_by'] or ['soft weights']}", "body_fit",
                                              id=t["id"], error=t["achieved"], blocked_by=t["blocked_by"]))
        if after.get("secondary") and any((s[1] or 0) > 0 for s in after["secondary"]):
            limitations.append(limitation("BODY_FIT_SECONDARY_RECORDED", "코트 자락 등 매달린 가지(secondary)와의 관통은 재기만 했다(제약 아님 — 물리로 흔들린다)",
                                          "body_fit", secondary=after["secondary"]))
        if not op:
            limitations.append(limitation("BODY_FIT_NOT_APPLIED", "고칠 관통 · 목표가 없어 원래 시퀀스 그대로(항등 trim)", "body_fit"))
        result.values["body_fit"] = record
        result.limitations = limitations + result.limitations
        diagnostics.append(diag("info", "BODY_FIT_APPLIED", f"body_fit {n} frames: hand/forearm penetration {before['target_pen_pct_max']}% · "
                                f"{before['target_depth_max']} cm → {after['target_pen_pct_max']}% · {after['target_depth_max']} cm, joints "
                                f"{solved['deltas']['frames_changed']} frames (≤ {solved['deltas']['deg_max']}°), {seconds}"))
        result.diagnostics = diagnostics + result.diagnostics
        return result

    @staticmethod
    def remains(after: dict, predicted: dict, solved: dict) -> list[dict]:
        out = []
        clamped = bool(solved["deltas"].get("clamped"))
        for key, pen, depth in after["pairs_over_penetration"]:
            pv = predicted.get(key) or {}
            if (pv.get("frames_over_penetration_pct") or 0.0) == 0.0 and (pv.get("depth_max") or 0.0) <= depth / 2.0:
                reason = "MODEL_APPROXIMATION"   # 모델은 풀렸다고 보는데 C++ 실측이 남김(기준 본 강체 근사 · 매끈화)
            elif clamped:
                reason = "JOINT_LIMIT"
            else:
                reason = "NOT_RESOLVED"
            out.append({"pair": key, "pen_pct": pen, "depth_max": depth, "reason": reason})
        return out
