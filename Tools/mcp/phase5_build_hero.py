"""Phase 5 — 히어로 AnimBP 를 도구만으로 처음부터 구성한다 (2026-10-16 사용자 확정: 새 ABP 재구성 · BlendSpace 재사용 · UpperBody 슬롯 신설).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phase5_build_hero.py [--overwrite] [--recheck] [--diff-only]

산출: /Game/Animation/Hero/ABP_Hero_McpBuild (저장) · Tools/mcp/phase5_build_state.json · .claude/plans/animbp-phase5-hero-diff.md (운영 애셋과 비교)
운영 애셋 /Game/Animation/Hero/ABP_Hero_Base 는 읽기(비교)만 한다.

구성 (운영 애셋 덤프 2026-10-16 기준, 수치는 거기서 가져옴):
  루트   SM → Slot DefaultSlot(전신) → SaveCachedPose "FullBody" → UseCachedPose ×2
         → (BasePose) / (→ Slot UpperBody → BlendPoses_0) → LayeredBoneBlend(spine_01) → Inertialization → Output
         ※ 상체 슬롯은 반드시 전신 슬롯 **뒤**에. 나란히 두면 UpperBody 슬롯이 비어 있을 때 로코모션 상체가 전신 몽타주 상체를 덮는다 (2026-10-16 PIE 에서 실측된 실수)
  SM     `Locomotions` — 상태 5(Idle · Move · JumpStart · FallLoop · FallLand) · conduit 2(JumpSelector · EndInAir) · alias 4(JumpSources · JumpFallInterruptSources · IdleAlias · MoveAlias)
         · 전이 12, Entry=Idle — 운영 애셋과 1:1 (Phase 6-1 부터; 그 전엔 alias/conduit 없이 직접 전이로 단순화했었다)
  상태   Idle=AS_Idle · Move=BS_Hero_Locomotion1D(X←Speed) · JumpStart=AS_Hero_Jump · FallLoop=AS_Hero_FallLoop · FallLand=AS_Hero_Land
         상태 생성·내부 채우기·conduit·alias·전이·이름 변경이 **배치 하나** (graph:{ref} · result_of · rename_node)
"""
from __future__ import annotations

import json
import pathlib
import sys

from anim_graph_mcp import bridge

BUILD = "/Game/Animation/Hero/ABP_Hero_McpBuild"
PROD = "/Game/Animation/Hero/ABP_Hero_Base"
SKELETON = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
PARENT = "/Script/AstralBreak.AstralAnimInstance"
STATE_FILE = pathlib.Path("Tools/mcp/phase5_build_state.json")
DIFF_FILE = pathlib.Path(".claude/plans/animbp-phase5-hero-diff.md")

ASSETS = {
    "idle": "/Game/Assets/IdaFaber/Demo/Animations/Girl/AS_Idle",
    "bs": "/Game/Animation/Hero/Anims/Locomotions/BS_Hero_Locomotion1D",
    "jump": "/Game/Animation/Hero/Anims/Locomotions/AS_Hero_Jump",
    "fall": "/Game/Animation/Hero/Anims/Locomotions/AS_Hero_FallLoop",
    "land": "/Game/Animation/Hero/Anims/Locomotions/AS_Hero_Land",
}
# 운영 애셋 전이 규칙의 리터럴 (덤프에서 읽음)
SPEED_STOP = 10.0      # Move → Idle: !bHasMovementInput && Speed < 10
SPEED_MOVE = 20.0      # 착지 뒤 Idle/Move 분기: Speed >= 20
GROUND_LAND = 25.0     # FallLoop → FallLand: GroundDistance < 25
UPPER_BODY_BONE = "spine_01"
UPPER_BODY_SLOT = "UpperBody"
FULL_BODY_SLOT = "DefaultSlot"

FAILS: list[str] = []


def check(cond: bool, msg: str) -> bool:
    print(("[ ok ] " if cond else "[FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)
    return cond


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:1500]}")
        sys.exit(1)
    for d in env.get("diagnostics", []):
        print(f"   diag[{d['level']}] {d['code']}: {d['message']}")
    return env["result"]


def structure(asset: str, depth: int = -1) -> dict:
    return must(bridge.call("get_anim_graph_structure", {"asset_path": asset, "depth": depth}, timeout=bridge.COMPILE_TIMEOUT), f"structure {asset}")


def apply(ops: list, expected: str, what: str, compile: bool = False) -> dict:
    pv = bridge.call("preview_graph_operations", {"asset_path": BUILD, "operations": ops})
    if not (pv.get("ok") and pv["result"]["valid"]):
        print(f"[FAIL] preview {what}:\n" + json.dumps(pv, ensure_ascii=False, indent=1)[:4000])
        sys.exit(1)
    r = bridge.call("apply_graph_operations", {"asset_path": BUILD, "operations": ops, "expected_revision": expected, "compile": compile},
                    timeout=bridge.COMPILE_TIMEOUT)
    if not r.get("ok"):
        print(f"[FAIL] apply {what}:\n" + json.dumps(r, ensure_ascii=False, indent=1)[:5000])
        sys.exit(1)
    res = r["result"]
    print(f"   {what}: applied={res['applied']} revision={res['revision_after']}")
    if compile:
        for m in res["compile"].get("messages", []):
            print(f"   compile[{m['level']}] {m['text']}")
        check(res["compile"].get("num_errors") == 0, f"{what} 컴파일 0 에러 (warnings={res['compile'].get('num_warnings')})")
    return res


# ----------------------------------------------------------------------------------------------------------------------
# 규칙 (AST)
def var(n: str) -> dict:
    return {"var": n}


def cmp(op: str, left: dict, lit: float) -> dict:
    return {"compare": {"op": op, "left": left, "right": {"literal": lit}}}


AUTO = {"automatic": True, "trigger_time": -1.0}
# 운영 애셋 전이 12 (덤프 2026-10-16): ref, from, to, crossfade, priority, rule
TRANSITIONS = [
    ("t_idle_move", "idle", "move", 0.25, 1, var("bHasMovementInput")),
    ("t_move_idle", "move", "idle", 0.30, 1, {"and": [{"not": var("bHasMovementInput")}, cmp("<", var("Speed"), SPEED_STOP)]}),
    ("t_src_sel", "jumpsrc", "jumpsel", 0.20, 1, {"literal": True}),
    ("t_sel_jump", "jumpsel", "jumpstart", 0.20, 1, var("bIsJumping")),
    ("t_sel_fall", "jumpsel", "fallloop", 0.20, 2, var("bIsFalling")),
    ("t_jump_fall", "jumpstart", "fallloop", 0.20, 1, AUTO),
    ("t_fall_land", "fallloop", "fallland", 0.20, 1, cmp("<", var("GroundDistance"), GROUND_LAND)),
    ("t_land_end_auto", "fallland", "endinair", 0.20, 1, AUTO),
    ("t_land_end_ground", "fallland", "endinair", 0.20, 1, var("bIsOnGround")),
    ("t_interrupt_end", "interrupt", "endinair", 0.20, 1, var("bIsOnGround")),
    ("t_end_idle", "endinair", "idlealias", 0.20, 1, cmp(">=", var("Speed"), SPEED_MOVE)),   # 운영 그대로 (방향이 반대로 보임 — 비교 문서 §5 관찰)
    ("t_end_move", "endinair", "movealias", 0.20, 1, cmp("<", var("Speed"), SPEED_MOVE)),
]
STATES = [("idle", "Idle", [0, 0]), ("move", "Move", [500, 0]), ("jumpstart", "JumpStart", [0, 500]), ("fallloop", "FallLoop", [500, 500]), ("fallland", "FallLand", [1000, 500])]
CONDUITS = [("jumpsel", "JumpSelector", [250, 250]), ("endinair", "EndInAir", [1250, 250])]
ALIASES = [("jumpsrc", "JumpSources", [-300, 250], ["idle", "move"]), ("interrupt", "JumpFallInterruptSources", [800, 800], ["jumpstart", "fallloop"]),
           ("idlealias", "IdleAlias", [1600, 150], ["idle"]), ("movealias", "MoveAlias", [1600, 350], ["move"])]


def build() -> None:
    info_prod = must(bridge.call("get_anim_blueprint_info", {"asset_path": PROD}), "prod info")
    prod_vars = {v["name"] for v in info_prod["variables"]}
    check({"Speed", "bHasMovementInput", "bIsJumping", "bIsFalling", "bIsOnGround", "GroundDistance"} <= prod_vars, f"필요 변수 존재: {sorted(prod_vars)}")

    print("\n=== 1. 생성 ===")
    overwrite = "--overwrite" in sys.argv
    created = bridge.call("create_animation_blueprint", {"asset_path": BUILD, "skeleton": SKELETON, "parent_class": PARENT, "overwrite": overwrite})
    if not created.get("ok"):
        code = created.get("error", {}).get("code")
        if code == "ASSET_EXISTS":
            print(f"{BUILD} 가 이미 있다 — 다시 만들려면 --overwrite (기존 애셋 삭제)")
            sys.exit(2)
        must(created, "create")
    s0 = structure(BUILD, 0)
    root = next(n for n in s0["nodes"] if n["class"] == "AnimGraphNode_Root")

    print("\n=== 2. 루트 그래프 — 전신 슬롯 → FullBody 캐시 → (Base / 상체 슬롯) → 본 레이어 → Inertialization ===")
    ops_root = [
        {"op": "add_node", "ref": "sm", "class": "AnimGraphNode_StateMachine", "pos": [-1500, 0]},
        {"op": "add_node", "ref": "slot_full", "class": "AnimGraphNode_Slot", "pos": [-1200, 0], "properties": {"SlotName": FULL_BODY_SLOT}},
        {"op": "connect", "from": {"ref": "sm", "pin": "Pose"}, "to": {"ref": "slot_full", "pin": "Source"}},
        # 전신 슬롯 출력(몽타주 포함)을 캐시해 두 갈래로 — 상체 슬롯이 비어 있으면 같은 포즈라 블렌드가 항등이 된다
        {"op": "add_node", "ref": "save", "class": "AnimGraphNode_SaveCachedPose", "pos": [-900, 0], "properties": {"CacheName": "FullBody"}},
        {"op": "connect", "from": {"ref": "slot_full", "pin": "Pose"}, "to": {"ref": "save", "pin": "Pose"}},
        {"op": "add_node", "ref": "use_base", "class": "AnimGraphNode_UseCachedPose", "pos": [-600, -150]},
        {"op": "set_property", "ref": "use_base", "property": "SaveCachedPoseNode", "value": {"ref": "save"}},
        {"op": "add_node", "ref": "use_upper", "class": "AnimGraphNode_UseCachedPose", "pos": [-900, 250]},
        {"op": "set_property", "ref": "use_upper", "property": "SaveCachedPoseNode", "value": {"ref": "save"}},
        {"op": "add_node", "ref": "slot_upper", "class": "AnimGraphNode_Slot", "pos": [-600, 250], "properties": {"SlotName": UPPER_BODY_SLOT}},
        {"op": "connect", "from": {"ref": "use_upper", "pin": "Pose"}, "to": {"ref": "slot_upper", "pin": "Source"}},
        {"op": "add_node", "ref": "layer", "class": "AnimGraphNode_LayeredBoneBlend", "pos": [-300, 0], "properties": {"bMeshSpaceRotationBlend": True}},
        {"op": "set_property", "ref": "layer", "property": "LayerSetup", "value": [{"BranchFilters": [{"BoneName": UPPER_BODY_BONE, "BlendDepth": 0}]}]},
        {"op": "connect", "from": {"ref": "use_base", "pin": "Pose"}, "to": {"ref": "layer", "pin": "BasePose"}},
        {"op": "connect", "from": {"ref": "slot_upper", "pin": "Pose"}, "to": {"ref": "layer", "pin": "BlendPoses_0"}},
        {"op": "add_node", "ref": "inertia", "class": "AnimGraphNode_Inertialization", "pos": [0, 0]},
        {"op": "connect", "from": {"ref": "layer", "pin": "Pose"}, "to": {"ref": "inertia", "pin": "Source"}},
        {"op": "connect", "from": {"ref": "inertia", "pin": "Pose"}, "to": {"node": root["node_guid"], "pin": "Result"}},
    ]
    r_root = apply(ops_root, s0["revision"], "루트")
    refs = dict(r_root["refs"])

    print("\n=== 3. 상태머신 `Locomotions` — 상태 5(내부 포함) · conduit 2 · alias 4 · Entry · 전이 12 — 배치 하나 ===")
    ops_sm: list[dict] = [{"op": "rename_node", "node": refs["sm"], "name": "Locomotions"}]
    ops_sm += [{"op": "add_state", "ref": ref, "sm": {"node": refs["sm"]}, "name": name, "pos": pos} for ref, name, pos in STATES]
    ops_sm.append({"op": "set_entry_state", "sm": {"node": refs["sm"]}, "state": {"ref": "idle"}})
    # 상태 내부 — 같은 배치에서 graph:{ref} · result_of (Phase 6-1)
    for ref, asset, loop in (("idle", ASSETS["idle"], True), ("jumpstart", ASSETS["jump"], False), ("fallloop", ASSETS["fall"], True), ("fallland", ASSETS["land"], False)):
        ops_sm += [
            {"op": "add_node", "ref": f"{ref}_seq", "graph": {"ref": ref}, "class": "AnimGraphNode_SequencePlayer", "pos": [-400, 0], "asset": asset, "properties": {"bLoopAnimation": loop}},
            {"op": "connect", "from": {"ref": f"{ref}_seq", "pin": "Pose"}, "to": {"result_of": {"ref": ref}, "pin": "Result"}},
        ]
    ops_sm += [
        {"op": "add_node", "ref": "move_speed", "graph": {"ref": "move"}, "class": "K2Node_VariableGet", "variable": "Speed", "pos": [-800, 120]},
        {"op": "add_node", "ref": "move_bs", "graph": {"ref": "move"}, "class": "AnimGraphNode_BlendSpacePlayer", "pos": [-400, 0], "asset": ASSETS["bs"], "properties": {"bLoop": True}},
        {"op": "connect", "from": {"ref": "move_speed", "pin": "Speed"}, "to": {"ref": "move_bs", "pin": "X"}},
        {"op": "connect", "from": {"ref": "move_bs", "pin": "Pose"}, "to": {"result_of": {"ref": "move"}, "pin": "Result"}},
    ]
    ops_sm += [{"op": "add_conduit", "ref": ref, "sm": {"node": refs["sm"]}, "name": name, "pos": pos, "rule": {"literal": True}} for ref, name, pos in CONDUITS]
    ops_sm += [{"op": "add_state_alias", "ref": ref, "sm": {"node": refs["sm"]}, "name": name, "pos": pos, "states": [{"ref": s} for s in states]} for ref, name, pos, states in ALIASES]
    for ref, src, dst, xfade, prio, rule in TRANSITIONS:
        ops_sm.append({"op": "add_transition", "ref": ref, "from": {"ref": src}, "to": {"ref": dst},
                       "properties": {"CrossfadeDuration": xfade, "PriorityOrder": prio}, "rule": rule})
    r_in = apply(ops_sm, r_root["revision_after"], "상태머신+내부", compile=True)
    refs.update(r_in["refs"])

    print("\n=== 5. 저장 · 재조회 ===")
    saved = must(bridge.call("save_animation_blueprint", {"asset_path": BUILD}), "save")
    check(bool(saved.get("saved", True)), f"저장: {saved}")
    final = structure(BUILD, -1)
    STATE_FILE.write_text(json.dumps({"revision": final["revision"], "nodes": sorted(n["node_guid"] for n in final["nodes"]),
                                      "state_machines": final["state_machines"], "refs": refs}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"saved → {STATE_FILE} (revision {final['revision']})")

    print("\n=== 6. 운영 애셋과 비교 → diff 문서 ===")
    write_diff(structure(PROD, -1), final, refs)


# ----------------------------------------------------------------------------------------------------------------------
def describe_rule(struct: dict, t: dict) -> str:
    """전이 규칙 한 줄 — 도구 생성이면 rule_source, 아니면 규칙 그래프의 K2 노드 제목 + 리터럴 기본값."""
    if t["automatic"]:
        return "automatic"
    if t.get("rule_source") is not None:
        return json.dumps(t["rule_source"], ensure_ascii=False)
    parts = []
    result_default = None
    for n in struct["nodes"]:
        if n["graph_guid"] != t["rule_graph_guid"]:
            continue
        if n["class"] == "AnimGraphNode_TransitionResult":
            pin = next((p for p in n["pins"] if p["name"] == "bCanEnterTransition"), None)
            result_default = pin["default"] if pin else None
            continue
        if n["class"] == "EdGraphNode_Comment":
            continue
        lits = [f"{p['name']}={p['default']}" for p in n["pins"] if p["dir"] == "in" and not p["linked"] and p["name"] not in ("self", "ErrorTolerance") and p["default"] not in (None, "")]
        parts.append(n["title"] + (f"({', '.join(lits)})" if lits else ""))
    return " · ".join(parts) if parts else f"(노드 없음 → Result 기본값 {result_default})"


def root_chain(struct: dict) -> list[str]:
    """Output Pose 에서 입력을 거슬러 올라간 루트 그래프 노드 사슬 (단일 입력만 따라간다)."""
    root_graph = struct["root_graph_guid"]
    nodes = {n["node_guid"]: n for n in struct["nodes"] if n["graph_guid"] == root_graph}
    chain, cur = [], next(n for n in nodes.values() if n["class"] == "AnimGraphNode_Root")
    seen = set()
    while cur and cur["node_guid"] not in seen:
        seen.add(cur["node_guid"])
        label = cur["class"].replace("AnimGraphNode_", "")
        props = cur.get("properties") or {}
        for k in ("SlotName", "CacheName", "LayerSetup"):
            if k in props:
                label += f"[{k}={json.dumps(props[k], ensure_ascii=False)}]"
        chain.append(label)
        links = [p["linked"] for p in cur["pins"] if p["dir"] == "in" and p["linked"] and p["type"].startswith("struct:PoseLink")]
        cur = nodes.get(links[0][0].split(":")[0]) if links else None
    return chain


def write_diff(prod: dict, build: dict, refs: dict) -> None:
    def sm_rows(struct: dict):
        sm = struct["state_machines"][0]
        names = {s["node_guid"]: s["name"] for s in sm["states"]}
        states = []
        for s in sm["states"]:
            inner = [n for n in struct["nodes"] if n["graph_guid"] == s.get("bound_graph_guid") and n["class"] != "AnimGraphNode_StateResult"]
            desc = ", ".join(n["class"].replace("AnimGraphNode_", "") + (f"({pathlib.PurePosixPath(n['asset']).stem})" if n.get("asset") else "") for n in inner)
            states.append((s["name"], s["kind"], desc or "—"))
        trans = [(names[t["from"]], names[t["to"]], describe_rule(struct, t), t["crossfade_duration"], t["priority_order"]) for t in sm["transitions"]]
        return sm["name"], states, trans

    p_name, p_states, p_trans = sm_rows(prod)
    b_name, b_states, b_trans = sm_rows(build)
    lines = [
        "# Phase 5 — ABP_Hero_McpBuild vs ABP_Hero_Base 구조 비교",
        "",
        f"> 생성 `Tools/mcp/phase5_build_hero.py` · 빌드 애셋 `{BUILD}` (revision `{build['revision']}`) · 운영 애셋 `{PROD}` (revision `{prod['revision']}`, 읽기만)",
        "> 빌드 애셋은 도구(apply_graph_operations)만으로 빈 AnimBP 에서 구성했다. 운영 애셋은 사람이 만든 것이며 변경하지 않았다.",
        "",
        "## 1. 수치",
        "",
        "| | 운영 | 빌드 |",
        "| :--- | ---: | ---: |",
        f"| 그래프 | {len(prod['graphs'])} | {len(build['graphs'])} |",
        f"| 노드 | {len(prod['nodes'])} | {len(build['nodes'])} |",
        f"| 연결 | {len(prod['connections'])} | {len(build['connections'])} |",
        f"| 상태 (alias·conduit 포함) | {len(p_states)} | {len(b_states)} |",
        f"| 전이 | {len(p_trans)} | {len(b_trans)} |",
        "",
        "## 2. 루트 그래프 (Output Pose 에서 거슬러 올라감)",
        "",
        f"- 운영: `{' ← '.join(root_chain(prod))}`",
        f"- 빌드: `{' ← '.join(root_chain(build))}`",
        "",
        f"빌드는 전신 슬롯(`{FULL_BODY_SLOT}`) **출력**을 SaveCachedPose `FullBody` 로 캐시해 BasePose 와 상체 슬롯(`{UPPER_BODY_SLOT}`) 두 갈래로 나눈 뒤 LayeredBoneBlend(`{UPPER_BODY_BONE}` 이하, 메시 공간 회전 블렌드)로 합친다. "
        "상체 슬롯이 비어 있으면 전신 슬롯 출력(몽타주 포함)이 그대로 통과해 블렌드가 항등이다 — 상체 슬롯을 전신 슬롯과 나란히 두면 전신 몽타주의 상체가 로코모션으로 덮인다(2026-10-16 PIE 실측). "
        "몽타주 5개는 전부 DefaultSlot 을 쓰므로 UpperBody 슬롯은 몽타주 슬롯을 바꾸기 전까지 비어 있다(콘텐츠 작업). 운영 애셋에도 같은 레이어가 적용돼 있다(§5).",
        "",
        f"## 3. 상태머신 — 운영 `{p_name}` / 빌드 `{b_name}`",
        "",
        "| 상태 | 운영 | 빌드 |",
        "| :--- | :--- | :--- |",
    ]
    all_states = sorted({s[0] for s in p_states} | {s[0] for s in b_states}, key=lambda n: ([s[0] for s in p_states] + [s[0] for s in b_states]).index(n))
    pm, bm = {s[0]: s for s in p_states}, {s[0]: s for s in b_states}
    for n in all_states:
        p = f"{pm[n][1]}: {pm[n][2]}" if n in pm else "—"
        b = f"{bm[n][1]}: {bm[n][2]}" if n in bm else "—"
        lines.append(f"| {n} | {p} | {b} |")
    lines += ["", "### 전이 — 운영", "", "| from | to | 규칙 | xfade | prio |", "| :--- | :--- | :--- | ---: | ---: |"]
    lines += [f"| {a} | {b} | {r} | {x:g} | {p} |" for a, b, r, x, p in p_trans]
    lines += ["", "### 전이 — 빌드 (규칙은 도구 AST 원문)", "", "| from | to | 규칙 | xfade | prio |", "| :--- | :--- | :--- | ---: | ---: |"]
    lines += [f"| {a} | {b} | `{r}` | {x:g} | {p} |" for a, b, r, x, p in b_trans]
    lines += [
        "",
        "## 4. 의도한 차이",
        "",
        "1. **상태머신은 운영과 1:1** (Phase 6-1) — 상태 5 · conduit 2 · alias 4 · 전이 12 · 이름 `Locomotions` · 상태 내부까지 배치 하나로. 운영의 전이 규칙은 사람이 만든 K2 노드, 빌드는 도구 AST(rule_source) 라는 차이만 있다.",
        f"2. **UpperBody 레이어** — §2. 운영 애셋에도 적용돼 있다(§5) (Slot `{UPPER_BODY_SLOT}` + LayeredBoneBlend LayerSetup `{UPPER_BODY_BONE}`).",
        "3. **Move 상태의 Speed 바인딩** — 운영과 같이 K2 VariableGet → BlendSpacePlayer.X 핀 연결 (Property Binding 아님).",
        "4. **Inertialization** — 운영과 같이 루트 끝에 둔다. 허용 목록 프로퍼티는 없고 기본값 그대로.",
        "",
        "## 5. 운영 애셋 적용 상태",
        "",
        "- §4-3 UpperBody 레이어는 2026-10-16 사용자 승인으로 운영 애셋에 적용됐다 (Locomotion·Jump 는 운영에 이미 있음). 첫 적용은 상체 슬롯을 전신 슬롯과 나란히 둬 공격 몽타주 상체가 깨졌고, 같은 날 전신 슬롯 뒤 `FullBody` 캐시 배선으로 재적용했다. 운영 루트 사슬은 §2 참조. PIE 확인은 사용자가 한다.",
        "- 운영 애셋 관찰: `EndInAir → IdleAlias` 규칙이 `Speed >= 20`, `EndInAir → MoveAlias` 가 `Speed < 20` 으로 읽힌다(덤프 기준). 의도가 반대라면 사람이 고칠 항목 — 도구는 건드리지 않았다.",
    ]
    DIFF_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"diff → {DIFF_FILE}")


def recheck() -> None:
    print("\n=== R. 에디터 재시작 후 재조회 ===")
    saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    s = structure(BUILD, -1)
    check(s["revision"] == saved["revision"], f"revision 동일 ({s['revision']})")
    check(sorted(n["node_guid"] for n in s["nodes"]) == saved["nodes"], "노드 Guid 집합 동일")
    check(s["state_machines"] == saved["state_machines"], "state_machines 뷰 동일")
    comp = must(bridge.call("compile_animation_blueprint", {"asset_path": BUILD}), "compile")
    check(comp.get("num_errors") == 0, f"재시작 후 컴파일 0 에러 (warnings={comp.get('num_warnings')})")


def main() -> int:
    status = must(bridge.call("get_editor_status"), "status")
    print(f"editor {status.get('engine_version')} tools {len(status['tools'])}")
    if "--recheck" in sys.argv:
        recheck()
    elif "--diff-only" in sys.argv:
        # 애셋은 그대로 두고 비교 문서만 다시 쓴다
        saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        write_diff(structure(PROD, -1), structure(BUILD, -1), saved.get("refs", {}))
    else:
        build()
    print("\n" + ("PASS" if not FAILS else f"FAIL ({len(FAILS)}):\n  - " + "\n  - ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
