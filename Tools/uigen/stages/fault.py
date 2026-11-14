"""--inject-fault — normalize 뒤 spec 을 일부러 깨뜨린다 (설계 §11 1a-4 '깨뜨린 run 1회가 재시도로 통과' · §12-2 9).

결함은 spec patch(source: fault)로 만들어 patches/000.json 에 남기고 spec.json 에 적용한다 — 재시도의 정정 patch 와 같은 모양 · 같은 적용 코드.
대상은 spec 에서 고른다(손 spec 의 위젯 이름에 묶지 않는다): '영역' = 루트 Canvas 직계 · 점 앵커 · bbox_intent 가 있는 위젯.
모두 배치(build 분기) 결함이라 codegen 계약은 그대로다.
"""
from __future__ import annotations

from core import patch as patch_mod
from core import spec as spec_mod
from stages import StageError

FAULTS = {
    "offscreen": "첫 영역을 캔버스 너비만큼 오른쪽으로 민다 — 화면 밖 · 영역/말단 배치 실패",
    "overlap": "중심이 가장 가까운 두 영역 중 작은 쪽을 큰 쪽 중심으로 옮긴다 — 겹침 · 영역 배치 실패",
    "drift": "가장 큰 영역을 너비의 25 % 만큼 왼쪽으로 민다 — 영역 배치(IoU)만 실패",
}


def regions(spec: dict) -> list[dict]:
    """정규화 값으로 본 영역 — [{id, slot(정규화), intent}] (트리 순서)."""
    norm = spec_mod.normalize(spec)
    out = []
    for w in norm["widgets"]:
        slot = w.get("slot") or {}
        a = slot.get("anchors")
        if w.get("parent") != norm["root"] or slot.get("kind") != "canvas" or not w.get("bbox_intent") or slot.get("auto_size"):
            continue
        if a[0] != a[2] or a[1] != a[3]:
            continue
        out.append({"id": w["id"], "slot": slot, "intent": [float(v) for v in w["bbox_intent"]]})
    return out


def _center(b):
    return b[0] + b[2] / 2, b[1] + b[3] / 2


def fault_patch(name: str, spec: dict) -> dict:
    if name not in FAULTS:
        raise StageError("FAULT_UNKNOWN", f"--inject-fault '{name}' — one of {', '.join(FAULTS)}")
    regs = regions(spec)
    if not regs:
        raise StageError("FAULT_NO_TARGET", "the spec has no region (root canvas child with point anchors and bbox_intent) to break")
    canvas_w = float(spec["canvas"][0])
    if name == "offscreen":
        r = regs[0]
        pos = r["slot"]["position"]
        ops = [{"op": "set", "widget": r["id"], "path": "slot.position", "value": [spec_mod.canon_number(pos[0] + canvas_w), pos[1]],
                "reason": f"fault offscreen — +{canvas_w:g} px right"}]
    elif name == "overlap":
        if len(regs) < 2:
            raise StageError("FAULT_NO_TARGET", "overlap needs two regions")
        best = None
        for i in range(len(regs)):
            for j in range(i + 1, len(regs)):
                ci, cj = _center(regs[i]["intent"]), _center(regs[j]["intent"])
                d = (ci[0] - cj[0]) ** 2 + (ci[1] - cj[1]) ** 2
                if best is None or d < best[0]:
                    best = (d, regs[i], regs[j])
        _, a, b = best
        small, big = (a, b) if a["intent"][2] * a["intent"][3] <= b["intent"][2] * b["intent"][3] else (b, a)
        cs, cb = _center(small["intent"]), _center(big["intent"])
        pos = small["slot"]["position"]
        ops = [{"op": "set", "widget": small["id"], "path": "slot.position",
                "value": [spec_mod.canon_number(pos[0] + cb[0] - cs[0]), spec_mod.canon_number(pos[1] + cb[1] - cs[1])],
                "reason": f"fault overlap — '{small['id']}' onto the centre of '{big['id']}'"}]
    else:   # drift
        r = max(regs, key=lambda x: x["intent"][2] * x["intent"][3])
        pos = r["slot"]["position"]
        dx = round(r["intent"][2] * 0.25)
        ops = [{"op": "set", "widget": r["id"], "path": "slot.position", "value": [spec_mod.canon_number(pos[0] - dx), pos[1]],
                "reason": f"fault drift — {dx} px left"}]
    return {"schema_version": 1, "base_revision": None, "source": "fault", "note": f"--inject-fault {name}: {FAULTS[name]}", "ops": ops}


def inject(run, name: str) -> tuple[str, dict]:
    """patches/000.json 을 쓰고 spec.json 에 적용한다. (detail, 기록) 를 돌려준다."""
    spec = run.read_json("spec.json")
    patch = fault_patch(name, spec)
    try:
        broken = patch_mod.apply_patch(spec, patch)
    except patch_mod.PatchError as exc:
        raise StageError("FAULT_PATCH", str(exc)) from exc
    run.write_json("patches/000.json", patch)
    run.write_json("spec.json", broken)
    targets = ", ".join(f"{op['widget']}.{op['path']}={op['value']}" for op in patch["ops"])
    return f"{name} — {targets}", {"name": name, "description": FAULTS[name], "patch": "patches/000.json", "ops": patch["ops"]}
