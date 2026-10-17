# AnimGraph MCP

Claude Code ↔ (stdio MCP) ↔ `Tools/mcp/anim_graph_mcp/server.py` ↔ (HTTP/JSON, 127.0.0.1:18765) ↔ `Plugins/AnimGraphMcp` (에디터 C++)

설계·API 근거: `.claude/plans/animbp-automation-phase1.md`

## 설치 (1회)

```
python -m venv Tools/mcp/.venv
Tools/mcp/.venv/Scripts/python.exe -m pip install -r Tools/mcp/requirements.txt
```

프로젝트 루트의 `.mcp.json` 이 Claude Code 에 서버를 등록한다. 에디터는 `Plugins/AnimGraphMcp` 가 활성화된 상태로 떠 있어야 한다.

## 설정

`Config/DefaultEngine.ini` (없으면 기본값):

```
[AnimGraphMcp]
Port=18765
bRequireToken=True
bAutoStart=True
```

에디터 콘솔: `AnimGraphMcp.Start` / `AnimGraphMcp.Stop` / `AnimGraphMcp.Status`.
커맨드라인 `-AnimGraphMcpPort=18766` 으로 인스턴스별 포트 오버라이드.

토큰은 에디터가 기동할 때 `Saved/AnimGraphMcp/token` 에 쓴다. `get_editor_status` 만 토큰 면제.

### 보호 목록 (삭제·덮어쓰기 거부)

```
[AnimGraphMcp]
+ProtectedAssets=/Game/Animation/Hero/ABP_Hero_Base   ; 패키지 또는 오브젝트 경로, 정확히 일치
+ProtectedPaths=/Game/Assets/                          ; 패키지 경로 접두
```

`delete_animation_blueprint` 와 `create/duplicate_animation_blueprint` 의 `overwrite` 가 이 목록을 보고 `ASSET_PROTECTED`(403) 로 거부한다. 읽기·편집·저장은 막지 않는다. 삭제는 `confirm=true` 가 필수이고, 다른 애셋이 참조하면 `force=true` 없이는 `ASSET_REFERENCED`(409).

## Tool (17개)

조회 `get_editor_status` · `get_anim_blueprint_info`(`layers`·`implemented_interfaces` 포함) · `get_anim_graph_structure` · `list_animation_assets`(`details` 로 BlendSpace 축·샘플) — 생성/저장 `create_animation_blueprint` · `create_blendspace`(1D/2D, 축·샘플 사전 검증) · `create_anim_layer_interface` · `implement_anim_layer_interface`(Lyra 식 Linked Anim Layer) · `save_animation_blueprint` · `duplicate_animation_blueprint` · `delete_animation_blueprint` — 편집 `preview_graph_operations` · `apply_graph_operations`(op 19종: 노드·연결·속성·상태머신·규칙·`bind_pin`·`set_linked_layer` …) · `compile_animation_blueprint` — 검증 `run_automation_tests` · `poll_automation_tests` — 프로세스 `quit_editor`.

`quit_editor` 는 저장 안 된 패키지가 있으면 `save_dirty=true`(콘텐츠만 저장, 맵 제외) 또는 `discard_dirty=true` 없이는 `DIRTY_PACKAGES`(409) 로 거부하고 에디터를 유지한다. 응답의 `process_id` 로 `Tools/mcp/wait_for_exit.py <pid>` 가 프로세스 소멸을 기다린다. 자동화용으로 직접 띄운 에디터에만 쓴다.

`run_automation_tests {filter, timeout=120, dry_run}` 는 에디터 안에서 Unreal Automation 테스트를 직접 돌린다(Session Frontend 불필요). `filter` 는 테스트 경로 접두/부분 문자열 — `"AnimGraphMcp.Smoke"` 는 플러그인의 AnimBP 구조 스모크 테스트(`[AnimGraphMcp] SmokeTestPaths` 아래 AnimBP 마다 1개: 컴파일 0 에러 · 루트 Output Pose 연결 · 빈 상태 · 끊긴 UseCachedPose · 무효 Linked Layer), `"AstralBreak."` 는 프로젝트 테스트. 지연 명령이 없으면 응답에 결과가 바로 들어오고(`done=true`), 아니면 `poll_automation_tests {job_id}` 로 본다.

## 수동 확인

```
Tools/mcp/.venv/Scripts/python.exe Tools/mcp/smoke_test.py /Game/Animation/Hero/ABP_Hero_Base
```

전체 회귀는 `run_all.py` 하나로 — 에디터 기동 → 단계 테스트(`phase3/4/5/6_1/6_3/6_4/6_4b/6_5/6_2_test.py`) → 종료 → 재기동 → 각 `--recheck` → 종료, 결과 `Tools/mcp/results/<date>.json`:

```
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/run_all.py [--attach] [--only phase6_5_test] [--skip-recheck]
```

개별 스크립트와 기동·종료 폴링(`wait_for_bridge.py` · `wait_for_exit.py`)은 `.claude/plans/animbp-automation-handoff-phase6-2.md` §8 참조.

## 응답 봉투

```json
{ "ok": true, "tool": "get_editor_status", "request_id": "…", "result": {…}, "error": null, "diagnostics": [] }
{ "ok": false, "tool": "…", "request_id": "…", "result": null, "error": { "code": "ASSET_NOT_FOUND", "message": "…" }, "diagnostics": [] }
```

같은 `(tool, request_id)` 재전송은 캐시된 봉투를 돌려주고 핸들러를 다시 실행하지 않는다.
