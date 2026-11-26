# Editor MCP Core (`Plugins/EditorMcpCore`)

에디터 MCP 기능 플러그인들이 같이 쓰는 **공용 코어**입니다 — 로컬 HTTP/JSON 브리지(127.0.0.1 전용) · 디스패처 · 응답 봉투 · 토큰 · `request_id` 멱등 캐시 · `get_editor_status` · `quit_editor` · Automation 실행 · 보호 목록 · 쓰기 허용 경로 · 전역 더티 비교. 2026-11-14 `AnimGraphMcp` 에서 떼어 냈습니다(설계 [ui-autogen-pipeline.md](../../Docs/Design/ui-autogen-pipeline.md) §3-1).

```text
AI Agent ─ stdio MCP ─▶ Tools/mcp/{anim_graph_mcp,state_tree_mcp,...}/server.py ─ HTTP/JSON 127.0.0.1:18765 ─▶ EditorMcpCore 브리지
                                                                                                         ├─ AnimGraphMcp  (애니)
                                                                                                         ├─ StateTreeMcp  (AI)
                                                                                                         └─ WidgetMcp     (UI — Phase 1a 부터 Tool)
```

- 모듈 `EditorMcpCore`(Type Editor). 프로젝트 코드에 의존하지 않습니다. 기능 플러그인은 `.uplugin` 의 `Plugins` 에 `EditorMcpCore` 를, `Build.cs` 에 `EditorMcpCore` 를 넣습니다.
- Python 쪽 공용 클라이언트는 `Tools/mcp/editor_bridge/bridge.py`(옛 `from anim_graph_mcp import bridge` 도 같은 모듈).

## 기능 플러그인 등록

```cpp
#include "EditorMcpCoreModule.h"

void FMyFeatureModule::StartupModule()
{
    IEditorMcpCoreModule& Core = IEditorMcpCoreModule::Get();
    Core.RegisterTools(TEXT("MyFeature"), [](FAnimMcpDispatcher& D) { MyTools::Register(D); });
    Core.RegisterStatusSection(TEXT("MyFeature"), [](const TSharedRef<FJsonObject>& R) { R->SetObjectField(TEXT("my_feature"), …); });
}
void FMyFeatureModule::ShutdownModule()
{
    if (IEditorMcpCoreModule* Core = IEditorMcpCoreModule::GetIfLoaded()) { Core->UnregisterTools(TEXT("MyFeature")); }
}
```

- 코어는 브리지를 시작할 때마다(에디터 기동 뒤 `OnPostEngineInit` · `EditorMcp.Start`) 새 디스패처에 코어 Tool 과 등록 함수를 전부 다시 돌립니다. 이미 떠 있을 때 등록 · 해제하면 그 자리에서 Tool 과 라우트를 붙이고 뗍니다.
- 등록 함수 안에서 만든 Tool 은 그 기능 소유가 됩니다(`FAnimMcpDispatcher::BeginFeature/EndFeature` · `RemoveFeature`). 해제 때 그 기능의 Tool 만 빠지고 `request_id` 캐시도 비웁니다.
- 새 코드는 `EditorMcp.h` 의 별칭(`FEditorMcpDispatcher` · `FEditorMcpError` · `EditorMcpJson` …)을 쓸 수 있습니다. 코어 타입 이름(`FAnimMcp*` · `AnimMcp*`)은 기존 코드 수천 줄을 건드리지 않으려고 분리 전 그대로 둡니다.

## 설정 — `Config/DefaultEngine.ini`

```ini
[EditorMcp]
Port=18765                 ; 커맨드라인 -AnimGraphMcpPort=18766 으로 인스턴스별 오버라이드 (이름은 분리 전 그대로)
bRequireToken=True         ; Saved/AnimGraphMcp/token 을 헤더 X-AnimMcp-Token 으로 요구 (get_editor_status 만 면제)
bAutoStart=True            ; 에디터 기동 시 리스너 시작
+ProtectedAssets=/Game/Characters/Hero/ABP_Hero    ; 삭제·덮어쓰기 거부 (모든 기능 공통)
+ProtectedPaths=/Game/ThirdParty/
```

- **옛 `[AnimGraphMcp]` 섹션도 그대로 읽습니다.** 배열(`+Key=`)은 두 섹션을 합치고(`[EditorMcp]` 먼저), 값(`Key=`)은 `[EditorMcp]` 에 있으면 그것, 없으면 `[AnimGraphMcp]`(`Core/EditorMcpSettings.h`). 기능 키(애니 생성 경로 등)는 각 기능 플러그인 README.
- 콘솔: `EditorMcp.Start` / `EditorMcp.Stop` / `EditorMcp.Status`, 옛 이름 `AnimGraphMcp.Start` / `Stop` / `Status` 도 같은 동작.
- 토큰 파일 위치 `Saved/AnimGraphMcp/token`, 헤더 `X-AnimMcp-Token`, 로그 카테고리 `LogAnimGraphMcp`, 기동 로그 `AnimGraphMcp bridge listening on …` 은 분리 전 그대로입니다(기존 Python 클라이언트 · 하네스 호환).

## 코어 Tool (4개)

| Tool | 입력 | 하는 일 |
| :--- | :--- | :--- |
| `get_editor_status` | — | 토큰 면제. 엔진 · 프로젝트 · PIE · 포트 · Tool 목록 · `process_id` · 보호 목록 · `dirty_package_count` · `plugin_version`(EditorMcpCore) · `features[{name, tools}]` + 기능 필드(AnimGraphMcp `generation` · StateTreeMcp `state_tree_edit_paths` · WidgetMcp `widget`). 필드 이름 · 모양은 분리 전과 같다(`features` · `widget` 만 추가) |
| `run_automation_tests` | `filter(필수), timeout=120, dry_run=false` | 에디터 안에서 Automation 테스트 실행(`FAutomationTestFramework` 직접 구동). 지연 명령이 없으면 동기 완료(`done=true`), 아니면 `job_id` 로 poll |
| `poll_automation_tests` | `job_id` | `run_automation_tests` · `run_anim_scenario` · `run_state_tree_scenario` 잡의 진행 · 결과 |
| `quit_editor` | `save_dirty=false, discard_dirty=false, discard_only_under?` | 더티 패키지가 있으면 둘 중 하나 없이는 `DIRTY_PACKAGES` 로 거부. `save_dirty` 는 콘텐츠만 저장(맵 제외). `discard_only_under`(패키지 경로 접두 배열, 예 `["/Game/_AutoGen/"]` — 2026-11-14 UI 파이프라인)를 주면 `discard_dirty` 여도 그 밖의 더티가 하나라도 있으면 `DIRTY_PACKAGES`(details `outside_discard_only_under`) — 주지 않으면 지금까지와 같다. 응답 `process_id` |

통신 규약(봉투 · `request_id` 캐시 · 진단 · 오류 코드 → HTTP 상태)은 분리 전과 같습니다 — [`Plugins/AnimGraphMcp/README.md`](../AnimGraphMcp/README.md) '통신 규약' · '오류 코드'.

## 기능이 같이 쓰는 코어 라이브러리

| 헤더 | 내용 |
| :--- | :--- |
| `Bridge/AnimMcpDispatcher.h` · `AnimMcpHttpBridge.h` · `AnimMcpTypes.h` | Tool 테이블 · 봉투 · 멱등 캐시 · 기능 소유 / HTTPServer 라우트 · 토큰 · `SyncRoutes` / 오류 코드 · 요청 헬퍼 · JSON |
| `Core/AnimMcpAssetResolver.h` | 경로 정규화 · 존재 확인 · 클래스 검사 로드 |
| `Core/AnimMcpAssetProtection.h` | 보호 목록(파괴 연산 거부) |
| `Core/AnimMcpAutomationRunner.h` · `Core/AnimMcpRuntimeScenario.h` | Automation 잡 러너 · PIE 시나리오 계약(명령 문자열 · 관측 슬롯) |
| `Core/AnimMcpPropertyValues.h` | JSON ↔ 리플렉션 프로퍼티 값 (ImportText · PropertyToJson · 오브젝트 참조) |
| `Core/EditorMcpGuard.h` | 쓰기 허용 경로(접두 · '/' 경계) · 전역 더티 스냅샷(`FDirtySnapshot`) |
| `Core/EditorMcpSettings.h` | `[EditorMcp]` + 옛 `[AnimGraphMcp]` 설정 읽기 |
| `AnimMcpLog.h` | 로그 카테고리 `LogAnimGraphMcp` |

시험: Automation `EditorMcpCore.*` (`Settings` — 두 섹션 읽기 규칙 · 접두 경계, `Dispatcher` — 기능 소유 · 해제 뒤 캐시).
