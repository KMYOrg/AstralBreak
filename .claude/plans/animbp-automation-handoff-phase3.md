# AI Animation Blueprint Automation
## 개발 지침서 (개정판) — Phase 3 착수용 핸드오프

> **대체됨 (2026-10-16):** Phase 4 까지 반영한 개정 2판은 [animbp-automation-handoff-phase5.md](animbp-automation-handoff-phase5.md) 다. 이 문서는 Phase 3·4 작업 당시 기록으로만 남긴다.

> 작성 2026-10-14 · 브랜치 `feat/ai_auto_ABP` · 기준 엔진 UE 5.7.4 소스 빌드
> 이 문서는 최초 지침서(Phase 1 착수 시 전달)를 **현재 구현 상태에 맞춰 개정**한 것이다. "후보", "조사 대상"이던 항목은 확정값으로 바꾸었고, 완료된 Phase 는 결과만 남겼다.
> 설계 근거·엔진 소스 경로·검증표의 원문은 [animbp-automation-phase1.md](animbp-automation-phase1.md) 에 있다. 구조를 재논의하기 전에 그 문서의 §B(API 검증표)·§C(아키텍처 결정)·§G(위험)를 먼저 읽는다.

---

### 1. 프로젝트 개요 및 최종 목표 (변경 없음)

Unreal Engine 5.7.4 Source Build 환경에서 Claude Code 가 Animation Blueprint 를 생성·조회·수정·컴파일·검증할 수 있게 하는 AI Agent Tool 시스템을 개발한다. 사용자가 애니메이션 애셋과 동작 설계 가이드를 주면 Claude Code 가 실행 중인 에디터와 상호작용해 실제 AnimBP 를 구성한다. 기존 AnimBP 는 전체 재생성이 아니라 구조를 분석하고 필요한 부분만 안전하게 수정한다.

핵심 목표 중 현재 상태:

| 목표 | 상태 |
| :--- | :---: |
| AnimBP 애셋 자동 생성 및 조회 | ✅ |
| 기존 AnimGraph · State Machine 구조 분석 | 🔶 그래프 트리·노드·핀·연결·허용 목록 프로퍼티 값·바인딩 보유·노출 핀 조회 가능(Phase 3). 상태머신 전용 뷰는 Phase 4 |
| AnimGraph 노드 생성·수정·삭제 및 Pin 연결 | ✅ Phase 3 — add_node·connect·disconnect·remove_node·set_property·set_asset·expose_pin·add_blend_pose |
| State Machine · State · Transition 자동 구성 | ✅ Phase 4 — add_state·add_transition·set_entry_state, 상태 삭제 시 전이 연쇄 |
| Transition Rule 및 블렌딩 조건 설정 | ✅ Phase 4 — set_transition_rule(JSON AST, 멱등, rule_source 복원), 전이 properties(crossfade·priority·blend_mode…) |
| AnimSequence · BlendSpace · Montage 연결 | 🔶 애셋 플레이어 노드에 애셋 할당 가능. BlendSpace 생성은 Phase 4 |
| 기존 C++ AnimInstance 와 연동 | 🔶 부모 클래스 지정·변수 목록 조회 가능. 변수 참조 노드는 Phase 4 |
| 컴파일 및 오류 분석 | ✅ 노드 Guid 매핑 포함 |
| 저장 · 변경 검증 · 실패 복구 | ✅ revision 해시 · 보상 롤백 · 롤백 검증 |
| 다른 UE5 프로젝트에서 재사용 가능한 MCP Tool | 🔶 플러그인은 프로젝트 비의존. 타 프로젝트 재현 검증은 Phase 6 |

이 프로젝트의 목표는 특정 캐릭터 AnimBP 하나를 만드는 것이 아니라 범용 도구를 만드는 것이다. 이 원칙은 그대로다.

---

### 2. 개발 환경 (확정)

| 항목 | 값 |
| :--- | :--- |
| Engine | UE 5.7.4 소스 빌드, `D:/UnrealSource/UnrealEngine-5.7.4-release` (`Engine/Build/Build.version` 확인) |
| Project | `D:/UE5Projects/AstralBreak` — 런타임 모듈 1개 `AstralBreak`, 에디터 모듈 없음(플러그인이 대신) |
| 플러그인 | `Plugins/AnimGraphMcp/` — 에디터 전용 모듈 `AnimGraphMcpEditor`. uproject 에 등록됨 |
| MCP 서버 | Python 3.13, `Tools/mcp/anim_graph_mcp/`, 전용 venv `Tools/mcp/.venv` (gitignore), 패키지 `mcp 2.3.0` (`MCPServer` API — 1.x 의 `FastMCP` 아님), `httpx` |
| Claude Code 등록 | 프로젝트 루트 `.mcp.json` → 서버명 `anim-graph-mcp`. 세션 시작 시 Tool 9개가 `mcp__anim-graph-mcp__*` 로 보인다 |
| 통신 | Claude Code ↔ server.py: stdio MCP · server.py ↔ 플러그인: `POST http://127.0.0.1:18765/v1/<tool>` JSON |
| 설정 | `Config/DefaultEngine.ini [AnimGraphMcp] Port=18765 / bRequireToken=True / bAutoStart=True` (현재는 전부 기본값, ini 에 미기재). 커맨드라인 `-AnimGraphMcpPort=`. 콘솔 `AnimGraphMcp.Start/Stop/Status` |
| 토큰 | 에디터 기동마다 `Saved/AnimGraphMcp/token` 에 기록, 종료 시 삭제. `get_editor_status` 만 토큰 면제 |
| 빌드 | `Engine/Build/BatchFiles/Build.bat AstralBreakEditor Win64 {Development|DebugGame} -Project=<uproject> -WaitMutex -NoHotReload`. **두 구성 모두 빌드**한다(사용자는 평소 DebugGame 에디터 사용) |
| 툴체인 | MSVC 14.38 (UBT 가 14.44 를 금지) |
| 운영 애셋 | `/Game/Animation/Hero/ABP_Hero_Base` (스켈레톤 `/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F`, 부모 `UAstralAnimInstance`) — **읽기 전용 대상. 편집 테스트 금지** |
| 테스트 애셋 | `/Game/Animation/Test/ABP_McpTest` — 덮어쓰기 가능. 같은 스켈레톤 |

구현 가능성과 API 사용 여부는 **설치된 5.7.4 엔진 소스**를 기준으로 검증한다. 다른 버전의 예제 코드를 그대로 쓰지 않는다. 이 원칙은 Phase 1·2·2.5 전체에서 지켜졐고, 검증된 API 와 소스 경로는 phase1 문서 §B 에 있다.

---

### 3. AI Agent 의 최종 사용 시나리오 (변경 없음)

"현재 캐릭터의 AnimBP 에 기본 이동, 록온 이동, 점프 및 공격 애니메이션 시스템을 구성해 줘. 지정한 AnimSequence·BlendSpace·Montage 를 쓰고 기존 C++ 시스템과 연동해 줘."

Claude Code 의 수행 순서(1~12)는 최초 지침서와 같다. 현재 Tool 로 가능한 범위는 1~5(분석·조회·계획), 6 중 노드 생성·연결, 7 중 애셋 할당, 10~12(검증·컴파일·보고)다.

초기 적용 대상의 범위 조정:

- **Free Locomotion** (Idle·Walk·Run·Speed 블렌딩) — Phase 5 대상 유지
- **Lock-On Locomotion** — **보류**. 2026-10-10 결정: strafe 는 락온이 아니라 추후 "사격 후 일정 시간 유지되는 strafe 모드"로 도입한다. 현재 코드는 락온 중에도 `bOrientRotationToMovement=true` 라 strafe 자세가 성립하지 않는다. 선행 게임플레이 작업은 phase1 문서 §F Phase 5 보류 표(S-A/B/C)
- **Jump** (Start·Loop/Fall·Landing, 지면·수직 속도 전이) — Phase 5 대상 유지
- **Attack** (Montage·Combo·Full/Upper Body Slot·Layered Blend Per Bone) — Phase 5 대상 유지

프로젝트 `UAstralAnimInstance` 가 이미 노출하는 변수(전부 BlueprintReadOnly, 스레드 안전 스냅샷 패턴): `Speed`, `Acceleration`, `MovementDirection`, `bIsOnGround`, `bIsInAir`, `bIsJumping`, `bIsFalling`, `bHasMovementInput`, `GroundDistance`, `GameplayTagPropertyMap`. Transition Rule 은 이들을 참조한다.

---

### 4. 아키텍처 (확정 · 구현됨)

```text
Claude Code (AI Agent)
        │  stdio MCP  (.mcp.json → Tools/mcp/.venv python server.py)
        ▼
Python MCP 서버   Tools/mcp/anim_graph_mcp/server.py  — Tool 선언·입력 스키마(함수 시그니처)
                  Tools/mcp/anim_graph_mcp/bridge.py  — HTTP 전달, 토큰, request_id, 오류 봉투 정규화
        │  POST http://127.0.0.1:18765/v1/<tool>  (JSON, X-AnimMcp-Token)
        ▼
에디터 플러그인   Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/
  ├─ AnimGraphMcpEditorModule.cpp  설정 로드, Dispatcher·Bridge 조립, Tool 등록, 콘솔 명령
  ├─ Bridge/AnimMcpHttpBridge      엔진 HTTPServer 라우트(tool 당 1개), 토큰 전처리기, 응답 쓰기
  ├─ Bridge/AnimMcpDispatcher      JSON 파싱 → request_id 캐시(256) → 핸들러 → 봉투
  ├─ Bridge/AnimMcpTypes           오류 코드, FAnimMcpError, 파라미터 헬퍼, 진단, JSON 헬퍼
  ├─ Core/AnimMcpAssetResolver     경로 정규화 · AssetRegistry 존재 확인 · 로드 · 클래스 검증
  ├─ Core/AnimMcpGraphInspector    (읽기만) 그래프 트리 · 노드 · 핀 · 연결 · 변수 · revision 해시
  ├─ Core/AnimMcpBlueprintFactory  AnimBP 생성 (팩토리 미사용, CreateBlueprint 재현)
  ├─ Core/AnimMcpGraphMutator      (쓰기 기계) 노드 생성 · 핀 연결 · 검증 함수
  ├─ Core/AnimMcpOperations        (정책) operations 배치: 사전 검증 · 트랜잭션 · 보상 롤백 · revision 대조
  ├─ Core/AnimMcpCompiler          컴파일(FCompilerResultsLog → node_guid) · 강제 저장
  └─ Tools/AnimMcpTools_{Status,Inspect,Assets,Graph,Compile}.cpp  Tool 핸들러 (얇음)
        ▼
Unreal Editor API (게임 스레드)  →  Animation Blueprint
```

**확정 결정과 근거(요약)**

- **Python 만으로는 불가.** 파이썬 래퍼는 `BlueprintVisible` 프로퍼티만 노출하고 `UEdGraph::Nodes`·`UEdGraphNode::NodeGuid`·핀은 노출되지 않는다 (phase1 §B-7). 그래프 조회·편집은 전부 C++.
- **엔진 내장 `HTTPServer` 모듈.** `FHttpServerModule` 이 게임 스레드 티커(`FTSTickerObjectBase`)라 핸들러가 게임 스레드에서 실행된다. 기본 바인드 `localhost`. 별도 스레드·디스패치 코드 없음. 핸들러 진입에 `ensure(IsInGameThread())` 를 두어 가정을 검증한다.
- **Remote Control API · 오픈소스 Unreal MCP 는 채택하지 않음.** AnimGraph 편집 API 를 제공하지 않거나 포크 유지 비용이 크다 (phase1 §C-1).
- **MCP 서버는 얇은 프록시.** 그래프 로직을 Python 에 두지 않는다. 함수 docstring·타입 힌트가 곧 Claude 가 보는 Tool 설명·스키마다.
- **긴 작업은 동기 처리.** 컴파일 등은 에디터 프레임을 블로킹한다(에디터가 실행기). 클라이언트 타임아웃 기본 60초, 컴파일 포함 180초.
- **에디터 기동 직후** 리스너는 먼저 열리고 응답은 로딩 완료 후 온다 → `wait_for_bridge.py` 로 폴링.

---

### 5. UE 5.7.4 API (검증 완료)

최초 지침서 §5 의 조사 후보는 전부 엔진 소스에서 확인됐다. 표 전체는 phase1 문서 §B. 구현에 실제로 쓰인 것:

| 용도 | API | 모듈 |
| :--- | :--- | :--- |
| AnimBP 생성 | `FKismetEditorUtilities::CreateBlueprint(Parent, Package, Name, BPTYPE_Normal, UAnimBlueprint, UBlueprintGeneratedClass, Ctx)` + `TargetSkeleton` 3곳 세팅 (팩토리 cpp 재현). `UAnimBlueprintFactory` 는 다이얼로그·모달 때문에 미사용 | UnrealEd |
| 그래프 탐색 | `UBlueprint::FunctionGraphs/UbergraphPages/MacroGraphs` + `UEdGraph::SubGraphs` 재귀, `GraphGuid`, `NodeGuid`, `UEdGraphSchema_K2::GN_AnimGraph` | Engine · BlueprintGraph |
| 노드 생성 | `FGraphNodeCreator<UAnimGraphNode_Base>`(`CreateNode(false, Class)` → 위치 → `Finalize()`). Finalize 가 Guid·`PostPlacedNewNode`(서브그래프 생성)·기본 핀을 만든다. 애셋은 `UAnimGraphNode_AssetPlayerBase::SetAnimationAsset`, 수용 여부는 `SupportsAssetClass` | AnimGraph · Engine |
| 핀 연결 | `Schema->CanCreateConnection` (MAKE·PROMOTION·BREAK_OTHERS 허용, DISALLOW·CONVERSION_NODE 거부) → `TryCreateConnection` | Engine |
| 노드 삭제 | `UEdGraphNode::BreakAllNodeLinks()` + `DestroyNode()` (서브그래프 보유 노드는 자기 그래프도 제거) — 현재 롤백에서만 사용 | Engine |
| 컴파일 | `FKismetEditorUtilities::CompileBlueprint(BP, None, &FCompilerResultsLog)`; `Log.Messages` 의 `FUObjectToken` → `UEdGraphNode` → Guid | UnrealEd · Core |
| 저장 | `UEditorAssetSubsystem::SaveLoadedAsset(BP, /*bOnlyIfIsDirty*/ false)` | UnrealEd |
| 삭제(덮어쓰기) | `UEditorAssetSubsystem::DeleteAsset` + 메모리 잔존 객체는 임시 패키지로 `Rename` + `MarkAsGarbage` | UnrealEd |
| 트랜잭션 | `FScopedTransaction`; 실패 시 보상 롤백 후 `Cancel()`. **`Cancel` 은 기록만 버리고 상태를 되돌리지 않는다**(`UTransBuffer::Cancel`) | UnrealEd |
| 변수 목록 | `TFieldIterator<FProperty>` on `SkeletonGeneratedClass` (CPF_BlueprintVisible), `UEdGraphSchema_K2::ConvertPropertyToPinType` | CoreUObject · BlueprintGraph |
| 애셋 목록 | `IAssetRegistry::GetAssets(FARFilter)` + 태그 `Skeleton` → `FPackageName::ExportTextPathToObjectPath` | AssetRegistry |

Phase 3·4 에서 새로 필요한 API(핀 노출 `SetPinVisibility`, 노드 프로퍼티 `GetFNodeProperty`/`ExportText`, State Machine 계열, `UK2Node_VariableGet`/`UK2Node_CallFunction`, `UEdGraphNode_Comment`)는 phase1 §B-3·B-4·B-5 에 헤더·시그니처가 확인되어 있다.

---

### 6. Python 과 C++ 의 역할 구분 (확정)

- **Python**: MCP 서버(Tool 선언·스키마), HTTP 프록시, 테스트 스크립트. 그래프 로직 없음.
- **C++**: 조회·생성·편집·컴파일·저장 전부.
- 기존 `Tools/ue_exec.py`(Python 원격 실행)는 에디터 종료(`Tools/scripts/quit_editor.py`)·프로브 등 **운용 보조**로만 쓴다. 그래프 편집 채널로 쓰지 않는다.

---

### 7. AnimGraph 구조 조회 (구현됨 · 확장 예정)

**구현된 응답** (`get_anim_blueprint_info`):
`asset_path, revision, parent_class, parent_anim_blueprint, is_template, target_skeleton, preview_mesh, blueprint_type, status, anim_graph_guid, graphs[{graph_guid, name, class, parent_graph_guid, owner_node_guid, owner_node_class, node_count}], variables[{name, cpp_type, pin_category, pin_subcategory, source(native|blueprint), owner_class, read_only}], linked_anim_layer_count, linked_anim_layers[]`

**구현된 응답** (`get_anim_graph_structure`):
`schema_version, asset_path, revision, root_graph_guid, depth, graphs[], nodes[{node_guid, graph_guid, class, title, pos[x,y], asset, is_sink, comment?, pins[{name, dir, type, default, hidden, linked["guid:pin"]}], sub_graphs[guid]}], connections[{from:{node,pin}, to:{node,pin}}]`

**노드 식별**: 입력은 항상 `node_guid`(+ 배치 내 임시 `ref`). 표시 이름은 응답에만 있다.

**revision**: 그래프 Guid·클래스·이름, 노드 Guid·클래스·위치, 핀 이름·방향·카테고리·기본값·연결, **그리고 노드의 EditAnywhere 프로퍼티 + FAnimNode 멤버 값**(Phase 3; PoseLink·Transient·FText 제외, 노출 핀은 (이름, bShowPin))을 결정적 순서로 이어 SHA1. `ABP_Hero_Base`(그래프 21·노드 69) 계산 315ms.

**Phase 3 에서 추가된 조회** (노드 항목): `properties{}` — 허용 목록 프로퍼티의 현재 값(set_property 가 받는 이름과 동일) · `optional_pins[{property, shown, can_toggle, bound}]` · `has_binding`. 바인딩은 보존 대상으로만 표기(편집은 Phase 6). 상태머신 전용 뷰 `get_state_machine_structure` 는 Phase 4.

---

### 8. AnimGraph 편집 (Phase 3 구현 완료 · 2026-10-15)

**구현된 op** (전부 `preview_graph_operations` / `apply_graph_operations` 의 `operations[]`)

| op | 입력 | 동작 · 롤백 |
| :--- | :--- | :--- |
| `add_node` | `ref?, graph?(guid, 생략=루트), class, pos?[x,y], asset?, enum?(BlendListByEnum), properties?{name:value}` | `FGraphNodeCreator` 생성 → enum 바인딩(`ReloadEnum`+재구성) → properties 는 set_property 와 같은 경로. 롤백 = `DestroyNode` |
| `connect` | `from:{node|ref, pin}, to:{node|ref, pin}` | `CanCreateConnection` → `TryCreateConnection`. 롤백 = 양 끝 핀 링크 스냅샷(노드, 핀 이름) 복원 |
| `disconnect` | `from:{node|ref, pin}, to?:{node|ref, pin}` | `to` 있으면 `BreakSinglePinLink`, 없으면 `BreakPinLinks`. 롤백 = 스냅샷 복원 |
| `remove_node` | `node|ref` | **분리 보관**(사용자 확정): `UEdGraph::RemoveNode(링크 끊기)` 로 Nodes 에서만 제외, 객체 유지. 롤백 = `AddNode` + 링크 복원. 배치 성공 확정 시 `DestroyNode`(서브그래프 정리). `CanUserDeleteNode()==false`(Root·Result·Entry) 거부. 제거된 노드를 뒤 op 가 가리키면 `NODE_NOT_FOUND` |
| `set_property` | `node|ref, property, value` | 허용 목록(§8-1) 리플렉션 `ImportText` → `PreEditChange/PostEditChangeProperty` → **노출된 비연결 핀의 기본값도 동기화**(핀이 진실: 컴파일·숨김 시 핀→구조체 복사). NodeRef 규칙(UseCachedPose.SaveCachedPoseNode)은 value 가 노드 참조. 롤백 = 이전 ExportText 재적용 |
| `set_asset` | `node|ref, asset` | `SetAnimationAsset`. 롤백 = 이전 애셋(null 이면 리플렉션으로 직접 복원) |
| `expose_pin` | `node|ref, property, visible?=true` | `ShowPinForProperties` 이름 검색 → `SetPinVisibility`(내부 ReconstructNode). 같은 상태면 no-op. 롤백 = 반대 값 |
| `add_blend_pose` | `node|ref, entry?` | LayeredBoneBlend: `AddPinToBlendByFilter`. BlendListByEnum: `ExposeEnumElementAsPin` 재현(entry 필수, _MAX·중복 거부). 롤백 = 마지막 포즈 제거(제거 인덱스 핀 `SetSavePinIfOrphaned(false)` 후 재구성 — 고아 핀 방지) |

**8-1. set_property 허용 목록** (`Core/AnimMcpPropertyRules.cpp`, 사용자 확정 "확장 목록"): SequencePlayer `bLoopAnimation, PlayRate, StartPosition, PlayRateBasis` · BlendSpacePlayer `bLoop, PlayRate, StartPosition, X, Y, bResetPlayTimeWhenBlendSpaceChanges` · Slot `SlotName, bAlwaysUpdateSourcePose` · SaveCachedPose `CacheName`(Node) · UseCachedPose `SaveCachedPoseNode`(NodeRef) · LayeredBoneBlend `bMeshSpaceRotationBlend, bMeshSpaceScaleBlend, bBlendRootMotionBasedOnRootBone, LODThreshold` · BlendListBase(ByBool·ByEnum) `BlendTime[]` · BlendListByEnum `BoundEnum, VisibleEnumEntries`(읽기 전용) · Transition `CrossfadeDuration, PriorityOrder, BlendMode, Bidirectional, bDisabled, bAutomaticRuleBasedOnSequencePlayerInState, AutomaticRuleTriggerTime` · State `bAlwaysResetOnEntry`. 표는 클래스 이름으로 매칭하고 상위 클래스를 거슬러 올라간다. LayerSetup(본 필터)은 Phase 5 보류.

**지원 노드** (전부 생성·연결·컴파일 0 에러 확인): SequencePlayer · BlendSpacePlayer · Slot · LayeredBoneBlend · BlendListByBool · BlendListByEnum · SaveCachedPose/UseCachedPose · StateMachine(생성만 — 내부는 Phase 4) · Root(기존 노드만).

**속성 변경 원칙** (변경 없음): ① 노드별 공식 Setter ② 허용 목록 기반 리플렉션 ③ 노드별 특수 처리. 임의 프로퍼티 범용 명령은 금지.

**실측으로 확인한 엔진 동작** (Phase 4~5 에서 그대로 적용): 포즈 출력 핀은 **단일 연결**(두 번째 연결이 첫 연결을 끊는다 — 공유는 Save/UseCachedPose) · 노출 핀의 기본값이 구조체 값보다 우선 · 비기본값 핀은 재구성 때 고아로 남는다.

---

### 9. State Machine 및 Transition Rule (Phase 4 · 구현 완료 2026-10-15)

**op 4종** (`Core/AnimMcpOperations`, 되돌리기 저널 패턴 동일)

| op | 입력 | 동작 · 롤백 |
| :--- | :--- | :--- |
| `add_state` | `ref?, sm:{node|ref} \| graph:guid, name?, pos?` | `FGraphNodeCreator<UAnimStateNode>` → Finalize(BoundGraph+StateResult 자동) → 엔진 이름 검증기 → `OnRenameNode`(=BoundGraph 이름). 롤백 = `DestroyNode`(BoundGraph 제거) |
| `add_transition` | `ref?, from:{node|ref}, to:{node|ref}, properties?, rule?` | Creator → Finalize(BoundGraph+TransitionResult 자동) → `CreateConnections(From, To)` → properties(set_property 경로) → rule(아래). 롤백 = `DestroyNode` |
| `set_entry_state` | `sm \| graph, state:{node|ref}` | `EntryNode->GetOutputPin()` ↔ `State->GetInputPin()` `TryCreateConnection` (스키마가 이전 Entry 연결을 끊음). 롤백 = Entry 핀 스냅샷 복원 |
| `set_transition_rule` | `node|ref (transition), rule` | 기존 규칙 노드·주석을 분리 보관 → AST 에서 전체 재생성 → `bAutomaticRuleBasedOnSequencePlayerInState` 설정. **같은 원문 + 그래프 미변경이면 no-op (`unchanged:true`)**. 롤백 = 생성 노드 제거 + 보관 노드 복귀 + Result 핀 기본값·플래그 복원 |
| `remove_node` (확장) | 상태 노드 | 연결된 전이를 먼저 분리 → 상태 분리. 성공 확정 시 전부 `DestroyNode` (에디터와 같은 결과) |

**규칙 AST** (`Core/AnimMcpTransitionRule`, 2026-10-15 사용자 확정 "JSON 트리")

```jsonc
{"var": "bIsFalling"}                                                     // BlueprintVisible 프로퍼티 → UK2Node_VariableGet(self)
{"not": R} · {"and": [R, R, ...]} · {"or": [R, R, ...]}                    // Not_PreBool · BooleanAND/OR 사슬
{"compare": {"op": ">", "left": {"var": "Speed"}, "right": {"literal": 10.0}}}  // (op × 타입) → UKismetMathLibrary 표. Real·Int·Int64 전 연산, Bool·Name 은 ==/!=
{"literal": true}                                                          // 상대 핀 기본값으로 (노드 없음). 최상위 literal 은 Result 핀 기본값
{"call": {"function": "FMax", "class"?: "/Script/...", "args": {"A": R, "B": R}}}  // BlueprintPure ∧ HasFunctionBlueprintThreadSafeMetaData ∧ 소유 ∈ {AnimInstance 사슬, UKismetMathLibrary}. 모든 입력 파라미터 필수
{"automatic": true, "trigger_time"?: -1.0}                                 // 그래프 없이 플래그만 (최상위 전용)
```

- 정규화 JSON(키 순서 고정) + 생성 직후 그래프 해시를 BoundGraph 의 `UEdGraphNode_Comment` 첫 줄 `AnimGraphMcp rule_source v1` 아래 기록. Inspector 가 `rule_source` 복원, 해시 불일치 = `rule_modified`(사람 편집).
- **float 변수 핀 → double 함수 핀: 허용 확정** (`EdGraphSchema_K2.cpp:4533` PC_Real 은 서브타입 무관 호환). 변환 노드 불필요.
- `UK2Node_PromotableOperator` 미사용 유지. 프로젝트 정책(복잡 조건은 C++ bool) 유지.
- 조회는 새 Tool 없이 `get_anim_graph_structure` 의 `state_machines[]` (사용자 확정) — §10.

**엔진 함정 2건 (phase1 "Phase 4 결과")**: 전이 노드는 링크 0 통지에 자살하므로 분리·복원은 `BreakLinkTo`(통지 없음) 로 · 주석 노드 `PostPlacedNewNode` 가 `NodeComment` 를 "Comment" 로 되돌리므로 원문은 Finalize 뒤에 쓴다.

---

### 10. MCP Tool 인터페이스 (현재 9개 · 실제 시그니처)

Python 측 함수명 = 플러그인 라우트명. 모든 응답은 봉투 `{ok, tool, request_id, result, error:{code,message,details?}, diagnostics:[{level,code,message,...}]}` + Python 이 덧붙이는 `http_status`.

| Tool | 입력 | 비고 |
| :--- | :--- | :--- |
| `get_editor_status` | — | 토큰 면제. 엔진·프로젝트·PIE·플러그인 상태·열린 에디터·포트·Tool 목록 |
| `get_anim_blueprint_info` | `asset_path` | §7 |
| `get_anim_graph_structure` | `asset_path, graph_guid?, depth=1` | §7. depth 0 = 그 그래프만, -1 = 전부. **Phase 4: `state_machines[]`** (범위 안의 상태머신 그래프마다 entry_state · states[{name, kind(state/conduit/alias), bound_graph_guid, in/out}] · transitions[{from, to, crossfade_duration, priority_order, blend_mode, bidirectional, disabled, automatic, rule_graph_guid, rule_generated, rule_source, rule_modified, rule_node_count}]), schema_version 1.1 |
| `list_animation_assets` | `skeleton?, asset_class=all, path_prefix=/Game, limit=200` | 클래스: AnimSequence·BlendSpace·AnimMontage·AnimComposite·all |
| `create_animation_blueprint` | `asset_path, skeleton, parent_class=/Script/Engine.AnimInstance, preview_mesh?, overwrite=false` | overwrite 는 기존 애셋 **삭제** — 사용자 확인 후 |
| `preview_graph_operations` | `asset_path, operations[]` | 그래프 불변. `valid, revision, planned[{index, op, ref, ok, error?, note?}], would_create, would_connect, would_disconnect, would_remove, would_modify`. 미생성 ref 를 가리키는 op 는 클래스 수준 검증 후 `note` 로 apply 시점 검증을 예고 |
| `apply_graph_operations` | `asset_path, operations[], expected_revision?, compile=false, save=false` | 사전 전체 검증 → 트랜잭션 → 실패 시 보상 롤백+`rollback_verified` → `refs{ref→guid}, revision_before/after, compile, saved` |
| `compile_animation_blueprint` | `asset_path, save_on_success=false` | `ok, num_errors, num_warnings, status, messages[{level,text,node_guid,graph_guid,object}]` |
| `save_animation_blueprint` | `asset_path` | 강제 저장 |

**오류 코드**: `BAD_REQUEST`(400) · `UNAUTHORIZED`(401) · `TOOL_NOT_FOUND`/`ASSET_NOT_FOUND`/`GRAPH_NOT_FOUND`/`NODE_NOT_FOUND`/`PIN_NOT_FOUND`(404) · `ASSET_EXISTS`/`REVISION_MISMATCH`(409) · `CONNECTION_REJECTED`/`PROPERTY_NOT_ALLOWED`/`COMPILE_FAILED`/`SAVE_FAILED`(400) · `INTERNAL`(500). Python 측 추가: `EDITOR_GONE`, `TIMEOUT`, `TRANSPORT`, `BAD_RESPONSE`.

**Phase 3 은 Tool 을 추가하지 않았다** — 전부 `operations[]` 의 `op` 종류 추가(§8). Tool 9개 그대로이므로 Claude Code 재시작 없이 바로 쓸 수 있다. 후보로 남은 Tool: `get_state_machine_structure`(Phase 4), `validate_anim_graph`, `get_operation_result`, `quit_editor`(Phase 6 — Python 원격 실행이 에디터를 못 찾는 경우가 있었다).

---

### 11. 그래프 변경 안전성 (구현됨)

- **Preview / Apply 분리**: 같은 입력, preview 는 Mutator 의 `Validate*` 만 호출. Inspector 는 쓰기 함수가 없고 Mutator 는 트랜잭션 밖에서 호출되지 않는다.
- **Batch**: 적용 전 **전체** 사전 검증(하나라도 실패면 무변경) → `FScopedTransaction` 안에서 순차 적용 → 각 op 는 적용 직전 재검증.
- **실패 복구 = 보상 롤백**: 이 배치가 만든 노드를 역순 `DestroyNode`, `connect` 가 바꾼 양 끝 핀 링크를 스냅샷으로 복원 → 트랜잭션 `Cancel`(Undo 히스토리에 안 남김) → `revision_after == revision_before` 로 **복구를 검증**해 `rollback_verified` 로 보고. 에디터 `UndoTransaction` 은 쓰지 않는다(결과가 Undo 버퍼 상태에 의존하지 않도록).
- **충돌 감지**: `expected_revision` 불일치 → `REVISION_MISMATCH`, 무변경.
- **멱등**: 같은 `(tool, request_id)` 재전송은 캐시 봉투 반환. 배치 내 `ref` 중복은 검증 실패.
- **애셋 보호**: 운영 애셋 `ABP_Hero_Base` 는 테스트 금지. 생성은 기본적으로 기존 애셋을 건드리지 않음(`overwrite` 명시 필요). `save` 는 기본 false 이고 컴파일 오류 시 저장하지 않는다.

---

### 12. 컴파일 및 검증 전략 (구현 상태)

- **구조 검증**: op 사전 검증(그래프·노드·핀 존재, 스키마 연결 가능성, 노드 클래스, 애셋 수용·스켈레톤 일치)이 이 역할. 독립 Tool `validate_anim_graph` 는 미구현.
- **컴파일 검증**: 구현됨. 메시지는 노드 Guid 로 매핑.
- **런타임 검증**: 미구현(Phase 6). 기존 `Tools/scripts/run_automation_tests.py`·`read_automation_results.py` 재사용 예정.

---

### 13. 단계별 로드맵 (현재 위치: Phase 3 착수 전)

| Phase | 상태 | 내용 |
| :--- | :---: | :--- |
| 1 조사·설계 | ✅ 2026-10-10 | phase1 문서 |
| 2 통신 골격 | ✅ 2026-10-10 | 플러그인·HTTP·Dispatcher·MCP 서버·상태/정보 Tool. 커밋 `a669c33` |
| 2.5 최소 수직 통합 | ✅ 2026-10-14 | 생성→SequencePlayer→Root 연결→컴파일→저장→재조회(재시작 후 포함). Tool 9개. 커밋 `d87608f` |
| 3 범용 AnimGraph 편집 | ✅ 2026-10-15 | §8 op 8종, 노드 9종, Inspector 프로퍼티·바인딩·노출 핀, revision 에 프로퍼티 포함. `phase3_test.py` PASS(재시작 포함). phase1 문서 "Phase 3 결과" |
| 4 State Machine | ✅ 2026-10-15 | §9 op 4종 + 규칙 AST 생성기 + `state_machines[]` 뷰. `phase4_test.py` PASS(재시작 포함) + phase3 회귀 PASS. phase1 문서 "Phase 4 결과" |
| **5 실제 캐릭터 적용** | ⬜ **다음** | Free Locomotion · Jump · Attack. **복제본에서 먼저**, diff 검토 후 원본. strafe 보류. 선행 결정: BlendSpace 생성 vs 재사용, 복제 Tool |
| 6 고급·안정화 | ⬜ | Linked Layer 편집, Property Binding, Alias/Conduit, Automation Test, 타 프로젝트 재현 |

---

### 14. Phase 3 작업 목록 (✅ 2026-10-15 완료 — 결과는 phase1 문서 "Phase 3 결과" 절)

**목표**: 기존 AnimBP 를 "읽고 → 필요한 부분만 고치고 → 검증하는" 범용 편집이 되게 한다.

**14.1 Inspector 확장**
- 노드 프로퍼티 값 조회(허용 목록 프로퍼티만, `GetFNodeProperty` 리플렉션). `get_anim_graph_structure` 노드 항목에 `properties{}` 추가
- Property Binding 보유 표시 (`has_binding` / 바인딩된 프로퍼티 이름). 편집은 안 함, 보존만
- revision 에 노드 프로퍼티 값 포함 (`ExportText` 또는 허용 목록 값 직렬화). 비용을 `ABP_Hero_Base`(그래프 22개) 에서 측정

**14.2 Mutator · Operations 확장**
- `disconnect`, `set_property`(허용 목록), `set_asset`, `expose_pin`, `remove_node`
- `remove_node` 의 롤백 전략 결정(§8 표) — 설계 먼저, 사용자 확인 후 구현
- 노드 종류: BlendSpacePlayer · Slot · LayeredBoneBlend · BlendListByBool · BlendListByEnum · Save/UseCachedPose · StateMachine(생성만)
- `expose_pin` 뒤 핀 재탐색 규칙 준수

**14.3 테스트**
- `Tools/mcp/phase3_test.py`: 테스트 AnimBP 에 위 op 를 적용·롤백·재조회. 운영 애셋은 `get_anim_graph_structure depth=-1` 전체 덤프가 오류 없이 나오는지(읽기)만
- 각 op 의 성공·거부(허용 목록 외 프로퍼티, 호환되지 않는 연결, 없는 노드) 케이스

**14.4 완료 기준**
- `ABP_Hero_Base` 전체 덤프 성공(바인딩·Linked Layer 보존 표기)
- 모든 신규 op 가 preview 로 거부/허용이 갈리고, apply 중간 실패 시 `rollback_verified=true`
- 같은 배치 2회 적용 시 2회째는 `REVISION_MISMATCH` 또는 멱등 캐시(의도한 쪽으로)
- 속성만 바꾼 변경이 revision 을 바꾼다
- Development · DebugGame 빌드 성공, 테스트 PASS, 에디터 재시작 후 재조회 일치

---

### 15. 산출물

- 코드: 플러그인 `Core/`·`Tools/` 추가·수정, `server.py` Tool 추가
- 테스트: `Tools/mcp/phase3_test.py`
- 문서: phase1 문서 끝에 "Phase 3 결과" 절 추가(기존 "Phase 2 결과"·"Phase 2.5 결과" 형식), 이 핸드오프 문서의 §1·§8·§10·§13 상태 갱신
- 메모리: `project_animbp-automation.md` 갱신

---

### 16. 작업 규칙 (이 프로젝트·이 사용자 기준)

1. **구현 전 확인.** 설계 선택지가 갈리는 곳(예: `remove_node` 롤백 방식)은 코드 전에 사용자에게 묻는다. 분석·조회는 묻지 않고 진행한다.
2. **엔진 API 는 소스에서 확인하고 경로를 남긴다.** 추측으로 "가능하다"고 쓰지 않는다. 확인 못 한 것은 ❓ 로 표기.
3. **파일 읽기는 Read, 검색은 Grep/Glob.** Bash 로 파일을 cat·루프하지 않는다. `Saved/`·`Binaries/`·`Intermediate/` 는 권한 설정상 읽을 수 없다(크래시 로그 포함 — 로그가 꼭 필요하면 사용자에게 요청).
4. **빌드는 두 구성 모두.** 에디터가 떠 있으면 그 구성의 DLL 이 잠겨 링크 실패한다. 다른 구성은 빌드 가능.
5. **에디터는 내가 백그라운드로 띄우고 내린다.** 기동: `UnrealEditor.exe <uproject>` (`run_in_background`) → `Tools/mcp/.venv/Scripts/python.exe Tools/mcp/wait_for_bridge.py 480 10` 폴링. 종료: `python Tools/ue_exec.py Tools/scripts/quit_editor.py`. 사용자에게 "에디터 켜 주세요"라고 하지 않는다.
6. **Git Bash 경로 변환 주의.** `/Game/...` 인자를 Python 스크립트에 넘길 때 `MSYS_NO_PATHCONV=1` 을 앞에 붙인다. MCP 경로(JSON 본문)는 영향 없음.
7. **`FJsonObject` 를 두 컨테이너에 넣지 않는다.** 순환 참조가 생기면 직렬화가 무한 재귀해 에디터가 크래시한다(종료 코드 3). 2026-10-14 에 두 번 재현됨.
8. **운영 애셋 `ABP_Hero_Base` 는 읽기만.** 편집 테스트는 `/Game/Animation/Test/ABP_McpTest`(또는 새 테스트 애셋).
9. **커밋은 사용자가 한다.** `git commit/push/checkout` 등은 권한 설정상 확인을 요구한다. 변경 파일 목록과 커밋 메시지 초안만 제시.
10. **문서 관례.** 설계·핸드오프 md 는 `.claude/plans/`. 구조를 재논의하기 전에 phase1 문서의 근거를 먼저 읽는다.
11. **Claude Code 에 등록된 MCP Tool(`mcp__anim-graph-mcp__*`)은 세션 시작 시점의 Tool 목록으로 고정된다.** Phase 3 에서 Tool 을 추가하면 Claude Code 재시작 전까지는 `Tools/mcp/phase3_test.py`(HTTP 직접 호출)로 검증한다. 기존 9개는 에디터만 떠 있으면 세션 안에서 바로 호출 가능.

---

### 17. 미커밋 변경 (Phase 4, 2026-10-15 기준)

Phase 3 는 `2a85228` 로 커밋됨. 사용자가 커밋 여부를 결정한다. `Tools/mcp/phase{3,4}_state.json` 은 재시작 비교용 임시 상태 파일 — 저장소에 넣지 않아도 된다(gitignore 후보). 테스트 애셋 `ABP_McpTest.uasset` 은 내용이 바뀌었다(이제 상태머신 포함).

```
 M .claude/plans/animbp-automation-phase1.md                 ("Phase 4 결과" 절)
 M .claude/plans/animbp-automation-handoff-phase3.md         (§1·§9·§10·§13·§17·최종 지시 갱신)
 M Content/Animation/Test/ABP_McpTest.uasset
 M Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Core/AnimMcpGraphInspector.{h,cpp}   (state_machines 뷰)
 M Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Core/AnimMcpGraphMutator.{h,cpp}     (상태머신 함수 · 통지 없는 링크 해제)
 M Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Core/AnimMcpOperations.{h,cpp}       (op 4종 · 전이 연쇄 삭제)
 M Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Tools/AnimMcpTools_Graph.cpp
 M Tools/mcp/anim_graph_mcp/server.py
?? Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Core/AnimMcpTransitionRule.{h,cpp}
?? Tools/mcp/phase4_test.py
?? Tools/mcp/debug_dump_rules.py
?? Tools/mcp/phase4_state.json   (임시)
```

커밋 메시지 초안: `Feat: AnimGraph MCP Phase 4 — State Machine op 4종·Transition Rule AST 생성기·state_machines 뷰`

---

### 최종 지시 (새 세션용 — Phase 5)

Phase 5(실제 캐릭터 적용) 를 수행한다. 먼저 이 문서 §3(시나리오·범위)·§8·§9 와 phase1 문서 §A-4(애셋 현황)·§F Phase 5·"Phase 3/4 결과"(실측 엔진 동작)를 읽고, `get_anim_graph_structure(ABP_Hero_Base, depth=-1)` 로 운영 애셋의 현재 구조(상태머신 Locomotions · 상태 11 · 전이 12 · Linked Layer 0 · 바인딩 0)를 덤프해 **무엇이 이미 있고 무엇을 추가할지** 먼저 정리한다. 작업은 **복제본**에서만 — 복제 수단(`duplicate_animation_blueprint` Tool 추가 vs 에디터에서 사용자가 복제)과 BlendSpace(기존 `BS_Vesper_Locomotion1D` 재사용 vs `create_blendspace` 구현)는 **구현 전에 사용자와 확정**한다. 완료 기준은 복제본에서 Free Locomotion · Jump · Attack 이 컴파일 0 에러로 구성되고, 원본과 복제본의 structure diff 를 사용자가 검토한 뒤에만 원본에 적용한다. strafe 는 보류 유지(§3).
