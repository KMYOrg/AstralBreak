# AnimGraph MCP

Claude Code ↔ (stdio MCP) ↔ `Tools/mcp/anim_graph_mcp/server.py` ↔ (HTTP/JSON, 127.0.0.1:18765) ↔ `Plugins/AnimGraphMcp` (에디터 C++)

플러그인 쪽 전체 참조(Tool 30개 · op 20종 · 오류 코드 · 제약 · 소스 구조)는 [`Plugins/AnimGraphMcp/README.md`](../../Plugins/AnimGraphMcp/README.md). 설계·API 근거는 `.claude/plans/animbp-automation-phase1.md`.

## 설치 (1회)

```
python -m venv Tools/mcp/.venv
Tools/mcp/.venv/Scripts/python.exe -m pip install -r Tools/mcp/requirements.txt
```

프로젝트 루트의 `.mcp.json` 이 Claude Code 에 서버 `anim-graph-mcp` 를 등록한다:

```json
{ "mcpServers": { "anim-graph-mcp": {
    "command": "Tools/mcp/.venv/Scripts/python.exe",
    "args": ["Tools/mcp/anim_graph_mcp/server.py"],
    "env": { "ANIMGRAPH_MCP_PORT": "18765" } } } }
```

에디터는 `Plugins/AnimGraphMcp` 가 활성화된 상태로 떠 있어야 한다. 다른 프로젝트에 옮길 때는 `Plugins/AnimGraphMcp` + `Tools/mcp`(venv 제외) + `.mcp.json` 을 복사하고 `.uproject` 에 플러그인을 등록한 뒤 에디터 타깃을 빌드한다. 토큰 파일 위치는 `<프로젝트>/Saved/AnimGraphMcp/token` 이고 `bridge.py` 가 자기 위치에서 프로젝트 루트를 찾는다(`ANIMGRAPH_MCP_PROJECT_DIR` 로 오버라이드).

## 설정

`Config/DefaultEngine.ini` (없으면 기본값):

```
[AnimGraphMcp]
Port=18765
bRequireToken=True
bAutoStart=True
+ProtectedAssets=/Game/Animation/Hero/ABP_Hero_Base   ; 삭제·덮어쓰기 거부 — 패키지 또는 오브젝트 경로, 정확히 일치
+ProtectedPaths=/Game/Assets/                          ; 삭제·덮어쓰기 거부 — 패키지 경로 접두
+SmokeTestPaths=/Game/Animation                        ; 스모크 테스트가 여는 AnimBP 경로
```

에디터 콘솔: `AnimGraphMcp.Start` / `AnimGraphMcp.Stop` / `AnimGraphMcp.Status`. 커맨드라인 `-AnimGraphMcpPort=18766` 으로 인스턴스별 포트 오버라이드. 토큰은 에디터가 기동할 때 `Saved/AnimGraphMcp/token` 에 쓴다. `get_editor_status` 만 토큰 면제.

## Tool (30개)

조회 `get_editor_status` · `get_anim_blueprint_info` · `get_anim_graph_structure` · `list_animation_assets` — 생성/저장 `create_animation_blueprint` · `create_blendspace`(`aim_offset` 로 AimOffset) · `create_anim_layer_interface` · `implement_anim_layer_interface` · `save_animation_blueprint` · `duplicate_animation_blueprint` · `delete_animation_blueprint` — 레이어 `set_layer_inputs`(값 파라미터) · `add_anim_layers` · `remove_anim_layers`(구현 ABP 자동 동기화) — 편집 `preview_graph_operations` · `apply_graph_operations`(op 20종, `set_layer_instance_class` 포함) · `compile_animation_blueprint` — 변수·업데이트 함수 `add_blueprint_variable` · `remove_blueprint_variable` · `set_update_function`(ThreadSafeUpdateAnimation 을 스펙에서 생성) — 몽타주 `create_anim_montage` · `set_montage_slots` · `set_montage_sections` · `add_skeleton_slot`(노티파이는 `Tools/lib/ab_montage.py`) — 콘텐츠 선행 `reassign_skeleton`(같은 본 이름의 중복 스켈레톤 통합, 참조 애셋 동반) · `set_sequence_additive`(AimOffset 샘플 기준 포즈) — 검증 `run_automation_tests` · `poll_automation_tests` · `run_anim_scenario`(PIE 에서 상태머신 현재 상태·슬롯 활성 확인) — 프로세스 `quit_editor`.

실전 적용 스크립트: `reassign_hero_skeleton.py`(히어로 애셋 40개 스켈레톤 통합, 1회성) · `build_hero_combat.py`(히어로 전투 ABP — Lyra 식 레이어 · 근접/원거리 · 조준 strafe, 설계는 `.claude/plans/hero-combat-abp.md`) · `build_hero_turninplace.py`(제자리 회전 — 베이스 RotateRootBone + 공급자 조준 Idle 상태머신 IdleTurn, 제자리 패치·멱등, `--verify-only`; build_hero_combat 이 끝에 호출). PIE 실측은 `Tools/scripts/pie_turn_probe_run.py`(에디터 밖에서 `pie_aim_probe.py` 단계를 순서대로 — 조준 → 컨트롤러·액터 Yaw +90 → 틱마다 RootYawOffset 등 기록).

각 Tool 의 입력과 op 사전은 `server.py` 의 docstring(= Claude 가 보는 설명)과 플러그인 README 에 있다. 새 Tool 은 Claude Code 세션을 다시 시작해야 MCP 목록에 보인다.

전형적인 흐름: `get_anim_blueprint_info` 로 `revision`·`variables` 확인 → `get_anim_graph_structure` 로 Guid 파악 → `preview_graph_operations` → `apply_graph_operations {expected_revision, compile:true, save:true}` → `run_automation_tests {"filter": "AnimGraphMcp.Smoke"}` → `run_anim_scenario {asset_path, set_variables, expect}` + `poll_automation_tests` 로 "Speed 300 → Run" 같은 런타임 동작 확인(테스트가 PIE 를 열고 닫는다 — 에디터에서 PIE 를 켜 두지 말 것).

## 수동 확인 · 테스트

```
Tools/mcp/.venv/Scripts/python.exe Tools/mcp/smoke_test.py /Game/Animation/Hero/ABP_Hero_Base
```

전체 회귀는 `run_all.py` 하나로 — 에디터 기동 → 단계 테스트(`phase3/4/5/6_1/6_3/6_4/6_4b/7_1/7_2/7_3/7_4/7_5/7_6/6_5/6_2_test.py`) → 종료 → 재기동 → 각 `--recheck` → 종료, 결과 `Tools/mcp/results/<date>.json`:

```
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/run_all.py [--attach] [--only phase6_5_test] [--skip-recheck]
```

Git Bash 에서 `/Game/...` 인자는 `MSYS_NO_PATHCONV=1`, 한글 출력은 `PYTHONIOENCODING=utf-8`. 개별 스크립트와 기동·종료 폴링(`wait_for_bridge.py` · `wait_for_exit.py`)은 `.claude/plans/animbp-automation-handoff-phase6-2.md` §8 참조. 테스트 애셋은 `/Game/Animation/Test/` 아래(덮어쓰기 대상).

## 응답 봉투

```json
{ "ok": true, "tool": "get_editor_status", "request_id": "…", "result": {…}, "error": null, "diagnostics": [] }
{ "ok": false, "tool": "…", "request_id": "…", "result": null, "error": { "code": "ASSET_NOT_FOUND", "message": "…" }, "diagnostics": [] }
```

같은 `(tool, request_id)` 재전송은 캐시된 봉투를 돌려주고 핸들러를 다시 실행하지 않는다. 전송 오류는 `bridge.py` 가 `EDITOR_GONE` · `TIMEOUT` · `TRANSPORT` · `BAD_RESPONSE` 로 같은 모양에 넣는다.
