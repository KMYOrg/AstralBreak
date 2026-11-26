"""놓인 칸의 정체 — 승격 기록 · screens.yaml 이 단일 원천이다 (설계 §11 'Phase 3 설계' ②, Phase 3-3).

화면은 칸을 ScreenId 로만 부른다(inputs cells[].cell). WBP 경로 · 크기 · 버튼인가 · C++ 부모 클래스와 그 헤더는 전부 여기서 얻는다 — 같은 값을 화면마다 적지 않는다:
  WBP · 승격한 run   promoted/<ScreenId>/promotion.json
  크기 · 버튼인가     promoted/<ScreenId>/source/spec.json (canvas · 최상위 button)
  C++ 부모 클래스     screens.yaml(손으로 쓴 parent 또는 스텁 widget) — 승격한 run 의 codegen.json 이 본 클래스와 같아야 한다
  헤더                생성 화면 = <ui_dir>/<feature>/<widget>.h, 손으로 쓴 클래스 = 모듈 안의 <클래스>.h 하나(UHT 는 모듈 안에서 헤더 이름이 겹치지 않게 한다)
"""
from __future__ import annotations

import json
import pathlib

from core import config

PROMOTED = config.UIGEN_DIR / "promoted"


class CellError(ValueError):
    def __init__(self, code: str, message: str, **details):
        self.code = code
        self.details = details
        super().__init__(f"{code}: {message}")


def package_of(class_path: str) -> str:
    return str(class_path or "").split(".", 1)[0]


def index(root: pathlib.Path | None = None) -> dict[str, dict]:
    """승격된 화면 — WBP 패키지 경로 → {screen_id, run_id, source}."""
    out = {}
    for p in sorted(pathlib.Path(root or PROMOTED).glob("*/promotion.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        out[package_of(rec["wbp"])] = {"screen_id": rec["screen_id"], "run_id": rec.get("run_id"), "source": p.parent / "source"}
    return out


def _source_spec(rec: dict) -> dict:
    return json.loads((rec["source"] / "spec.json").read_text(encoding="utf-8"))


def by_screen(screen_id: str, root: pathlib.Path | None = None) -> dict:
    """칸 하나 — {screen_id, class(WBP 패키지), run_id, size, button, profile}. 승격돼 있지 않으면 CellError."""
    for pkg, rec in index(root).items():
        if rec["screen_id"] == screen_id:
            spec = _source_spec(rec)
            return {"screen_id": screen_id, "class": pkg, "run_id": rec["run_id"], "size": [int(v) for v in spec["canvas"]], "button": bool(spec.get("button")),
                    "profile": spec.get("profile")}
    raise CellError("CELL_NOT_PROMOTED", f"cell '{screen_id}' has no promotion record — run and promote the cell first (promote_screen.py record)", cell=screen_id)


def is_button(class_path: str, root: pathlib.Path | None = None) -> bool:
    rec = index(root).get(package_of(class_path))
    return bool(rec) and bool(_source_spec(rec).get("button"))


def header_of(class_name: str, module_root: pathlib.Path) -> str:
    """모듈 안의 <클래스>.h 하나 → include 경로(모듈 루트 기준)."""
    root = pathlib.Path(module_root)
    hits = sorted(p.relative_to(root).as_posix() for p in root.rglob(f"{class_name}.h")) if root.is_dir() else []
    if len(hits) != 1:
        raise CellError("CLASS_HEADER", f"{class_name}.h: {len(hits)} file(s) under {root.as_posix()} — the include path of U{class_name} must be exactly one header",
                        found=hits)
    return hits[0]


def cpp_class(class_path: str, screens: dict, cg: dict, module_root: pathlib.Path, root: pathlib.Path | None = None) -> dict:
    """놓인 칸 WBP → {cell, widget_class(U 없이), include, button}. screens.yaml 과 승격한 run 이 다르면 CellError."""
    from core import cppgen
    pkg = package_of(class_path)
    rec = index(root).get(pkg)
    if rec is None:
        raise CellError("CELL_NOT_PROMOTED", f"{pkg} has no promotion record", cell=pkg)
    screen = screens.get(rec["screen_id"])
    if not isinstance(screen, dict) or screen.get("probe"):
        raise CellError("SCREEN_UNKNOWN", f"screens.yaml has no screen '{rec['screen_id']}' for the cell {pkg}", cell=pkg)
    cls = cppgen.parent_class(screen)
    cgp = rec["source"] / "codegen.json"
    if cgp.is_file():
        built = json.loads(cgp.read_text(encoding="utf-8")).get("class")
        if built != f"/Script/{cg['module']}.{cls}":
            raise CellError("CELL_CLASS_CHANGED", f"{pkg} was promoted with parent {built}, screens.yaml says {cls}", cell=pkg, was=built, now=cls)
    include = header_of(cls, module_root) if cppgen.hand_written(screen) else f"{cg['ui_dir']}/{screen['feature']}/{screen['widget']}.h"
    return {"cell": rec["screen_id"], "widget_class": cls, "include": include, "button": bool(_source_spec(rec).get("button"))}


def changed(cells: list[dict] | None, root: pathlib.Path | None = None) -> list[dict]:
    """brief.cells · 승격 기록 cells 중 칸이 그 뒤 다시 승격된 것 — [{cell, was, now}]."""
    out: dict[str, dict] = {}
    runs = {rec["screen_id"]: rec["run_id"] for rec in index(root).values()}
    for c in cells or []:
        if runs.get(c["cell"]) != c["run_id"]:
            out[c["cell"]] = {"cell": c["cell"], "was": c["run_id"], "now": runs.get(c["cell"])}
    return [out[k] for k in sorted(out)]


def users_of(screen_id: str, root: pathlib.Path | None = None) -> list[dict]:
    """이 칸을 쓰는 승격된 화면 — [{screen_id, run_id, widgets, cell_run_id}] (그 화면의 승격 기록 cells 에서)."""
    out = []
    for p in sorted(pathlib.Path(root or PROMOTED).glob("*/promotion.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        for c in rec.get("cells") or []:
            if c.get("cell") == screen_id:
                out.append({"screen_id": rec["screen_id"], "run_id": rec["run_id"], "widgets": c["widgets"], "cell_run_id": c.get("run_id")})
    return out
