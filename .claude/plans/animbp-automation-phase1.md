# AI Animation Blueprint Automation — Phase 1 보고서

> 작성 2026-10-10 · 기준 엔진 UE 5.7.4 소스 빌드 · 기준 프로젝트 AstralBreak (`feat/lockon_sync`, 3db3149)
> 성격: 기술 조사 + 아키텍처 결정 + 구현 계획. **이 단계에서 코드·애셋·설정은 변경하지 않았다.**
> 표기: ✅ 엔진/프로젝트 소스에서 직접 확인 · ⚠️ 추론 또는 외부 자료 · ❓ Phase 2에서 확인 필요

---

## 요약

- AnimGraph·State Machine·Transition Rule을 코드로 생성하는 데 필요한 API는 **전부 5.7.4 에디터 모듈(`AnimGraph`, `UnrealEd`, `BlueprintGraph`)에 공개 선언으로 존재한다.** 노드 생성(`FGraphNodeCreator`), 서브그래프 자동 생성(`PostPlacedNewNode`), 상태 간 전이(`CreateConnections`), 핀 연결(`TryCreateConnection`), 컴파일(`CompileBlueprint` + `FCompilerResultsLog`), 저장(`UEditorAssetSubsystem::SaveLoadedAsset`)까지 호출 순서를 소스에서 추적했다.
- **Python만으로는 불가능하다.** 파이썬 래퍼는 `BlueprintVisible` 프로퍼티와 `BlueprintCallable` 함수만 노출하는데, `UEdGraph::Nodes`·`UEdGraphNode::NodeGuid`·`UBlueprint::FunctionGraphs`는 전부 플래그 없는 `UPROPERTY()`이고 핀(`Pins`)은 UPROPERTY도 아니다. 그래프 조회조차 C++이 필요하다.
- **권장 아키텍처: Python MCP 서버(얇은 프록시) ↔ 로컬 HTTP/JSON ↔ C++ 에디터 플러그인(엔진 내장 `HTTPServer` 모듈).** 내장 HTTP 서버는 게임 스레드 티커로 돌아 핸들러가 게임 스레드에서 실행되고, 기본 바인드 주소가 `localhost`다. 두 요구(스레드 안전·로컬 전용)가 추가 코드 없이 충족된다.
- 기존 `Tools/ue_exec.py`(Python 원격 실행)는 **애셋 카탈로그·테스트 실행 보조**로 계속 쓰되 그래프 편집 채널로는 쓰지 않는다.
- 첫 수직 통합(Phase 2.5)의 전 경로가 확인된 API로 닫힌다. 미확정 사항은 §G에 모았다.

---

## A. 환경 조사 결과

### A-1. 엔진

| 항목 | 값 | 근거 |
| :--- | :--- | :--- |
| 버전 | 5.7.4 (CompatibleChangelist 47537391, 브랜치 UE5) | ✅ `Engine/Build/Build.version` |
| 루트 | `D:/UnrealSource/UnrealEngine-5.7.4-release` | ✅ |
| 번들 Python 버전 | 미확인 (디렉터리 열람 권한 거부) | ❓ |

### A-2. 프로젝트

| 항목 | 값 | 근거 |
| :--- | :--- | :--- |
| 루트 | `D:/UE5Projects/AstralBreak` | ✅ |
| 모듈 | 런타임 모듈 1개 `AstralBreak`. **에디터 모듈 없음, `Plugins/` 폴더 없음** | ✅ `AstralBreak.uproject`, `Source/` |
| 타깃 | `AstralBreak.Target.cs`, `AstralBreakEditor.Target.cs` (Editor 타깃은 있으나 ExtraModuleNames에 런타임 모듈만) | ✅ |
| 활성 플러그인 (uproject) | ModelingToolsEditorMode, EnhancedInput, GameplayAbilities, ModularGameplay, GameFeatures, MotionWarping | ✅ |
| 빌드 의존 | GameplayAbilities/Tags/Tasks, ModularGameplay, GameFeatures, MotionWarping, AIModule, NetCore, UMG/Slate, DeveloperSettings | ✅ `AstralBreak.Build.cs` |
| 기존 MCP 연동 | 없음 | ✅ |
| Python 에디터 스크립팅 | **사용 중.** `DefaultEngine.ini`에 `bRemoteExecution=True`, `AdditionalPaths=Tools/lib`. `Tools/ue_exec.py`가 UDP 멀티캐스트로 에디터를 찾아 스크립트를 실행 | ✅ `Config/DefaultEngine.ini:132-146`, `Tools/ue_exec.py` |

> ❓ **플러그인 활성 경로 불일치.** `PythonScriptPlugin.uplugin`과 `EditorScriptingUtilities.uplugin`은 둘 다 `"EnabledByDefault": false`이고 uproject에도 없는데, 프로젝트는 `unreal.EditorAssetLibrary`(EditorScriptingUtilities 소속)와 원격 실행을 사용해 왔다. 동작은 관측된 사실이므로 어떤 경로로 활성화되는지(에디터 로컬 설정 등) Phase 2 첫 단계에서 `IPluginManager`로 확인한다. 새 플러그인의 의존 선언에 영향을 준다.

### A-3. 애니메이션 관련 C++ 구조

| 클래스 | 역할 | 비고 |
| :--- | :--- | :--- |
| `UAstralAnimInstance` ([AstralAnimInstance.h](../../Source/AstralBreak/Animation/AstralAnimInstance.h)) | 유일한 AnimInstance 베이스. `NativeUpdateAnimation`(게임 스레드)에서 `FAstralAnimSnapshot`을 채우고 `NativeThreadSafeUpdateAnimation`(워커)에서 BlueprintReadOnly 프로퍼티로 산출 | **이미 스레드 안전 스냅샷 패턴** |
| 노출 프로퍼티 | `Speed`, `Acceleration`, `MovementDirection`(-180~180), `bIsOnGround`, `bIsInAir`, `bIsJumping`, `bIsFalling`, `bHasMovementInput`, `GroundDistance` + `GameplayTagPropertyMap` | 전부 `BlueprintReadOnly, Transient` → Transition Rule에서 바로 참조 가능 |
| 없는 것 | 락온 상태 플래그, 전투 스타일 플래그 | Phase 5 결정 사항 (§G) |
| 노티파이 | `AstralAnimNotify_GameplayEvent`, `AnimNotifyState_GameplayEventWindow`, `_RootMotionPawnCollisionPolicy`, `_InputFacing`(MotionWarping 파생) | 몽타주 저작은 `Tools/lib/ab_montage.py`가 이미 자동화 |

### A-4. 애셋 현황 (AnimBP 자동화의 입력)

| 종류 | 경로 | 비고 |
| :--- | :--- | :--- |
| 기존 AnimBP | `/Game/Animation/Hero/ABP_Hero_Base` | **운영 애셋 — 테스트 대상 금지.** 테스트는 별도 경로에 생성 |
| 1D 블렌드스페이스 | `/Game/Animation/Hero/Anims/Locomotions/BS_Hero_Locomotion1D` | Free Locomotion 후보 |
| 8방향 Walk/Run 루프 | 같은 폴더 `M_Neutral_{Walk,Run}_Loop_{F,FL,FR,L*,R*,B,BL,BR}` | Lock-On 2D 블렌드스페이스 재료 |
| 점프 | `Jump_Start`, `Jump_Apex`, `Jump_Land`, `Jump_Recovery`, `AS_Hero_Jump/FallLoop/Land` | |
| 공격 몽타주 | `/Game/Animation/Hero/Montages/AM_Hero_Attack1~3`, `AM_Hero_Finisher1` | 슬롯 이름은 Phase 5에서 조회 |
| 스켈레톤·메시 | `/Game/Characters/UEFN_Mannequin/Meshes/SK_UEFN_Mannequin` | Hero BP `BP_Hero_Vesper`가 사용하는지 Phase 2.5에서 확인 ❓ |

### A-5. 재사용 가능한 기존 자산

| 자산 | 재사용 방식 |
| :--- | :--- |
| `Tools/ue_exec.py` + `Tools/lib/ab_assets.py` | `list_animation_assets` 초기 구현 또는 교차 검증. MCP 서버가 subprocess로 호출 가능 |
| `Tools/lib/ab_blueprint.py` | 실측 제약 기록("EventGraph 노드 생성 불가")이 Python 한계의 1차 증거. 패턴(dry-run 기본, JSON 스펙 빌드)을 Tool 설계에 계승 |
| `Tools/scripts/run_automation_tests.py`, `read_automation_results.py` | Phase 6 런타임 검증 재사용 |
| `.claude/hooks/allow_readonly.py`, `settings.json` | 새 플러그인 빌드·실행 명령의 권한 경계 그대로 적용 |
| `.claude/skills/` 3종 | 네 번째 스킬(AnimBP)로 같은 형식 추가 |

---

## B. UE 5.7.4 API 검증표

모든 경로는 `Engine/Source/` 기준. 모듈 열은 Build.cs에서 의존 선언할 이름.

### B-1. 생성·컴파일·저장

| API | 헤더 | 모듈 | 접근 | 확인 내용 |
| :--- | :--- | :--- | :---: | :--- |
| `UAnimBlueprintFactory` | `Editor/UnrealEd/Classes/Factories/AnimBlueprintFactory.h` | UnrealEd | MinimalAPI | ✅ 멤버 `ParentClass`, `TargetSkeleton`, `PreviewSkeletalMesh`, `bTemplate` 공개. `ConfigureProperties()`는 **Slate 다이얼로그**를 띄우므로 호출 금지. `FactoryCreateNew`는 실패 시 `FMessageDialog::Open` **모달**(`Private/Factories/AnimBlueprintFactory.cpp:460`) → 사전 검증 필수 |
| `FKismetEditorUtilities::CreateBlueprint` | `Editor/UnrealEd/Public/Kismet2/KismetEditorUtilities.h:124` | UnrealEd | UNREALED_API | ✅ 팩토리가 실제로 호출하는 오버로드. `(ParentClass, Outer, Name, BPTYPE_Normal, UAnimBlueprint::StaticClass(), UBlueprintGeneratedClass::StaticClass(), CallingContext)`. 내부에서 `UEdGraphSchema_K2::GN_AnimGraph` 이름의 `UAnimationGraph`를 `AddDomainSpecificGraph`로 추가 (`Private/Kismet2/Kismet2.cpp:500-503`) |
| 팩토리 후처리 | `AnimBlueprintFactory.cpp:475-494` | | | ✅ 생성 후 `NewBP->TargetSkeleton`, `GeneratedClass`·`SkeletonGeneratedClass`의 `TargetSkeleton`을 직접 세팅. 직접 `CreateBlueprint`를 쓰면 **이 세 줄을 재현해야 한다** |
| `FKismetEditorUtilities::CanCreateBlueprintOfClass` | 같은 헤더 `:178` | UnrealEd | UNREALED_API | ✅ 사전 검증용 |
| `FKismetEditorUtilities::CompileBlueprint` | 같은 헤더 `:169` | UnrealEd | UNREALED_API | ✅ `(UBlueprint*, EBlueprintCompileOptions, FCompilerResultsLog*)` |
| `FCompilerResultsLog` | `Editor/UnrealEd/Public/Kismet2/CompilerResultsLog.h` | UnrealEd | | ✅ `NumErrors`(:109), `NumWarnings`(:112), `bSilentMode`(:115) → 토큰화 메시지에서 노드 참조를 꺼내 NodeGuid로 매핑 |
| `UEditorAssetSubsystem::SaveLoadedAsset` | `Editor/UnrealEd/Public/Subsystems/EditorAssetSubsystem.h:277` | UnrealEd | UNREALED_API | ✅ `(UObject*, bOnlyIfIsDirty)`. `DoesAssetExist`(:87), `DeleteAsset`(:155)도 동일 클래스. **EditorScriptingUtilities 플러그인 의존 없이** 저장 가능 |
| `FScopedTransaction` | `Editor/UnrealEd/Public/ScopedTransaction.h:21,28` | UnrealEd | UNREALED_API | ✅ `Cancel()`(:34) → `GEditor->CancelTransaction(Index)` (`Private/ScopedTransaction.cpp:46`). 취소가 객체 상태를 되돌리는지는 ❓ (Phase 2 실측) |
| `UBlendSpaceFactoryNew` / `UBlendSpaceFactory1D` | `Editor/UnrealEd/Classes/Factories/BlendSpaceFactory*.h` | UnrealEd | MinimalAPI | ✅ `TargetSkeleton` 멤버. `ConfigureProperties()` 역시 다이얼로그 → 직접 세팅 후 `FactoryCreateNew` ❓(축 설정 API 미조사, Phase 4) |
| `UAnimBlueprint` | `Runtime/Engine/Classes/Animation/AnimBlueprint.h` | Engine | BlueprintType | ✅ `TargetSkeleton`(:91), `bIsTemplate`(:100), `GetParentAnimBlueprint`(:162) |

### B-2. 그래프·노드 기본 (EdGraph 계층)

| API | 헤더 | 모듈 | 확인 내용 |
| :--- | :--- | :--- | :--- |
| `FGraphNodeCreator<T>` | `Runtime/Engine/Classes/EdGraph/EdGraph.h:273-313` | Engine | ✅ `CreateNode()` → 멤버 설정 → `Finalize()`. Finalize가 `CreateNewGuid` → `PostPlacedNewNode` → (핀 없으면) `AllocateDefaultPins` 순으로 호출. **소멸자에서 Finalize 누락을 checkf** |
| `UEdGraph::Nodes`, `SubGraphs` | `EdGraph.h:79, :100` | Engine | ✅ 둘 다 플래그 없는 `UPROPERTY()`. `SubGraphs`는 `WITH_EDITORONLY_DATA` |
| `UEdGraph::GraphGuid` | `EdGraph.h:104` | Engine | ✅ 그래프 식별자로 사용 가능 |
| `UEdGraph::RemoveNode` | `EdGraph.h:167` | Engine | ✅ `(Node, bBreakAllLinks, bAlwaysMarkDirty)` — 단, 서브그래프 보유 노드는 `DestroyNode()` 경로가 맞다 (아래) |
| `UEdGraphNode::NodeGuid` | `EdGraph/EdGraphNode.h:406` | Engine | ✅ 플래그 없는 `UPROPERTY()` FGuid |
| `UEdGraphNode::FindPin` / `GetAllPins` / `BreakAllNodeLinks` / `DestroyNode` / `ReconstructNode` | `EdGraphNode.h:580, 513, 661, 707, 712` | Engine | ✅ |
| `UEdGraphSchema::TryCreateConnection` | `EdGraph/EdGraphSchema.h:826` | Engine | ✅ virtual. `CanCreateConnection`(:773)으로 사전 판정 |
| `UEdGraphSchema::BreakPinLinks` / `BreakSinglePinLink` | `:1040, :1048` | Engine | ✅ |
| `UEdGraphSchema::TrySetDefaultValue` | `EdGraphSchema.h:928`, K2 오버라이드 `Editor/BlueprintGraph/Classes/EdGraphSchema_K2.h:575` | Engine / BlueprintGraph | ✅ 상수 핀 값 설정 경로 |
| `FBlueprintEditorUtils` | `Editor/UnrealEd/Public/Kismet2/BlueprintEditorUtils.h` | UnrealEd | ✅ `CreateNewGraph`(:328), `AddDomainSpecificGraph`(:432), `RemoveGraph`(:448), `MarkBlueprintAsModified`(:314), `MarkBlueprintAsStructurallyModified`(:304), `FindBlueprintForGraph`(:256), `FindBlueprintForNode`(:240), `AddMemberVariable`(:848), `RefreshAllNodes`(:147) |

### B-3. AnimGraph 노드 (모듈 `AnimGraph`, 헤더 `Editor/AnimGraph/Public/`)

`AnimGraph.Build.cs`: Public 의존 Core/CoreUObject/Engine/Slate/AnimGraphRuntime/BlueprintGraph. UnrealEd·KismetCompiler는 Private + 순환 참조. 플러그인은 `AnimGraph`, `BlueprintGraph`, `UnrealEd`, `AnimGraphRuntime`을 직접 선언한다.

| API | 헤더 | 확인 내용 |
| :--- | :--- | :--- |
| `UAnimationGraph` | `AnimationGraph.h` | ✅ `UEdGraph` 파생, `BlueprintType`. `GetGraphNodesOfClass`(:33)가 **유일한 BlueprintCallable** |
| `UAnimationGraphSchema` | `AnimationGraphSchema.h:23` | ✅ `UEdGraphSchema_K2` 파생 → 포즈 핀 연결도 `TryCreateConnection`. `CreateDefaultNodesForGraph`가 `UAnimGraphNode_Root` 1개 생성 (`Private/AnimationGraphSchema.cpp:241-248`). `IsPosePin`(:99) 정적 |
| `UAnimGraphNode_Base` | `AnimGraphNode_Base.h` | ✅ `ShowPinForProperties`(:205, `TArray<FOptionalPinFromProperty>`), `SetPinVisibility(bool, OptionalPinIndex)`(:470 → cpp:136, 내부에서 `ReconstructNode`), `GetPinProperty(FName)`(:524), `GetFNodeProperty()`/`GetFNode()`(:574/577 → cpp:462/480: `FAnimNode_Base` 파생 첫 구조체 프로퍼티를 리플렉션으로 탐색), `Binding`(:233, `UAnimGraphNodeBinding`)·`HasBinding`(:556) — Property Binding은 조회·보존 대상, `PropertyBindings_DEPRECATED`(:209) |
| 출력 핀 이름 | `Private/AnimGraphNode_Base.cpp:251-257` | ✅ 싱크 노드가 아니면 `"Pose"`(`PC_Struct`/`FPoseLink`) |
| `UAnimGraphNode_Root` | `AnimGraphNode_Root.h` | ✅ `FAnimNode_Root Node`; 입력 포즈 링크 프로퍼티는 `Result` (`Runtime/Engine/Classes/Animation/AnimNode_Root.h:17`) → 핀 이름 `"Result"` ❓(Phase 2.5에서 `FindPin` 실측) |
| `UAnimGraphNode_SequencePlayer` | `AnimGraphNode_SequencePlayer.h` | ✅ `FAnimNode_SequencePlayer Node`(:20). `SetAnimationAsset(UAnimationAsset*)` override(:57, 베이스 `AnimGraphNode_AssetPlayerBase.h:46`). 런타임 노드 `Sequence`·`PlayRate`·`bLoopAnimation`·`StartPosition`은 `PinHiddenByDefault, FoldProperty` (`AnimNode_SequencePlayer.h:115-141`), setter `SetSequence/SetLoopAnimation/SetPlayRate`(:151-152, :257) |
| `UAnimGraphNode_BlendSpacePlayer` | `AnimGraphNode_BlendSpacePlayer.h` | ✅ `FAnimNode_BlendSpacePlayer Node`(:21), `SetAnimationAsset` override(:47) |
| `UAnimGraphNode_Slot` | `AnimGraphNode_Slot.h:18` | ✅ `FAnimNode_Slot Node` (`SlotName`은 런타임 구조체 멤버 ❓ 이름 확인) |
| `UAnimGraphNode_LayeredBoneBlend` | `AnimGraphNode_LayeredBoneBlend.h` | ✅ `AddPinToBlendByFilter()`/`RemovePinFromBlendByFilter`(:21-22) ANIMGRAPH_API. 본 필터 데이터는 `FAnimNode_LayeredBoneBlend` 멤버 ❓ |
| `UAnimGraphNode_BlendListByBool` / `ByEnum` | 각 헤더 `:17/:21` | ✅ `Node` 멤버 존재. 핀 구성은 베이스 `UAnimGraphNode_BlendListBase` ❓ |
| `UAnimGraphNode_SaveCachedPose` / `UseCachedPose` | `:22,:25` / `:21,:24` | ✅ `CacheName`(FString), `SaveCachedPoseNode`(weak) |
| `UAnimGraphNode_LinkedAnimLayer` | `AnimGraphNode_LinkedAnimLayer.h` | ✅ 존재 (조회·보존만, 편집은 Phase 6) |

### B-4. State Machine 계층 (모듈 `AnimGraph`)

| API | 헤더 | 확인 내용 |
| :--- | :--- | :--- |
| `UAnimGraphNode_StateMachine` | `AnimGraphNode_StateMachine.h` | ✅ `FAnimNode_StateMachine Node`. 베이스 `UAnimGraphNode_StateMachineBase::EditorStateMachineGraph`(`_StateMachineBase.h:23`) |
| 상태머신 그래프 자동 생성 | `Private/AnimGraphNode_StateMachineBase.cpp:141-167` | ✅ `PostPlacedNewNode`가 `FBlueprintEditorUtils::CreateNewGraph(this, NAME_None, UAnimationStateMachineGraph, UAnimationStateMachineSchema)` → `RenameGraphWithSuggestion("New State Machine")` → `Schema->CreateDefaultNodesForGraph` → 부모 그래프 `SubGraphs`에 추가. **즉 `FGraphNodeCreator::Finalize()` 한 번으로 상태머신 그래프·Entry 노드까지 생긴다** |
| `UAnimationStateMachineGraph` | `AnimationStateMachineGraph.h` | ✅ `EntryNode`(:22), `OwnerAnimGraphNode`(:26) |
| `UAnimationStateMachineSchema` | `AnimationStateMachineSchema.h` | ✅ `CreateDefaultNodesForGraph`가 `UAnimStateEntryNode` 생성·`EntryNode` 세팅 (`Private/...Schema.cpp:131-143`). `TryCreateConnection`(:216-242)이 State↔State 핀 방향을 보정하고 `MarkBlueprintAsModified`. **`CreateAutomaticConversionNodeAndConnections`(:244-272)가 두 상태 사이에 `UAnimStateTransitionNode`를 자동 스폰하고 `CreateConnections`까지 수행** → 에디터에서 드래그로 전이 만드는 것과 동일 경로 |
| `UAnimStateNode` | `AnimStateNode.h` | ✅ `BoundGraph`(:31). `PostPlacedNewNode`(cpp:130-156)가 `UAnimationStateGraph`+`UAnimationStateGraphSchema`로 BoundGraph 생성·기본 노드(`UAnimGraphNode_StateResult`) 생성·`SubGraphs` 추가. `GetPoseSinkPinInsideState()`(:74), `GetResultNodeInsideState()`(:77) ANIMGRAPH_API. 핀: 입력 `"In"`, 출력 `"Out"` (카테고리 `"Transition"`, cpp:32-36). `DestroyNode`(cpp:158-170)가 `RemoveGraph(Recompile)` |
| `UAnimStateNodeBase` | `AnimStateNodeBase.h` | ✅ `GetTransitionList`(:44), `GetAnimBlueprint`(:49), `GetBoundGraph`(:46) |
| `UAnimStateEntryNode` | `AnimStateEntryNode.h` | ✅ `GetOutputNode()`/`GetOutputPin()`(:29-30) ANIMGRAPH_API. 삭제·복제 불가 |
| `UAnimStateTransitionNode` | `AnimStateTransitionNode.h` | ✅ `BoundGraph`(:26, 규칙 그래프), `CustomTransitionGraph`(:30), `PriorityOrder`(:35), `CrossfadeDuration`(:39), `BlendMode`(:46), `bAutomaticRuleBasedOnSequencePlayerInState`(:62), `LogicType`(:82), `Bidirectional`(:100), `bDisabled`(:104). `CreateConnections(Prev, Next)`(:173 → cpp:340-355: 핀 0을 Prev 출력에, 핀 1을 Next 입력에 `MakeLinkTo`), `GetPreviousState/GetNextState`(:171-172), `RelinkHead/Tail`(:179/185). `PostPlacedNewNode`(cpp:109)가 `CreateBoundGraph()`(cpp:671-692: `UAnimationTransitionGraph`+`UAnimationTransitionSchema`, 이름 `"Transition"`) 호출 |
| `UAnimationTransitionGraph` | `AnimationTransitionGraph.h` | ✅ `UAnimationGraph` 파생. `GetResultNode()`(:18) → `UAnimGraphNode_TransitionResult` |
| `UAnimGraphNode_TransitionResult` | `AnimGraphNode_TransitionResult.h` | ✅ `FAnimNode_TransitionResult Node`. 런타임 `bCanEnterTransition`은 `PinShownByDefault` (`AnimNode_TransitionResult.h:17-18`) → **bool 입력 핀 `"bCanEnterTransition"`이 기본 노출** ❓(핀 이름 실측) |
| `UAnimationStateGraph` | `AnimationStateGraph.h` | ✅ `GetResultNode()` → `UAnimGraphNode_StateResult` |
| `UAnimStateAliasNode`, `UAnimStateConduitNode` | 각 헤더 | ✅ 존재 (Phase 6) |

### B-5. Transition Rule 표현식 (모듈 `BlueprintGraph`, `Engine`)

| API | 헤더 | 확인 내용 |
| :--- | :--- | :--- |
| `UK2Node_VariableGet` | `Editor/BlueprintGraph/Classes/K2Node_VariableGet.h` | ✅ 베이스 `UK2Node_Variable::VariableReference`(`K2Node_Variable.h:58`, `FMemberReference`), `SetFromProperty(Property, bSelfContext, OwnerClass)`(:120) |
| `FMemberReference::SetSelfMember` / `SetExternalMember` | `Runtime/Engine/Classes/Engine/MemberReference.h:187 / :177` | ✅ AnimInstance 자기 프로퍼티는 `SetSelfMember(FName)` |
| `UK2Node_CallFunction::SetFromFunction` | `K2Node_CallFunction.h:217` | ✅ virtual |
| `UK2Node_PromotableOperator` | `K2Node_PromotableOperator.h` | ✅ `SetFromFunction` override(:68), 와일드카드 승격 노드. MVP에서는 **단순 `UK2Node_CallFunction` + 구체 함수**를 권장 (승격 로직 회피) |
| `UKismetMathLibrary::Greater_DoubleDouble` / `Less_DoubleDouble` / `BooleanAND` | `Runtime/Engine/Classes/Kismet/KismetMathLibrary.h:567 / :563 / :229` | ✅ 전부 `BlueprintPure` |
| 멀티스레드 평가 | `Runtime/Engine/Classes/Animation/AnimInstance.h:376 bUseMultiThreadedAnimationUpdate`, `:1378 NativeThreadSafeUpdateAnimation` | ✅ 상태머신 getter류는 전부 `BlueprintThreadSafe`(:1068-1144). 프로젝트 AnimInstance는 스냅샷 패턴을 이미 따르므로 **그 프로퍼티를 읽는 규칙은 스레드 안전** |

### B-6. 통신 (모듈 `HTTPServer`, `Runtime/Online/HTTPServer/`)

| API | 헤더 | 확인 내용 |
| :--- | :--- | :--- |
| `FHttpServerModule` | `Public/HttpServerModule.h` | ✅ `FTSTickerObjectBase` 상속(:26) → **게임 스레드 티커**. `Get()`이 `check(IsInGameThread())`(cpp:111). `GetHttpRouter(Port, bFailOnBindFailure)`(:55), `StartAllListeners/StopAllListeners`(:68/73). `Tick`이 모든 Listener → Connection을 틱(cpp:182-195, `HttpListener.cpp:152,229`) |
| 스레드 결론 | | ✅ accept/recv/핸들러 호출 전부 게임 스레드 틱 안. **핸들러는 게임 스레드에서 실행된다.** 별도 디스패치 없이 UObject 편집 가능. 다만 핸들러가 길면 에디터 프레임이 멈춤 → 긴 작업은 `OnComplete`를 보관하고 다음 틱에 완료 가능 |
| `IHttpRouter::BindRoute` | `Public/IHttpRouter.h:34` | ✅ `(FHttpPath, EHttpServerRequestVerbs, FHttpRequestHandler)` → `FHttpRouteHandle`. `UnbindRoute`(:41). `RegisterRequestPreprocessor`(:49) — 토큰 검사 지점 |
| `FHttpRequestHandler` | `Public/HttpRequestHandler.h:19` | ✅ `TDelegate<bool(const FHttpServerRequest&, const FHttpResultCallback&)>`. true 반환 = 언젠가 OnComplete 호출 약속(비동기 허용) |
| `FHttpServerRequest` | `Public/HttpServerRequest.h` | ✅ `PeerAddress`, `RelativePath`, `Verb`, `Headers`, `QueryParams`, `PathParams`, `Body(TArray<uint8>)` |
| `FHttpServerResponse` | `Public/HttpServerResponse.h` | ✅ `Create(FString, ContentType)`(:56), `Ok()`(:99), `Error(Code, ErrorCode, Msg)`(:109). `FHttpResultCallback = TFunction<void(TUniquePtr<FHttpServerResponse>&&)>` |
| 바인드 주소 | `Private/HttpServerConfig.h:13`, `.cpp:17`, `HttpListener.cpp:64-75` | ✅ 기본 `"localhost"` → `SetLoopbackAddress()`. `[HTTPServer.Listeners] DefaultBindAddress`/`ListenerOverrides`로 변경 가능. **기본값이 이미 127.0.0.1 전용** |
| 선례 | `Plugins/VirtualProduction/RemoteControl/Source/WebRemoteControl/Private/WebRemoteControl.h` | ✅ Remote Control이 같은 `IHttpRouter`로 30여 라우트를 운영 (:106-136) — 패턴 참고 |
| 게임 스레드 디스패치(대안) | `Runtime/Core/Public/Async/Async.h:463 AsyncTask(ENamedThreads, TUniqueFunction)` | ✅ 다른 전송 계층을 쓸 경우에만 필요 |

### B-7. Python 노출 범위 (왜 Python으로는 안 되는가)

| 근거 | 위치 | 의미 |
| :--- | :--- | :--- |
| `IsScriptExposedProperty` | `Plugins/Experimental/PythonScriptPlugin/Source/PythonScriptPlugin/Private/PyGenUtil.cpp:1608-1611` | ✅ 파이썬 속성으로 노출되는 프로퍼티 = `CPF_BlueprintVisible \| CPF_BlueprintAssignable` |
| `ShouldExportEditorOnlyProperty` | 같은 파일 `:1810-1814` | ✅ `get_editor_property`가 닿는 범위 = `CPF_Edit` |
| `UEdGraph::Nodes`, `UEdGraphNode::NodeGuid`, `UBlueprint::FunctionGraphs` | `EdGraph.h:79`, `EdGraphNode.h:406`, `Engine/Blueprint.h:543` | ✅ 셋 다 플래그 없는 `UPROPERTY()` → **Python에서 읽을 수 없음** |
| `UEdGraphNode::Pins` | `EdGraphNode.h` | ✅ UPROPERTY 아님 → 불가 |
| `UBlueprintEditorLibrary` | `Editor/BlueprintEditorLibrary/Public/BlueprintEditorLibrary.h` | ✅ 그래프 단위(`FindGraph`, `AddFunctionGraph`, `RemoveGraph`, `CompileBlueprint`, `AddMemberVariable`, `CreateBlueprintAssetWithParent`)만. 노드·핀 API 없음 |
| `UAnimationBlueprintLibrary` | `Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h` | ✅ 이름과 달리 **AnimSequence 편집**(노티파이·커브) 라이브러리. AnimGraph 무관 |
| 프로젝트 실측 | `Tools/lib/ab_blueprint.py:4` | ✅ "EventGraph 노드 생성 불가" 기록 |

결론: Python으로 가능한 것은 `UAnimationGraph::GetGraphNodesOfClass`로 노드 객체 목록을 얻고 `EditAnywhere` 멤버(`Node` 구조체 등)를 읽는 정도다. 핀·연결·Guid·서브그래프는 C++만 가능하다. **§6 역할 분리(Python = MCP 서버·보조, C++ = 그래프 편집)는 확인된 사실에 의해 강제된다.**

---

## C. 아키텍처 결정서

### C-1. 대안 비교

| 기준 | ① Python MCP + 내장 HttpServer C++ 플러그인 (권장) | ② 기존 오픈소스 Unreal MCP 확장 | ③ Python 원격 실행 확장 (현 `ue_exec.py`) | ④ Remote Control API |
| :--- | :--- | :--- | :--- | :--- |
| 5.7.4 호환 | ✅ 엔진 모듈만 사용 | ⚠️ 프로젝트별 상이 (5.6~5.8 표기) | ✅ 이미 동작 | ✅ 엔진 플러그인 |
| AnimGraph 편집 | ✅ 전 API 접근 | ⚠️ 대부분 Actor/일반 BP 중심. AnimBP 상태머신 깊이 미검증 | ❌ 핀·연결·Guid 접근 불가 (B-7) | ❌ 프로퍼티·함수 호출 노출만. 그래프 편집 라우트 없음 |
| 게임 스레드 안전 | ✅ 티커 기반 → 핸들러가 게임 스레드 | ⚠️ 대부분 자체 TCP 스레드 → 디스패치 코드 품질 의존 | ✅ 원격 실행도 Tick 기반 (`PythonScriptRemoteExecution.h:36`) | ✅ 같은 HttpServer |
| 구현 난이도 | 중 (플러그인 1개 + 얇은 서버) | 저~중 (단, 코드 이해·포크 유지) | 저 (하지만 목표 달성 불가) | 중 (그래프 편집은 결국 C++ 추가) |
| 확장성·재사용 | ✅ 프로젝트 비의존 플러그인 | ⚠️ 상류 변경 추적 | ⚠️ 스크립트 뭉치 | ⚠️ RC 프리셋 모델에 종속 |
| 외부 의존 | Python `mcp` 패키지만 | 저장소별 상이 | 없음 | 없음 |
| 디버깅 | ✅ curl로 직접 호출, UE 로그 | ⚠️ | ✅ | ✅ |
| 보안 | ✅ 기본 loopback, 라우트 화이트리스트 | ⚠️ 일부가 임의 Python 실행 노출 | ⚠️ 임의 코드 실행 채널 | ⚠️ 임의 함수 호출 |

⚠️ 오픈소스 현황(2026-10 웹 검색, 코드 미검증): `chongdashu/unreal-mcp`(C++ TCP 55557 + Python), `lilklon/UEBlueprintMCP`(5.7+, TCP 55558, BP/UMG/Material 60+ 명령), `ziggymar/unreal-mcp`(Node/TS, 5.6/5.8), `Natfii/UnrealClaude`(5.7, AnimBP 편집 주장). 공통 패턴은 "C++ 플러그인이 소켓 서버 + 외부 MCP 서버"로 ①과 같다. AnimGraph 상태머신·Transition Rule을 Guid 기반으로 다루는 구현은 확인하지 못했다. **UnrealClaude의 AnimBP 도구는 Phase 3 착수 전 소스 열람 가치가 있다**(채택이 아니라 함정 선행 학습 목적).

### C-2. 결정

**① 채택.** 근거 세 가지.

1. 엔진 내장 `HTTPServer`가 스레드 문제와 로컬 바인드를 기본값으로 해결한다(B-6). 자체 소켓 스레드 + `AsyncTask` 디스패치 코드를 쓰지 않아도 된다.
2. 그래프 편집 로직은 어차피 C++로 새로 써야 하므로(B-7), 외부 프로젝트 포크는 통신 계층만 절약하고 유지 비용을 더한다.
3. Remote Control이 동일 모듈 위에 수십 라우트를 운영하는 선례가 있어(B-6) 수명주기·라우팅 패턴을 그대로 참조할 수 있다.

### C-3. 통신 규약

- 전송: `POST http://127.0.0.1:<port>/v1/<tool>` JSON 본문 / JSON 응답. 포트는 설정값(제안 18765 ❓ 사용자 결정). `[HTTPServer.Listeners]`는 기본 `localhost` 유지.
- 인증: 플러그인 기동 시 랜덤 토큰을 로그·`Saved/AnimMcp/token` 파일에 기록, `RegisterRequestPreprocessor`에서 `X-AnimMcp-Token` 헤더 검사 ❓(로컬 전용이라 선택 사항. Phase 2 결정).
- 요청 공통 필드: `request_id`(멱등 키), `expected_revision`(선택).
- 응답 공통 봉투: `{ "ok": bool, "request_id", "result": {...}, "error": {"code","message","details"}, "diagnostics": [...] }`.
- 동시성: 게임 스레드 단일 큐 → 자연 직렬화. `request_id` 중복은 캐시된 결과 재반환.
- 타임아웃: 클라이언트(Python) 측 60초 기본, `compile`은 180초. 서버는 긴 작업도 동기 처리(에디터 블로킹은 허용 — 에디터가 실행기).
- 종료: `ShutdownModule`에서 `UnbindRoute` 전부 + `StopAllListeners`. 에디터가 요청 중 종료되면 클라이언트는 connection reset을 `EDITOR_GONE`으로 매핑.

### C-4. 스레드 처리

- 핸들러 진입점에서 `ensure(IsInGameThread())` 1회 — 가정이 아니라 **검증**으로 남긴다.
- 모든 UObject 편집은 핸들러 동기 호출. 비동기가 필요한 경우(미래)는 `OnComplete`를 `TSharedPtr`로 보관하고 `FTSTicker`로 완료.
- Python 서버는 단일 워커로 요청을 직렬 전달 (MCP 호출 자체가 순차).

### C-5. 오류 모델

| code | 의미 |
| :--- | :--- |
| `EDITOR_GONE` | 연결 실패 (에디터 미기동·종료) |
| `BAD_REQUEST` | 스키마 위반 |
| `ASSET_NOT_FOUND` / `ASSET_EXISTS` | 경로 해석 실패 / 생성 충돌 |
| `GRAPH_NOT_FOUND` / `NODE_NOT_FOUND` / `PIN_NOT_FOUND` | Guid·이름 해석 실패 |
| `REVISION_MISMATCH` | `expected_revision` 불일치 |
| `CONNECTION_REJECTED` | `CanCreateConnection` 거부 (스키마 응답 메시지 포함) |
| `PROPERTY_NOT_ALLOWED` | 허용 목록 외 프로퍼티 |
| `COMPILE_FAILED` | `NumErrors > 0` (메시지 배열 동반) |
| `SAVE_FAILED` | `SaveLoadedAsset` false |
| `INTERNAL` | 예외·check 직전 가드 |

---

## D. Unreal Editor Plugin 설계 초안

### D-1. 위치·이름

- 경로: `Plugins/AnimGraphMcp/` (프로젝트 내, 재사용 시 폴더째 복사). 이름 ❓ 사용자 결정.
- 모듈 1개: `AnimGraphMcpEditor`, `"Type": "Editor"`, `"LoadingPhase": "Default"`. 런타임 모듈 없음 → 쿠킹·패키징 무영향.

```
Plugins/AnimGraphMcp/
├── AnimGraphMcp.uplugin
├── Source/AnimGraphMcpEditor/
│   ├── AnimGraphMcpEditor.Build.cs
│   ├── Public/   (비움 — 외부 노출 없음)
│   └── Private/
│       ├── AnimGraphMcpEditorModule.cpp      StartupModule: 라우터 획득·라우트 바인드 / Shutdown: 해제
│       ├── Bridge/AnimMcpHttpBridge.{h,cpp}  FHttpServerModule·IHttpRouter 래핑, 토큰 검사, JSON 파싱/직렬화
│       ├── Bridge/AnimMcpDispatcher.{h,cpp}  tool 이름 → 핸들러 테이블, request_id 캐시, 공통 봉투
│       ├── Core/AnimMcpAssetResolver.{h,cpp} 경로 → UAnimBlueprint/USkeleton/UAnimationAsset 로드·검증, AssetRegistry 질의
│       ├── Core/AnimMcpGraphInspector.{h,cpp}  AnimBP → JSON (그래프 계층·노드·핀·연결·상태머신·바인딩·revision)
│       ├── Core/AnimMcpGraphMutator.{h,cpp}    노드 생성/삭제, 핀 연결/해제, 속성 설정(허용 목록), 핀 노출
│       ├── Core/AnimMcpStateMachineEditor.{h,cpp} 상태머신·State·Transition·Rule 그래프 구성
│       ├── Core/AnimMcpCompiler.{h,cpp}      CompileBlueprint + FCompilerResultsLog → diagnostics, SaveLoadedAsset
│       ├── Core/AnimMcpTransaction.{h,cpp}   FScopedTransaction 스코프 + 실패 시 Cancel + 사후 revision 재계산
│       └── Tools/AnimMcpTools_*.cpp          tool별 핸들러 (Status, Inspect, Operations, Compile)
└── Content/ (없음)
mcp/anim_graph_mcp/                            Python MCP 서버 (프로젝트 루트 또는 Tools/ 하위 ❓)
```

### D-2. Build.cs 의존 (전부 B절에서 확인)

```
PublicDependencyModuleNames: Core, CoreUObject, Engine
PrivateDependencyModuleNames:
  UnrealEd            FKismetEditorUtilities · FBlueprintEditorUtils · FScopedTransaction · UEditorAssetSubsystem · 팩토리
  AnimGraph           UAnimGraphNode_* · UAnimState* · UAnimation*Graph/Schema
  AnimGraphRuntime    FAnimNode_* 런타임 구조체 (AnimGraph의 Public 의존)
  BlueprintGraph      UK2Node_VariableGet · UK2Node_CallFunction · UEdGraphSchema_K2
  KismetCompiler      FCompilerResultsLog 의존 체인 (❓ 링크 시 필요 여부 확인)
  HTTPServer          FHttpServerModule · IHttpRouter   (모듈명은 "HTTPServer", 파일은 HttpServer.Build.cs)
  Json, JsonUtilities 요청/응답
  AssetRegistry       애셋 탐색
  Projects            IPluginManager (A-2 플러그인 상태 확인)
```

### D-3. 클래스 책임과 의존

```
HttpBridge ──▶ Dispatcher ──▶ Tools_* ──┬──▶ GraphInspector ──▶ (읽기만)
                                        ├──▶ GraphMutator ─────┐
                                        ├──▶ StateMachineEditor┼─▶ Transaction (스코프 소유)
                                        ├──▶ Compiler ─────────┘
                                        └──▶ AssetResolver (모두가 사용)
```

- **Inspector는 쓰지 않고, Mutator/StateMachineEditor는 Transaction 밖에서 호출되지 않는다.** 이 두 규칙이 Preview/Apply 분리의 코드상 표현이다.
- `preview_graph_operations`는 Mutator의 **검증 단계만** 호출한다(대상 해석 + `CanCreateConnection` + 허용 목록 + 타입 호환). 검증 함수와 적용 함수를 쌍으로 두되 적용은 검증 통과를 전제로 한다.
- 노드 식별: `{"graph": "<GraphGuid>", "node": "<NodeGuid>"}`. 표시 이름은 응답에만 포함, 입력으로 받지 않는다.
- revision: Inspector가 `(GraphGuid, NodeGuid 목록, 각 노드 핀 이름·LinkedTo 쌍, FNode 구조체 `ExportText`)`를 결정적 순서로 해시(SHA1). AnimBP 전체 그래프 트리에 대해 1개. ❓ `ExportText` 비용은 Phase 3에서 측정, 과하면 노드 `Modify` 카운터 대안.

### D-4. 복구 전략 (Transaction ≠ 원자성)

1. 배치 시작 전 Inspector로 `revision_before` 계산, `expected_revision`과 대조.
2. `FScopedTransaction` 열고 작업 순차 적용. 각 작업은 **적용 전 검증을 다시 수행**(Preview 결과 재사용 금지 — 상태가 변했을 수 있다).
3. 중간 실패 → `Cancel()` → 되돌림 여부를 `revision_after == revision_before`로 **확인**. 불일치면 `error.details.rollback_verified=false`로 보고하고 저장하지 않는다.
4. 성공 시 `MarkBlueprintAsStructurallyModified` → (옵션) 컴파일 → 응답에 `revision_after`.
5. 저장은 별도 Tool(`save_animation_blueprint`) 또는 `apply`의 `save: true` 옵션. 기본 false.

---

## E. MCP Tool 및 JSON Schema 초안

Python 측은 `mcp` 공식 SDK(FastMCP)로 각 Tool을 등록하고 입력 스키마를 pydantic으로 검증한 뒤 그대로 HTTP로 전달한다. 로직 없음.

### E-1. `get_editor_status`

```jsonc
// in
{}
// out.result
{
  "engine_version": "5.7.4", "project": "AstralBreak",
  "plugin_version": "0.1.0", "schema_version": "1.0",
  "game_thread": true, "is_pie": false,
  "plugins": { "PythonScriptPlugin": true, "EditorScriptingUtilities": true },
  "open_asset_editors": ["/Game/Animation/Hero/ABP_Hero_Base"]
}
```

### E-2. `get_anim_blueprint_info`

```jsonc
// in
{ "asset_path": "/Game/Animation/Test/ABP_McpTest" }
// out.result
{
  "asset_path": "...", "revision": "sha1:…",
  "parent_class": "/Script/AstralBreak.AstralAnimInstance",
  "parent_anim_blueprint": null, "is_template": false,
  "target_skeleton": "/Game/Characters/UEFN_Mannequin/Meshes/SK_UEFN_Mannequin",
  "preview_mesh": "...",
  "graphs": [ { "graph_guid": "…", "name": "AnimGraph", "class": "AnimationGraph", "parent_graph_guid": null, "owner_node_guid": null } ],
  "variables": [ { "name": "Speed", "type": "float", "source": "native" } ],
  "linked_anim_layers": [], "property_bindings_count": 0,
  "diagnostics": []
}
```

### E-3. `get_anim_graph_structure`

```jsonc
// in
{ "asset_path": "...", "graph_guid": "…(선택, 생략=AnimGraph 루트)", "depth": 2, "include_defaults": false }
// out.result
{
  "schema_version": "1.0", "asset_path": "...", "revision": "sha1:…",
  "graphs": [ { "graph_guid": "…", "name": "AnimGraph", "class": "AnimationGraph", "parent_graph_guid": null, "owner_node_guid": null } ],
  "nodes": [
    { "node_guid": "…", "graph_guid": "…", "class": "AnimGraphNode_SequencePlayer", "title": "Play AS_Hero_Rifle_Idle",
      "pos": [0, 0], "asset": "/Game/.../AS_Hero_Rifle_Idle",
      "properties": { "bLoopAnimation": true, "PlayRate": 1.0 },
      "pins": [ { "name": "Pose", "dir": "out", "type": "struct:PoseLink", "linked": ["…nodeguid:Result"] },
                { "name": "PlayRate", "dir": "in", "type": "real:double", "default": "1.0", "linked": [] } ],
      "bindings": [], "sub_graphs": ["…"] }
  ],
  "connections": [ { "from": { "node": "…", "pin": "Pose" }, "to": { "node": "…", "pin": "Result" } } ],
  "state_machines": [
    { "node_guid": "…", "graph_guid": "…", "name": "Locomotion", "entry_state": "Idle",
      "states": [ { "node_guid": "…", "name": "Idle", "bound_graph_guid": "…", "type": "BlendGraph" } ],
      "transitions": [ { "node_guid": "…", "from": "Idle", "to": "Run", "priority": 1, "crossfade": 0.2, "blend_mode": "Linear",
                         "rule_graph_guid": "…", "rule_summary": "Speed > 10.0", "automatic": false, "bidirectional": false } ] }
  ],
  "diagnostics": [ { "level": "warning", "code": "PIN_UNLINKED", "node": "…", "pin": "Result", "message": "..." } ]
}
```

### E-4. `preview_graph_operations` / `apply_graph_operations`

두 Tool은 **같은 입력**을 받는다. preview는 검증 결과와 예상 변경만 돌려주고 그래프를 건드리지 않는다.

```jsonc
// in
{
  "asset_path": "...", "expected_revision": "sha1:…(선택)", "request_id": "uuid",
  "compile": false, "save": false,
  "operations": [
    { "op": "add_node", "ref": "idle", "graph": "<GraphGuid>", "class": "AnimGraphNode_SequencePlayer",
      "pos": [-400, 0], "asset": "/Game/Animation/Hero/Anims/Locomotions/AS_Hero_Rifle_Idle",
      "properties": { "bLoopAnimation": true } },
    { "op": "connect", "from": { "ref": "idle", "pin": "Pose" }, "to": { "node": "<RootNodeGuid>", "pin": "Result" } },
    { "op": "set_property", "node": "<NodeGuid>", "property": "PlayRate", "value": 1.2 },
    { "op": "expose_pin", "node": "<NodeGuid>", "property": "PlayRate", "visible": true },
    { "op": "disconnect", "pin": { "node": "<NodeGuid>", "pin": "Pose" } },
    { "op": "remove_node", "node": "<NodeGuid>" },
    { "op": "create_state_machine", "ref": "sm", "graph": "<GraphGuid>", "name": "Locomotion", "pos": [0, 0] },
    { "op": "add_state", "ref": "st_idle", "state_machine": { "ref": "sm" }, "name": "Idle", "entry": true },
    { "op": "add_transition", "ref": "tr1", "from": { "ref": "st_idle" }, "to": { "ref": "st_run" },
      "crossfade": 0.2, "priority": 1 },
    { "op": "set_transition_rule", "transition": { "ref": "tr1" },
      "rule": { "kind": "compare", "variable": "Speed", "operator": ">", "constant": 10.0 } }
  ]
}
```

- `ref`는 배치 안에서 앞 작업이 만든 노드를 뒤 작업이 가리키는 임시 이름. 응답에서 `ref → node_guid` 표로 확정된다.
- `rule.kind` MVP: `"bool_variable"`(`{"variable": "bIsFalling", "negate": false}`), `"compare"`(변수 vs 상수, `> >= < <= == !=`), `"and"`(위 둘의 목록). 함수 호출은 Phase 4 후반.
- `set_property.property` 허용 목록(초기): SequencePlayer `bLoopAnimation, PlayRate, StartPosition`; BlendSpacePlayer `bLoop, PlayRate`; Slot `SlotName`; SaveCachedPose `CacheName`; Transition `CrossfadeDuration, PriorityOrder, BlendMode, Bidirectional, bDisabled`; State `bAlwaysResetOnEntry`. 애셋 참조는 `asset` 필드로만(`SetAnimationAsset` 경유).

```jsonc
// out.result (preview)
{ "revision": "sha1:…", "valid": true,
  "planned": [ { "index": 0, "op": "add_node", "ref": "idle", "ok": true },
               { "index": 1, "op": "connect", "ok": false, "error": { "code": "CONNECTION_REJECTED", "message": "Pose → Result: ..." } } ],
  "would_create": 2, "would_remove": 0, "would_modify": 1 }
// out.result (apply)
{ "revision_before": "sha1:…", "revision_after": "sha1:…", "applied": 4,
  "refs": { "idle": "<NodeGuid>", "sm": "<NodeGuid>" },
  "compile": { "ran": false }, "saved": false }
```

### E-5. `compile_animation_blueprint`

```jsonc
// in
{ "asset_path": "...", "save_on_success": false }
// out.result
{ "ok": false, "num_errors": 1, "num_warnings": 2, "revision": "sha1:…",
  "messages": [ { "level": "error", "text": "...", "node_guid": "…", "graph_guid": "…", "pin": null } ],
  "saved": false }
```

### E-6. 그 외 (목록만, Phase 2~4에서 구체화)

`list_animation_assets`(skeleton 필터·클래스 필터·경로 접두), `create_animation_blueprint`(parent_class, skeleton, path, overwrite=false), `create_blendspace`(Phase 4), `save_animation_blueprint`, `get_state_machine_structure`(E-3의 부분집합), `validate_anim_graph`(컴파일 없는 구조 검증 = E-3 diagnostics만), `get_operation_result`(request_id 캐시 조회).

---

## F. 단계별 구현 계획

### Phase 2 — 통신 골격

| # | 작업 | 완료 기준 |
| :---: | :--- | :--- |
| 2-1 | 플러그인 뼈대 + Build.cs + 모듈 시작/종료에서 `GetHttpRouter`·`BindRoute`/`UnbindRoute` | 에디터 기동 로그에 포트·토큰, `curl -X POST /v1/get_editor_status` 200 |
| 2-2 | `IPluginManager`로 Python/EditorScriptingUtilities 활성 상태 확인 → status에 노출 (A-2 ❓ 해소) | 응답 `plugins` 필드 |
| 2-3 | Dispatcher + 공통 봉투 + 오류 코드 + `request_id` 캐시 | 동일 request_id 2회 → 2번째는 캐시 응답 |
| 2-4 | AssetResolver + `get_anim_blueprint_info` (기존 `ABP_Hero_Base` 읽기 전용 조회) | 스켈레톤·부모 클래스·그래프 Guid 목록 반환 |
| 2-5 | Python MCP 서버(FastMCP) — 위 두 Tool 등록, `.mcp.json` 예시 | Claude Code에서 `get_editor_status` 호출 성공 |
| 2-6 | `.claude/settings.json` allow에 플러그인 빌드·MCP 실행 명령 추가 (사용자 승인 후) | |

### Phase 2.5 — 최소 수직 통합 (§14.7 시나리오)

호출 순서(전부 B절 확인 API):

1. `FKismetEditorUtilities::CanCreateBlueprintOfClass(UAstralAnimInstance)` + `IsChildOf(UAnimInstance)` 사전 검증 → 실패면 `BAD_REQUEST` (모달 회피).
2. `UPackage* Pkg = CreatePackage("/Game/Animation/Test/ABP_McpTest")` → `FKismetEditorUtilities::CreateBlueprint(Parent, Pkg, "ABP_McpTest", BPTYPE_Normal, UAnimBlueprint::StaticClass(), UBlueprintGeneratedClass::StaticClass())` → `TargetSkeleton` 3곳 세팅(팩토리 475-494 재현) → `FAssetRegistryModule::AssetCreated`.
3. `FBlueprintEditorUtils::FindBlueprintForGraph`/`FunctionGraphs`에서 `GN_AnimGraph` 그래프 획득 → `GetNodesOfClass<UAnimGraphNode_Root>` 1개.
4. `FGraphNodeCreator<UAnimGraphNode_SequencePlayer>` → `CreateNode()` → `Finalize()` → `SetAnimationAsset(AS_Hero_Rifle_Idle)` → `NodePosX/Y`.
5. `Schema->TryCreateConnection(Seq->FindPin("Pose"), Root->FindPin("Result"))` → false면 `CanCreateConnection` 응답 메시지로 `CONNECTION_REJECTED`.
6. `MarkBlueprintAsStructurallyModified` → `CompileBlueprint(BP, None, &Log)` → `NumErrors == 0`.
7. `UEditorAssetSubsystem::SaveLoadedAsset(BP)`.
8. 패키지 언로드 없이 `get_anim_graph_structure` 재조회 → 노드 2 · 연결 1 · revision 반환. 에디터 재시작 후 동일 조회로 영속 확인.

**완료 기준**: Claude Code → MCP → 에디터 경로로 위 8단계가 1회 명령으로 끝나고, 재시작 후 조회 결과가 같다. 운영 애셋 `ABP_Hero_Base`는 건드리지 않는다.

### Phase 3 — 범용 AnimGraph 편집

| 작업 | 완료 기준 |
| :--- | :--- |
| Inspector 완성 (핀·연결·서브그래프 재귀·바인딩 조회·revision) | `ABP_Hero_Base` 전체 덤프가 오류 없이 나오고 LinkedAnimLayer/바인딩이 보존 표기 |
| Mutator: add/remove/connect/disconnect/set_property(허용 목록)/expose_pin | 각 op 단위 테스트 AnimBP에서 성공·거부 케이스 |
| Preview/Apply + Transaction + Cancel 검증 (D-4) | 중간 실패 배치 후 `revision_after == revision_before` |
| BlendSpacePlayer, Slot, LayeredBlendPerBone, BlendPosesByBool, Save/UseCachedPose 지원 | 각 노드 생성·연결·컴파일 통과 |

### Phase 4 — State Machine

| 작업 | 완료 기준 |
| :--- | :--- |
| `create_state_machine`(Finalize → 자동 서브그래프), `add_state`(PostPlacedNewNode → BoundGraph), Entry 연결(`EntryNode->GetOutputPin()` ↔ State `In`) | 상태 2개·Entry 연결된 상태머신 컴파일 통과 |
| `add_transition`: `FGraphNodeCreator<UAnimStateTransitionNode>` → Finalize(BoundGraph 생성) → `CreateConnections(Prev, Next)` | 양방향·우선순위·크로스페이드 반영 |
| `set_transition_rule` MVP: BoundGraph(`UAnimationTransitionGraph`)에 `UK2Node_VariableGet`(`SetSelfMember`) ± `UK2Node_CallFunction`(`Greater_DoubleDouble` 등, 상수는 `TrySetDefaultValue`) → `GetResultNode()->FindPin("bCanEnterTransition")` 연결 | `Speed > 10`, `bIsFalling`, AND 조합 컴파일 통과·PIE에서 전이 관측 |
| 상태 내부 그래프 편집 = Phase 3 Mutator를 `BoundGraph`에 그대로 적용 (`GetPoseSinkPinInsideState`) | |
| `create_blendspace`(2D, 축 설정 API 조사 포함) | |

### Phase 5 — 실제 캐릭터 적용

Free Locomotion(`BS_Hero_Locomotion1D` + `Speed`), Lock-On Locomotion(8방향 2D BS + `Speed`/`MovementDirection`), Jump(`bIsInAir`/`bIsJumping`/`bIsFalling`/`bIsOnGround`), Attack(Slot + LayeredBlendPerBone). **`ABP_Hero_Base`에 적용하기 전에 복제본에서 전 과정 수행 → diff 검토 → 승인 후 원본.** AnimInstance 변경(락온 플래그 등)은 별도 커밋·별도 승인.

### Phase 6 — 고급·안정화

LinkedAnimLayer 편집, Property Binding 쓰기, Alias/Conduit, Automation Test(기존 `run_automation_tests.py` 재사용), 두 번째 프로젝트에서 플러그인 폴더 복사만으로 Phase 2.5 재현.

---

## G. 기술적 위험과 미확정 사항

### G-1. 위험 평가

| 위험 | 수준 | 근거 | 대응 |
| :--- | :---: | :--- | :--- |
| MinimalAPI 클래스의 비가상·비내보내기 함수 링크 실패 | 중 | `UAnimBlueprintFactory`, `UAnimStateNode` 등 MinimalAPI. 핵심 메서드는 `ANIMGRAPH_API` 명시이나 일부(`UAnimStateNode::GetBoundGraph` 등)는 inline/virtual에 의존 | virtual은 vtable 경유라 안전. 비가상·비export 함수가 필요해지면 동등 로직을 플러그인에 재현. 링크 오류를 Phase 2.5에서 조기 노출 |
| 팩토리/다이얼로그 모달 | 중 | `ConfigureProperties` Slate 다이얼로그, `FactoryCreateNew` 실패 시 `FMessageDialog` | 팩토리 미사용, `CreateBlueprint` 직접 호출 + 사전 검증 |
| 노드 초기화 누락 | 중 | `FGraphNodeCreator` 미Finalize는 checkf 크래시; 서브그래프는 `PostPlacedNewNode`에서만 생긴다 | Creator 패턴 강제, `NewObject`로 직접 만들지 않음 (StateMachineSchema도 템플릿 스폰 뒤 PerformAction으로 PostPlaced 경유) |
| 핀 재구성 | 중 | `SetPinVisibility`가 `ReconstructNode` 호출 → 기존 링크는 `ReallocatePinsDuringReconstruction`가 복원하지만 핀 포인터는 무효화 | op 실행 후 핀을 이름으로 재탐색. 포인터를 op 간에 보관하지 않음 |
| Transition Rule 그래프 복잡성 | 중 | K2 노드 조합·타입 승격·Pure 함수 제약 | MVP를 변수·비교·AND로 한정, 복잡 조건은 C++ AnimInstance에 계산 위임 (프로젝트 패턴과 일치) |
| 스레드 안전 오해 | 저 | `BlueprintThreadSafe` 메타만으로 데이터 안전 보장 안 됨 | 규칙은 AnimInstance 자기 프로퍼티만 읽도록 제한. 함수 호출 지원 시 `UAnimInstance`의 ThreadSafe 함수(B-5) 화이트리스트 |
| 트랜잭션 취소가 완전 복구를 보장하지 않을 가능성 | 중 | `Cancel()`→`CancelTransaction` 의미 미실측 | D-4의 revision 대조로 **복구를 검증**. 실패 시 저장 금지 + 보고 |
| HTTP 핸들러가 에디터 프레임 블로킹 | 저 | 게임 스레드 동기 처리 | 수용(에디터는 실행기). 컴파일 등은 클라이언트 타임아웃 넉넉히 |
| 포트 충돌·좀비 리스너 | 저 | `GetHttpRouter`는 바인드 실패 시 경고만(cpp:160-179) | `bFailOnBindFailure=true`로 호출, 실패를 status에 노출 |
| 엔진 업그레이드 | 중 | 5.6에서 `BlendProfile_DEPRECATED` 등 변경 이력 존재 | 엔진 API 호출을 `Core/` 5개 클래스에 격리, 버전 매크로 최소. 본 문서의 소스 경로가 재검증 체크리스트 |
| 기존 AnimBP 호환 | 중 | `ABP_Hero_Base` 구조 미조회(바이너리) | Phase 3 Inspector로 먼저 덤프하고 바인딩·레이어 보존 확인 후 편집 |
| 운영 애셋 손상 | 높 | | 테스트 경로 분리, 복제본 선적용, `save` 기본 false, 삭제·대규모 변경은 Tool 수준에서 `confirm: true` 필수 |
| Python 플러그인 활성 경로 불명 | 저 | A-2 | Phase 2-2에서 확인. 새 플러그인은 Python에 의존하지 않으므로 기능 영향 없음 |

### G-2. 추가 검증 필요 (❓ 목록)

1. 핀 실명: Root `Result`, TransitionResult `bCanEnterTransition`, State `In/Out` — `FindPin` 실측.
2. `FScopedTransaction::Cancel()`의 복구 범위.
3. `UBlendSpace` 축·샘플 설정 API (Phase 4).
4. `FAnimNode_Slot::SlotName`, `FAnimNode_LayeredBoneBlend` 본 필터 멤버 이름.
5. 번들 Python 버전 (MCP 서버는 시스템 Python 사용 예정이므로 영향 적음).
6. `KismetCompiler` 모듈 링크 필요 여부.
7. revision 해시 비용.
8. 오픈소스 `Natfii/UnrealClaude` AnimBP 도구의 구현 방식 (참고 목적).

### G-3. 구현 시작 전 결정 사항 (사용자)

| 결정 | 제안 |
| :--- | :--- |
| 플러그인 이름·위치 | `Plugins/AnimGraphMcp`, 모듈 `AnimGraphMcpEditor` |
| MCP 서버 위치 | `Tools/mcp/anim_graph_mcp/` (기존 Tools 관례 유지) |
| 포트·토큰 | 18765, 토큰 검사 켬 |
| 테스트 AnimBP 경로 | `/Game/Animation/Test/ABP_McpTest` (Git 추적, Phase 2.5 산출물) |
| Transition Rule MVP 노드 | `UK2Node_CallFunction` + 구체 함수 (PromotableOperator 미사용) |
| Phase 5의 AnimInstance 변경 | 락온 플래그 추가 여부. 대안: `MovementDirection` 기반 2D BS는 플래그 없이도 동작(시뮬 프록시 포함) — 락온 상태가 로컬 전용(TargetingComponent 비복제)인 현 구조와도 맞다 |
| Phase 2 착수 승인 | 본 문서 검토 후 |

---

## 부록 — 확인에 사용한 파일

**프로젝트**: `AstralBreak.uproject`, `Source/AstralBreak.Build.cs`, `Source/AstralBreakEditor.Target.cs`, `Config/DefaultEngine.ini`, `Config/DefaultGame.ini`, `Source/AstralBreak/Animation/AstralAnimInstance.{h,cpp}`, `Tools/ue_exec.py`, `Tools/lib/ab_blueprint.py`, `.claude/settings.json`, `Content/Animation/**`, `Content/Characters/**`

**엔진** (`Engine/Source/`): `Editor/UnrealEd/Classes/Factories/{AnimBlueprintFactory,BlendSpaceFactoryNew}.h`, `Editor/UnrealEd/Private/Factories/AnimBlueprintFactory.cpp`, `Editor/UnrealEd/Private/Kismet2/Kismet2.cpp`, `Editor/UnrealEd/Public/Kismet2/{KismetEditorUtilities,BlueprintEditorUtils,CompilerResultsLog}.h`, `Editor/UnrealEd/Public/{ScopedTransaction,FileHelpers}.h`, `Editor/UnrealEd/Private/ScopedTransaction.cpp`, `Editor/UnrealEd/Public/Subsystems/EditorAssetSubsystem.h`, `Editor/UnrealEd/Classes/Editor/EditorEngine.h`, `Editor/AnimGraph/AnimGraph.Build.cs`, `Editor/AnimGraph/Public/{AnimationGraph,AnimationGraphSchema,AnimGraphNode_Base,AnimGraphNode_SequencePlayer,AnimGraphNode_BlendSpacePlayer,AnimGraphNode_Slot,AnimGraphNode_LayeredBoneBlend,AnimGraphNode_BlendListByBool,AnimGraphNode_BlendListByEnum,AnimGraphNode_SaveCachedPose,AnimGraphNode_UseCachedPose,AnimGraphNode_Root,AnimGraphNode_AssetPlayerBase,AnimGraphNode_StateMachine,AnimGraphNode_StateMachineBase,AnimGraphNode_TransitionResult,AnimationStateMachineGraph,AnimationStateMachineSchema,AnimStateNode,AnimStateNodeBase,AnimStateEntryNode,AnimStateTransitionNode,AnimationTransitionGraph,AnimationStateGraph}.h`, `Editor/AnimGraph/Private/{AnimGraphNode_Base,AnimGraphNode_StateMachineBase,AnimStateNode,AnimStateTransitionNode,AnimationStateMachineSchema,AnimationGraphSchema,AnimationStateGraphSchema,AnimationTransitionSchema,AnimationStateGraph,AnimationTransitionGraph}.cpp`, `Editor/BlueprintGraph/Classes/{EdGraphSchema_K2,K2Node_Variable,K2Node_VariableGet,K2Node_CallFunction,K2Node_PromotableOperator}.h`, `Editor/BlueprintEditorLibrary/Public/BlueprintEditorLibrary.h`, `Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h`, `Runtime/Engine/Classes/EdGraph/{EdGraph,EdGraphNode,EdGraphSchema}.h`, `Runtime/Engine/Classes/Animation/{AnimBlueprint,AnimInstance,AnimNode_SequencePlayer,AnimNode_Root,AnimNode_TransitionResult}.h`, `Runtime/Engine/Classes/Engine/{Blueprint,MemberReference}.h`, `Runtime/Engine/Classes/Kismet/KismetMathLibrary.h`, `Runtime/Core/Public/Async/Async.h`, `Runtime/Online/HTTPServer/Public/*.h`, `Runtime/Online/HTTPServer/Private/{HttpServerModule,HttpListener,HttpServerConfig}.{h,cpp}`, `Runtime/Online/HTTPServer/HttpServer.Build.cs`

**엔진 플러그인** (`Engine/Plugins/`): `Experimental/PythonScriptPlugin/PythonScriptPlugin.uplugin`, `.../Private/{PyGenUtil,PyWrapperObject}.cpp`, `.../Private/PythonScriptRemoteExecution.h`, `Editor/EditorScriptingUtilities/EditorScriptingUtilities.uplugin`, `VirtualProduction/RemoteControl/Source/WebRemoteControl/Private/WebRemoteControl.h`
