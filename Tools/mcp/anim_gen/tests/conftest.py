"""anim_gen pytest 공통 — 에디터 없이 돈다 (지침서 §14 Phase 3 · 4 완료 기준).

FakeEditor 는 플러그인 Tool 봉투를 흉내 낸다(허용 목록 · 덮어쓰기 없음 · 스켈레톤). Mock Provider 는 local_ai · external.meshy
자리에 끼워 실제 규칙 표로 시험한다. 진짜 HTTP 와 서브프로세스는 막아 둔다 — 호출되면 테스트가 실패한다. 정책의 Blender 경로는
기본으로 없는 파일을 가리킨다(이 컴퓨터에 Blender · Kimodo 가 있어도 결과가 같다) — Blender 테스트는 test_blender.py, Kimodo 테스트는
test_local_ai.py 가 가짜 실행 파일 · 캐시를 준다.

    Tools/mcp/.venv/Scripts/python.exe -m pytest Tools/mcp/anim_gen/tests -q
"""
from __future__ import annotations

import copy
import math
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import model_fixture  # noqa: E402
from anim_gen import policy as policy_mod  # noqa: E402
from anim_gen.body_model import BodyModel, pair_stats  # noqa: E402
from anim_gen.editor import EditorClient, asset_name, is_under, package_path  # noqa: E402
from anim_gen.providers.base import Provider, StepFailed, StepResult  # noqa: E402
from anim_gen.registry import Registry  # noqa: E402
from anim_gen.service import Service  # noqa: E402
from anim_gen.store import Store  # noqa: E402

VESPER = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
VESPER_MESH = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
UE4 = "/Game/Assets/CM/Meshes/SK_Mannequin_Skeleton_HK"
UE4_MESH = "/Game/Assets/CM/Meshes/SK_Mannequin_HK"
HERO = "/Game/Animation/Hero/Vesper"
AIM_IDLE = f"{HERO}/Rifle/Aim/AS_Vesper_Rifle_AimIdle"
ATTACK3 = f"{HERO}/Sickle/Actions/AS_Vesper_Sickle_Attack3"
KATANA = "/Game/Assets/CM/Anims/Katana_Attack_Slash1"
OUT = "/Game/Animation/Test/AIAnimation/P3"
# Phase 7 — 포장 · 연결 Tool 도 쓰기(계획은 이것들을 부르지 않는다)
INTEGRATION_WRITE_TOOLS = {"set_sequence_additive", "create_anim_montage", "set_montage_sections", "create_blendspace",
                           "duplicate_animation_blueprint", "apply_graph_operations"}
WRITE_TOOLS = {"apply_animation_edits", "retarget_animations", "import_animation_file", "create_ik_rig", "create_ik_retargeter"} | INTEGRATION_WRITE_TOOLS
ABP_TOOLS = {"get_anim_blueprint_info", "preview_graph_operations", "duplicate_animation_blueprint", "apply_graph_operations",
             "compile_animation_blueprint", "run_anim_scenario"}
KNOWN_OPS = {"trim", "retime", "time_warp", "hold_pose", "concat", "mirror", "offset_bone", "rotate_root", "bone_deltas"}
COMBAT_ABP = "/Game/Animation/Hero/ABP_Hero_Combat"
RUNTIME_ABP = "/Game/Animation/Test/ABP_McpRuntimeTest"
WALK = f"{HERO}/Common/Locomotion/AS_Vesper_Neutral_Walk_Loop_F"
IDLE = f"{HERO}/Common/Locomotion/AS_Vesper_Idle"
OTHER_ABP = "/Game/Characters/Enemy/ABP_Grunt"


def _bone(name, parent, t):
    return {"name": name, "parent": parent, "ref_component": {"t": list(t), "r": [0, 0, 0]}}


_ROT = "CHANNELS 3 Zrotation Xrotation Yrotation"


def _leg(side: str, x: float, toe: tuple[float, float, float], s: float) -> str:
    return (f"JOINT {side}UpLeg\n{{\nOFFSET {x} 0 0\n{_ROT}\nJOINT {side}Leg\n{{\nOFFSET 0 {-45 * s} 0\n{_ROT}\nJOINT {side}Foot\n{{\nOFFSET 0 {-45 * s} 0\n"
            f"{_ROT}\nJOINT {side}ToeBase\n{{\nOFFSET {toe[0]} {toe[1]} {toe[2]}\n{_ROT}\nEnd Site\n{{\nOFFSET {toe[0] / 2} 0 {toe[2] / 2}\n}}\n}}\n}}\n}}\n}}\n")


def make_bvh(toe=(0.0, -8.0, 12.0), scale: float = 1.0, frames: int = 3, rows: int | None = None, extra: str = "",
             root: str = "Hips", frame_time: float = 1 / 120) -> str:
    """합성 BVH — Y-up, 키 약 183 단위(×scale)의 사람(관절 11개), 발끝이 toe 방향(BVH 좌표, 기본 +Z → UE +Y). 데이터는 전부 0."""
    s = scale
    toe = tuple(v * s for v in toe)
    body = (f"HIERARCHY\nROOT {root}\n{{\nOFFSET 0 0 0\nCHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation\n"
            + _leg("Left", 10 * s, toe, s) + _leg("Right", -10 * s, toe, s)
            + f"JOINT Spine\n{{\nOFFSET 0 {10 * s} 0\n{_ROT}\nJOINT Head\n{{\nOFFSET 0 {60 * s} 0\n{_ROT}\nEnd Site\n{{\nOFFSET 0 {15 * s} 0\n}}\n}}\n}}\n"
            + extra + "}\n")
    channels = 6 + 3 * 10 + (3 if extra else 0)
    row = " ".join(["0"] * channels)
    data = "\n".join([row] * (frames if rows is None else rows))
    return f"{body}MOTION\nFrames: {frames}\nFrame Time: {frame_time:.8f}\n{data}\n"


# Vesper 처럼 +Y 를 보는 UE 스켈레톤(발목 → 볼이 +Y). inspect_skeleton(details) 용
VESPER_BONES = [_bone("root", None, (0, 0, 0)), _bone("pelvis", "root", (0, -1.4, 105)), _bone("head", "pelvis", (0, 0, 171)),
                _bone("thigh_l", "pelvis", (9, -1.4, 102)), _bone("calf_l", "thigh_l", (10, 0, 55)), _bone("foot_l", "calf_l", (12, -3.5, 9.5)),
                _bone("ball_l", "foot_l", (13, 8.3, 2.5)), _bone("thigh_r", "pelvis", (-9, -1.4, 102)), _bone("calf_r", "thigh_r", (-10, 0, 55)),
                _bone("foot_r", "calf_r", (-12, -3.5, 9.5)), _bone("ball_r", "foot_r", (-13, 8.3, 2.5))]
# 팔 — 실제 Vesper 기준 포즈(inspect_skeleton ref_component, 2026-10-26): 어깨 관절 폭 23.96 · 위팔 24.38 · 아래팔 23.28 cm (자루 무기 간격 사상)
for _s, _x in (("l", 1.0), ("r", -1.0)):
    VESPER_BONES += [_bone(f"clavicle_{_s}", "pelvis", (1.76 * _x, -0.3, 146.384)), _bone(f"upperarm_{_s}", f"clavicle_{_s}", (11.982 * _x, -5.004, 145.66)),
                     _bone(f"lowerarm_{_s}", f"upperarm_{_s}", (27.48 * _x, -6.322, 126.884)), _bone(f"hand_{_s}", f"lowerarm_{_s}", (42.557 * _x, -1.395, 109.848))]


# SB(3ds Max Biped) 처럼 +X 를 보는 소스(왼쪽 −Y) — 정면 맞춤(리타깃 facing_yaw_deg +90) 시험용. FX 본은 z −2217cm 외톨이
SB = "/Game/Assets/SB/SB_Skeleton"
SB_MESH = "/Game/Assets/SB/SB_Body"
SB_ANIM = "/Game/Assets/SB/Evefin"
SB_BONES = [_bone("Root", None, (0, 0, 0)), _bone("Bip001-Pelvis", "Root", (1, 0, 99)), _bone("Bip001-Head", "Bip001-Pelvis", (0, 0, 152)),
            _bone("Bip001-L-Thigh", "Bip001-Pelvis", (1, -9, 99)), _bone("Bip001-L-Calf", "Bip001-L-Thigh", (0, -12, 55)),
            _bone("Bip001-L-Foot", "Bip001-L-Calf", (-5, -15, 15)), _bone("Bip001-L-Toe0", "Bip001-L-Foot", (-2.4, -15.3, 4)),
            _bone("Bip001-R-Thigh", "Bip001-Pelvis", (1, 9, 99)), _bone("Bip001-R-Calf", "Bip001-R-Thigh", (0, 12, 55)),
            _bone("Bip001-R-Foot", "Bip001-R-Calf", (-5, 15, 15)), _bone("Bip001-R-Toe0", "Bip001-R-Foot", (-2.4, 15.3, 4)),
            _bone("FX_GunFire_Rail_End", "Bip001-Pelvis", (300, 0, -2217))]
SB_CHAINS = [{"name": "LeftLeg", "start": "Bip001-L-Thigh", "end": "Bip001-L-Toe0"},
             {"name": "RightLeg", "start": "Bip001-R-Thigh", "end": "Bip001-R-Toe0"}]


def _obj(path: str) -> str:
    return f"{path}.{asset_name(path)}"


def write_png(path: pathlib.Path, width: int, height: int, rgb: tuple[int, int, int]) -> pathlib.Path:
    """작은 단색 RGBA PNG (표준 라이브러리) — 캡처 흉내 · APNG 시험용."""
    import struct
    import zlib

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    row = b"\x00" + bytes([*rgb, 255]) * width
    data = zlib.compress(row * height)
    path = pathlib.Path(path)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", data)
                     + chunk(b"IEND", b""))
    return path


def err(code: str, message: str = "", **details) -> dict:
    return {"code": code, "message": message or code, "details": details}


class FakeEditor:
    """플러그인 Tool 의 봉투 모양과 가드만 흉내 낸다 — 동작 수치는 고정값."""

    def __init__(self):
        self.up = True
        self.calls: list[tuple[str, dict]] = []
        self.fail: dict[str, list[dict]] = {}
        self.diags: dict[str, list[dict]] = {}  # Tool → 봉투 diagnostics (성공·실패 모두)
        self.output_paths = ["/Game/Animation/Generated/", "/Game/Animation/Test/"]
        self.import_roots = ["Saved/AnimGen/Import/"]
        self.meshes = {VESPER: VESPER_MESH, UE4: UE4_MESH, SB: SB_MESH}
        self.bones = {VESPER: VESPER_BONES, UE4: VESPER_BONES, SB: SB_BONES}
        self.auto_rig_fail: set[str] = set()
        self.assets: dict[str, dict] = {
            AIM_IDLE: {"class": "AnimSequence", "skeleton": VESPER, "length": 1.3333, "frame_rate": 30.0, "loop": True, "root_motion": False},
            ATTACK3: {"class": "AnimSequence", "skeleton": VESPER, "length": 1.6, "frame_rate": 60.0, "loop": False, "root_motion": True},
            KATANA: {"class": "AnimSequence", "skeleton": UE4, "length": 1.9, "frame_rate": 30.0, "loop": False, "root_motion": True},
            SB_ANIM: {"class": "AnimSequence", "skeleton": SB, "length": 10.375, "frame_rate": 24.0, "loop": False, "root_motion": False},
            WALK: {"class": "AnimSequence", "skeleton": VESPER, "length": 1.0667, "frame_rate": 30.0, "loop": True, "root_motion": False},
            IDLE: {"class": "AnimSequence", "skeleton": VESPER, "length": 2.0, "frame_rate": 30.0, "loop": True, "root_motion": False},
        }
        # Phase 7 — 스켈레톤 슬롯 · AnimBP · 스모크 · 시나리오 흉내
        self.promotion_paths = ["/Game/Animation/Hero/"]
        self.slots = {VESPER: ["DefaultSlot", "UpperBody"]}
        self.abps: dict[str, dict] = {COMBAT_ABP: {"skeleton": VESPER, "revision": "sha1:combat"},
                                      RUNTIME_ABP: {"skeleton": VESPER, "revision": "sha1:runtime"},
                                      OTHER_ABP: {"skeleton": UE4, "revision": "sha1:grunt"}}
        self.compile_ok = True
        self.smoke_fail: set[str] = set()      # 이 문자열을 품은 필터는 실패
        self.smoke_missing: set[str] = set()   # 이 문자열을 품은 필터는 테스트 0개
        self.scenario_polls = 1                # 끝나기 전 poll 횟수
        self.scenario_jobs: dict[str, dict] = {}
        # Phase 8-1 — validate_animation profile_positions · body_clearance 흉내: 애셋 이름 → {gap, stance, peak, penetration, status}
        self.profiles: dict[str, dict] = {}
        # Phase 8-2 — capture_animation 흉내: ini CaptureOutputRoots(디스크 — 테스트가 tmp_path 를 준다, 기본 비어 있음) · 남길 더티
        self.capture_roots: list[str] = []
        self.capture_dirty: list[str] = []

    # ---- 호출 ----
    def call(self, tool: str, params: dict, timeout: float | None = None) -> dict:
        self.calls.append((tool, copy.deepcopy(params)))
        if not self.up:
            return self._env(tool, error=err("EDITOR_GONE", "Cannot reach the editor bridge"))
        if self.fail.get(tool):
            env = self._env(tool, error=self.fail[tool].pop(0))
        else:
            try:
                env = self._env(tool, result=getattr(self, f"_{tool}")(params))
            except _Refuse as refusal:
                env = self._env(tool, error=refusal.error)
        env["diagnostics"] = copy.deepcopy(self.diags.get(tool, []))
        return env

    @staticmethod
    def _env(tool: str, result=None, error=None) -> dict:
        return {"ok": error is None, "tool": tool, "request_id": "fake", "result": result, "error": error, "diagnostics": []}

    def client(self) -> EditorClient:
        return EditorClient(call=self.call)

    def count(self, tool: str) -> int:
        return sum(1 for t, _ in self.calls if t == tool)

    @property
    def writes(self) -> list[tuple[str, dict]]:
        return [(t, p) for t, p in self.calls if t in WRITE_TOOLS]

    @property
    def abp_calls(self) -> list[tuple[str, dict]]:
        return [(t, p) for t, p in self.calls if t in ABP_TOOLS]

    # ---- 가드 ----
    def _allowed(self, path: str) -> None:
        if not is_under(path, self.output_paths):
            raise _Refuse(err("OUTPUT_PATH_NOT_ALLOWED", f"{path} outside GenerationOutputPaths"))

    def _new(self, path: str, **info) -> str:
        path = package_path(path)
        self._allowed(path)
        if path in self.assets:
            raise _Refuse(err("ASSET_EXISTS", f"{path} exists"))
        self.assets[path] = info
        return path

    def _source(self, path: str) -> dict:
        info = self.assets.get(package_path(path))
        if info is None:
            raise _Refuse(err("ASSET_NOT_FOUND", f"{path} not found"))
        return info

    # ---- Tool ----
    def _get_editor_status(self, p):
        return {"generation": {"output_paths": self.output_paths, "import_source_roots": self.import_roots,
                               "max_retarget_assets_per_call": 50, "promotion_paths": self.promotion_paths,
                               "capture_output_roots": self.capture_roots}, "dirty_package_count": 0}

    def _search_animations(self, p):
        tokens = [t for t in (p.get("query") or "").lower().replace("_", " ").split() if t]
        cls = p.get("class", "AnimSequence")
        items = []
        for path, info in sorted(self.assets.items()):
            name = asset_name(path).lower()
            if not path.startswith(p.get("path_prefix", "/Game")):
                continue
            if cls != "all" and info.get("class") != cls:
                continue
            if p.get("skeleton") and package_path(p["skeleton"]) != info.get("skeleton"):
                continue
            if not all(t in name for t in tokens):
                continue
            items.append({"asset_path": _obj(path), "name": asset_name(path), "class": info.get("class"),
                          "skeleton": _obj(info["skeleton"]) if info.get("skeleton") else None, "length": info.get("length"),
                          "frame_rate": info.get("frame_rate"), "root_motion": info.get("root_motion"), "loop": info.get("loop"), "score": 1.0})
        limit = p.get("limit", 50)
        return {"total": len(items), "returned": min(len(items), limit), "truncated": len(items) > limit, "items": items[:limit]}

    def _inspect_skeleton(self, p):
        mesh = self.meshes.get(package_path(p["skeleton"]))
        bones = self.bones.get(package_path(p["skeleton"]), [])
        if not p.get("details"):
            bones = [{"name": b["name"], "parent": b["parent"]} for b in bones]
        return {"skeleton_path": _obj(p["skeleton"]), "mesh": _obj(mesh) if mesh else None, "mesh_source": "skeleton_preview" if mesh else "none",
                "bones": bones, "slot_groups": [{"group": "DefaultGroup", "slots": self.slots.get(package_path(p["skeleton"]), ["DefaultSlot"])}]}

    def _check_ops(self, ops):
        bad = [i for i, o in enumerate(ops) if o.get("op") not in KNOWN_OPS]
        return [{"index": i, "op": o.get("op"), "ok": i not in bad} for i, o in enumerate(ops)], bad

    def _preview_animation_edits(self, p):
        src = self._source(p["source"])
        planned, bad = self._check_ops(p["operations"])
        out = {"valid": not bad, "planned": planned,
               "result": {"length": src["length"], "frame_rate": src["frame_rate"], "frames": int(src["length"] * src["frame_rate"])},
               "seams": [], "limitations": []}
        if p.get("asset_path"):
            out["would_create"] = {"allowed": is_under(p["asset_path"], self.output_paths), "exists": package_path(p["asset_path"]) in self.assets}
        return out

    def _apply_animation_edits(self, p):
        src = self._source(p["source"])
        planned, bad = self._check_ops(p["operations"])
        if bad:
            raise _Refuse(err("BAD_REQUEST", "One or more operations failed; nothing was created", planned=planned))
        loop = p["loop"] if p.get("loop") is not None else src["loop"]
        length = src["length"]
        for i, op in enumerate(p["operations"]):
            start, end = op.get("start", 0.0), op.get("end", length)
            if op["op"] == "bone_deltas":
                # Phase 8-4a — 배열 길이 = 그 op 직전 버퍼의 키 수(플러그인처럼 BAD_OP 이면 아무것도 만들지 않는다)
                keys = int(round(length * src["frame_rate"])) + 1
                short = [b["bone"] for b in op.get("bones") or [] for k in ("rotation_deg", "translation_cm") if b.get(k) is not None and len(b[k]) != keys]
                if short or not op.get("bones"):
                    planned[i] = {"index": i, "op": op["op"], "ok": False, "error": {"code": "BAD_OP", "message": f"bone(s) {short} need {keys} entries (one per key)"}}
                    raise _Refuse(err("BAD_REQUEST", "One or more operations failed; nothing was created", planned=planned))
            if op["op"] == "retime" and op.get("duration"):
                length = op["duration"]
            elif op["op"] == "retime":
                length = round(length - (end - start) + (end - start) / op["rate"], 4)
            elif op["op"] == "time_warp":
                length = round(op["knots"][-1][1], 4)
            elif op["op"] == "trim":
                length = round(end - start, 4)
        path = self._new(p["asset_path"], **{"class": "AnimSequence", "skeleton": src["skeleton"], "length": length,
                                             "frame_rate": src["frame_rate"], "loop": loop, "root_motion": src["root_motion"]})
        item = {"status": "PASSED", "numeric": {"length": length, "frame_rate": src["frame_rate"], "loop": loop}}
        return {"asset_path": _obj(path), "length": length, "frame_rate": src["frame_rate"], "frames": int(length * src["frame_rate"]),
                "validation": {"status": "PASSED", "asset": item}, "limitations": ["1 notify(ies) dropped"], "saved": p.get("save", False)}

    def _validate_animation(self, p):
        items = []
        for a in p["assets"]:
            info = self._source(a)
            prof = self.profiles.get(asset_name(a)) or {}
            # 플러그인처럼 경고가 있으면 PASSED_WITH_WARNINGS — prof.warnings = 상대 · 구조 검사 경고, 관통은 body_clearance 하위 검사 경고
            warnings = list(prof.get("warnings", []))
            pen = prof.get("penetration", 0.0) if p.get("body_clearance") else 0.0
            status = prof.get("status") or info.get("status", "PASSED")
            if status == "PASSED" and (warnings or pen):
                status = "PASSED_WITH_WARNINGS"
            item = {"asset": _obj(a), "status": status, "issues": [{"level": "warning", "code": c} for c in warnings],
                    "numeric": {"length": info["length"], "frame_rate": info["frame_rate"], "loop": info["loop"], "pelvis_height_cm": 105.0,
                                "max_deg_per_frame": 30.0}}
            if p.get("profile_bones"):
                item["numeric"]["profile"] = self._profile(p["profile_bones"], prof, bool(p.get("profile_positions")), bool(p.get("profile_rotations")))
            if p.get("body_clearance"):
                item["body_clearance"] = {"arms": [{"upper_arm": "upperarm_l", "frames_over_penetration_pct": pen, "frames_over_contact_pct": pen,
                                                    "depth_max": 3.5 if pen else 0.0, "worst": {"frame": 3, "time": 0.1}},
                                                   {"upper_arm": "upperarm_r", "frames_over_penetration_pct": 0.0, "frames_over_contact_pct": 0.0,
                                                    "depth_max": 0.0, "worst": {"frame": 0, "time": 0.0}}],
                                          "issues": [{"level": "warning", "code": "BODY_PENETRATION"}] if pen else []}
                spec = p["body_clearance"] if isinstance(p["body_clearance"], dict) else {}
                if spec.get("parts") == "all" or spec.get("legs") or spec.get("per_frame") or spec.get("model") or spec.get("hands"):
                    # Phase 8-4a — 부위 쌍 · 프레임 깊이 · 몸 모델 흉내: 합성 모델(model_fixture)을 body_model 로 재서 C++ 와 같은 모양으로.
                    # 8-4b hands — 손끼리 쌍은 parts.hands.pairs 로 따로(이 합성 모델엔 손 지도가 없어 빈 목록)
                    model = model_fixture.make_model()
                    series = BodyModel(model).series()
                    pairs = [{"side": s, "arm_part": a, "body_part": b, **pair_stats(v, model["contact_cm"], model["penetration_cm"])} for (s, a, b), v in series.items()]
                    is_hand = lambda pr: pr["body_part"].startswith(("hand_", "forearm_"))  # noqa: E731
                    item["body_clearance"]["parts"] = {"pairs": [pr for pr in pairs if not is_hand(pr)]}
                    if spec.get("hands"):
                        item["body_clearance"]["parts"]["hands"] = {"pairs": [pr for pr in pairs if is_hand(pr)]}
                    if spec.get("per_frame"):
                        item["body_clearance"]["per_frame"] = model_fixture.per_frame_from(model, series)
                    if spec.get("model"):
                        item["body_clearance"]["model"] = model
            items.append(item)
        return {"assets": items}

    @staticmethod
    def _profile(bones: list[str], prof: dict, positions: bool, rotations: bool = False) -> dict:
        """10 표본(1/30 초) — 오른손목이 표본 5 에서 prof.peak cm/s 로 한 번 움직이고, 왼손목 = 오른손 + (gap, 0, 0) · 엉덩 ±9(표본 5 부터
        prof.reach cm 아래로 — 손 속도를 바꾸지 않고 엉덩 기준 손 궤적 폭만 키운다) · 발 ±9 × stance · 위팔(어깨)은 손목 위 50 · 아래팔(팔꿈치)
        위 25 cm(팔 길이 50 cm)."""
        if prof.get("speeds"):
            # Phase 8-3 timing — 본별 속도 열(cm/s, 1/30 초 표본)을 그대로(위치는 쓰지 않는다)
            n = len(next(iter(prof["speeds"].values())))
            return {"times": [round((i + 1) / 30, 4) for i in range(n)], "frames_per_sample": 1,
                    "speed_cm_s": {b: list(prof["speeds"].get(b, [0.0] * n)) for b in bones}}
        n, dt = 10, 1 / 30
        gap, stance, peak, reach = prof.get("gap", 60.0), prof.get("stance", 5.0), prof.get("peak", 300.0), prof.get("reach", 0.0)
        right = [[0.0, 30.0 + (peak * dt if i >= 5 else 0.0), 120.0] for i in range(n)]
        left = [[x + gap, y, z] for x, y, z in right]
        hip_z = [95.0 - (reach if i >= 5 else 0.0) for i in range(n)]
        tracks = {"hand_r": right, "hand_l": left, "thigh_l": [[9.0, 0.0, z] for z in hip_z], "thigh_r": [[-9.0, 0.0, z] for z in hip_z],
                  "foot_l": [[9.0 * stance, 0.0, 8.0]] * n, "foot_r": [[-9.0 * stance, 0.0, 8.0]] * n,
                  "upperarm_r": [[x, y, z + 50.0] for x, y, z in right], "upperarm_l": [[x, y, z + 50.0] for x, y, z in left],
                  "lowerarm_r": [[x, y, z + 25.0] for x, y, z in right], "lowerarm_l": [[x, y, z + 25.0] for x, y, z in left]}
        out = {"times": [round((i + 1) * dt, 4) for i in range(n)], "frames_per_sample": 1,
               "speed_cm_s": {b: [0.0] * n for b in bones if b in tracks}}
        if positions:
            out["position_cm"] = {b: tracks[b] for b in bones if b in tracks}
        if rotations:
            # Phase 8-4a profile_rotations — 같은 표본의 컴포넌트 공간 쿼터니언(흉내는 항등)
            out["rotations"] = {b: [[0.0, 0.0, 0.0, 1.0]] * n for b in bones if b in tracks}
        return out

    def _import_animation_file(self, p):
        dest = package_path(p["dest_path"])
        self._allowed(dest)
        anim_info = {"class": "AnimSequence", "length": 2.0, "frame_rate": 30.0, "loop": False, "root_motion": False}
        if any(path.rsplit("/", 1)[0] == dest for path in self.assets):
            # 플러그인처럼 빈 폴더에만(하위 폴더는 보지 않는다 — AnimMcpAnimImport.cpp DEST_NOT_EMPTY)
            raise _Refuse(err("ASSET_EXISTS", f"'{dest}' already holds assets — import into an empty folder", reason="DEST_NOT_EMPTY"))
        if p.get("skeleton"):
            # 기존 스켈레톤에 애니만 (메시 · 스켈레톤을 만들지 않는다). name 이 있으면 그 이름(플러그인: 기본은 파일 이름)
            skel = package_path(p["skeleton"])
            anim = self._new(f"{dest}/{p.get('name') or 'Mock_Anim'}", **anim_info, skeleton=skel)
            return {"imported": [_obj(anim)], "animations": [{"asset": _obj(anim), "skeleton": _obj(skel)}], "skeleton": _obj(skel), "mesh": None,
                    "skeleton_created": False}
        skel = self._new(f"{dest}/Mock_Skeleton", **{"class": "Skeleton"})
        mesh = self._new(f"{dest}/Mock", **{"class": "SkeletalMesh", "skeleton": skel})
        self.meshes[skel] = mesh
        anim = self._new(f"{dest}/Mock_Anim", **anim_info, skeleton=skel)
        return {"imported": [_obj(skel), _obj(mesh), _obj(anim)], "animations": [{"asset": _obj(anim), "skeleton": _obj(skel)}],
                "skeleton": _obj(skel), "mesh": _obj(mesh)}

    def _create_ik_rig(self, p):
        if p.get("mode", "auto") == "auto" and package_path(p["skeletal_mesh"]) in self.auto_rig_fail:
            raise _Refuse(err("IKRIG_AUTO_FAILED", "no template", bones=[{"name": "root", "parent": None}]))
        return {"asset_path": _obj(self._new(p["asset_path"], **{"class": "IKRigDefinition"}))}

    def _create_ik_retargeter(self, p):
        yaw = p.get("facing_yaw_deg") or 0.0
        return {"asset_path": _obj(self._new(p["asset_path"], **{"class": "IKRetargeter"})),
                "facing_alignment": {"yaw_deg": yaw, "target_root": "root", "consistent": True} if yaw else None}

    def _retarget_animations(self, p):
        target_skel = next(s for s, m in self.meshes.items() if m == package_path(p["target_mesh"]))
        rule = p.get("name_rule") or {}
        generated, items = [], []
        for a in p["assets"]:
            src = self._source(a)
            name = asset_name(a).replace(rule.get("replace_from", ""), rule.get("replace_to", "")) if rule.get("replace_from") else asset_name(a)
            name = f"{rule.get('prefix', '')}{name}{rule.get('suffix', '')}"
            path = self._new(f"{package_path(p['output_path'])}/{name}", **{**src, "skeleton": target_skel})
            generated.append({"source": _obj(a), "asset": _obj(path)})
            items.append({"asset": _obj(path), "status": "PASSED_WITH_WARNINGS",
                          "numeric": {"length": src["length"], "frame_rate": src["frame_rate"], "loop": src["loop"]}})
        out = {"generated": generated, "validation": {"status": "PASSED_WITH_WARNINGS", "assets": items}, "saved": p.get("save", False)}
        if p.get("body_clearance") == "resolve":
            # 팔-몸통 관통 보정 — 왼팔만 고쳐진 모양 (수치는 고정값)
            arm = lambda side, pen: {"upper_arm": f"upperarm_{side}", "frames_over_penetration_pct": pen}  # noqa: E731
            out["body_clearance"] = [{"asset": g["asset"], "modified": True, "issues": [],
                                      "arms": [{"upper_arm": "upperarm_l", "corrected_frames_pct": 40.0, "deg_max": 9.5},
                                               {"upper_arm": "upperarm_r", "corrected_frames_pct": 0.0, "deg_max": 0.0}],
                                      "before": {"arms": [arm("l", 30.0), arm("r", 0.0)]}, "after": {"arms": [arm("l", 0.0), arm("r", 0.0)]}}
                                     for g in generated]
        return out

    # ---- Phase 8-2 — 대상 메시 캡처 (플러그인 AnimMcpCapture 흉내 — 작은 진짜 PNG 를 쓴다) ----
    def _capture_animation(self, p):
        out = pathlib.Path(p["output_dir"])
        if not any(str(out.as_posix()).startswith(r.rstrip("/") + "/") for r in self.capture_roots):
            raise _Refuse(err("OUTPUT_PATH_NOT_ALLOWED", f"{out} is not below CaptureOutputRoots", reason="CAPTURE_ROOT", field="output_dir"))
        if out.exists() and any(out.iterdir()):
            raise _Refuse(err("BAD_REQUEST", f"{out} is not empty", reason="OUTPUT_DIR_NOT_EMPTY", field="output_dir"))
        if self.capture_dirty:
            raise _Refuse(err("UNEXPECTED_DIRTY", "capture left packages dirty", unexpected=self.capture_dirty, dir=out.as_posix()))
        info = self._source(p["asset"])
        if p.get("facing") not in ("+X", "-X", "+Y", "-Y"):
            raise _Refuse(err("BAD_REQUEST", "bad facing", field="facing"))
        length, fps = info["length"], info["frame_rate"]
        times = p.get("times") or [round(i * length / max(1, p.get("count", 4) - 1), 4) for i in range(p.get("count", 4))]
        views = p.get("views") or ["front", "side"]
        out.mkdir(parents=True, exist_ok=True)
        frames, rows = [], []
        for r, t in enumerate(times):
            frame = min(round(t * fps), round(length * fps))
            rows.append({"time": t, "frame": frame, "frame_time": round(frame / fps, 4), "clamped": False, "pose_center": [0, 0, 100 + r]})
            for v in views:
                path = out / f"{v}_{frame:05d}.png"
                write_png(path, 6, 8, (r * 10, 20, 30))
                frames.append({"row": r, "time": t, "frame": frame, "frame_time": round(frame / fps, 4), "view": v, "path": path.as_posix(),
                               "sha1": f"fake{r}{v}", "subject_px": {"x0": 1, "y0": 1, "x1": 4, "y1": 6}, "coverage_pct": 30.0, "touches_edge": False})
        write_png(out / "sheet.png", 12, 16, (1, 2, 3))
        compare = None
        if p.get("compare"):
            for row in p["compare"]["rows"]:
                for img in row:
                    if not pathlib.Path(img).is_file():
                        raise _Refuse(err("BAD_REQUEST", f"no file at {img}", reason="FILE_NOT_FOUND", field="compare"))
            write_png(out / "compare.png", 24, 16, (4, 5, 6))
            compare = {"path": (out / "compare.png").as_posix(), "label": p["compare"].get("label", ""), "own_columns": len(views),
                       "compare_columns": len(p["compare"]["rows"][0]), "size": [24, 16], "scale": 1.0}
        sequence = None
        if p.get("sequence"):
            seq_fps = p["sequence"].get("fps", 15)
            n = min(math.ceil(length * seq_fps - 1e-3) + 1, p["sequence"].get("max_frames", 150))  # 플러그인처럼 끝 프레임까지
            seq_dir = out / "sequence"
            seq_dir.mkdir()
            paths = []
            for k in range(n):
                write_png(seq_dir / f"f_{k:05d}.png", 10, 4, (k % 256, 0, 0))
                paths.append((seq_dir / f"f_{k:05d}.png").as_posix())
            sequence = {"dir": seq_dir.as_posix(), "fps": seq_fps, "count": n, "frames": paths, "times": [round(k / seq_fps, 4) for k in range(n)],
                        "size": [10, 4], "truncated": False, "seconds": 0.01}
        return {"asset": _obj(p["asset"]), "mesh": _obj(p["mesh"]), "facing": p["facing"], "length": length, "frame_rate": fps,
                "dir": out.as_posix(), "frames": frames, "sheet": (out / "sheet.png").as_posix(), "compare": compare, "sequence": sequence,
                "layout": {"rows": rows, "columns": [{"kind": "view", "view": v, "width": 6} for v in views], "cell_height": 8, "gap": 6,
                           "size": [12, 16], "scale": 1.0},
                "camera": {v: {"look": [0, -1, 0], "right": [1, 0, 0], "ortho_width_cm": 200.0, "resolution": [6, 8], "cm_per_px": 0.4} for v in views},
                "bounds": {"min": [-50, -30, 0], "max": [50, 30, 180], "frames_sampled": 10, "from": "bone_vertex_boxes"},
                "cells_touching_edge": 0, "seconds": 0.05}

    # ---- Phase 7 — 포장 · 연결 (플러그인의 옵트인 generation_guard 흉내) ----
    def _guard(self, p: dict, path: str) -> dict | None:
        if not p.get("generation_guard"):
            return None
        self._allowed(path)
        if p.get("overwrite"):
            raise _Refuse(err("BAD_REQUEST", "generation_guard never overwrites", reason="OVERWRITE_NOT_ALLOWED", field="overwrite"))
        return {"enabled": True, "newly_dirty": [package_path(path)]}

    def _set_sequence_additive(self, p):
        path = package_path(p["asset_path"])
        guard = self._guard(p, path)
        info = self._source(path)
        info.update({k: p[k] for k in ("additive_type", "ref_pose_type", "ref_frame_index") if k in p})
        return {"asset_path": _obj(path), "additive_type": f"AAT_{info.get('additive_type', 'None')}", "ref_pose_type": f"ABPT_{info.get('ref_pose_type', 'RefPose')}",
                "ref_pose_sequence": _obj(p["ref_pose_sequence"]) if p.get("ref_pose_sequence") else None, "ref_frame_index": info.get("ref_frame_index", 0),
                "additive_valid": True, "changed": ["AdditiveAnimType"], "unchanged": False, "saved": p.get("save", False), **({"guard": guard} if guard else {})}

    def _create_anim_montage(self, p):
        guard = self._guard(p, p["asset_path"])
        anim = self._source(p["animation"])
        slot = p.get("slot", "DefaultSlot")
        if slot not in self.slots.get(anim["skeleton"], ["DefaultSlot"]):
            raise _Refuse(err("BAD_REQUEST", f"Slot '{slot}' is not registered", reason="SLOT_NOT_IN_SKELETON", field="slot"))
        path = self._new(p["asset_path"], **{"class": "AnimMontage", "skeleton": anim["skeleton"], "length": anim["length"], "frame_rate": anim["frame_rate"],
                                             "loop": False, "root_motion": False, "slot": slot, "animation": package_path(p["animation"])})
        return {"asset_path": _obj(path), "class": "AnimMontage", "length": anim["length"], "slots": [{"index": 0, "name": slot}],
                "sections": [{"name": "Default", "start": 0.0, "next": None}], "blend_in": p.get("blend_in", 0.25), "blend_out": p.get("blend_out", 0.25),
                "created": True, "saved": p.get("save", False), **({"guard": guard} if guard else {})}

    def _set_montage_sections(self, p):
        path = package_path(p["asset_path"])
        guard = self._guard(p, path)
        info = self._source(path)
        names = [s["name"] for s in p["sections"]]
        if any(s.get("next") and s["next"] not in names for s in p["sections"]):
            raise _Refuse(err("BAD_REQUEST", "next not found", reason="NEXT_NOT_FOUND"))
        info["sections"] = p["sections"]
        return {"asset_path": _obj(path), "length": info["length"], "sections": [{"name": s["name"], "start": s["start"], "next": s.get("next")} for s in p["sections"]],
                "unchanged": False, "saved": p.get("save", False), **({"guard": guard} if guard else {})}

    def _create_blendspace(self, p):
        guard = self._guard(p, p["asset_path"])
        skeleton = package_path(p["skeleton"])
        for i, s in enumerate(p.get("samples") or []):
            if self._source(s["animation"]).get("skeleton") != skeleton:
                raise _Refuse(err("BAD_REQUEST", "sample skeleton", reason="SKELETON_MISMATCH", field=f"samples[{i}]"))
        cls = "BlendSpace1D" if p["dimensions"] == 1 else "BlendSpace"
        path = self._new(p["asset_path"], **{"class": cls, "skeleton": skeleton, "samples": p.get("samples") or []})
        return {"asset_path": _obj(path), "class": cls, "sample_count": len(p.get("samples") or []), "samples": p.get("samples") or [], "created": True,
                "saved": p.get("save", False), **({"guard": guard} if guard else {})}

    def _abp(self, path: str) -> dict:
        info = self.abps.get(package_path(path))
        if info is None:
            raise _Refuse(err("ASSET_NOT_FOUND", f"No asset at '{path}'"))
        return info

    def _get_anim_blueprint_info(self, p):
        info = self._abp(p["asset_path"])
        return {"asset_path": _obj(p["asset_path"]), "revision": info["revision"], "target_skeleton": _obj(info["skeleton"])}

    def _plan_ops(self, ops):
        planned = [{"index": i, "op": o.get("op"), "ok": o.get("op") != "bad_op"} for i, o in enumerate(ops)]
        return planned, all(x["ok"] for x in planned)

    def _preview_graph_operations(self, p):
        info = self._abp(p["asset_path"])
        planned, valid = self._plan_ops(p["operations"])
        return {"valid": valid, "revision": info["revision"], "planned": planned}

    def _duplicate_animation_blueprint(self, p):
        src = self._abp(p["source_path"])
        dest = package_path(p["dest_path"])
        guard = self._guard(p, dest)
        if dest in self.abps or dest in self.assets:
            raise _Refuse(err("ASSET_EXISTS", f"{dest} exists"))
        self.abps[dest] = {"skeleton": src["skeleton"], "revision": src["revision"]}
        self.assets[dest] = {"class": "AnimBlueprint", "skeleton": src["skeleton"]}
        return {"asset_path": _obj(dest), "revision": src["revision"], "source_revision": src["revision"], "duplicated": True,
                "saved": p.get("save", False), **({"guard": guard} if guard else {})}

    def _apply_graph_operations(self, p):
        path = package_path(p["asset_path"])
        guard = self._guard(p, path)
        info = self._abp(path)
        if p.get("expected_revision") and p["expected_revision"] != info["revision"]:
            raise _Refuse(err("REVISION_MISMATCH", "Graph changed since the plan was made", expected=p["expected_revision"], actual=info["revision"]))
        planned, valid = self._plan_ops(p["operations"])
        if not valid:
            raise _Refuse(err("BAD_REQUEST", "One or more operations failed validation; nothing was applied", planned=planned))
        for o in p["operations"]:
            if o.get("op") == "set_asset" and package_path(o.get("asset")) not in self.assets:
                raise _Refuse(err("ASSET_NOT_FOUND", f"{o.get('asset')} not found"))
        before = info["revision"]
        info["revision"] = before + "+"
        compiled = {"ok": self.compile_ok, "num_errors": 0 if self.compile_ok else 1, "num_warnings": 0,
                    "messages": [] if self.compile_ok else [{"level": "error", "text": "bad pin"}]} if p.get("compile") else {"ran": False}
        return {"revision_before": before, "revision_after": info["revision"], "applied": len(p["operations"]), "operations": planned, "refs": {},
                "compile": compiled, "saved": bool(p.get("save") and self.compile_ok), **({"guard": guard} if guard else {})}

    def _compile_animation_blueprint(self, p):
        self._abp(p["asset_path"])
        return {"ok": self.compile_ok, "num_errors": 0 if self.compile_ok else 1, "num_warnings": 0, "messages": []}

    def _run_automation_tests(self, p):
        flt = p["filter"]
        total = 0 if any(s in flt for s in self.smoke_missing) else 1
        failed = int(total > 0 and any(s in flt for s in self.smoke_fail))
        return {"done": True, "total": total, "completed": total, "passed": total - failed, "failed": failed, "ok": not failed,
                "tests": [{"name": flt, "state": "failed" if failed else "Success", "errors": ["smoke boom"] if failed else [], "warnings": []}] if total else []}

    def _run_anim_scenario(self, p):
        self._abp(p["asset_path"])
        job_id = f"scn{len(self.scenario_jobs) + 1}"
        self.scenario_jobs[job_id] = {"params": copy.deepcopy(p), "left": self.scenario_polls}
        return {"job_id": job_id, "done": False, "total": 1, "completed": 0, "tests": []}

    def _poll_automation_tests(self, p):
        job = self.scenario_jobs[p["job_id"]]
        if job["left"] > 0:
            job["left"] -= 1
            return {"job_id": p["job_id"], "done": False, "total": 1, "completed": 0, "tests": []}
        q = job["params"]
        expect = q.get("expect") or {}
        speed = (q.get("set_variables") or {}).get("Speed", 0)
        machines = {m: {"state": "Run" if speed >= 100 else "Idle", "elapsed": 0.3} for m in (expect.get("state_machines") or {"Locomotion": None})}
        montage = q.get("montage")
        slots = {s: bool(montage) and package_path(montage) in self.assets for s in expect.get("slots_active") or []}
        errors = [f"expected '{st}' but it is in '{machines[m]['state']}'" for m, st in (expect.get("state_machines") or {}).items() if machines[m]["state"] != st]
        errors += [f"Slot '{s}' is not active" for s, on in slots.items() if not on]
        observed = {"state_machines": machines, "slots": slots, "montage_playing": bool(montage), "frames_waited": q.get("wait_frames", 10)}
        return {"job_id": p["job_id"], "done": True, "total": 1, "completed": 1, "passed": int(not errors), "failed": int(bool(errors)), "ok": not errors,
                "tests": [{"name": "AnimGraphMcp.Runtime.AnimBlueprint", "state": "failed" if errors else "Success", "errors": errors, "observed": observed}]}

    def _list_animation_assets(self, p):
        prefix = p.get("path_prefix", "/Game")
        items = [{"asset_path": _obj(path), "name": asset_name(path), "class": info.get("class")} for path, info in sorted(self.assets.items())
                 if path.startswith(prefix.rstrip("/") + "/")]
        return {"total": len(items), "returned": len(items), "truncated": False, "assets": items}


class _Refuse(Exception):
    def __init__(self, error: dict):
        super().__init__(error["code"])
        self.error = error


# ---- Mock Provider ----
def _manifest(registry: Registry, name: str, **overrides) -> dict:
    manifest = copy.deepcopy(registry.get(name).manifest)
    manifest.update({"license": "ok", **overrides})
    return manifest


class MockAI(Provider):
    """local_ai 자리. failures 를 앞에서부터 하나씩 던진다."""

    def __init__(self, manifest: dict, failures: list[StepFailed] | None = None):
        super().__init__(manifest)
        self.failures = list(failures or [])
        self.submits = 0

    def run(self, ctx):
        self.submits += 1
        if self.failures:
            raise self.failures.pop(0)
        return StepResult(values={"file": "D:/Mock/local_ai.fbx"})


class MockPaid(Provider):
    """external.meshy 자리 — 유료. 가격 확인 여부 · 비동기 · 실제 금액 · 실패를 고를 수 있다. submits = 외부 호출 횟수."""

    def __init__(self, manifest: dict, price: float = 0.5, cost_known: bool = True, actual: float | None = 0.5, polls_needed: int = 0,
                 failures: list[StepFailed] | None = None):
        super().__init__(manifest)
        self.price = price
        self.cost_known = cost_known
        self.actual = actual
        self.polls_needed = polls_needed
        self.failures = list(failures or [])
        self.submits = 0
        self.polls = 0
        self._left: dict[str, int] = {}

    @property
    def external_calls(self) -> int:
        return self.submits + self.polls

    def estimate(self, request, policy=None):
        if not self.cost_known:
            return {"cost_known": False, "estimate_usd": None, "basis": "mock: price unknown"}
        return {"cost_known": True, "estimate_usd": self.price, "basis": "mock price list"}

    def run(self, ctx):
        self.submits += 1
        if self.failures:
            raise self.failures.pop(0)
        if self.polls_needed:
            task = f"task{self.submits}"
            self._left[task] = self.polls_needed
            return StepResult(pending={"task": task})
        return StepResult(values={"file": "D:/Mock/meshy.fbx"}, actual_cost_usd=self.actual)

    def poll(self, ctx, handle):
        self.polls += 1
        task = handle["task"]
        self._left[task] = self._left.get(task, 1) - 1
        if self._left[task] > 0:
            return None
        return StepResult(values={"file": "D:/Mock/meshy.fbx"}, actual_cost_usd=self.actual)


# ---- 픽스처 ----
@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """진짜 브리지·HTTP 호출 금지 — Mock 단계 테스트는 외부 호출 0 이어야 한다. external.meshy 는 httpx.Client 를 쓰므로 실제 전송 계층
    (HTTPTransport) 자체를 막는다 — 테스트는 httpx.MockTransport 를 준다."""
    import httpx

    from anim_graph_mcp import bridge

    def refuse(*args, **kwargs):
        raise AssertionError("real HTTP call in a mock test")

    monkeypatch.setattr(bridge, "call", refuse)
    monkeypatch.setattr(httpx, "post", refuse)
    monkeypatch.setattr(httpx, "get", refuse)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


@pytest.fixture(autouse=True)
def no_real_subprocess(monkeypatch, tmp_path):
    """정책 기본값의 Blender · Kimodo 경로를 없는 파일로 · 진짜 서브프로세스 금지 — 결과가 이 컴퓨터의 설치 여부에 따라 달라지지 않게."""
    from anim_gen.providers import subprocess_step

    def refuse(*args, **kwargs):
        raise AssertionError("real subprocess in a mock test")

    original = policy_mod.load_default
    missing = tmp_path / "not-installed"
    paths = {"blender_executable": (missing / "blender.exe").as_posix(), "kimodo_python": (missing / "kimodo" / "python.exe").as_posix(),
             "kimodo_hf_cache": (missing / "kimodo" / "hf_cache").as_posix()}
    monkeypatch.setattr(policy_mod, "load_default", lambda: policy_mod.deep_merge(original(), {"paths": paths}))
    monkeypatch.setattr(subprocess_step, "launch", refuse)


@pytest.fixture
def fake():
    return FakeEditor()


@pytest.fixture
def state_dir(tmp_path):
    return tmp_path / "AnimGen"


@pytest.fixture
def make_service(fake, state_dir):
    def make(**replace) -> tuple[Service, Registry]:
        registry = Registry()
        for name, factory in replace.items():
            registry.replace(factory(registry))
        return Service(store=Store(state_dir), registry=registry, editor=fake.client()), registry
    return make


@pytest.fixture
def service(make_service):
    return make_service()[0]


def request(**overrides) -> dict:
    base = {"target_skeleton": VESPER, "hero": "Vesper", "family": "Rifle", "animation_name": "AS_Vesper_Rifle_AimIdle_TwistP3",
            "description": "상체를 왼쪽으로 비튼 조준 대기", "motion_category": "idle", "loop": True,
            "search": {"query": "rifle aim idle", "path_prefix": HERO},
            "edits": {"operations": [{"op": "offset_bone", "targets": [{"bone": "spine_01", "rotation": {"yaw": 15}}]}]},
            "output_path": OUT}
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not ...}


def mock_ai(failures=None):
    return lambda registry: MockAI(_manifest(registry, "local_ai"), failures=failures)


def mock_paid(**kwargs):
    def factory(registry):
        return MockPaid(_manifest(registry, "external.meshy", cost_estimable=True, auth_env=kwargs.pop("auth_env", None)), **kwargs)
    return factory


def enable_paid(service: Service, **billing) -> None:
    env = service.set_generation_policy(patch={"billing": {"paid_api_enabled": True, "max_cost_per_job_usd": 2.0, "max_total_cost_usd": 5.0, **billing}})
    assert env["ok"], env
