# AI Animation Blueprint Automation
## 개발 지침서 (개정 2판) — Phase 5 착수용 핸드오프

> 작성 2026-10-16 · 브랜치 `feat/ai_auto_ABP` · 기준 엔진 UE 5.7.4 소스 빌드
> 최초 지침서(Phase 1 착수 시 전달)를 **Phase 4 까지 구현된 상태**에 맞춰 다시 쓴 것이다. 완료된 Phase 는 결과만 남기고, 미확정이던 항목은 전부 확정값으로 바꾸었다.
> 설계 근거·엔진 소스 경로·API 검증표·각 Phase 의 상세 결과는 [animbp-automation-phase1.md](animbp-automation-phase1.md) 에 있다 (§B API 검증표 · §C 아키텍처 결정 · §F 단계 계획 · §G 위험 · "Phase 2/2.5/3/4 결과"). 구조를 재논의하기 전에 그 문서를 먼저 읽는다.
> 이 문서는 [animbp-automation-handoff-phase3.md](animbp-automation-handoff-phase3.md) 를 대체한다.
> **2026-10-16 추기: Phase 5 완료·커밋. 6-1 완료 뒤 통합본 [animbp-automation-handoff-phase6-2.md](animbp-automation-handoff-phase6-2.md)(개정 4판) 가 이 문서를 대체한다.** 실측 결과 운영 애셋에 이동·점프가 이미 완성돼 있어 범위를 "새 ABP 처음부터 재구성" 으로 바꿨다(§14.0 사용자 확정). 결과·추가 도구·함정은 phase1 문서 "Phase 5 결과", 빌드 vs 운영 비교는 [animbp-phase5-hero-diff.md](animbp-phase5-hero-diff.md). §13·§17 만 갱신했고 나머지 절은 착수 시점 그대로다.

---

### 1. 프로젝트 개요 및 최종 목표 (변경 없음)

Unreal Engine 5.7.4 Source Build 환경에서 Claude Code 가 Animation Blueprint 를 생성·조회·수정·컴파일·검증할 수 있게 하는 AI Agent Tool 시스템을 개발한다. 사용자가 애니메이션 애셋과 동작 설계 가이드를 주면 Claude Code 가 실행 중인 에디터와 상호작용해 실제 AnimBP 를 구성한다. 기존 AnimBP 는 전체 재생성이 아니라 구조를 분석하고 필요한 부분만 안전하게 수정한다.

핵심 목표 중 현재 상태:

| 목표 | 상태 |
| :--- | :---: |
| AnimBP 애셋 자동 생성 및 조회 | ✅ |
| 기존 AnimGraph · State Machine 구조 분석 | ✅ 그래프 트리 · 노드 · 핀 · 연결 · 허용 목록 프로퍼티 값 · 바인딩 보유 · 노출 핀 · 상태머신 뷰(states/transitions/entry/rule_source) |
| AnimGraph 노드 생성·수정·삭제 및 Pin 연결 | ✅ op 8종 (§8) |
| State Machine · State · Transition 자동 구성 | ✅ op 4종 (§9). 상태 삭제 시 전이 연쇄 |
| Transition Rule 및 블렌딩 조건 설정 | ✅ JSON AST → 규칙 그래프 (멱등, 원문 복원, 사람 편집 감지) · 전이 properties |
| AnimSequence · BlendSpace · Montage 연결 | 🔶 애셋 플레이어 노드에 할당·교체 가능. **BlendSpace 생성은 미구현** (Phase 5 결정 사항) |
| 기존 C++ AnimInstance 와 연동 | ✅ 부모 클래스 지정 · 변수 목록 조회 · 규칙에서 변수 참조(`var`) · ThreadSafe 함수 호출(`call`) |
| 컴파일 및 오류 분석 | ✅ 노드 Guid 매핑 포함 |
| 저장 · 변경 검증 · 실패 복구 | ✅ revision 해시 · 되돌리기 저널 · 롤백 검증 |
| 다른 UE5 프로젝트에서 재사용 가능한 MCP Tool | 🔶 플러그인은 프로젝트 비의존. 타 프로젝트 재현 검증은 Phase 6 |

이 프로젝트의 목표는 특정 캐릭터 AnimBP 하나를 만드는 것이 아니라 범용 도구를 만드는 것이다. Phase 5 는 그 도구로 **실제 캐릭터를 처음 구성해 보는 단계**이며, 여기서 드러나는 부족분은 도구 쪽에 반영한다.

---

### 2. 개발 환경 (확정)

| 항목 | 값 |
| :--- | :--- |
| Engine | UE 5.7.4 소스 빌드, `D:/UnrealSource/UnrealEngine-5.7.4-release` (`Engine/Build/Build.version`) |
| Project | `D:/UE5Projects/AstralBreak` — 런타임 모듈 1개 `AstralBreak`, 에디터 모듈 없음(플러그인이 대신) |
| 플러그인 | `Plugins/AnimGraphMcp/` — 에디터 전용 모듈 `AnimGraphMcpEditor`. uproject 에 등록됨 |
| MCP 서버 | Python 3.13, `Tools/mcp/anim_graph_mcp/`, 전용 venv `Tools/mcp/.venv` (gitignore), 패키지 `mcp 2.3.0` (`MCPServer` API — 1.x 의 `FastMCP` 아님), `httpx` |
| Claude Code 등록 | 프로젝트 루트 `.mcp.json` → 서버명 `anim-graph-mcp`. 세션 시작 시 Tool 9개가 `mcp__anim-graph-mcp__*` 로 보인다 |
| 통신 | Claude Code ↔ server.py: stdio MCP · server.py ↔ 플러그인: `POST http://127.0.0.1:18765/v1/<tool>` JSON |
| 설정 | `Config/DefaultEngine.ini [AnimGraphMcp] Port=18765 / bRequireToken=True / bAutoStart=True` (전부 기본값, ini 미기재). 커맨드라인 `-AnimGraphMcpPort=`. 콘솔 `AnimGraphMcp.Start/Stop/Status` |
| 토큰 | 에디터 기동마다 `Saved/AnimGraphMcp/token`, 종료 시 삭제. `get_editor_status` 만 토큰 면제 |
| 빌드 | `Engine/Build/BatchFiles/Build.bat AstralBreakEditor Win64 {Development\|DebugGame} -Project=<uproject> -WaitMutex -NoHotReload`. **두 구성 모두** (사용자는 평소 DebugGame 에디터). 플러그인만 바뀌면 10~15초 |
| 툴체인 | MSVC 14.38 (UBT 가 14.44 를 금지) |
| 운영 애셋 | `/Game/Animation/Hero/ABP_Hero_Base` (스켈레톤 `/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F`, 부모 `UAstralAnimInstance`) — **읽기 전용. Phase 5 는 복제본에서 작업** |
| 테스트 애셋 | `/Game/Animation/Test/ABP_McpTest` — 덮어쓰기 가능. 같은 스켈레톤. 현재 내용: 상태머신(Idle·Run, 전이 2, 규칙) — 상태 내부는 비어 있음(§3-1) |
| 테스트 실행 | `PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/phaseN_test.py [--recheck]` |

구현 가능성과 API 사용 여부는 **설치된 5.7.4 엔진 소스**를 기준으로 검증한다. 다른 버전의 예제 코드를 그대로 쓰지 않는다. 검증된 API 와 소스 경로는 phase1 문서 §B 와 각 "Phase N 결과" 절에 있다.

---

### 3. AI Agent 의 최종 사용 시나리오와 Phase 5 범위

"현재 캐릭터의 AnimBP 에 기본 이동, 점프 및 공격 애니메이션 시스템을 구성해 줘. 지정한 AnimSequence·BlendSpace·Montage 를 쓰고 기존 C++ 시스템과 연동해 줘."

현재 Tool 로 이 시나리오의 1~12 단계(분석·조회·계획·생성·연결·규칙·검증·컴파일·보고)가 전부 가능하다. 아직 없는 것은 BlendSpace **생성**(기존 애셋 할당은 가능)과 복제 Tool 이다.

**Phase 5 적용 대상**

- **Free Locomotion** — Idle·Walk·Run. 기존 `BS_Vesper_Locomotion1D`(`Speed` 축) 재사용이 1순위 (§14 결정 사항)
- **Jump** — Start · Loop/Fall · Landing. 전이 규칙은 `bIsInAir` / `bIsJumping` / `bIsFalling` / `bIsOnGround`(`var`) 와 `automatic`
- **Attack** — Montage 는 게임플레이(GAS)가 재생하므로 AnimGraph 쪽은 Slot(`SlotName`) + LayeredBoneBlend(Full/Upper Body) 구성이 대상
- **Lock-On Locomotion(strafe)** — **보류 유지**. 2026-10-10 결정: 락온이 아니라 추후 "사격 후 일정 시간 유지되는 strafe 모드". 현재 코드는 `bOrientRotationToMovement=true` 라 strafe 자세가 성립하지 않는다. 선행 작업은 phase1 §F Phase 5 보류 표(S-A/B/C)

`UAstralAnimInstance` 노출 변수(전부 BlueprintReadOnly, 스레드 안전 스냅샷): `Speed`, `Acceleration`, `MovementDirection`(float) · `bIsOnGround`, `bIsInAir`, `bIsJumping`, `bIsFalling`, `bHasMovementInput`(bool) · `GroundDistance`(float) · `GameplayTagPropertyMap`. 규칙 AST 의 `var` 는 이들을 가리킨다.

**3-1. 운영 애셋의 현재 구조 (2026-10-16 덤프)** — 상태머신 `Locomotions` 1개 · 상태 11(`Idle`, `Move`, `JumpSources`, `JumpSelector`, `JumpStart`, `FallLoop`, `FallLand`, `EndInAir`, `JumpFallInterruptSources`, Alias 2: `IdleAlias`, `MoveAlias`) · 전이 12 · 그래프 21 · 노드 69 · 연결 50 · Linked Layer 0 · 바인딩 0. 즉 **이동·점프 상태머신은 사람이 이미 만들어 둔 상태**다. Phase 5 첫 작업은 이 구조를 `get_anim_graph_structure(depth=-1)` 로 덤프해 "이미 있는 것 / 비어 있는 것 / 추가할 것" 표를 만드는 것이다.

**3-2. 테스트에서 검증하지 않은 경로** — Phase 4 테스트는 상태·전이·규칙만 만들고 **상태 내부 그래프(BoundGraph)는 비워 두었다**(StateResult 만 있어 레퍼런스 포즈). 설계상 상태 내부는 별도 op 없이 `add_node`/`connect` 에 `graph: <bound_graph_guid>` 를 넘겨 채우지만, 이 경로는 아직 실측하지 않았고 StateResult 입력 핀 이름(`Result` 로 추정)도 미확인이다. **Phase 5 의 첫 번째 실측 항목.**

---

### 4. 아키텍처 (확정 · 구현됨)

```text
Claude Code (AI Agent)
        │  stdio MCP  (.mcp.json → Tools/mcp/.venv python server.py)
        ▼
Python MCP 서버   Tools/mcp/anim_graph_mcp/server.py  — Tool 선언·입력 스키마(함수 시그니처·docstring = Claude 가 보는 설명)
                  Tools/mcp/anim_graph_mcp/bridge.py  — HTTP 전달, 토큰, request_id, 오류 봉투 정규화
        │  POST http://127.0.0.1:18765/v1/<tool>  (JSON, X-AnimMcp-Token)
        ▼
에디터 플러그인   Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/
  ├─ AnimGraphMcpEditorModule.cpp  설정 로드, Dispatcher·Bridge 조립, Tool 등록, 콘솔 명령
  ├─ Bridge/AnimMcpHttpBridge      엔진 HTTPServer 라우트(tool 당 1개), 토큰 전처리기, 응답 쓰기
  ├─ Bridge/AnimMcpDispatcher      JSON 파싱 → request_id 캐시(256) → 핸들러 → 봉투
  ├─ Bridge/AnimMcpTypes           오류 코드, FAnimMcpError, 파라미터 헬퍼, 진단, JSON 헬퍼
  ├─ Core/AnimMcpAssetResolver     경로 정규화 · AssetRegistry 존재 확인 · 로드 · 클래스 검증
  ├─ Core/AnimMcpGraphInspector    (읽기만) 그래프 트리 · 노드 · 핀 · 연결 · 변수 · 프로퍼티 값 · 바인딩 · 상태머신 뷰 · revision 해시
  ├─ Core/AnimMcpBlueprintFactory  AnimBP 생성 (팩토리 미사용, CreateBlueprint 재현)
  ├─ Core/AnimMcpPropertyRules     set_property 허용 목록 표 · JSON↔ImportText 변환 · 값→JSON  (Phase 3)
  ├─ Core/AnimMcpGraphMutator      (쓰기 기계) 노드 생성·분리·복귀 · 핀 연결/해제 · 속성 · 애셋 · 핀 노출 · 상태/전이/Entry
  ├─ Core/AnimMcpTransitionRule    규칙 AST 검증·정규화 · K2 노드 생성 · 주석 원문/해시 읽기  (Phase 4)
  ├─ Core/AnimMcpOperations        (정책) operations 배치: 사전 검증 · 트랜잭션 · 되돌리기 저널 · revision 대조
  ├─ Core/AnimMcpCompiler          컴파일(FCompilerResultsLog → node_guid) · 강제 저장
  └─ Tools/AnimMcpTools_{Status,Inspect,Assets,Graph,Compile}.cpp  Tool 핸들러 (얇음)
        ▼
Unreal Editor API (게임 스레드)  →  Animation Blueprint
```

**확정 결정과 근거(요약)**

- **Python 만으로는 불가.** 파이썬 래퍼는 `BlueprintVisible` 프로퍼티만 노출하고 `UEdGraph::Nodes`·`NodeGuid`·핀은 노출되지 않는다 (phase1 §B-7). 그래프 조회·편집은 전부 C++.
- **엔진 내장 `HTTPServer` 모듈.** `FHttpServerModule` 이 게임 스레드 티커라 핸들러가 게임 스레드에서 실행된다. 기본 바인드 `localhost`. 핸들러 진입에 `ensure(IsInGameThread())`.
- **Remote Control API · 오픈소스 Unreal MCP 는 채택하지 않음** (phase1 §C-1).
- **MCP 서버는 얇은 프록시.** 그래프 로직을 Python 에 두지 않는다.
- **긴 작업은 동기 처리.** 컴파일 등은 에디터 프레임을 블로킹한다(에디터가 실행기). 클라이언트 타임아웃 기본 60초, 컴파일 포함 180초.
- **에디터 기동 직후** 리스너는 먼저 열리고 응답은 로딩 완료 후 온다 → `wait_for_bridge.py` 로 폴링.
- **Inspector 는 쓰지 않고, Mutator 는 트랜잭션 밖에서 호출되지 않는다.** Preview/Apply 분리의 코드상 표현.

---

### 5. UE 5.7.4 API (검증 완료 · 구현에 쓰인 것)

| 용도 | API | 모듈 |
| :--- | :--- | :--- |
| AnimBP 생성 | `FKismetEditorUtilities::CreateBlueprint(...)` + `TargetSkeleton` 3곳 세팅 (팩토리 cpp 재현). `UAnimBlueprintFactory` 는 모달 때문에 미사용 | UnrealEd |
| 그래프 탐색 | `UBlueprint::FunctionGraphs/UbergraphPages/MacroGraphs` + `UEdGraph::SubGraphs` 재귀, `GraphGuid`, `NodeGuid`, `GN_AnimGraph` | Engine · BlueprintGraph |
| 노드 생성 | `FGraphNodeCreator<T>`(`CreateNode(false, Class)` → 위치 → `Finalize()`). Finalize 가 Guid·`PostPlacedNewNode`(서브그래프)·기본 핀을 만든다. 애셋은 `SetAnimationAsset`, 수용 여부 `SupportsAssetClass` | AnimGraph · Engine |
| 핀 연결/해제 | `CanCreateConnection`(MAKE·PROMOTION·BREAK_OTHERS 허용) → `TryCreateConnection` · `BreakSinglePinLink` · `BreakPinLinks` · **`UEdGraphPin::BreakLinkTo`(통지 없음 — 분리·롤백 전용)** | Engine |
| 노드 분리/삭제 | `UEdGraph::RemoveNode(Node, bBreakAllLinks=false)`(Nodes 에서만 제외, 객체 유지) · `AddNode`(복귀) · `DestroyNode`(확정, 서브그래프 제거) | Engine |
| 속성 | `GetFNodeProperty()` 리플렉션 · `ImportText_Direct`/`ExportText_Direct` · `PreEditChange`/`PostEditChangeProperty` · 노출 핀 동기화 `PropertyValueToString_Direct` → `TrySetDefaultValue` | CoreUObject · UnrealEd · BlueprintGraph |
| 핀 노출 | `ShowPinForProperties` 이름 검색 → `SetPinVisibility(bool, index)` (내부 ReconstructNode) | AnimGraph |
| 블렌드 포즈 | `UAnimGraphNode_LayeredBoneBlend::AddPinToBlendByFilter` · BlendListByEnum 은 `ReloadEnum` + `VisibleEnumEntries`(리플렉션) + `Node.AddPose()` + `ReconstructNode` 재현 · 제거 시 `SetSavePinIfOrphaned(false)` | AnimGraph · AnimGraphRuntime |
| 상태머신 | `FGraphNodeCreator<UAnimStateNode>`(BoundGraph 자동) · `FNameValidatorFactory::MakeValidator` · `OnRenameNode` · `FGraphNodeCreator<UAnimStateTransitionNode>` + `CreateConnections(Prev, Next)` · `EntryNode->GetOutputPin()` ↔ `GetInputPin()` | AnimGraph · UnrealEd |
| 규칙 그래프 | `UK2Node_VariableGet::SetFromProperty(Prop, true, Class)` · `UK2Node_CallFunction::SetFromFunction` · `UKismetMathLibrary` 비교/논리 함수 · `FBlueprintEditorUtils::HasFunctionBlueprintThreadSafeMetaData` · `UEdGraphNode_Comment`(원문은 **Finalize 뒤** 기록) | BlueprintGraph · UnrealEd · Engine |
| 핀 타입 | `UEdGraphSchema_K2::ArePinTypesCompatible` — **PC_Real 은 float/double 무관 항상 호환** (EdGraphSchema_K2.cpp:4533) | BlueprintGraph |
| 컴파일 | `FKismetEditorUtilities::CompileBlueprint(BP, None, &Log)`; `FUObjectToken` → 노드 Guid | UnrealEd |
| 저장·삭제 | `UEditorAssetSubsystem::SaveLoadedAsset(BP, false)` · `DeleteAsset` + 잔존 객체 임시 패키지 `Rename` | UnrealEd |
| 트랜잭션 | `FScopedTransaction`; 실패 시 되돌리기 저널 실행 후 `Cancel()`. **`Cancel` 은 기록만 버린다** | UnrealEd |

Phase 5 에서 새로 필요할 수 있는 API: `UEditorAssetSubsystem::DuplicateAsset`(복제 Tool), `UBlendSpaceFactory1D`/`UBlendSpaceFactoryNew` + 축·샘플 설정(`UBlendSpace` 편집 API 미조사 ❓), `FAnimNode_LayeredBoneBlend::LayerSetup` 본 필터(`FInputBlendPose::BranchFilters`) 설정 ❓.

---

### 6. Python 과 C++ 의 역할 구분 (확정)

- **Python**: MCP 서버(Tool 선언·스키마), HTTP 프록시, 테스트 스크립트. 그래프 로직 없음.
- **C++**: 조회·생성·편집·컴파일·저장 전부.
- 기존 `Tools/ue_exec.py`(Python 원격 실행)는 운용 보조로만. 에디터를 못 찾는 경우가 있어 테스트 에디터 종료는 `taskkill //PID <pid> //F` 로 대신했다(§16-5).

---

### 7. AnimGraph 구조 조회 (구현됨)

**`get_anim_blueprint_info`**: `asset_path, revision, parent_class, parent_anim_blueprint, is_template, target_skeleton, preview_mesh, blueprint_type, status, anim_graph_guid, graphs[{graph_guid, name, class, parent_graph_guid, owner_node_guid, owner_node_class, node_count}], variables[{name, cpp_type, pin_category, pin_subcategory, source, owner_class, read_only}], linked_anim_layer_count, linked_anim_layers[]`

**`get_anim_graph_structure`** (schema_version 1.1): `asset_path, revision, root_graph_guid, depth, graphs[], nodes[{node_guid, graph_guid, class, title, pos, asset, is_sink, comment?, pins[{name, dir, type, default, hidden, linked}], sub_graphs[], properties{}, optional_pins[{property, shown, can_toggle, bound}], has_binding}], connections[{from, to}], state_machines[{graph_guid, name, node_guid, entry_node_guid, entry_state, states[{node_guid, name, class, kind(state|conduit|alias), bound_graph_guid, always_reset_on_entry?, outgoing_transitions[], incoming_transitions[]}], transitions[{node_guid, name, from, to, from_name, to_name, priority_order, crossfade_duration, blend_mode, bidirectional, disabled, automatic, automatic_trigger_time, shared_rules, rule_graph_guid, rule_generated, rule_source, rule_modified, rule_node_count}]}]`

**노드 식별**: 입력은 항상 `node_guid`(+ 배치 내 임시 `ref`). 표시 이름은 응답에만 있다.

**revision**: 그래프 Guid·클래스·이름, 노드 Guid·클래스·위치, 핀 이름·방향·카테고리·기본값·연결, 노드의 EditAnywhere 프로퍼티 + FAnimNode 멤버 값(PoseLink·Transient·FText 제외, 노출 핀은 (이름,bShowPin))을 결정적 순서로 SHA1. `ABP_Hero_Base` 315ms. 속성만 바꿔도 바뀌고, 조회·컴파일로는 바뀌지 않는다.

---

### 8. AnimGraph 편집 op (Phase 3 구현 완료)

전부 `preview_graph_operations` / `apply_graph_operations` 의 `operations[]`. 노드는 `{"node": "<guid>"}` 또는 `{"ref": "<name>"}`(같은 배치의 앞 add_* 가 만든 노드), 핀은 이름.

| op | 입력 | 동작 · 롤백 |
| :--- | :--- | :--- |
| `add_node` | `ref?, graph?(guid, 생략=루트), class, pos?[x,y], asset?, enum?(BlendListByEnum), properties?{name:value}` | Creator 생성 → enum 바인딩 → properties(set_property 경로). **상태 내부는 `graph: <bound_graph_guid>`**. 롤백 = `DestroyNode` |
| `connect` | `from:{node\|ref, pin}, to:{node\|ref, pin}` | `CanCreateConnection` → `TryCreateConnection`. 롤백 = 양 끝 핀 링크 스냅샷(노드, 핀 이름) 복원 |
| `disconnect` | `from, to?` | `to` 있으면 단일 링크, 없으면 전부. 롤백 = 스냅샷 복원 |
| `remove_node` | `node\|ref` | **분리 보관**: 링크를 통지 없이 끊고 Nodes 에서만 제외, 객체 유지. 롤백 = 복귀 + 링크 복원. 성공 확정 시 `DestroyNode`. Root·Result·Entry 거부. 상태 노드면 전이 연쇄(§9) |
| `set_property` | `node\|ref, property, value` | 허용 목록(§8-1) 리플렉션 → PostEditChange → **노출된 비연결 핀 기본값 동기화**. NodeRef 규칙(UseCachedPose.SaveCachedPoseNode)은 value 가 노드 참조. 롤백 = 이전 값 |
| `set_asset` | `node\|ref, asset` | `SetAnimationAsset`. 롤백 = 이전 애셋 |
| `expose_pin` | `node\|ref, property, visible?=true` | `SetPinVisibility`(ReconstructNode). 롤백 = 반대 값 |
| `add_blend_pose` | `node\|ref, entry?` | LayeredBoneBlend / BlendListByEnum(entry 필수) 포즈 추가. 롤백 = 마지막 포즈 제거 |

**8-1. set_property 허용 목록** (`Core/AnimMcpPropertyRules.cpp`): SequencePlayer `bLoopAnimation, PlayRate, StartPosition, PlayRateBasis` · BlendSpacePlayer `bLoop, PlayRate, StartPosition, X, Y, bResetPlayTimeWhenBlendSpaceChanges` · Slot `SlotName, bAlwaysUpdateSourcePose` · SaveCachedPose `CacheName` · UseCachedPose `SaveCachedPoseNode`(NodeRef) · LayeredBoneBlend `bMeshSpaceRotationBlend, bMeshSpaceScaleBlend, bBlendRootMotionBasedOnRootBone, LODThreshold` · BlendListBase(ByBool·ByEnum) `BlendTime[]` · BlendListByEnum `BoundEnum, VisibleEnumEntries`(읽기 전용) · Transition `CrossfadeDuration, PriorityOrder, BlendMode, Bidirectional, bDisabled, bAutomaticRuleBasedOnSequencePlayerInState, AutomaticRuleTriggerTime` · State `bAlwaysResetOnEntry`. 클래스 이름으로 매칭, 상위 클래스 상속. **LayerSetup(본 필터)은 미지원** — Attack 의 Upper Body 블렌드에 필요하면 Phase 5 에서 추가(§14).

**지원 노드** (생성·연결·컴파일 확인): SequencePlayer · BlendSpacePlayer · Slot · LayeredBoneBlend · BlendListByBool · BlendListByEnum · SaveCachedPose/UseCachedPose · StateMachine · Root(기존 노드만). 그 외 `UAnimGraphNode_Base` 파생 비추상 클래스도 `add_node` 는 받지만(클래스 이름 해석) 허용 목록·테스트가 없다.

**속성 변경 원칙**: ① 노드별 공식 Setter ② 허용 목록 기반 리플렉션 ③ 노드별 특수 처리. 임의 프로퍼티 범용 명령은 금지.

---

### 9. State Machine 및 Transition Rule (Phase 4 구현 완료)

| op | 입력 | 동작 · 롤백 |
| :--- | :--- | :--- |
| `add_state` | `ref?, sm:{node\|ref} \| graph:guid, name?, pos?` | Creator → Finalize(BoundGraph+StateResult 자동) → 이름 검증기 → `OnRenameNode`. 응답 `bound_graph_guid`. 롤백 = `DestroyNode` |
| `add_transition` | `ref?, from:{node\|ref}, to:{node\|ref}, properties?, rule?` | Creator → Finalize(BoundGraph+TransitionResult 자동) → `CreateConnections` → properties → rule. 롤백 = `DestroyNode` |
| `set_entry_state` | `sm \| graph, state:{node\|ref}` | Entry → State (스키마가 이전 Entry 연결을 끊음). 롤백 = Entry 핀 스냅샷 |
| `set_transition_rule` | `node\|ref (transition), rule` | 기존 규칙 노드·주석 분리 보관 → AST 에서 전체 재생성 → automatic 플래그. **같은 원문 + 사람 편집 없음 = no-op(`unchanged:true`)**. 롤백 = 생성 제거 + 보관 복귀 + Result 핀 기본값·플래그 복원 |
| `remove_node`(확장) | 상태 노드 | 연결된 전이를 먼저 분리 → 상태 분리. 성공 확정 시 전부 `DestroyNode` |

**규칙 AST** (`Core/AnimMcpTransitionRule`)

```jsonc
{"var": "bIsFalling"}                                                              // BlueprintVisible 프로퍼티 → VariableGet(self)
{"not": R} · {"and": [R, R, ...]} · {"or": [R, R, ...]}                             // Not_PreBool · BooleanAND/OR 사슬
{"compare": {"op": ">", "left": {"var": "Speed"}, "right": {"literal": 10.0}}}           // (op × 타입) → KismetMathLibrary. Real·Int·Int64 전 연산, Bool·Name 은 ==/!=. 한쪽은 non-literal
{"literal": true}                                                                   // 상대 핀 기본값 (노드 없음). 최상위 literal 은 Result 핀 기본값
{"call": {"function": "FMax", "class"?: "/Script/...", "args": {"A": R, "B": R}}}  // BlueprintPure ∧ ThreadSafe 메타(함수 또는 클래스) ∧ 소유 ∈ {AnimInstance 사슬, UKismetMathLibrary}. 모든 입력 파라미터 필수
{"automatic": true, "trigger_time"?: -1.0}                                          // 그래프 없이 플래그만 (최상위 전용)
```

- 정규화 JSON(키 순서 고정) + 생성 직후 그래프 해시를 BoundGraph 의 `UEdGraphNode_Comment`(첫 줄 `AnimGraphMcp rule_source v1`) 에 기록. Inspector 가 `rule_source` 복원, 해시 불일치 = `rule_modified`.
- 멱등은 재생성이 아니라 주석 비교 후 no-op 으로 구현(재생성은 Guid 가 바뀌어 revision 이 달라진다).
- float 변수 → double 함수 핀 허용 확정. `UK2Node_PromotableOperator` 미사용. 프로젝트 정책: 복잡 조건은 C++ AnimInstance 에서 bool 로 계산하고 규칙은 `var` 기본.

---

### 10. MCP Tool 인터페이스 (9개 · Phase 3·4 에서 추가 없음)

Python 함수명 = 플러그인 라우트명. 응답 봉투 `{ok, tool, request_id, result, error:{code,message,details?}, diagnostics[]}` + `http_status`.

| Tool | 입력 | 비고 |
| :--- | :--- | :--- |
| `get_editor_status` | — | 토큰 면제. 엔진·프로젝트·PIE·플러그인·열린 에디터·포트·Tool 목록 |
| `get_anim_blueprint_info` | `asset_path` | §7 |
| `get_anim_graph_structure` | `asset_path, graph_guid?, depth=1` | §7. depth 0 = 그 그래프만, -1 = 전부(상태머신·규칙 그래프 포함) |
| `list_animation_assets` | `skeleton?, asset_class=all, path_prefix=/Game, limit=200` | AnimSequence·BlendSpace·AnimMontage·AnimComposite·all |
| `create_animation_blueprint` | `asset_path, skeleton, parent_class, preview_mesh?, overwrite=false` | overwrite 는 기존 애셋 **삭제** — 사용자 확인 후 |
| `preview_graph_operations` | `asset_path, operations[]` | 그래프 불변. `valid, revision, planned[{index, op, ref, ok, error?, note?}], would_*`. 미생성 ref 는 클래스 수준 검증 + `note` |
| `apply_graph_operations` | `asset_path, operations[], expected_revision?, compile=false, save=false` | 사전 전체 검증 → 트랜잭션 → 실패 시 롤백+`rollback_verified` → `refs, revision_before/after, operations[], compile, saved` |
| `compile_animation_blueprint` | `asset_path, save_on_success=false` | `ok, num_errors, num_warnings, status, messages[{level, text, node_guid, graph_guid}]` |
| `save_animation_blueprint` | `asset_path` | 강제 저장 |

**오류 코드**: `BAD_REQUEST`(400) · `UNAUTHORIZED`(401) · `TOOL_NOT_FOUND`/`ASSET_NOT_FOUND`/`GRAPH_NOT_FOUND`/`NODE_NOT_FOUND`/`PIN_NOT_FOUND`(404) · `ASSET_EXISTS`/`REVISION_MISMATCH`(409) · `CONNECTION_REJECTED`/`PROPERTY_NOT_ALLOWED`/`COMPILE_FAILED`/`SAVE_FAILED`(400) · `INTERNAL`(500). Python 측: `EDITOR_GONE`, `TIMEOUT`, `TRANSPORT`, `BAD_RESPONSE`.

**Tool 추가 시 주의**: Claude Code 에 등록된 MCP Tool 목록은 세션 시작 시점에 고정된다. 새 Tool 은 Claude Code 재시작 전까지 `Tools/mcp/phaseN_test.py`(HTTP 직접 호출)로만 검증한다. Phase 5 후보: `duplicate_animation_blueprint`, `create_blendspace`, `quit_editor`.

---

### 11. 그래프 변경 안전성 (구현됨)

- **Preview / Apply 분리**: 같은 입력. preview 는 검증 함수만.
- **Batch**: 적용 전 **전체** 사전 검증(하나라도 실패면 무변경) → `FScopedTransaction` 안에서 순차 적용 → 각 op 는 적용 직전 재검증.
- **되돌리기 저널**: 각 op 가 적용 직후 자기 되돌리기 클로저를 등록 → 실패 시 역순 실행 → `Cancel` → `revision_after == revision_before` 로 **복구 검증**(`rollback_verified`). 에디터 Undo 는 쓰지 않는다. 핀은 포인터가 아니라 (노드, 핀 이름).
- **충돌 감지**: `expected_revision` 불일치 → `REVISION_MISMATCH`, 무변경.
- **멱등**: 같은 `(tool, request_id)` 재전송은 캐시 봉투. 같은 규칙 AST 재적용은 no-op.
- **애셋 보호**: 운영 애셋은 읽기만. `overwrite` 명시 필요. `save` 기본 false, 컴파일 오류 시 저장 안 함.

---

### 12. 컴파일 및 검증 전략 (구현 상태)

- **구조 검증**: op 사전 검증. 독립 Tool `validate_anim_graph` 는 미구현.
- **컴파일 검증**: 구현됨. 메시지는 노드 Guid 로 매핑. `"X was visible but ignored"` info 는 연결되지 않은 노출 핀에 대한 엔진 메시지로 정상.
- **런타임 검증**: 미구현(Phase 6). `Tools/scripts/run_automation_tests.py`·`read_automation_results.py` 재사용 예정. Phase 5 에서는 PIE 수동 확인이 대신한다.

---

### 13. 단계별 로드맵 (현재 위치: Phase 5 착수 전)

| Phase | 상태 | 내용 |
| :--- | :---: | :--- |
| 1 조사·설계 | ✅ 2026-10-10 | phase1 문서 |
| 2 통신 골격 | ✅ 2026-10-10 | 플러그인·HTTP·Dispatcher·MCP 서버. 커밋 `a669c33` |
| 2.5 최소 수직 통합 | ✅ 2026-10-14 | 생성→노드→연결→컴파일→저장→재조회. Tool 9개. 커밋 `d87608f` |
| 3 범용 AnimGraph 편집 | ✅ 2026-10-15 | op 8종 · 노드 9종 · 프로퍼티/바인딩/노출 핀 · revision 에 프로퍼티. 커밋 `2a85228` |
| 4 State Machine | ✅ 2026-10-15 | op 4종 · 규칙 AST · `state_machines[]`. `phase4_test.py` + phase3 회귀 PASS. **미커밋**(§17) |
| 5 실제 캐릭터 적용 | ✅ 2026-10-16 | 범위 변경(새 ABP 재구성) · VariableGet 노드 · LayerSetup · `phase5_test.py` · `phase5_build_hero.py` · 비교 문서. 검토 뒤 **원본에 UpperBody 레이어 적용·저장(PIE 확인은 사용자)**. 결과는 phase1 문서 "Phase 5 결과" |
| **6 고급·안정화** | ⬜ **다음** | Alias/Conduit 생성 · 이름 변경 op · 같은 배치 `graph:{ref}` · duplicate · create_blendspace · Linked Layer · Property Binding · Automation Test · 타 프로젝트 재현 · `quit_editor` Tool |

---

### 14. 이번 세션의 작업: Phase 5

**목표**: 운영 애셋 `ABP_Hero_Base` 의 **복제본**에 Free Locomotion · Jump · Attack 을 도구만으로 구성해 컴파일 0 에러를 만들고, 원본과의 diff 를 사용자가 검토한 뒤 원본에 적용한다. 도구의 부족분(BlendSpace 생성·LayerSetup·복제 Tool 등)이 드러나면 Phase 5 안에서 도구에 반영한다.

**14.0 구현 전 사용자와 확정할 것** (선택지 제시 → 확정 → 코드)

1. **복제 수단** — (A) `duplicate_animation_blueprint` Tool 추가(`UEditorAssetSubsystem::DuplicateAsset`; 재시작 전까지 HTTP 테스트) vs (B) 사용자가 에디터에서 복제해 경로를 알려 준다.
2. **BlendSpace** — (A) 기존 `/Game/Animation/Hero/Vesper/Common/Locomotion/BS_Vesper_Locomotion1D` 재사용 vs (B) `create_blendspace` 구현(`UBlendSpaceFactory1D`, 축·샘플 설정 API 조사 선행).
3. **적용 순서와 범위** — Free Locomotion → Jump → Attack 순. 운영 애셋에 이미 있는 상태머신(§3-1)을 어디까지 유지하고 무엇을 바꾸는지는 덤프 표를 보고 결정.

**14.1 선행 실측 (확정 없이 진행)**
- 운영 애셋 `depth=-1` 덤프 → "이미 있음 / 비어 있음 / 추가" 표.
- **상태 내부 채우기 경로**(§3-2): 테스트 애셋 `ABP_McpTest` 의 Idle 상태 `bound_graph_guid` 에 `add_node`(SequencePlayer) + `connect`(→ StateResult) → 컴파일 → 롤백 → 재조회. StateResult 입력 핀 이름 확인. `phase4_test.py` 에 절로 추가.

**14.2 복제본 구성** (복제 수단 확정 후)
- Free Locomotion: 상태 내부에 BlendSpacePlayer(`X`←`Speed` 노출 핀 연결 또는 `set_property X`), 전이 규칙 `compare Speed`.
- Jump: 상태 Start·Loop·Land, 규칙 `var bIsJumping/bIsFalling/bIsOnGround`, Land → Idle 은 `automatic`.
- Attack: 루트 그래프에 Slot(`SlotName` = 프로젝트 몽타주 슬롯 — `Tools/data/montages.json`·`AM_Vesper_Sickle_Attack1~3` 에서 확인) + LayeredBoneBlend(Upper Body). **LayerSetup 본 필터가 필요하면 허용 목록에 `set_property` 특수 처리 추가**(구조체 배열 → JSON 변환 설계 필요).
- 각 단계: preview → apply(compile=true) → structure 재조회. 복제본만 저장.

**14.3 검토·적용**
- 원본 vs 복제본 structure diff 를 사람이 읽을 수 있게 정리(노드/연결/상태/전이/규칙 단위) → 사용자 검토.
- 승인 뒤 원본에 같은 operations 를 적용(expected_revision 으로 보호) → 컴파일 → PIE 수동 확인은 사용자.

**14.4 완료 기준**
- 복제본에서 Free Locomotion · Jump · Attack 컴파일 0 에러, 에디터 재시작 후 재조회 일치.
- 상태 내부 채우기 경로가 테스트로 고정됨.
- 도구 변경이 있었다면 Development · DebugGame 빌드 성공 + `phase3_test.py`·`phase4_test.py` 회귀 PASS.
- diff 문서와 사용자 승인 기록.

---

### 15. 산출물

- 코드: 도구 부족분 반영(복제 Tool · BlendSpace · LayerSetup 중 확정된 것), `server.py` docstring 갱신.
- 테스트: `phase4_test.py` 에 상태 내부 절 추가, 필요 시 `Tools/mcp/phase5_test.py`.
- 문서: phase1 문서 끝 "Phase 5 결과" 절(기존 형식), 이 문서 §1·§3·§13·§17 갱신, 복제본 diff 문서(`.claude/plans/`).
- 메모리: `project_animbp-automation.md` 갱신.

---

### 16. 작업 규칙 (이 프로젝트·이 사용자 기준)

1. **구현 전 확인.** 설계 선택지가 갈리는 곳(§14.0)은 코드 전에 사용자에게 선택지를 제시하고 확정한다. 분석·조회·실측은 묻지 않고 진행한다.
2. **엔진 API 는 소스에서 확인하고 경로를 남긴다.** 추측으로 "가능하다"고 쓰지 않는다. 확인 못 한 것은 ❓.
3. **파일 읽기는 Read, 검색은 Grep/Glob.** Bash 로 파일을 cat·루프하지 않는다. `Saved/`·`Binaries/`·`Intermediate/` 는 권한상 읽을 수 없다(크래시 로그 필요 시 사용자에게 요청).
4. **빌드는 두 구성 모두.** 에디터가 떠 있으면 그 구성의 DLL 이 잠겨 링크 실패한다 → 빌드 전 에디터를 내린다.
5. **에디터는 내가 백그라운드로 띄우고 내린다.** 기동: `UnrealEditor.exe <uproject>`(백그라운드) → `Tools/mcp/.venv/Scripts/python.exe Tools/mcp/wait_for_bridge.py 480 10` 폴링. 종료: `python Tools/ue_exec.py Tools/scripts/quit_editor.py`, 에디터를 못 찾으면 `taskkill //PID <pid> //F`(내가 띄운 테스트 에디터에만). 사용자에게 "에디터 켜 주세요"라고 하지 않는다.
6. **Git Bash 접두.** Python 스크립트에 `/Game/...` 인자를 넘길 때 `MSYS_NO_PATHCONV=1`, 한글 출력은 `PYTHONIOENCODING=utf-8`. MCP JSON 본문은 영향 없음.
7. **`FJsonObject` 를 두 컨테이너에 넣지 않는다.** 순환 참조 → 직렬화 무한 재귀 → 에디터 크래시(종료 코드 3).
8. **운영 애셋 `ABP_Hero_Base` 는 읽기만.** Phase 5 편집은 복제본, 도구 테스트는 `ABP_McpTest`.
9. **커밋은 사용자가 한다.** 변경 파일 목록과 커밋 메시지 초안만 제시.
10. **문서 관례.** 설계·핸드오프 md 는 `.claude/plans/`. 구조를 재논의하기 전에 phase1 문서의 근거를 먼저 읽는다.
11. **MCP Tool 목록은 세션 시작 시 고정.** 새 Tool 은 재시작 전까지 HTTP 테스트로 검증.
12. **실측으로 확인된 엔진 함정 (코드에 그대로 적용)**: 포즈 출력 핀은 단일 연결(공유는 Save/UseCachedPose) · 노출 핀의 기본값이 구조체 값보다 우선(컴파일·숨김 시 핀→구조체) · 비기본값 핀은 재구성 때 고아로 남는다(`SetSavePinIfOrphaned(false)`) · 전이 노드는 자기 핀 링크 0 통지에 스스로 DestroyNode 한다(분리·복원은 `BreakLinkTo`) · 주석 노드 `PostPlacedNewNode` 가 `NodeComment` 를 "Comment" 로 되돌린다(Finalize 뒤에 쓴다) · MinimalAPI 클래스의 protected 멤버·비내보내기 함수는 공개 가상 함수나 리플렉션으로 우회 · 헤더의 네임스페이스 안 `class X*` 전방선언은 네임스페이스 스코프 타입을 만든다(전역에서 선언).

---

### 17. 미커밋 변경 (Phase 5, 2026-10-16 기준)

Phase 4 까지 커밋됨(`3737c67`). 아래는 사용자가 커밋 여부를 결정한다. `Tools/mcp/phase*_state.json` 은 재시작 비교용 임시 파일. 테스트 애셋 `ABP_McpTest`·`ABP_McpLayerTest` 는 덮어쓰기 대상. **`ABP_Hero_McpBuild.uasset` 은 Phase 5 산출물(운영 애셋 아님)** — 커밋 여부는 사용자 결정.

```
 M .claude/plans/animbp-automation-phase1.md                 ("Phase 5 결과" 절)
 M .claude/plans/animbp-automation-handoff-phase5.md         (§13 · §17)
?? .claude/plans/animbp-phase5-hero-diff.md                  (빌드 vs 운영 비교 — phase5_build_hero.py 가 생성)
 M Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Core/AnimMcpGraphMutator.{h,cpp}     (VariableGet · ValidateLayerSetup · ExportTextItem_Direct)
 M Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Core/AnimMcpOperations.{h,cpp}       (add_node VariableGet 분기 · PendingBlendPoses)
 M Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Core/AnimMcpPropertyRules.{h,cpp}    (LayerSetup·BlendMode · 구조체 JSON 재귀 · enum 이름)
 M Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Core/AnimMcpTransitionRule.cpp       (VariableClassOf 공유)
 M Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Tools/AnimMcpTools_Graph.cpp         (Tool 설명)
 M Tools/mcp/anim_graph_mcp/server.py                                                          (docstring)
 M Tools/mcp/phase4_test.py                                                                     (B2 절)
 M Tools/mcp/phase3_state.json · phase4_state.json   (임시)
?? Tools/mcp/phase5_test.py
?? Tools/mcp/phase5_build_hero.py
?? Tools/mcp/phase5_state.json · phase5_build_state.json   (임시)
 M Content/Animation/Test/ABP_McpTest.uasset
?? Content/Animation/Test/ABP_McpLayerTest.uasset
?? Content/Animation/Hero/ABP_Hero_McpBuild.uasset
 M Content/Animation/Hero/ABP_Hero_Base.uasset              (운영 애셋 — UpperBody 레이어 적용·재배선, 사용자 승인 2026-10-16, revision 3c146b5f…)
?? Tools/mcp/phase5_prod_state.json   (임시 — 운영 애셋 재시작 비교용)
```

커밋 메시지 초안: `Feat: AnimGraph MCP Phase 5 — VariableGet 노드·LayerSetup 본 필터·히어로 ABP 도구 재구성`

---

### 최종 지시 (새 세션용 — Phase 5)

Phase 5(실제 캐릭터 적용) 를 수행한다. 먼저 이 문서 전체와 phase1 문서 §A-4(애셋 현황)·§F Phase 5·"Phase 3 결과"·"Phase 4 결과" 를 읽고, 코드 `Core/AnimMcpOperations.cpp`(되돌리기 저널 패턴)·`Core/AnimMcpTransitionRule.cpp`·`Core/AnimMcpPropertyRules.cpp` 를 훑는다. 그다음 에디터를 띄워 (1) §14.1 의 상태 내부 채우기 경로를 테스트 애셋에서 실측해 `phase4_test.py` 에 절로 고정하고, (2) 운영 애셋 `depth=-1` 덤프로 "이미 있음 / 비어 있음 / 추가" 표를 만든다. **§14.0 의 복제 수단·BlendSpace·적용 범위는 코드 전에 사용자와 확정**한다. 복제본에서만 편집하고, 원본 적용은 diff 검토·승인 뒤에만 한다. 각 단계 끝에 빌드(두 구성, 도구를 바꿨을 때)·테스트·에디터 재시작 재조회를 통과시키고 §15 산출물을 남긴다. strafe 는 보류 유지(§3).
