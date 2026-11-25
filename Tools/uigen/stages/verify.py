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
  appearance        (1b 후속 J-b) 레퍼런스 ↔ 렌더 국소 차이 진단 결함 0 — gen/diagnose(국소 지도 · 회색 합성 · 3 배 절취선 · 글자 획 맞대기 ·
                    원인 단계). concept 모드만(손 spec 은 건너뜀). 구조 게이트(위 10 개)와 따로 본다 — 결과의 structural_pass 가 그것만의 통과.
  edit_regression   (Phase 4) 이어서 고치기 run(edit.json 이 있을 때)의 고친 시도에만 — 대상 밖은 하나도 안 바뀜(stages/edit · gen/edit_gate). 그때 appearance 는
                    base 와 견줘 나눈 결과(이어받음 · 의도한 변경 · 오류)로 바뀐다. 그 밖의 run 은 게이트 11 개 그대로.

출력: attempts/NNN/{gates.json, geometry.json, render/, sample/} · run 폴더의 render.png(기준 해상도 · force_visible) ·
      render_sample.png(brief sample 을 overrides 로 — 사람 눈용, 게이트 아님) · geometry.json(마지막 시도).
게이트 실패는 예외가 아니다 — 결과를 돌려주고 오케스트레이터가 fix 로 간다. 브리지 자체가 실패하면(렌더 불가 등) 그 게이트들을 실패로 남긴다.
"""
from __future__ import annotations

import shutil
import time

from core import button
from core import config
from core import cppgen
from core import geometry as geo
from core import spec as spec_mod
from core.ue import ToolchainError
from stages import StageError, ue_toolchain
from stages.build import package_of

GATES = ("compile", "bindings", "texture_settings", "offscreen", "overlap", "required_elements", "iou_region", "iou_leaf", "baked_text", "roundtrip",
         "appearance")
RENDER_GATES = ("offscreen", "overlap", "iou_region", "iou_leaf")
APPEARANCE = "appearance"
EDIT_REGRESSION = "edit_regression"


def structural_failed(result: dict) -> list[str]:
    """구조 게이트(appearance 밖) 중 실패 — 재시도 · fix 는 이것만 본다(외형 진단은 통과 뒤 외형 라운드 · 글자 맞춤이 몫)."""
    return [n for n in result.get("failed", []) if n != APPEARANCE]


def appearance_gate(run, attempt: int, rendered: bool, render_state=None) -> tuple[dict, dict | None]:
    """1b 후속 J-b — gen/diagnose 진단 → appearance 게이트 + 기록(run 폴더 diagnosis.json · attempts/NNN/diagnosis/).
    render_state(overrides, name="state") → PNG(1b 후속 K): 숨은 위젯을 컨셉 상태로 켜고 끈 엔진 렌더 — 사람 눈 그림 compare.png(run 폴더에도 복사) · E8.
    1b 후속 L 다음 — 상태 검사(gen/state_check)가 같은 함수로 게임 기본 상태 · 게이지 진행률 렌더를 이름(폴더)마다 더 받는다."""
    from gen import diagnose
    if not diagnose.enabled(run.cfg):
        return gate(APPEARANCE, True, skipped="appearance.enabled is off"), None
    if not run.path("reference.png").is_file():
        return gate(APPEARANCE, True, skipped="no reference (hand spec) — nothing to compare"), None
    if not rendered:
        return gate(APPEARANCE, False, details={"error": "the render failed this attempt — nothing to diagnose"}), None
    try:
        rec = diagnose.diagnose(run.dir, attempt_dir(run, attempt) / "diagnosis", run.cfg, render_state=render_state)
    except Exception as exc:  # noqa: BLE001 — 진단이 깨지면 실패로 남긴다(통과로 넘기지 않음)
        return gate(APPEARANCE, False, details={"error": f"{type(exc).__name__}: {exc}"[:300]}), None
    rec["attempt"] = attempt
    cp = attempt_dir(run, attempt) / "diagnosis" / "compare.png"
    if cp.is_file():
        shutil.copyfile(cp, run.path("compare.png"))
    run.write_json("diagnosis.json", rec)
    return diagnose.gate(rec), rec


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


def gate_bindings(comp: dict, contract: list[dict], live: list[dict], hand_written: bool = False) -> dict:
    missing = comp.get("missing_bindings", [])
    diff = cppgen.hand_written_diff(contract, live) if hand_written else cppgen.contract_diff(contract, live)      # 손으로 쓴 부모(Phase 3-2)는 클래스가 원천
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


def gate_bindings_probe(comp: dict, contract: list[dict], exported_spec: dict) -> dict:
    """1b 후속 G2 — 검증 화면(probe): C++ 클래스가 없어 BindWidget 리플렉션 대신 WBP 트리에서 계약 위젯의 이름 · 타입을 본다."""
    have = {w["id"]: w.get("type") for w in exported_spec.get("widgets", [])}
    diff = [f"{b['name']}: missing in the widget tree" if b["name"] not in have else
            f"{b['name']}: {have[b['name']]} in the tree, contract wants {b['widget_class']}" for b in contract if have.get(b["name"]) != b["widget_class"]]
    return gate("bindings", not diff, value=len(diff), threshold=0,
                details={"probe": "no C++ class (probe screen) — names and types checked in the widget tree", "contract_diff": diff,
                         "contract": len(contract), "missing_bindings": comp.get("missing_bindings", [])})


def gate_required(brief: dict, exported_spec: dict, drawn_by_style: str | None = None) -> dict:
    """drawn_by_style = 버튼 칸의 기본 그림 위젯 — 트리 대신 클래스 기본값의 스타일이 그린다(있으면 있는 것으로)."""
    have = {w["id"] for w in exported_spec.get("widgets", [])}
    if drawn_by_style and (exported_spec.get("defaults") or {}).get("Style"):
        have.add(drawn_by_style)
    missing = [el["id"] for el in brief.get("required_elements", []) if el["id"] not in have]
    return gate("required_elements", not missing, value=len(missing), threshold=0,
                details={"missing": missing, "required": len(brief.get("required_elements", []))})


def gate_roundtrip(spec: dict, export: dict, manifest: dict) -> tuple[dict, dict]:
    ue_to_asset = {a["ue_path"]: a["asset_id"] for a in manifest["assets"] if a.get("ue_path")}
    same, diffs = spec_mod.roundtrip_equal(spec, export.get("spec") or {}, ue_to_asset)
    styled = button.style_diff(spec, export, ue_to_asset)      # 버튼 칸 — 트리에 없는 상태 그림 일곱 · 크기 · 값
    same, diffs = same and not styled, diffs + styled
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


def render_resolutions(cfg: dict, profile: dict, canvas) -> list[list[int]]:
    """게이트 렌더의 해상도 — 프로필이 `resolutions: canvas` 면(칸) 캔버스 크기 하나, 아니면 pipeline.yaml 것 + 캔버스."""
    canvas = [int(v) for v in canvas]
    if profile.get("resolutions") == "canvas":
        return [canvas]
    out = [list(map(int, r)) for r in cfg["render"]["resolutions"]]
    if canvas not in out:
        out.insert(0, canvas)
    return out


def desired_size_note(spec: dict, renders: list[dict], gates_cfg: dict) -> dict | None:
    """버튼 칸 — 자동 크기로 놓았을 때의 크기(render desired_size) ↔ 캔버스. 다르면 화면에 놓을 때 그림이 늘어난다. → {desired, canvas, ok} 또는 None."""
    tol = gates_cfg.get("desired_size_max_px")
    if not button.of(spec) or tol is None:
        return None
    got = next((r.get("desired_size") for r in renders if r.get("desired_size")), None)
    canvas = [float(v) for v in spec["canvas"]]
    return {"desired": got, "canvas": canvas, "ok": got is not None and all(abs(float(a) - b) <= float(tol) for a, b in zip(got, canvas))}


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


class StateRenders:
    """진단의 상태 렌더 — render_state(overrides, name) → PNG(1b 후속 K · L 다음 — 컨셉 상태 · 게임 기본 상태 · 게이지 비율 …, 이름마다 다른 폴더: render_widget 은
    빈 폴더에만 쓴다). prefetch(목록)면 render_widget states 한 호출로 모두 그려 둔다(Phase 2 — 호출마다 SDF 글꼴 준비 2 초를 고정으로 기다리던 것을 한 번으로,
    상태 하나를 그리는 길은 같다). 묶음에 없거나 값이 다르거나 묶음이 실패하면 예전처럼 한 장씩. record = {batch, batch_s, engine_s, single, error}."""

    def __init__(self, tc, wbp: str, adir, canvas):
        self.tc, self.wbp, self.adir, self.canvas = tc, wbp, adir, list(canvas)
        self.done: dict[str, tuple[dict, str]] = {}
        self.requests: dict[str, dict] = {}            # 진단이 요구한 상태 목록(이름 → overrides) — 수정 run 이 앞 · 뒤를 같은 목록으로 견준다
        self.record: dict = {"batch": 0, "single": 0}

    def prefetch(self, requests: dict[str, dict]) -> None:
        self.requests = dict(requests)
        t0 = time.monotonic()
        try:
            r = self.tc.call("render_widget", {"asset_path": self.wbp, "output_dir": self.adir.resolve().as_posix(), "resolutions": [self.canvas],
                                               "force_visible": False, "states": [{"name": n, "overrides": ov} for n, ov in requests.items()]},
                             timeout=180.0 + 2.0 * len(requests))
            self.done = {st["name"]: (requests[st["name"]], st["renders"][0]["png"]) for st in r["states"]}
            self.record.update(batch=len(self.done), batch_s=round(time.monotonic() - t0, 2), engine_s=r.get("seconds"))
        except (ToolchainError, KeyError, IndexError, TypeError) as exc:   # 옛 플러그인(states 를 모름) · 렌더 실패 — 한 장씩
            self.done = {}
            self.record.update(batch=0, error=f"{type(exc).__name__}: {exc}"[:300])

    def __call__(self, overrides, name="state"):
        hit = self.done.get(name)
        if hit is not None and hit[0] == overrides:
            return hit[1]
        self.record["single"] += 1
        out = self.adir / name
        if out.is_dir() and any(out.iterdir()):                            # 묶음이 도중에 실패해 남긴 폴더
            out = self.adir / f"{name}_single"
        r = self.tc.call("render_widget", {"asset_path": self.wbp, "output_dir": out.resolve().as_posix(), "resolutions": [self.canvas],
                                           "force_visible": False, "overrides": overrides, "prefix": name})
        return r["renders"][0]["png"]


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
    resolutions = render_resolutions(cfg, profile, canvas)
    cg_rec = run.read_json("codegen.json")
    contract = cg_rec["contract"]["bindings"]
    probe = cg_rec.get("reason") == "probe"     # 1b 후속 G2 — 검증 화면: C++ 클래스가 없어 bindings 는 WBP 트리에서 이름 · 타입으로
    hand_written = cg_rec.get("reason") == "hand_written"
    adir = attempt_dir(run, attempt)
    adir.mkdir(parents=True, exist_ok=True)
    tc = toolchain or ue_toolchain(run)
    gates: dict[str, dict] = {}
    roundtrip, unsupported, artifacts, notes = None, [], {}, {}
    export = None

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
        if not probe:
            live = tc.call("list_bind_widgets", {"asset_path": wbp})["bindings"]
            gates["bindings"] = gate_bindings(comp, contract, live, hand_written)
    except ToolchainError as exc:
        bridge_failed(["bindings"], exc)
    assets = {a["asset_id"]: a["ue_path"] for a in manifest["assets"] if a.get("ue_path")}
    try:
        export = tc.call("export_widget_spec", {"asset_path": wbp, "assets": assets})
        gates["texture_settings"] = gate_textures(export.get("textures", []), manifest, cfg["textures"])
        gates["required_elements"] = gate_required(brief, export.get("spec") or {}, button.art_id(spec))
        if probe:
            gates["bindings"] = gate_bindings_probe(comp, contract, export.get("spec") or {})
        gates["roundtrip"], roundtrip = gate_roundtrip(spec, export, manifest)
        roundtrip["revision_matches_build"] = export.get("revision") == state.get("revision")
        unsupported = export.get("unsupported") or []
    except ToolchainError as exc:
        bridge_failed(["texture_settings", "required_elements", "roundtrip"] + (["bindings"] if probe else []), exc)
    try:
        rend = tc.call("render_widget", {"asset_path": wbp, "output_dir": (adir / "render").resolve().as_posix(), "resolutions": resolutions,
                                         "force_visible": True, "prefix": "render"})
        renders = [{**r, "geometry": button.geometry_rows(spec, r["geometry"])} for r in rend["renders"]]
        rgates, extra = render_gates(spec, renders, canvas, gates_cfg, profile.get("stacking_parents"))
        for g in rgates:
            gates[g["name"]] = g
        notes["placement_inner"] = extra["inner"]   # 박스 등 중간 위젯 — 기록만
        ds = desired_size_note(spec, renders, gates_cfg)
        if ds is not None:                          # 칸의 자기 크기는 배치의 일부다 — iou_region 게이트에 싣는다
            notes["desired_size"] = ds
            if not ds["ok"]:
                g = gates["iou_region"]
                g["pass"] = False
                g["details"]["desired_size"] = ds
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
    render_state = StateRenders(tc, wbp, adir, canvas)
    gates[APPEARANCE], diag = appearance_gate(run, attempt, "render" in artifacts, render_state)
    notes["state_renders"] = render_state.record
    if render_state.record.get("error"):
        run.log(f"verify: state renders one by one — {render_state.record['error']}")
    if diag and diag.get("pictures"):
        artifacts["diagnosis"] = f"attempts/{attempt:03d}/diagnosis/{diag['pictures'][0]}"
    if run.path("compare.png").is_file():
        artifacts["compare"] = "compare.png"
    if run.path("edit.json").is_file():          # Phase 4 — 이어서 고치기: base 면 기록만, 고친 시도면 12 번째 게이트 + 외형 나누기
        from stages import edit
        edit.after_verify(run, attempt, tc, wbp, gates, {"export": export, "requests": render_state.requests, "diagnosis": diag}, artifacts)

    ordered = [gates[n] for n in (*GATES, EDIT_REGRESSION) if n in gates]
    failed = [g["name"] for g in ordered if not g["pass"]]
    result = {"schema_version": 1, "run_id": run.run_id, "attempt": attempt, "pass": not failed, "failed": failed, "gates": ordered,
              "structural_pass": not [n for n in failed if n != APPEARANCE],
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
