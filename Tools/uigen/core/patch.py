"""spec patch 적용 · 재시도 분기 (설계 §4-4 · §2-2).

적용은 원자적이다 — 사본에 차례로 적용하고, 어느 op 든 실패하거나 결과 spec 이 의미 검사에 걸리면 아무것도 바꾸지 않고 PatchError.
같은 규칙을 브리지(조정기)도 지킨다: locked 위젯은 건드릴 수 없고, 바인딩은 추가만 된다(바인딩 위젯 제거 · 바인딩 지우기 거부).
"""
from __future__ import annotations

import copy

from core import schema
from core import spec as spec_mod

FORBIDDEN_SET_ROOTS = {"id", "type", "parent"}   # type 은 바꾸지 않는다(제거 + 추가), parent 는 move


class PatchError(ValueError):
    def __init__(self, code: str, message: str, index: int | None = None, **details):
        self.code = code
        self.index = index
        self.details = details
        super().__init__(f"{code}{f' (op {index})' if index is not None else ''}: {message}")


def _locked_ids(spec: dict) -> set[str]:
    return set(spec.get("locked", []))


def _check_unlocked(spec: dict, wid: str, i: int) -> None:
    locked = _locked_ids(spec)
    if wid in locked:
        raise PatchError("LOCKED", f"'{wid}' is locked (unsupported by export) — patches cannot change it", i, widget=wid)


def _set_path(target: dict, parts: list[str], value) -> None:
    node = target
    for part in parts[:-1]:
        nxt = node.get(part)
        if nxt is None:
            if value is None:
                return
            nxt = node[part] = {}
        if not isinstance(nxt, dict):
            raise TypeError(part)
        node = nxt
    if value is None:
        node.pop(parts[-1], None)
    else:
        node[parts[-1]] = copy.deepcopy(value)


def _op_set(spec: dict, op: dict, i: int) -> None:
    index = spec_mod.widget_index(spec)
    wid = op["widget"]
    if wid not in index:
        raise PatchError("NOT_FOUND", f"no widget '{wid}'", i, widget=wid)
    _check_unlocked(spec, wid, i)
    parts = op["path"].split(".")
    if parts[0] in FORBIDDEN_SET_ROOTS:
        raise PatchError("BAD_OP", f"'{parts[0]}' cannot be set (use move / remove_widget + add_widget)", i, path=op["path"])
    if parts[:2] == ["slot", "kind"]:
        raise PatchError("BAD_OP", "slot.kind follows the parent type — use move", i, path=op["path"])
    w = index[wid]
    if parts[0] == "binding" and w.get("binding"):
        removing = op["value"] is None and len(parts) == 1
        clearing = len(parts) == 2 and parts[1] in ("data", "kind") and op["value"] is None
        if removing or clearing:
            raise PatchError("BINDING_REMOVAL", f"'{wid}' binding cannot be removed (bindings only grow)", i, widget=wid)
    try:
        _set_path(w, parts, op["value"])
    except TypeError as exc:
        raise PatchError("BAD_OP", f"path '{op['path']}' runs through a non-object at '{exc}'", i, path=op["path"]) from exc


def _insert_at(spec: dict, widget: dict, parent: str, index: int | None) -> None:
    """parent 의 index 번째 자식 자리로 widgets[] 에 넣는다(형제 순서 = 슬롯 순서)."""
    widgets = spec["widgets"]
    siblings = [k for k, w in enumerate(widgets) if w.get("parent") == parent]
    if index is None or index >= len(siblings):
        pos = (siblings[-1] + 1) if siblings else next(k for k, w in enumerate(widgets) if w["id"] == parent) + 1
    else:
        pos = siblings[index]
    widgets.insert(pos, widget)


def _op_add(spec: dict, op: dict, i: int) -> None:
    w = copy.deepcopy(op["widget"])
    index = spec_mod.widget_index(spec)
    if w["id"] in index:
        raise PatchError("DUPLICATE_ID", f"'{w['id']}' already exists", i, widget=w["id"])
    parent = w.get("parent")
    if parent not in index:
        raise PatchError("NOT_FOUND", f"parent '{parent}' does not exist", i, widget=w["id"], parent=parent)
    _check_unlocked(spec, parent, i)
    _insert_at(spec, w, parent, op.get("index"))


def _op_remove(spec: dict, op: dict, i: int) -> None:
    wid = op["widget"]
    index = spec_mod.widget_index(spec)
    if wid not in index:
        raise PatchError("NOT_FOUND", f"no widget '{wid}'", i, widget=wid)
    if wid == spec.get("root"):
        raise PatchError("BAD_OP", "the root cannot be removed", i, widget=wid)
    gone = [wid] + spec_mod.descendants(spec, wid)
    for g in gone:
        _check_unlocked(spec, g, i)
        if index[g].get("binding"):
            raise PatchError("BINDING_REMOVAL", f"'{g}' is bound — bound widgets cannot be removed (bindings only grow)", i, widget=g)
    spec["widgets"] = [w for w in spec["widgets"] if w["id"] not in gone]


def _op_move(spec: dict, op: dict, i: int) -> None:
    wid, parent = op["widget"], op["parent"]
    index = spec_mod.widget_index(spec)
    for x in (wid, parent):
        if x not in index:
            raise PatchError("NOT_FOUND", f"no widget '{x}'", i, widget=x)
    if wid == spec.get("root"):
        raise PatchError("BAD_OP", "the root cannot be moved", i, widget=wid)
    if parent == wid or parent in spec_mod.descendants(spec, wid):
        raise PatchError("CYCLE", f"'{parent}' is '{wid}' or below it", i, widget=wid, parent=parent)
    _check_unlocked(spec, wid, i)
    _check_unlocked(spec, parent, i)
    w = index[wid]
    old_parent_type = index[w["parent"]]["type"]
    new_parent_type = index[parent]["type"]
    spec["widgets"] = [x for x in spec["widgets"] if x["id"] != wid]
    w["parent"] = parent
    if "slot" in op:
        w["slot"] = copy.deepcopy(op["slot"])
    elif spec_mod.CHILD_SLOT_KIND.get(old_parent_type) != spec_mod.CHILD_SLOT_KIND.get(new_parent_type):
        w["slot"] = {"kind": spec_mod.CHILD_SLOT_KIND.get(new_parent_type)}   # 다른 종류 부모 — 슬롯은 기본값부터
    _insert_at(spec, w, parent, op.get("index"))


def _op_replace_asset(spec: dict, op: dict, i: int) -> None:
    assets = {a["asset_id"]: a for a in spec.get("assets", [])}
    aid = op["asset"]
    if aid not in assets:
        raise PatchError("NOT_FOUND", f"no asset '{aid}'", i, asset=aid)
    a = assets[aid]
    if "procedural" in op:
        a["procedural"] = copy.deepcopy(op["procedural"])
    if "prompt" in op:
        a["prompt"] = op["prompt"]


OPS = {"set": _op_set, "add_widget": _op_add, "remove_widget": _op_remove, "move": _op_move, "replace_asset": _op_replace_asset}


def apply_patch(spec: dict, patch: dict) -> dict:
    """patch 를 적용한 새 spec. 실패하면 PatchError (spec 은 그대로)."""
    errs = schema.errors("patch", patch)
    if errs:
        raise PatchError("BAD_PATCH", "; ".join(errs[:5]), errors=errs)
    out = copy.deepcopy(spec)
    for i, op in enumerate(patch["ops"]):
        OPS[op["op"]](out, op, i)
    sem = spec_mod.validate_semantics(out)
    if sem:
        raise PatchError("INVALID_RESULT", "patched spec fails validation: " + "; ".join(sem[:5]), errors=sem)
    errs = schema.errors("spec", out)
    if errs:
        raise PatchError("INVALID_RESULT", "patched spec fails the schema: " + "; ".join(errs[:5]), errors=errs)
    return out


BRANCH_ORDER = ("codegen", "generate", "build")   # 앞일수록 더 이른 단계로 돌아간다


def op_branch(op: dict) -> str:
    kind = op["op"]
    if kind == "add_widget" and op["widget"].get("binding"):
        return "codegen"
    if kind == "set" and op["path"].split(".")[0] == "binding":
        return "codegen"
    if kind == "replace_asset":
        return "generate"
    return "build"


def branch_for(patch: dict) -> str:
    """patch 가 돌아갈 단계 — 바인딩 추가 · 바뀜 = codegen, 에셋 교체 = generate, 그 밖(배치 · 슬롯 · 스타일 · 텍스트) = build (설계 §2-2)."""
    branches = {op_branch(op) for op in patch.get("ops", [])}
    return next((b for b in BRANCH_ORDER if b in branches), "build")


def regenerate_assets(patch: dict) -> list[str]:
    """generate 로 돌아갈 때 다시 만들 에셋 — 그 에셋만."""
    return sorted({op["asset"] for op in patch.get("ops", []) if op["op"] == "replace_asset"})
