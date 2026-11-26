"""Phase 3-3 — 조작 화면: 동작 · 칸 바인딩 계약, 놓인 칸(요청이 정한 자리 · 원본 아트 속 칸 그림), 가리는 위젯 없음, 바탕 위 표시, 긴 글자, 메뉴 프로필, 상대 경로, 쓰는 화면
목록, 한 명령. 검사는 먼저 **일부러 틀린 값**이 걸리는지 본다. 에디터 · codex · claude 없음."""
from __future__ import annotations

import copy
import json
import pathlib
import types

import numpy as np
import pytest
from PIL import Image

import make_screen
from core import cellref, config, cppgen, hit, schema
from core import spec as spec_mod
from gen import backdrop, cell_art, cells, overlay_mark, screen_check
from gen import diagnose as dg
from stages import StageError, analyze, fix, normalize, request

CFG = config.load_pipeline()
CG = CFG["codegen"]
SCREENS = config.load_screens()
MODULE = config.repo_path(CG["module_root"])
S = dg.settings(CFG)


# ---------------------------------------------------------------------------------------------------------------------
# 승격된 칸 흉내 — 버튼 칸 하나 · 줄 칸 하나

ROW = [200, 40]
BTN = [120, 40]


def promote_fake(root: pathlib.Path, screen: str, spec: dict, textures: dict[str, np.ndarray], cls: str | None, run_id="R20261125_000000_X", geometry=None, cells_=None) -> None:
    src = root / screen / "source"
    (src / "assets" / "final").mkdir(parents=True)
    (src / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    W, H = spec["canvas"]
    geo = geometry or [{"id": w["id"], "type": w["type"], "parent": w.get("parent") or "", "x": 0, "y": 0, "w": W, "h": H, "visible": True} for w in spec["widgets"]]
    (src / "geometry.json").write_text(json.dumps({"canvas": [W, H], "geometry": {f"{W}x{H}": geo}}), encoding="utf-8")
    for a, px in textures.items():
        Image.fromarray(px.astype(np.uint8), "RGBA").save(src / "assets" / "final" / f"{a}.png")
    (src / "manifest.json").write_text(json.dumps({"assets": [{"asset_id": a, "file": f"assets/final/{a}.png"} for a in textures]}), encoding="utf-8")
    if cls:
        (src / "codegen.json").write_text(json.dumps({"class": cls}), encoding="utf-8")
    rec = {"screen_id": screen, "run_id": run_id, "wbp": f"/Game/UI/T/{screen}/WBP_{screen}.WBP_{screen}", **({"cells": cells_} if cells_ else {})}
    (root / screen / "promotion.json").write_text(json.dumps(rec), encoding="utf-8")


def row_spec() -> dict:
    return {"schema_version": 1, "canvas": ROW, "profile": "cell", "root": "Root", "assets": [{"asset_id": "band", "size": ROW, "provenance": "codex"}],
            "widgets": [{"id": "Root", "type": "CanvasPanel"},
                        {"id": "Band", "type": "Image", "parent": "Root", "bbox_intent": [0, 0, *ROW], "slot": {"kind": "canvas"}, "style": {"brush": {"draw_as": "image", "asset": "band"}}}]}


def button_spec() -> dict:
    return {"schema_version": 1, "canvas": BTN, "profile": "cell", "root": "Root", "assets": [{"asset_id": "art", "size": BTN, "provenance": "codex"}],
            "button": {"art": "Art", "states": {}, "theme": {"id": "blade", "sha256": "0" * 64}},
            "widgets": [{"id": "Root", "type": "CanvasPanel"},
                        {"id": "Art", "type": "Image", "parent": "Root", "bbox_intent": [0, 0, *BTN], "slot": {"kind": "canvas"}, "style": {"brush": {"draw_as": "image", "asset": "art"}}}]}


def band_px(size=ROW, level=20) -> np.ndarray:
    c = np.zeros((size[1], size[0], 4))
    c[4:-4, 4:-4] = (level, level, level + 4, 220)
    c[-7:-4, 10:-10] = (220, 215, 205, 255)
    return c


@pytest.fixture
def promoted(tmp_path):
    root = tmp_path / "promoted"
    promote_fake(root, "HubMemberRow", row_spec(), {"band": band_px()}, "/Script/AstralBreak.AstralHubMemberRowWidget", "R20261125_000001_HubMemberRow")
    promote_fake(root, "ButtonSmall", button_spec(), {"art": band_px(BTN, 12)}, "/Script/AstralBreak.AstralButtonBase", "R20261125_000002_ButtonSmall")
    return root


ROW_PKG, BTN_PKG = "/Game/UI/T/HubMemberRow/WBP_HubMemberRow", "/Game/UI/T/ButtonSmall/WBP_ButtonSmall"


def screen_spec() -> dict:
    """화면 하나 — 제목 글자 · 줄 칸 하나 · 버튼 칸 둘."""
    def cell(wid, pkg, kind, data, x, y, size, **b):
        return {"id": wid, "type": "UserWidget", "class": pkg, "parent": "Root", "bbox_intent": [x, y, *size],
                "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [x, y], "size": list(size), "z": 10}, "binding": {"data": data, "kind": kind, **b}}
    return {"schema_version": 1, "canvas": [640, 360], "profile": "menu", "root": "Root", "assets": [],
            "widgets": [{"id": "Root", "type": "CanvasPanel"},
                        {"id": "Title", "type": "TextBlock", "parent": "Root", "bbox_intent": [20, 20, 200, 30], "slot": {"kind": "canvas", "position": [20, 20], "size": [200, 30]},
                         "text": {"source": "static", "value": "출정"}},
                        cell("Row1", ROW_PKG, "cell", "row1", 20, 80, ROW),
                        cell("ReadyButton", BTN_PKG, "action", "ready", 400, 280, BTN, selectable=True),
                        cell("LaunchButton", BTN_PKG, "action", "launch", 400, 320, BTN)]}


def resolver(promoted):
    return cppgen.cell_resolver(SCREENS, CG, MODULE, promoted)


# ---------------------------------------------------------------------------------------------------------------------
# 계약

def test_cells_bind_their_real_class_from_the_promotion_record(promoted):
    e = {x["name"]: x for x in cppgen.binding_entries(screen_spec(), resolver(promoted))}
    assert e["Row1"]["widget_class"] == "AstralHubMemberRowWidget" and e["Row1"]["include"] == "UI/Screens/AstralHubMemberRowWidget.h" and e["Row1"]["cell"] == "HubMemberRow"
    assert e["ReadyButton"]["widget_class"] == "AstralButtonBase" and e["ReadyButton"]["include"] == "UI/Foundation/AstralButtonBase.h"      # 모듈에서 찾은 헤더 하나
    assert e["ReadyButton"]["selectable"] is True and e["LaunchButton"]["selectable"] is False and "selectable" not in e["Row1"]
    with pytest.raises(cppgen.ContractError, match="CELL_UNRESOLVED"):
        cppgen.binding_entries(screen_spec())


def test_wrong_kind_unknown_cell_or_changed_class_is_refused(promoted):
    for wid, kind in (("Row1", "action"), ("ReadyButton", "cell")):
        s = screen_spec()
        w = next(x for x in s["widgets"] if x["id"] == wid)
        w["binding"] = {"data": "x", "kind": kind}
        with pytest.raises(cppgen.ContractError, match="CELL_KIND"):
            cppgen.binding_entries(s, resolver(promoted))
    s = screen_spec()
    s["widgets"][2]["class"] = "/Game/UI/T/Nope/WBP_Nope"
    with pytest.raises(cppgen.ContractError, match="CELL_NOT_PROMOTED"):
        cppgen.binding_entries(s, resolver(promoted))
    (promoted / "HubMemberRow" / "source" / "codegen.json").write_text(json.dumps({"class": "/Script/AstralBreak.AstralOldRow"}), encoding="utf-8")
    with pytest.raises(cppgen.ContractError, match="CELL_CLASS_CHANGED"):
        cppgen.binding_entries(screen_spec(), resolver(promoted))
    with pytest.raises(cellref.CellError, match="CLASS_HEADER"):
        cellref.header_of("NoSuchAstralClass", MODULE)


def contract(promoted, spec=None, previous=None):
    b, ch = cppgen.merge(cppgen.binding_entries(spec or screen_spec(), resolver(promoted)), previous)
    doc = cppgen.contract_doc("HubReady", SCREENS["HubReady"], CG, b, cppgen.screen_base(SCREENS["HubReady"], MODULE))
    return doc, ch


def test_generated_screen_base_only_asks_and_never_changes_its_own_look(promoted):
    doc, _ = contract(promoted)
    schema.require("codegen", {"schema_version": 1, "run_id": "R", "screen": "HubReady", "class": "/Script/AstralBreak.AstralHubReadyWidget", "contract_hash": cppgen.contract_hash(doc),
                               "contract": doc, "changes": {"added": [], "demoted": [], "changed": [], "restored": []}, "skipped": True, "reason": "new", "files": [],
                               "editor": {}, "build": {"ran": False}})
    t = cppgen.render(doc, cppgen.contract_hash(doc))
    h, c = t["view_base_h"], t["view_base_cpp"]
    assert '#include "UI/Foundation/AstralActivatableWidget.h"' in h and "class ASTRALBREAK_API UAstralHubReadyViewBase : public UAstralActivatableWidget" in h
    assert "TObjectPtr<UAstralButtonBase> ReadyButton;" in h and "TObjectPtr<UAstralHubMemberRowWidget> Row1;" in h
    assert "virtual void HandleReadyClicked() {}" in h and "virtual void HandleLaunchClicked() {}" in h
    assert "UAstralHubMemberRowWidget* GetRow1() const { return Row1; }" in h
    assert "void SetReadyEnabled(bool bEnabled);" in h and "void SetReadySelected(bool bSelected);" in h
    assert "void SetLaunchEnabled(bool bEnabled);" in h and "SetLaunchSelected" not in h                # 선택 모양은 요청이 selectable 일 때만
    assert "ReadyButton->OnClicked().AddUObject(this, &ThisClass::HandleReadyClicked);" in c and "Super::NativeOnInitialized();" in c
    assert '#include "UI/Screens/AstralHubMemberRowWidget.h"' in c and '#include "UI/Foundation/AstralButtonBase.h"' in c
    assert "SetSelectedLook(bSelected)" in c and "SetIsEnabled(bEnabled)" in c
    body = c[c.index("NativeOnInitialized()"):c.index("SetLaunchEnabled")]
    assert "SetSelectedLook" not in body and "SetIsEnabled" not in body                                  # 누름은 요청만 — 모양을 안 바꾼다
    assert "#include \"UI/Screens/AutoGen/AstralHubReadyViewBase.h\"" in t["widget_h"]
    head = h.splitlines()
    assert json.loads(head[2][len(cppgen.CONTRACT_PREFIX):]) == doc and cppgen.contract_hash(doc) in head[1]


def test_new_pieces_enter_the_hash_only_when_used(promoted, monkeypatch):
    plain = [{"name": "T", "widget_class": "TextBlock", "data": "t", "kind": "text", "optional": False, "setter": "SetT"}]
    assert cppgen.generator_for(plain) == cppgen.generator_id() == "1:49a7a94ed467"
    d = cppgen.contract_doc("StatusHUD", SCREENS["StatusHUD"], CG, plain, cppgen.screen_base(SCREENS["StatusHUD"], MODULE))
    assert "base" not in d
    doc, _ = contract(promoted)
    used = doc["generator"]
    assert used.startswith("1:49a7a94ed467+")
    monkeypatch.setitem(cppgen.EXTRA, "action", {**cppgen.EXTRA["action"], "enabled": ["x"]})
    assert contract(promoted)[0]["generator"] != used and cppgen.generator_for(plain) == "1:49a7a94ed467"
    cell_only = [b for b in doc["bindings"] if b["kind"] == "cell"]
    assert cppgen.extras_of(cell_only, None) == ["cell"] and cppgen.extras_of(cell_only, {"class": "X", "include": "x"}) == ["cell", "screen"]
    assert cppgen.extras_of(plain, None) == []


def test_removed_action_stays_optional_and_names_do_not_collide(promoted):
    doc, _ = contract(promoted)
    s = screen_spec()
    s["widgets"] = [w for w in s["widgets"] if w["id"] != "LaunchButton"]
    doc2, ch = contract(promoted, s, doc["bindings"])
    b = {x["name"]: x for x in doc2["bindings"]}
    assert b["LaunchButton"]["optional"] and ch["demoted"] == ["LaunchButton"]
    h = cppgen.render(doc2, cppgen.contract_hash(doc2))["view_base_h"]
    assert "UPROPERTY(meta = (BindWidgetOptional))\n\tTObjectPtr<UAstralButtonBase> LaunchButton;" in h and "HandleLaunchClicked" in h
    s = screen_spec()
    s["widgets"].append({"id": "Flag", "type": "TextBlock", "parent": "Root", "slot": {"kind": "canvas"}, "binding": {"data": "ready_enabled", "kind": "text"},
                         "text": {"source": "dynamic", "data": "ready_enabled"}})
    with pytest.raises(cppgen.ContractError, match="SETTER_COLLISION"):
        contract(promoted, s)


def test_the_llm_never_sees_cells_or_text_overflow():
    s = json.dumps(analyze.output_schema())
    for word in ('"UserWidget"', '"cell"', '"action"', '"selectable"', '"overflow"', '"button"', '"derived"'):
        assert word not in s.replace('"button", "provided"', "").replace('"size_box", "button"]', ""), word
    kinds = analyze.output_schema()["$defs"]["binding"]["properties"]["kind"]
    assert kinds == {"enum": ["text", "number", "progress", "flag", "image"]}


# ---------------------------------------------------------------------------------------------------------------------
# 가리는 위젯 없음

def geo_of(spec, extra=()):
    return [{"id": w["id"], "type": w["type"], "parent": w.get("parent") or "", "visible": True, **dict(zip("xywh", w.get("bbox_intent") or [0, 0, *spec["canvas"]]))}
            for w in spec["widgets"]] + list(extra)


def exported(spec):
    n = spec_mod.normalize(spec)
    return {"root": n["root"], "widgets": n["widgets"]}


def test_menu_defaults_do_not_eat_clicks_and_other_screens_keep_the_engine_defaults():
    n = {w["id"]: w["visibility"] for w in spec_mod.normalize(screen_spec())["widgets"]}
    assert n == {"Root": "self_hit_test_invisible", "Title": "hit_test_invisible", "Row1": "hit_test_invisible", "ReadyButton": "self_hit_test_invisible",
                 "LaunchButton": "self_hit_test_invisible"}
    hud = {**screen_spec(), "profile": "hud"}
    n = {w["id"]: w["visibility"] for w in spec_mod.normalize(hud)["widgets"]}
    assert n["Title"] == "visible" and n["Row1"] == "self_hit_test_invisible"
    assert {w["id"]: w["visibility"] for w in spec_mod.normalize(button_spec())["widgets"]}["Art"] == "visible"      # 버튼 칸은 예전 그대로
    assert {w["id"]: w["visibility"] for w in spec_mod.normalize(row_spec())["widgets"]}["Band"] == "hit_test_invisible"
    s = screen_spec()
    s["widgets"][1]["visibility"] = "collapsed"
    assert spec_mod.normalize(s)["widgets"][1]["visibility"] == "collapsed"


def test_a_clean_screen_has_no_blocker(promoted):
    s = screen_spec()
    r = hit.check(s, exported(s), geo_of(s), promoted)
    assert r == {"buttons": ["LaunchButton", "ReadyButton"], "blocked": [], "dead": []}


def cover(wid="Cover", vis="visible", z=20, bbox=(390, 270, 60, 60), **extra):
    return {"id": wid, "type": "Image", "parent": "Root", "bbox_intent": list(bbox), "slot": {"kind": "canvas", "z": z, "position": list(bbox[:2]), "size": list(bbox[2:])},
            "visibility": vis, "style": {"brush": {"draw_as": "none"}}, **extra}


@pytest.mark.parametrize("vis,z,blocked", [("visible", 20, True), ("hit_test_invisible", 20, False), ("self_hit_test_invisible", 20, False), ("visible", 0, False)])
def test_wrong_visible_decoration_over_a_button_is_caught(promoted, vis, z, blocked):
    s = screen_spec()
    s["widgets"].append(cover(vis=vis, z=z))
    r = hit.check(s, exported(s), geo_of(s), promoted)
    assert bool(r["blocked"]) is blocked
    if blocked:
        assert {(b["button"], b["by"]) for b in r["blocked"]} == {("ReadyButton", "Cover")} or {b["by"] for b in r["blocked"]} == {"Cover"}


def test_wrong_an_invisible_parent_protects_only_when_it_takes_children_along(promoted):
    s = screen_spec()
    s["widgets"] += [{"id": "Layer", "type": "Overlay", "parent": "Root", "bbox_intent": [390, 270, 60, 60], "slot": {"kind": "canvas", "z": 30}, "visibility": "self_hit_test_invisible"},
                     {"id": "Deco", "type": "Image", "parent": "Layer", "bbox_intent": [390, 270, 60, 60], "slot": {"kind": "overlay"}, "visibility": "visible"}]
    assert [b["by"] for b in hit.check(s, exported(s), geo_of(s), promoted)["blocked"]][:1] == ["Deco"]
    s["widgets"][-2]["visibility"] = "hit_test_invisible"
    assert hit.check(s, exported(s), geo_of(s), promoted)["blocked"] == []


def test_wrong_dead_buttons_and_overlapping_cells_are_caught(promoted):
    s = screen_spec()
    next(w for w in s["widgets"] if w["id"] == "ReadyButton")["visibility"] = "hit_test_invisible"
    assert [d["button"] for d in hit.check(s, exported(s), geo_of(s), promoted)["dead"]] == ["ReadyButton"]
    s = screen_spec()
    g = [x for x in geo_of(s) if x["id"] != "LaunchButton"]
    assert [d["why"] for d in hit.check(s, exported(s), g, promoted)["dead"]] == ["not drawn"]
    s = screen_spec()                                                        # 두 버튼이 겹침
    next(w for w in s["widgets"] if w["id"] == "LaunchButton")["bbox_intent"] = [420, 300, *BTN]
    assert hit.check(s, exported(s), geo_of(s), promoted)["blocked"][0]["why"] == "another button"
    s = screen_spec()                                                        # 줄 칸이 버튼을 덮음 — 칸 속 위젯이 클릭을 먹는 값이면 막힌 것
    row = next(w for w in s["widgets"] if w["id"] == "Row1")
    row.update(bbox_intent=[390, 270, *ROW], visibility="self_hit_test_invisible")
    row["slot"]["z"] = 50
    assert hit.check(s, exported(s), geo_of(s), promoted)["blocked"] == []          # 정규형이 hit_test_invisible 이라 안 먹는다
    src = promoted / "HubMemberRow" / "source" / "spec.json"
    bad = row_spec()
    bad["widgets"][1]["visibility"] = "visible"
    src.write_text(json.dumps(bad), encoding="utf-8")
    assert hit.check(s, exported(s), geo_of(s), promoted)["blocked"][0]["why"] == "cell with visible parts"


# ---------------------------------------------------------------------------------------------------------------------
# 원본 아트 속 칸 자리

def sheet(shift=(0, 0), extra=None):
    """640 × 360 시안 — 줄 칸(20, 80) 이 (조금 다르게) 그려져 있고 제목 띠가 따로 있다 → (곧은 색, 알파)."""
    col, a = np.zeros((360, 640, 3)), np.zeros((360, 640))
    px = band_px()
    x, y = 20 + shift[0], 80 + shift[1]
    col[y:y + ROW[1], x:x + ROW[0]] = px[..., :3] + 12
    a[y:y + ROW[1], x:x + ROW[0]] = px[..., 3] / 255
    a[y + ROW[1] + 2:y + ROW[1] + 5, x + 40:x + 60] = 0.3            # 칸 아래로 삐져나온 얼룩
    col[20:50, 20:220] = 60
    a[20:50, 20:220] = 0.9
    if extra:
        extra(col, a)
    return col, a


def paste(promoted, at=(20, 80)):
    c = {"widget": "Row1", "cell": "HubMemberRow", "at": list(at), "size": ROW}
    return cell_art.Paste([c], {"Row1": cells.picture(ROW_PKG, promoted)["states"]["normal_base"]})


def test_the_cell_place_shows_the_approved_cell_picture(promoted):
    col, a = sheet(shift=(1, 2))
    p = paste(promoted)
    c2, a2 = p(col, a)
    px = band_px()
    got = np.dstack([c2, a2 * 255])[80:120, 20:220]
    assert np.abs(got - px)[px[..., 3] > 0].max() < 1.0                  # 칸의 픽셀 그대로
    assert p.record[0]["shift"] == [1, 2] and p.record[0]["cleared_px"] > 0
    assert a2[120:130, 20:220].max() == 0                                # 삐져나온 얼룩도 그 칸의 그림 — 지운다
    assert (a2[20:50, 20:220] == a[20:50, 20:220]).all()                 # 다른 요소는 그대로
    far = np.ones_like(a, bool)
    far[60:140, 0:240] = False
    assert (a2[far] == a[far]).all() and (c2[far] == col[far]).all()


def test_wrong_place_or_art_over_the_cell_is_refused(promoted):
    col, a = sheet(shift=(0, 6))
    with pytest.raises(cell_art.CellArtError, match="CELL_PLACE"):
        paste(promoted)(col, a)

    def line(c, al):
        al[40:200, 100:106] = 1.0                                         # 칸을 가로지르는 다른 그림(띠와 이어짐)
        c[40:200, 100:106] = 200
        al[190:330, 60:400] = 1.0
    with pytest.raises(cell_art.CellArtError, match="CELL_ART_OVERLAP"):
        paste(promoted)(*sheet(extra=line))
    with pytest.raises(cell_art.CellArtError, match="CELL_OUTSIDE"):
        paste(promoted, at=(620, 350))(*sheet())


# ---------------------------------------------------------------------------------------------------------------------
# 요청이 정하는 자리

def brief_of(promoted, **over) -> dict:
    b = {"resolution": [640, 360], "screen_type": "menu",
         "cells": [{"widget": "Row1", "cell": "HubMemberRow", "class": ROW_PKG, "at": [20, 80], "size": ROW, "button": False, "run_id": "r"},
                   {"widget": "ReadyButton", "cell": "ButtonSmall", "class": BTN_PKG, "at": [400, 280], "size": BTN, "button": True, "run_id": "r", "props": {"ButtonText": "준비"}}],
         "dynamic_data": [{"id": "row1", "type": "cell", "widget": "Row1", "widget_type": "UserWidget"},
                          {"id": "ready", "type": "action", "widget": "ReadyButton", "widget_type": "UserWidget", "selectable": True}], "static_text": [], "required_elements": []}
    return {**b, **over}


def empty_spec(*widgets):
    return {"schema_version": 1, "canvas": [640, 360], "profile": "menu", "root": "Root", "widgets": [{"id": "Root", "type": "CanvasPanel"}, *widgets], "assets": []}


def region(wid, bbox, **extra):
    return {"id": wid, "type": "Overlay", "parent": "Root", "bbox_intent": list(bbox), "slot": {"kind": "canvas", "position": list(bbox[:2]), "size": list(bbox[2:])}, **extra}


def test_cells_come_from_the_request_with_the_cell_size(promoted):
    s = request.place_cells(empty_spec(), brief_of(promoted))
    b = next(w for w in s["widgets"] if w["id"] == "ReadyButton")
    assert b["bbox_intent"] == [400, 280, 120, 40] and b["slot"]["size"] == [120, 40] and b["props"] == {"ButtonText": "준비"}
    assert b["binding"] == {"data": "ready", "kind": "action", "selectable": True} and b["class"] == BTN_PKG
    assert request.place_cells(s, brief_of(promoted)) == s                                       # 다시 넣어도 하나
    assert spec_mod.validate_semantics(s) == []
    assert request.cell_errors(s, brief_of(promoted)) == []
    over = request.place_cells(empty_spec(region("Column", [0, 60, 240, 100])), brief_of(promoted))
    assert any(e.startswith("CELL_COVER: 'Column'") for e in request.cell_errors(over, brief_of(promoted)))
    alien = copy.deepcopy(s)
    alien["widgets"].append({**b, "id": "Mine"})
    assert any(e.startswith("CELL: 'Mine'") for e in request.cell_errors(alien, brief_of(promoted)))


def test_anchor_regions_keep_the_place_and_move_together(promoted):
    s = request.place_cells(empty_spec(region("Title", [20, 20, 200, 30]), region("Bar", [400, 200, 200, 30])), brief_of(promoted))
    rec = request.apply_anchor_regions(s, brief_of(promoted, anchor_regions=[{"box": [320, 0, 320, 360], "anchor": [1, 0.5]}]))
    ix = spec_mod.widget_index(s)
    assert {r["widget"] for r in rec} == {"Bar", "ReadyButton"} and ix["Title"]["slot"]["position"] == [20, 20]
    for wid in ("Bar", "ReadyButton"):
        sl, bb = ix[wid]["slot"], ix[wid]["bbox_intent"]
        assert sl["anchors"] == [1, 0.5, 1, 0.5] and sl["alignment"] == [1, 0.5]
        x = 1 * 640 + sl["position"][0] - 1 * sl["size"][0]
        y = 0.5 * 360 + sl["position"][1] - 0.5 * sl["size"][1]
        assert [x, y] == bb[:2]


@pytest.mark.parametrize("parent", ["overlay", "canvas"])
def test_text_box_keeps_the_requested_width(promoted, parent):
    pan = region("Panel", [10, 20, 300, 60])
    if parent == "canvas":
        pan = {**pan, "type": "CanvasPanel"}
    t = {"id": "Name", "type": "TextBlock", "parent": "Panel", "bbox_intent": [30, 30, 90, 24], "slot": {"kind": "overlay" if parent == "overlay" else "canvas"},
         "font": {"size": 18, "family": CFG["fonts"]["default_family"], "outline": {"size": 2}}, "text": {"source": "dynamic", "data": "name"}}
    b = brief_of(promoted, cells=[], dynamic_data=[{"id": "name", "type": "text", "widget": "Name", "widget_type": "TextBlock", "text_box": [40, 30, 200, 40], "overflow": "ellipsis"}])
    s = empty_spec(pan, t)
    assert request.text_box_errors(s, b) == []
    r = request.apply_text_boxes(s, b, CFG)[0]
    w = spec_mod.widget_index(s)["Name"]
    assert w["overflow"] == "ellipsis" and w["bbox_intent"][0] == 40 and w["bbox_intent"][2] == 200 and r["box"] == w["bbox_intent"]
    assert abs(w["bbox_intent"][1] + w["bbox_intent"][3] / 2 - 50) < 0.1
    if parent == "overlay":
        assert w["slot"]["padding"][0] == 30 and w["slot"]["padding"][2] == 70 and w["slot"]["h_align"] == "fill" and w["slot"]["v_align"] == "center"
    else:
        assert w["slot"]["position"][0] == 30 and w["slot"]["size"][0] == 200
    assert request.text_box_errors(empty_spec(pan, {**t, "justification": "center"}), b)[0].startswith("TEXT_BOX_JUSTIFY")      # 엔진은 가운데 정렬을 줄이지 않는다
    box = {**region("Panel", [10, 20, 300, 60]), "type": "VerticalBox"}
    assert request.text_box_errors(empty_spec(box, {**t, "slot": {"kind": "vertical_box"}}), b)[0].startswith("TEXT_BOX_PARENT")


def test_llm_fix_cannot_touch_cells_text_boxes_or_marks(promoted):
    b = brief_of(promoted)
    b["dynamic_data"] += [{"id": "name", "type": "text", "widget": "Name", "text_box": [0, 0, 9, 9]}, {"id": "lead", "type": "flag", "widget": "Mark", "over": "Band"}]
    s = request.place_cells(empty_spec(), brief_of(promoted))
    ops = [{"op": "set", "widget": "Row1", "path": "slot.position", "value": [0, 0]}, {"op": "remove_widget", "widget": "ReadyButton"},
           {"op": "set", "widget": "Name", "path": "slot.padding", "value": [0, 0, 0, 0]}, {"op": "set", "widget": "Mark", "path": "style.brush", "value": {}}]
    assert len(fix.guard_ops(ops, s, b)) == 4
    assert fix.guard_ops([{"op": "set", "widget": "Name", "path": "justification", "value": "left"}], s, b) == []


# ---------------------------------------------------------------------------------------------------------------------
# 바탕 위 표시

MW, MH = 320, 90


def band_art(mark=True):
    """반투명 띠(왼쪽이 옅어짐) + 아래 강철 선 + 왼쪽 초승달 → (곧은 색, 알파)."""
    import cv2
    col, a = np.zeros((MH, MW, 3)), np.zeros((MH, MW))
    xx = np.arange(MW)[None, :]
    col[4:84] = (18, 18, 20)
    a[4:84] = np.clip(xx / 60.0, 0, 0.88)
    col[78:82, 10:] = (222, 216, 204)
    a[78:82, 10:] = 1.0
    if mark:
        m = np.zeros((MH * 4, MW * 4), np.uint8)
        cv2.ellipse(m, (70 * 4, 40 * 4), (24 * 4, 24 * 4), 0, 60, 300, 255, 4 * 4, cv2.LINE_AA)
        t = cv2.resize(m, (MW, MH), interpolation=cv2.INTER_AREA) / 255.0
        cp = col * a[..., None] * (1 - t[..., None]) + np.array([205, 200, 190]) * t[..., None] * 0.95
        ca = a * (1 - t) + 0.95 * t
        col, a = np.where(ca[..., None] > 1e-4, cp / np.maximum(ca, 1e-4)[..., None], 0), ca
    return col, a


MARK_BOX = [44, 14, 52, 52]


def test_the_mark_is_split_from_the_band_under_it():
    col, a = band_art()
    plain_c, plain_a = band_art(mark=False)
    fb = overlay_mark.fit_box(col, a, MARK_BOX)
    assert fb == overlay_mark.fit_box(col, a, [46, 16, 46, 44]) == overlay_mark.fit_box(col, a, [42, 12, 56, 56])      # 모자란 · 넉넉한 상자도 같은 자리
    m = overlay_mark.measure(col, a, fb)
    c2, a2 = overlay_mark.paste_base(col, a, [m])
    for bg in (0, 128, 255):
        want = plain_c * plain_a[..., None] + bg * (1 - plain_a[..., None])
        got = c2 * a2[..., None] + bg * (1 - a2[..., None])
        assert np.abs(got - want).max() < 14                                             # 표시를 걷은 띠 = 원래 띠(가로로 빠르게 옅어지는 자리라 흰 바탕에서 10 남짓)
        al = m["rgba"][..., 3:] / 255
        x, y, w, h = m["box"]
        on = got.copy()
        on[y:y + h, x:x + w] = m["rgba"][..., :3] * al + on[y:y + h, x:x + w] * (1 - al)
        concept = col * a[..., None] + bg * (1 - a[..., None])
        assert np.abs(on - concept).max() < 16                                           # 얹으면 시안
    out = ~m["mask"]
    assert (c2[out] == col[out]).all() and (a2[out] == a[out]).all()                     # 획 밖은 시안 그대로


def test_a_mark_that_cannot_be_measured_stops():
    col, a = band_art(mark=False)
    with pytest.raises(overlay_mark.MarkError, match="no mark"):
        overlay_mark.fit_box(col, a, MARK_BOX)
    col, a = band_art()
    with pytest.raises(overlay_mark.MarkError, match="runs out"):
        overlay_mark.fit_box(col, a, [44, 14, 20, 20])                                   # 초승달의 일부만 — 크게 벗어남
    with pytest.raises(overlay_mark.MarkError, match="edge of the box"):
        overlay_mark.measure(col, a, [44, 14, 40, 40])


def mark_scene():
    col, a = band_art()
    m = overlay_mark.measure(col, a, overlay_mark.fit_box(col, a, MARK_BOX))
    c2, a2 = overlay_mark.paste_base(col, a, [m])
    tex = {"plate": np.dstack([c2, a2 * 255]), "mark": m["rgba"]}
    spec = {"schema_version": 1, "canvas": [MW, MH], "profile": "cell", "root": "Root",
            "widgets": [{"id": "Root", "type": "CanvasPanel"}, {"id": "Plate", "type": "Image", "parent": "Root", "slot": {"kind": "canvas"}, "style": {"brush": {"asset": "plate"}}},
                        {"id": "Mark", "type": "Image", "parent": "Root", "slot": {"kind": "canvas", "z": 1}, "style": {"brush": {"asset": "mark"}}}]}
    boxes = [{"id": "Root", "x": 0, "y": 0, "w": MW, "h": MH, "visible": True}, {"id": "Plate", "x": 0, "y": 0, "w": MW, "h": MH, "visible": True},
             {"id": "Mark", **dict(zip("xywh", m["box"])), "visible": True}]
    return spec, boxes, tex, {"widget": "Mark", "over": "Plate", "box": m["box"], "mask_px": m["mask"]}, (col, a)


def run_marks(tex=None, off_spec=None, shift=0, boom=None):
    spec, boxes, tex0, mk, (rc, ra) = mark_scene()
    tex = tex or tex0
    base = backdrop.compose(spec, boxes, tex, [MW, MH], (0, 0, 0))[0]
    off = backdrop.compose(off_spec or dg._without(spec, {"Mark"}), boxes, tex, [MW, MH], (0, 0, 0))[0]
    if shift:
        off = np.roll(off, shift, 1)

    def draw(name):
        assert name == "state_Mark_off"
        if boom:
            raise boom
        return off
    r = screen_check.mark_states([mk], spec, boxes, tex, [MW, MH], rc, ra, S, base, render_state=draw)
    return {f["check"] for f in r["findings"]}, r


def test_a_correct_mark_is_clean():
    found, r = run_marks()
    assert found == set() and r["marks"][0]["contrast"] > 30 and set(r["images"]["Mark"]) == {"on", "off", "off_gray"}


def test_wrong_hole_where_the_mark_was_cut_out_of_the_plate():
    spec, boxes, tex, mk, _ = mark_scene()
    x, y, w, h = mk["box"]
    p = tex["plate"].copy()
    p[y:y + h, x:x + w] = 0                                                              # 예전 규칙 — 상자째 판에서 뺌
    assert "mark_trace" in run_marks({**tex, "plate": p})[0]


def test_wrong_trace_of_the_mark_left_in_the_plate():
    _, _, tex, _, (col, a) = mark_scene()
    assert {"mark_trace"} <= run_marks({**tex, "plate": np.dstack([col, a * 255])})[0]   # 표시가 판에도 구워짐


def test_wrong_mark_does_not_hide_moves_or_cannot_be_drawn():
    spec, *_ = mark_scene()
    assert {"mark_state", "mark_same"} <= run_marks(off_spec=spec)[0]
    assert "mark_outside" in run_marks(shift=6)[0]
    assert run_marks(boom=RuntimeError("x"))[0] == {"mark_render"}


# ---------------------------------------------------------------------------------------------------------------------
# 긴 글자

def long_scene(long_px, base_px=(60, 70), stray=None, neighbour=(200, 260)):
    """글자 칸 [50, 20, 140, 24] · 이웃 글자 칸(x0 = neighbour[0]). 글자는 세로 막대 무늬로."""
    spec = {"widgets": [{"id": "Name", "type": "TextBlock", "font": {"outline": {"size": 2}}}, {"id": "Ready", "type": "TextBlock"}]}
    boxes = [{"id": "Name", "x": 50, "y": 20, "w": 140, "h": 24, "visible": True}, {"id": "Ready", "x": neighbour[0], "y": 20, "w": neighbour[1] - neighbour[0], "h": 24, "visible": True}]
    blank = np.full((64, 320, 3), 12.0)

    def ink(img, x0, x1):
        for x in range(int(x0), int(x1), 6):
            img[24:40, x:x + 3] = 230
        return img
    nt = blank.copy()
    ready = (max(neighbour[0], 200) + 4, neighbour[1] - 4)
    base = ink(ink(blank.copy(), *base_px), *ready)
    img = ink(ink(blank.copy(), *long_px), *ready)
    if stray:
        ink(img, *stray)
    return spec, boxes, base, img, nt


def run_long(*a, **k):
    spec, boxes, base, img, nt = long_scene(*a, **k)
    r = screen_check.long_texts({"Name": "아주 긴 이름"}, spec, boxes, [320, 64], S, base, render_state=lambda n: img, notext=nt)
    return {f["check"] for f in r["findings"]}, r


def test_a_long_text_that_fills_and_stays_in_its_box_is_clean():
    found, r = run_long((52, 186))
    assert found == set() and r["texts"][0]["fill"] >= 0.8


def test_wrong_long_text_leaves_its_box_touches_or_proves_nothing():
    assert "long_outside" in run_long((52, 240))[0]                                      # 줄임이 안 먹음 — 칸 밖(이웃 위)까지
    assert run_long((52, 100))[0] == {"long_short"}                                      # 짧거나 덮어쓰기가 안 먹음
    assert "long_touch" in run_long((52, 186), neighbour=(150, 260))[0]                  # 칸끼리 겹쳐 이웃 글자 칸으로 들어감
    spec, boxes, base, img, nt = long_scene((52, 186))
    r = screen_check.long_texts({"Name": "x"}, spec, boxes, [320, 64], S, base, render_state=lambda n: (_ for _ in ()).throw(RuntimeError("no")), notext=nt)
    assert {f["check"] for f in r["findings"]} == {"long_render"}
    assert screen_check.long_texts({"Name": "x"}, spec, boxes, [320, 64], S, base)["texts"] == []          # 엔진 없음 — 못 본다


def _screen_run(tmp_path):
    """진단 run 하나(test_state_check._diag_run) + 긴 글자 표본(Warn)."""
    from test_state_check import _diag_run
    rd = _diag_run(tmp_path)
    (rd / "brief.json").write_text(json.dumps({"dynamic_data": [{"widget": "Warn", "long_sample": "아주 긴 경고 문구"}]}), encoding="utf-8")
    return rd


def test_a_failed_concept_render_does_not_pass_marks_or_long_texts(tmp_path, monkeypatch):
    """verify 인데 컨셉 상태 렌더부터 못 그림 — 버튼처럼 표시 · 긴 글자도 오류(3-3 뒤 빈틈: 표시는 합성끼리 견줘 통과, 긴 글자는 '못 봄'으로 0 건이었다)."""
    rd = _screen_run(tmp_path)
    monkeypatch.setattr(screen_check, "load_extra", lambda _rd: {"marks": [{"widget": "Plate", "box": [0, 0, 8, 8]}], "long": {"Warn": "아주 긴 경고 문구"}})
    monkeypatch.setattr(screen_check, "mark_states", lambda *a, **k: {"marks": [{"widget": "Plate"}], "findings": [], "images": {}, "renderer": "composite"})

    def boom(*_a, **_k):
        raise RuntimeError("editor gone")
    rec = dg.diagnose(rd, None, {"appearance": {"state_checks": "error"}}, pictures=False, render_state=boom)
    got = {(d["check"], tuple(d["widgets"])) for d in rec["defects"] if str(d.get("check")).endswith("_render")}
    assert got == {("mark_render", ("Plate",)), ("long_render", ("Warn",))} and not dg.gate(rec)["pass"]
    assert all("editor gone" in d["cause"] for d in rec["defects"] if str(d.get("check")).endswith("_render"))
    off = dg.diagnose(rd, None, {"appearance": {"state_checks": "error"}}, pictures=False)              # 오프라인은 엔진을 기대하지 않는다
    assert not any(str(d.get("check")).endswith("_render") for d in off["defects"])
    assert dg.engine_unseen(True, None, (10, 10), buttons=[], marks=[], longs=[]) == []                  # 볼 것이 없으면 오류도 없다


def test_long_texts_are_checked_even_when_the_text_trace_breaks(tmp_path, monkeypatch):
    """긴 글자는 S4(글자 밑 흔적)와 따로 — S4 가 깨져도 건너뛰지 않고, 긴 글자 검사 자체가 깨지면 오류."""
    from test_verify_speed import _engine

    from gen import state_check
    rd = _screen_run(tmp_path)
    monkeypatch.setattr(state_check, "text_trace", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("S4 broke")))
    rec = dg.diagnose(rd, None, {"appearance": {"state_checks": "error"}}, pictures=False, render_state=_engine(rd, tmp_path / "e1"))
    sc = rec["state_checks"]
    assert "S4 broke" in sc["text_trace_error"] and sc["long_texts"]["renderer"] == "engine" and [t["widget"] for t in sc["long_texts"]["texts"]] == ["Warn"]
    monkeypatch.setattr(screen_check, "long_texts", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad")))
    rec = dg.diagnose(rd, None, {"appearance": {"state_checks": "error"}}, pictures=False, render_state=_engine(rd, tmp_path / "e2"))
    assert [d["widgets"] for d in rec["defects"] if d.get("check") == "long_render"] == [["Warn"]] and not dg.gate(rec)["pass"]


def test_state_requests_lists_the_mark_and_long_states(tmp_path):
    extra = {"marks": [{"widget": "Mark"}], "long": {"Name": "긴 글"}}
    r = screen_check.requests(extra, {"H": {"visible": True}})
    assert r == {"state_Mark_off": {"H": {"visible": True}, "Mark": {"visible": False}}, "state_long": {"H": {"visible": True}, "Name": {"text": "긴 글"}}}
    assert screen_check.requests(None, {}) == {} and screen_check.requests({"marks": [], "long": {}}, {}) == {}
    (tmp_path / "brief.json").write_text(json.dumps({"dynamic_data": [{"widget": "Name", "long_sample": "긴 글"}, {"widget": "X"}]}), encoding="utf-8")
    assert screen_check.load_extra(tmp_path) == {"marks": [], "long": {"Name": "긴 글"}}


# ---------------------------------------------------------------------------------------------------------------------
# 요청 · 프로필 · 경로

def test_requests_that_do_not_fit_are_refused(promoted):
    base = {"screen_type": "menu", "required_elements": [{"id": "Band", "kind": "image"}], "data": []}

    def errs(**over):
        return [e.split(":")[0] for e in normalize._screen_errors({**base, **over})]
    cell = {"id": "row1", "type": "cell", "widget": "Row1", "cell": "HubMemberRow", "at": [0, 0]}
    assert errs(cells=[cell]) == []
    assert errs(cells=[cell, {**cell, "id": "b"}]) == ["CELL_DUPLICATE"]
    assert errs(cells=[{**cell, "widget": "Band"}]) == ["CELL_REQUIRED"]
    assert errs(cells=[{**cell, "selectable": True}]) == ["CELL_SELECTABLE"]
    assert errs(cells=[cell], screen_type="hud") == ["CELL_SCREEN"]
    txt = {"id": "n", "type": "text", "widget": "N", "widget_type": "TextBlock", "sample": "abc"}
    assert errs(data=[{**txt, "overflow": "ellipsis", "text_box": [0, 0, 1, 1], "long_sample": "abcd"}]) == []
    assert errs(data=[{**txt, "overflow": "ellipsis"}]) == ["TEXT_LONG"]
    assert errs(data=[{**txt, "overflow": "ellipsis", "text_box": [0, 0, 1, 1], "long_sample": "ab"}]) == ["TEXT_LONG"]
    mark = {"id": "m", "type": "flag", "widget": "M", "widget_type": "Image", "sample": True, "over": "Band"}
    assert errs(data=[mark]) == []
    for bad in ({"over": "Nope"}, {"widget_type": "TextBlock"}, {"sample": False}):
        assert errs(data=[{**mark, **bad}]) == ["DATA_OVER"]
    with pytest.raises(StageError) as e:
        normalize._brief_cells({"cells": [{**cell, "type": "action"}]}, promoted)
    assert e.value.code == "CELL_KIND"
    with pytest.raises(StageError) as e:
        normalize._brief_cells({"cells": [{**cell, "cell": "Nope"}]}, promoted)
    assert e.value.code == "CELL_NOT_PROMOTED"
    with pytest.raises(StageError) as e:
        normalize._brief_cells({"cells": [{**cell, "text": "x"}]}, promoted)
    assert e.value.code == "CELL_TEXT"


def test_the_fixtures_are_valid_requests():
    for name in ("hub_member_row", "hub_ready"):
        inp = config.load_yaml(config.UIGEN_DIR / "fixtures" / name / "inputs.yaml")
        assert schema.errors("inputs", inp) == []
        assert normalize._inputs_errors(inp) + normalize._screen_errors(inp) == []
        assert cppgen.validate_screen(inp["screen_id"], SCREENS[inp["screen_id"]]) == []
    assert cppgen.screen_base(SCREENS["HubReady"], MODULE) == {"class": "AstralActivatableWidget", "include": "UI/Foundation/AstralActivatableWidget.h"}


def test_menu_profile_has_input_rules_and_its_own_prompt_line():
    p = config.load_profile("menu")
    assert p["input_rules"] and p["analyze_note"] and spec_mod.input_rules("menu") and spec_mod.input_rules("cell") and not spec_mod.input_rules("hud")
    hud = config.load_profile("hud")
    assert {k: p["gates"][k] for k in hud["gates"]} == hud["gates"]                      # 값은 hud 와 같게 시작


def test_recorded_paths_are_repo_relative_and_old_absolute_ones_still_read():
    f = config.UIGEN_DIR / "fixtures" / "hub_ready" / "inputs.yaml"
    assert config.repo_rel(f) == "Tools/uigen/fixtures/hub_ready/inputs.yaml" == config.repo_rel(str(f).replace("/", "\\"))
    assert config.recorded_path("Tools/uigen/fixtures/hub_ready/inputs.yaml") == f
    assert config.recorded_path(f.as_posix()) == f                                        # 옛 절대 경로 — 지금도 있으면 그대로
    assert config.recorded_path("Q:/old/AstralBreak/Tools/uigen/fixtures/hub_ready/inputs.yaml") == f      # 없는 드라이브 → Tools/uigen/ 뒤로 다시
    assert config.repo_rel("C:/somewhere/else/x.png") == "C:/somewhere/else/x.png"


# ---------------------------------------------------------------------------------------------------------------------
# E2 뭉개짐 — 8 비트 반올림 안에서 같은 그림은 뭉개진 것이 아니다

def test_blur_needs_pixels_that_differ_beyond_rounding():
    import cv2
    rng = np.random.default_rng(3)
    noisy = np.full((60, 200, 3), 4.0) + rng.integers(0, 2, (60, 200, 1))                  # 어두운 평면의 1 단계 잡음 ↔ 반올림으로 사라진 렌더
    assert not dg.beyond_rounding(np.full((60, 200, 3), 4.0), noisy).any()
    pat = 20 + 8 * np.sign(np.sin(np.arange(200) * 1.2))[None, :, None] * np.ones((60, 1, 3))      # 낮은 대비 무늬가 진짜로 뭉개진 것은 그대로 걸린다
    assert dg.beyond_rounding(cv2.GaussianBlur(pat, (0, 0), 1.2), pat).mean() > 0.9


# ---------------------------------------------------------------------------------------------------------------------
# 쓰는 화면 목록 · 한 명령

def test_users_of_a_cell_and_cells_promoted_again(promoted):
    used = [{"cell": "HubMemberRow", "class": ROW_PKG, "run_id": "R20261125_000001_HubMemberRow", "widgets": ["Row1", "Row2"]}]
    promote_fake(promoted, "HubReady", screen_spec(), {}, None, "R20261125_000003_HubReady", cells_=used)
    u = cellref.users_of("HubMemberRow", promoted)
    assert [x["screen_id"] for x in u] == ["HubReady"] and u[0]["widgets"] == ["Row1", "Row2"] and cellref.users_of("ButtonSmall", promoted) == []
    assert cellref.changed(used, promoted) == []
    rec = json.loads((promoted / "HubMemberRow" / "promotion.json").read_text(encoding="utf-8"))
    (promoted / "HubMemberRow" / "promotion.json").write_text(json.dumps({**rec, "run_id": "R20261126_000000_HubMemberRow"}), encoding="utf-8")
    assert cellref.changed(used, promoted) == [{"cell": "HubMemberRow", "was": "R20261125_000001_HubMemberRow", "now": "R20261126_000000_HubMemberRow"}]


def fixture_folder(tmp_path, **over):
    fx = tmp_path / "fx" / "demo"
    fx.mkdir(parents=True)
    (fx / "inputs.yaml").write_text("screen_id: Demo\nconcept_text_ref: concept_text_ref.png\n", encoding="utf-8")
    (fx / "concept_prompt.md").write_text("p", encoding="utf-8")
    for k, v in over.items():
        (fx / k.replace("__", ".")).write_text(v, encoding="utf-8")
    return fx


def fake_tools(calls, fail_run=False):
    def concept(argv):
        calls.append(["concept", *argv])
        out = pathlib.Path(argv[argv.index("--out-dir") + 1])
        out.mkdir(parents=True, exist_ok=True)
        if "art" in argv:
            (out / "concept.png").write_bytes(f"art {out.name}".encode())
            (out / "concept.json").write_text("{}", encoding="utf-8")
        return 0

    def pipeline(argv):
        calls.append(["run", *argv])
        work = pathlib.Path(argv[argv.index("--work-root") + 1])
        rd = work / "R20261125_000009_Demo"
        rd.mkdir(parents=True)
        (rd / "compare.png").write_bytes(b"x")
        (rd / "report.json").write_text(json.dumps({"run_id": rd.name, "status": "fail" if fail_run else "pass", "gates": [{"name": "compile", "pass": True}], "attempts": [{}],
                                                    "recorded": {"diagnosis": {"summary": {"errors": 0, "approx": 1}}}}), encoding="utf-8")
        return 1 if fail_run else 0
    return concept, pipeline


def test_make_screen_stops_for_a_person_to_pick(tmp_path, capsys):
    fx, work, calls = fixture_folder(tmp_path), tmp_path / "work", []
    c, p = fake_tools(calls)
    assert make_screen.main([str(fx), "--candidates", "2", "--work-root", str(work)], concept_main=c, pipeline_main=p) == make_screen.EXIT_PICK
    assert [x[0] for x in calls] == ["concept", "concept"] and not (fx / "concept.png").exists()           # 고르기 전에는 아무것도 안 정한다
    assert all("--only" in x and "art" in x for x in calls) and "--pick <1, 2>" in capsys.readouterr().out
    assert make_screen.main([str(fx), "--candidates", "1", "--work-root", str(work)], concept_main=c, pipeline_main=p) == make_screen.EXIT_PICK
    assert (work / "_candidates" / "demo" / "3" / "concept.png").is_file()                                 # 예전 후보는 그대로


def test_make_screen_pick_draws_the_text_reference_and_runs(tmp_path, capsys):
    fx, work, calls = fixture_folder(tmp_path, text_ref_layout__yaml="texts: []"), tmp_path / "work", []
    c, p = fake_tools(calls)
    make_screen.main([str(fx), "--work-root", str(work)], concept_main=c, pipeline_main=p)
    calls.clear()
    assert make_screen.main([str(fx), "--pick", "2", "--work-root", str(work)], concept_main=c, pipeline_main=p) == 0
    assert (fx / "concept.png").read_bytes() == b"art 2"
    assert [x[0] for x in calls] == ["concept", "run"] and "--draw" in calls[0] and "text_ref" in calls[0]
    s = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert s["status"] == "pass" and s["errors"] == 0 and s["approx"] == 1 and s["eye_check"].startswith("not yet") and s["compare"].endswith("compare.png")
    assert make_screen.main([str(fx), "--pick", "1", "--work-root", str(work)], concept_main=c, pipeline_main=p) == make_screen.EXIT_FAIL      # 있는 그림을 말없이 안 바꾼다
    assert (fx / "concept.png").read_bytes() == b"art 2"
    assert make_screen.main([str(fx), "--pick", "9", "--replace", "--work-root", str(work)], concept_main=c, pipeline_main=p) == make_screen.EXIT_FAIL


def test_make_screen_current_needs_a_concept(tmp_path):
    fx, work, calls = fixture_folder(tmp_path), tmp_path / "work", []
    c, p = fake_tools(calls, fail_run=True)
    assert make_screen.main([str(fx), "--pick", "current", "--work-root", str(work)], concept_main=c, pipeline_main=p) == make_screen.EXIT_FAIL and calls == []
    (fx / "concept.png").write_bytes(b"mine")
    assert make_screen.main([str(fx), "--pick", "current", "--work-root", str(work)], concept_main=c, pipeline_main=p) == 1                  # run 의 종료 코드 그대로
    assert [x[0] for x in calls] == ["concept", "run"] and (fx / "concept.png").read_bytes() == b"mine" and "--force" in calls[0]
    (fx / "concept_text_ref.png").write_bytes(b"ref")                                       # codex 참고판이 있고 그림이 그대로 — 다시 안 만든다
    calls.clear()
    import shutil
    shutil.rmtree(work)
    make_screen.main([str(fx), "--pick", "current", "--work-root", str(work)], concept_main=c, pipeline_main=p)
    assert [x[0] for x in calls] == ["run"]
    assert make_screen.main([str(tmp_path / "nope")], concept_main=c, pipeline_main=p) == make_screen.EXIT_FAIL


def test_placed_cell_shows_its_start_state(promoted):
    """시작 때 접힌 위젯은 놓인 칸의 그림에 없다(force_visible 은 칸 속까지 안 들어간다)."""
    sp = row_spec()
    sp["widgets"].append({"id": "Mark", "type": "Image", "parent": "Root", "slot": {"kind": "canvas", "z": 1}, "style": {"brush": {"asset": "mark"}}, "visibility": "collapsed"})
    mark = np.zeros((ROW[1], ROW[0], 4))
    mark[10:20, 10:20] = (255, 255, 255, 255)
    root = promoted.parent / "p2"
    promote_fake(root, "HubMemberRow", sp, {"band": band_px(), "mark": mark}, None)
    off = cells.picture(ROW_PKG, root)["states"]["normal_base"]
    assert off[15, 15, 0] < 60
    sp["widgets"][-1]["visibility"] = "visible"
    root = promoted.parent / "p3"
    promote_fake(root, "HubMemberRow", sp, {"band": band_px(), "mark": mark}, None)
    assert cells.picture(ROW_PKG, root)["states"]["normal_base"][15, 15, 0] > 200


def test_prompt_lists_cells_as_reserved_places(tmp_path, promoted):
    run = types.SimpleNamespace(run_id="R", path=lambda *a: tmp_path.joinpath(*a), read_json=lambda n: json.loads((tmp_path / n).read_text(encoding="utf-8")))
    b = brief_of(promoted, screen_id="HubReady", text="t", style_keywords=[])
    p = analyze.build_prompt(run, b, CFG)
    assert "Row1: HubMemberRow at [20, 80, 200, 40]" in p and "make no widget" in p and "interactive menu" in p and "HUD is not UI" not in p
    assert "- Row1: UserWidget" not in p                                                    # 계약 줄에는 없다(파이프라인이 넣는다)
    hud = {**b, "screen_type": "hud", "cells": [], "dynamic_data": []}
    assert "the scene behind the HUD is not UI" in analyze.build_prompt(run, hud, CFG)
    cell = analyze.build_prompt(run, {**hud, "screen_type": "cell"}, CFG)
    assert "nothing off-screen at 640×360." in cell
