# StateTree MCP (`Plugins/StateTreeMcp`)

실행 중인 Unreal Editor 안에서 StateTree 애셋을 **생성 · 조회 · 편집 · 컴파일 · 되돌리기 · PIE 실행 관측**하는 에디터 MCP 기능 플러그인입니다. 2026-11-14 `AnimGraphMcp` 에서 분리했습니다(설계 [ui-autogen-pipeline.md](../../Docs/Design/ui-autogen-pipeline.md) §3-1). 브리지 · 토큰 · 봉투 · 멱등 캐시 · 자동 시험 러너 · 보호 목록은 공용 코어 [`EditorMcpCore`](../EditorMcpCore/README.md) 가 갖고, 이 플러그인은 모듈 시작 때 Tool 9개를 코어에 등록합니다.

```text
AI Agent ─ stdio MCP ─▶ Tools/mcp/state_tree_mcp/server.py ─ HTTP/JSON 127.0.0.1:18765 ─▶ EditorMcpCore 브리지 ─▶ StateTreeMcp Tool ─▶ UStateTree
```

- 모듈 `StateTreeMcpEditor`(Type Editor). 의존 플러그인 `EditorMcpCore` · `StateTree` · `GameplayStateTree` · `GameplayAbilities`(시험 프로브 Task).
- 설계 · 근거는 `Docs/StateTree/DevelopmentGuide.md`, 실측은 `Docs/StateTree/Feasibility.md` · `Phase1Report.md` · `Phase2Report.md`. (분리 전 기록 문서의 `AnimGraphMcp.StateTree.*` · `/Script/AnimGraphMcpEditor.*` 는 지금 이름으로 읽습니다.)

## 설정 — `Config/DefaultEngine.ini`

```ini
[EditorMcp]
; StateTree Tool 의 쓰기 허용 목록 (패키지 경로 접두). 밖은 생성 · 적용 · 컴파일 · 되돌리기 거부 (OUTPUT_PATH_NOT_ALLOWED)
+StateTreeEditPaths=/Game/AI/
```

옛 `[AnimGraphMcp]` 섹션의 `+StateTreeEditPaths=` 도 그대로 읽습니다(두 섹션을 합침). `get_editor_status.state_tree_edit_paths` 가 정규화된 값을 돌려줍니다(이 플러그인이 더하는 필드). 보호 목록(`ProtectedAssets` · `ProtectedPaths`)은 코어 것을 같이 씁니다.

**옛 시험 타입 경로** — 시험 전용 Evaluator · 프로브 Task 는 `/Script/StateTreeMcpEditor.AnimMcpTestEvaluator` · `/Script/StateTreeMcpEditor.AnimMcpLifecycleProbeTask` 입니다. 분리 전 경로(`/Script/AnimGraphMcpEditor.*`)로 저장된 애셋(`Content/AI/Test/ST_M3_Probe`)은 `DefaultEngine.ini [CoreRedirects]` 의 `StructRedirects` 4줄이 새 경로로 잇습니다.

## StateTree Tool (9개) — MCP 서버 `state-tree-mcp`

| Tool | 쓰기 | 입력 · 결과 |
| :--- | :---: | :--- |
| `create_state_tree` | ○ | `asset_path, schema_class?, schema_properties?{ContextActorClass, AIControllerClass}, save=true`. 덮어쓰기 없음(`ASSET_EXISTS`). 결과 = inspect |
| `inspect_state_tree` | | `asset_path`. 스키마 · 컨텍스트 · 파라미터 · 상태 트리 · 노드(값) · 전환 · 바인딩 · `revision` · `compile_state`(`up_to_date` · `stale` · `failed`). BP 노드도 읽기는 된다 |
| `list_state_tree_node_types` | | `asset_path?` 또는 `schema_class?`, `kind?`(`task` · `condition` · `evaluator` · `property_function`). 프로퍼티 표 포함 |
| `list_state_tree_bindable_sources` | | `asset_path, node`(GUID). `GetBindableStructs` 결과. 메뉴에 없는 프로퍼티는 빼고 `hidden_properties` 로 센다 |
| `preview_state_tree_operations` | | `asset_path, operations[]`. 변경 없음. 첫 실패에서 멈추고 뒤 op 는 `skipped`. 같은 배치의 노드가 얽힌 바인딩은 `deferred:["scope"]` — **Preview 통과가 범위 통과를 보장하지 않는다** |
| `apply_state_tree_operations` | ○ | `asset_path, operations[], expected_revision?, compile=true, save=true`. 결과 `revision_before/after` · `compile_state` · `refs` · `compile{ok, messages, fixups}` |
| `compile_state_tree` | ○ | `asset_path`. `ok` · `messages` · `fixups`. 실패는 기존 컴파일 결과까지 지운다. 저장하지 않는다 |
| `revert_state_tree` | ○ | `asset_path`. 디스크로 재로드. **Undo 기록 전체(모든 애셋)가 사라지고 열린 편집기가 닫혔다 열린다** — `undo_history_cleared` · `editor_reopened` |
| `run_state_tree_scenario` | | `asset_path, map?, pawn_class?, spawn_location?, player_location?, events?[{tag, after?, when_state?, expect_state?, expect_transition?, window?}], expect_states?, duration=30, start_timeout=10, clients=0, timeout?`. PIE 를 직접 열고 닫는다. 잡을 돌려주고 결과는 코어의 `poll_automation_tests` — 아래 '검증 — StateTree 시나리오' |

**operations** (`state` · `node` · `target` = GUID · 같은 배치의 ref · 이름. 이름이 겹치면 `AMBIGUOUS_NAME`):

| op | 입력 | 비고 |
| :--- | :--- | :--- |
| `add_state` | `ref?, parent?(기본 Root), name, type?(state\|group), selection?, tag?, enabled?` | `linked` 계열은 Phase 3 |
| `remove_state` | `state, cascade?` | 전환 · 바인딩이 참조하면 `cascade` 없이 `NODE_REFERENCED` |
| `set_state_properties` | `state, properties` | `TasksCompletion` · `SelectionBehavior` · `Tag` · `bEnabled` · `CustomTickRate` · `Weight` · `RequiredEventToEnter`. 뒤 셋의 켜짐 플래그는 값에 따라 자동, `null` 이면 끈다 |
| `add_task` | `ref?, state, type, values?` | |
| `add_enter_condition` | `ref?, state, type, values?, operand?, indent?` | |
| `add_evaluator` · `add_global_task` | `ref?, type, values?` | |
| `add_transition` | `ref?, state, trigger, target, event_tag?, priority?, delay?, conditions?[{ref?, type, values?, operand?, indent?}]` | `target` = 상태 또는 `succeeded` · `failed` · `next_state` · `next_selectable_state`. `OnEvent` 는 `event_tag` 필수, `OnDelegate` 미지원 |
| `remove_transition` | `state, transition` | |
| `remove_node` | `node` | 다른 바인딩의 소스면 `NODE_REFERENCED`. 함수 노드는 `unbind_property` 로 |
| `set_node_values` | `node, values` | BP · 함수 노드 불가 |
| `bind_property` | `source:{struct, path}, target:{node, path}` | `struct` = ref · GUID · 노드 이름 · 컨텍스트 이름(`Actor` · `AIController`) · `parameters`. 빈 `path` = 구조체 자체. 같은 대상의 기존 바인딩(함수 포함)은 대체 |
| `unbind_property` | `target:{node, path}` | 함수 바인딩이면 함수 입력까지 지운다 |
| `bind_property_function` | `ref?, function, output?, target:{node, path}` | 함수 노드를 만들어 출력을 대상에 묶는다. 입력은 뒤의 `bind_property` 로(`target.node` = 이 ref). `output` 은 출력이 하나면 생략 |

`values` 는 인스턴스 데이터에서 먼저 찾고 없으면 노드 구조체에서 찾는다(거리 조건의 `Operator` · `bInvert` 는 노드 구조체). `Output` · `Context` 쓰기는 거부한다. 타입 경로는 `list_state_tree_node_types` 의 전체 경로만 받는다. 값 변환(JSON → ImportText · 값 → JSON)은 코어의 `Core/AnimMcpPropertyValues` 를 쓴다.

**실패 처리** — 사전 검증 실패의 `error.code` 는 처음 실패한 op 의 코드이고 `details.planned[]` 에 전체 결과가 있다. 적용 뒤 실패는 `details` 에 `stage`(`apply` · `compile` · `fixups` · `save`) · `messages` · `fixups` · `rollback{verified, method, undo_history_cleared, editor_reopened, revision}`. `method` = `undo`(우리 트랜잭션을 되돌림 — 앞선 Undo 기록 유지) · `none`(변경 없음) · `reload`(그 밖 — Undo 기록 전체 소실). 적용은 애셋이 더티면 `ASSET_DIRTY` 로 거부하므로 `save=false` 뒤에는 에디터에서 저장하거나 `revert_state_tree` 해야 한다.

오류 코드(StateTree 전용): 404 `STATE_NOT_FOUND` · `TYPE_NOT_FOUND`, 409 `ASSET_DIRTY` · `PIE_ACTIVE` · `TRANSACTION_ACTIVE` · `NODE_REFERENCED`(`details.transitions[]` · `bindings[]`), 400 `TYPE_NOT_ALLOWED` · `AMBIGUOUS_NAME` · `BINDING_OUT_OF_SCOPE` · `BAD_SOURCE_PATH` · `BAD_TARGET_PATH` · `INCOMPATIBLE_TYPES` · `NOT_BINDABLE` · `COMPILE_FIXUPS`. 공통 코드는 코어 README.

## 검증 — StateTree 시나리오 (PIE)

`run_state_tree_scenario` 는 트리가 실제로 어떻게 도는지 프레임 단위로 기록합니다. 입출력 예는 `Docs/StateTree/Phase2Report.md` §1 입니다.

```jsonc
{ "asset_path": "/Game/AI/Test/ST_P2_Loop", "map": "/Game/Maps/CombatTestMap",
  "pawn_class": "/Game/AI/Test/BP_P2_Enemy", "spawn_location": [1200, -800, 120],
  "events": [ { "tag": "GameplayEvent.Parried", "after": 0.5, "expect_transition": false, "window": 0.5 },
              { "tag": "GameplayEvent.Damaged", "when_state": "Idle", "expect_state": "Chase" } ],
  "expect_states": ["Idle", "Chase", "Attack", "Idle"], "duration": 20 }
```

- `spawn_location` 이 있으면 `pawn_class` 를 런타임 스폰합니다 — 그 폰의 `AutoPossessAI` 가 스폰을 허용해야 합니다. 없으면 맵에 있는 인스턴스를 찾고 `pawn_class` 는 필터입니다. 여럿이면 이름 순 첫 번째만 봅니다.
- **이벤트는 `sent` · `transitioned` · `reached_expected` 로 나눠 판정합니다.** `sent` = 트리가 실행 중이라 큐에 넣는 호출까지 감, `transitioned` = 엔진의 상태 진입 횟수가 늘어남, `reached_expected` = `expect_state` 가 활성으로 보임. 전환은 활성 목록이 아니라 진입 횟수로 봅니다 — 타임라인은 프레임 표본이라 한 프레임 안에 들어갔다 나온 상태는 이름이 없습니다. `state_changes` 가 2 이상 뛰면 그런 상태가 있었던 것입니다(`EnterState` 에서 실패하는 작업).
- `expect_transition: false` 는 무관한 이벤트의 대조 시험입니다.
- `expect_states` 는 순서만 봅니다. 사이에 다른 상태가 끼어도 통과하므로 엄밀한 순서는 `timeline` 을 직접 봅니다. 없으면 `duration` 까지 관측합니다.
- `clients: N` 은 리슨 서버 + 클라이언트 N 입니다. 사용자 플레이 설정과 무관하게 네트 모드 · 인원을 명시합니다. 관측은 서버 월드 인스턴스만, `worlds[]` 에 월드별 개수를 싣습니다.
- `log[]` 는 PIE 시작 뒤 StateTree · Navigation · PathFollowing 경고 이상입니다. 시험은 로그로 실패시키지 않습니다. 인스턴스를 못 찾으면 `candidates` 에 폰별 컨트롤러와 컴포넌트별 트리가 실립니다.
- **`EnterState` · `ExitState` 를 보려면 프로브 Task 를 상태에 넣는다** — `/Script/StateTreeMcpEditor.AnimMcpLifecycleProbeTask`(값 `Label` · `AbilityPath`). 결과는 `observed.probe`.
- `StateTreeMcp.16_RuntimeScenario` 를 필터로 직접 돌리면 시나리오 없이도 엔진 클래스 고정물로 실제로 돕니다.
- 에디터가 뜬 직후에는 30초쯤 기다리고 시작합니다 — 기동 직후 CEF 가속 페인트와 자동 테스트 플래그가 겹쳐 엔진 `check` 로 죽은 적이 있습니다(`Phase2Report.md` §4).

## 시험

Automation `StateTreeMcp.*`(분리 전 `AnimGraphMcp.StateTree.*`) — `run_automation_tests {"filter": "StateTreeMcp."}`. 실제 핸들러를 로컬 디스패처로 부르고, 애셋은 `/Game/AI/Test/` 에만 시각이 붙은 이름으로 만든다.

## 소스 구조

```text
Source/StateTreeMcpEditor/Private/
  StateTreeMcpEditorModule.cpp      코어에 Tool 9개 · state_tree_edit_paths 상태 필드 등록 / 해제
  Core/   AnimMcpStateTreeAsset     StateTree 경로 규칙([EditorMcp]/[AnimGraphMcp]) · 생성 · 컴파일 측정(fixups) · 복구 2단(Undo → 재로드) · 편집기 알림
          AnimMcpStateTreeBindings  바인딩 사전 검증(범위 · 경로 · 메뉴 · 타입) · 소스 후보
          AnimMcpStateTreeInspector 애셋 → JSON · 노드 타입 목록
          AnimMcpStateTreeOperations 배치: 기존 트리의 그림자로 계획(검증 + 실행 단계) · Preview · Apply
          AnimMcpStateTreeRuntime   run_state_tree_scenario — 시나리오 파싱 · 지연 명령 · 프레임별 관측 · 판정(전송 · 전환 · 기대 상태)
  Tools/  StateTreeMcpTools.cpp     Tool 핸들러 9개
  Tests/  AnimMcpStateTreeTests.cpp StateTreeMcp.* — §8 필수 항목 + PIE 거부 · 열린 편집기 · 런타임 시나리오 고정물
          AnimMcpStateTreeTestTypes 시험 전용 Evaluator · 생명주기 프로브 Task (meta=Hidden)
```

파일 이름의 `AnimMcp` 접두는 분리 전 이름 그대로입니다(이력 · 기존 문서 대조용).
