"""edit — 이어서 고치기(Phase 4 — 설계 §11 'Phase 4 설계' ② ~ ④). run_pipeline --from <ScreenId | run_id> --edit <patch.json>

  seed   원천(승격본의 원천 묶음 또는 남은 run 폴더)을 새 run 폴더로 — analyze · layer · generate · refine 을 안 돌고 최종 spec · 텍스처를 그대로 쓴다.
         patch 검사(받는 op · 계약 · 어휘)는 여기서 끝낸다 — 에디터 없이 바로 거절.
  base   (시도 1) 고치기 전 spec 을 그대로 짓고 전체 게이트 — 수정의 정답. --from <ScreenId> 면 지금 승격본과 역추출 · 그림까지 같은지도 본다(BASE_DRIFT).
  edit   (시도 2) patch → build → 대상의 bbox_intent 를 새 실측 상자로 → verify(+ 12번째 게이트 edit_regression · 외형 결과 나누기 · edit.png).

LLM 0 · codex 0 · 재시도 0 · 글자 맞춤 0 — 고침 · 글자 맞춤을 켜면 안 바꾼 칸이 다시 흔들린다. 실패하면 이유를 남기고 끝낸다(patch 를 고쳐 다시).
계약이 바뀌면 EDIT_CONTRACT_CHANGED — codegen 의 쓰기 · 빌드까지 가지 않는다.
"""
from __future__ import annotations

import copy
import json
import pathlib
import shutil

from core import button
from core import cellref
from core import config
from core import cppgen
from core import geometry as geo
from core import patch as patch_mod
from core import promotion as promo
from core import schema
from core import spec as spec_mod
from core.run import RUN_ID_RE
from core.ue import ToolchainError
from gen import edit_gate
from stages import StageError, toolchain_error, ue_toolchain

BASE_ATTEMPT, EDIT_ATTEMPT = 1, 2
OPS = ("set", "move", "add_widget", "remove_widget")
PARENT_ONLY = ("lineage.json", "geometry.json", "diagnosis.json", "codegen.json", "edit.json")   # 부모의 기록 — 새 run 의 것과 섞이지 않게 parent/ 로
PATCH_FILE = "patches/001.json"
VIEWS = ("sample", "state", "state_values", "state_off")      # edit.png 에 먼저 넣을 그림(있는 것) — 나머지는 가장 많이 바뀐 것


def screen_of(source: str) -> str:
    """--from 값 → 화면 ID."""
    return source.split("_", 2)[2] if RUN_ID_RE.match(source) else source


def store_of(run, opts) -> promo.Store:
    return promo.Store(getattr(opts, "promoted_root", None), getattr(opts, "content_root", None), run.work_root)


def edit_doc(run) -> dict | None:
    return run.read_json("edit.json") if run.path("edit.json").is_file() else None


def save_doc(run, doc: dict) -> None:
    schema.require("edit", doc)
    run.write_json("edit.json", doc)


# ---------------------------------------------------------------------------------------------------------------------
# seed

def _resolve(run, opts) -> dict:
    """{kind, dir, run_id, promotion, edits} — 승격본이면 파일 · 묶음이 기록 그대로인지도."""
    src = opts.source
    store = store_of(run, opts)
    screen = screen_of(src)
    try:
        rec = store.load(screen)
    except (schema.SchemaError, ValueError) as exc:
        raise StageError("PROMOTION_UNREADABLE", f"{store.record_path(screen)}: {exc}") from exc
    if not RUN_ID_RE.match(src):
        if rec is None:
            raise StageError("NOT_PROMOTED", f"'{src}' has no promotion record ({store.record_path(src).as_posix()}) — promote_screen.py record, or --from <run_id>")
        left = store.unfinished(src)
        if left:
            raise StageError("PROMOTION_UNFINISHED", f"an unfinished promotion is left in {left[0].as_posix()} — promote_screen.py recover {src}")
        bad = store.check_files(rec)
        if bad:
            raise StageError("BASE_DRIFT", f"{rec['dest']} differs from its promotion record {bad} — someone changed the promoted files", diff=bad)
        bad = store.check_source(rec)
        if bad:
            raise StageError("SOURCE_CHANGED", f"the source bundle of '{src}' differs from its promotion record {bad}", diff=bad)
        return {"kind": "promoted", "dir": store.source_dir(src), "run_id": rec["run_id"], "promotion": rec, "edits": rec["edits"]}
    rd = store.run_dir(src)
    for f in ("lineage.json", "report.json", "spec.json", "brief.json", "manifest.json"):
        if not (rd / f).is_file():
            raise StageError("SOURCE_INCOMPLETE", f"{rd.as_posix()} has no {f}")
    status = {f: json.loads((rd / f).read_text(encoding="utf-8")).get("status") for f in ("lineage.json", "report.json")}
    if set(status.values()) != {"pass"}:
        raise StageError("SOURCE_NOT_PASSED", f"{src} is not a passed and saved run: {status}")
    if rec is not None and rec["run_id"] == src:
        edits = rec["edits"]
    else:
        edits = (json.loads((rd / "edit.json").read_text(encoding="utf-8")).get("edits") or []) if (rd / "edit.json").is_file() else []
    return {"kind": "run", "dir": rd, "run_id": src, "promotion": None, "edits": edits}


def _load_patch(path) -> dict:
    try:
        patch = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StageError("EDIT_PATCH_BAD", f"{path}: {exc}") from exc
    errs = schema.errors("patch", patch)
    if errs:
        raise StageError("EDIT_PATCH_BAD", "; ".join(errs[:5]), errors=errs)
    if patch["source"] != "edit":
        raise StageError("EDIT_PATCH_BAD", f"source is '{patch['source']}' — an edit run takes source 'edit'")
    if patch.get("base_revision"):
        raise StageError("EDIT_PATCH_BAD", "base_revision is only for patches inside a run (it holds texture paths, so every run has its own) — leave it out")
    return patch


def check_patch(spec: dict, patch: dict) -> dict:
    """patch 를 사본에 적용하고 수정 run 의 규칙을 본다 → {"spec": 고친 spec, "targets", "affects", "allow_overlap"}. 어기면 StageError."""
    targets = []
    for i, op in enumerate(patch["ops"]):
        if op["op"] not in OPS:
            raise StageError("EDIT_OP_REFUSED", f"op {i}: '{op['op']}' is not accepted in an edit run (textures are cut from the concept — a full run makes new ones)")
        wid = op["widget"]["id"] if op["op"] == "add_widget" else op["widget"]
        if wid == spec["root"]:
            raise StageError("EDIT_OP_REFUSED", f"op {i}: the root '{wid}' cannot be a target — everything on the screen is below it, nothing could be compared")
        if op["op"] == "set" and op["path"].split(".")[0] in ("binding", "bbox_intent"):
            raise StageError("EDIT_OP_REFUSED", f"op {i}: '{wid}.{op['path']}' — bindings come from the inputs (full run), bbox_intent is measured by the run")
        if op["op"] == "add_widget" and op["widget"].get("binding"):
            raise StageError("EDIT_OP_REFUSED", f"op {i}: '{wid}' has a binding — bound widgets come from the inputs (full run)")
        targets.append(wid)
    try:
        out = patch_mod.apply_patch(spec, patch)
    except patch_mod.PatchError as exc:
        raise StageError("EDIT_PATCH_BAD", str(exc), **exc.details) from exc
    if cppgen.binding_entries(out) != cppgen.binding_entries(spec):
        raise StageError("EDIT_CONTRACT_CHANGED", "the patch changes the binding contract — run the full pipeline from the inputs")
    known = set(spec_mod.widget_index(spec)) | set(spec_mod.widget_index(out))
    affects, pairs = list(patch.get("affects") or []), [list(p) for p in patch.get("allow_overlap") or []]
    unknown = sorted((set(affects) | {w for p in pairs for w in p}) - known)
    if unknown:
        raise StageError("EDIT_PATCH_BAD", f"affects / allow_overlap name unknown widget(s) {unknown}")
    root = spec["root"]
    if root in affects:
        raise StageError("EDIT_PATCH_BAD", f"affects cannot hold the root '{root}' — that would allow everything to change")
    if pairs:
        have = {frozenset(p) for p in out.get("allow_overlap", [])}
        out["allow_overlap"] = list(out.get("allow_overlap", [])) + [p for p in pairs if frozenset(p) not in have]
    if spec_mod.roundtrip_view(spec) == spec_mod.roundtrip_view(out):
        raise StageError("NO_EFFECT", "the patch leaves the widget blueprint exactly as it is (same values)")
    return {"spec": out, "targets": sorted(set(targets)), "affects": sorted(set(affects)), "allow_overlap": pairs}


def _line_of(path: pathlib.Path, needle: str) -> int | None:
    try:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if needle in line and not line.lstrip().startswith("#"):
                return n
    except OSError:
        return None
    return None


def source_notes(run, spec: dict, targets) -> list[dict]:
    """글꼴 · 글자의 단일 원천(참고판 배치 yaml · inputs.yaml)이 이 수정으로 낡은 곳 — 자동으로 고치지 않는다(그림까지 다시 그려야 한다)."""
    from stages import analyze
    brief = run.read_json("brief.json")
    norm = run.read_json("normalize.json") if run.path("normalize.json").is_file() else {}
    inputs = config.recorded_path(norm["inputs"]) if norm.get("inputs") else None
    layout = None
    if inputs is not None:
        ref = inputs.parent / "concept_text_ref.json"
        try:
            layout = json.loads(ref.read_text(encoding="utf-8")).get("layout_file")
        except (OSError, ValueError):
            layout = None

    def where(path, wid):
        if path is None:
            return {"file": None, "line": None}
        p = config.repo_path(path)
        try:
            rel = p.resolve().relative_to(config.REPO_ROOT.resolve()).as_posix()
        except ValueError:
            rel = p.as_posix()
        return {"file": rel, "line": _line_of(p, f"widget: {wid},") or _line_of(p, f"widget: {wid}")}

    index = spec_mod.widget_index(spec)
    notes = []

    def add(wid, path, was, now, src):
        if now is not None and spec_mod._canon(was, path.rsplit(".", 1)[-1]) != spec_mod._canon(now, path.rsplit(".", 1)[-1]):   # noqa: SLF001
            notes.append({"widget": wid, "path": path, "source_value": was, "edited_value": now, **where(src, wid)})

    for wid, font in analyze.declared_fonts(brief).items():
        if wid in targets and wid in index:
            for k in ("size", "weight", "color"):
                if k in font:
                    add(wid, f"font.{k}", font[k], (index[wid].get("font") or {}).get(k), layout)
    for wid, outline in analyze.requested_outlines(brief).items():
        if wid in targets and wid in index:
            add(wid, "font.outline", outline, (index[wid].get("font") or {}).get("outline") or {}, inputs)
    for s in brief.get("static_text", []):
        if s["widget"] in targets and s["widget"] in index:
            add(s["widget"], "text.value", s.get("value"), (index[s["widget"]].get("text") or {}).get("value"), inputs)
    return notes


def seed(run, opts) -> str:
    src = _resolve(run, opts)
    screen = screen_of(opts.source)
    rels = promo.source_files(src["dir"])
    for rel in rels:
        dst = run.path("parent", rel) if rel in PARENT_ONLY else run.path(rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src["dir"] / rel, dst)
    spec, brief, manifest = run.read_json("spec.json"), run.read_json("brief.json"), run.read_json("manifest.json")
    if brief["screen_id"] != screen:
        raise StageError("SOURCE_INCOMPLETE", f"the source brief is for '{brief['screen_id']}', not '{screen}'")
    for a in manifest["assets"]:
        p = run.path(a["file"])
        if not p.is_file() or promo.sha256_file(p) != a["sha256"]:
            raise StageError("SOURCE_CORRUPT", f"{a['file']} is {'missing' if not p.is_file() else 'not the texture the manifest recorded'}", asset=a["asset_id"])
        a["ue_path"] = None
    manifest["run_id"] = run.run_id
    run.write_json("manifest.json", manifest)
    if brief.get("cells"):                              # 놓인 칸 — 이 run 이 검증하는 것은 지금 승격된 칸이다(크기가 달라졌으면 화면을 다시 만들어야 한다)
        for c in brief["cells"]:
            try:
                now = cellref.by_screen(c["cell"], getattr(opts, "promoted_root", None))
            except cellref.CellError as exc:
                raise StageError(exc.code, str(exc).split(": ", 1)[-1], **exc.details) from exc
            if now["size"] != c["size"] or now["class"] != c["class"]:
                raise StageError("CELL_CHANGED", f"the cell '{c['cell']}' is {now['size']} now, the screen was made for {c['size']} — run the full pipeline", cell=c["cell"])
            c["run_id"] = now["run_id"]
        run.write_json("brief.json", brief)
    if not run.path("specs/000.json").is_file():        # 손 spec — 입력 원본이 곧 최종 spec
        run.write_json("specs/000.json", spec)
    patch = _load_patch(opts.edit)
    run.write_json(PATCH_FILE, patch)
    chk = check_patch(spec, patch)
    doc = {"schema_version": 1, "run_id": run.run_id, "screen_id": screen, "parent_run_id": src["run_id"],
           "source": {"kind": src["kind"], "from": opts.source}, "patch": patch, "targets": chk["targets"], "affects": chk["affects"],
           "allow_overlap": chk["allow_overlap"],
           "edits": [*src["edits"], {"run_id": run.run_id, "parent_run_id": src["run_id"], "note": patch.get("note"), "patch": patch}],
           "source_notes": source_notes(run, chk["spec"], chk["targets"]), "base_attempt": BASE_ATTEMPT, "edit_attempt": EDIT_ATTEMPT}
    save_doc(run, doc)
    for n in doc["source_notes"]:
        run.log(f"edit: the font source is now stale — {n['file']}{':' + str(n['line']) if n.get('line') else ''} {n['widget']} {n['path']} "
                f"{n['source_value']} (edited to {n['edited_value']})")
    return (f"{len(rels)} file(s) from {src['kind']} '{opts.source}' (parent {src['run_id']}, {len(src['edits'])} earlier edit(s)) — "
            f"{len(patch['ops'])} op(s) on {', '.join(chk['targets'])}")


# ---------------------------------------------------------------------------------------------------------------------
# 계약 — codegen 이 쓰기 · 빌드까지 가지 않게 그 전에 멈춘다

def contract_guard(run, opts, toolchain=None) -> None:
    from stages import codegen
    cg = run.cfg["codegen"]
    spec, brief = run.read_json("spec.json"), run.read_json("brief.json")
    screen_id = brief["screen_id"]
    screen = config.load_screens().get(screen_id)
    if not isinstance(screen, dict):
        raise StageError("SCREEN_UNKNOWN", f"screens.yaml has no screen '{screen_id}'")
    if screen.get("probe") or cppgen.hand_written(screen):       # C++ 를 만들지 않는 화면 — 손으로 쓴 부모는 codegen 이 리플렉션과 대조한다
        return
    paths = cppgen.target_paths(codegen._module_root(run, opts), cg["ui_dir"], screen)      # noqa: SLF001
    have = {k: cppgen.read_generated(p) for k, p in paths.items()}
    prev = have["view_base_h"]
    try:
        bindings, _ = cppgen.merge(cppgen.binding_entries(spec, codegen._resolver(run, opts, cg)),      # noqa: SLF001
                                   prev["contract"]["bindings"] if prev["owned"] and prev["contract"] else None)
        base = cppgen.screen_base(screen, config.repo_path(cg["module_root"]))
    except cppgen.ContractError as exc:
        raise StageError("EDIT_CONTRACT_CHANGED", f"the contract does not fit the generated C++: {exc}") from exc
    chash = cppgen.contract_hash(cppgen.contract_doc(screen_id, screen, cg, bindings, base))
    if not (all(have[k]["owned"] and have[k]["hash"] == chash for k in codegen.AUTOGEN_KEYS) and all(have[k]["exists"] for k in codegen.STUB_KEYS)):
        raise StageError("EDIT_CONTRACT_CHANGED", f"contract {chash} is not the generated C++ ({prev['hash']}) — an edit run writes and builds no C++; run the full "
                         "pipeline from the inputs", contract=chash, generated=prev["hash"])
    tc = toolchain or ue_toolchain(run)
    try:
        if tc.editor_status() is not None:
            diff = cppgen.contract_diff(bindings, tc.list_bind_widgets(f"/Script/{cg['module']}.{screen['widget']}"))
            if diff:
                raise StageError("EDIT_CONTRACT_CHANGED", "the running editor's class differs from the generated C++ (stale binary — build first): " + "; ".join(diff[:4]),
                                 diff=diff)
    except ToolchainError as exc:
        raise toolchain_error(exc, "edit: ") from exc


# ---------------------------------------------------------------------------------------------------------------------
# 그림 · 상태 목록

def attempt_images(run_dir, attempt: int) -> dict[str, str]:
    """시도 폴더의 그림 — {render_WxH · 상태 이름 · sample: 경로}."""
    adir = pathlib.Path(run_dir) / "attempts" / f"{attempt:03d}"
    out = {p.stem: p.as_posix() for p in sorted((adir / "render").glob("render_*.png"))}
    if not adir.is_dir():
        return out
    for d in sorted(p for p in adir.iterdir() if p.is_dir() and p.name.startswith("state")):
        png = sorted(d.glob("*.png"))
        if png:
            out[d.name.removesuffix("_single")] = png[0].as_posix()
    s = sorted((adir / "sample").glob("*.png"))
    if s:
        out["sample"] = s[0].as_posix()
    return out


class _Replay:
    """기록된 시도의 상태 렌더를 되돌려 주며 진단이 요구하는 상태 목록만 받는다(오프라인)."""

    def __init__(self, adir):
        self.adir, self.requests = pathlib.Path(adir), None

    def prefetch(self, requests):
        self.requests = requests

    def __call__(self, overrides, name="state"):
        p = sorted((self.adir / name).glob("*.png")) or sorted((self.adir / f"{name}_single").glob("*.png"))
        return p[0].as_posix() if p else None


def recorded_requests(run_dir, attempt: int, cfg: dict) -> dict[str, dict]:
    """그 시도의 진단이 쓴 상태 렌더 목록(이름 → overrides) — 수정 run 은 적어 둔 것, 그 밖은 진단을 되풀이해 얻는다(에디터 없음)."""
    rd = pathlib.Path(run_dir)
    p = rd / "attempts" / f"{attempt:03d}" / "edit_view.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))["requests"]
    if not (rd / "reference.png").is_file():
        return {}
    from gen import diagnose
    rp = _Replay(rd / "attempts" / f"{attempt:03d}")
    diagnose.diagnose(rd, None, cfg, pictures=False, render_state=rp)
    return rp.requests or {}


def render_all(tc, cfg: dict, wbp: str, out: pathlib.Path, canvas, requests: dict, brief: dict, profile: str = "hud") -> dict[str, str]:
    """WBP 하나의 그림 전부 — attempt_images 와 같은 이름(세 해상도 force_visible · 상태 · sample)."""
    from stages import verify
    out = pathlib.Path(out)
    resolutions = verify.render_resolutions(cfg, config.load_profile(profile), canvas)
    r = tc.call("render_widget", {"asset_path": wbp, "output_dir": (out / "render").resolve().as_posix(), "resolutions": resolutions,
                                  "force_visible": True, "prefix": "render"})
    images = {pathlib.Path(x["png"]).stem: x["png"] for x in r["renders"]}
    states = {**requests, "sample": verify.sample_overrides(brief)}
    s = tc.call("render_widget", {"asset_path": wbp, "output_dir": out.resolve().as_posix(), "resolutions": [list(canvas)], "force_visible": False,
                                  "states": [{"name": n, "overrides": ov} for n, ov in states.items()]}, timeout=180.0 + 2.0 * len(states))
    images.update({x["name"]: x["renders"][0]["png"] for x in s["states"]})
    return images


def compare_wbp(tc, cfg: dict, spec: dict, brief: dict, wbp: str, textures: dict[str, str], requests: dict, want: dict[str, str], out) -> dict:
    """저장된 WBP(승격본)가 이 spec · 이 그림들(want)과 같은가 — 역추출 + 렌더 전부. {revision, roundtrip_equal, diffs, unsupported, renders}."""
    ex = tc.call("export_widget_spec", {"asset_path": wbp, "assets": textures})
    ue_to_asset = {v: k for k, v in textures.items()}
    same, diffs = spec_mod.roundtrip_equal(spec, ex.get("spec") or {}, ue_to_asset)
    diffs = diffs + button.style_diff(spec, ex, ue_to_asset)
    same = same and not diffs
    got = render_all(tc, cfg, wbp, out, [int(v) for v in spec["canvas"]], requests, brief, spec["profile"])
    return {"revision": ex.get("revision"), "roundtrip_equal": same, "diffs": diffs[:10], "unsupported": ex.get("unsupported") or [],
            "renders": edit_gate.compare_sets(want, got)}


def drift(run, opts, toolchain=None) -> str:
    """--from <ScreenId> — base 가 지금 승격본과 역추출 · 그림까지 같은가. 다르면 BASE_DRIFT(승격본 · 원천 · 코드 중 하나가 어긋남)."""
    doc = edit_doc(run)
    rec = store_of(run, opts).require(doc["screen_id"])
    view = run.read_json(f"attempts/{BASE_ATTEMPT:03d}/edit_view.json")
    tc = toolchain or ue_toolchain(run)
    try:
        res = compare_wbp(tc, run.cfg, run.read_json("spec.json"), run.read_json("brief.json"), rec["wbp"], rec["textures"], view["requests"],
                          attempt_images(run.dir, BASE_ATTEMPT), run.path("promoted"))
    except ToolchainError as exc:
        raise toolchain_error(exc, "edit: ") from exc
    doc.setdefault("base", {})["promoted"] = res
    save_doc(run, doc)
    r = res["renders"]
    if not res["roundtrip_equal"] or r["different"]:
        raise StageError("BASE_DRIFT", f"the base built from the source bundle is not the promoted screen — roundtrip {'same' if res['roundtrip_equal'] else res['diffs'][:3]}, "
                         f"pictures different {sorted(r['different'])[:6]}")
    return f"base = promoted {rec['wbp']} — roundtrip same, pictures {r['same_pixels']}/{r['n']} same ({r['same_bytes']} to the byte)"


# ---------------------------------------------------------------------------------------------------------------------
# 대상의 새 상자

def apply_edit(run) -> str:
    doc = edit_doc(run)
    chk = check_patch(run.read_json("spec.json"), doc["patch"])
    run.write_json("spec.json", chk["spec"])
    return f"{len(doc['patch']['ops'])} op(s) applied ({PATCH_FILE}) — targets {', '.join(doc['targets'])}"


def _canvas_geometry(run, attempt: int, canvas) -> dict[str, dict]:
    g = edit_gate.by_resolution(run.read_json(f"attempts/{attempt:03d}/geometry.json")["geometry"])
    return g[f"{canvas[0]}x{canvas[1]}"]


def measure_intents(run, spec_file: str, toolchain=None) -> str:
    """지은 뒤 한 해상도를 그려 자리가 달라진 대상(자손 · affects)의 bbox_intent 를 새 실측 상자로 — iou 게이트가 옮긴 것을 결함으로 보지 않게(WBP 에 안 들어가는 값)."""
    doc, spec = edit_doc(run), run.read_json("spec.json")
    base_spec = run.read_json(f"specs/{BASE_ATTEMPT:03d}.json")
    canvas = [int(v) for v in spec["canvas"]]
    tc = toolchain or ue_toolchain(run)
    wbp = run.read_json("build.json")["wbp"]["asset_path"]
    try:
        r = tc.call("render_widget", {"asset_path": wbp, "output_dir": run.path("attempts", f"{EDIT_ATTEMPT:03d}", "intent").resolve().as_posix(),
                                      "resolutions": [canvas], "force_visible": True, "prefix": "intent"})
    except ToolchainError as exc:
        raise toolchain_error(exc, "edit: ") from exc
    now = geo.by_id(r["renders"][0]["geometry"])
    was = _canvas_geometry(run, BASE_ATTEMPT, canvas)
    ids = _scope(doc, base_spec, spec)
    moved = []
    for w in spec["widgets"]:
        wid = w["id"]
        g, b = now.get(wid), was.get(wid)
        if wid not in ids or not w.get("bbox_intent") or not geo.painted(g):
            continue
        if b is not None and max(abs(float(g[k]) - float(b[k])) for k in ("x", "y", "w", "h")) <= edit_gate.GEO_EPS:
            continue
        box = [geo.r3(v) for v in geo.box(g)]
        moved.append({"widget": wid, "was": w["bbox_intent"], "now": box})
        w["bbox_intent"] = box
    doc["bbox_intent"] = moved
    save_doc(run, doc)
    if moved:
        run.write_json("spec.json", spec)
        run.write_json(spec_file, spec)
    return f"{len(moved)} target box(es) moved: {', '.join(m['widget'] for m in moved)}" if moved else "no target box moved"


def _scope(doc: dict, before: dict, after: dict) -> set[str]:
    return edit_gate.scope(before, after, [*doc["targets"], *doc["affects"]])


# ---------------------------------------------------------------------------------------------------------------------
# verify 가 부르는 곳(edit.json 이 있을 때만)

def after_verify(run, attempt: int, tc, wbp: str, gates: dict, view: dict, artifacts: dict) -> None:
    """view = {"export": 역추출 결과, "requests": 진단이 쓴 상태 목록, "diagnosis": 진단 기록}. 시도 1 = 기록, 시도 2 = 12번째 게이트 + 외형 나누기."""
    doc = edit_doc(run)
    export = view.get("export") or {}
    run.write_json(f"attempts/{attempt:03d}/edit_view.json", {"schema_version": 1, "attempt": attempt, "requests": view.get("requests") or {},
                                                              "export": {"spec": export.get("spec"), "textures": export.get("textures") or [],
                                                                         "revision": export.get("revision")}})
    if attempt == doc["base_attempt"]:
        diag = view.get("diagnosis") or {}
        doc["base"] = {"attempt": attempt, "failed": [n for n, g in gates.items() if not g["pass"]], "errors": len(diag.get("defects") or []),
                       "states": len(view.get("requests") or {}), "revision": export.get("revision")}
        save_doc(run, doc)
        return
    if attempt != doc["edit_attempt"]:
        return
    try:
        reg, zone, rows, imgs = _regression(run, doc, tc, wbp, view)
    except Exception as exc:  # noqa: BLE001 — 게이트가 깨지면 실패로 남긴다(통과로 넘기지 않음)
        gates[edit_gate.GATE] = {"name": edit_gate.GATE, "pass": False, "details": {"error": f"{type(exc).__name__}: {exc}"[:400]}}
        doc["regression"] = gates[edit_gate.GATE]["details"]
        save_doc(run, doc)
        return
    gates[edit_gate.GATE] = reg
    doc["regression"] = {"pass": reg["pass"], **{k: v for k, v in reg["details"].items() if k != "scope"}}
    ag = gates.get("appearance")
    if ag and not ag.get("skipped") and view.get("diagnosis"):
        bd = f"attempts/{BASE_ATTEMPT:03d}/diagnosis/diagnosis.json"
        base_diag = run.read_json(bd) if run.path(bd).is_file() else {}       # 없으면 이어받은 것이 없다고 본다(더 엄하게)
        split = edit_gate.split_defects(base_diag.get("defects") or [], view["diagnosis"].get("defects") or [], zone,
                                        set(reg["details"]["scope"]))
        gates["appearance"] = edit_gate.appearance(ag, split)
        doc["appearance"] = split
    doc["picture"] = _picture(run, rows, imgs, zone)
    if doc["picture"]:
        artifacts["edit"] = "edit.png"
    save_doc(run, doc)


def _same_requests(base_req: dict, edit_req: dict, name: str) -> bool:
    return name in edit_req and edit_req[name] == base_req[name]


def _regression(run, doc: dict, tc, wbp: str, view: dict) -> tuple:
    """→ (게이트, 자리(기준 해상도 — 상자 ∪ 발자국), 그림마다 {px, outside …}, (base 그림, 고친 뒤 그림))."""
    before, after = run.read_json(f"specs/{BASE_ATTEMPT:03d}.json"), run.read_json("spec.json")
    canvas = [int(v) for v in after["canvas"]]
    base_view = run.read_json(f"attempts/{BASE_ATTEMPT:03d}/edit_view.json")
    manifest, state = run.read_json("manifest.json"), run.read_json("build.json")
    ids = _scope(doc, before, after)
    ue_to_asset = {a["ue_path"]: a["asset_id"] for a in manifest["assets"] if a.get("ue_path")}
    sizes = {a["asset_id"]: list(a["size"]) for a in after.get("assets", []) if "size" in a}
    touched = (state["attempts"][-1].get("apply") or {}).get("changed_widgets") or []
    spec_res = edit_gate.spec_changes(base_view["export"], view.get("export") or {}, ids, ue_to_asset, sizes, touched)
    gb = edit_gate.by_resolution(run.read_json(f"attempts/{BASE_ATTEMPT:03d}/geometry.json")["geometry"])
    ga = edit_gate.by_resolution(run.read_json(f"attempts/{EDIT_ATTEMPT:03d}/geometry.json")["geometry"])
    geo_res = edit_gate.geometry_changes(gb, ga, ids)

    # 그림 — base 의 상태 목록으로 앞 · 뒤를 같은 overrides 로 그린 것끼리(수정 탓에 진단의 목록이 달라졌으면 그 상태만 base 목록으로 다시 그린다)
    base_req, edit_req = base_view["requests"], view.get("requests") or {}
    imgs_b, imgs_a = attempt_images(run.dir, BASE_ATTEMPT), attempt_images(run.dir, EDIT_ATTEMPT)
    have = {w["id"] for w in after["widgets"]}
    again = {n: {w: o for w, o in ov.items() if w in have} for n, ov in base_req.items() if not _same_requests(base_req, edit_req, n) or n not in imgs_a}
    adir = run.path("attempts", f"{EDIT_ATTEMPT:03d}")
    if again:
        s = tc.call("render_widget", {"asset_path": wbp, "output_dir": (adir / "base_states").resolve().as_posix(), "resolutions": [canvas], "force_visible": False,
                                      "states": [{"name": n, "overrides": ov} for n, ov in again.items()]}, timeout=180.0 + 2.0 * len(again))
        imgs_a.update({x["name"]: x["renders"][0]["png"] for x in s["states"]})
    pad = edit_gate.pads(before, after, ids)
    zones: dict[tuple, object] = {}

    def zone_for(name, shape):
        key = name.removeprefix("render_") if name.startswith("render_") else f"{canvas[0]}x{canvas[1]}"
        if (key, shape) not in zones:
            zones[(key, shape)] = edit_gate.zone_mask(shape, [gb.get(key, {}), ga.get(key, {})], ids, pad)
        return zones[(key, shape)]

    rows: dict[str, dict] = {}
    missing = sorted(set(imgs_b) - set(imgs_a))
    for name, p in imgs_b.items():
        q = imgs_a.get(name)
        if q is None:
            continue
        if edit_gate.same_file(p, q):
            rows[name] = {"px": 0, "outside": 0}
            continue
        a, b = edit_gate.load(p), edit_gate.load(q)
        rows[name] = edit_gate.image_row(a, b, zone_for(name, a.shape[:2]))
    notes: dict = {}
    left = [n for n, r in rows.items() if r["outside"]]
    if left:
        notes["footprint"] = _footprints(run, doc, tc, wbp, left, imgs_b, imgs_a, rows, zone_for, before, after, base_req, gb, ga, ids, canvas)
    if missing:
        notes["missing_pictures"] = missing
        spec_res["diffs"].append(f"pictures missing after the edit: {missing[:5]}")
    new_states = sorted(set(edit_req) - set(base_req))
    if new_states:
        notes["new_states"] = new_states
    if again:
        notes["states_drawn_again"] = sorted(again)
    zone = zone_for("state", (canvas[1], canvas[0]))
    fp = (notes.get("footprint") or {}).pop("_mask", None)
    reg = edit_gate.regression_gate(spec_res, geo_res, rows, ids, notes)
    return reg, (zone | fp if fp is not None else zone), rows, (imgs_b, imgs_a)


def _footprints(run, doc, tc, wbp, names, imgs_b, imgs_a, rows, zone_for, before, after, base_req, gb, ga, ids, canvas) -> dict:
    """대상을 끈 렌더를 앞 · 뒤로 더 그려 '대상이 실제로 그린 픽셀'로 다시 잰다 — 상자 밖으로 넘친 글자는 여기서 풀린다.
    대상을 끄면 다른 위젯이 움직이는 배치(박스 부모 등)면 발자국에 형제가 들어가므로 쓰지 않고 상자 기준 그대로 둔다."""
    import numpy as np

    from stages import verify
    roots = [*doc["targets"], *doc["affects"]]
    brief = run.read_json("brief.json")
    adir = run.path("attempts", f"{EDIT_ATTEMPT:03d}")
    res_names = [n for n in names if n.startswith("render_")]
    state_names = [n for n in names if not n.startswith("render_")]
    resolutions = [[int(v) for v in n.removeprefix("render_").split("x")] for n in res_names] or [list(canvas)]

    def draw(spec, label):
        have = {w["id"] for w in spec["widgets"]}
        off = {i: {"visible": False} for i in roots if i in have}
        out, geometry = {}, {}
        r = tc.call("render_widget", {"asset_path": wbp, "output_dir": (adir / f"off_{label}" / "render").resolve().as_posix(), "resolutions": resolutions,
                                      "force_visible": True, "overrides": off, "prefix": "render"})
        for x in r["renders"]:
            key = f"{x['resolution'][0]}x{x['resolution'][1]}"
            out[f"render_{key}"] = x["png"]
            geometry[key] = geo.by_id(x["geometry"])
        if state_names:
            ovs = {n: (verify.sample_overrides(brief) if n == "sample" else base_req[n]) for n in state_names}
            s = tc.call("render_widget", {"asset_path": wbp, "output_dir": (adir / f"off_{label}").resolve().as_posix(), "resolutions": [canvas], "force_visible": False,
                                          "states": [{"name": n, "overrides": {**{w: o for w, o in ov.items() if w in have},
                                                                               **{i: {**(ov.get(i) or {}), "visible": False} for i in off}}} for n, ov in ovs.items()]},
                        timeout=180.0 + 2.0 * len(ovs))
            out.update({x["name"]: x["renders"][0]["png"] for x in s["states"]})
        return out, geometry

    off_a, geo_off_a = draw(after, "edit")
    off_b, geo_off_b = _with_spec(run, tc, wbp, before, after, lambda: draw(before, "base"))
    moved = {}
    for label, on, off in (("base", gb, geo_off_b), ("edit", ga, geo_off_a)):
        ch = edit_gate.geometry_changes({k: on.get(k, {}) for k in off}, off, ids)["outside"]
        if ch:
            moved[label] = sorted(ch)
    rec: dict = {"pictures": sorted(names), "used": not moved}
    if moved:
        rec["reason"] = f"turning the targets off moves other widgets {moved} — only the target boxes count"
        return rec
    canvas_mask = np.zeros((canvas[1], canvas[0]), bool)
    for n in names:
        if n not in off_a or n not in off_b:
            continue
        a, b = edit_gate.load(imgs_b[n]), edit_gate.load(imgs_a[n])
        fp = edit_gate.diff_mask(a, edit_gate.load(off_b[n])) | edit_gate.diff_mask(b, edit_gate.load(off_a[n]))
        row = edit_gate.image_row(a, b, zone_for(n, a.shape[:2]), fp)
        rows[n] = {**row, "footprint": True, "outside_boxes": rows[n]["outside"]}
        if fp.shape == canvas_mask.shape:
            canvas_mask |= fp & edit_gate.diff_mask(a, b)
    rec["_mask"] = canvas_mask
    return rec


def _with_spec(run, tc, wbp: str, spec: dict, back: dict, fn):
    """WBP 를 잠깐 spec 으로 되돌려 fn 을 부르고 back 으로 다시 — revision 이 앞과 같아야 한다(아니면 실패)."""
    state, manifest = run.read_json("build.json"), run.read_json("manifest.json")
    assets = {a["asset_id"]: a["ue_path"] for a in manifest["assets"]}

    def apply(sp, rev):
        from stages import build
        return tc.call("apply_widget_spec", {"asset_path": wbp, "spec": build.editor_target(sp, state), "assets": assets,
                                             "expected_revision": rev})["revision_after"]

    rev = apply(spec, state["revision"])
    try:
        out = fn()
    finally:
        end = apply(back, rev)
    if end != state["revision"]:
        raise StageError("EDIT_RESTORE_FAILED", f"applying the edit again gave revision {end}, it was {state['revision']}")
    return out


def _picture(run, rows: dict, imgs: tuple, zone) -> dict | None:
    """edit.png — 사람 눈(바꾼 자리 안의 모양은 기계가 판정하지 않는다)."""
    imgs_b, imgs_a = imgs
    try:
        canvas = run.read_json("spec.json")["canvas"]
        names = [n for n in (f"render_{int(canvas[0])}x{int(canvas[1])}", *VIEWS) if n in rows and n in imgs_a]
        rest = sorted((n for n, r in rows.items() if r.get("px") and n not in names and not n.startswith("render_")), key=lambda n: -rows[n]["px"])
        names = [n for n in names if rows[n].get("px")][:4] + rest[:1]
        views = [{"name": n, "before": edit_gate.load(imgs_b[n]), "after": edit_gate.load(imgs_a[n])} for n in names]
        return edit_gate.picture(run.path("edit.png"), views, zone)
    except Exception as exc:  # noqa: BLE001 — 그림 실패는 기록만
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}


def summary(run) -> dict | None:
    """report.recorded.edit."""
    doc = edit_doc(run)
    if doc is None:
        return None
    reg, app = doc.get("regression") or {}, doc.get("appearance") or {}
    return {"parent_run_id": doc["parent_run_id"], "from": doc["source"], "targets": doc["targets"], "affects": doc["affects"], "note": doc["patch"].get("note"),
            "ops": len(doc["patch"]["ops"]), "edits": len(doc["edits"]), "source_notes": doc.get("source_notes") or [], "base": doc.get("base"),
            "bbox_intent": doc.get("bbox_intent") or [], "problems": reg.get("problems"), "pixels": reg.get("pixels"),
            "appearance": {k: len(v) for k, v in app.items()} if app else None, "picture": doc.get("picture")}
