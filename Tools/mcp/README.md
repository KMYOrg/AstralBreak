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

## Tool (12개)

조회 `get_editor_status` · `get_anim_blueprint_info` · `get_anim_graph_structure` · `list_animation_assets` — 생성/저장 `create_animation_blueprint` · `save_animation_blueprint` · `duplicate_animation_blueprint` · `delete_animation_blueprint` — 편집 `preview_graph_operations` · `apply_graph_operations` · `compile_animation_blueprint` — 프로세스 `quit_editor`.

`quit_editor` 는 저장 안 된 패키지가 있으면 `save_dirty=true`(콘텐츠만 저장, 맵 제외) 또는 `discard_dirty=true` 없이는 `DIRTY_PACKAGES`(409) 로 거부하고 에디터를 유지한다. 응답의 `process_id` 로 `Tools/mcp/wait_for_exit.py <pid>` 가 프로세스 소멸을 기다린다. 자동화용으로 직접 띄운 에디터에만 쓴다.

## 수동 확인

```
Tools/mcp/.venv/Scripts/python.exe Tools/mcp/smoke_test.py /Game/Animation/Hero/ABP_Hero_Base
```

단계 테스트(`phase3/4/5/6_1/6_2_test.py`, 각 `--recheck`)와 기동·종료 폴링(`wait_for_bridge.py` · `wait_for_exit.py`)은 `.claude/plans/animbp-automation-handoff-phase6-2.md` §8 참조.

## 응답 봉투

```json
{ "ok": true, "tool": "get_editor_status", "request_id": "…", "result": {…}, "error": null, "diagnostics": [] }
{ "ok": false, "tool": "…", "request_id": "…", "result": null, "error": { "code": "ASSET_NOT_FOUND", "message": "…" }, "diagnostics": [] }
```

같은 `(tool, request_id)` 재전송은 캐시된 봉투를 돌려주고 핸들러를 다시 실행하지 않는다.
