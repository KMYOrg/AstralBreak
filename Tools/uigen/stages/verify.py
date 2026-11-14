"""verify — 합격 게이트 (설계 §2-2 verify · §8-1). 값은 profiles/<screen_type>.yaml gates (잠정).

게이트(전부 report.json gates[] 에 남는다 — 통과 · 실패 · 건너뜀 모두):
  compile           compile_widget_blueprint 오류 0
  bindings          missing_bindings 0 이고 list_bind_widgets(WBP 의 부모) = codegen 계약
  texture_settings  export_widget_spec 의 textures[] 가 manifest 와 같음(압축 · 그룹 · 밉 · 스트리밍 · sRGB)
  offscreen         3 해상도 렌더(force_visible)에서 보이는 위젯이 화면 안
  overlap           형제 bbox 교차 / 작은 쪽 면적 > overlap_max_ratio 가 0 (Overlay 자식끼리 · allow_overlap 제외)
  required_elements brief.required_elements 가 WBP 에 다 있음
  iou_region        기준 해상도(spec.canvas)에서 루트 Canvas 직계의 bbox_intent 대비 IoU ≥ iou_region_min (작으면 중심점)
  iou_leaf          말단 위젯 IoU ≥ iou_leaf_min · min(w, h) < small_px 면 중심점 거리 ≤ small_center_max_px
  baked_text        생성 에셋 OCR 검출 0 — procedural 은 건너뜀(통과 + 이유)
  roundtrip         export → core.spec.roundtrip_equal(정규화 비교) · GUID 맵 누락 0

출력: attempts/NNN/{gates.json, geometry.json, render/, sample/} · run 폴더의 render.png(기준 해상도 · force_visible) ·
      render_sample.png(brief sample 을 overrides 로 — 사람 눈용, 게이트 아님) · geometry.json(마지막 시도).
게이트 실패는 예외가 아니다 — 결과를 돌려주고 오케스트레이터가 fix 로 간다. 브리지 자체가 실패하면(렌더 불가 등) 그 게이트들을 실패로 남긴다.
"""
from __future__ import annotations

import shutil
import time

from core import config
from core import cppgen
from core import geometry as geo
from core import spec as spec_mod
from core.ue import ToolchainError
from stages import StageError, ue_toolchain
from stages.build import package_of

GATES = ("compile", "bindings", "texture_settings", "offscreen", "overlap", "required_elements", "iou_region", "iou_leaf", "baked_text", "roundtrip")
RENDER_GATES = ("offscreen", "overlap", "iou_region", "iou_leaf")


def gate(name: str, ok: bool, value=None, threshold=None, details=None, skipped: str | None = None) -> dict:
    g = {"name": name, "pass": bool(ok)}
    if value is not None:
        g["value"] = value
    if threshold is not None:
        g["threshold"] = threshold
    if skipped:
        g["skipped"] = skipped
    if details is not None:
        g["details"] = details
    return g


def attempt_dir(run, attempt: int):
    return run.path("attempts", f"{attempt:03d}")


# ---------------------------------------------------------------------------------------------------------------------
# 게이트 계산 (에디터 결과 → 게이트) — pytest 는 합성 입력으로 부른다

def gate_compile(comp: dict) -> dict:
    msgs = [m for m in comp.get("messages", []) if m.get("level") in ("error", "warning")][:10]
    return gate("compile", comp.get("ok") is True and comp.get("errors", 1) == 0, value=comp.get("errors"), threshold=0,
                details={"status": comp.get("status"), "warnings": comp.get("warnings"), "messages": msgs})


def gate_bindings(comp: dict, contract: list[dict], live: list[dict]) -> dict:
    missing = comp.get("missing_bindings", [])
    diff = cppgen.contract_diff(contract, live)
    return gate("bindings", not missing and not diff, value=len(missing) + len(diff), threshold=0,
                details={"missing_bindings": missing, "contract_diff": diff, "contract": len(contract), "class": len(live)})


def gate_textures(exported: list[dict], manifest: dict, tex_cfg: dict) -> dict:
    by_pkg = {a["ue_path"]: a for a in manifest["assets"] if a.get("ue_path")}
    want_common = {"lod_group": tex_cfg["lod_group"], "mip_gen": tex_cfg["mip_gen"], "never_stream": bool(tex_cfg["never_stream"]),
                   "srgb": bool(tex_cfg["srgb"])}
    rows, bad, seen = [], [], set()
    for t in exported:
        pkg = package_of(t.get("asset_path", ""))
        a = by_pkg.get(pkg)
        if a is None:
            bad.append({"texture": pkg, "problem": "not in manifest"})
            continue
        seen.add(a["asset_id"])
        want = {"compression": a["compression"], **want_common}
        diff = {k: {"want": v, "got": t.get(k)} for k, v in want.items() if t.get(k) != v}
        row = {"asset_id": a["asset_id"], "ue_path": pkg, "size": t.get("size"), **{k: t.get(k) for k in want}}
        if list(t.get("size") or []) != list(a["size"]):
            row["size_note"] = f"manifest {a['size']}"   # 기록만 — 게이트 항목은 다섯 설정
        rows.append(row)
        if diff:
            bad.append({"asset_id": a["asset_id"], "ue_path": pkg, "diff": diff})
    unreferenced = sorted(a["asset_id"] for a in manifest["assets"] if a["asset_id"] not in seen)
    return gate("texture_settings", not bad and bool(rows or not manifest["assets"]), value=len(bad), threshold=0,
                details={"textures": rows, "mismatches": bad, "unreferenced_assets": unreferenced})


def gate_required(brief: dict, exported_spec: dict) -> dict:
    have = {w["id"] for w in exported_spec.get("widgets", [])}
    missing = [el["id"] for el in brief.get("required_elements", []) if el["id"] not in have]
    return gate("required_elements", not missing, value=len(missing), threshold=0,
                details={"missing": missing, "required": len(brief.get("required_elements", []))})


def gate_roundtrip(spec: dict, export: dict, manifest: dict) -> tuple[dict, dict]:
    ue_to_asset = {a["ue_path"]: a["asset_id"] for a in manifest["assets"] if a.get("ue_path")}
    same, diffs = spec_mod.roundtrip_equal(spec, export.get("spec") or {}, ue_to_asset)
    guid_missing = export.get("guid_missing") or []
    rt = {"equal": same, "diffs": diffs[:20], "guid_missing": guid_missing, "unsupported": export.get("unsupported") or [],
          "revision": export.get("revision")}
    return gate("roundtrip", same and not guid_missing, value=len(diffs), threshold=0, details=rt), rt


def gate_baked_text(manifest: dict) -> dict:
    procedural = [a for a in manifest["assets"] if a.get("backend") == "procedural"]
    others = [a for a in manifest["assets"] if a.get("backend") != "procedural"]
    if not others:
        return gate("baked_text", True, skipped="procedural 에셋만 — 글자를 그리지 않아 OCR 해당 없음(1b 부터 생성 이미지 OCR)",
                    details={"procedural": [a["asset_id"] for a in procedural]})
    found = [{"asset_id": a["asset_id"], "text": a["ocr_text"]} for a in others if a.get("ocr_text")]
    pending = [a["asset_id"] for a in others if a.get("ocr_text") is None]
    return gate("baked_text", not found and not pending, value=len(found), threshold=0,
                details={"found": found, "not_checked": pending})


def render_gates(spec: dict, renders: list[dict], canvas, gates_cfg: dict, stacking) -> tuple[list[dict], dict]:
    """렌더 결과 → offscreen · overlap · iou_region · iou_leaf 게이트 + 기준 해상도 geometry."""
    base = next((r for r in renders if list(r["resolution"]) == list(canvas)), renders[0])
    off_all = []
    for r in renders:
        for o in geo.offscreen(r["geometry"], r["resolution"]):
            off_all.append({"resolution": list(r["resolution"]), **o})
    out = [gate("offscreen", len(off_all) <= int(gates_cfg["offscreen_max"]), value=len(off_all), threshold=int(gates_cfg["offscreen_max"]),
                details={"resolutions": [list(r["resolution"]) for r in renders], "offscreen": off_all})]
    ov = geo.overlaps(base["geometry"], spec, float(gates_cfg["overlap_max_ratio"]), stacking)
    out.append(gate("overlap", not ov["violations"], value=len(ov["violations"]), threshold=float(gates_cfg["overlap_max_ratio"]),
                    details={"resolution": list(base["resolution"]), **ov}))
    pl = geo.placement(spec, base["geometry"], gates_cfg)
    for cat, name, key in (("region", "iou_region", "iou_region_min"), ("leaf", "iou_leaf", "iou_leaf_min")):
        rows = pl[cat]
        failed = [r["id"] for r in rows if not r["pass"]]
        out.append(gate(name, not failed, value=geo.placement_gate_value(rows),
                        threshold={"iou": float(gates_cfg[key]), "small_px": float(gates_cfg["small_px"]),
                                   "center_px": float(gates_cfg["small_center_max_px"])},
                        details={"resolution": list(base["resolution"]), "failed": failed, "widgets": rows}))
    return out, {"inner": pl["inner"]}


def sample_overrides(brief: dict) -> dict:
    """brief.dynamic_data 의 sample → render_widget overrides (사람 눈용 렌더)."""
    out: dict[str, dict] = {}
    for d in brief.get("dynamic_data", []):
        s = d.get("sample")
        if s is None:
            continue
        o = out.setdefault(d["widget"], {})
        if d["type"] == "progress":
            o["percent"] = float(s)
        elif d["type"] == "flag":
            o["visible"] = bool(s)
        elif d["type"] == "number":
            digits = cppgen.fraction_digits(d.get("format"))
            o["text"] = f"{float(s):.{digits}f}" if digits else str(int(round(float(s))))
        elif d["type"] == "text":
            o["text"] = str(s)
    return {k: v for k, v in out.items() if v}


# ---------------------------------------------------------------------------------------------------------------------

def run(run, opts, toolchain=None) -> dict:
    """게이트 결과 {attempt, pass, gates, failed, roundtrip, unsupported, artifacts, duration_s} — attempts/NNN/gates.json 에도 쓴다."""
    t0 = time.monotonic()
    attempt = int(getattr(opts, "attempt", 1) or 1)
    cfg = run.cfg
    spec = run.read_json("spec.json")
    brief = run.read_json("brief.json")
    manifest = run.read_json("manifest.json")
    state = run.read_json("build.json")
    if not state.get("wbp"):
        raise StageError("NOTHING_BUILT", "build.json has no widget blueprint")
    wbp = state["wbp"]["asset_path"]
    profile = config.load_profile(spec["profile"])
    gates_cfg = profile["gates"]
    canvas = [int(v) for v in spec["canvas"]]
    resolutions = [list(map(int, r)) for r in cfg["render"]["resolutions"]]
    if canvas not in resolutions:
        resolutions.insert(0, canvas)
    contract = run.read_json("codegen.json")["contract"]["bindings"]
    adir = attempt_dir(run, attempt)
    adir.mkdir(parents=True, exist_ok=True)
    tc = toolchain or ue_toolchain(run)
    gates: dict[str, dict] = {}
    roundtrip, unsupported, artifacts, notes = None, [], {}, {}

    def bridge_failed(names, exc):
        for n in names:
            gates[n] = gate(n, False, details={"error": {"code": exc.code, "message": str(exc)}})

    try:
        comp = tc.call("compile_widget_blueprint", {"asset_path": wbp})
        gates["compile"] = gate_compile(comp)
    except ToolchainError as exc:
        comp = {}
        bridge_failed(["compile"], exc)
    try:
        live = tc.call("list_bind_widgets", {"asset_path": wbp})["bindings"]
        gates["bindings"] = gate_bindings(comp, contract, live)
    except ToolchainError as exc:
        bridge_failed(["bindings"], exc)
    assets = {a["asset_id"]: a["ue_path"] for a in manifest["assets"] if a.get("ue_path")}
    try:
        export = tc.call("export_widget_spec", {"asset_path": wbp, "assets": assets})
        gates["texture_settings"] = gate_textures(export.get("textures", []), manifest, cfg["textures"])
        gates["required_elements"] = gate_required(brief, export.get("spec") or {})
        gates["roundtrip"], roundtrip = gate_roundtrip(spec, export, manifest)
        roundtrip["revision_matches_build"] = export.get("revision") == state.get("revision")
        unsupported = export.get("unsupported") or []
    except ToolchainError as exc:
        bridge_failed(["texture_settings", "required_elements", "roundtrip"], exc)
    try:
        rend = tc.call("render_widget", {"asset_path": wbp, "output_dir": (adir / "render").resolve().as_posix(), "resolutions": resolutions,
                                         "force_visible": True, "prefix": "render"})
        renders = rend["renders"]
        rgates, extra = render_gates(spec, renders, canvas, gates_cfg, profile.get("stacking_parents"))
        for g in rgates:
            gates[g["name"]] = g
        notes["placement_inner"] = extra["inner"]   # 박스 등 중간 위젯 — 기록만
        geometry = {f"{r['resolution'][0]}x{r['resolution'][1]}": r["geometry"] for r in renders}
        doc = {"schema_version": 1, "run_id": run.run_id, "attempt": attempt, "canvas": canvas, "force_visible": True, "geometry": geometry}
        run.write_json(f"attempts/{attempt:03d}/geometry.json", doc)
        run.write_json("geometry.json", doc)
        base = next((r for r in renders if list(r["resolution"]) == canvas), renders[0])
        shutil.copyfile(base["png"], run.path("render.png"))
        artifacts.update(render="render.png", geometry="geometry.json", render_dir=f"attempts/{attempt:03d}/render")
    except (ToolchainError, OSError, KeyError) as exc:
        err = exc if isinstance(exc, ToolchainError) else ToolchainError(type(exc).__name__, str(exc))
        bridge_failed(RENDER_GATES, err)
    gates["baked_text"] = gate_baked_text(manifest)
    try:   # 사람 눈용 — sample 값을 넣고 보이기 규칙 그대로(force_visible 아님). 실패해도 게이트와 무관
        srend = tc.call("render_widget", {"asset_path": wbp, "output_dir": (adir / "sample").resolve().as_posix(), "resolutions": [canvas],
                                          "force_visible": False, "overrides": sample_overrides(brief), "prefix": "sample"})
        shutil.copyfile(srend["renders"][0]["png"], run.path("render_sample.png"))
        artifacts["render_sample"] = "render_sample.png"
    except (ToolchainError, OSError, KeyError, IndexError) as exc:
        notes["sample_render_error"] = str(exc)

    ordered = [gates[n] for n in GATES if n in gates]
    failed = [g["name"] for g in ordered if not g["pass"]]
    result = {"schema_version": 1, "run_id": run.run_id, "attempt": attempt, "pass": not failed, "failed": failed, "gates": ordered,
              "roundtrip": roundtrip, "unsupported": unsupported, "artifacts": artifacts, "notes": notes, "wbp": wbp,
              "revision": state.get("revision"), "duration_s": round(time.monotonic() - t0, 3)}
    run.write_json(f"attempts/{attempt:03d}/gates.json", result)
    return result


def summary(result: dict) -> str:
    n = len(result["gates"])
    if result["pass"]:
        skipped = [g["name"] for g in result["gates"] if g.get("skipped")]
        return f"attempt {result['attempt']}: {n}/{n} gates pass" + (f" ({', '.join(skipped)} skipped)" if skipped else "")
    return f"attempt {result['attempt']}: {n - len(result['failed'])}/{n} gates pass — failed: {', '.join(result['failed'])}"
