# StateTree 엔진 API 조사

작성일: 2026-11-04 · 대상: UE 5.7.4 · Phase 0 산출물  
함께 읽을 문서: [DevelopmentGuide.md](DevelopmentGuide.md)(지침서) · [Feasibility.md](Feasibility.md)(실측 결과 · 확정 설계)

지침서 §2 를 엔진 파일 · 줄 근거로 넓힌 문서다. 판정 표기:

- **[소스]** 소스를 읽어 확인했고 실행은 하지 않았다.
- **[실측 En]** Phase 0 실험 En 에서 실제로 돌려 확인했다.

경로 약어 (엔진 루트 `D:/UnrealSource/UnrealEngine-5.7.4-release/Engine` 기준):

| 약어 | 경로 |
| :--- | :--- |
| `ST/` | `Plugins/Runtime/StateTree/Source/` |
| `STE/` | `Plugins/Runtime/StateTree/Source/StateTreeEditorModule/` |
| `STM/` | `Plugins/Runtime/StateTree/Source/StateTreeModule/` |
| `GST/` | `Plugins/Runtime/GameplayStateTree/Source/GameplayStateTreeModule/` |
| `PBU/` | `Plugins/Runtime/PropertyBindingUtils/Source/` |
| `Ed/` | `Source/Editor/UnrealEd/` |

## 1. 모듈과 플러그인

| 사실 | 근거 | 판정 |
| :--- | :--- | :--- |
| `StateTree` · `GameplayStateTree` 는 `EnabledByDefault=false` | `StateTree.uplugin:13`, `GameplayStateTree.uplugin:13` | [소스] |
| `StateTree` 플러그인이 `PropertyBindingUtils` 를 끌어온다 | `StateTree.uplugin` Plugins 목록 | [소스] |
| 모듈 의존성 `StateTreeModule` · `StateTreeEditorModule` · `GameplayStateTreeModule` · `PropertyBindingUtils` · `PropertyBindingUtilsEditor` 로 이 조사의 API 가 전부 링크된다 | 두 구성 빌드 성공 | [실측] |
| `USTRUCT` 의 `StaticStruct` 는 구조체에 API 매크로가 없어도 링크된다. `Node.Get<FStateTreeNodeBase>()` · `TInstancedStruct<FPropertyBindingBindableStructDescriptor>::Get()` 가 다른 모듈에서 동작 | 링크 성공 | [실측] |
| `IsPropertyBindable` 은 `PropertyBindingUtilsEditor` export 다 — 교정본 §3 의 의존성 목록에 없던 모듈 | `PBU/PropertyBindingUtilsEditor/Public/PropertyBindingExtension.h:72` | [실측] |

## 2. 생성

| API | 위치 | 비고 |
| :--- | :--- | :--- |
| `UStateTreeFactory::SetSchemaClass` | `STE/Public/StateTreeFactory.h:26` | `TObjectPtr<UClass>` 를 받는다 |
| `UStateTreeFactory::FactoryCreateNew` | `STE/Private/StateTreeFactory.cpp:113` | EditorData · Schema · 루트 · EditorSchema 생성 뒤 컴파일(:121 ~ :135). 스키마가 없거나 컴파일 실패면 `nullptr` |
| `UStateTreeFactory::ConfigureProperties` | `STE/Private/StateTreeFactory.cpp:59` | 클래스 선택 창 — 호출하지 않는다 |
| `IAssetTools::CreateAsset` | `Source/Developer/AssetTools/Private/AssetTools.cpp:1718` | `ConfigureProperties` 를 부르지 않는다(부르는 쪽은 `CreateAssetWithDialog` :1990). 저장도 하지 않고 더티만 표시(:1778) |

실측에서 더 나온 것:

- 같은 이름이면 `CanCreateAsset` 이 대화형에서는 덮어쓰기 창을 띄우고(`:4851`), 무인 실행에서는 `Error` 로그 + `false` 다(`:4844 ~ :4847`). **Tool 은 `CreateAsset` 전에 존재를 직접 확인해야 한다.** [실측 E1 — 창 경로는 소스만]
- 스키마가 없으면 `nullptr` 이지만 빈 패키지가 메모리에 남는다(`CreatePackage` `:1755` 가 팩토리보다 먼저). 스키마 유효성도 먼저 본다. [실측 E1]
- `CanCreateAsset` 의 이름 오류도 `FMessageDialog` 다(`:4800`) — 경로 · 이름 형식 검사도 Tool 쪽 사전 검사 대상이다. [소스]

## 3. 스키마와 컨텍스트

| 사실 | 근거 | 판정 |
| :--- | :--- | :--- |
| `ContextActorClass`, `ContextDataDescs` 는 `UStateTreeComponentSchema` 의 protected | `GST/Public/Components/StateTreeComponentSchema.h:82` · `:98` | [소스] |
| `AIControllerClass` 는 `UStateTreeAIComponentSchema` 의 protected, 세터 없음 | `GST/Public/Components/StateTreeAIComponentSchema.h:37` | [소스] |
| 기본값은 Pawn · AAIController | `GST/Private/Components/StateTreeAIComponentSchema.cpp:19` ~ `:27` | [실측 E2] |
| `PostEditChangeChainProperty` 를 안 부르면 Descs 는 낡은 값 그대로 | `...AIComponentSchema.cpp:51`, `...ComponentSchema.cpp:84`. 대조군에서 값은 들어갔는데 Desc 는 `Pawn` | [실측 E2] |
| 로드 때는 `PostLoad` 가 값에서 Descs 를 다시 만든다 | `...AIComponentSchema.cpp:29`, `...ComponentSchema.cpp:77`. 재시작 뒤 프로젝트 클래스 유지 | [실측 E6] |
| 스키마를 바꾼 뒤에는 재컴파일해야 컴파일 산출물(`UStateTree::GetContextDataDescs`)에 들어간다 | 컴파일 뒤 산출물 Desc 확인 | [실측 E2] |
| `FClassProperty::MetaClass` 는 private 이고 getter 가 없다 — 리플렉션으로 기대 기반 클래스를 읽을 수 없다 | `Source/Runtime/CoreUObject/Public/UObject/UnrealType.h:3415` | [실측 — 컴파일 오류] |

## 4. 노드

| API | 위치 |
| :--- | :--- |
| `UStateTreeState::AddChildState` · `AddTask<T>` · `AddEnterCondition<T>` · `AddTransition` | `STE/Public/StateTreeState.h:256` · `:294` · `:272` · `:321` |
| `FStateTreeTransition::AddCondition<T>` | `STE/Public/StateTreeState.h:96` |
| `UStateTreeEditorData::AddSubTree` · `AddEvaluator<T>` · `AddGlobalTask<T>` | `STE/Public/StateTreeEditorData.h:229` · `:252` · `:274` |
| 런타임 타입 경로의 원본 절차(Private) | `STE/Private/Customizations/StateTreeEditorNodeUtils.cpp:468` |
| 허용 판정 `IsStructAllowed` · `IsClassAllowed` | `STM/Public/StateTreeSchema.h:36` · `:42` |
| 후보 목록 `GetNodeClassCache` · `GetScripStructs` | `STE/Public/StateTreeEditorModule.h:67`, `STE/Public/StateTreeNodeClassCache.h:100` |
| 캐시 루트 구조체 등록 | `STE/Private/StateTreeEditorModule.cpp:59` ~ `:68` |

- 이름으로 고르는 경로가 된다. `FindObject<UScriptStruct>(nullptr, TEXT("/Script/Module.Struct"))` + 지침서 §2-3 절차로 `MoveTo` · `Delay` · `CompareDistance` 트리가 컴파일됐다. [실측 E3]
- `FStateTreeDelayTask` 는 **Private 헤더**(`STM/Private/Tasks/StateTreeDelayTask.h:41`)에 있지만 리플렉션 경로로는 쓸 수 있다. 템플릿 `AddTask<T>` 로는 불가능했을 노드다. [실측 E3]
- AI 스키마 허용 목록 실측 결과 — Task 5개: `MoveTo` · `RunEnvQuery` · `DebugText` · `Delay` · `RunParallelStateTree`. Condition 13개: 태그 3 · 비교 Bool/Distance/Enum/Float/Int/Name · 객체 3 · Random. GAS 어빌리티 실행 Task 는 없다. [실측 E3]
- `StateTreeComponentSchema` 는 `MoveTo` 를 막는다. AI 태스크 허용은 `UStateTreeAIComponentSchema::IsStructAllowed` 가 더한다(`...AIComponentSchema.cpp:35`). [실측 E3]

필수 Input 판정: `Category = "Input"` 이고 `meta=Optional` 이 아니면 컴파일 오류(`STE/Private/StateTreeCompiler.cpp:2804` ~ `:2816`). `Category = "Context"` 는 타입으로 자동 바인딩(`:2840` ~ `:2850`). 용도 판정은 공개 함수 `UE::StateTree::GetUsageFromMetaData`(`STM/Public/StateTreePropertyBindings.h:673`).

## 5. `ValidateStateTree` 와 컴파일

호출 순서 (`STE/Private/StateTreeCompilerManager.cpp:173`):

1. `ValidateStateTree` — `:175`
2. `FStateTreeCompiler::Compile` — `:177`
3. 성공: `LastCompiledEditorDataHash = 현재 해시` — `:183`
4. 실패: `ResetCompiled()` · 해시 0 — `:189` · `:190`
5. `OnPostCompile` 브로드캐스트 — `:196` (성공 · 실패 모두)

`ValidateStateTree`(`STE/Private/StateTreeEditingSubsystem.cpp:87`)가 고치는 것:

| 동작 | 위치 | 비고 |
| :--- | :--- | :--- |
| 스키마가 막은 노드 제거 | `:285` → `STE/Private/StateTreeEditorSchema.cpp:13` | `Warning` 로그 |
| 풀 수 없는 바인딩 제거 | `:229` · `:288` → `PBU/PropertyBindingUtils/Private/PropertyBindingBindingCollection.cpp:196` | 아래 표 |
| 상태 링크 이름 갱신 · 연결 파라미터 · 트랜잭션 플래그 | `:289` ~ `:291` | |

### 바인딩 삭제의 실제 규칙 [실측 E4]

`RemoveInvalidBindings` 는 소스 값 뷰가 유효할 때만 소스 경로를 푼다(`PropertyBindingBindingCollection.cpp:219` · `:220`). 컨텍스트의 값 뷰는 메모리가 `nullptr` 이라(`STE/Private/StateTreeEditorData.cpp:1625`, `PBU/.../PropertyBindingDataView.h:57`) 건너뛴다. 그래서 결과가 네 갈래로 나뉜다.

| 경우 | 컴파일 | 바인딩 | 메시지 |
| :--- | :--- | :--- | :--- |
| 인스턴스 소스 오타 · 비필수 대상 | **성공** | 2 → 1 | 없음 |
| 인스턴스 소스 오타 · 필수 Input | 실패 | 1 → 0 | `Input property 'Source' ... is expected to have a binding.` — 오타는 언급 없음 |
| 컨텍스트 소스 오타 | 실패 | 유지 | `Malformed target property path for binding source property 'NoSuchProperty' ...` |
| 대상 경로 오타 | **성공** | 2 → 1 | 없음 |

**삭제 로그는 기본 설정에서 아예 남지 않는다.** `PROPERTY_BINDINGS_LOG(..., Log, ...)` 인데 카테고리 기본 등급이 `Warning` 이다(`PBU/PropertyBindingUtils/Public/PropertyBindingTypes.h:9`). 수집기를 걸었지만 0 줄이었다.

### 로드할 때마다 컴파일한다 [실측 E5 · E6]

에디터의 `UStateTree::PostLoad` 는 조건 없이 `Compile()` 을 부른다(`STM/Private/StateTree.cpp:423`). 결과:

- 컴파일 결과는 저장본에서 읽히는 것이 아니라 **로드 때 다시 만들어진다.** 재로드 복구가 `ResetCompiled` 를 되돌리는 이유가 이것이다.
- 로드만으로 `ValidateStateTree` 가 돈다. C++ 프로퍼티 이름이 바뀌어 바인딩이 풀리지 않으면, 그 애셋은 **로드 때 조용히 바인딩을 잃고 더티 표시도 없다.** 다음 저장에서 영구화된다.
- 에디터 안에서 `stale` 인 채 저장된 애셋도 로드 뒤에는 `up_to_date` 또는 `failed` 로 보인다. `stale` 은 메모리 안에서만 나타나는 상태다.

### `PreBeginPIE`

`CompileIfChanged` 를 메모리의 모든 `UStateTree` 에 호출한다(`STE/Private/StateTreeCompilerManager.cpp:238`). [소스]

## 6. 컴파일 로그

- `Messages` 는 protected(`STE/Public/StateTreeCompilerLog.h:110`). 파생 구조체로 읽는다. USTRUCT 일 필요는 없다. [실측]
- 필드: `Severity`(int32) · `State` · `Item` · `Message`(`:30` ~ `:42`). 지침서 §2-5 JSON 이 그대로 만들어진다 — `State->ID` · `State->GetPath()` · `Item.ID` · `Item.Name`. [실측 E4]
- 바인딩 오류 메시지는 원문 그대로 쓸 만하다. 다만 위 표처럼 원인을 가리키지 않는 경우가 있어 사전 검증이 먼저다.

## 7. 리비전과 복제

| 사실 | 근거 | 판정 |
| :--- | :--- | :--- |
| `CalculateStateTreeHash` = EditorData CRC32. Transient · `ExcludeFromHash` 제외 | `STE/Private/StateTreeEditingSubsystem.cpp:295`, `STE/Private/StateTreeObjectHash.cpp:8` | [소스] |
| 컴파일 직후 리비전 = `LastCompiledEditorDataHash` | | [실측 E1 · E3] |
| 저장 → 재시작 → 재로드 → 재컴파일 전 과정에서 리비전 불변 | | [실측 E6] |
| Undo / Redo 뒤 리비전이 이전 값으로 정확히 돌아온다 | | [실측 E7] |
| GUID 는 재로드 · 재시작을 넘어 유지 | | [실측 E5a · E6] |
| 편집 후 미컴파일 = 리비전 ≠ 컴파일 해시 → `stale` 판정 가능 | 값 `ba94d55c` vs `5b63b06a` | [실측 E7] |
| `PostDuplicate` 는 무조건 `DuplicateIDs` | `STE/Private/StateTreeEditorData.cpp:292` · `:1046` | [소스] |
| `Within = "StateTree"` | `STE/Public/StateTreeEditorData.h:64` | [소스] |

## 8. 바인딩

| API | 위치 |
| :--- | :--- |
| `FPropertyBindingPath` 생성자 · `FromString` · `ResolveIndirections` · `ResolveIndirectionsWithValue` | `PBU/PropertyBindingUtils/Public/PropertyBindingPath.h:251` · `:274` · `:294` · `:305` |
| `GetPropertyCompatibility` | `PBU/PropertyBindingUtils/Public/PropertyBindingTypes.h:163` |
| `IsPropertyBindable` | `PBU/PropertyBindingUtilsEditor/Public/PropertyBindingExtension.h:72`, 구현 `Private/PropertyBindingExtension.cpp:1142` |
| `GetBindableStructs` | `STE/Private/StateTreeEditorData.cpp:301` |
| `GetBindingDataViewByID` | `STE/Private/StateTreeEditorData.cpp:642` |
| `AddPropertyBinding` | `STE/Public/StateTreeEditorData.h:294` |
| `AddFunctionBinding` | `STE/Public/StateTreeEditorPropertyBindings.h:63` |
| `CreateParametersForStruct` | `STE/Public/StateTreeEditorData.h:102` |

- 사전 검증 시제품이 데이터를 건드리지 않고 범위 · 소스 경로 · 대상 경로 · 타입을 모두 잡았다. 컴파일 오류가 될 것과 조용히 지워질 것을 한 함수로 처리한다. 값 뷰가 유효하면 `ResolveIndirectionsWithValue`, 아니면(컨텍스트) `ResolveIndirections(구조체)` 다. [실측 E4]
- 범위 판정의 단일 원천은 `GetBindableStructs` 가 맞다. 컴파일러도 같은 함수를 부른다(`STE/Private/StateTreeCompiler.cpp:2566`). [실측 E4]
- `Promotable`(float → double)은 통과시켜야 한다. `Incompatible` 만 거부한다. [실측 E4]
- 경로가 빈 소스 = 구조체 자체. 컨텍스트 Actor 를 객체 입력에 묶을 때 쓴다. 타입 비교는 `GetPropertyCompatibility` 가 아니라 `IsChildOf` 로 직접 한다. [실측 E4]

### 메뉴 노출과 컴파일은 규칙이 다르다 [실측 E2 · E4]

엔진 바인딩 메뉴는 `IsPropertyBindable` 로 거른다. `CPF_Edit` 가 있고, protected/private 이면 `AllowPrivateAccess` 가 있어야 한다(`PropertyBindingExtension.cpp:1142`). **컴파일러는 이 검사를 하지 않는다.**

| 소스 경로 | 메뉴 | 컴파일 |
| :--- | :--- | :--- |
| `AAstralCombatCharacter.bTelegraphAttackEnabled` (protected EditAnywhere) | 안 나옴 | 성공 |
| `AAstralCharacter.HealthComponent` (protected + AllowPrivateAccess) | 나옴 | 시험 안 함 |
| `Actor.RootComponent.RelativeLocation` | 안 나옴 | 성공 |
| Property Function `Get Actor Location` | 나옴 | 성공 |

`AAstralCombatCharacter` 의 프로젝트 프로퍼티 11개 중 메뉴에 나오는 것은 `AllowPrivateAccess` 가 붙은 컴포넌트 3개뿐이다. 나머지 8개는 경로로는 풀리지만 메뉴에는 없다. 런타임 복사는 Phase 0 에서 확인하지 않았다.

### Actor 위치를 FVector 로 받기

`FStateTreeCompareDistanceCondition.Source` 는 필수 Input FVector 다. 엔진이 의도한 경로는 Property Function `FStateTreeGetActorLocationPropertyFunction`(`GST/Private/PropertyFunctions/StateTreeActorPropertyFunctions.h:22`)이다. 헤더는 Private 이지만 `/Script/GameplayStateTreeModule.StateTreeGetActorLocationPropertyFunction` 으로 찾을 수 있다.

```cpp
// 출력 → 대상. 반환된 경로의 StructID 가 새 함수 노드 ID
FPropertyBindingPath Out = Data->EditorBindings.AddFunctionBinding(Struct, {Segment("Output")}, TargetPath);
// 입력은 일반 바인딩으로 — 경로 없는 컨텍스트 Actor
Data->AddPropertyBinding(FPropertyBindingPath(ActorDescId), FPropertyBindingPath(Out.GetStructID(), "Input"));
```

컴파일 · 재시작 왕복 모두 확인했다. [실측 E4 · E6]

## 9. 파라미터

`CreateParametersForStruct(GetRootParametersGuid(), Descs)` 로 추가가 된다(`STE/Private/StateTreeEditorData.cpp:593`). `OnParametersChanged` 브로드캐스트까지 포함한다. [실측 — 모든 실험 트리의 `TargetLocation` · `bFlag`]  
변경 · 삭제는 Phase 0 에서 시험하지 않았다. 지침서 §2-8 판단 그대로다.

## 10. 복구에 쓰는 API

### 재로드

`UPackageTools::ReloadPackages(Packages, Error, AssumePositive)` — `Ed/Public/PackageTools.h:155`, 구현 `Ed/Private/PackageTools.cpp:835`.

| 동작 | 근거 | 판정 |
| :--- | :--- | :--- |
| `AssumePositive` 는 더티 패키지의 더티를 지우고 재로드 대상에 넣는다 | `PackageTools.cpp:732` ~ `:745` | [실측 E5a] |
| 기존 객체는 교체되고 옛 포인터 · 약한 포인터가 무효가 된다 | | [실측 E5a] |
| 재로드는 **트랜잭션 버퍼 전체를 비운다** — 다른 애셋 Undo 기록까지 | `PackageTools.cpp:1215` ~ `:1221` | [실측 E5b · E5e] |
| 열린 편집기는 닫혔다가 새 객체로 다시 열린다 | `Ed/Private/Subsystems/AssetEditorSubsystem.cpp:1438` · `:1457` ~ `:1484` · `:1501` | [실측 E5b] |
| 재오픈 시 `FindOrAddViewModel` → `ValidateStateTree` | `STE/Private/StateTreeEditor.cpp:161` | [실측 E5b — 리비전 · 더티 불변] |
| 재로드 애셋을 참조하는 다른 애셋의 편집기도 닫혔다 다시 열린다 | `AssetEditorSubsystem.cpp:1472` ~ `:1481` | [소스] |
| 활성 트랜잭션이 있으면 `UTransBuffer::Reset` 이 취소하고 버퍼를 비운다 — 재로드 전에 닫아야 한다 | `Ed/Private/EditorTransaction.cpp:1366` · `:1372` · `:1387` | [소스] |
| `FGlobalComponentReregisterContext` 로 월드 컴포넌트 전체를 재등록한다 — 큰 맵에서 비용 | `PackageTools.cpp:932` | [소스] |

### Undo

`UEditorEngine::UndoTransaction(bCanRedo)` — `Ed/Classes/Editor/EditorEngine.h:1034`.

| 동작 | 판정 |
| :--- | :--- |
| 트랜잭션 끝낸 뒤 컴파일 실패 → Undo → 재컴파일로 리비전 · 컴파일 결과 복원 | [실측 E5c · E5d] |
| Undo 가 패키지 더티도 원래대로(깨끗하게) 돌린다 | [실측 E5c · E5d] |
| `ValidateStateTree` 의 조용한 삭제도 `Data->Modify()` 스냅샷으로 함께 돌아온다 | [실측 E5e A] |
| 앞선 Undo 기록 · 열린 편집기 · 뷰모델이 그대로 유지 | [실측 E5d] |
| **실제 변경이 기록되지 않은 트랜잭션은 큐에서 사라진다**(`Ed/Private/EditorTransaction.cpp:1325` ~ `:1329`) | [실측 E5e B] |

마지막 항목이 위험 지점이다. 큐를 확인하지 않고 Undo 하면 **사용자의 앞선 작업이 되돌아간다.** `GEditor->Trans->GetQueueLength()`(`Ed/Classes/Editor/Transactor.h:580`)로 우리 트랜잭션이 남았는지 먼저 본다. E5e B 에서 큐는 1 → 1, 맨 위는 사용자 트랜잭션이었다.

## 11. 편집기 동기화

| API | 위치 | 판정 |
| :--- | :--- | :--- |
| `FindViewModel` — 없으면 만들지 않는다 | `STE/Private/StateTreeEditingSubsystem.cpp:38` | [실측 E5a] |
| `FindOrAddViewModel` — `ValidateStateTree` 호출 | 같은 파일 `:54` · `:73` | [소스] |
| `NotifyAssetChangedExternally` — `OnAssetChanged` 1회 | `STE/Private/StateTreeViewModel.cpp:782` | [실측 E7] |
| `PostUndo` · `PostRedo` — `OnAssetChanged` | `StateTreeViewModel.cpp:861` · `:867` | [실측 E7] |
| 컴파일 뒤 자동 알림 | `StateTreeEditingSubsystem.cpp:323` | [실측 E7] |

트리 뷰 동작: `OnAssetChanged` 를 받으면 `TreeView->RebuildList()` 로 **행을 즉시 지우고**(`STE/Private/SStateTreeView.cpp:436` · `:442`) 다음 틱에 다시 만든다. 위젯 틱은 페인트 때 돈다. 그래서 창이 그려지지 않으면 행 수가 0 으로 남고, 복원하면 바로 돌아온다. [실측 E7b]

## 12. 런타임 (Phase 2 용 — 이번에 실행하지 않음)

`GST/Public/Components/StateTreeComponent.h` — `SendStateTreeEvent` `:117` · `:120`, `GetStateTreeRunStatus` `:124`, `GetActiveStateNames` `:138`(`WITH_GAMEPLAY_DEBUGGER` 안, `:130`). [소스]

## 13. 자동화 러너 함정

`FEngineLoop::Tick` 순서: `GEngine->Tick` → **워커 Tick**(`Source/Runtime/Launch/Private/LaunchEngineLoop.cpp:6012`) → **코어 티커의 러너**(`:6072`) → `GFrameCounter++`(`:6100`).

`FAutomationWorkerModule::Tick` 은 `GIsAutomationTesting` 이고 latent 큐가 비어 있으면 `ReportTestComplete` → `StopTest` 를 부른다(`Source/Runtime/AutomationWorker/Private/AutomationWorkerModule.cpp:68` ~ `:92` · `:196`). 세션당 한 번이다(`bExecuteNextNetworkCommand` 를 내린다). 수정 전 러너는 이를 모른 채 `ExecuteNetworkCommands` 로 들어가 `check(GIsAutomationTesting)` 로 죽었다. [실측 — E7 첫 실행 크래시]

latent 명령이 **러너 호출**에서 끝나는 경우에만 났다. **워커 호출**에서 끝나면 안전했다. 시간 대기로 끝나는 명령은 프레임의 첫 호출이 워커라서 우연히 피해 왔다.

**수정(2026-11-04):** `ExecuteLatentCommands` 의 반환값은 호출 시작 때 큐가 비어 있었는지라서 이번 호출에서 빈 경우를 알리지 못한다(`Source/Runtime/Core/Private/Misc/AutomationTest.cpp:678` · `:705`). 러너는 호출 뒤 `IsLatentCommandQueueEmpty()`(`Source/Runtime/Core/Public/Misc/AutomationTest.h:1153`)를 보고 같은 호출에서 `StopTest` 까지 끝낸다. 테스트가 프레임을 넘길 때 큐는 항상 차 있으므로 워커 조건이 성립하지 않는다. 회귀 시험은 `AnimGraphMcp.Runner.*` 다.

**테스트 필터:** `RequestedTestFilter` 기본값은 Smoke 이고(`Source/Runtime/Core/Private/Misc/AutomationTest.cpp:1497`) 이 값이면 `EnqueueLatentCommand` 가 `check` 로 죽는다(`:474`). 세션 첫 Automation 호출이 `run_anim_scenario` 면 에디터가 종료됐다. [실측] `run_anim_scenario` 처럼 `FindTests` 를 거치지 않는 호출도 있으므로 러너는 `StartJobWithTests` 에서 전 필터를 설정한다. 시나리오 도구는 자동 시험으로 재현할 수 없다 — 새 에디터의 첫 호출로만 확인된다.

## 14. deprecated 대체표

| 쓰지 말 것 | 대체 | 근거 |
| :--- | :--- | :--- |
| `FStateTreePropertyPath` | `FPropertyBindingPath` | `STM/Public/StateTreePropertyBindings.h:176` |
| `FStateTreePropertyPathIndirection` | `FPropertyBindingPathIndirection` | 같은 파일 `:169` |
| `EStateTreePropertyAccessCompatibility` | `UE::PropertyBinding::EPropertyCompatibility` | `:116` |
| `EStateTreePropertyCopyType` | `EPropertyCopyType` | `:63` |
| `FStateTreePropertyIndirection` · `FStateTreePropertyCopy` · `FStateTreePropertyCopyBatch` | `FPropertyBindingCopyInfo` 계열 | `:353` · `:380` · `:412` |
| `AddPropertyBinding(FStateTreePropertyPath, ...)` | `FPropertyBindingPath` 오버로드 | `STE/Public/StateTreeEditorData.h:308` · `:314` |
| `GetAccessibleStruct` | `GetAccessibleStructsInExecutionPath` | `StateTreeEditorData.h:204` |
| `RootParameters` 직접 접근 | `GetRootParametersPropertyBag` | `StateTreeEditorData.h:386` |
| `AddPropertyBinding` · `RemovePropertyBindings` · `HasPropertyBinding` · `FindPropertyBinding` · `GetPropertyBindingSource` · `GetPropertyBindingsFor` · `RemoveUnusedBindings` | `AddBinding` · `RemoveBindings` · `HasBinding` · `FindBinding` · `GetBindingSource` · `GetBindingsFor` · `RemoveInvalidBindings` (`FPropertyBindingBindingCollection`) | `STE/Public/StateTreeEditorPropertyBindings.h:80` ~ `:154` |
| `GetAccessibleStructs` · `GetStructByID` · `GetDataViewByID` | `GetBindableStructs` · `GetBindableStructByID` · `GetBindingDataViewByID` | 같은 파일 `:202` ~ `:236` |
| `FStateTreeEditorPropertyCreationDesc` | `UE::PropertyBinding::FPropertyCreationDescriptor` | 같은 파일 `:179` |
| `FStateTreeTransition::EventTag` | `RequiredEvent.Tag` | `STE/Public/StateTreeState.h:168` |
| `FStateTreeNodeClassData::GetStructName` | `GetStructPath` | `STE/Public/StateTreeNodeClassCache.h:31` |
| `UPackageTools::ReloadPackages(..., bool bInteractive)` | `EReloadPackagesInteractionMode` 오버로드 | `Ed/Public/PackageTools.h:143` |

## 15. 실험에서 실제로 쓴 API 요약

Phase 0 시험 코드에 있던 것을 Phase 1 이 아래처럼 옮겼다(시험 파일은 `AnimMcpStateTreeTests.cpp` 로 대체). 실제 위치는 `Core/AnimMcpStateTree*` 다.

| 시험 코드 함수 | 옮길 곳 |
| :--- | :--- |
| `CreateTreeAsset` · `SetSchemaClassProperty` | `create_state_tree` |
| `InitNodeByStruct` · `AddNodeByStruct` | `Core/AnimMcpStateTreeOperations` |
| `PreflightBinding` | `Core/AnimMcpStateTreeBindings` |
| `FCompileLogReader` · `MessagesToJson` · `CompileAndMeasure` | `compile_state_tree` · Apply 5단계 |
| E5d 의 Undo → 재컴파일 → 리비전 비교, E5e 의 큐 확인 · 재로드 전환 | Apply 6단계 · `revert_state_tree` |
