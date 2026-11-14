"""가짜 에디터(WidgetMcp Tool 11개 중 파이프라인이 쓰는 것) — build · verify · finalize 를 에디터 없이 돈다.

- 패키지: 메모리 dict(경로 → 텍스처 · WBP). 저장하면 saved 로 표시. quit(세션 끝)이면 저장 안 한 것은 사라진다.
- WBP 트리: apply 가 받은 정규화 spec 그대로(조정기가 목표와 같게 만든다 — 실제 도구의 계약). export 는 그 spec 을 돌려준다.
- 렌더 geometry: 아래 작은 배치 계산기(캔버스 점 앵커 · Overlay/Border/SizeBox 패딩 · 박스 fill 비율). 손 spec 의 bbox_intent 와 같은 값을 낸다.
  실제 Slate 처럼 그리기 영역 밖으로 완전히 나간 위젯(과 자식)은 컬링 — geometry (0, 0, 0, 0).
- 결함 손잡이: texture_override(임포트 설정 바꾸기) · drop_from_export(역추출에서 위젯 빼기) · compile_errors.
"""
from __future__ import annotations

import copy
import hashlib
import json
import pathlib

from core import png
from core import spec as spec_mod

DESIRED = (40.0, 20.0)   # 채움이 아닌 정렬의 원하는 크기(가짜)
TEXT_LINE = 1.6          # TextBlock 줄 높이 / 글꼴 크기 — 엔진 기본 글꼴(Roboto + 한글 대체) 1a-4 실측 16→26 · 18→29 · 26→42 · 30→48


def desired(w: dict) -> tuple[float, float]:
    if w["type"] == "TextBlock":
        return DESIRED[0], float(round(w["font"]["size"] * TEXT_LINE))
    return DESIRED


class FakeBridgeError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _rev(obj) -> str:
    return "sha1:" + hashlib.sha1(json.dumps(obj, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------------------------------------------------------------
# 배치 계산기

def layout(spec: dict, W: float, H: float) -> dict[str, tuple[float, float, float, float]]:
    norm = spec_mod.normalize(spec)
    index = spec_mod.widget_index(norm)
    kids = spec_mod.children_map(norm)
    out: dict[str, tuple] = {norm["root"]: (0.0, 0.0, float(W), float(H))}

    def place_aligned(px, pw, pad_a, pad_b, align, want):
        inner = pw - pad_a - pad_b
        if align == "fill":
            return px + pad_a, inner
        want = min(want, inner)   # 칸보다 크면 칸 크기(실측 — 34 크기 글자가 50 칸에서 50)
        if align in ("center",):
            return px + pad_a + (inner - want) / 2, want
        if align in ("right", "bottom"):
            return px + pw - pad_b - want, want
        return px + pad_a, want

    def walk(wid):
        x, y, w, h = out[wid]
        ptype = index[wid]["type"]
        children = kids.get(wid, [])
        if ptype == "CanvasPanel":
            for c in children:
                s = index[c]["slot"]
                a, al, pos, size = s["anchors"], s["alignment"], s["position"], s["size"]
                if a[0] == a[2]:
                    cx, cw = x + a[0] * w + pos[0] - al[0] * size[0], size[0]
                else:
                    cx, cw = x + a[0] * w + pos[0], (x + a[2] * w - size[0]) - (x + a[0] * w + pos[0])
                if a[1] == a[3]:
                    cy, ch = y + a[1] * h + pos[1] - al[1] * size[1], size[1]
                else:
                    cy, ch = y + a[1] * h + pos[1], (y + a[3] * h - size[1]) - (y + a[1] * h + pos[1])
                out[c] = (cx, cy, cw, ch)
        elif ptype in ("VerticalBox", "HorizontalBox"):
            vertical = ptype == "VerticalBox"
            main = h if vertical else w
            pads = [index[c]["slot"]["padding"] for c in children]
            used = sum((p[1] + p[3]) if vertical else (p[0] + p[2]) for p in pads)
            autos = [c for c in children if index[c]["slot"]["size_rule"] == "auto"]
            used += len(autos) * (DESIRED[1] if vertical else DESIRED[0])
            fills = sum(index[c]["slot"]["fill"] for c in children if index[c]["slot"]["size_rule"] == "fill") or 1
            cur = y if vertical else x
            for c, p in zip(children, pads):
                s = index[c]["slot"]
                ext = (DESIRED[1] if vertical else DESIRED[0]) if s["size_rule"] == "auto" else (main - used) * s["fill"] / fills
                dw, dh = desired(index[c])
                if vertical:   # 칸 = 주축 ext, 교차축 정렬 · 주축 안 정렬(v_align)
                    cx, cw = place_aligned(x, w, p[0], p[2], s["h_align"], dw)
                    cy, ch = place_aligned(cur, p[1] + ext + p[3], p[1], p[3], s["v_align"], dh)
                    out[c] = (cx, cy, cw, ch)
                    cur += p[1] + ext + p[3]
                else:
                    cy, ch = place_aligned(y, h, p[1], p[3], s["v_align"], dh)
                    cx, cw = place_aligned(cur, p[0] + ext + p[2], p[0], p[2], s["h_align"], dw)
                    out[c] = (cx, cy, cw, ch)
                    cur += p[0] + ext + p[2]
        elif ptype in ("Overlay", "Border", "SizeBox", "Button", "UniformGridPanel"):
            for c in children:
                s = index[c]["slot"]
                p = s.get("padding", [0, 0, 0, 0])
                dw, dh = desired(index[c])
                cx, cw = place_aligned(x, w, p[0], p[2], s.get("h_align", "fill"), dw)
                cy, ch = place_aligned(y, h, p[1], p[3], s.get("v_align", "fill"), dh)
                out[c] = (cx, cy, cw, ch)
        for c in children:
            walk(c)

    walk(norm["root"])
    return out


def painted_layout(spec: dict, W: float, H: float) -> dict[str, tuple[float, float, float, float]]:
    """layout + 실제 Slate 의 컬링 — 그리기 영역 밖으로 완전히 나간 위젯과 그 자식은 그리지 않아 geometry 가 (0, 0, 0, 0) [실측 1a-4]."""
    boxes = layout(spec, W, H)
    kids = spec_mod.children_map(spec)

    def walk(wid, culled):
        b = boxes[wid]
        inter = max(0.0, min(b[0] + b[2], W) - max(b[0], 0.0)) * max(0.0, min(b[1] + b[3], H) - max(b[1], 0.0))
        culled = culled or (b[2] > 0 and b[3] > 0 and inter == 0)
        if culled:
            boxes[wid] = (0, 0, 0, 0)
        for c in kids.get(wid, []):
            walk(c, culled)

    walk(spec["root"], False)
    return boxes


# ---------------------------------------------------------------------------------------------------------------------

class FakeEditor:
    def __init__(self, toolchain):
        self.tc = toolchain                 # binary(바인딩 계약) 은 FakeToolchain 이 가진다
        self.packages: dict[str, dict] = {}
        self.texture_override: dict[str, dict] = {}   # 텍스처 이름 → 덮어쓸 설정(결함 시험)
        self.drop_from_export: set[str] = set()
        self.compile_errors = 0
        self.log: list[tuple[str, dict]] = []

    def end_session(self) -> None:
        self.packages = {k: v for k, v in self.packages.items() if v.get("saved")}

    def call(self, tool: str, params: dict) -> dict:
        self.log.append((tool, copy.deepcopy(params)))
        fn = getattr(self, f"t_{tool}", None)
        if fn is None:
            raise FakeBridgeError("UNKNOWN_TOOL", tool)
        return fn(params)

    # -- 도구 ----------------------------------------------------------------------------------------------------------

    def t_import_ui_textures(self, p):
        out = []
        for t in p["textures"]:
            pkg = f"{p['dest_path']}/{t['name']}"
            if pkg in self.packages:
                raise FakeBridgeError("OVERWRITE_NOT_ALLOWED", f"'{pkg}' already exists")
            w, h, _ = png.read_rgba(t["file"])
            settings = {"compression": t.get("compression", "TC_EditorIcon"), "lod_group": t.get("lod_group", "TEXTUREGROUP_UI"),
                        "mip_gen": t.get("mip_gen", "TMGS_NoMipmaps"), "never_stream": t.get("never_stream", True), "srgb": t.get("srgb", True)}
            settings.update(self.texture_override.get(t["name"], {}))
            self.packages[pkg] = {"kind": "texture", "size": [w, h], **settings}
            out.append({"asset_path": f"{pkg}.{t['name']}", "name": t["name"], "size": [w, h], **settings, "seconds": 0.001})
        return {"dest_path": p["dest_path"], "textures": out, "saved": False}

    def _bindings(self):
        return [dict(b) for b in self.tc.binary]

    def _wbp(self, path) -> dict:
        w = self.packages.get(path)
        if not w or w["kind"] != "wbp":
            raise FakeBridgeError("ASSET_NOT_FOUND", f"no widget blueprint '{path}'")
        return w

    def _revision(self, w) -> str:
        return _rev({"parent": w["parent"], "spec": w["spec"]})

    def _compile(self, w) -> dict:
        have = {x["id"]: x["type"] for x in w["spec"]["widgets"]}
        missing = []
        for b in self._bindings():
            if b["optional"]:
                continue
            t = have.get(b["name"])
            if t is None or (b.get("widget_class") and t != b["widget_class"]):
                missing.append({"name": b["name"], "reason": "missing" if t is None else "type", "expected": b.get("widget_class"), "actual": t or "",
                                "optional": False})
        errors = len(missing) + self.compile_errors
        return {"ok": errors == 0, "status": "up_to_date" if errors == 0 else "error", "errors": errors, "warnings": 0, "messages": [],
                "missing_bindings": missing, "generated_class": f"{w['path']}_C"}

    def t_create_widget_blueprint(self, p):
        path = p["asset_path"]
        if path in self.packages:
            raise FakeBridgeError("OVERWRITE_NOT_ALLOWED", f"'{path}' already exists")
        root = p.get("root_id") or "Root"
        w = {"kind": "wbp", "path": path, "parent": p.get("parent_class") or "/Script/UMG.UserWidget",
             "spec": {"root": root, "widgets": [{"id": root, "type": "CanvasPanel", "visibility": "self_hit_test_invisible"}], "locked": []},
             "compiled": False}
        self.packages[path] = w
        required = sum(1 for b in self._bindings() if not b["optional"])
        comp = {"ran": False, "reason": f"parent has {required} required BindWidget(s)"} if required else {"ran": True, **self._compile(w)}
        return {"asset_path": f"{path}.{path.rsplit('/', 1)[-1]}", "parent_class": w["parent"], "root": root, "root_type": "CanvasPanel",
                "revision": self._revision(w), "compile": comp, "bindings": self._bindings(), "saved": False}

    def t_apply_widget_spec(self, p):
        w = self._wbp(p["asset_path"])
        before = self._revision(w)
        if p.get("expected_revision") != before:
            raise FakeBridgeError("REVISION_MISMATCH", "the widget blueprint changed since that revision")
        old = {x["id"]: x for x in w["spec"]["widgets"]}
        target = copy.deepcopy(p["spec"])
        ops = []
        for x in target["widgets"]:
            o = old.get(x["id"])
            clean = {k: v for k, v in x.items() if k not in spec_mod.NON_WBP_WIDGET_FIELDS}
            if o is None:
                ops.append({"op": "add", "widget": x["id"]})
            elif {k: v for k, v in o.items() if k not in spec_mod.NON_WBP_WIDGET_FIELDS} != clean:
                ops.append({"op": "set", "widget": x["id"]})
        for wid in old:
            if wid not in {x["id"] for x in target["widgets"]}:
                ops.append({"op": "remove", "widget": wid})
        assets = p.get("assets") or {}
        for x in target["widgets"]:
            x.pop("bbox_intent", None)
            x.pop("binding", None)
            for key, brush in (x.get("style") or {}).items():
                if key in spec_mod.BRUSH_KEYS and isinstance(brush, dict) and brush.get("asset"):
                    if brush["asset"] not in assets:
                        raise FakeBridgeError("ASSET_NOT_FOUND", f"no texture for asset '{brush['asset']}'")
                    brush["asset"] = assets[brush["asset"]]   # WBP 는 UE 경로를 담는다
        w["spec"] = target
        w["compiled"] = True
        return {"asset_path": w["path"], "ops": ops, "missing_bindings": [], "revision_before": before, "revision_after": self._revision(w),
                "applied": len(ops), "verified": True, "compile": self._compile(w), "saved": False}

    def t_compile_widget_blueprint(self, p):
        w = self._wbp(p["asset_path"])
        return {**self._compile(w), "asset_path": w["path"], "revision": self._revision(w)}

    def t_list_bind_widgets(self, p):
        return {"class": p.get("class") or "fake", "bindings": self._bindings()}

    def t_export_widget_spec(self, p):
        w = self._wbp(p["asset_path"])
        rev_map = {v: k for k, v in (p.get("assets") or {}).items()}
        spec = copy.deepcopy(w["spec"])
        spec["widgets"] = [x for x in spec["widgets"] if x["id"] not in self.drop_from_export]
        textures = set()
        for x in spec["widgets"]:
            for key, brush in (x.get("style") or {}).items():
                if key in spec_mod.BRUSH_KEYS and isinstance(brush, dict) and brush.get("asset"):
                    textures.add(brush["asset"])
                    if rev_map:
                        brush["asset"] = rev_map.get(brush["asset"], brush["asset"])
        tex = [{"asset_path": f"{t}.{t.rsplit('/', 1)[-1]}", **{k: v for k, v in self.packages[t].items() if k != "kind"}} for t in sorted(textures)]
        return {"asset_path": w["path"], "parent_class": w["parent"], "spec": {"schema_version": 1, **spec}, "revision": self._revision(w),
                "unsupported": [], "textures": tex, "bindings": self._bindings(), "guid_map_count": len(spec["widgets"]),
                "widget_count": len(spec["widgets"]), "guid_missing": []}

    def t_render_widget(self, p):
        w = self._wbp(p["asset_path"])
        if not w["compiled"] or self._compile(w)["errors"]:
            raise FakeBridgeError("NOT_COMPILED", "not compiled cleanly")
        out_dir = pathlib.Path(p["output_dir"])
        if out_dir.exists() and any(out_dir.iterdir()):
            raise FakeBridgeError("OUTPUT_DIR_NOT_EMPTY", str(out_dir))
        out_dir.mkdir(parents=True, exist_ok=True)
        spec = {"root": w["spec"]["root"], "widgets": copy.deepcopy(w["spec"]["widgets"])}
        types = {x["id"]: x["type"] for x in spec["widgets"]}
        parents = {x["id"]: x.get("parent", "") for x in spec["widgets"]}
        vis = {x["id"]: x.get("visibility", "visible") for x in spec["widgets"]}
        for wid, ov in (p.get("overrides") or {}).items():
            if "visible" in ov:
                vis[wid] = "hit_test_invisible" if ov["visible"] else "collapsed"

        def visible(wid):
            while wid:
                if not p.get("force_visible") and vis.get(wid) in ("collapsed", "hidden"):
                    return False
                wid = parents.get(wid)
            return True

        renders = []
        for res in p.get("resolutions") or [[1920, 1080]]:
            boxes = painted_layout(spec, res[0], res[1])
            f = png.write_rgba(out_dir / f"{p.get('prefix', 'render')}_{res[0]}x{res[1]}.png", 2, 2, bytes([0, 0, 0, 255] * 4))
            geom = [{"id": wid, "type": types[wid], "parent": parents[wid], "x": b[0], "y": b[1], "w": b[2], "h": b[3], "visible": visible(wid)}
                    for wid, b in boxes.items()]
            renders.append({"resolution": list(res), "png": f.as_posix(), "draws": 2, "diff_pixels_vs_prev": [0], "geometry": geom})
        return {"asset_path": w["path"], "output_dir": out_dir.as_posix(), "renders": renders, "probes": [], "scale": 1,
                "force_visible": bool(p.get("force_visible")), "seconds": 0.01}

    def _under(self, run_path):
        prefix = run_path.rstrip("/") + "/"
        return sorted(k for k in self.packages if k.startswith(prefix))

    def t_save_widget_run(self, p):
        saved, already = [], []
        for k in self._under(p["run_path"]):
            (already if self.packages[k].get("saved") else saved).append(k)
            self.packages[k]["saved"] = True
        return {"run_path": p["run_path"], "saved": saved, "already_saved": already}

    def t_discard_run_packages(self, p):
        under = self._under(p["run_path"])
        if any(self.packages[k].get("saved") for k in under):
            raise FakeBridgeError("SAVED_PACKAGES", "some packages are saved on disk")
        for k in under:
            del self.packages[k]
        return {"run_path": p["run_path"], "discarded": under, "still_dirty": []}
