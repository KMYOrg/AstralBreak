# AI Animation Blueprint Automation
## 개발 지침서 (개정 4판) — Phase 6-2 착수용 핸드오프 (Phase 5 · 6-1 반영 통합본)

> 작성 2026-10-16 · 브랜치 `feat/ai_auto_ABP` · 기준 엔진 UE 5.7.4 소스 빌드
> 최초 지침서(Phase 1 착수 시 전달)를 **Phase 6-1 까지 구현된 상태**에 맞춰 다시 쓴 것이다. 환경·아키텍처·op 사전·Tool·작업 규칙·실측 함정을 **이 문서 하나에** 모았으므로, 새 세션은 이 문서와 근거 문서 [animbp-automation-phase1.md](animbp-automation-phase1.md)(§B API 검증표 · §C 아키텍처 결정 · "Phase 2 ~ 6-1 결과" 절) 두 개만 읽으면 된다.
> 이 문서는 [animbp-automation-handoff-phase5.md](animbp-automation-handoff-phase5.md)(개정 2판) 과 [animbp-automation-handoff-phase6.md](animbp-automation-handoff-phase6.md)(개정 3판, Phase 6 분할 계획) 을 **대체**한다. 둘은 이력으로만 남긴다.

---

### 1. 프로젝트 개요 · 최종 목표 · 현재 상태

Unreal Engine 5.7.4 Source Build 환경에서 Claude Code 가 Animation Blueprint 를 생성·조회·수정·컴파일·검증할 수 있게 하는 AI Agent Tool 시스템. 사용자가 애니메이션 애셋과 동작 설계 가이드를 주면 Claude Code 가 실행 중인 에디터와 상호작용해 실제 AnimBP 를 구성한다. 기존 AnimBP 는 전체 재생성이 아니라 구조를 분석하고 필요한 부분만 안전하게 수정한다. **특정 캐릭터 하나가 아니라 범용 도구**가 목표다.

| 최초 목표 | 상태 | 비고 |
| :--- | :---: | :--- |
| AnimBP 애셋 자동 생성 및 조회 | ✅ | |
| 기존 AnimGraph · State Machine 구조 분석 | ✅ | 그래프 트리 · 노드 · 핀 · 연결 · 허용 목록 프로퍼티 · 바인딩 보유 · 노출 핀 · 상태머신 뷰(상태/conduit/alias · 전이 · 규칙 원문) |
| AnimGraph 노드 생성·수정·삭제 및 Pin 연결 | ✅ | op 8종 + VariableGet 노드 + LayerSetup(Phase 5) |
| State Machine · State · Transition 자동 구성 | ✅ | op 4종(Phase 4) + conduit · alias · rename · 같은 배치 상태 내부(Phase 6-1) — **운영 애셋 상태머신을 1:1 재현** |
| Transition Rule 및 블렌딩 조건 | ✅ | JSON AST → 규칙 그래프, 멱등, 사람 편집 감지. conduit 도 같은 경로 |
| AnimSequence · BlendSpace · Montage 연결 | ✅ | 할당·교체 + **BlendSpace 1D/2D 생성**(6-3, 축·샘플·사전 검증) |
| 기존 C++ AnimInstance 와 연동 | ✅ | 변수 조회 · 규칙 `var`/`call` · `K2Node_VariableGet` 노드 · **핀 Property Binding**(6-4a, `bind_pin`/`unbind_pin`) |
| Linked Anim Layer (Lyra 식 레이어 분리) | ✅ | 6-4b — 인터페이스 생성 · 구현 · 레이어 노드(`add_node layer` · `set_linked_layer`) · 조회. **포즈 입력만** |
| 컴파일 및 오류 분석 | ✅ | 노드 Guid 매핑 + **(6-5) 에디터 안 Automation 실행**(`run_automation_tests`/`poll_automation_tests`) · 구조 스모크 테스트 `AnimGraphMcp.Smoke.AnimBlueprint`(경로 아래 ABP 전부 — 컴파일·빈 루트·빈 상태·끊긴 캐시·빈 레이어) · 통합 러너 `run_all.py` |
| 저장 · 변경 검증 · 실패 복구 | ✅ | revision 해시 · 되돌리기 저널 · 롤백 검증 · 재시작 재조회 테스트 |
| 애셋 수명 (복제 · 삭제 · 에디터 종료) | ✅ | Phase 6-2 — ini 보호 목록 · 참조 검사 · 더티 패키지 거부. **MCP 에는 세션 재시작 뒤 보임** |
| 다른 UE5 프로젝트에서 재사용 | 🔶 | 플러그인은 프로젝트 비의존. **타 프로젝트 재현 미검증** (6-6) |

**Phase 이력**: 1 조사(10-10) · 2 통신 골격(`a669c33`) · 2.5 수직 통합(`d87608f`) · 3 범용 편집(`2a85228`) · 4 State Machine(`3737c67`) · 5 실제 캐릭터(`cdc20fc`) · 6-1 상태머신 완성(`51cb0a8`) · 6-2 애셋 수명(커밋됨, 10-16) · 6-3 BlendSpace(커밋됨, 10-16) · 6-4a Property Binding · 6-4b Linked Anim Layer(`37a2042`, 10-17) · **6-5 검증 자동화(10-17, 미커밋 — §13)**. 남은 것은 6-6 (§12).

**실제 적용 결과**: 운영 애셋 `/Game/Animation/Hero/ABP_Hero_Base` 에 UpperBody 레이어(Slot `UpperBody` + LayeredBoneBlend `spine_01`) 가 사용자 승인 배치로 적용·PIE 확인·커밋됐다(revision `3c146b5f…`). 도구만으로 만든 `/Game/Animation/Hero/ABP_Hero_McpBuild` 는 운영 애셋과 구조 1:1(그래프 21 · 연결 54 · 상태 11 · 전이 12) — 비교 문서 [animbp-phase5-hero-diff.md](animbp-phase5-hero-diff.md).

---

### 2. 개발 환경 (확정)

| 항목 | 값 |
| :--- | :--- |
| Engine | UE 5.7.4 소스 빌드, `D:/UnrealSource/UnrealEngine-5.7.4-release` |
| Project | `D:/UE5Projects/AstralBreak` — 런타임 모듈 1개 `AstralBreak`, 에디터 모듈 없음(플러그인이 대신) |
| 플러그인 | `Plugins/AnimGraphMcp/` — 에디터 전용 모듈 `AnimGraphMcpEditor`(Build.cs 의존: UnrealEd · AnimGraph · AnimGraphRuntime · BlueprintGraph · HTTPServer · Sockets · Json · AssetRegistry · Projects). uproject 에 등록 |
| MCP 서버 | Python 3.13, `Tools/mcp/anim_graph_mcp/{server.py, bridge.py}`, venv `Tools/mcp/.venv`(gitignore), 패키지 `mcp 2.3.0`(`MCPServer` API — 1.x `FastMCP` 아님) · `httpx` |
| Claude Code 등록 | 프로젝트 루트 `.mcp.json` → 서버명 `anim-graph-mcp`. 세션 시작 시 Tool 17개가 `mcp__anim-graph-mcp__*` 로 보인다(6-2 이전 세션은 9개, 6-3 이전 12개, 6-4b 이전 13개, 6-5 이전 15개). **Tool 목록은 세션 시작 시 고정** — 새 Tool 은 재시작 전까지 HTTP 테스트로만 검증 |
| 통신 | Claude Code ↔ server.py: stdio MCP · server.py ↔ 플러그인: `POST http://127.0.0.1:18765/v1/<tool>` JSON, 헤더 `X-AnimMcp-Token` |
| 설정 | `Config/DefaultEngine.ini [AnimGraphMcp] Port=18765 / bRequireToken=True / bAutoStart=True`(전부 기본값, ini 미기재) + **보호 목록(6-2, ini 기재됨)** `+ProtectedAssets=/Game/Animation/Hero/ABP_Hero_Base` · `+ProtectedPaths=/Game/Assets/` — 삭제·덮어쓰기만 막는다. **(6-5)** `+SmokeTestPaths=/Game/Animation` — 스모크 테스트가 여는 AnimBP 경로(생략 시 같은 기본값). 커맨드라인 `-AnimGraphMcpPort=`. 콘솔 `AnimGraphMcp.Start/Stop/Status` |
| 토큰 | 에디터 기동마다 `Saved/AnimGraphMcp/token`, 종료 시 삭제. `get_editor_status` 만 면제 |
| 빌드 | `Engine/Build/BatchFiles/Build.bat AstralBreakEditor Win64 {Development\|DebugGame} -Project=<uproject> -WaitMutex -NoHotReload`. **두 구성 모두**(사용자는 DebugGame 에디터). 플러그인만 바뀌면 10~15초. 에디터가 떠 있으면 DLL 잠금으로 링크 실패 → 먼저 내린다 |
| 툴체인 | MSVC 14.38 (UBT 가 14.44 금지) |
| 에디터 기동/종료 | 기동 `UnrealEditor.exe <uproject>`(백그라운드) → `Tools/mcp/.venv/Scripts/python.exe Tools/mcp/wait_for_bridge.py 540 10` 폴링 → 응답 뒤 **25초 대기**(애셋 로딩). **종료는 `quit_editor` Tool**(HTTP: `bridge.call("quit_editor", {"save_dirty": True})` 또는 `{"discard_dirty": True}`; 더티가 있으면 둘 중 하나 없이는 거부) → `Tools/mcp/wait_for_exit.py [pid] 180 5` 로 프로세스 소멸 폴링(pid 는 응답 `process_id`). `taskkill` 은 브리지가 죽었을 때만 — `tasklist //FI` 는 `MSYS_NO_PATHCONV=1` 셸에서 깨진다. 테스트 전에 내 에디터가 아닌 사용자 에디터가 떠 있지 않은지 `tasklist` 로 본다(같은 포트면 먼저 뜬 쪽만 브리지를 연다) |
| 운영 애셋 | `/Game/Animation/Hero/ABP_Hero_Base`(스켈레톤 `/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F`, 부모 `UAstralAnimInstance`) — **읽기만. 변경은 사용자 승인 배치만** |
| 빌드 애셋 | `/Game/Animation/Hero/ABP_Hero_McpBuild` — `phase5_build_hero.py` 가 생성/덮어쓰기 |
| 테스트 애셋 | `/Game/Animation/Test/ABP_McpTest`(phase3·4·6-1 이 덮어씀) · `/Game/Animation/Test/ABP_McpLayerTest`(phase5) · `ABP_McpDup`·`ABP_McpChild`(phase6-2 가 만들고 지움 — recheck 뒤 남지 않는다) · `BS_McpTest`·`BS_McpTest2D`·`ABP_McpBsTest`(phase6-3) · `ABP_McpBindTest`(phase6-4) · `ALI_McpTest`·`ABP_McpLayerBase`·`ABP_McpLayerProvider`(phase6-4b) — 전부 덮어쓰기 대상 |
| 테스트 실행 | `PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/<script>.py [--recheck]`. **(6-5) 전체는 `Tools/mcp/run_all.py`** 하나 — 에디터 기동 → 단계 9개 → quit → 재기동 → `--recheck` 7개 → quit, 결과 `Tools/mcp/results/<date>.json`(이미 뜬 에디터에 붙이려면 `--attach`, `--only a,b` · `--skip-recheck`) |

`UAstralAnimInstance` 노출 변수(전부 BlueprintReadOnly, 스레드 안전 스냅샷): `Speed`, `Acceleration`, `MovementDirection`(float) · `bIsOnGround`, `bIsInAir`, `bIsJumping`, `bIsFalling`, `bHasMovementInput`(bool) · `GroundDistance`(float). 규칙 `var` 와 `K2Node_VariableGet` 의 `variable` 가 이들을 가리킨다. 프로젝트 정책: 복잡 조건은 C++ AnimInstance 에서 bool 로 계산하고 규칙은 `var` 기본.

구현 가능성과 API 사용 여부는 **설치된 5.7.4 엔진 소스**를 기준으로 검증한다. 다른 버전 예제를 그대로 쓰지 않는다. 확인한 API 는 phase1 §B 와 각 "Phase N 결과" 절에 경로가 있다.

---

### 3. 아키텍처 (확정 · 구현됨)

```text
Claude Code (AI Agent)
        │  stdio MCP  (.mcp.json → Tools/mcp/.venv python server.py)
        ▼
Python MCP 서버   Tools/mcp/anim_graph_mcp/server.py  — Tool 17개 선언·입력 스키마(함수 시그니처·docstring = Claude 가 보는 설명, op 사전 포함)
                  Tools/mcp/anim_graph_mcp/bridge.py  — HTTP 전달, 토큰, request_id, 오류 봉투 정규화 (테스트 스크립트와 공유)
        │  POST http://127.0.0.1:18765/v1/<tool>
        ▼
에디터 플러그인   Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/
  ├─ AnimGraphMcpEditorModule.cpp  설정 로드, Dispatcher·Bridge 조립, Tool 등록, 콘솔 명령
  ├─ Bridge/AnimMcpHttpBridge      엔진 HTTPServer 라우트(tool 당 1개), 토큰 전처리기, 응답 쓰기
  ├─ Bridge/AnimMcpDispatcher      JSON 파싱 → request_id 캐시(256) → 핸들러 → 봉투
  ├─ Bridge/AnimMcpTypes           오류 코드, FAnimMcpError, 파라미터 헬퍼, 진단, JSON 헬퍼
  ├─ Core/AnimMcpAssetResolver     경로 정규화 · AssetRegistry 존재 확인 · 로드 · 클래스 검증
  ├─ Core/AnimMcpGraphInspector    (읽기만) 그래프 트리 · 노드 · 핀 · 연결 · 변수 · 프로퍼티 값 · 바인딩 · 상태머신 뷰 · revision 해시
  ├─ Core/AnimMcpBlueprintFactory  AnimBP 생성 (팩토리 미사용, CreateBlueprint 재현; overwrite 는 AssetOps 삭제 경유)
  ├─ Core/AnimMcpAssetProtection   (6-2) ini 보호 목록 — 삭제·덮어쓰기 전 검사, ASSET_PROTECTED
  ├─ Core/AnimMcpAssetOps          (6-2) 삭제 기계(ForceDelete 뒤 잔존 패키지·파일 정리, 파일 잠금 재시도) · 참조자 조회 · 복제(Guid 보존 스코프)
  ├─ Core/AnimMcpBlendSpaceFactory (6-3) BlendSpace 1D/2D 생성(팩토리 재현 · 축은 프로퍼티 시스템 · 샘플 사전 검증) · 요약
  ├─ Core/AnimMcpPropertyBinding   (6-4a) 핀 Property Binding — 노드 Binding 객체·PropertyBindings 맵을 리플렉션으로, 경로 해석은 IPropertyAccessEditor
  ├─ Core/AnimMcpAnimLayer         (6-4b) 레이어 인터페이스 생성(CreateBlueprint 재현 + UAnimationGraph 함수 그래프 + 입력 포즈) · ImplementNewInterface · 레이어 노드 설정(SetupFromLayerId 재현) · 조회
  ├─ Core/AnimMcpPropertyRules     set_property 허용 목록 · JSON↔ImportText(구조체·배열 재귀) · 값→JSON(enum 이름)
  ├─ Core/AnimMcpGraphMutator      (쓰기 기계) 노드 생성·분리·복귀 · 핀 연결/해제 · 속성 · 애셋 · 핀 노출 · 블렌드 포즈 · 상태/전이/Entry · VariableGet · LayerSetup 검증 · conduit/alias/rename
  ├─ Core/AnimMcpTransitionRule    규칙 AST 검증·정규화 · K2 노드 생성(전이·conduit 규칙 그래프 공용) · 주석 원문/해시
  ├─ Core/AnimMcpOperations        (정책) operations 배치: 참조 해석(ref·result_of·graph:{ref}) · 사전 검증 · 트랜잭션 · 되돌리기 저널 · revision 대조
  ├─ Core/AnimMcpCompiler          컴파일(FCompilerResultsLog → node_guid) · 강제 저장
  ├─ Core/AnimMcpAutomationRunner  (6-5) FAutomationTestFramework 직접 구동 — 테스트 목록(필터) · 잡(순차 StartTestByName → Execute{Network,Latent}Commands → StopTest) · 동기 완료/FTSTicker 진행 · 테스트별 타임아웃 · 잡 기술(JSON)
  ├─ Tests/AnimMcpSmokeTests.cpp    (6-5) IMPLEMENT_COMPLEX_AUTOMATION_TEST "AnimGraphMcp.Smoke.AnimBlueprint" — ini SmokeTestPaths 아래 AnimBP 마다 테스트 1개(WITH_DEV_AUTOMATION_TESTS)
  └─ Tools/AnimMcpTools_{Status,Inspect,Assets,Graph,Compile,Editor,Layers,Automation}.cpp  Tool 핸들러 (얇음; Editor = quit_editor · Layers = 레이어 인터페이스 2종 · Automation = run/poll_automation_tests)
        ▼
Unreal Editor API (게임 스레드)  →  Animation Blueprint
```

**확정 결정과 근거(요약, 상세는 phase1 §C)** — Python 만으로는 불가(파이썬 래퍼는 `UEdGraph::Nodes`·핀을 노출하지 않음) → 그래프 조회·편집은 전부 C++ · 엔진 내장 `HTTPServer`(게임 스레드 티커, 기본 바인드 localhost) · Remote Control API·오픈소스 Unreal MCP 미채택 · MCP 서버는 얇은 프록시(그래프 로직 없음) · 긴 작업은 동기(에디터 프레임 블로킹; 클라 타임아웃 60초, 컴파일 포함 180초) · Inspector 는 쓰지 않고 Mutator 는 트랜잭션 밖에서 호출되지 않는다(Preview/Apply 분리의 코드상 표현) · `FJsonObject` 를 두 컨테이너에 넣지 않는다(순환 → 직렬화 무한 재귀 → 에디터 크래시).

---

### 4. MCP Tool 인터페이스 (17개 · 6-2 에서 3개, 6-3 에서 1개, 6-4b 에서 2개, 6-5 에서 2개 추가)

Python 함수명 = 플러그인 라우트명. 응답 봉투 `{ok, tool, request_id, result, error:{code,message,details?}, diagnostics[]}` + `http_status`. 같은 `(tool, request_id)` 재전송은 캐시 봉투.

| Tool | 입력 | 비고 |
| :--- | :--- | :--- |
| `get_editor_status` | — | 토큰 면제. 엔진·프로젝트·PIE·플러그인·열린 에디터·포트·Tool 목록 · (6-2) `process_id` · `protection{assets,paths}` · `dirty_package_count` |
| `get_anim_blueprint_info` | `asset_path` | revision · parent_class · target_skeleton · graphs[](+`interface_guid`) · **variables[]**(규칙 `var`/VariableGet 대상) · linked_anim_layers[] · (6-4b) `implemented_interfaces[{interface, blueprint, graphs[]}]` · `layers[{name, graph_guid, interface\|null, interface_guid, group, input_poses[]}]` — 인터페이스 BP 자신의 레이어도 여기 |
| `get_anim_graph_structure` | `asset_path, graph_guid?, depth=1` | depth 0 = 그 그래프만, -1 = 전부. §5 |
| `list_animation_assets` | `skeleton?, asset_class=all, path_prefix=/Game, limit=200, details=false` | AnimSequence·BlendSpace·AnimMontage·AnimComposite. (6-3) `details` 면 BlendSpace 항목에 `blendspace{class, dimensions, axes[], samples[], sample_count, grid_sample_count, segment_count, triangle_count, interpolate_using_grid, anim_length, loop}` (로드 필요 — 좁은 경로에서만) |
| `create_blendspace` (6-3) | `asset_path, skeleton, dimensions:1\|2, axes:[{name,min,max,grid=4,snap=false,wrap=false}], samples?:[{animation, value:[x]\|[x,y]}], preview_mesh?, overwrite=false, save=false` | 1 → `UBlendSpace1D`, 2 → `UBlendSpace`. 생성 전 전부 검증(BAD_REQUEST details.field/reason: `OUT_OF_RANGE`·`DUPLICATE_POSITION`·`SKELETON_MISMATCH`·`ADDITIVE_MISMATCH`·`ENGINE_REJECTED`), 실패 시 애셋 없음. 응답 = 요약 + `created, saved`. 2D 기본은 삼각분할(그리드 0) |
| `create_animation_blueprint` | `asset_path, skeleton, parent_class, preview_mesh?, overwrite=false` | overwrite 는 기존 애셋 **삭제** — 사용자 확인 후 |
| `preview_graph_operations` | `asset_path, operations[]` | 그래프 불변. `valid, revision, planned[{index, op, ref, ok, error?, note?}], would_*`. 미생성 ref 는 클래스 수준 검증 + `note` |
| `apply_graph_operations` | `asset_path, operations[], expected_revision?, compile=false, save=false` | 사전 전체 검증 → 트랜잭션 → 실패 시 롤백+`rollback_verified` → `refs, revision_before/after, operations[], compile, saved` |
| `compile_animation_blueprint` | `asset_path, save_on_success=false` | `ok, num_errors, num_warnings, status, messages[{level, text, node_guid, graph_guid}]` |
| `save_animation_blueprint` | `asset_path` | 강제 저장 |
| `duplicate_animation_blueprint` (6-2) | `source_path, dest_path, overwrite=false, preserve_node_guids=true, save=false` | info + `duplicated, source_path, source_revision, node_guids_preserved, saved`. overwrite 는 보호 검사 뒤 삭제. **revision 은 원본과 다르다**(오브젝트 참조 프로퍼티에 패키지 이름) — 구조 비교는 Guid·연결로 |
| `delete_animation_blueprint` (6-2) | `asset_path, confirm(필수 true), force=false` | AnimBP 만. 보호 → `ASSET_PROTECTED`, 참조 중 → `ASSET_REFERENCED`(details.referencers; `force` 면 삭제 + `REFERENCES_BROKEN` 진단). 응답 `deleted, forced, referencers[]` |
| `create_anim_layer_interface` (6-4b) | `asset_path, layers:[{name, group?, input_poses?:[...]}], overwrite=false, save=false` | ALI 애셋(BPTYPE_Interface, 부모 UAnimLayerInterface) + 레이어 그래프 + 그룹 + 입력 포즈 → **항상 컴파일**(구현 전제). 이름: 유효 식별자·중복 불가·`AnimGraph` 예약. 응답 = info + `layers` + `compile` + `created` |
| `implement_anim_layer_interface` (6-4b) | `asset_path, interface, compile=true, save=false` | ABP 가 ALI 구현 → 레이어마다 그래프(Root + 입력 포즈 자동). 거부: `ALREADY_IMPLEMENTED` · `GRAPH_NAME_CONFLICT` · `NOT_LAYER_INTERFACE` · `NOT_COMPILED`/`NO_LAYERS` · 대상이 인터페이스. 응답 = info + `implemented_interfaces` + `layers` + `compile` |
| `run_automation_tests` (6-5) | `filter(필수), timeout=120, dry_run=false` | `FAutomationTestFramework` 직접 구동(Session Frontend 없음). `filter` 는 테스트 전체 경로의 접두/부분 문자열(대소문자 무시; `"AnimGraphMcp.Smoke"` · `"AstralBreak."` · `"."` 전부). 잡을 만들고 즉시 진행 — 지연(latent) 명령이 없으면 **동기 완료**(`done=true`, 결과 포함), 있으면 FTSTicker 로 프레임마다 진행하고 `poll` 로 본다. 응답 `{job_id, filter, total, completed, passed, failed, done, ok, elapsed, running?, tests[{name, state:passed\|failed\|not_started\|timeout, duration, errors[], warnings[]}]}`. `dry_run` 은 매칭 목록만(`tests[{name, display_name, command, source_file, source_line}]`). 매칭 0 → `total 0, done` + 진단 `NO_TESTS`. 거부: 다른 잡 진행 중/`GIsAutomationTesting` → BAD_REQUEST. 잡은 최근 16개 보관 |
| `poll_automation_tests` (6-5) | `job_id` | 같은 모양. 모르는 id → BAD_REQUEST |
| `quit_editor` (6-2) | `save_dirty=false, discard_dirty=false` | 더티 패키지 있고 둘 다 false → `DIRTY_PACKAGES`(에디터 유지). `save_dirty` 는 **콘텐츠만** 저장(맵은 안 함, 더티 맵은 `discard_dirty` 로만). 응답 `quit_requested, process_id, saved_packages[], discarded_packages[], was_pie` → `wait_for_exit.py` |

**오류 코드**: `BAD_REQUEST`(400) · `UNAUTHORIZED`(401) · `ASSET_PROTECTED`(403) · `TOOL_NOT_FOUND`/`ASSET_NOT_FOUND`/`GRAPH_NOT_FOUND`/`NODE_NOT_FOUND`/`PIN_NOT_FOUND`(404) · `ASSET_EXISTS`/`REVISION_MISMATCH`/`ASSET_REFERENCED`/`DIRTY_PACKAGES`(409) · `CONNECTION_REJECTED`/`PROPERTY_NOT_ALLOWED`/`COMPILE_FAILED`/`SAVE_FAILED`(400) · `INTERNAL`(500). Python 측: `EDITOR_GONE`, `TIMEOUT`, `TRANSPORT`, `BAD_RESPONSE`.

---

### 5. 구조 조회 응답 (schema_version 1.1)

`get_anim_graph_structure`: `asset_path, revision, root_graph_guid, depth, graphs[{graph_guid, name, class, parent_graph_guid, owner_node_guid, owner_node_class, node_count}], nodes[{node_guid, graph_guid, class, title, pos, asset, is_sink, comment?, pins[{name, dir, type, default, hidden, linked[]}], sub_graphs[], properties{}, optional_pins[{property, shown, can_toggle, bound}], has_binding}], connections[{from:{node,pin}, to:{node,pin}}], state_machines[{graph_guid, name, node_guid, entry_node_guid, entry_state, states[{node_guid, name, class, kind(state|conduit|alias), bound_graph_guid, always_reset_on_entry?, outgoing_transitions[], incoming_transitions[], (conduit) rule_graph_guid·rule_generated·rule_source·rule_modified·rule_node_count, (alias) global·aliased_states[]·aliased_state_names[]}], transitions[{node_guid, name, from, to, from_name, to_name, priority_order, crossfade_duration, blend_mode, bidirectional, disabled, automatic, automatic_trigger_time, shared_rules, rule_graph_guid, rule_generated, rule_source, rule_modified, rule_node_count}]}]`

- **노드 식별**은 항상 `node_guid`(+ 배치 내 임시 `ref`). 표시 이름은 응답에만.
- **revision**: 그래프·노드·핀·연결·EditAnywhere 프로퍼티·FAnimNode 멤버 값을 결정적 순서로 SHA1. 속성만 바꿔도 바뀌고 조회·컴파일로는 안 바뀐다. 규칙 그래프는 재생성하면 Guid 가 바뀌므로 멱등은 주석 비교로 구현(§7).
- `properties{}` 는 허용 목록 값만. 구조체 배열(LayerSetup) 은 객체 배열, enum 은 이름(`"BranchFilter"`).
- (6-4a) `optional_pins[]` 의 `bound` 핀은 `binding{path[], path_text, type, context, promotion}` 를 갖는다. revision 은 바인딩을 포함한다(`B|이름|경로|타입|컨텍스트`; 없으면 줄 없음 → 기존 값 호환).
- 상태 내부 포즈 그래프의 sink 는 `AnimGraphNode_StateResult`, 입력 핀 `Result`. conduit 의 `bound_graph_guid` 는 규칙 그래프(포즈 그래프 아님).

---

### 6. op 사전 (19종 · `preview_graph_operations` / `apply_graph_operations` 의 `operations[]`)

**참조 형태** — 노드: `{"node": "<guid>"}` · `{"ref": "<같은 배치 앞 add_* 의 ref>"}` · `"<guid>"` · `{"result_of": {node|ref}}`(그 상태의 StateResult 노드). 핀은 이름. `add_node.graph`: 생략=루트 AnimGraph · `"<graph_guid>"` · `{node|ref}`(상태 → 그 포즈 그래프; conduit·alias 거부).

| op | 입력 | 동작 · 롤백 |
| :--- | :--- | :--- |
| `add_node` | `ref?, graph?, class, pos?[x,y], asset?, enum?(BlendListByEnum), properties?{name:value}` | Creator 생성 → enum → properties. 롤백 `DestroyNode` |
| `add_node` (변수) | `ref?, graph?, class:"K2Node_VariableGet", variable, pos?` | AnimGraph·상태 포즈 그래프만(전이/conduit 규칙·상태머신 그래프 거부). 출력 핀 = 변수 이름. asset·enum·properties 불가 |
| `connect` | `from:{node\|ref\|result_of, pin}, to:{…}` | 스키마 `CanCreateConnection`→`TryCreateConnection`. 포즈 출력 핀은 단일 연결(공유는 Save/UseCachedPose). 롤백 = 양끝 링크 스냅샷 |
| `disconnect` | `from, to?` | `to` 없으면 from 의 링크 전부 |
| `remove_node` | `node\|ref` | 분리 보관 → 성공 확정 시 `DestroyNode`. Root·Result·Entry 거부. 상태·conduit·alias 를 지우면 연결 전이 연쇄 |
| `set_property` | `node\|ref, property, value` | 허용 목록(§6-1) 리플렉션 → PostEditChange → 노출된 비연결 핀 기본값 동기화. NodeRef(`UseCachedPose.SaveCachedPoseNode`) 는 value 가 노드 참조. LayerSetup 은 포즈 수·본 검증 |
| `set_asset` | `node\|ref, asset` | `SetAnimationAsset` |
| `expose_pin` | `node\|ref, property, visible?=true` | `SetPinVisibility`(ReconstructNode) |
| `add_blend_pose` | `node\|ref, entry?` | LayeredBoneBlend / BlendListByEnum(entry 필수) |
| `add_state` | `ref?, sm:{node\|ref} \| graph, name?, pos?` | BoundGraph+StateResult 자동. 응답 `bound_graph_guid` |
| `add_transition` | `ref?, from:{…}, to:{…}, properties?, rule?` | 끝점은 상태·conduit·alias. **전이 대상 alias 는 단일 상태·global 아님** |
| `set_entry_state` | `sm \| graph, state:{…}` | Entry → State |
| `set_transition_rule` | `node\|ref (전이\|conduit), rule` | AST → 규칙 그래프 전체 재생성, 멱등. conduit 에 `automatic` 불가 |
| `add_conduit` | `ref?, sm \| graph, name?, pos?, rule?` | 규칙 그래프 자동. 응답 `rule_graph_guid` |
| `add_state_alias` | `ref?, sm \| graph, name?, pos?, states:[{node\|ref}] \| global:true` | 대상은 같은 상태머신의 실제 상태만(conduit·alias 불가). global+states 동시 불가 |
| `set_alias_states` | `node\|ref, states \| global` | 전이 대상 alias 는 단일 상태 유지해야 함 |
| `rename_node` | `node\|ref, name` | 상태·conduit·alias·상태머신 노드. 엔진 이름 검증기(중복·금지 문자·레이어 함수명 충돌). 응답 `old_name` |
| `bind_pin` (6-4a) | `node\|ref, property, path:[...]\|"A.B"` | 노출 가능 핀을 AnimInstance 프로퍼티/BlueprintPure 함수 경로에 묶는다(VariableGet 불필요). 핀은 노출되고(`pin_exposed`) **링크가 없어야** 한다(`PIN_LINKED` — 같은 배치의 앞선 disconnect 도 사전 검증은 모른다 → 두 배치). 경로는 `SkeletonGeneratedClass` 에서 해석(`PATH_UNRESOLVED`), 타입은 승격 허용(`TYPE_INCOMPATIBLE`). 응답 `type(Property\|Function), path_text, promotion, replaced`. 롤백 = 이전 항목 복원 + 핀 가시성 |
| `unbind_pin` (6-4a) | `node\|ref, property` | 바인딩 제거(핀은 노출 유지). 없으면 BAD_REQUEST. 롤백 = 항목 복원 |
| `add_node` + `layer` (6-4b) | `class:"AnimGraphNode_LinkedAnimLayer", layer` | 구현한 인터페이스 레이어 또는 자체 레이어 그래프 이름. 같은 ABP 에서 **한 레이어는 노드 하나만**(`LAYER_IN_USE`, 컴파일 규칙). 입력 포즈 핀은 레이어 시그니처대로. 응답 `linked_layer{}` |
| `set_linked_layer` (6-4b) | `node\|ref, layer` | 레이어 재지정. 입력 포즈 핀에 링크가 있으면 `PINS_LINKED`(먼저 `disconnect` — 사라지는 핀이 고아로 남아 컴파일 오류). 응답 `old_layer`. 롤백 = 이전 레이어 참조 복원 |

**6-1. set_property 허용 목록** (`Core/AnimMcpPropertyRules.cpp`): SequencePlayer `bLoopAnimation, PlayRate, StartPosition, PlayRateBasis` · BlendSpacePlayer `bLoop, PlayRate, StartPosition, X, Y, bResetPlayTimeWhenBlendSpaceChanges` · Slot `SlotName, bAlwaysUpdateSourcePose` · SaveCachedPose `CacheName` · UseCachedPose `SaveCachedPoseNode`(NodeRef) · LayeredBoneBlend `bMeshSpaceRotationBlend, bMeshSpaceScaleBlend, bBlendRootMotionBasedOnRootBone, LODThreshold, BlendMode, LayerSetup` · BlendListBase(ByBool·ByEnum) `BlendTime[]` · BlendListByEnum `BoundEnum, VisibleEnumEntries`(읽기 전용) · Transition `CrossfadeDuration, PriorityOrder, BlendMode, Bidirectional, bDisabled, bAutomaticRuleBasedOnSequencePlayerInState, AutomaticRuleTriggerTime` · State `bAlwaysResetOnEntry`. 구조체 값은 USTRUCT 멤버 이름 그대로의 JSON 객체(`LayerSetup = [{"BranchFilters": [{"BoneName": "spine_01", "BlendDepth": 0}]}, …]`, 포즈당 1개, 본은 TargetSkeleton 에 존재해야 함).

**6-2. 규칙 AST** (`Core/AnimMcpTransitionRule`)

```jsonc
{"var": "bIsFalling"}                                                              // BlueprintVisible 프로퍼티 → VariableGet(self)
{"not": R} · {"and": [R, R, ...]} · {"or": [R, R, ...]}                             // Not_PreBool · BooleanAND/OR 사슬
{"compare": {"op": ">", "left": {"var": "Speed"}, "right": {"literal": 10.0}}}           // (op × 타입) → KismetMathLibrary. Real·Int·Int64 전 연산, Bool·Name 은 ==/!=. 한쪽은 non-literal
{"literal": true}                                                                   // 상대 핀 기본값. 최상위 literal 은 Result 핀 기본값 (노드 없음)
{"call": {"function": "FMax", "class"?: "/Script/...", "args": {"A": R, "B": R}}}  // BlueprintPure ∧ ThreadSafe 메타 ∧ 소유 ∈ {AnimInstance 사슬, UKismetMathLibrary}
{"automatic": true, "trigger_time"?: -1.0}                                          // 전이만. 그래프 없이 플래그 (최상위 전용)
```

정규화 JSON + 그래프 해시를 규칙 그래프의 `UEdGraphNode_Comment`(첫 줄 `AnimGraphMcp rule_source v1`) 에 기록 → Inspector 가 `rule_source` 복원, 해시 불일치 = `rule_modified`. 같은 원문 + 사람 편집 없음 = no-op(`unchanged:true`). float 변수 → double 함수 핀은 PC_Real 로 항상 호환.

**6-3. 지원 노드**(생성·연결·컴파일 확인): SequencePlayer · BlendSpacePlayer · Slot · LayeredBoneBlend · BlendListByBool · BlendListByEnum · Save/UseCachedPose · StateMachine · Inertialization(허용 목록 없음) · K2Node_VariableGet · Root(기존만). 그 외 `UAnimGraphNode_Base` 파생 비추상 클래스도 `add_node` 는 받지만 허용 목록·테스트가 없다. **속성 변경 원칙**: ① 노드별 공식 Setter ② 허용 목록 리플렉션 ③ 노드별 특수 처리. 임의 프로퍼티 범용 명령은 금지.

---

### 7. 그래프 변경 안전성 (구현됨)

- **Preview / Apply 분리**: 같은 입력, preview 는 검증 함수만. 미생성 ref 를 가리키는 op 는 클래스 수준 검증 + `note`(apply 에서 완전 검증).
- **Batch**: 적용 전 **전체** 사전 검증(하나라도 실패면 무변경) → `FScopedTransaction` 안에서 순차 적용 → 각 op 는 적용 직전 재검증. 사전 검증은 같은 배치의 앞선 `add_blend_pose` 수를 더해 LayerSetup 항목 수를 본다.
- **되돌리기 저널**: 각 op 가 적용 직후 되돌리기 클로저를 등록 → 실패 시 역순 실행 → `Cancel` → `revision_after == revision_before` 로 **복구 검증**(`rollback_verified`). 에디터 Undo 는 쓰지 않는다. 핀은 (노드, 핀 이름). 분리 보관 노드는 성공 확정 시 `DestroyNode`.
- **충돌 감지**: `expected_revision` 불일치 → `REVISION_MISMATCH`, 무변경. **멱등**: 같은 `(tool, request_id)` 재전송은 캐시, 같은 규칙 AST 재적용은 no-op.
- **애셋 보호**: 운영 애셋은 읽기만(변경은 사용자 승인 배치). `overwrite` 명시 필요. `save` 기본 false, 컴파일 오류 시 저장 안 함. (6-2) 파괴 연산(delete · create/duplicate overwrite)은 `[AnimGraphMcp] ProtectedAssets/ProtectedPaths` 를 먼저 보고, 삭제는 `confirm` + 참조 검사(`force`), 종료는 더티 검사(`save_dirty`/`discard_dirty`).

---

### 8. 테스트 · 스크립트 · 문서

| 파일 | 역할 |
| :--- | :--- |
| `Tools/mcp/phase3_test.py` | 범용 편집 7절 (거부 10종 · 롤백 · revision 규칙) |
| `Tools/mcp/phase4_test.py` | 상태머신 7절 + **B2**(상태 내부 · VariableGet→BlendSpace.X · 거부 6종 · 롤백) |
| `Tools/mcp/phase5_test.py` | LayerSetup 1·2 포즈 · 조회 왕복 · 거부 6종 · 롤백 (`ABP_McpLayerTest`) |
| `Tools/mcp/phase6_1_test.py` | 운영 구조 1:1 배치 하나(op 39) · 뷰 · rename · set_alias_states · 거부 9종 · 10-op 롤백 · conduit/alias 삭제 연쇄 |
| `Tools/mcp/phase6_2_test.py` | 애셋 수명 5절 — A 상태(Tool 12·process_id·protection) · B 복제(Guid 보존/재생성 · 거부 4종 · 보호 2종) · C 복제본 편집·저장·create overwrite 보호 · D 삭제(거부 5종 · 참조 중 → force · 자식 삭제 · 디스크 확인) · E quit(DIRTY_PACKAGES → save_dirty → 프로세스 소멸). `--recheck` 는 저장 확인 + 정리 삭제 + 더티 없는 quit. `--no-quit` 으로 종료 생략 |
| `Tools/mcp/phase6_5_test.py` | 검증 자동화 5절 — A dry_run(스모크 테스트 = 경로 아래 ABP 9개, 운영 애셋 포함) · B 스모크 실행(동기 완료 · 전부 passed · 레이어 제공자는 passed+경고) · C 프로젝트 테스트 `AstralBreak.` 18개 · poll 동일 · 부분 필터 · D 거부 3종(filter 누락 · 모르는 job_id · 매칭 0 → NO_TESTS) · E 음성(빈 상태 ABP `ABP_McpSmokeNeg` 를 만들어 그 애셋만 failed → 삭제). `--recheck` 는 스모크·프로젝트 재실행 |
| `Tools/mcp/run_all.py` | **통합 러너** — 에디터 기동(`UnrealEditor.exe`, 브리지 폴링, 25초 대기) → phase3/4/5/6-1/6-3/6-4/6-4b/6-5/6-2(`--no-quit`) → `quit_editor discard_dirty` + `wait_for_exit` → 재기동 → `--recheck` 5/6-1/6-3/6-4/6-4b/6-2/6-5 → quit. 단계마다 PASS/FAIL·소요·`[FAIL]` 줄·꼬리 15줄을 `Tools/mcp/results/<date>.json` 에 남기고 종료 코드 0/1. `--attach`(뜬 에디터에 붙어 단계만) · `--only a,b` · `--skip-recheck` · `--engine` · `--project` |
| `Tools/mcp/phase6_4b_test.py` | Linked Anim Layer 8절 — A 인터페이스 생성 · B 구현 · C 레이어 노드 · D 구현 그래프 채우기 · E 공급자 ABP · F set_linked_layer(PINS_LINKED·롤백) · G 거부 14종 · H 저장. `--recheck` |
| `Tools/mcp/phase6_4_test.py` | Property Binding 6절 — A bind X←Speed · B 재바인딩(점 경로·함수 경로) · C unbind · D 롤백 2종 · E 거부 9종 + 같은 배치 ref · F 저장. `--recheck` |
| `Tools/mcp/phase6_3_test.py` | BlendSpace 5절 — A 원본 요약(list details) · B 1D 재현(원본과 축·샘플·grid·선분 동일) · C 새 ABP 에 BlendSpacePlayer+Speed→X 컴파일·저장 · D 2D(삼각형 1) · E 거부 12종 + 미생성 확인. `--recheck` |
| `Tools/mcp/phase5_build_hero.py` | `ABP_Hero_McpBuild` 를 도구만으로 생성(루트 레이어 + 상태머신 1:1), 비교 문서 생성. `--overwrite` · `--recheck` · `--diff-only` |
| `Tools/mcp/smoke_test.py` · `wait_for_bridge.py` · `wait_for_exit.py` · `mcp_client_test.py` · `debug_dump_rules.py` | 스모크 · 기동 폴링 · 종료 폴링(6-2) · MCP 클라 · 규칙 덤프 |
| `Tools/mcp/phase*_state.json` · `Tools/mcp/results/*.json` | 재시작 `--recheck` 비교용 · 러너 결과 — **임시 파일**(커밋 제외 후보) |
| `.claude/plans/animbp-automation-phase1.md` | 근거 문서 — §A 환경 · §B API 검증표 · §C 결정 · §F 계획 · "Phase 2 ~ 6-1 결과" |
| `.claude/plans/animbp-phase5-hero-diff.md` | 빌드 vs 운영 비교(자동 생성) |

모든 `--recheck` 는 에디터 재시작 뒤 revision·노드 Guid 집합·state_machines 뷰 일치를 본다. 테스트 순서 주의: phase3·4·6-1 이 같은 `ABP_McpTest` 를 덮어쓰므로 **recheck 할 스크립트를 마지막에 실행**한다. 6-5 이후의 표준 순서 = `run_all.py` 가 하는 그대로: 기동 → phase3 → 4 → 5 → 6-1 → 6-3 → 6-4 → 6-4b → 6-5 → 6-2(`--no-quit`) → quit(discard) → 재기동 → phase5/6-1/6-3/6-4/6-4b/6-2/6-5 `--recheck` → quit. 6-5 recheck 는 6-2 recheck(ABP_McpDup 정리) 뒤에 둬야 스모크 애셋 수가 1차와 같다.

---

### 9. 작업 규칙 (이 프로젝트·이 사용자 기준)

1. **구현 전 확인.** 설계 선택지가 갈리는 곳(§12 의 ❓·확정 항목)은 코드 전에 사용자에게 선택지를 제시하고 확정한다. 분석·조회·실측은 묻지 않고 진행한다. 조사 결과로 선택지가 사라지면(소스에서 규칙이 확정되면) 묻지 않고 근거를 남긴다(6-1 §9-1 사례).
2. **엔진 API 는 소스에서 확인하고 경로를 남긴다.** 추측으로 "가능하다"고 쓰지 않는다. 확인 못 한 것은 ❓.
3. **파일 읽기는 Read, 검색은 Grep/Glob.** Bash 로 파일을 cat·루프하지 않는다. `Saved/`·`Binaries/`·`Intermediate/` 는 권한상 읽을 수 없다.
4. **빌드는 두 구성 모두**, 에디터를 내리고. 빌드 뒤 에디터 재기동 → `wait_for_bridge` → 25초 대기 → 테스트.
5. **에디터는 내가 띄우고 내린다**(§2). 사용자에게 "에디터 켜 주세요"라고 하지 않는다. 작업이 끝나면 테스트 에디터를 `quit_editor` 로 내린다(사용자는 자기 DebugGame 에디터로 PIE 확인). 사용자 에디터에는 `quit_editor`·`delete` 를 쓰지 않는다.
6. **Git Bash 접두.** `/Game/...` 인자는 `MSYS_NO_PATHCONV=1`, 한글 출력 `PYTHONIOENCODING=utf-8`. `tasklist //FI` 와는 같은 셸에서 쓰지 않는다.
7. **`FJsonObject` 를 두 컨테이너에 넣지 않는다.**
8. **운영 애셋 `ABP_Hero_Base` 는 읽기만.** 변경은 사용자 승인 뒤 `expected_revision` 배치 하나로, 컴파일·저장까지 하고 PIE 는 사용자.
9. **커밋은 사용자가 한다.** 변경 파일 목록과 커밋 메시지 초안만 제시.
10. **문서 관례.** 설계·핸드오프 md 는 `.claude/plans/`. 단계가 끝나면 phase1 문서 끝에 "Phase N 결과" 절(기존 형식), 이 문서 §1 표·§12 진행 상황·§13 갱신, 메모리 `project_animbp-automation.md` 갱신.
11. **MCP Tool 목록은 세션 시작 시 고정.** 새 Tool 은 재시작 전까지 `Tools/mcp/phaseN_test.py`(HTTP 직접 호출)로만 검증.
12. **실측으로 확인된 엔진 함정 (코드에 그대로 적용)**:
    - 포즈 출력 핀은 단일 연결(공유는 Save/UseCachedPose) · 노출 핀의 기본값이 구조체 값보다 우선(컴파일·숨김 시 핀→구조체) · 비기본값 핀은 재구성 때 고아로 남는다(`SetSavePinIfOrphaned(false)`).
    - 전이 노드는 자기 핀 링크 0 통지에 스스로 `DestroyNode` 한다 → 분리·복원은 `BreakLinkTo`(통지 없음) · 상태 삭제는 전이를 먼저 분리.
    - 주석 노드 `PostPlacedNewNode` 가 `NodeComment` 를 "Comment" 로 되돌린다 → 원문은 Finalize 뒤에 쓴다.
    - MinimalAPI 클래스의 protected 멤버·비내보내기 함수는 공개 가상 함수나 리플렉션으로 우회. 헤더의 네임스페이스 안 `class X*` 전방선언은 네임스페이스 스코프 타입을 만든다(전역에서 선언).
    - **`ExportText_Direct(Delta=null)` 는 0 값(enum 0·숫자 0)을 빈 문자열로 낸다**(Property.cpp:1005) → 조회·롤백 저장은 `ExportTextItem_Direct`, enum 은 `GetNameStringByValue`. revision 해시는 기존 호환을 위해 `ExportText_Direct` 유지.
    - 기존 노드의 없는 핀은 **사전 검증**에서 걸린다 → 롤백 경로 테스트는 같은 배치의 ref 노드로 만든다.
    - 전이 **대상** alias 는 정확히 하나의 상태를 가리키고 global 이 아니어야 컴파일된다(AnimStateAliasNode.cpp:52-55). `UAnimStateAliasNode::OnRenameNode` 는 검증 없이 이름만 바꾼다 → 도구가 먼저 검증. conduit BoundGraph 는 `UAnimationTransitionGraph`(conduit 스키마), Result 는 `TransitionResult`/`bCanEnterTransition`.
    - **애니 그래프 설계**: 상체 레이어 슬롯은 전신 슬롯 **출력**(캐시) 뒤에 둔다. 나란히 두면 비어 있는 상체 슬롯이 로코모션 상체로 전신 몽타주를 덮는다(PIE 실측).
    - **(6-2) 참조 중인 패키지는 ForceDelete 가 파일을 남긴다**(ObjectTools.cpp:2535-2550) → `ResetLoaders` → `UnloadPackages` → 잔존 객체 임시 패키지 이동 → `PackageDeleted` → 파일 직접 삭제 → `ScanModifiedAssetFiles`. 링커를 안 끊으면 Windows 에서 파일 삭제가 실패한다. `FEditorFileUtils::SaveDirtyPackages(bFastSave)` 는 더티 ABP 를 저장하지 않는다 → 애셋마다 `SaveLoadedAsset`. 복제본 revision 은 원본과 다르다(패키지 이름이 프로퍼티 ExportText 에 섞임) — 구조 비교는 Guid·연결로. 방금 저장한 파일은 잠깐 잠길 수 있다 → 파일 삭제는 0.3초×10회 재시도.
    - **(6-4a) Property Binding**: 바인딩 객체(`UAnimGraphNodeBinding_Base`)는 Private 헤더·private 맵 → 노드 `Binding` 과 `PropertyBindings` 를 리플렉션(FObjectPropertyBase·FMapProperty·FScriptMapHelper)으로. `GetMutableBinding()` 은 불완전 타입이라 `GetClass()` 도 못 부른다. 타입(PinType·promotion)은 `ReconstructNode` 가 계산. **사전 검증은 같은 배치의 앞선 op 를 모른다** — 링크 해제 뒤 bind 는 두 배치. 사전 검증 실패의 `reason` 은 `details.planned[i].error.details` 에 있다.
    - **(6-4b) Linked Layer**: 인터페이스는 먼저 컴파일(구현은 `MD_AnimBlueprintFunction` 메타를 본다) · 구현 그래프는 `ImplementedInterfaces[].Graphs`(FunctionGraphs 아님) · 구현 그래프의 Root+입력 포즈는 엔진이 자동 생성 · `SetupFromLayerId`/`SetLayerName` 은 호출 불가(MinimalAPI·protected) → `Node.Layer/Interface/InstanceClass`·`InterfaceGuid` + 리플렉션 `FunctionReference.SetSelfMember` 로 재현 · 한 레이어는 ABP 당 노드 하나 · 링크된 입력 포즈 핀은 레이어 변경 전 끊는다 · 그룹 기본값 "DefaultSharedGroup". 적용 중 실패의 `reason` 은 `details.cause`.
    - **(6-5) Automation 직접 구동**: `FAutomationTestFramework::Get()` 에 `SetRequestedTestFilter(EAutomationTestFlags_FilterMask)` + `LoadTestModules()` 뒤 `GetValidTestNames` 로 목록 · `StartTestByName(cmd, 0, fullpath)` 는 `GIsSlowTask`/PIE 면 시작하지 않고 `GIsAutomationTesting` 을 세운다(도구는 그 뒤 플래그를 확인해 `not_started`) · 이후 `ExecuteNetworkCommands()`·`ExecuteLatentCommands()` 가 둘 다 true 가 되면 `StopTest(FAutomationTestExecutionInfo&)` 로 결과(`bSuccessful`·`Duration`·`GetEntries()` 의 Error/Warning) · 타임아웃은 `DequeueAllCommands()` 뒤 StopTest. `AddWarning` 은 실패가 아니다(`bElevateLogWarningsToErrors` 기본 false). 스모크는 `IMPLEMENT_COMPLEX_AUTOMATION_TEST`(`GetTests` 가 AssetRegistry 로 ABP 를 열거, 명령 = 오브젝트 경로) · 컴파일은 `FKismetEditorUtilities::CompileBlueprint(BP, SkipGarbageCollection, &Log)` · **레이어 제공자 ABP(인터페이스 구현만, 루트 미사용 — Lyra `ABP_ItemAnimLayersBase`)는 루트 미연결이 정상** → 경고로 낮춤.
    - **(6-3) BlendSpace**: `BlendParameters` 는 protected·setter 없음 → Persona 처럼 프로퍼티 시스템으로(고정 필드 6개). `AddSample` 은 범위 밖을 거부하지 않고 **축을 늘린다**(ExpandRangeForSample) → 도구가 먼저 거부. 2D 기본은 삼각분할(그리드 0, `bInterpolateUsingGrid=false`), 1D 는 선분+그리드. 추가 뒤 `ResampleData → ValidateSampleData → PostEditChange`.

---

### 10. 사용자 확정 사항 이력

| 날짜 | 결정 |
| :--- | :--- |
| 2026-10-10 | strafe 는 락온이 아니라 추후 "사격 후 일정 시간 strafe 모드" — Phase 5 범위 밖(선행 작업은 phase1 §F Phase 5 보류 표) |
| 2026-10-15 | `remove_node` 롤백 = 분리 보관 · `set_property` 허용 목록 = 확장 목록 · 규칙 입력 = JSON 트리 AST · `call` 화이트리스트 · 상태머신 조회 = structure 응답 확장 |
| 2026-10-16 | Phase 5 범위 = **새 ABP 처음부터 재구성**(복제본 아님) · 도구 추가 = VariableGet 노드·LayerSetup · BlendSpace 재사용 · Attack 슬롯 = `UpperBody` 신설 · 운영 애셋 UpperBody 레이어 적용 승인(재배선 포함) · Phase 6 전부 진행, 6-1~6-6 분할 |
| 2026-10-17 (6-4b) | §12-C = **Lyra 식 레이어 분리를 쓸 계획 → 저작까지 구현**. 범위 = Tool 2개(create/implement) + op(add_node layer · set_linked_layer) + 조회 확장, 포즈 입력만 |
| 2026-10-17 (6-5) | 검증 자동화 설계 = **FAutomationTestFramework 직접 구동**(run_automation_tests 가 잡 시작 + FTSTicker 진행, 동기 완료면 응답에 결과, 아니면 poll_automation_tests) · 스모크 테스트는 **플러그인 안**(`AnimGraphMcp.Smoke.AnimBlueprint`, ini 경로 아래 ABP 전부 — 컴파일·빈 상태·끊긴 캐시·빈 레이어) · `run_all.py` 통합 러너 |
| 2026-10-16 (6-3) | §12-B 는 질문 없이 해소 — Persona 가 리플렉션(프로퍼티 핸들)으로 축을 편집하므로 같은 경로를 고정 필드에만 사용. 사용자 결정 없음 |
| 2026-10-16 (6-2) | 삭제 보호 = **A안** ini `[AnimGraphMcp] ProtectedAssets/ProtectedPaths` + `confirm` 필수 + 참조 중이면 `force` 없이는 거부 · `quit_editor` 는 더티 패키지가 있으면 `save_dirty`/`discard_dirty` 없이는 거부 · 복제는 노드 Guid 보존 기본 |

---

### 11. 6-1 까지의 Phase 5 · 6-1 결과 요약 (상세는 phase1 문서)

- **Phase 5**: 실측 결과 운영 애셋에 이동·점프가 완성돼 있어 범위를 새 ABP 재구성으로 변경. VariableGet 노드 · LayerSetup(구조체 JSON 재귀) · `phase5_test.py` · `phase5_build_hero.py` · 비교 문서. 운영 애셋에 UpperBody 레이어 적용 → 첫 배선 실수(상체 슬롯을 전신과 나란히) 를 PIE 에서 발견 → 전신 슬롯 뒤 `FullBody` 캐시로 재배선, 사용자 확인·커밋.
- **Phase 6-1**: op 4종(conduit·alias·set_alias_states·rename) · conduit 규칙 · 같은 배치 `graph:{ref}`·`result_of` · Inspector alias/conduit 필드. `phase6_1_test.py` PASS, 회귀·recheck PASS, 히어로 빌드가 운영 상태머신 1:1. 운영 애셋 관찰: `EndInAir → IdleAlias` 가 `Speed >= 20`, `→ MoveAlias` 가 `Speed < 20`(반대로 보임, 사람이 확인할 항목 — 도구는 그대로 재현).
- **Phase 6-2**: Tool 3개(duplicate·delete·quit_editor) · 보호 목록(`Core/AnimMcpAssetProtection`) · 삭제/복제 기계(`Core/AnimMcpAssetOps`) · `wait_for_exit.py`. `phase6_2_test.py` PASS, 회귀·recheck PASS. 실측 3건(참조 중 패키지의 파일 잔존 · SaveDirtyPackages 실패 · 자식 ABP 의 NO_ANIM_GRAPH)은 phase1 "Phase 6-2 결과".
- **Phase 6-3**: `create_blendspace`(1D/2D, 축·샘플, 사전 검증) · `list_animation_assets details` · `Core/AnimMcpBlendSpaceFactory`. `phase6_3_test.py` PASS, 회귀·recheck PASS. 원본 `BS_Hero_Locomotion1D` 1:1 재현. 실측(AddSample 의 축 확장 · 2D 삼각분할 · 파일 잠금 재시도)은 phase1 "Phase 6-3 결과".
- **Phase 6-4a**: op `bind_pin`/`unbind_pin` · `Core/AnimMcpPropertyBinding` · Inspector `binding{}` · revision 포함. `phase6_4_test.py` PASS(VariableGet 없이 X←Speed 컴파일 0 에러, 함수 경로, 롤백, 거부 9종), 회귀·recheck PASS.
- **Phase 6-4b**: Tool `create_anim_layer_interface`·`implement_anim_layer_interface` · op `add_node layer`·`set_linked_layer` · `Core/AnimMcpAnimLayer` · Inspector `implemented_interfaces`·`layers`·`linked_layer`. `phase6_4b_test.py` PASS(인터페이스 3 레이어 → 구현 → 레이어 노드 2 연결 컴파일 0 에러 → 공급자 ABP), 회귀·recheck PASS. 실측 규칙 2건(레이어는 ABP 당 노드 하나 · 링크된 입력 포즈 핀은 변경 전 끊기)은 phase1 "Phase 6-4b 결과".
- **Phase 6-5**: Tool `run_automation_tests`·`poll_automation_tests` · `Core/AnimMcpAutomationRunner` · 스모크 `Tests/AnimMcpSmokeTests.cpp`(`AnimGraphMcp.Smoke.AnimBlueprint`, ini `SmokeTestPaths`) · 러너 `run_all.py`. `phase6_5_test.py` PASS(스모크 9 ABP 전부 passed · 프로젝트 테스트 18/18 · 음성 1건 검출), `run_all.py` 로 전 단계·recheck PASS. 실측: 레이어 제공자 ABP 는 루트 미연결이 정상 → 경고. 상세는 phase1 "Phase 6-5 결과".

---

### 12. 남은 단계 (6-6) 와 확정할 것

```text
6-2 애셋 수명 ✅ ─────┐
6-3 BlendSpace ✅ ────┼──▶ 6-5 검증 자동화 ✅ ──▶ 6-6 범용화 검증
6-4a 바인딩 ✅ · 6-4b 레이어 ✅ ┘
```

공통 완료 기준: 두 구성 빌드(경고 0) · 단계 테스트 PASS · phase3/4/5/6-1/6-2/6-3/6-4/6-4b 회귀 PASS · 재시작 `--recheck` 일치 · phase1 "Phase 6-N 결과" · 이 문서 갱신 · 사용자 커밋.

**6-4a Property Binding — 완료 (2026-10-17)**: op 2종 · `Core/AnimMcpPropertyBinding` · `phase6_4_test.py`. ❓(에디터가 바인딩을 채우는 경로)는 소스로 해소. 상세는 phase1 "Phase 6-4a 결과".

**6-4b Linked Anim Layer — 완료 (2026-10-17, §12-C 사용자 확정)**: Tool 2개 · op 2종 · `Core/AnimMcpAnimLayer` · `phase6_4b_test.py`. 포즈 입력만(값 파라미터·`InstanceClass` 지정·인터페이스에 레이어 추가/삭제는 범위 밖 — 필요 시 후속). 상세는 phase1 "Phase 6-4b 결과".

**6-2 애셋 수명 — 완료 (2026-10-16)**: §4 Tool 3개 · 보호 목록 · `wait_for_exit.py` · `phase6_2_test.py`. 두 ❓ 는 소스로 해소(복제본 Guid 는 `TheSameNodeGuid` 스코프로 보존 · 응답은 동기 소켓 쓰기 + FTSTicker 1프레임 지연). 상세는 phase1 "Phase 6-2 결과".

**6-3 BlendSpace 생성 — 완료 (2026-10-16)**: `create_blendspace` · `list_animation_assets details` · `Core/AnimMcpBlendSpaceFactory` · `phase6_3_test.py`. §12-B 는 소스로 해소(Persona 가 프로퍼티 시스템으로 축 편집 — 공개 setter 없음). 상세는 phase1 "Phase 6-3 결과".

**6-5 검증 자동화 — 완료 (2026-10-17, 사용자 확정 설계)**: `run_automation_tests {filter, timeout, dry_run}` + `poll_automation_tests {job_id}`(FAutomationTestFramework 직접 구동 — 동기 완료면 응답에 결과, 아니면 FTSTicker 진행 + poll; ❓ 완료 델리게이트는 쓰지 않고 `ExecuteLatentCommands` 가 비면 `StopTest` 로 수집) · `Core/AnimMcpAutomationRunner` · 스모크 `AnimGraphMcp.Smoke.AnimBlueprint`(플러그인 `Tests/`, ini `SmokeTestPaths` 아래 ABP 전부: 컴파일 0 에러 · 루트 Output Pose 연결(레이어 제공자는 경고) · 빈 상태 · 끊긴 UseCachedPose · 무효 LinkedAnimLayer · 빈 레이어 구현(경고)) · `run_all.py` · `phase6_5_test.py`. 실측·미검증 경로(latent 테스트 — 프로젝트·스모크 테스트는 전부 동기)는 phase1 "Phase 6-5 결과".

**6-6 범용화 검증** — 플러그인 소스에서 `AstralBreak`·`/Game/Animation/Hero`·`AstralAnimInstance` grep 0건(테스트 제외; 스모크의 기본 경로 `/Game/Animation` 은 ini 로 바꿀 수 있어 허용) · **§12-D 두 번째 프로젝트**에 `Plugins/AnimGraphMcp` + `Tools/mcp` + `.mcp.json` 복사 → 빌드 → `smoke_test.py` → Phase 2.5 시나리오 재현(엔진 마네킹 스켈레톤) · `Tools/mcp/README.md`·`Plugins/AnimGraphMcp/README.md` 를 설치·설정·Tool·op 사전·오류 코드·제약으로 갱신.

**코드 전에 사용자와 확정할 것(남은 1건)** — A(6-2) 사용자 확정, B(6-3) 소스로 해소, C(6-4b) 2026-10-17 사용자 확정·구현됨(§10).
- **D (6-6)** 두 번째 프로젝트 — 새 빈 프로젝트(권장 `D:/UE5Projects/AnimMcpSandbox`) vs 기존 프로젝트.

(§9-1 alias 방향은 6-1 에서, §12-A 는 6-2 에서 사용자 확정, §12-B 는 6-3 에서 소스로 해소, §12-C 는 6-4b 에서 사용자 확정, 6-5 설계(직접 구동·start/poll·플러그인 안 스모크·run_all)는 2026-10-17 사용자 확정.)

---

### 13. 미커밋 변경 (6-5, 2026-10-17 기준)

Phase 6-4(a+b) 까지 커밋됨(`37a2042`). 아래가 6-5 미커밋이다. `Tools/mcp/phase*_state.json` · `Tools/mcp/results/*.json` 은 임시 파일(gitignore 후보). 테스트 애셋은 회귀가 덮어쓴 결과.

```
 M .claude/plans/animbp-automation-handoff-phase6-2.md  (이 문서 — 6-5 반영, 최종 지시 = 6-6)
 M .claude/plans/animbp-automation-phase1.md            ("Phase 6-5 결과" 절 · 부록 엔진 파일)
 M Config/DefaultEngine.ini                             ([AnimGraphMcp] +SmokeTestPaths=/Game/Animation)
?? Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Core/AnimMcpAutomationRunner.{h,cpp}   (Automation 구동 기계)
?? Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Tools/AnimMcpTools_Automation.cpp      (run/poll_automation_tests)
?? Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Tests/AnimMcpSmokeTests.cpp            (AnimGraphMcp.Smoke.AnimBlueprint)
 M Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Tools/AnimMcpTools.h · AnimGraphMcpEditorModule.cpp   (RegisterAutomationTools)
 M Tools/mcp/anim_graph_mcp/server.py                   (Tool 2개 문서)
 M Tools/mcp/README.md                                  (Tool 17개 · run_all)
?? Tools/mcp/phase6_5_test.py · run_all.py · phase6_5_state.json(임시) · results/(임시)
 M Tools/mcp/phase3/4/5/6_1/6_2/6_3/6_4/6_4b_state.json  (임시)
 M Content/Animation/Test/*.uasset                       (회귀 재저장)
```

커밋 메시지 초안: `Feat: AnimGraph MCP Phase 6-5 — 에디터 내 Automation 실행 Tool(run/poll_automation_tests), AnimBP 구조 스모크 테스트, 통합 러너 run_all.py`

---

### 최종 지시 (새 세션용 — Phase 6-6)

Phase 6-6(범용화 검증)을 수행한다. 먼저 이 문서 전체와 phase1 문서 "Phase 2.5 결과"(최소 수직 통합 시나리오) · "Phase 6-2 결과"(quit_editor·wait_for_exit) · "Phase 6-5 결과"(run_all·스모크) 를 읽는다. **코드 전에 §12-D 를 사용자와 확정한다** — 두 번째 프로젝트를 새 빈 프로젝트(권장 `D:/UE5Projects/AnimMcpSandbox`, 엔진 마네킹 스켈레톤)로 만들지 기존 프로젝트를 쓸지, 그리고 그 프로젝트의 생성·빌드를 내가 해도 되는지. 작업: ① 플러그인 소스(`Plugins/AnimGraphMcp/Source`, 테스트 `Tests/` 제외)에서 `AstralBreak`·`/Game/Animation/Hero`·`AstralAnimInstance`·`SKEL_UE5_F` 를 Grep 해 0건으로 만든다(스모크의 기본 경로 `/Game/Animation` 은 ini 로 바꿀 수 있으므로 허용) · ② 두 번째 프로젝트에 `Plugins/AnimGraphMcp` + `Tools/mcp`(venv 제외) + `.mcp.json` + ini `[AnimGraphMcp]` 를 복사 → 두 구성 빌드 → 에디터 기동 → `smoke_test.py` → Phase 2.5 시나리오(ABP 생성 → SequencePlayer→Root 연결 → 컴파일 → 저장 → 재조회) 를 `run_automation_tests "AnimGraphMcp.Smoke"` 까지 재현 → 발견한 프로젝트 의존(경로·클래스·ini 기본값)을 플러그인 쪽에서 고친다 · ③ `Tools/mcp/README.md`·`Plugins/AnimGraphMcp/README.md`(없으면 신설)를 설치(uproject 등록·ini·venv·.mcp.json)·설정·Tool 17개·op 19종 사전·오류 코드·제약·테스트(run_all)로 갱신. 완료 기준: 두 프로젝트 모두 두 구성 빌드(경고 0) · 이 프로젝트에서 `run_all.py` ALL PASS · 두 번째 프로젝트에서 스모크·Phase 2.5 재현 PASS · phase1 "Phase 6-6 결과" · 이 문서 §1(재사용 ✅)·§12·§13 갱신 · 메모리 갱신 → 변경 파일 목록과 커밋 메시지 초안 제시(두 번째 프로젝트는 이 저장소 밖 — 커밋 대상 아님). 운영 애셋은 읽기만 한다. 에디터는 내가 띄우고 `quit_editor` 로 내린다(사용자 에디터에는 쓰지 않는다).
