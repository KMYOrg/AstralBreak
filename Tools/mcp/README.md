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

## 수동 확인

```
Tools/mcp/.venv/Scripts/python.exe Tools/mcp/smoke_test.py /Game/Animation/Hero/ABP_Hero_Base
```

## 응답 봉투

```json
{ "ok": true, "tool": "get_editor_status", "request_id": "…", "result": {…}, "error": null, "diagnostics": [] }
{ "ok": false, "tool": "…", "request_id": "…", "result": null, "error": { "code": "ASSET_NOT_FOUND", "message": "…" }, "diagnostics": [] }
```

같은 `(tool, request_id)` 재전송은 캐시된 봉투를 돌려주고 핸들러를 다시 실행하지 않는다.
