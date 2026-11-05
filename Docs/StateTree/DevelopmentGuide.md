# StateTree 자동화 개발 지침서 (교정본)

작성일: 2026-11-04  
대상: UE 5.7.4 · AstralBreak · M3(일반 몬스터 AI · 어그로)  
상태: **Phase 2 구현 · 자동 검증 완료(2026-11-05) — 결과는 [Phase2Report.md](Phase2Report.md). 다음은 M3 본 작업이다.** Phase 1 완료(2026-11-05, [Phase1Report.md](Phase1Report.md)) · 사용자 눈 확인 대기. Phase 0 완료(2026-11-04). 사용자가 가져온 원본 지침서를 엔진 소스와 기존 `AnimGraphMcp` 에 대조해 고쳤고, Phase 0 · 2 실측으로 §2 · §5 · §6 을 다시 고쳤다. 실측 · 변경 이유는 [Feasibility.md](Feasibility.md), 엔진 근거는 [APIResearch.md](APIResearch.md).

표기: **[확인]** = 엔진 · 프로젝트 소스를 읽어 확인. **[실측]** = Phase 0 · 2 실험으로 확인.

## 0. 원본에서 바꾼 것

| # | 원본 | 교정 | 이유 |
| :---: | :--- | :--- | :--- |
| 1 | 새 Editor 플러그인 · 새 HTTP 서버 | `AnimGraphMcp` 플러그인 안에 Tool 묶음 추가, Python 은 얇은 새 서버가 `bridge.py` 공유 | 브리지 · 토큰 · 봉투 · 멱등 캐시 · 경로 보호 · PIE 러너가 이미 있다. 이중 구현 금지 |
| 2 | 도구 약 60개 · 상태형 `begin_edit`/`commit`/`rollback` | Tool 9개 + `operations` 배치 하나 | 기존 `apply_graph_operations` 와 같은 방식. 세션 상태가 없다 |
| 3 | 바인딩을 Phase 2 로 미룸 | **Phase 1 에 포함** | `Input` 프로퍼티는 바인딩이 없으면 컴파일 오류. 원본 예시(거리 기반 전환)도 바인딩 없이는 불가 |
| 4 | `validate` 를 검사로 취급 | 엔진 `ValidateStateTree` 는 **데이터를 고친다** — 우리 검사는 읽기 전용으로 따로 둔다 | §2-4 |
| 5 | 컴파일 오류 JSON 에 `code` · `property` | 엔진 로그에 없는 필드라 제거 | §2-5 |
| 6 | Dry Run = 복제본에 적용 | 복제본은 GUID 가 전부 바뀌어 그대로 못 쓴다 → 사전 검증 + 실패 시 Undo, 안 되면 디스크 재로드 | §2-6 · §5 |
| 7 | 멀티플레이 Server/Client 런타임 구분 | 서버 월드만 본다 | AIController 는 서버에만 있다 |
| 8 | 최근 전환 기록 · 전환 사유 조회 | 활성 상태 폴링 타임라인 + 상태 진입 횟수로 대체, 사유는 제외 | 공개 API 없음(`WITH_STATETREE_TRACE_DEBUGGER` 추적만). 폴링만으로는 한 프레임 안의 전환을 놓친다 — §6 |
| 9 | BP 노드 생성(Phase 4) | 제외 | 프로젝트 원칙 = 게임플레이 로직은 C++ |
| 10 | Commandlet · CI(Phase 5) | 제외 | 헤드리스 실행은 사용자가 거부한 이력 · 프로젝트에 CI 없음 |
| 11 | `statetree.add_state` 같은 점 표기 · `statetree.ping` | `apply_state_tree_operations` 등 snake_case · ping 삭제 | 기존 Tool 이름 규칙 · 상태 확인은 `get_editor_status` |
| 12 | 공통 응답 `{success, ...}` | 기존 봉투 `{ok, tool, request_id, result, error, diagnostics}` | 전 Tool 통일. `revision_before/after` · `changed` 는 `result` 안 |
| 13 | `docs/StateTreeAPIResearch.md` | `Docs/StateTree/` | 저장소 폴더 규칙 |

## 1. 목표와 범위

**목표:** M3 의 StateTree 애셋을 Claude 가 만들고, 읽고, 컴파일하고, PIE 에서 실제 전환까지 확인하는 닫힌 고리를 만든다.

**완료 기준은 범용성이 아니라 실사용이다.** `ST_Enemy_Melee` 1개가 도구만으로 저작되어, PIE 에서 몬스터가 플레이어를 인지 → 추격 → 공격하고 그 상태 전환이 타임라인으로 확인되면 끝이다.

**이 도구가 줄이지 않는 M3 작업(C++):** AIController, 어그로 컴포넌트, 적 PawnData, 스폰, StateTree 커스텀 노드(GAS 어빌리티 실행 등), `UAstralGA_Enemy_TelegraphAttack` 의 '스폰 즉시 자체 반복' 구조를 AI 구동으로 바꾸는 일, 네트워크 3단계 테스트. 도구는 애셋 저작 · 검증 쪽만 맡는다.

## 2. 확인된 전제 (UE 5.7.4)

### 2-1. 모듈과 플러그인 [확인]

- `StateTree`(`StateTreeModule` · `StateTreeEditorModule` · `StateTreeTestSuite` · `StateTreeDeveloper`), `GameplayStateTree`(`GameplayStateTreeModule`), `PropertyBindingUtils` 로 나뉜다.
- `StateTree` · `GameplayStateTree` 는 Phase 0 에서 켰다(`AstralBreak.uproject` · `AnimGraphMcp.uplugin`). 두 구성 빌드 확인. [실측]
- `StateTreeEditorModule` 의 Public 헤더로 이 지침서의 편집 API 가 모두 닿는다. 클래스 단위 export 가 아니라 `UE_API` 멤버 단위 export 다 — 쓰려는 함수가 inline 이거나 `UE_API` 인지 확인할 것. `USTRUCT` 의 `StaticStruct` 는 API 표시 없이도 링크된다. [실측]
- 엔진 내장 AI 노드: `FStateTreeMoveToTask`, `FStateTreeRunEnvQueryTask`, `FStateTreeCompareDistanceCondition`, 공용 비교 · 태그 조건. **GAS 어빌리티 실행 Task 는 없다** — 프로젝트 C++ 로 만든다.

### 2-2. 생성 [확인]

- `IAssetTools::CreateAsset` + `UStateTreeFactory::SetSchemaClass` 를 쓴다. `ConfigureProperties` 는 클래스 선택 창을 띄우므로 호출하지 않는다(`CreateAsset` 은 호출하지 않음). 팩토리가 EditorData · Schema · EditorSchema · 루트 상태를 만들고 컴파일까지 한다. 저장은 하지 않는다. [실측 E1]
- `CreateAsset` 전에 존재 · 이름 형식 · 스키마를 **직접 확인**한다. 같은 이름은 대화형이면 덮어쓰기 창이 뜨고 무인이면 `Error` 로그 + `nullptr` 이다. 스키마가 없으면 `nullptr` 이지만 빈 패키지가 메모리에 남는다. [실측 E1]
- 스키마는 `UStateTreeAIComponentSchema`. `ContextActorClass` · `AIControllerClass` 는 **protected UPROPERTY 이고 세터가 없다.** 리플렉션으로 값을 넣은 뒤 `PostEditChangeChainProperty` 를 불러야 `ContextDataDescs` 가 갱신되고, 그 뒤 재컴파일해야 산출물에 들어간다. 원본의 생성 입력에는 이 값이 없어서, 없으면 Pawn · AAIController 기본형으로만 바인딩된다. [실측 E2]
- `FClassProperty::MetaClass` 는 private 이라 기대 기반 클래스는 Tool 안의 이름 표로 둔다.

### 2-3. 노드 생성 [확인]

- `AddTask<T>` · `AddEnterCondition<T>` · `AddEvaluator<T>` · `AddGlobalTask<T>` · `FStateTreeTransition::AddCondition<T>` 는 **컴파일 시점 타입 전용 템플릿**이다. 런타임에 이름으로 고르는 경로는 Private(`EditorNodeUtils::SetNodeTypeStruct`)에만 있다.
- 따라서 플러그인에 절차를 직접 둔다: `ID = FGuid::NewGuid()` → `Node.InitializeAs(Struct)` → `GetInstanceDataType()` 이 Struct 면 `Instance.InitializeAs`, Class 면 `InstanceObject = NewObject` → `GetExecutionRuntimeDataType()` 도 같은 방식. Private 헤더는 포함하지 않는다. [실측 E3]
- 타입은 전체 경로(`/Script/GameplayStateTreeModule.StateTreeMoveToTask`)로 찾는다. `FStateTreeDelayTask` 처럼 Private 헤더의 노드도 이 경로로는 쓸 수 있다. [실측 E3]
- 허용 판정은 `UStateTreeSchema::IsStructAllowed` · `IsClassAllowed`, 후보 목록은 `FStateTreeEditorModule::GetNodeClassCache()`. [실측 E3]
- 상태 추가는 Builder API(`AddRootState` · `AddChildState` · `AddTransition`)를 쓴다. `FStateTreeViewModel` 의 상태 조작은 선택 상태 기반이고 새 상태를 돌려주지 않아 자동화에 맞지 않는다.

### 2-4. `ValidateStateTree` 와 컴파일의 숨은 변경 [확인]

`UStateTreeEditingSubsystem::ValidateStateTree` 는 검사가 아니라 **수정**이다. `CompileStateTree` 와 `FindOrAddViewModel` 이 먼저 부른다.

**`RemoveInvalidBindings` 의 실제 규칙** [실측 E4]. 소스 경로는 값 뷰가 있을 때만 푼다. 컨텍스트는 메모리 없는 뷰라 건너뛴다.

| 경우 | 컴파일 | 바인딩 |
| :--- | :--- | :--- |
| 인스턴스 소스(파라미터 · 노드) 오타 · 비필수 대상 | **성공** | **조용히 삭제** |
| 인스턴스 소스 오타 · 필수 `Input` | 실패 | 삭제된 뒤 '바인딩 없음' 오류 — 메시지에 오타가 안 나온다 |
| 컨텍스트 소스 오타 | 실패 | 유지 |
| 대상 경로 오타 | **성공** | **조용히 삭제** |

삭제 로그는 기본 설정에서 **아예 남지 않는다**(`LogPropertyBindingUtils` 기본 등급 `Warning`, 삭제 로그는 `Log`).

- `EditorSchema->Validate` 가 스키마가 막은 Evaluator · Enter Condition · Consideration · Task 를 비운다.
- 컴파일 실패 시 `ResetCompiled()` 로 **기존 컴파일 결과까지 지운다.** 살아 있는 애셋에서 컴파일하면 실패만으로 그 애셋은 실행 불가가 된다. [실측 E5]
- **에디터의 `UStateTree::PostLoad` 는 무조건 `Compile()` 을 부른다** — 로드할 때마다 위의 모든 일이 일어난다. 컴파일 결과는 저장본에서 읽히지 않고 로드 때 다시 만들어진다. C++ 프로퍼티 이름 변경으로 풀리지 않게 된 바인딩은 로드 순간 사라지고 더티 표시도 없다. [실측 E5 · E6]
- `PreBeginPIE` 가 메모리의 모든 `UStateTree` 에 `CompileIfChanged()` 를 부른다 — 임시 복제본을 남겨 두면 함께 컴파일된다. [실측 Phase 2 — PIE 시작 때 다른 시험의 고장 난 트리 컴파일 실패 로그가 나온다]

대응: 바인딩은 넣기 전에 직접 검증하고, 컴파일 전후 바인딩 · 노드 수를 비교해 줄어든 것을 `fixups` 로 보고한다. 엔진 `ValidateStateTree` 를 '검증 Tool' 로 노출하지 않는다.

### 2-5. 컴파일 로그 [확인]

`FStateTreeCompilerLog::Messages` 는 protected 이고 getter 가 없다. **파생 구조체**로 읽어 `CompileStateTree` 에 넘긴다. 메시지에 있는 것은 `Severity` · `State` · `Item`(`FStateTreeBindableStructDesc`) · `Message` 뿐이다. 오류 코드와 프로퍼티 필드는 없다.

```json
{ "severity": "error", "state_id": "guid", "state_path": "Root/Chase",
  "item_id": "guid", "item_name": "MoveTo", "message": "엔진 원문" }
```

우리 코드(`INVALID_BINDING` 등)는 사전 검증 오류에만 붙인다.

### 2-6. 복제와 리비전 [확인]

- `UStateTreeEditorData::PostDuplicate` 는 무조건 `DuplicateIDs()` — **복제본의 GUID 는 전부 새 값**이고 대응표는 공개되지 않는다. GUID 를 쓰는 배치를 복제본에 그대로 적용할 수 없다.
- `UStateTreeEditorData` 는 `Within = "StateTree"` 라 EditorData 만 떼어 복제할 수 없다.
- 리비전은 `CalculateStateTreeHash`(EditorData CRC32). `UStateTree::LastCompiledEditorDataHash` 와 비교하면 '컴파일 필요' 를 알 수 있다. 둘 다 공개. 저장 · 재시작 · 재로드 · 재컴파일 · Undo 를 거쳐도 같은 데이터면 같은 값이다. [실측 E5 · E6 · E7]
- `stale` 은 메모리 안에서만 나타난다. 로드하면 항상 재컴파일되므로 `up_to_date` 또는 `failed` 다.
- `AddTask<T>` 류는 `FGuid::NewGuid()` — 같은 배치를 다시 돌려도 바이트는 다르다. '같은 결과' 는 GUID 정규화 뒤 구조 동일을 뜻한다.

### 2-7. 바인딩 [확인]

- 경로는 `FPropertyBindingPath`(`FromString` · `ResolveIndirectionsWithValue`). 5.6 이후 `FStateTreePropertyPath` 계열은 deprecated.
- **허용 소스의 단일 원천은 `GetBindableStructs(TargetStructID, ...)`.** 실행 경로상 앞선 구조체만 돌려주므로 범위 규칙을 직접 짜지 않고, 순환 검사도 필요 없다. 컴파일러도 같은 함수를 쓴다. [실측 E4]
- 타입 호환은 `UE::PropertyBinding::GetPropertyCompatibility`, 값 뷰는 `GetBindingDataViewByID`. `Promotable`(float → double)은 통과, `Incompatible` 만 거부. 값 뷰가 없는 컨텍스트는 `ResolveIndirections(구조체)` 로 푼다. 경로가 빈 소스는 구조체 자체다 — 타입은 `IsChildOf` 로 본다. [실측 E4]
- 소스 ID: 노드 = `FStateTreeEditorNode::ID`, 루트 파라미터 = `GetRootParametersGuid()`, 상태 파라미터 = `Parameters.ID`, 이벤트 = `GetEventID()`, 컨텍스트 = 스키마 디스크립터 ID.
- `Context` 프로퍼티는 컴파일러가 타입으로 **자동 바인딩**한다. 도구가 미리 묶지 않는다.
- **메뉴 노출과 컴파일은 규칙이 다르다.** 엔진 메뉴는 `UE::PropertyBinding::IsPropertyBindable` 로 거른다 — `CPF_Edit` + public 또는 `AllowPrivateAccess`. 컴파일러는 이 검사를 하지 않는다. `AAstralCombatCharacter` 의 프로젝트 프로퍼티 11개 중 메뉴에 나오는 것은 컴포넌트 3개뿐이다. §10 D-6. [실측 E2]
- `FStateTreeCompareDistanceCondition.Source` 는 필수 Input FVector 다. Actor 위치는 Property Function `/Script/GameplayStateTreeModule.StateTreeGetActorLocationPropertyFunction` 으로 얻는다 — `AddFunctionBinding` + 입력에 일반 바인딩. 공개 API 로 되고 재시작 왕복도 확인했다. §10 D-5. [실측 E4 · E6]
- **`Get Actor Location` 의 입력은 필수가 아니다.** 안 묶으면 컴파일 · 실행 모두 조용히 성공하고 출력이 `(0, 0, 0)` 으로 고정된다. 거리 조건은 폰이 어디 있든 원점 기준으로 재므로 트리가 멀쩡해 보인 채 전환이 일어나지 않는다. `inspect_state_tree` 로 입력 바인딩을 직접 확인한다. [실측 Phase 2 S5]

### 2-8. 파라미터 [확인]

`RootParameterPropertyBag` 는 private 이고 공개 API 는 추가(`CreateRootProperties` · `CreateParametersForStruct`)뿐이다. 추가는 `OnParametersChanged` 까지 포함해 동작한다. [실측] 엔진 테스트 스위트도 `const_cast` 를 쓴다. 변경 · 삭제 뒤 필요한 알림은 미확인이라 M3 범위에서 뺀다(§7 Phase 3).

### 2-9. 편집기 동기화 [확인]

`FindViewModel`(없으면 만들지 않음) → `NotifyAssetChangedExternally()`. `FindOrAddViewModel` 은 없을 때 ViewModel 을 만들고 `ValidateStateTree` 를 돌리므로 쓰지 않는다. 컴파일 뒤에는 성공 · 실패와 상관없이 엔진이 `OnPostCompile` 로 알린다. Undo · Redo 도 뷰에 알린다. [실측 E7]

트리 뷰는 알림을 받으면 행을 즉시 지우고 페인트 때 다시 만든다. 창이 그려지지 않으면(최소화) 행이 0 으로 남고 복원하면 바로 돌아온다 — 멈춤이 아니다. 시험에서 행을 볼 때는 행 수까지 비교한다. [실측 E7b]

### 2-10. 런타임 [확인]

- `UStateTreeComponent`: `GetStateTreeRunStatus()`(시작하지 못하면 `Unset`), `SendStateTreeEvent()`(`void` — 실행 중이 아니면 경고만), `GetActiveStateNames()`(`WITH_GAMEPLAY_DEBUGGER` 안, `Root` 포함, 이름 중복 가능). [실측]
- 트리 참조 `StateTreeRef` 와 `InstanceData` 는 protected 이고 getter 가 없다 — 리플렉션으로 읽는다. 상태 진입 횟수는 `FStateTreeExecutionState::StateChangeCount`. 컨텍스트의 `GetStateChangeCount` 는 `WITH_STATETREE_DEBUG` 전용이다. [실측]
- AIController 는 서버에만 존재한다. 멀티 PIE 에서는 서버 월드의 인스턴스만 찾는다. 클라이언트 월드에는 폰만 복제된다. [실측 S6]
- **컴포넌트 자동 시작을 끄고 Possess 에서 시작한다.** 자동 시작은 런타임 스폰에서 컨트롤러 `BeginPlay` 가 `Possess` 보다 먼저라 컨텍스트 Actor 가 없어 시작하지 못한다. 레벨 배치에서는 된다. [실측 S3 · S4]
- **Possess 시작은 ASC 보다 먼저다.** `StartLogic` 은 `APawn::PostInitializeComponents` 안에서 돌아 `AAstralCombatCharacter` 의 ASC 결합 · `BeginPlay` 의 어빌리티 부여보다 앞선다. 첫 상태가 GA 를 쓰면 시작을 늦춰야 한다. [확인]
- **언포제션 때 `StopLogic` 의 컨텍스트 검사가 실패한다.** `AAIController::OnUnPossess` 가 폰을 먼저 비운다. 그때 `Stop` 이 돌지 않아 `ExitState` 가 불리지 않는다. 경고 2줄은 실측, `ExitState` 미호출은 [확인]. M3 에서 `OnUnPossess` 오버라이드로 고친다 — [Phase2Report §6](Phase2Report.md).
- `AutoPossessAI` 기본값은 `PlacedInWorld` 라 런타임 스폰한 폰에는 컨트롤러가 붙지 않는다. [확인]
- `MoveTo` 가 `EnterState` 에서 실패하면 상태 이름이 타임라인에 보이지 않고 로그도 없다. 전환이 없는 상태가 끝나면 트리는 `Root` 첫 자식으로 돌아간다. [실측 S2 · S5]

### 2-11. 재사용할 프로젝트 자산 [확인]

| 쓸 것 | 위치 | 용도 |
| :--- | :--- | :--- |
| HTTP 브리지 · 토큰 · 봉투 · 멱등 캐시 | `Private/Bridge/AnimMcp*` | 그대로 |
| Tool 등록 | `AnimMcpTools.h` 에 `RegisterStateTreeTools` 추가 | 그대로 |
| 배치 패턴(`ParseOperations` · `ref` · `expected_revision` · Preview/Apply · `rollback_verified`) | `Core/AnimMcpOperations` | 같은 계약으로 새 구현 |
| 경로 보호 | `Core/AnimMcpAssetProtection` | 그대로 + 허용 경로 추가 |
| PIE 시나리오 · 잡 · 폴링 | `AnimMcpAutomationRunner` · `AnimMcpRuntimeScenario` | 관측 대상만 교체 |
| Python 브리지 클라이언트 | `Tools/mcp/anim_graph_mcp/bridge.py` | 공유 |

## 3. 구조

```text
Claude Code
  ├─ anim-graph-mcp (기존)
  └─ state-tree-mcp (신규, Tools/mcp/state_tree_mcp/server.py — 로직 없음, bridge.py 공유)
        │  HTTP 127.0.0.1:18765 + 토큰
        ▼
AnimGraphMcp 플러그인 (기존 브리지 · 디스패처)
  ├─ Tools/AnimMcpTools_StateTree.cpp          Tool 핸들러(얇게)
  ├─ Core/AnimMcpStateTreeAsset.cpp            경로 검사 · 생성 · 컴파일 측정 · 복구 2단 · 뷰 알림
  ├─ Core/AnimMcpStateTreeInspector.cpp        애셋 → JSON
  ├─ Core/AnimMcpStateTreeOperations.cpp       계획 · Preview · Apply
  ├─ Core/AnimMcpStateTreeBindings.cpp         경로 해석 · 호환 · 후보 목록
  └─ Core/AnimMcpStateTreeRuntime.cpp          PIE 관측
```

추가 의존성: `AnimGraphMcp.uplugin` 에 `StateTree` · `GameplayStateTree`, `Build.cs` 에 `StateTreeModule` · `StateTreeEditorModule` · `GameplayStateTreeModule` · `PropertyBindingUtils` · `PropertyBindingUtilsEditor`(`IsPropertyBindable`) · `GameplayTags`(`Tag` · `event_tag`) · `AIModule`(시나리오의 `AAIController`, Phase 2). Phase 0 의 `Slate` · `SlateCore` 는 Phase 1 시험이 위젯을 보지 않아 뺐다. 플러그인 이름 변경은 하지 않는다. 런타임 모듈 `AstralBreak.Build.cs` 에 `StateTreeModule` · `GameplayStateTreeModule`(Phase 2) — UBT 가 요구하지 않아 `.uproject` 의존성은 그대로다.

`[AnimGraphMcp]` ini 추가: `+StateTreeEditPaths=/Game/AI/` — 이 밖의 StateTree 는 생성 · 편집 거부. 읽는 코드와 함께 Phase 1 에서 넣는다. 시험 애셋은 `/Game/AI/Test/`.

## 4. Tool

| Tool | 쓰기 | 설명 |
| :--- | :---: | :--- |
| `create_state_tree` | ○ | `asset_path`, `schema_class`(기본 AI), `schema_properties?`(`ContextActorClass` · `AIControllerClass`). 덮어쓰기 없음. 순서는 [Feasibility §4](Feasibility.md) |
| `inspect_state_tree` | | 스키마 · 컨텍스트 · 상태 트리 · 노드(값 포함) · 전환 · 바인딩 · `revision` · `compile_state`(`up_to_date` · `stale` · `failed`). BP 노드도 읽기는 지원 |
| `list_state_tree_node_types` | | 스키마가 허용하는 노드 타입 + 프로퍼티(이름 · 타입 · 용도 `Input`/`Output`/`Context`/`Parameter`) |
| `list_state_tree_bindable_sources` | | 대상 노드 ID → `GetBindableStructs` 결과와 프로퍼티 |
| `preview_state_tree_operations` | | 사전 검증만. 데이터를 바꾸지 않는다 |
| `apply_state_tree_operations` | ○ | 배치 적용. `operations`, `expected_revision?`, `compile=true`, `save=true` |
| `compile_state_tree` | ○ | 수동 컴파일. 메시지 + `fixups` |
| `revert_state_tree` | ○ | 디스크 상태로 재로드. **Undo 기록 전체가 사라지고 열린 편집기가 닫혔다 열린다** — 응답에 `undo_history_cleared` · `editor_reopened` |
| `run_state_tree_scenario` | | PIE 시나리오 — job 시작, 결과는 기존 `poll_automation_tests`. §6 |

### operations (Phase 1)

```text
add_state            { ref?, parent?, name, type?, selection?, tag?, enabled? }
remove_state         { state, cascade? }     참조 중인 전환이 있으면 cascade 없이 거부
set_state_properties { state, properties }   allowlist: TasksCompletion, SelectionBehavior, Tag, bEnabled, CustomTickRate,
                                             Weight, RequiredEventToEnter(+bHasRequiredEventToEnter)
add_task             { ref?, state, type, values? }
add_enter_condition  { ref?, state, type, values?, operand?, indent? }
add_evaluator        { ref?, type, values? }
add_global_task      { ref?, type, values? }
add_transition       { ref?, state, trigger, target, event_tag?, priority?, delay?, conditions? }
remove_transition    { state, transition }
remove_node          { node }
set_node_values      { node, values }        인스턴스 데이터 프로퍼티
bind_property        { source: { struct, path }, target: { node, path } }
unbind_property      { target: { node, path } }
bind_property_function { ref?, function, output?, target: { node, path } }   D-5 — 함수 노드를 만들어 출력을 대상에 묶는다.
                                             입력은 같은 배치의 bind_property 로 묶는다(target.node = 이 op 의 ref)
```

`bind_property` · `bind_property_function` 의 소스 경로에 메뉴에 없는 프로퍼티가 있으면 `NOT_BINDABLE` 로 거부한다(D-6). 소스 `struct` 는 ref · GUID 외에 컨텍스트 이름(`Actor` · `AIController`)과 `parameters`(루트 파라미터)를 받는다. 경로가 비면 구조체 자체다.

`values` 는 인스턴스 데이터에서 먼저 찾고, 없으면 노드 구조체에서 찾는다 — 거리 조건의 `Operator` · `bInvert` 는 노드 구조체에 있다. `inspect` 도 같은 평평한 모양으로 돌려준다. `Output` · `Context` 프로퍼티 쓰기와 BP 노드 값 쓰기는 거부한다(`PROPERTY_NOT_ALLOWED`).

`add_state` 의 `type` 은 `state` · `group` 만 받는다. `linked` · `linked_asset` · `subtree` 는 §7 Phase 3 이다. `parent` 를 생략하면 Root 의 자식이다.

삭제와 바인딩: 지워지는 노드의 **입력** 바인딩은 op 가 직접 지운다(남겨 두면 컴파일이 조용히 지워 `fixups` 가 된다). 지워지는 노드가 다른 노드의 **소스**이면 `remove_node` 는 `NODE_REFERENCED` 로 거부하고, `remove_state` 는 전환 참조와 함께 `cascade` 없이 거부한다 — `cascade` 면 참조 전환 · 바인딩도 지운다. `unbind_property` 의 대상이 함수 바인딩이면 그 함수 노드의 입력 바인딩까지 지운다.

`apply` 를 `save=false` 로 부르면 애셋이 더티로 남아 다음 `apply` 는 `ASSET_DIRTY` 다. 저장 전용 Tool 은 없으므로 `revert_state_tree` 후 다시 하거나 에디터에서 저장한다.

`state` · `node` · `target` 은 GUID 또는 같은 배치의 `ref`. 이름 조회는 허용하되 중복이면 `AMBIGUOUS_NAME`. `target` 의 특수 값(`succeeded` · `failed` · `next_state`)은 `EStateTreeTransitionType` 에 대응한다. 엔진 프로퍼티 이름 그대로 쓴다: 전환 이벤트는 `RequiredEvent`(`EventTag` 는 deprecated), 가중치는 `Weight`.

## 5. Apply 순서

1. 허용 경로 · 보호 경로 · PIE 활성(`PIE_ACTIVE`) · 활성 트랜잭션(`TRANSACTION_ACTIVE` — 사용자 드래그 중이면 우리 트랜잭션이 거기 합쳐져 Undo 할 수 없다) · `expected_revision`(`REVISION_MISMATCH`) 확인.
2. 애셋이 이미 더티면 `ASSET_DIRTY` 거부 — 열린 편집기의 수동 변경을 덮지 않고, 재로드가 잃을 것이 없게 하기 위해서다. 한 번도 저장되지 않은 애셋도 더티라 여기서 걸린다.
3. 전체 ops 를 **변경 없이** 해석한다: ref · 타입 존재 · 스키마 허용 · 프로퍼티 · 값 · 삭제 참조 · 바인딩(소스 경로 · 대상 경로 · 타입 · `NOT_BINDABLE`). 계획은 기존 트리의 그림자를 op 순서대로 갱신하며 실행 단계를 만든다 — Preview 와 Apply 가 같은 계획을 쓴다.
   **예외 — 범위:** `GetBindableStructs` 는 실제 데이터를 따라가므로 같은 배치에서 만드는 노드는 넣을 수 없다. 범위 규칙을 직접 짜지 않는다(§2-7). 양쪽이 기존 노드일 때만 여기서 범위를 보고, 나머지는 Preview 응답에 `deferred: ["scope"]` 로 표시한다. **Preview 통과가 범위 통과를 보장하지 않는다.**
4. `QueueBefore = GetQueueLength() - GetUndoCount()` 를 기록하고 `FScopedTransaction` 안에서 Builder API 로 적용. `EditorData` 와 바꾸는 상태를 먼저 `Modify()`. 바인딩 op 는 넣기 직전에 살아 있는 데이터로 `PreflightBinding` 전체를 다시 돌린다(3의 예외 처리). **트랜잭션은 컴파일 전에 닫는다.**
5. 트랜잭션 밖에서, 바인딩 · 노드를 기록하고 컴파일. 사라진 항목은 `fixups`.
6. **실패 처리(적용 중 실패 · 컴파일 실패 · 의도치 않은 제거 · 저장 실패) — 2단:** [실측 E5]
   1. **Undo:** 실효 큐 길이(`GetQueueLength() - GetUndoCount()`)가 `QueueBefore + 1` 이면 `GEditor->UndoTransaction(false)` → `CompileStateTree` → 리비전 = 적용 전 && 실행 가능 여부 = 적용 전이면 끝. 편집기 · 뷰모델 · 앞선 Undo 기록이 그대로이고 0.02초 안쪽이다. **리비전보다 큐를 먼저 본다** — 컴파일이 불량 바인딩을 지우면 리비전은 적용 전과 같아져도 트랜잭션은 큐에 남는다. [실측 Phase 1 `07_Fixups`]
   2. **변경 없음:** 큐에 우리 트랜잭션이 없고 리비전 · 실행 가능 여부 · 컴파일 해시가 적용 전과 같으면 아무것도 하지 않는다(`method: "none"`). 실제 변경이 없으면 엔진이 트랜잭션을 버린다. 여기서 재로드로 가면 Undo 기록만 잃는다. `Modify` 는 값이 그대로여도 패키지를 더티로 만들므로 더티 표시만 적용 전으로 돌린다.
   3. **재로드:** 그 밖의 모든 경우. `UPackageTools::ReloadPackages(..., AssumePositive)` → **모든 포인터를 다시 찾는다**(GC 가 돈다) → 리비전 비교. Undo 기록 전체가 사라지고 열린 편집기가 닫혔다 열린다.
   4. 큐를 확인하지 않고 Undo 하지 않는다. 실제 변경이 기록되지 않은 트랜잭션은 엔진이 버리므로, 그대로 Undo 하면 **사용자의 앞선 작업이 되돌아간다.** [실측 E5e]
   5. 응답은 `rollback { verified, method, undo_history_cleared, editor_reopened, revision }`. `method` 는 `none` · `undo` · `reload`. 둘 다 실패하면 `verified=false` 로 그대로 보고한다.
7. 성공이면 저장 → `FindViewModel` 이 있으면 알림. `revision_before/after` · `refs` · `fixups` · 컴파일 메시지 반환. 적용 트랜잭션은 버퍼에 남는다 — 사용자가 Undo 할 수 있고, 그러면 `stale` 이 된다.

재로드 복구는 닫힌 · 열린 편집기 모두 통과했으므로 보상 저널 대안은 쓰지 않는다. 이유와 수치는 [Feasibility §2 E5](Feasibility.md).

## 6. 런타임 검증

`run_state_tree_scenario` 입력: `asset_path`(컴포넌트가 참조하는 트리), `map?`, `pawn_class?`, `spawn_location?`(있으면 `pawn_class` 를 런타임 스폰, 없으면 배치 인스턴스의 필터), `player_location?`, `events?[{ tag, after?, when_state?, expect_state?, expect_transition?, window? }]`, `expect_states?`, `duration?`, `start_timeout?`, `clients?`(0 = Standalone, N = 리슨 서버 + 클라이언트 N), `timeout?`. 입출력 예는 [Phase2Report §1](Phase2Report.md).

출력: `{ t, active_states[], run_status, state_changes, pawn_location }` 변화 시점 타임라인 + 이벤트별 판정 + 기대 순서 판정 + 월드별 인스턴스 수 + 경고 로그. 인스턴스를 못 찾으면 `candidates`.

- **이벤트는 세 단계로 판정한다: `sent` · `transitioned` · `reached_expected`.** [실측] 활성 목록 비교로 전환을 판정하면 안 된다 — 한 프레임 안에 들어갔다 나간 상태(`EnterState` 에서 실패하는 작업)를 놓쳐 `sent 인데 전환 없음` 이라는 거짓 판정이 나온다. 전환은 엔진의 상태 진입 횟수로 본다. 앞 표본보다 2 이상 뛰면 이름이 보이지 않은 상태가 있었다는 뜻이다.
- `sent` 는 트리가 실행 중이라 큐에 넣는 호출까지 갔다는 뜻이다. `SendStateTreeEvent` 는 결과를 돌려주지 않는다.
- `expect_transition: false` 는 무관한 이벤트의 대조 시험이다.
- 기대 순서가 없으면 일찍 끝내지 않는다. 있으면 그 순서와 이벤트가 끝날 때 끝낸다.
- 네트 모드 · 인원은 항상 명시한다. 사용자의 플레이 설정을 따르면 결과가 설정에 묶인다.
- 전환 사유는 다루지 않는다. 이벤트 뒤의 전환이 이벤트 때문인지는 구분하지 않는다.
- 기존 러너 규칙을 따른다: PIE 는 시나리오가 직접 시작하고, 이미 PIE 면 `PIE_ACTIVE`.
- 필터로 직접 돌리면 시나리오 없이 경고만 내지 않고 엔진 클래스 고정물로 실제로 돈다. `AnimGraphMcp.Runtime` 처럼 검사한 것이 없게 두지 않는다.

## 7. 단계

단계마다 빌드 → 에디터 → 검증을 하고, 다음 단계는 사용자 승인 뒤 시작한다. 커밋은 사용자.

### Phase 0 — 타당성 실험 (완료 2026-11-04)

플러그인 활성화 · 빌드(Development · DebugGame) 후, 시험용 Automation 테스트로 소스만으로 단정할 수 없는 것을 확인했다.

| # | 실험 | 통과 기준 | 판정 |
| :---: | :--- | :--- | :--- |
| E1 | `CreateAsset` + `SetSchemaClass` | 창 없이 생성 · 컴파일 성공 | 통과 |
| E2 | 스키마 클래스를 리플렉션으로 설정 | 프로젝트 클래스 프로퍼티가 바인딩 후보에 나온다 | 통과 |
| E3 | 이름으로 네이티브 노드 추가 | `MoveTo` · `CompareDistance` 포함 트리 컴파일 성공 | 통과 |
| E4 | 바인딩 정상 · 오타 | 정상은 통과, 오타는 사전 검증이 잡는다. §2-4 의 조용한 삭제 재현 | 통과 |
| E5 | 재로드 복구 | 닫힌 · 열린 편집기 둘 다 리비전 일치, 크래시 없음, 컴파일 결과 복원 | 통과 — 단 §5 의 1단을 Undo 로 변경 |
| E6 | 저장 → 에디터 재시작 → 재로드 | 리비전 동일 | 통과 |
| E7 | 열린 편집기 외부 수정 | 알림 뒤 트리 뷰 갱신 · Undo 동작 | 자동 판정 통과 · 화면은 사람 확인 |

산출물: [APIResearch.md](APIResearch.md), [Feasibility.md](Feasibility.md). 시험 코드 `Private/Tests/AnimMcpStateTreeFeasibilityTests.cpp`.

### Phase 1 — 저작 고리

Tool 8개(`run_state_tree_scenario` 제외) + §4 operations(`bind_property_function` 포함 — D-5) + 바인딩(메뉴에 없는 소스는 `NOT_BINDABLE` — D-6) + `state-tree-mcp` + Automation 테스트.

완료 기준: 내장 노드만으로 `Idle → Chase → Attack` 트리를 배치 한 번에 생성 · 컴파일 · 저장, 재시작 뒤 `inspect` 일치, 잘못된 입력은 오류와 함께 디스크 무변경, 사용자가 에디터에서 열어 수동 편집 가능.

### Phase 2 — 런타임 고리 (완료 2026-11-05)

`run_state_tree_scenario` + 최소 AIController `AAstralEnemyController`. 완료 기준: 최소 AIController 가 내장 노드 트리를 돌리고 PIE 타임라인으로 전환 순서 확인, 이벤트로 전환 확인. 결과는 [Phase2Report.md](Phase2Report.md). 시험 트리는 `state-tree-mcp` 로 저작했고 첫 실사용이다.

### 그다음 — M3 본 작업

C++ 작업 + `ST_Enemy_Melee` 저작. 이것이 도구의 최종 인수 시험이다.

### Phase 3 — 필요할 때만 (M5 보스 전 재검토)

필요가 실제로 생기면 그 항목만: 파라미터 편집 · Utility Consideration · Linked State/Asset · 상태 이동 · 복제 · Property Function 고급 기능(`bind_property_function` 은 D-5 로 Phase 1) · 출력 바인딩 · 애셋 비교.

### 제외

BP 노드 생성, Commandlet, CI 보고서, 상태형 편집 세션, 전환 사유 조회.

## 8. 테스트

Automation(`AnimGraphMcp.StateTree.*`)을 쓰고 `run_automation_tests` 로 돌린다. Phase 1 필수 항목:

1. 빈 트리 생성 · 잘못된 스키마 거부 · 덮어쓰기 거부
2. 부모/자식 상태 · 이름 중복 시 GUID 식별
3. 네이티브 Task · Enter Condition · Evaluator · Global Task 추가
4. 전환 연결 · 대상 삭제 거부와 cascade
5. 바인딩 정상 · 소스 오타 · 타입 불일치 · 범위 밖 소스
6. 컴파일 실패 시 자동 복구와 메시지 추출
7. 조용한 바인딩 제거의 `fixups` 감지
8. `expected_revision` 불일치 · 더티 애셋 · 허용 경로 밖 · PIE 중 거부
9. 저장 → 재로드 왕복, 같은 배치 반복 시 GUID 정규화 후 구조 동일
10. Node GUID 중복 없음
11. 실패 복구 2단 — Undo 경로에서 앞선 Undo 기록 유지, 트랜잭션이 버려진 경우 Undo 없이 재로드
12. 컨텍스트 소스 오타 · 대상 오타도 사전 검증이 잡는다
13. 메뉴에 없는 프로퍼티는 `NOT_BINDABLE` 로 거부(§10 D-6)
14. `bind_property_function` — 함수 출력을 필수 Input 에 묶고 입력은 같은 배치의 `bind_property` 로 묶어 컴파일 · 저장 · 재로드(§10 D-5). 없는 함수 타입 · 출력 프로퍼티 오타 · 타입 불일치 거부
15. 열린 편집기 — 적용 알림, Undo 복구 뒤 뷰모델 · 편집기 유지, `revert_state_tree` 의 `editor_reopened`(Phase 1 에서 추가. 뷰모델과 편집기 수만 보고 화면은 판정하지 않는다)

Phase 2 는 PIE 활성 상태 확인 · 이벤트 전송 — `16_RuntimeScenario`(대조 이벤트 · 숨은 전환 · 정상 전환) · `17_ScenarioJudge`(판정 함수) · `18_ScenarioRefused`(사전 검증) · `08b`(PIE 중 거부). 산출 애셋은 `/Game/AI/Test/` 에만 만든다.

## 9. 금지 사항

원본 §16 을 유지하고 다음을 더한다.

- 임시 `UStateTree` 복제본을 살려 두지 말 것(`PreBeginPIE` 가 컴파일한다).
- `FindOrAddViewModel` 을 Tool 경로에서 호출하지 말 것.
- 큐 길이 확인 없이 `UndoTransaction` 을 부르지 말 것(§5 — 사용자 작업이 되돌아간다).
- 트랜잭션을 연 채 재로드하지 말 것. 재로드 뒤 이전 포인터를 쓰지 말 것.
- 에디터 Private 헤더를 포함하지 말 것 — 필요한 절차는 공개 템플릿을 보고 옮긴다.
- 컴파일 성공을 바인딩 유지의 증거로 삼지 말 것(§2-4).
- 활성 상태 목록 비교로 전환 여부를 판정하지 말 것(§6). 시나리오 타임라인에 이름이 없다고 그 상태에 안 들어간 것이 아니다.
- 시험 BP 는 CDO 값을 쓴 뒤 컴파일할 것. 컴파일 뒤에 쓰면 같은 세션의 새 인스턴스가 네이티브 기본값을 받고, 맵에 배치했다면 그 값이 재정의로 저장된다. [실측 Phase 2]
- 도구 범위를 넓히기 전에 M3 애셋이 실제로 그 기능을 쓰는지 먼저 볼 것.

## 10. 정할 것

| # | 내용 | 추천 |
| :---: | :--- | :--- |
| D-1 | §7 축소 범위와 제외 목록 | 이대로 |
| D-2 | `AnimGraphMcp` 재사용(새 플러그인 없음) | 재사용 |
| D-3 | StateTree 애셋 경로 `/Game/AI/` | 이대로 |
| D-4 | 원격 실행 바인드 `0.0.0.0`(`DefaultEngine.ini:146`) | 이 기회에 `127.0.0.1` — 원본의 '외부 접근 금지' 와 충돌 |
| D-5 | Phase 1 완료 기준의 빈틈 — 거리 조건의 필수 FVector 입력에 묶을 op 가 없다 | **결정(2026-11-05): `bind_property_function` op 를 Phase 1 에 추가.** §4 · §7 · §8 반영. Property Function 은 §7 Phase 3 항목이었으므로 범위 변경이고, 범위는 op 하나뿐이다 — 함수 노드 삭제는 `unbind_property` 로 대상 바인딩을 지우는 것까지다 |
| D-6 | 메뉴에 없는 프로퍼티(`IsPropertyBindable=false`)를 도구가 묶어도 되는가 | **결정(2026-11-05): 거부(`NOT_BINDABLE`).** M3 C++ 에서 `AllowPrivateAccess` 또는 Evaluator 출력으로 낸다 |
| D-7 | `AnimMcpAutomationRunner` 경합 수정 시점([Feasibility §3](Feasibility.md)) | 해결(2026-11-04) — [Feasibility §6](Feasibility.md) |
