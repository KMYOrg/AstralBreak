"""1b 후속 L 다음 고침 — controls_alpha 실패 사슬: (나) 편집기가 담지 못하는 값 가드(draw_as none 브러시 image_size) · (다) 결정적 fixer 가 투명 image
브러시로 크기 · (가) 재시도 루프가 build 거절 뒤 patch 전 spec 으로 되돌려 fix 를 1 회 다시."""
from __future__ import annotations

import types

import pytest

from stages import StageError, fix

SPEC = {"root": "Root", "canvas": [400, 200], "widgets": [
    {"id": "Root", "type": "CanvasPanel"},
    {"id": "Group", "type": "Overlay", "parent": "Root", "bbox_intent": [100, 50, 66, 66],
     "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [100, 50], "size": [66, 66], "auto_size": True}},
    {"id": "Badge", "type": "Image", "parent": "Group", "bbox_intent": [100, 50, 66, 66], "style": {"brush": {"draw_as": "none"}},
     "slot": {"kind": "overlay", "h_align": "left", "v_align": "top", "padding": [0, 0, 0, 0]}}]}


def test_vocabulary_guard_rejects_image_size_on_a_none_brush():
    bad = [{"op": "set", "widget": "Badge", "path": "style.brush.image_size", "value": [66, 66]}]
    after = {**SPEC, "widgets": [*SPEC["widgets"][:2], {**SPEC["widgets"][2], "style": {"brush": {"draw_as": "none", "image_size": [66, 66]}}}]}
    errs = fix.vocabulary_errors(after, bad)
    assert errs and "draw_as none cannot hold image_size" in errs[0]
    ok_brush = {"draw_as": "image", "color": fix.INVISIBLE_IMAGE_COLOR, "image_size": [66, 66]}
    after_ok = {**SPEC, "widgets": [*SPEC["widgets"][:2], {**SPEC["widgets"][2], "style": {"brush": ok_brush}}]}
    assert fix.vocabulary_errors(after_ok, [{"op": "set", "widget": "Badge", "path": "style.brush", "value": ok_brush}]) == []
    # 패치가 안 건드린 위젯은 보지 않는다(잘 되던 spec 은 그대로)
    assert fix.vocabulary_errors(after, [{"op": "set", "widget": "Group", "path": "slot.position", "value": [100, 50]}]) == []


def test_deterministic_fixer_sizes_an_invisible_leaf_image_with_a_transparent_image_brush():
    gates = [{"name": "iou_leaf", "pass": False, "details": {"failed": ["Badge"]}}]
    geometry = [{"id": "Root", "x": 0, "y": 0, "w": 400, "h": 200, "visible": True},
                {"id": "Group", "x": 100, "y": 50, "w": 32, "h": 32, "visible": True},
                {"id": "Badge", "x": 100, "y": 50, "w": 32, "h": 32, "visible": True}]
    fixes, ops = fix.propose_deterministic(SPEC, gates, geometry)
    assert ops == [{"op": "set", "widget": "Badge", "path": "style.brush", "reason": ops[0]["reason"],
                    "value": {"draw_as": "image", "color": "#FFFFFF00", "image_size": [66, 66]}}]
    # 캔버스 슬롯 잎 · 보이는 브러시는 예전 길(이 규칙 안 탐)
    vis = {**SPEC, "widgets": [*SPEC["widgets"][:2], {**SPEC["widgets"][2], "style": {"brush": {"draw_as": "image", "color": "#FFFFFFFF"}}}]}
    assert not any(o.get("path") == "style.brush" for o in fix.propose_deterministic(vis, gates, geometry)[1])


class _Run:
    def __init__(self, files):
        self.files, self.records = dict(files), []

    def read_json(self, p):
        return self.files[p]

    def write_json(self, p, v):
        self.files[p] = v

    def stage_begin(self, name):
        self.records.append(("begin", name))

    def stage_end(self, name, status, detail="", **extra):
        self.records.append((name, status))


def test_retry_loop_refixes_after_the_editor_rejects_a_fix_patch(monkeypatch):
    import run_pipeline as rp
    pre = {"widgets": [{"id": "A"}], "v": "pre"}
    run = _Run({"specs/001.json": pre, "patches/001.json": {"ops": [{"op": "set"}]}, "spec.json": {"v": "patched"}})
    ctx = {"attempts": [{"spec": "specs/001.json", "patch": "patches/001.json", "branch": "build"}, {"spec": "specs/002.json"}],
           "last": {"pass": False, "failed": ["iou_leaf"], "gates": []}, "fixes": []}
    seen = {}

    def fake_propose(run_, attempt, res, rejected=None):
        seen.update(attempt=attempt, rejected=rejected, spec=run_.read_json("spec.json"))
        return {"fixes": [], "patch": {"ops": [{"op": "set", "widget": "A", "path": "x", "value": 1}]}, "patch_file": "patches/001.json", "branch": "build"}
    monkeypatch.setattr(rp.fix, "propose", fake_propose)
    monkeypatch.setattr(rp.patch_mod, "apply_patch", lambda spec, patch: {**spec, "v": "refixed"})
    monkeypatch.setattr(rp, "_structural_only", lambda res: res)
    ok = rp._refix_after_build_rejection(run, ctx, 2, StageError("VALIDATION_FAILED", "applied tree differs"))
    assert ok and seen["attempt"] == 1 and seen["spec"]["v"] == "pre" and "VALIDATION_FAILED" in seen["rejected"][0]
    assert run.files["spec.json"]["v"] == "refixed" and run.files["patches/001_rejected.json"] == {"ops": [{"op": "set"}]}
    # 한 번만 — 다시 거절되면 False(원래 오류를 던짐)
    assert not rp._refix_after_build_rejection(run, ctx, 2, StageError("VALIDATION_FAILED", "again"))
    # 첫 시도 build 실패(fix patch 없음)는 받지 않는다
    assert not rp._refix_after_build_rejection(run, {"attempts": [{"spec": "specs/001.json"}], "last": None, "fixes": []}, 1,
                                               StageError("X", "y"))
