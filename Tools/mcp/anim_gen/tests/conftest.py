"""anim_gen pytest 공통 — 에디터 없이 돈다 (지침서 §14 Phase 3 · 4 완료 기준).

FakeEditor 는 플러그인 Tool 봉투를 흉내 낸다(허용 목록 · 덮어쓰기 없음 · 스켈레톤). Mock Provider 는 local_ai · external.meshy
자리에 끼워 실제 규칙 표로 시험한다. 진짜 HTTP 와 서브프로세스는 막아 둔다 — 호출되면 테스트가 실패한다. 정책의 Blender 경로는
기본으로 없는 파일을 가리킨다(이 컴퓨터에 Blender · Kimodo 가 있어도 결과가 같다) — Blender 테스트는 test_blender.py, Kimodo 테스트는
test_local_ai.py 가 가짜 실행 파일 · 캐시를 준다.

    Tools/mcp/.venv/Scripts/python.exe -m pytest Tools/mcp/anim_gen/tests -q
"""
from __future__ import annotations

import copy
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from anim_gen import policy as policy_mod  # noqa: E402
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
WRITE_TOOLS = {"apply_animation_edits", "retarget_animations", "import_animation_file", "create_ik_rig", "create_ik_retargeter"}
KNOWN_OPS = {"trim", "retime", "hold_pose", "concat", "mirror", "offset_bone", "rotate_root"}


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
        }

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
                               "max_retarget_assets_per_call": 50}, "dirty_package_count": 0}

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
                "bones": bones}

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
        for op in p["operations"]:
            if op["op"] == "retime" and op.get("duration"):
                length = op["duration"]
        path = self._new(p["asset_path"], **{"class": "AnimSequence", "skeleton": src["skeleton"], "length": length,
                                             "frame_rate": src["frame_rate"], "loop": loop, "root_motion": src["root_motion"]})
        item = {"status": "PASSED", "numeric": {"length": length, "frame_rate": src["frame_rate"], "loop": loop}}
        return {"asset_path": _obj(path), "length": length, "frame_rate": src["frame_rate"], "frames": int(length * src["frame_rate"]),
                "validation": {"status": "PASSED", "asset": item}, "limitations": ["1 notify(ies) dropped"], "saved": p.get("save", False)}

    def _validate_animation(self, p):
        items = []
        for a in p["assets"]:
            info = self._source(a)
            items.append({"asset": _obj(a), "status": info.get("status", "PASSED"),
                          "numeric": {"length": info["length"], "frame_rate": info["frame_rate"], "loop": info["loop"]}})
        return {"assets": items}

    def _import_animation_file(self, p):
        dest = package_path(p["dest_path"])
        self._allowed(dest)
        anim_info = {"class": "AnimSequence", "length": 2.0, "frame_rate": 30.0, "loop": False, "root_motion": False}
        if p.get("skeleton"):
            # 기존 스켈레톤에 애니만 (메시 · 스켈레톤을 만들지 않는다)
            skel = package_path(p["skeleton"])
            anim = self._new(f"{dest}/Mock_Anim", **anim_info, skeleton=skel)
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

    def estimate(self, request):
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
    """진짜 브리지·HTTP 호출 금지 — Mock 단계 테스트는 외부 호출 0 이어야 한다."""
    import httpx

    from anim_graph_mcp import bridge

    def refuse(*args, **kwargs):
        raise AssertionError("real HTTP call in a mock test")

    monkeypatch.setattr(bridge, "call", refuse)
    monkeypatch.setattr(httpx, "post", refuse)
    monkeypatch.setattr(httpx, "get", refuse)


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
