"""blender Provider — headless Blender 로 BVH → FBX (지침서 §4 · §14 Phase 4).

계획: BVH 헤더를 Python 으로 읽어(bvh.py) 단위 · 정면 회전 · 범위 · fps 를 정하고 계획에 고정한다 — Blender 를 띄우지 않는다.
실행: blender -b --factory-startup -P anim_gen/blender/bvh_to_fbx.py -- args.json 을 Popen 으로 띄우고 pending 핸들을 돌려준다.
게임 스레드 · 백그라운드 스레드 없이 get_generation_status 의 poll 이 끝났는지 본다(§3.4 · §16-14). 출력은 ini ImportSourceRoots
아래만(<첫 루트>/Blender/<job_id>/A<n>/) — 그 FBX 를 retarget 파이프의 import 단계가 받는다. 취소하면 프로세스를 끝낸다
(로컬 프로세스라 실제로 멈춘다 — 외부 API 의 '결과 무시'와 다르다). 자식 프로세스는 stdin 을 막고 출력을 로그 파일로 보낸다
(anim-gen-mcp 는 stdio MCP 라 상속하면 프로토콜이 깨진다).
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import time

from .. import bvh
from ..editor import EditorCallError
from ..envelope import AnimGenError, diag, limitation
from ..fallback import from_editor_error
from ..store import PROJECT_DIR
from .base import PlanBlocked, PlanContext, Provider, RunContext, StepFailed, StepResult

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "blender" / "bvh_to_fbx.py"
PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_TIMEOUT_S = 300
FPS_SNAP = 0.05           # 120.0048 fps(Frame Time 0.008333) 같은 반올림 오차는 정수 fps 로 맞춘다
LOG_TAIL_LINES = 3
PROXY_MESH = {"min_width_cm": 0.5, "width_ratio": 0.08}
_SECRET_ENV = re.compile(r"(API_KEY|APIKEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)
_NAME = re.compile(r"[^A-Za-z0-9_]")


def import_roots(settings: dict | None) -> list[pathlib.Path]:
    """get_editor_status.generation.import_source_roots — ini 가 유일한 기준(§3.1-6). 상대 경로는 프로젝트 기준."""
    raw = ((settings or {}).get("generation") or {}).get("import_source_roots") or []
    return [p if p.is_absolute() else PROJECT_DIR / p for p in map(pathlib.Path, raw)]


def is_under(path: str | os.PathLike, root: str | os.PathLike) -> bool:
    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    try:
        return os.path.commonpath([a, b]) == b
    except ValueError:  # 다른 드라이브
        return False


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def child_env() -> dict:
    """키 · 토큰 이름의 환경 변수는 넘기지 않는다(§16-16 — Blender 는 필요 없다)."""
    return {k: v for k, v in os.environ.items() if not _SECRET_ENV.search(k)}


def launch(cmd: list[str], **kwargs):
    """실제 서브프로세스 — 테스트는 Provider 에 popen 을 주거나 이 함수를 막는다."""
    return subprocess.Popen(cmd, **kwargs)


class BlenderProvider(Provider):
    def __init__(self, manifest: dict, *, popen=None, clock=None):
        super().__init__(manifest)
        self._popen = popen
        self._clock = clock or time.time
        self._procs: dict[str, object] = {}   # 출력 폴더 → Popen. 이 서버 프로세스 안에서만 — 다시 뜨면 report 파일로 판정한다

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
            resolved = self.resolve(request, pctx.settings, pctx.editor if pctx.editor_ok else None)
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
        return {"step": "convert", "provider": self.name, "tool": "blender -b -P anim_gen/blender/bvh_to_fbx.py", "inputs": dict(mf),
                "resolved": resolved, "risks": risks, "expected_limitations": self.limitations(resolved), "sample_rate": resolved["sample_rate"],
                "measured": {"length": rng["duration"], "frame_rate": resolved["sample_rate"] or resolved["fps"]["output"]}}

    def resolve(self, request: dict, settings: dict | None, editor) -> dict:
        """BVH → 계획에 고정할 값. settings 가 없으면 루트 검사를, editor 가 없으면 대상 정면 측정을 미룬다."""
        mf = request["motion_file"]
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
    def check_root(path: pathlib.Path, settings: dict | None) -> None:
        if settings is None:
            return
        roots = import_roots(settings)
        if not any(is_under(path, root) for root in roots):
            raise AnimGenError("IMPORT_SOURCE_NOT_ALLOWED", f"{path.as_posix()} is outside [AnimGraphMcp] ImportSourceRoots — put the motion file under one",
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

    # ---- 실행 ----
    def run(self, ctx: RunContext) -> StepResult:
        exe = self.executable(ctx.policy)
        if not exe or not pathlib.Path(exe).is_file():
            raise StepFailed("PROVIDER_UNAVAILABLE", "NOT_INSTALLED", f"blender_executable not found: {exe}")
        settings = ctx.editor.status()
        if settings is None:
            raise StepFailed("PROVIDER_UNAVAILABLE", "EDITOR", "Editor unreachable — import roots come from get_editor_status and the next steps need it",
                             fatal=True)
        resolved = self._resolve_at_run(ctx, settings)
        out_dir = import_roots(settings)[0] / "Blender" / ctx.job_id / f"A{ctx.attempt}"
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = {name: out_dir / file for name, file in (("fbx", f"{resolved['name']}.fbx"), ("report", "report.json"), ("log", "blender.log"),
                                                          ("args", "args.json"))}
        paths["report"].unlink(missing_ok=True)  # 같은 시도 폴더의 이전 report 가 '끝남'으로 읽히지 않게
        mf = ctx.request["motion_file"]
        args = {"bvh": resolved["file"], "fbx": paths["fbx"].as_posix(), "report": paths["report"].as_posix(), "cm_per_unit": resolved["unit"]["cm_per_unit"],
                "axis_forward": mf["axis_forward"], "axis_up": mf["axis_up"], "rotate_z_deg": resolved["facing"]["rotate_z_deg"],
                "first": resolved["range"]["first"], "last": resolved["range"]["last"], "fps": resolved["fps"]["output"], "proxy_mesh": PROXY_MESH,
                "package_dir": PACKAGE_DIR.as_posix()}
        paths["args"].write_text(json.dumps(args, ensure_ascii=False, indent=1), encoding="utf-8")
        cmd = [exe, "-b", "--factory-startup", "--python-exit-code", "3", "-P", str(SCRIPT), "--", str(paths["args"])]
        kwargs = {"stdin": subprocess.DEVNULL, "stderr": subprocess.STDOUT, "cwd": str(out_dir), "env": child_env()}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        with paths["log"].open("wb") as log:
            try:
                proc = (self._popen or launch)(cmd, stdout=log, **kwargs)
            except OSError as exc:
                raise StepFailed("PROVIDER_UNAVAILABLE", "LAUNCH_FAILED", f"could not start Blender: {exc}") from None
        timeout = float(((ctx.policy or {}).get("execution") or {}).get("subprocess_timeout_seconds", DEFAULT_TIMEOUT_S))
        started = self._clock()
        handle = {"pid": proc.pid, "started_at": started, "deadline": started + timeout, "timeout_s": timeout, "dir": out_dir.as_posix(),
                  **{name: p.as_posix() for name, p in paths.items()},
                  "resolved": {k: resolved[k] for k in ("file", "sha256", "unit", "range", "fps", "facing", "name")},
                  "joint_count": resolved["bvh"]["joint_count"]}
        self._procs[handle["dir"]] = proc
        return StepResult(pending=handle)

    def _resolve_at_run(self, ctx: RunContext, settings: dict) -> dict:
        """계획 값을 그대로 쓰되, 파일이 바뀌었으면 멈춘다. 계획 때 에디터가 없어 못 정한 값(루트 · 대상 정면)은 지금 정한다."""
        planned = ctx.step.get("resolved")
        try:
            if planned is None or not planned["facing"]["resolved"]:
                resolved = self.resolve(ctx.request, settings, ctx.editor)
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
        return resolved

    def poll(self, ctx: RunContext, handle: dict) -> StepResult | None:
        key = handle["dir"]
        proc = self._procs.get(key)
        code = proc.poll() if proc is not None else None
        if proc is not None and code is None:
            if self._clock() > handle["deadline"]:
                self._stop(key)
                raise StepFailed("GENERATION_FAILED", "TIMEOUT", f"Blender ran over {handle['timeout_s']:.0f}s and was stopped{self._tail(handle)}")
            return None
        report = _read_json(handle["report"])
        if proc is None and report is None:
            # 서버가 다시 떴다 — 이 프로세스의 핸들이 없어 끝났는지는 report 로만 안다
            if self._clock() <= handle["deadline"]:
                return None
            raise StepFailed("GENERATION_FAILED", "TIMEOUT", f"no Blender report by the deadline and the process (pid {handle['pid']}) is not tracked "
                             f"after a server restart — it was not stopped{self._tail(handle)}")
        self._procs.pop(key, None)
        if report is None:
            raise StepFailed("GENERATION_FAILED", f"BLENDER_EXIT_{code}", f"Blender exited ({code}) without a report{self._tail(handle)}")
        if not report.get("ok"):
            error = report.get("error") or {}
            raise StepFailed("GENERATION_FAILED", error.get("code") or "BLENDER_FAILED", f"bvh_to_fbx: {error.get('message')}{self._tail(handle)}")
        if not pathlib.Path(handle["fbx"]).is_file():
            raise StepFailed("GENERATION_FAILED", "NO_OUTPUT", f"Blender reported success but {handle['fbx']} is missing{self._tail(handle)}")
        return self._result(handle, report)

    def _result(self, handle: dict, report: dict) -> StepResult:
        resolved = handle["resolved"]
        converted = {k: report.get(k) for k in ("blender", "bones", "roots", "rest_height_cm", "ground_lift_cm", "rotate_z_deg", "frames",
                                                 "root_path", "fbx_bytes", "seconds")}
        converted["facing"] = (report.get("facing") or {}).get("axis")
        diagnostics = [diag("info", "BLENDER_CONVERTED", f"{pathlib.Path(resolved['file']).name} → {pathlib.Path(handle['fbx']).name}: "
                            f"{report.get('bones')} bones, {(report.get('frames') or {}).get('keys')} keys, {report.get('seconds')}s")]
        target = resolved["facing"].get("target")
        if target and converted["facing"] != target:
            diagnostics.append(diag("warning", "FACING_MISMATCH", f"converted skeleton faces {converted['facing']}, the target faces {target}"))
        if report.get("bones") != handle["joint_count"]:
            diagnostics.append(diag("warning", "BONE_COUNT_MISMATCH", f"{report.get('bones')} bones from {handle['joint_count']} BVH joints"))
        return StepResult(values={"file": handle["fbx"], "converted": converted}, limitations=self.limitations(resolved), diagnostics=diagnostics)

    def cancel(self, handle: dict) -> dict | None:
        pid = handle.get("pid")
        if handle.get("dir") not in self._procs:
            return {"stopped": False, "reason": "NOT_TRACKED", "pid": pid}
        return {"stopped": self._stop(handle["dir"]), "pid": pid}

    def _stop(self, key: str) -> bool:
        proc = self._procs.pop(key, None)
        if proc is None or proc.poll() is not None:
            return False
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return True

    @staticmethod
    def _tail(handle: dict) -> str:
        try:
            lines = [ln for ln in pathlib.Path(handle["log"]).read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        except OSError:
            return f" (log: {handle['log']})"
        tail = " | ".join(lines[-LOG_TAIL_LINES:])
        return f" (log: {handle['log']}{' — ' + tail if tail else ''})"


def _read_json(path: str) -> dict | None:
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
