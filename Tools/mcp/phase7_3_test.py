"""Phase 7-3 — 몽타주 슬롯·섹션 · 최소형 몽타주 생성 · 스켈레톤 슬롯 등록 · AimOffset 생성 · 몽타주 스모크.

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase7_3_test.py [--recheck]

새 Tool 4개(create_anim_montage · set_montage_slots · set_montage_sections · add_skeleton_slot)는 세션 재시작 전 MCP 에 보이지 않으므로
HTTP 직접 호출로 검증한다. 대상(생성·덮어쓰기): /Game/Animation/Test/AM_McpTest · AO_McpTest · AO_McpTest1D.
스켈레톤 SKEL_UE5_F 에는 UpperBody 슬롯을 (없으면) 등록·저장하고, McpTestSlot/McpTestGroup 은 저장하지 않는다(재시작 뒤 사라져야 함).
검사 항목:
  A. 스켈레톤 슬롯 — UpperBody 등록(멱등) · 임시 슬롯/그룹 생성·이동 · 거부 6종 · info.skeleton_slot_groups
  B. 몽타주 생성 — AS_Hero_Attack1 → AM_McpTest(slot UpperBody, blend) · 거부 6종(ASSET_EXISTS · 없는 애니 · BlendSpace · 미등록 슬롯 · 음수 blend · 보호 애셋)
  C. 슬롯 — 이름 변경 양방향 · 문자열 축약형 · 멱등 · 거부 5종 · 거부 뒤 불변
  D. 섹션 — 3섹션 체인+루프 · 멱등 · 정렬 · 거부 6종 · 0 미시작 경고 · 거부 뒤 불변
  E. 저장 · list details(montage · additive_type) · 몽타주 스모크(passed, 미사용 슬롯 경고)
  F. AimOffset — aim_offset=true 2D(AO_Rifle 9샘플; 재료가 MeshSpace additive 일 때) · 1D 빈 AimOffset · ADDITIVE_TYPE 거부
  R. --recheck — 임시 슬롯 사라짐 · UpperBody 유지 · 몽타주/AimOffset 요약 동일 · 스모크 passed
"""
from __future__ import annotations

import json
import sys
import time

from anim_graph_mcp import bridge

SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
# 프로젝트에는 같은 이름의 스켈레톤이 둘 있다(2026-10-17 실측): ABP_Hero_Base · AS_Hero_Finisher1 · AS_Hero_Jump 는 /Game/Assets/… 쪽,
# AS_Hero_Attack1~3 · AO_Rifle* · AM_Hero_Attack1~3 은 /Game/IdaFaber/… 쪽. 몽타주는 소스 시퀀스의 스켈레톤을 따르므로 소스를 Assets 쪽으로 고른다
SKELETON_AO = "/Game/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PROD_ABP = "/Game/Animation/Hero/ABP_Hero_Base"
SEQ = "/Game/Animation/Hero/Anims/Combat/AS_Hero_Finisher1"
IDLE = "/Game/Assets/IdaFaber/Demo/Animations/Girl/AS_Idle"
BS_PROD = "/Game/Animation/Hero/Anims/Locomotions/BS_Hero_Locomotion1D"
PROTECTED = "/Game/Assets/IdaFaber/Demo/Animations/Girl/AS_Idle"
AO_DIR = "/Game/Animation/Hero/Anims/Locomotions"
AM = "/Game/Animation/Test/AM_McpTest"
AO = "/Game/Animation/Test/AO_McpTest"
AO1D = "/Game/Animation/Test/AO_McpTest1D"
UPPER = "UpperBody"
JUNK_SLOT = "McpTestSlot"
JUNK_GROUP = "McpTestGroup"
STATE_FILE = "Tools/mcp/phase7_3_state.json"
NEW_TOOLS = {"create_anim_montage", "set_montage_slots", "set_montage_sections", "add_skeleton_slot"}
FAILS: list[str] = []

# AimOffset 샘플 — 이름 꼬리 [L|C|R][U|C|D] → (yaw, pitch)
AO_SAMPLES = {f"{AO_DIR}/AS_Hero_AO_Rifle{h}{v}": [yaw, pitch]
              for h, yaw in (("L", -90), ("C", 0), ("R", 90)) for v, pitch in (("U", 90), ("C", 0), ("D", -90))}


def check(cond: bool, msg: str) -> bool:
    print(("[ ok ] " if cond else "[FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)
    return cond


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:2000]}")
        sys.exit(1)
    for d in env.get("diagnostics", []):
        print(f"   diag[{d['level']}] {d['code']}: {d['message'][:160]}")
    return env["result"]


def code(env: dict) -> str:
    return env.get("error", {}).get("code", "") if not env.get("ok") else "OK"


def reason(env: dict) -> str:
    return (env.get("error", {}).get("details", {}) or {}).get("reason", "")


def diag_codes(env: dict) -> set[str]:
    return {d.get("code") for d in env.get("diagnostics", [])}


def call(tool: str, **params) -> dict:
    return bridge.call(tool, params, timeout=bridge.COMPILE_TIMEOUT)


def info(path: str) -> dict:
    return must(call("get_anim_blueprint_info", asset_path=path), "info")


def slot_groups(path: str = PROD_ABP) -> dict[str, list[str]]:
    return {g["group"]: g["slots"] for g in info(path)["skeleton_slot_groups"]}


def group_of(slot: str, groups: dict[str, list[str]]) -> str | None:
    return next((g for g, slots in groups.items() if slot in slots), None)


def list_details(cls: str, folder: str) -> list[dict]:
    return must(call("list_animation_assets", **{"class": cls, "path_prefix": folder, "details": True, "limit": 100}), f"list {cls} {folder}")["assets"]


def montage(path: str = AM) -> dict | None:
    for a in list_details("AnimMontage", path.rsplit("/", 1)[0]):
        if a["asset_path"].startswith(path + "."):
            return a.get("montage")
    return None


def blendspace(path: str) -> dict | None:
    for a in list_details("BlendSpace", path.rsplit("/", 1)[0]):
        if a["asset_path"].startswith(path + "."):
            return a.get("blendspace")
    return None


def shape(m: dict) -> dict:
    """비교용 — 슬롯 이름·세그먼트 · 섹션(이름·시작·next) · 길이·블렌드"""
    return {
        "slots": [(s["name"], [(g["animation"], round(g["start"], 4), round(g["length"], 4)) for g in s["segments"]]) for s in m["slots"]],
        "sections": [(s["name"], round(s["start"], 4), s["next"]) for s in m["sections"]],
        "length": round(m["length"], 4), "blend_in": round(m["blend_in"], 4), "blend_out": round(m["blend_out"], 4),
    }


def bs_shape(d: dict) -> dict:
    return {"class": d["class"], "aim_offset": d["aim_offset"], "dimensions": d["dimensions"],
            "axes": [(a["name"], a["min"], a["max"], a["grid"]) for a in d["axes"]],
            "samples": sorted((s["animation"], tuple(round(v, 4) for v in s["value"])) for s in d["samples"]),
            "sample_count": d["sample_count"]}


def jsonic(x):
    """비교용 — JSON 왕복(튜플 → 리스트)으로 state 파일과 같은 모양으로"""
    return json.loads(json.dumps(x))


def wait_job(job: dict, timeout: float = 300.0) -> dict:
    deadline = time.time() + timeout
    while not job.get("done") and time.time() < deadline:
        time.sleep(1.0)
        job = must(bridge.call("poll_automation_tests", {"job_id": job["job_id"]}), "poll")
    return job


def smoke_montage() -> dict:
    return wait_job(must(call("run_automation_tests", filter="AnimGraphMcp.Smoke.AnimMontage"), "smoke montage"))


def main_sections() -> None:
    print("=== A. 스켈레톤 슬롯 ===")
    st = must(bridge.call("get_editor_status"), "status")
    names = {t["name"] for t in st["tools"]}
    check(NEW_TOOLS <= names, f"Tool 4개 등록 (총 {len(names)})")
    groups0 = slot_groups()
    upper_before = group_of(UPPER, groups0)
    print(f"   skeleton_slot_groups: {groups0} · UpperBody 기존 그룹 = {upper_before}")
    r = call("add_skeleton_slot", skeleton=SKELETON, slot=UPPER, confirm=True, save=upper_before is None)
    a = must(r, "add UpperBody")
    check(a["group"] == "DefaultGroup" and a["added"] == (upper_before is None) and UPPER in dict((g["group"], g["slots"]) for g in a["slot_groups"])["DefaultGroup"], f"UpperBody → DefaultGroup (added={a['added']}, saved={a['saved']})")
    a2 = must(call("add_skeleton_slot", skeleton=SKELETON, slot=UPPER, confirm=True), "add UpperBody again")
    check(a2["unchanged"] is True and a2["added"] is False and a2["moved_from"] is None, "재등록 → unchanged")
    # 같은 에디터에서 두 번 돌리면 임시 슬롯이 메모리에 남아 있다(저장은 안 함) → 기대값은 시작 상태 기준
    junk_before, junk_group_before = group_of(JUNK_SLOT, groups0), JUNK_GROUP in groups0
    j = must(call("add_skeleton_slot", skeleton=SKELETON, slot=JUNK_SLOT, group=JUNK_GROUP, confirm=True), "add junk")
    check(j["added"] is (junk_before is None) and j["group_created"] is (not junk_group_before) and j["group"] == JUNK_GROUP and j["saved"] is False, f"임시 슬롯 {JUNK_SLOT} → 새 그룹 {JUNK_GROUP} (저장 안 함; added={j['added']}, group_created={j['group_created']})")
    mv = must(call("add_skeleton_slot", skeleton=SKELETON, slot=JUNK_SLOT, confirm=True), "move junk")
    check(mv["moved_from"] == JUNK_GROUP and mv["group"] == "DefaultGroup" and mv["unchanged"] is False, f"그룹 이동 → moved_from {mv['moved_from']}")
    r = call("add_skeleton_slot", skeleton=SKELETON, slot=JUNK_SLOT); check(code(r) == "BAD_REQUEST" and "confirm" in r["error"]["message"], "confirm 없음 → BAD_REQUEST")
    r = call("add_skeleton_slot", skeleton=SKELETON, slot=JUNK_GROUP, confirm=True); check(reason(r) == "SLOT_IS_GROUP", f"그룹 이름을 슬롯으로 → SLOT_IS_GROUP ({reason(r)})")
    r = call("add_skeleton_slot", skeleton=SKELETON, slot="McpOther", group=JUNK_SLOT, confirm=True); check(reason(r) == "GROUP_IS_SLOT", f"슬롯 이름을 그룹으로 → GROUP_IS_SLOT ({reason(r)})")
    r = call("add_skeleton_slot", skeleton=SKELETON, slot="  ", confirm=True); check(reason(r) == "EMPTY_NAME", f"빈 이름 → EMPTY_NAME ({reason(r)})")
    r = call("add_skeleton_slot", skeleton="/Game/Nope/SKEL_X", slot="A", confirm=True); check(code(r) == "ASSET_NOT_FOUND", f"없는 스켈레톤 → ASSET_NOT_FOUND ({code(r)})")
    r = call("add_skeleton_slot", skeleton=BS_PROD, slot="A", confirm=True); check(code(r) == "BAD_REQUEST", f"BlendSpace 를 스켈레톤으로 → BAD_REQUEST ({code(r)})")
    groups1 = slot_groups()
    check(group_of(UPPER, groups1) == "DefaultGroup" and group_of(JUNK_SLOT, groups1) == "DefaultGroup" and JUNK_GROUP in groups1, "info.skeleton_slot_groups 반영")

    print("\n=== B. 몽타주 생성 ===")
    c = must(call("create_anim_montage", asset_path=AM, animation=SEQ, slot=UPPER, blend_in=0.1, blend_out=0.2, overwrite=True), "create montage")
    check(c["created"] and c["class"] == "AnimMontage" and c["skeleton"].startswith(SKELETON), f"AM_McpTest 생성 ({c['class']}, length {c['length']:.3f})")
    check(len(c["slots"]) == 1 and c["slots"][0]["name"] == UPPER and c["slots"][0]["in_skeleton"] and len(c["slots"][0]["segments"]) == 1 and c["slots"][0]["segments"][0]["animation"].startswith(SEQ), f"슬롯 1 (UpperBody) · 세그먼트 1 ({c['slots'][0]['segments'][0]['animation']})")
    check([(s["name"], s["start"], s["next"]) for s in c["sections"]] == [("Default", 0.0, None)], f"섹션 Default@0 ({c['sections']})")
    check(abs(c["blend_in"] - 0.1) < 1e-4 and abs(c["blend_out"] - 0.2) < 1e-4 and c["length"] > 0.5, f"blend_in/out {c['blend_in']}/{c['blend_out']} · length {c['length']:.3f}")
    length = c["length"]
    r = call("create_anim_montage", asset_path=AM, animation=SEQ); check(code(r) == "ASSET_EXISTS", f"overwrite 없이 재생성 → ASSET_EXISTS ({code(r)})")
    r = call("create_anim_montage", asset_path=AM, animation="/Game/Nope/AS_X", overwrite=True); check(code(r) == "ASSET_NOT_FOUND", f"없는 애니 → ASSET_NOT_FOUND ({code(r)})")
    r = call("create_anim_montage", asset_path=AM, animation=BS_PROD, overwrite=True); check(code(r) == "BAD_REQUEST", f"BlendSpace 를 소스로 → BAD_REQUEST ({code(r)})")
    r = call("create_anim_montage", asset_path=AM, animation=SEQ, slot="NopeSlot", overwrite=True); check(reason(r) == "SLOT_NOT_IN_SKELETON", f"미등록 슬롯 → SLOT_NOT_IN_SKELETON ({reason(r)})")
    r = call("create_anim_montage", asset_path=AM, animation=SEQ, blend_in=-1, overwrite=True); check(code(r) == "BAD_REQUEST", f"음수 blend_in → BAD_REQUEST ({code(r)})")
    r = call("create_anim_montage", asset_path=PROTECTED, animation=SEQ, overwrite=True); check(code(r) == "ASSET_PROTECTED", f"보호 애셋 overwrite → ASSET_PROTECTED ({code(r)})")
    check(shape(montage()) == shape(c), "거부 뒤 몽타주 불변 (list details)")

    print("\n=== C. 슬롯 ===")
    s = must(call("set_montage_slots", asset_path=AM, slots=[{"index": 0, "slot": "DefaultSlot"}]), "slot → DefaultSlot")
    check(s["changed"] == 1 and s["slots"][0]["name"] == "DefaultSlot" and s["dirty"] is True, "UpperBody → DefaultSlot (changed 1)")
    s = must(call("set_montage_slots", asset_path=AM, slots=[UPPER]), "slot → UpperBody (string)")
    check(s["changed"] == 1 and s["slots"][0]["name"] == UPPER and s["slots"][0]["group"] == "DefaultGroup", "문자열 축약형 → UpperBody (changed 1)")
    s = must(call("set_montage_slots", asset_path=AM, slots=[UPPER]), "slot same")
    check(s["unchanged"] is True and s["changed"] == 0, "같은 이름 → unchanged")
    r = call("set_montage_slots", asset_path=AM, slots=["NopeSlot"]); check(reason(r) == "SLOT_NOT_IN_SKELETON" and isinstance((r["error"]["details"] or {}).get("slot_groups"), list), f"미등록 슬롯 → SLOT_NOT_IN_SKELETON + slot_groups ({reason(r)})")
    r = call("set_montage_slots", asset_path=AM, slots=[{"index": 5, "slot": UPPER}]); check(reason(r) == "SLOT_INDEX", f"index 범위 밖 → SLOT_INDEX ({reason(r)})")
    r = call("set_montage_slots", asset_path=AM, slots=[{"index": 0, "slot": UPPER}, {"index": 0, "slot": "DefaultSlot"}]); check(reason(r) == "DUPLICATE_INDEX", f"같은 index 두 번 → DUPLICATE_INDEX ({reason(r)})")
    r = call("set_montage_slots", asset_path=AM, slots=[]); check(code(r) == "BAD_REQUEST", f"빈 배열 → BAD_REQUEST ({code(r)})")
    r = call("set_montage_slots", asset_path=AM, slots=[""]); check(reason(r) == "EMPTY_NAME", f"빈 이름 → EMPTY_NAME ({reason(r)})")
    r = call("set_montage_slots", asset_path=PROD_ABP, slots=[UPPER]); check(code(r) == "BAD_REQUEST", f"ABP 를 몽타주로 → BAD_REQUEST ({code(r)})")
    check(montage()["slots"][0]["name"] == UPPER, "거부 뒤 슬롯 불변")

    print("\n=== D. 섹션 ===")
    spec = [{"name": "Start", "start": 0.0, "next": "Loop"}, {"name": "Loop", "start": round(length * 0.4, 3), "next": "Loop"}, {"name": "End", "start": round(length * 0.8, 3)}]
    d = must(call("set_montage_sections", asset_path=AM, sections=spec), "sections")
    got = [(s["name"], round(s["start"], 3), s["next"]) for s in d["sections"]]
    check(got == [("Start", 0.0, "Loop"), ("Loop", spec[1]["start"], "Loop"), ("End", spec[2]["start"], None)] and d["unchanged"] is False, f"섹션 3 (체인 Start→Loop, Loop 루프, End 정지): {got}")
    check(abs(d["sections"][0]["length"] - spec[1]["start"]) < 1e-3 and abs(sum(s["length"] for s in d["sections"]) - length) < 1e-3, f"섹션 길이 합 = 몽타주 길이 ({[round(s['length'], 3) for s in d['sections']]})")
    d2 = must(call("set_montage_sections", asset_path=AM, sections=spec), "sections again")
    check(d2["unchanged"] is True and d2["dirty"] is False, "같은 스펙 재적용 → unchanged")
    d3 = must(call("set_montage_sections", asset_path=AM, sections=[spec[2], spec[0], spec[1]]), "sections unsorted")
    check(d3["unchanged"] is True, "순서만 다른 스펙 → 정렬 뒤 unchanged")
    r = call("set_montage_sections", asset_path=AM, sections=[spec[0], {"name": "Start", "start": 0.2}]); check(reason(r) == "DUPLICATE_SECTION", f"중복 이름 → DUPLICATE_SECTION ({reason(r)})")
    r = call("set_montage_sections", asset_path=AM, sections=[{"name": "A", "start": length + 1}]); check(reason(r) == "SECTION_OUT_OF_RANGE", f"길이 밖 → SECTION_OUT_OF_RANGE ({reason(r)})")
    r = call("set_montage_sections", asset_path=AM, sections=[{"name": "A", "start": 0, "next": "Nope"}]); check(reason(r) == "NEXT_NOT_FOUND", f"없는 next → NEXT_NOT_FOUND ({reason(r)})")
    r = call("set_montage_sections", asset_path=AM, sections=[]); check(reason(r) == "NO_SECTIONS", f"빈 배열 → NO_SECTIONS ({reason(r)})")
    r = call("set_montage_sections", asset_path=AM, sections=[{"name": "", "start": 0}]); check(reason(r) == "EMPTY_NAME", f"빈 이름 → EMPTY_NAME ({reason(r)})")
    r = call("set_montage_sections", asset_path=AM, sections=[{"name": "A", "start": 0, "next": 5}]); check(code(r) == "BAD_REQUEST", f"next 가 숫자 → BAD_REQUEST ({code(r)})")
    check([(s["name"], round(s["start"], 3), s["next"]) for s in montage()["sections"]] == got, "거부 뒤 섹션 불변")
    r = call("set_montage_sections", asset_path=AM, sections=[{"name": "Late", "start": 0.2}])
    check(r.get("ok") and "NO_SECTION_AT_ZERO" in diag_codes(r), f"0 에서 시작하지 않는 첫 섹션 → 적용 + NO_SECTION_AT_ZERO 경고 ({diag_codes(r)})")
    must(call("set_montage_sections", asset_path=AM, sections=spec), "restore sections")

    print("\n=== E. 저장 · 조회 · 스모크 ===")
    e = must(call("set_montage_sections", asset_path=AM, sections=spec, save=True), "save")
    check(e["saved"] is True and e["unchanged"] is True, "저장 (unchanged 여도 강제 저장)")
    m = montage()
    check(m is not None and shape(m) == shape(e) and m["notify_count"] == 0 and UPPER in dict((g["group"], g["slots"]) for g in m["skeleton_slot_groups"])["DefaultGroup"], "list details → montage 요약 일치")
    seqs = {a["asset_path"].split(".")[0]: a for a in list_details("AnimSequence", AO_DIR)}
    ao_types = {p: seqs.get(p, {}).get("additive_type") for p in AO_SAMPLES}
    ao_valid = {p for p in AO_SAMPLES if seqs.get(p, {}).get("additive_valid")}
    check(all(ao_types.values()) and all("ref_pose_type" in seqs[p] for p in AO_SAMPLES), f"AnimSequence additive_type/additive_valid 노출: {sorted(set(ao_types.values()))} · valid {len(ao_valid)}/9")
    for p in sorted(set(AO_SAMPLES) - ao_valid):
        print(f"   invalid additive: {p.split('/')[-1]} ref_pose_type={seqs[p].get('ref_pose_type')} ref_pose_sequence={seqs[p].get('ref_pose_sequence')}")
    j = smoke_montage()
    mine = [t for t in j["tests"] if t["name"].endswith("AM_McpTest")]
    check(j["done"] and j["ok"] and j["total"] >= 1 and mine and mine[0]["state"] == "passed", f"몽타주 스모크 {j['passed']}/{j['total']} passed · AM_McpTest passed (warnings {mine[0]['warnings'][:1] if mine else None})")
    for t in j["tests"]:
        if t["warnings"]:
            print(f"   warn {t['name'].split('.')[-1]}: {t['warnings'][0][:120]}")
    must(call("set_montage_slots", asset_path=AM, slots=[JUNK_SLOT]), "slot → junk (in-memory)")
    j2 = smoke_montage()
    mine2 = [t for t in j2["tests"] if t["name"].endswith("AM_McpTest")]
    check(mine2 and mine2[0]["state"] == "passed" and any("No Slot node" in w for w in mine2[0]["warnings"]), f"Slot 노드 없는 슬롯 → passed + 경고 ({mine2[0]['warnings'][:1] if mine2 else None})")
    must(call("set_montage_slots", asset_path=AM, slots=[UPPER], save=True), "restore slot + save")

    print("\n=== F. AimOffset ===")
    mesh_space = all(t == "AAT_RotationOffsetMeshSpace" for t in ao_types.values())
    axes = [{"name": "Yaw", "min": -90, "max": 90, "grid": 4}, {"name": "Pitch", "min": -90, "max": 90, "grid": 4}]
    ao_saved = None
    if mesh_space and len(ao_valid) >= 3:
        # (실측 2026-10-17) 기준 포즈가 없는 additive 시퀀스는 엔진이 그 다음 샘플부터 거부한다 → 유효한 것만 샘플로
        f = must(call("create_blendspace", asset_path=AO, skeleton=SKELETON_AO, dimensions=2, axes=axes, aim_offset=True,
                      samples=[{"animation": p, "value": v} for p, v in AO_SAMPLES.items() if p in ao_valid], overwrite=True, save=True), "create aim offset")
        check(f["class"] == "AimOffsetBlendSpace" and f["aim_offset"] is True and f["sample_count"] == len(ao_valid) and f["saved"], f"AO_McpTest 2D 생성 ({f['class']}, 샘플 {f['sample_count']}/{len(ao_valid)})")
        ao_saved = bs_shape(blendspace(AO))
        check(ao_saved == bs_shape(f), "list details → 요약 일치")
    else:
        print(f"   (스킵) AO_Rifle 샘플이 MeshSpace additive 가 아니거나 유효 샘플 부족: {ao_types} valid={len(ao_valid)}")
    invalid = sorted(set(AO_SAMPLES) - ao_valid)
    if invalid:
        r = call("create_blendspace", asset_path="/Game/Animation/Test/AO_McpNope", skeleton=SKELETON_AO, dimensions=2, axes=axes, aim_offset=True, samples=[{"animation": invalid[0], "value": [0, 0]}])
        check(reason(r) == "ADDITIVE_INVALID", f"기준 포즈 없는 additive 샘플 → ADDITIVE_INVALID ({reason(r)})")
    f1 = must(call("create_blendspace", asset_path=AO1D, skeleton=SKELETON, dimensions=1, axes=[{"name": "Pitch", "min": -90, "max": 90}], aim_offset=True, overwrite=True, save=True), "create aim offset 1D")
    check(f1["class"] == "AimOffsetBlendSpace1D" and f1["aim_offset"] is True and f1["sample_count"] == 0, f"AO_McpTest1D 빈 생성 ({f1['class']})")
    r = call("create_blendspace", asset_path="/Game/Animation/Test/AO_McpNope", skeleton=SKELETON, dimensions=1, axes=[{"name": "Pitch", "min": -90, "max": 90}], aim_offset=True, samples=[{"animation": IDLE, "value": [0]}])
    check(reason(r) == "ADDITIVE_TYPE", f"비-additive 샘플 → ADDITIVE_TYPE ({reason(r)})")
    check(blendspace("/Game/Animation/Test/AO_McpNope") is None, "거부된 AimOffset 은 생성되지 않음")
    plain = blendspace("/Game/Animation/Test/BS_McpTest")  # 6-3 이 만든 애셋 — 덮어쓰지 않고 조회만 (6-3 recheck 가 비교한다)
    check(plain is None or (plain["aim_offset"] is False and plain["class"] == "BlendSpace1D"), f"일반 BlendSpace 는 aim_offset=false 로 조회 ({plain and plain['class']})")

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"montage": shape(m), "ao": ao_saved, "ao1d": bs_shape(blendspace(AO1D)), "upper_before": upper_before, "smoke_total": j["total"]}, f, indent=1, ensure_ascii=False)
    print(f"saved → {STATE_FILE}")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재조회 ===")
    with open(STATE_FILE, encoding="utf-8") as f:
        saved = json.load(f)
    groups = slot_groups()
    check(group_of(UPPER, groups) == "DefaultGroup", "UpperBody 슬롯 유지 (저장됨)")
    check(group_of(JUNK_SLOT, groups) is None and JUNK_GROUP not in groups, f"임시 슬롯·그룹 사라짐 (저장 안 함): {sorted(groups)}")
    m = montage()
    check(m is not None and jsonic(shape(m)) == saved["montage"], f"AM_McpTest 슬롯·섹션 동일 ({[s['name'] for s in m['slots']] if m else None} · {[s['name'] for s in m['sections']] if m else None})")
    if saved.get("ao"):
        check(jsonic(bs_shape(blendspace(AO))) == saved["ao"], "AO_McpTest 요약 동일")
    check(jsonic(bs_shape(blendspace(AO1D))) == saved["ao1d"], "AO_McpTest1D 요약 동일")
    j = smoke_montage()
    mine = [t for t in j["tests"] if t["name"].endswith("AM_McpTest")]
    check(j["ok"] and j["total"] == saved["smoke_total"] and mine and mine[0]["state"] == "passed" and not mine[0]["warnings"], f"몽타주 스모크 {j['passed']}/{j['total']} passed · AM_McpTest 경고 없음")


def main() -> int:
    status = must(bridge.call("get_editor_status"), "status")
    print(f"tools: {len(status['tools'])}")
    if "--recheck" in sys.argv:
        recheck()
    else:
        main_sections()
    print("\n" + ("PASS" if not FAILS else f"FAIL ({len(FAILS)}):\n  - " + "\n  - ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
