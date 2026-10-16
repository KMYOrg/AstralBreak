"""디버그 — 테스트 AnimBP 의 전이 규칙 그래프(주석·규칙 노드) 덤프. 운영 애셋은 건드리지 않는다.
    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/debug_dump_rules.py [asset_path]
"""
import json
import sys

from anim_graph_mcp import bridge

ABP = sys.argv[1] if len(sys.argv) > 1 else "/Game/Animation/Test/ABP_McpTest"
s = bridge.call("get_anim_graph_structure", {"asset_path": ABP, "depth": -1}, timeout=180)
if not s.get("ok"):
    print(json.dumps(s, ensure_ascii=False, indent=1)[:2000])
    sys.exit(1)
s = s["result"]
graphs = {g["graph_guid"]: g for g in s["graphs"]}
for n in s["nodes"]:
    if n["class"] == "EdGraphNode_Comment":
        print("COMMENT in", graphs.get(n["graph_guid"], {}).get("name"), repr(n.get("comment"))[:400])
for sm in s.get("state_machines", []):
    for t in sm["transitions"]:
        print("T", t["name"], "gen=", t["rule_generated"], "mod=", t["rule_modified"], "nodes=", t["rule_node_count"], "src=", t["rule_source"])
for n in s["nodes"]:
    g = graphs.get(n["graph_guid"], {})
    if g.get("class") == "AnimationTransitionGraph":
        print("  RULE NODE", g["name"], n["class"], n["title"][:40], [(p["name"], p["default"], p["linked"]) for p in n["pins"] if not p["hidden"]])
