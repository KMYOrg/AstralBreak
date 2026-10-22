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
| 없는 것 | 락온 상태 플래그, 전투 스타일 플래그 | **결정(2026-10-10): strafe는 락온이 아니라 추후 "사격 후 일정 시간" 모드로 도입한다. Phase 5 범위에서 Lock-On Locomotion은 보류.** 관련 선행 작업은 §F Phase 5 보류 표 |
| 회전 모드 | `bOrientRotationToMovement = true` 고정 (`AstralCharacter.cpp:38`). 락온은 카메라 Yaw 입력과 입력 회전 억제만 바꾼다 (`AstralHeroComponent.cpp:401,443`, `AstralHeroMovementComponent.cpp:178`) | ✅ 현재는 락온 중에도 몸이 이동 방향을 향함 → strafe 자세가 어느 머신에서도 나오지 않는다 |
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
- `rule`은 선언적 AST (§G-3 "Transition Rule 설계"). 종류: `var`(`{"kind":"var","name":"bIsFalling"}`), `not`, `and`/`or`(`items` 배열), `compare`(`{"kind":"compare","left":{"kind":"var","name":"Speed"},"op":">","right":{"kind":"literal","value":10.0}}`), `call`(화이트리스트 함수), `literal`, `automatic`(그래프 없이 전이 프로퍼티만). 생성기는 BoundGraph를 Result 노드만 남기고 비운 뒤 AST에서 재생성하고, AST 원문을 그래프 안 주석 노드에 기록한다.
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
| `set_transition_rule`: 규칙 AST → 테이블 기반 생성기. BoundGraph(`UAnimationTransitionGraph`)를 Result 노드만 남기고 비움 → `UK2Node_VariableGet`(`SetSelfMember`), `UK2Node_CallFunction`(표에서 고른 `UKismetMathLibrary` 함수, 상수는 `TrySetDefaultValue`), `BooleanAND/OR/NOT` 조립 → `GetResultNode()->FindPin("bCanEnterTransition")` 연결 → AST JSON을 `UEdGraphNode_Comment`에 기록. `automatic`은 전이 노드 프로퍼티만 설정 | `bIsFalling`, `Speed > 10`, AND/OR/NOT 조합, 자동 규칙 컴파일 통과·PIE에서 전이 관측. 같은 AST 2회 적용 → revision 동일(멱등). Inspector `rule_source`가 주석 노드에서 복원됨. ❓ float 변수 핀 → double 함수 핀 연결 허용 여부를 첫 항목으로 실측, 거부되면 표에 변환 노드 삽입 규칙 추가 |
| 상태 내부 그래프 편집 = Phase 3 Mutator를 `BoundGraph`에 그대로 적용 (`GetPoseSinkPinInsideState`) | |
| `create_blendspace`(2D, 축 설정 API 조사 포함) | |

### Phase 5 — 실제 캐릭터 적용

Free Locomotion(`BS_Hero_Locomotion1D` + `Speed`), Jump(`bIsInAir`/`bIsJumping`/`bIsFalling`/`bIsOnGround`), Attack(Slot + LayeredBlendPerBone). **`ABP_Hero_Base`에 적용하기 전에 복제본에서 전 과정 수행 → diff 검토 → 승인 후 원본.**

**보류 — Strafe Locomotion (2026-10-10 결정).** strafe는 락온 상태가 아니라 **추후 "사격 후 일정 시간 유지되는 strafe 모드"**로 도입한다. Phase 5에서는 다루지 않는다. 그때 필요한 선행 게임플레이 작업은 아래와 같고, 조사 결과만 남긴다.

| # | 작업 | 근거 |
| :---: | :--- | :--- |
| S-A | strafe 모드 중 회전 모드 전환: `bOrientRotationToMovement` 해제 + 조준 방향 Yaw 유지. 서버·소유 클라가 같은 규칙으로 계산해야 시뮬 프록시에 이동 복제로 전달된다 | 현재 `AstralCharacter.cpp:38` 고정 → strafe 자세가 어느 머신에서도 나오지 않는다 |
| S-B | strafe 모드 상태를 전 머신에 전달. 후보: 서버가 사격 GA 실행 시 ASC에 `State.Strafe` 태그를 지속시간 GE로 부여 → ASC Mixed 모드로 전 머신 복제 → `UAstralAnimInstance`에 `bIsStrafing` 프로퍼티 추가 + `GameplayTagPropertyMap` 매핑 | `AstralPlayerState.cpp:21`, `AstralAnimInstance.cpp:55`. 사격이 서버 권위 GA라 별도 RPC 없이 태그 경로만으로 충분할 가능성이 높다 ⚠️ |
| S-C | 8방향 2D BlendSpace(`Speed`/`MovementDirection`) + 1D/2D 선택은 `bIsStrafing` | S-A가 끝나면 `MovementDirection`은 모든 머신에서 자동으로 strafe 각도를 낸다 |

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
| Transition Rule 방식 | **결정됨(2026-10-10): 선언적 AST + 테이블 기반 생성기 + 그래프 전체 재생성 + 원본 보존.** 아래 "Transition Rule 설계" |
| Strafe Locomotion | **보류(2026-10-10)**: 락온이 아니라 추후 "사격 후 일정 시간" 모드. §F Phase 5 보류 표 S-A/B/C |

**Transition Rule 설계 (범용성·유지보수 기준)**

평가 경로: 런타임은 Result 노드의 `bCanEnterTransition`을 노드 노출 입력으로 평가한다 (`Runtime/Engine/Private/Animation/AnimNode_StateMachine.cpp:862 GetEvaluateGraphExposedInputs().Execute`). 규칙 그래프는 다른 애님 노드 핀과 같은 방식으로 컴파일되므로, bool 변수 직결 규칙은 일반 핀과 같은 최적화 경로를 타고 비교·함수 노드가 끼면 생성된 BP 함수 호출이 된다 ⚠️(최적화 세부는 일반 지식).

| 요소 | 내용 | 얻는 것 |
| :--- | :--- | :--- |
| 선언적 AST | `var` · `not` · `and` · `or` · `compare` · `call` · `literal` · `automatic` | 프로젝트 비의존. 변수 이름만 바꾸면 어느 UE5 프로젝트에서도 동작 |
| 테이블 기반 생성기 | (연산자, 피연산자 타입) → `UKismetMathLibrary` 함수명 표. 타입은 AnimBP 생성 클래스의 `FProperty`에서 읽어 결정 (`Greater_DoubleDouble`, `EqualEqual_BoolBool`, `BooleanAND` 등 전부 `BlueprintPure`) | 엔진 변경 시 표 한 곳만 수정. 핀 이름·타입이 함수 시그니처로 고정 → 조립이 결정적. `UK2Node_PromotableOperator`는 연결 순서에 따라 타입이 정해져 비결정적이므로 쓰지 않는다 |
| 그래프 전체 재생성 | `set_transition_rule`은 BoundGraph를 Result 노드만 남기고 비운 뒤 AST에서 다시 그린다 | 멱등. diff·패치 로직 없음. 같은 입력 → 같은 그래프 → 같은 revision |
| 원본 보존 | AST JSON을 BoundGraph 안 `UEdGraphNode_Comment`(`Editor/UnrealEd/Public/EdGraphNode_Comment.h` ✅)에 기록 | Inspector가 K2 노드를 역컴파일하지 않고 `rule_source`를 복원. 에디터에서 사람이 봐도 의도가 보임. 도구 소유 그래프 표식 (사람이 손으로 고친 규칙은 주석 노드가 없거나 해시 불일치 → 덮어쓰기 전 경고) |
| 함수 호출 화이트리스트 | `call`은 `BlueprintPure` ∧ `BlueprintThreadSafe` 메타 ∧ 소유 클래스가 {해당 AnimInstance 계열, `UAnimInstance`, `UKismetMathLibrary`}인 함수만 | 스레드 안전성을 메타데이터 신뢰가 아니라 플러그인 검사로 |
| 프로젝트 정책 (도구 제약과 분리) | AstralBreak는 복잡 조건을 `UAstralAnimInstance`의 스냅샷 패턴(C++ `NativeThreadSafeUpdateAnimation`)에서 bool로 계산하고 규칙은 `var` 하나를 기본으로 한다 | C++ 테스트 가능, fast path 유리. `compare`/`and`는 C++ 변경이 과한 경우와 타 프로젝트용 |

조립 방식 후보 비교(참고): ① bool 변수 참조 · ② 비교(CallFunction+구체 함수) · ③ 비교(PromotableOperator) · ④ C++ 사전 계산 참조 · ⑤ 자동 규칙(`bAutomaticRuleBasedOnSequencePlayerInState`) · ⑥ ThreadSafe 함수 호출 · ⑦ AND/OR 조합 · ⑧ 범용 표현식 컴파일러. 채택 설계는 ①②④⑤⑥⑦을 AST 종류로 흡수하고 ③·⑧은 제외한다.
| Phase 2 착수 승인 | 본 문서 검토 후 |

---

## Phase 2 결과 (2026-10-10, 브랜치 `feat/ai_auto_ABP`)

§F Phase 2 의 2-1 ~ 2-5 완료. 2-6(settings.json 허용 목록)은 사용자 승인 대기.

| 산출물 | 위치 |
| :--- | :--- |
| 에디터 플러그인 | `Plugins/AnimGraphMcp/` — 모듈 `AnimGraphMcpEditor`(Editor, Default). uproject 에 등록 |
| C++ 구성 | `Bridge/AnimMcpTypes`(오류 코드·봉투·파라미터 헬퍼) · `Bridge/AnimMcpDispatcher`(tool 테이블·request_id 캐시 256) · `Bridge/AnimMcpHttpBridge`(HTTPServer 라우트 `POST /v1/<tool>`, 토큰 전처리기, 상태 조회만 면제) · `Core/AnimMcpAssetResolver` · `Core/AnimMcpGraphInspector`(그래프 트리·변수·revision) · `Tools/AnimMcpTools_{Status,Inspect}` |
| 설정 | `DefaultEngine.ini [AnimGraphMcp] Port/bRequireToken/bAutoStart`, 커맨드라인 `-AnimGraphMcpPort=`, 콘솔 `AnimGraphMcp.Start/Stop/Status` |
| Python | `Tools/mcp/anim_graph_mcp/{bridge,server}.py`(mcp 2.x `MCPServer`), `Tools/mcp/{smoke_test,mcp_client_test,wait_for_bridge}.py`, venv `Tools/mcp/.venv`(gitignore) |
| Claude Code 등록 | 프로젝트 루트 `.mcp.json` → 서버 `anim-graph-mcp` |

**검증 (Development 에디터, ABP_Hero_Base 읽기 전용)**

- `get_editor_status` 200 · 토큰 없는 조회 401 · 같은 request_id 재전송 봉투 동일 · 없는 애셋 404 `ASSET_NOT_FOUND` → `smoke_test.py` PASS
- stdio MCP 클라이언트로 initialize → list_tools(2) → 두 Tool 호출 → `mcp_client_test.py` PASS
- 핸들러가 게임 스레드에서 실행됨 (`game_thread: true`, `ensure` 미발화). 에디터 기동 중 리스너는 먼저 열리고 응답은 로딩 완료 후 — 클라이언트 타임아웃으로 흡수
- Development · DebugGame 양쪽 빌드 성공 (MSVC 14.38)

**조사 결론 갱신**

- A-2 ❓ 해소: `PythonScriptPlugin`·`EditorScriptingUtilities` 모두 `enabled: true` 로 보고됨. uproject 에 없어도 활성 — 경로는 미추적이지만 새 플러그인은 이에 의존하지 않는다.
- `ABP_Hero_Base` 의 TargetSkeleton 은 `/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F` (UEFN 마네킹이 아님). Phase 2.5 테스트 AnimBP 는 이 스켈레톤으로 만든다.
- 구조: 루트 `AnimGraph` 노드 4 → 상태머신 `Locomotions`(노드 24) → 상태 `Idle`·`Move` 외 전이 그래프 다수 (총 22 그래프). Phase 3 Inspector 의 1차 덤프 대상.

**편차·메모**

- `mcp` 패키지는 2.3.0 — 1.x 의 `FastMCP` 가 `mcp.server.mcpserver.MCPServer` 로 바뀜. `requirements.txt` 는 `mcp>=2,<3`.
- Git Bash 에서 `/Game/...` 인자는 MSYS 경로 변환에 걸린다 → 스크립트 호출 시 `MSYS_NO_PATHCONV=1`. MCP 경로(JSON 본문)는 영향 없음.
- revision 해시는 아직 FAnimNode 프로퍼티 값을 포함하지 않는다 (§D-3 ❓ 그대로, Phase 3).
- 토큰 파일 경로를 절대 경로로 보고하도록 수정 — DebugGame 에 반영, Development 는 에디터 종료 후 재빌드 필요.

**Phase 2.5 착수 조건**: 본 결과 검토. 테스트 AnimBP 경로 `/Game/Animation/Test/ABP_McpTest`, 스켈레톤 `SKEL_UE5_F`, 시퀀스 `AS_Hero_Rifle_Idle`.

---

## Phase 2.5 결과 (2026-10-14, 브랜치 `feat/ai_auto_ABP`)

§14.7 시나리오 9단계 전부 통과 (`Tools/mcp/phase25_test.py` PASS). 운영 애셋 무변경.

| 산출물 | 위치 |
| :--- | :--- |
| 생성 | `Core/AnimMcpBlueprintFactory` — 팩토리 미사용(모달 회피), `FKismetEditorUtilities::CreateBlueprint` + 스켈레톤 3곳 세팅 재현. overwrite 시 `DeleteAsset` 후 메모리에 남은 객체는 임시 패키지로 이동 |
| 쓰기 기계 | `Core/AnimMcpGraphMutator` — Guid/핀 해석, 노드 클래스 해석(UAnimGraphNode_Base 파생만), `FGraphNodeCreator` 경로 생성, `SetAnimationAsset`, `CanCreateConnection` 검증 후 `TryCreateConnection` |
| 배치 | `Core/AnimMcpOperations` — `add_node`·`connect` AST, ref 표, 전체 사전 검증, `FScopedTransaction`, **보상 롤백**(만든 노드 DestroyNode·링크 스냅샷 복원) + `Cancel` + revision 대조 |
| 컴파일·저장 | `Core/AnimMcpCompiler` — `FCompilerResultsLog` 토큰 → node_guid 매핑, `UEditorAssetSubsystem::SaveLoadedAsset(…, false)` |
| Inspector 확장 | `DescribeNode`/`DescribePin`/`BuildGraphStructure`(depth), `FindGraphByGuid`/`FindNodeByGuid` |
| Tool 7개 추가 | `get_anim_graph_structure` · `list_animation_assets` · `create_animation_blueprint` · `save_animation_blueprint` · `preview_graph_operations` · `apply_graph_operations` · `compile_animation_blueprint` (총 9) |
| 테스트 애셋 | `/Game/Animation/Test/ABP_McpTest` (SequencePlayer `AS_IdleRifleAiming_02` → Output Pose) |

**검증**: 스켈레톤 필터 애셋 22건 · 생성(덮어쓰기 포함) · 루트 그래프 노드 `AnimGraphNode_Root` 핀 `Result` 확인 · preview valid & 그래프 불변 · apply 2 op + 컴파일 0/0 + 저장 · 재조회 연결 1건·revision 일치 · 실패 배치(없는 핀) `PIN_NOT_FOUND`, `rollback_verified=true`, 이후 revision 불변 · 중복 ref 거부. **에디터 재시작 후 재조회**: 노드 Guid·연결·애셋 참조 동일, `BS_UpToDate` (영속 확인). Development·DebugGame 빌드 성공.

**해결한 결함 2건**
- 실패 응답 조립 시 실패 op 의 `error.details` 객체를 바깥 `details` 로 재사용하고 그 안에 `applied` 를 넣어 **JSON 순환 참조** → 직렬화 무한 재귀로 에디터 크래시(종료 코드 3) 2회. 바깥 details 를 새 객체로 만들고 원인은 `cause` 아래에 둠. 교훈: 같은 `FJsonObject` 를 두 컨테이너에 넣을 때 트리인지 확인.
- 롤백을 `GEditor->UndoTransaction` 에 맡기던 설계를 보상 방식으로 교체. 크래시 원인은 아니었으나 결과가 에디터 Undo 버퍼 상태에 의존하지 않게 됨 (§D-4 "Undo ≠ 원자성" 원칙 구현).
- overwrite 시 `DeleteAsset` 뒤 같은 이름의 UBlueprint 가 메모리에 남아 `CreateBlueprint` 의 check 에 걸리는 경우 발생(재현 1회). 임시 패키지로 Rename + MarkAsGarbage 로 이름을 비우는 폴백 추가.

**조사 결론 갱신 (❓ 해소)**: Root 입력 핀 이름 `Result`, SequencePlayer 출력 핀 `Pose` 실측 확인. `FScopedTransaction::Cancel` 은 기록만 버린다(소스 확인) — 상태 복구는 보상 코드가 담당.

**Phase 3 착수 조건**: 본 결과 검토. 범위는 §F Phase 3 (Inspector 바인딩·revision 에 노드 프로퍼티 포함, remove_node/disconnect/set_property(허용 목록)/expose_pin, BlendSpacePlayer·Slot·LayeredBlend·BlendListByBool·CachedPose).

---

## Phase 3 결과 (2026-10-15, 브랜치 `feat/ai_auto_ABP`)

핸드오프 §14 작업 전부 구현. `Tools/mcp/phase3_test.py` 7개 절 **PASS** (거부 10종 · 롤백 검증 · revision 규칙 · 재시작 후 재조회). 운영 애셋 `ABP_Hero_Base` 는 읽기만. Development · DebugGame 빌드 성공, 경고 0.

**사용자 확정 결정 (구현 전, 2026-10-15)**
- `remove_node` 롤백 = **분리 보관**: 적용 시 `UEdGraph::RemoveNode(Node, bBreakAllLinks=true)` 로 Nodes 배열에서만 빼고 객체는 유지(`EdGraph.cpp:260` — RemoveNode 는 파괴하지 않는다). 실패 시 `AddNode` 로 복귀 + 링크 복원. 배치 성공 확정 시 트랜잭션 안에서 `DestroyNode()` 로 서브그래프까지 정리(StateMachine 파생은 `DestroyNode` 가 `RemoveGraph`).
- `set_property` 허용 목록 = **확장 목록** (`Core/AnimMcpPropertyRules.cpp` 표). LayerSetup(본 필터)은 Phase 5 보류.

| 산출물 | 위치 |
| :--- | :--- |
| 허용 목록 | `Core/AnimMcpPropertyRules.{h,cpp}` (신규) — 클래스 이름 상속 매칭, 스코프 Node/FNode/NodeRef, 읽기 전용 플래그, JSON↔ImportText 변환, 값→JSON |
| Inspector | 노드 `properties{}`(허용 목록 값) · `optional_pins[{property, shown, can_toggle, bound}]` · `has_binding`. revision 에 EditAnywhere 프로퍼티 + FAnimNode 멤버 포함 (PoseLink·Transient·FText 제외, 노출 핀은 (이름,bShowPin)) |
| Mutator | `Disconnect/DisconnectAll` · `DetachNode/ReattachNode/FinalizeRemoval` · `SetPropertyFromJson/Text`(+노출 핀 기본값 동기화) · `SetAsset/RestoreAsset` · `SetPinVisible` · `SetCachedPoseSource` · `SetBlendListEnum` · `AddBlendPose/RemoveLastBlendPose` |
| Operations | op 8종: `add_node`(+`enum`·`properties`) · `connect` · `disconnect` · `remove_node` · `set_property` · `set_asset` · `expose_pin` · `add_blend_pose`. 되돌리기 저널(op 별 클로저, 역순 실행). 핀은 (노드 포인터, 핀 이름) 으로 기억 — ReconstructNode 뒤에도 유효 |
| 지원 노드 | SequencePlayer · BlendSpacePlayer · Slot · LayeredBoneBlend · BlendListByBool · BlendListByEnum · Save/UseCachedPose · StateMachine(생성만) — 전부 생성·연결·컴파일 0 에러 |
| 테스트 | `Tools/mcp/phase3_test.py` (+`--recheck` 재시작 비교, 상태 파일 `phase3_state.json`) |

**검증 수치**: `ABP_Hero_Base` 전체 덤프 그래프 21 · 노드 69 · 연결 50 · 바인딩 0 · Linked Layer 0. **revision 계산(프로퍼티 포함) 315ms** — info 와 structure 가 같은 값, 2회 계산 동일(결정적). 속성만 바꾼 변경이 revision 을 바꾸고 같은 값 재적용은 유지. 9개 op 가 섞인 배치의 index 9 실패 → `rollback_verified=true`, 분리 보관 노드 복귀·프로퍼티·연결 수 복원. 같은 배치 2회 → `REVISION_MISMATCH`.

**실측으로 바로잡은 것 3건**
- **포즈 출력 핀은 단일 연결** — `UAnimationGraphSchema::CanCreateConnection` 이 출력 쪽에도 BREAK_OTHERS 를 돌려 두 번째 연결이 첫 연결을 끊는다. 공유는 Save/UseCachedPose 가 정석. 테스트 시나리오를 그에 맞게 고쳤다 (도구 결함 아님).
- **노출 핀의 기본값이 진실** — 핀이 보이는 동안 컴파일은 핀 → 구조체로 복사하고, 핀을 숨길 때도 핀 값이 구조체로 되돌아간다 (`AnimBlueprintNodeOptionalPinManager.cpp:108-121`). 구조체만 바꾸면 컴파일에서 덮어쓰인다. `set_property` 는 연결되지 않은 노출 핀의 기본값도 같은 값으로 맞춘다 (`PropertyValueToString_Direct` → `TrySetDefaultValue`).
- **블렌드 포즈 제거 시 고아 핀** — BlendTime 0.1 / BlendWeights 1.0 처럼 비기본값 핀은 재구성 때 고아로 남아 컴파일 경고를 낸다. 엔진의 `RemovePinFromBlendList` 와 같이 제거 인덱스 핀에 `SetSavePinIfOrphaned(false)` 를 먹인 뒤 재구성.

**접근 제한 우회 (MinimalAPI · protected)**: `UAnimGraphNode_BlendListByEnum::BoundEnum/VisibleEnumEntries` 는 protected → `GetEnum()`/`ReloadEnum()`(공개 가상) 과 `FindPropertyByName("VisibleEnumEntries")` 리플렉션. `ExposeEnumElementAsPin` 은 비내보내기 → 같은 순서(`VisibleEnumEntries.Add` · `Node.AddPose()` · `ReconstructNode`) 재현. `FAnimNode_BlendListBase::BlendPose` 는 protected → 길이는 `GetBlendTimes().Num()`. `FPoseLinkBase::StaticStruct()` 는 API 매크로가 없어 구조체 상속 사슬 이름 비교로 판정.

**운용 메모**: Python 원격 실행(`quit_editor.py`)이 에디터를 못 찾는 경우가 있었다(브리지는 정상). 테스트 전용 에디터는 `taskkill //F` 로 내렸다 — Phase 6 안정화에서 `quit_editor` Tool 추가를 검토.

**Phase 4 착수 조건**: 본 결과 검토. 범위는 §F Phase 4 (State Machine · State · Transition · `set_transition_rule` AST). 첫 실측 항목은 float 변수 핀 → double 함수 핀 연결 허용 여부.

---

## Phase 4 결과 (2026-10-15, 브랜치 `feat/ai_auto_ABP`)

§F Phase 4 전부 구현 (BlendSpace 생성 제외 — Phase 5 로). `Tools/mcp/phase4_test.py` 7개 절 **PASS** (운영 애셋 뷰 · 상태머신 구성 · 뷰 · 멱등/교체/call · 거부 9종 · 롤백 · 재시작 재조회) + `phase3_test.py` 회귀 PASS. Development · DebugGame 빌드 성공, 경고 0.

**사용자 확정 결정 (구현 전, 2026-10-15)**: 규칙 입력 = **JSON 트리 AST** · `call` = **§9 화이트리스트**(BlueprintPure ∧ `HasFunctionBlueprintThreadSafeMetaData` ∧ 소유 클래스 ∈ {AnimInstance 사슬, UKismetMathLibrary}) · 상태머신 조회 = **structure 응답 확장** `state_machines[]` (새 Tool 없음 → 재시작 불필요).

**❓ 해소 — float 변수 핀 → double 함수 핀**: 소스에서 바로 확인. `UEdGraphSchema_K2::ArePinTypesCompatible` (EdGraphSchema_K2.cpp:4533-4537) 는 PC_Real 이면 float/double 무관하게 항상 호환이고 바이트코드에 암시 변환을 넣는다. 실측: `Speed`(float) → `Greater_DoubleDouble.A` 연결·컴파일 0 에러. 변환 노드 규칙 불필요.

| 산출물 | 위치 |
| :--- | :--- |
| 규칙 생성기 | `Core/AnimMcpTransitionRule.{h,cpp}` (신규) — `Validate`(타입·화이트리스트·정규화 JSON) · `Build`(AST → UK2Node_VariableGet / UK2Node_CallFunction, (op×타입) 표, 깊이별 배치) · `ReadSource`/`HashRuleGraph`(주석 노드에서 원문 복원 + 사람 편집 감지) |
| Mutator | `AddState`(Creator → BoundGraph 자동 → 이름 검증기 → `OnRenameNode`) · `AddTransition`(Creator → `CreateConnections`) · `SetEntryState` · `CollectLinkedTransitions` · **`BreakAllLinksQuietly`/`DestroyNodeQuietly`** |
| Operations | op 4종 `add_state` · `add_transition`(+`properties`·`rule` 인라인) · `set_entry_state` · `set_transition_rule`. `remove_node` 가 상태를 지우면 전이도 연쇄 분리·삭제 |
| Inspector | `state_machines[{graph_guid, node_guid, entry_state, states[{name, kind, bound_graph_guid, in/out transitions}], transitions[{from, to, crossfade, priority, blend_mode, automatic, rule_graph_guid, rule_generated, rule_source, rule_modified, rule_node_count}]}]`, schema_version 1.1 |
| 테스트 | `Tools/mcp/phase4_test.py` (+`--recheck`), 디버그 덤프 `Tools/mcp/debug_dump_rules.py` |

**검증 수치**: 운영 애셋 `ABP_Hero_Base` 상태머신 1(Locomotions) · 상태 11(Alias 2 포함) · 전이 12, 전부 `rule_generated=false`(도구 미개입 표기). 테스트: 상태 3 · Entry · 전이 4 · 규칙 4종(var · compare(float>literal) · and/or/not 9노드 · automatic) 컴파일 0 에러. 같은 AST 재적용 `unchanged=true` 로 revision 동일(멱등). `call` FMax 로 교체 시 이전 노드 2 + 주석 1 분리. 7-op 배치(규칙 교체·Entry 변경·상태 추가·전이 추가·상태 삭제 연쇄·노드 추가) index 6 실패 → `rollback_verified=true`, 상태 3/전이 4/Entry/규칙 원문 전부 복원. Fall 삭제 → 전이 2개 연쇄 삭제 후 컴파일 0 에러.

**실측으로 바로잡은 것 2건**
- **전이 노드의 자살 통지** — `UAnimStateTransitionNode::PinConnectionListChanged` 는 자기 핀 링크가 0 이 되는 통지를 받으면 `DestroyNode` 한다 (AnimStateTransitionNode.cpp:323-337). `BreakAllPinLinks(true)`·`BreakAllNodeLinks`·`RemoveNode(bBreakAllLinks=true)` 는 상대 노드에 통지하므로, 상태를 분리 보관하면 전이가 즉시 사라져 롤백이 불가능해진다. 분리·복원·되돌리기 경로는 전부 `BreakLinkTo`(통지 없음) 로 끊고, 상태 삭제는 전이를 먼저 명시적으로 분리한다 (에디터와 같은 최종 결과).
- **주석 노드 원문** — `UEdGraphNode_Comment::PostPlacedNewNode` 가 `NodeComment` 를 기본 "Comment" 로 되돌린다 (EdGraphNode_Comment.cpp:97). 원문은 `Finalize()` 뒤에 써야 한다. 첫 실행에서 `rule_source` 가 전부 null 로 나온 원인.

**규칙 그래프 멱등의 구현**: 전체 재생성이라 노드 Guid 가 바뀌므로 "같은 AST 2회 → 같은 revision" 은 재생성으로는 성립하지 않는다. 대신 주석에 (원문, 생성 직후 그래프 해시) 를 두고, 원문이 같고 해시가 일치(사람이 손대지 않음)하면 **no-op** 으로 처리한다. 해시는 Guid 대신 (위치, 클래스, 함수/변수 이름, 핀 기본값, 인덱스 기반 링크) 로 계산해 재생성해도 같다.

**Phase 5 착수 조건**: 본 결과 검토. 범위는 §F Phase 5 — `ABP_Hero_Base` **복제본**에서 Free Locomotion(`BS_Hero_Locomotion1D` + `Speed`) · Jump · Attack(Slot + LayeredBlendPerBone) 을 구성하고 diff 검토 후 원본 적용. 선행: `create_blendspace`(축 설정 API 조사) 또는 기존 BlendSpace 재사용 결정, 복제 Tool(`duplicate_animation_blueprint`) 필요 여부.

---

## Phase 5 결과 (2026-10-16, 브랜치 `feat/ai_auto_ABP`)

**선행 실측이 범위를 바꿨다.** 운영 애셋 `ABP_Hero_Base` 를 `depth=-1` 로 덤프하니 이동·점프 상태머신이 **상태 내부까지 사람이 이미 완성**한 상태였다 (Idle=`AS_Idle` · Move=`BS_Hero_Locomotion1D` X←`Get Speed` K2 노드 · JumpStart/FallLoop/FallLand 시퀀스 · alias 4 · conduit 2 · 전이 12). 복제본에 "구성할 것" 이 Attack 레이어뿐이라, 사용자 확정(2026-10-16)으로 범위를 바꿨다:

- **적용 범위 = 새 ABP 처음부터 재구성** (`/Game/Animation/Hero/ABP_Hero_McpBuild`) → 운영 애셋과 구조 비교 → 검토 뒤 원본엔 Attack 레이어만 적용 후보.
- **도구 추가 = VariableGet 노드 · LayerSetup 본 필터** (같은 배치 ref 그래프·duplicate Tool 은 보류). **BlendSpace = 기존 재사용**. **Attack 슬롯 = `UpperBody` 신설** (몽타주 5개는 전부 `DefaultSlot` — 콘텐츠 작업은 별도).

| 산출물 | 위치 |
| :--- | :--- |
| 변수 Get 노드 | `add_node {class:"K2Node_VariableGet", variable}` — `Core/AnimMcpGraphMutator` `VariableClassOf`(규칙 생성기와 공유) · `IsVariableGetClassName` · `ValidateVariableGetGraph`(AnimGraph·상태 그래프만, 전이 규칙·상태머신 그래프 거부) · `ResolveVariable`(BlueprintVisible) · `AddVariableGetNode`(`FGraphNodeCreator<UK2Node_VariableGet>` + `SetFromProperty(self)`, 출력 핀 = 변수 이름). `Operations::ResolveAddNode/ApplyAddNode` 분기, asset·enum·properties 거부 |
| LayerSetup 본 필터 | `Core/AnimMcpPropertyRules` 허용 목록에 LayeredBoneBlend `BlendMode`·`LayerSetup` 추가. `JsonToImportText` 가 **구조체(JSON 객체 → `(Field=Value,...)`)·구조체 배열을 재귀** 변환, 없는 필드 거부, 생략 필드 기본값. `PropertyToJson` 이 구조체 → 객체로 되돌린다. `Mutator::ValidateLayerSetup` — LayeredBoneBlend · BlendMode==BranchFilter · 항목 수 == 포즈 수(+같은 배치 앞선 `add_blend_pose`, `FBatchState::PendingBlendPoses`) · 본 이름이 `TargetSkeleton` 에 존재 |
| 테스트 | `phase4_test.py` **B2 절** 추가(상태 내부 채우기 · VariableGet→BlendSpace.X · 거부 6종 · 롤백) · **`phase5_test.py`** 신규(LayerSetup 1·2 포즈 · 조회 왕복 · 거부 6종 · 롤백 · `--recheck`) · `phase3_test.py`·`phase4_test.py` 회귀 PASS |
| 히어로 빌드 | **`Tools/mcp/phase5_build_hero.py`** — 빈 ABP 에서 루트(SM → SaveCachedPose → UseCachedPose×2 → Slot DefaultSlot/UpperBody → LayeredBoneBlend(spine_01, 메시 공간 회전) → Inertialization → Output) · 상태 5 · 전이 11(규칙 AST) · 상태 내부(애셋 플레이어 · Speed→X) 를 배치 3개로 구성, 컴파일 0 에러, 저장. `--overwrite`·`--recheck`. 비교 문서 **`.claude/plans/animbp-phase5-hero-diff.md`** 자동 생성 |

**실측으로 바로잡은 것 2건**
- **`ExportText_Direct(Delta=null)` 는 0 값을 비운다** — `FProperty::ExportText_Direct` 는 `!Identical(Data, Delta)` 일 때만 쓰므로(Property.cpp:1005-1007) 값이 0 인 enum(`BranchFilter`)·숫자는 빈 문자열이 된다. 조회에서 `BlendMode:""` 로 드러났고, **롤백용 이전 값 저장(`SetPropertyFromJson`·`ImportPropertyText`)에도 같은 함정**이 있었다(0 값에서 바꾼 뒤 롤백하면 `ImportText("")` 실패). 셋 다 `ExportTextItem_Direct`(무조건 씀)로 바꾸고, enum 은 `GetNameStringByValue` 로 직접 이름을 낸다. Inspector 의 revision 해시는 그대로 `ExportText_Direct` 를 써서 기존 상태 파일과 호환된다.
- **사전 검증은 같은 배치의 `add_blend_pose` 를 모른다** — LayerSetup 항목 수 검증이 배치 적용 전 포즈 수로 거부했다. Preview 가 앞선 `add_blend_pose` 수를 노드별로 세어 더한다.

**실측 확정 (핸드오프 §3-2 의 미검증 경로)**: 상태 내부는 `add_state` 응답의 `bound_graph_guid` 를 다음 배치의 `add_node.graph` 에 넘겨 채운다. StateResult 입력 핀 이름은 **`Result`**. 같은 배치 안에서는 `graph` 가 guid 문자열만 받아 상태 생성과 내부 채우기가 두 배치로 나뉜다(보류한 편의 기능). `AnimGraphNode_Inertialization` 은 허용 목록 없이도 `add_node` 로 생성·연결·컴파일된다 (핀 `Source`/`Pose`).

**검증 수치**: `ABP_Hero_McpBuild` 그래프 18 · 노드 82 · 연결 59 · 상태 5 · 전이 11, 컴파일 0 에러 0 경고, 에디터 재시작 후 revision·노드 집합·state_machines 뷰 동일. 운영 애셋(그래프 21 · 노드 69 · 상태 11 · 전이 12)은 읽기만, revision `f11a834d…` 유지. Development · DebugGame 빌드 성공, 경고 0.

**운영 애셋 관찰(도구 미개입)**: `EndInAir → IdleAlias` 규칙이 `Speed >= 20`, `EndInAir → MoveAlias` 가 `Speed < 20` 으로 읽힌다 — 의도가 반대라면 사람이 고칠 항목.

**원본 적용 (2026-10-16, 사용자 승인 뒤)**: 비교 문서 검토 후 `ABP_Hero_Base` 에 UpperBody 레이어만 적용했다 — `expected_revision=f11a834d…` 으로 보호한 **배치 하나(op 16)**. 컴파일 0 에러 0 경고, 저장(revision `af9dca59…`).

**배선 실수와 재적용 (같은 날)**: 첫 적용은 상태머신 출력을 캐시해 `Slot DefaultSlot` 과 `Slot UpperBody` 를 **나란히** 두고 LayeredBoneBlend 로 합쳤다. 사용자 PIE 에서 **공격 몽타주 중 상체가 깨짐** — 몽타주는 DefaultSlot(전신)에서 도는데 비어 있는 UpperBody 슬롯은 로코모션 포즈를 그대로 내보내고, 그것이 `spine_01` 이하를 가중치 1 로 덮어 몽타주 상체를 지운다. 올바른 패턴은 **상체 슬롯을 전신 슬롯 뒤에**: `SM → Slot DefaultSlot → SaveCachedPose "FullBody" → UseCachedPose → Layer.BasePose` / `UseCachedPose → Slot UpperBody → Layer.BlendPoses_0` — 상체 슬롯이 비면 전신 출력이 그대로 통과해 블렌드가 항등이다. `expected_revision=af9dca59…` 배치 하나(op 10: BasePose 링크 해제 · SaveCachedPose FullBody · UseCachedPose 추가 · 기존 UpperBody 용 UseCachedPose 를 FullBody 로 교체 · Locomotion 캐시와 UseCachedPose 제거 · SM→DefaultSlot 직결 복구)로 재배선, 컴파일 0 에러 0 경고, 저장. **최종 revision `3c146b5f04c1648922feca885ba1eb8a0a52e118`**, 노드 74 · 연결 54, 상태머신 무변경, 에디터 재시작 후 재조회·컴파일 일치. `phase5_build_hero.py` 와 `ABP_Hero_McpBuild` 도 같은 배선으로 고쳐 재생성(revision `e8b13f62…`). PIE 재확인은 사용자. 되돌리기는 `git checkout -- Content/Animation/Hero/ABP_Hero_Base.uasset`.

**Phase 6 착수 조건**: 본 결과 검토. 후보 — Alias/Conduit 생성 · 상태머신/상태 이름 변경 op · 같은 배치 `graph:{ref}` · `duplicate_animation_blueprint` · `create_blendspace` · Linked Layer · Property Binding · Automation Test 연동 · `quit_editor` Tool · 타 프로젝트 재현.

---

## Phase 6-1 결과 (2026-10-16, 브랜치 `feat/ai_auto_ABP`) — 상태머신 완성

핸드오프 phase6 §3 전부 구현. `phase6_1_test.py` 8개 절 **PASS** + `phase3/4/5_test.py` 회귀 PASS + 재시작 `--recheck` PASS(6-1 · 5 · 히어로 빌드). Development · DebugGame 빌드 성공, 경고 0. **`phase5_build_hero.py` 가 운영 애셋과 상태머신 1:1**(상태 5 · conduit 2 · alias 4 · 전이 12 · 이름 `Locomotions` · 상태 내부) 인 `ABP_Hero_McpBuild` 를 만든다 — 비교 문서 §1 이 그래프 21/21 · 연결 54/54 · 상태 11/11 · 전이 12/12.

**§9-1(alias 방향) 은 소스로 해소 — 사용자 질문 불필요.** `UAnimStateAliasNode::ValidateNodeDuringCompilation`(AnimStateAliasNode.cpp:48-56): 들어오는 전이가 있는 alias 는 **정확히 하나의 상태를 가리키고 global 이 아니어야** 한다(컴파일 오류). 나가는 전이는 다중·global 모두 허용. 운영 애셋의 `IdleAlias`/`MoveAlias`(전이 대상) 는 단일 상태라 규칙에 맞는다. 도구는 이 규칙을 `ValidateAliasTargets`·`ValidateTransitionTarget` 로 적용 전에 거부한다.

| 산출물 | 위치 |
| :--- | :--- |
| op 4종 | `add_conduit {ref?, sm\|graph, name?, pos?, rule?}` · `add_state_alias {ref?, sm\|graph, name?, pos?, states:[{node\|ref}] \| global}` · `set_alias_states {node\|ref, states\|global}` · `rename_node {node\|ref, name}` — `Core/AnimMcpOperations.cpp` Validate/Apply 분기, `Core/AnimMcpGraphMutator` `AddConduit`(`FGraphNodeCreator<UAnimStateConduitNode>`, PostPlacedNewNode 가 BoundGraph 생성 AnimStateConduitNode.cpp:69-95) · `AddStateAlias` · `ValidateAliasTargets`/`SetAliasTargets`(`GetAliasedStates()` 비const 접근자 ANIMGRAPH_API, `bGlobalAlias`) · `ValidateTransitionTarget` · `RenameNode`(상태·conduit·alias = `UAnimStateNodeBase::OnRenameNode` → RenameGraph/StateAliasName, 상태머신 = `UAnimGraphNode_StateMachineBase::OnRenameNode` AnimGraphNode_StateMachineBase.cpp:243-246; 검증은 노드의 `MakeNameValidator`) · `RuleGraphOf` |
| conduit 규칙 | `set_transition_rule` 이 conduit 도 받는다. `AnimMcpTransitionRule::Build` 가 `UEdGraph*`(규칙 그래프) 를 받도록 바꿈 — conduit BoundGraph 도 `UAnimationTransitionGraph`(conduit 스키마). `ReplaceTransitionRule` 이 소유 노드(전이\|conduit) 공용, automatic 은 전이만 |
| 같은 배치 상태 내부 | `add_node.graph` 에 `{ref\|node}`(상태 → 포즈 그래프; conduit·alias 거부) · 노드 참조에 `{result_of: {ref\|node}}`(그 상태의 StateResult). 상태 생성·내부·conduit·alias·전이·이름 변경이 **배치 하나**(테스트 A: op 39) |
| Inspector | `states[]` 에 conduit 의 `rule_graph_guid/rule_generated/rule_source/rule_modified/rule_node_count`(전이와 같은 `WriteRuleFields`), alias 의 `global`·`aliased_states[]`·`aliased_state_names[]` |
| 테스트 | `Tools/mcp/phase6_1_test.py` — A 운영 구조 1:1 배치 하나 · B 뷰 · C rename(4종·되돌리기·거부 3) · D set_alias_states(대상 alias 거부 2·소스 교체·global·되돌리기) · E 거부 9종 · F 10-op 중간 실패 롤백(conduit·alias·rename·alias 대상·conduit 규칙·상태 삭제 연쇄 복원) · G conduit/alias 삭제 연쇄(상태 9·전이 8) · H 저장/recheck |
| 빌드 스크립트 | `phase5_build_hero.py` 상태머신 절을 운영 1:1 로(배치 하나) · `--diff-only` · 비교 문서 §4 "의도한 차이" 에서 alias/conduit·이름 항목 제거 |

**실측으로 확인한 것**
- alias 의 In/Out 핀 이름은 `In`/`Out`(AnimStateAliasNode.cpp:42-46), conduit 도 같다. `GetInputPin()/GetOutputPin()` 이 `Pins[0]/[1]`.
- conduit 규칙 그래프의 Result 는 `UAnimGraphNode_TransitionResult`, 핀 `bCanEnterTransition` — 전이와 동일해 규칙 생성기·주석(rule_source)·멱등이 그대로 동작. 비교 문서에서 conduit 내부에 `EdGraphNode_Comment` 가 하나 더 보이는 것은 도구 주석(원문 저장)이다.
- `UAnimStateAliasNode::OnRenameNode` 는 검증 없이 `StateAliasName` 만 바꾼다 — 도구가 `FNameValidatorFactory::MakeValidator(node)` 로 먼저 검증한다. 상태머신 이름 검증기(`FAnimStateMachineNodeNameValidator`) 는 다른 상태머신·애니 레이어 함수 이름과의 충돌도 본다.
- 운영 애셋의 `JumpSources → JumpSelector` 전이와 conduit 2개는 규칙 노드가 없고 **Result 기본값 `true`** 다(이전 비교 문서의 "규칙 없음 → false" 표기는 오류였고 `--diff-only` 로 정정).

**Phase 6-2 착수 조건**: 본 결과 검토. 범위는 핸드오프 phase6 §4(duplicate · delete · quit_editor Tool, 새 Tool 은 재시작 전 HTTP 테스트). §9-4(삭제 보호) 를 코드 전에 확정.

---

## Phase 6-2 결과 (2026-10-16, 브랜치 `feat/ai_auto_ABP`) — 애셋 수명

핸드오프 phase6-2 §12 "6-2" 전부 구현. `phase6_2_test.py` 5개 절 **PASS** + `phase3/4/5/6_1_test.py` 회귀 PASS + 재시작 `--recheck` PASS(5 · 6-1 · 6-2). Development · DebugGame 빌드 성공, 경고 0. Tool 은 9 → **12개** (세션 재시작 전에는 HTTP 로만 검증됨).

**사용자 확정 결정 (구현 전, 2026-10-16) — A안**: 삭제 보호 = **ini 보호 목록** `[AnimGraphMcp] +ProtectedAssets=` / `+ProtectedPaths=` + `confirm:true` 필수 + 참조 중이면 `force` 없이는 거부. `quit_editor` 는 더티 패키지가 있으면 `save_dirty` / `discard_dirty` 없이는 거부. 복제는 노드 Guid 보존이 기본.

**❓ 해소 (소스)**
- **복제본 노드 Guid**: `FBlueprintEditorUtils::PostDuplicateBlueprint` 가 모든 노드에 `CreateNewGuid()` 를 돌린다 — 단 `FBlueprintDuplicationScopeFlags::TheSameNodeGuid` 스코프 안에서는 유지 (BlueprintEditorUtils.cpp:1682-1688, 정의 BlueprintEditorUtils.h:1996-2016, `bStaticFlags` 가 UNREALED_API). 도구는 `preserve_node_guids`(기본 true) 로 이 스코프를 켠다. 그래프 Guid 는 UPROPERTY 라 항상 복사된다. **revision 은 복제본과 원본이 다르다** — 노드 프로퍼티의 오브젝트 참조(StateMachine 의 `EditorStateMachineGraph` 등)가 애셋 경로째 ExportText 되어 패키지 이름이 해시에 섞인다. 구조 비교는 그래프 Guid·노드 Guid·연결·상태머신 뷰로 한다(테스트 `shape()`).
- **quit 응답 시점**: HTTP 응답은 `OnComplete` 안에서 동기로 소켓에 쓰인다 (`FHttpConnection::BeginWrite` → `ContinueWrite(0)`, HttpConnection.cpp:229-246). 종료는 `FTSTicker` 로 한 프레임 미뤄 `GEngine->DeferredCommands` 에 `QUIT_EDITOR` 를 넣는다 — 코어 티커(LaunchEngineLoop.cpp:6072) 바로 뒤에 `TickDeferredCommands`(:6078) 가 돈다. `QUIT_EDITOR` = `UUnrealEdEngine::CloseEditor()`(EditorServer.cpp:5775-5779) = PIE 종료 + `RequestEngineExit`(UnrealEdEngine.cpp:935-950). `CLOSE_SLATE_MAINFRAME` 경로의 저장 프롬프트(MainFrameHandler.h:153-186)는 타지 않으므로 더티 처리는 도구가 명시적으로 한다.

| 산출물 | 위치 |
| :--- | :--- |
| 보호 목록 | `Core/AnimMcpAssetProtection.{h,cpp}` (신규) — `GConfig->GetArray([AnimGraphMcp] ProtectedAssets/ProtectedPaths, GEngineIni)` 1회 로드, 패키지 경로 정확 일치 / 접두 일치(대소문자 무시). `EnsureNotProtected` → `ASSET_PROTECTED`(403). 삭제·create overwrite·duplicate overwrite 세 곳에서 검사. 프로젝트 ini: `ABP_Hero_Base` · `/Game/Assets/` |
| 삭제·복제 기계 | `Core/AnimMcpAssetOps.{h,cpp}` (신규) — `DeleteAssetAtPath`(에디터 닫기 → `UEditorAssetSubsystem::DeleteAsset` → 아래 실측 처리) · `FindReferencers`(AssetRegistry `GetReferencers(Package)`, 자기·임시 제외) · `DuplicateAnimBlueprint`(`DuplicateLoadedAsset` + Guid 스코프 + 레지스트리 등록 보정). `AnimMcpBlueprintFactory` 의 overwrite 삭제가 이 기계를 쓴다 |
| Tool 3개 | `Tools/AnimMcpTools_Assets.cpp` `duplicate_animation_blueprint {source_path, dest_path, overwrite, preserve_node_guids, save}` → info + `duplicated/source_path/source_revision/node_guids_preserved/saved` · `delete_animation_blueprint {asset_path, confirm, force}` → `deleted/forced/referencers[]` (AnimBP 외 클래스는 BAD_REQUEST) · `Tools/AnimMcpTools_Editor.cpp` (신규) `quit_editor {save_dirty, discard_dirty}` → `quit_requested/process_id/saved_packages/discarded_packages/was_pie` |
| 상태 조회 | `get_editor_status` 에 `process_id` · `protection{assets,paths}` · `dirty_package_count` |
| 오류 코드 | `ASSET_PROTECTED`(403) · `ASSET_REFERENCED`(409, details.referencers) · `DIRTY_PACKAGES`(409, details.dirty_packages[{package,kind}]) |
| Python | `server.py` Tool 3개 · **`Tools/mcp/wait_for_exit.py`**(브리지 EDITOR_GONE ∧ `tasklist` 에 pid 없음 — subprocess 직접 호출이라 MSYS 경로 변환 무관) · `phase6_2_test.py`(+`--recheck`·`--no-quit`) |

**실측으로 바로잡은 것 3건**
- **참조 중인 패키지는 ForceDelete 가 파일을 남긴다** — `ObjectTools::CleanupAfterSuccessfulDelete` 는 패키지가 아직 참조되면(컴파일된 클래스·CDO 등) 삭제 목록에서 빼 파일도 두고 언로드도 않는다 (ObjectTools.cpp:2535-2550). 그 뒤 create 의 `FullyLoad()` 가 남은 파일에서 애셋을 되살려 "still exists" 로 실패했다(phase4·5 회귀에서 재현). 처리: `ResetLoaders(Package)`(링커가 쥔 파일 핸들 해제 — 안 하면 Windows 에서 삭제 실패) → `UPackageTools::UnloadPackages` → 남은 객체 임시 패키지로 이동·가비지 → `FAssetRegistryModule::PackageDeleted` → 파일 직접 삭제(`IFileManager::Delete`, `FileExists` 로 확인) → `ScanModifiedAssetFiles`. 팩토리에도 "생성 직전 잔존 객체 이동" 폴백을 되살렸다.
- **`FEditorFileUtils::SaveDirtyPackages(bFastSave)` 는 더티 ABP 를 저장하지 않고 false** — `quit_editor save_dirty` 는 패키지마다 애셋 객체를 찾아 `UEditorAssetSubsystem::SaveLoadedAsset`(save Tool 과 같은 경로) 로 저장한다. 맵(월드 패키지)은 이 도구가 저장하지 않는다 — 더티 맵이 있으면 `discard_dirty` 로만 종료.
- **자식 AnimBP(부모 = 다른 ABP 의 `_C`) 는 루트 AnimGraph 가 없다** — `create_animation_blueprint` 가 BP 클래스를 부모로 받으면 info 에 `NO_ANIM_GRAPH` 진단이 뜨는 것이 정상. 테스트의 참조자 재료로 썼다.

**검증 수치**: 복제(Guid 보존) 노드 12/12 동일·그래프 Guid·연결·상태머신 뷰 동일, Guid 재생성 시 수 같고 집합 다름. 거부 — 복제 4종(ASSET_EXISTS·자기 자신·없는 원본·보호 2종) · 삭제 5종(confirm·보호 2종·클래스·없음) · 참조 중 force 없음. force 삭제 뒤 디스크·레지스트리 모두 소멸, 자식 삭제 정상. quit: 더티 1 → `DIRTY_PACKAGES`(에디터 유지) → `save_dirty` 로 저장·종료, `wait_for_exit` 2회 폴링 안에 pid 소멸, 재시작 뒤 저장된 편집(노드 +1) 확인. 운영 애셋 revision `3c146b5f…` 전 구간 불변.

**Phase 6-3 착수 조건**: 본 결과 검토. 범위는 핸드오프 phase6-2 §12 "6-3 BlendSpace 생성". **§12-B(축 설정 — `BlendParameters` 리플렉션 ImportText 허용 여부)** 를 코드 전에 확정. 선행 조사: `Editor/UnrealEd/Private/Factories/BlendSpaceFactory*.cpp` · Persona 의 축 편집 경로.

---

## Phase 6-3 결과 (2026-10-16, 브랜치 `feat/ai_auto_ABP`) — BlendSpace 생성

핸드오프 phase6-2 §12 "6-3" 구현. `phase6_3_test.py` 5개 절 **PASS** + `phase3/4/5/6_1/6_2_test.py` 회귀 PASS + 재시작 `--recheck` PASS(5 · 6-1 · 6-3 · 6-2). Development · DebugGame 빌드 성공, 경고 0. Tool 12 → **13개** (`create_blendspace`; 세션 재시작 전에는 HTTP 로만 검증됨).

**§12-B 는 소스로 해소 — 사용자 질문 불필요.** `UBlendSpace::BlendParameters[3]` 은 protected 이고 공개 setter 가 없다 (BlendSpace.h:905-907). Persona 의 디테일 패널도 `DetailBuilder.GetProperty(GET_MEMBER_NAME_CHECKED(UBlendSpace, BlendParameters))->GetChildHandle(AxisIndex)` — 즉 **프로퍼티 시스템(리플렉션)** 으로 편집한다 (BlendSpaceDetails.cpp:208-217). 따라서 "리플렉션을 허용할지" 는 선택지가 아니라 엔진의 유일한 경로다. 도구는 `FProperty::ContainerPtrToValuePtr<FBlendParameter>(BlendSpace, AxisIndex)` 로 주소만 얻고 `FBlendParameter` 의 고정 필드 6개(DisplayName · Min · Max · GridNum · bSnapToGrid · bWrapInput)만 쓴 뒤 `PostEditChange()` — 임의 프로퍼티 ImportText 범용 명령이 아니므로 허용 목록 원칙과 충돌하지 않는다.

| 산출물 | 위치 |
| :--- | :--- |
| 생성 기계 | `Core/AnimMcpBlendSpaceFactory.{h,cpp}` (신규) — `ParseCreateParams`(JSON → 축·샘플, 형식 오류 BAD_REQUEST details.field) · `CreateBlendSpace`(팩토리 재현 EditorFactories.cpp:7353-7369/:7427-7443: `NewObject<UBlendSpace[1D]>` → `SetSkeleton` → 프리뷰 메시 → 축 → `AddSample` → `ResampleData` → `ValidateSampleData` → `PostEditChange` → `AssetCreated`) · `DescribeBlendSpace`(축·샘플·sample/grid/segment/triangle 수·anim_length·loop·interpolate_using_grid) |
| Tool | `create_blendspace {asset_path, skeleton, dimensions:1\|2, axes[{name,min,max,grid?,snap?,wrap?}], samples?[{animation, value:[x]\|[x,y]}], preview_mesh?, overwrite?, save?}` → 요약 + `created`·`saved`. `list_animation_assets` 에 `details?` — BlendSpace 항목에 `blendspace{...}` 요약(로드 필요, 요청 시에만) |
| 사전 검증 (애셋 생성 전, 실패 시 아무것도 남기지 않음) | 차원 1\|2 · 축 수 = 차원 · min<max · grid 1..1000 정수 · 샘플 애니는 `UAnimSequence` 만(몽타주 BAD_REQUEST) · 스켈레톤 `IsCompatibleForEditor`(`SKELETON_MISMATCH`) · **범위 밖 거부**(`OUT_OF_RANGE`) · 중복 위치(`DUPLICATE_POSITION`, `IsSameSamplePoint` 와 같은 허용 오차) · additive 타입 혼합(`ADDITIVE_MISMATCH`) · 엔진 `AddSample` 거부(`ENGINE_REJECTED`, 생성 중이던 객체는 가비지) · 기존 애셋은 보호 목록 → overwrite 삭제(6-2 기계) |
| 테스트 | `Tools/mcp/phase6_3_test.py` — A 원본 요약 · B 1D 재현(축·샘플·grid·선분 수 원본과 동일, anim_length 동일) · C 새 ABP 에 BlendSpacePlayer(set_asset)+Speed→X 컴파일 0 에러·저장 · D 2D(삼각형 1·그리드 0·wrap) · E 거부 12종 + 거부 후 미생성 확인 · `--recheck`. 테스트 애셋 `/Game/Animation/Test/BS_McpTest`·`BS_McpTest2D`·`ABP_McpBsTest`(덮어쓰기 대상) |

**실측으로 확인한 것**
- **`AddSample` 은 범위 밖 값을 거부하지 않고 축을 늘린다** — `ExpandRangeForSample`(BlendSpace.cpp:1610-1626) 이 Min/Max/GridNum 을 키운다. 요청한 축을 지키려면 도구가 먼저 거부해야 한다(구현함).
- **2D 는 기본적으로 그리드가 비어 있다** — `bInterpolateUsingGrid=false`(기본) 면 `ResampleData2D` 가 삼각분할(`BlendSpaceData.Triangles`) 만 만들고 `EmptyGridElements()` 한다 (BlendSpace.cpp:2784-2804). 1D 는 선분(`Segments`) + 그리드. 첫 테스트가 그리드 20 을 기대해 실패했고, 요약에 `segment_count`/`triangle_count`/`interpolate_using_grid` 를 추가해 바로잡았다. 샘플 3 → 삼각형 1.
- `ResampleData()` 는 내부에서 `ValidateSampleData()` 를 먼저 부른다(:2654) — Persona 순서(Resample → Validate) 를 그대로 따라도 무해.
- **방금 저장한 파일은 잠깐 잠길 수 있다** — 회귀 중 간헐적으로 `DeleteAsset` 뒤 파일 삭제가 실패했다(`IFileManager::Delete` 뒤에도 `FileExists`). 외부 핸들(바이러스 검사·레지스트리 스캔)로 보이며, `AnimMcpAssetOps::DeleteAssetAtPath` 가 0.3초 간격 최대 10회 재시도하도록 고쳤다(실측 "2 attempts" 로 통과). 6-2 기계의 보완.
- 원본 `BS_Hero_Locomotion1D`: 축 Speed 0..500 grid 5 · 샘플 3 · anim_length 6.0 — 도구로 1:1 재현되고 재시작 뒤 요약 동일.

**Phase 6-4 착수 조건**: 본 결과 검토. 범위는 핸드오프 §12 "6-4 바인딩·레이어" — (a) Property Binding `bind_pin`/`unbind_pin`(`FAnimGraphNodePropertyBinding`, 에디터 UI 가 바인딩을 채우는 경로 ❓ `Editor/AnimGraph/Private/AnimGraphNodeBinding*.cpp` · `AnimBlueprintExtension_PropertyAccess`), (b) Linked Anim Layer 는 **§12-C 로 진행 여부 확정**(운영 애셋은 Linked Layer 0).

---

## Phase 6-4a 결과 (2026-10-17, 브랜치 `feat/ai_auto_ABP`) — Property Binding

핸드오프 §12 "6-4 (a)" 구현. `phase6_4_test.py` 6개 절 **PASS** + `phase3/4/5/6_1/6_3/6_2_test.py` 회귀 PASS + 재시작 `--recheck` PASS(5 · 6-1 · 6-3 · 6-4 · 6-2). Development · DebugGame 빌드 성공, 경고 0. **Tool 추가 없음(op 2종)** — 세션 재시작 없이 MCP 에서 바로 쓸 수 있다. (b) Linked Anim Layer 는 §12-C 미확정으로 **미착수**.

**❓ 해소 — 에디터가 바인딩을 채우는 경로** (`AnimGraphNodeBinding_Base.cpp:428-507` OnAddBinding, `:509-521` OnRemoveBinding): `Binding->Modify()` → 핀 노출(`OnSetPinVisibility`) → 핀 링크 해제 → `FAnimGraphNodePropertyBinding{PropertyName, PropertyPath, PathAsText(IPropertyAccessEditor::MakeTextPath), Type(Property|Function), bIsBound=true}` → `PropertyBindings.Add` → `ReconstructNode()`(→ `OnReconstructNode` → `RecalculateBindingType` 이 PinType·PromotedPinType·bIsPromotion 을 `ResolvePropertyAccess`+`GetPropertyCompatibility` 로 계산, `:41-90`) → `MarkBlueprintAsModified`. 제거는 `PropertyBindings.Remove`. 컴파일은 `UAnimBlueprintExtension_Base` 가 `UAnimBlueprintExtension_PropertyAccess::AddCopy` 로 fast-path 복사를 등록(`AnimBlueprintExtension_Base.cpp:190-250`); PropertyAccess 확장은 `UAnimBlueprintExtension::RequestExtensionsForNode` 의 기본 집합이라(`AnimBlueprintExtension.cpp:75-83`) 별도 요청이 필요 없다.

**접근 제한과 우회**: `UAnimGraphNodeBinding_Base` 는 모듈 Private 헤더(`Editor/AnimGraph/Private/`), `PropertyBindings` 는 private UPROPERTY, `UAnimGraphNodeBinding` 은 `Internal/`. 노드의 `Binding`(private UPROPERTY, `AnimGraphNode_Base.h:232-233`) 도 `GetMutableBinding()` 이 불완전 타입 포인터를 돌려줘 `GetClass()` 조차 못 부른다 → **전부 리플렉션**: `FObjectPropertyBase("Binding")` 로 객체 → `FMapProperty("PropertyBindings")`(키 FName · 값 `FAnimGraphNodePropertyBinding` 검증) → `FScriptMapHelper::AddPair/FindValueFromHash/GetMaxIndex`. 공개 API 로 가능한 것은 그대로: `GetPinProperty(FName)` · `SetPinVisibility` · `RemoveBindings` · `HasBinding` · `ReconstructNode`. `GetPinBindingInfo`·`RecalculateBindingType`·`EnsureBindingsArePresent` 는 protected 라 쓰지 않고, 타입 계산은 `ReconstructNode` 에 맡긴다.

| 산출물 | 위치 |
| :--- | :--- |
| 바인딩 기계 | `Core/AnimMcpPropertyBinding.{h,cpp}` (신규) — `ReadBindings`(이름순) · `FindRaw`(롤백 보관) · `ValidateBind`(optional pin · `GetPinProperty` · 링크 없음 · `ResolvePropertyAccess` on `SkeletonGeneratedClass` · 콜백 오버로드로 리프가 함수인지 · `GetPropertyCompatibility` ≠ Incompatible) · `Bind`(핀 노출 → AddPair → ReconstructNode → MarkModified) · `Unbind`(`RemoveBindings` → ReconstructNode) · `WriteRaw/RemoveRaw`(되돌리기) · `AppendRevision` |
| op 2종 | `Core/AnimMcpOperations.cpp` `bind_pin {node\|ref, property, path:[...]\|"A.B"}` → 응답 `type, path_text, promotion, replaced, pin_exposed` · `unbind_pin {node\|ref, property}`. Preview: 실제 노드는 전체 검증, 같은 배치 ref 는 클래스만(DeferredNote). 되돌리기 = 이전 항목 복원/제거 + 핀 가시성 복원 |
| Inspector | `optional_pins[].binding {path[], path_text, type, context, promotion}`(bound 일 때) · revision 에 `B\|이름\|경로\|타입\|컨텍스트` 줄(바인딩 없으면 줄 없음 → 기존 해시 호환, 기존 state 파일 recheck 전부 통과) |
| 테스트 | `Tools/mcp/phase6_4_test.py` — A bind X←Speed(VariableGet 없이 컴파일 0 에러·bound·revision 변경) · B 점 경로 교체(replaced)·함수 경로 `GetDeltaSeconds`(type Function)·되돌리면 revision 동일 · C unbind(핀 노출 유지) · D 롤백 2종(같은 배치 ref 실패 op) · E 거부 9종(없는 프로퍼티·PATH_UNRESOLVED·TYPE_INCOMPATIBLE·path 누락·Root·PIN_LINKED·VariableGet·없는 ref) + 같은 배치 ref 에 bind · F 저장 · `--recheck`. 테스트 애셋 `/Game/Animation/Test/ABP_McpBindTest` |

**실측으로 확인한 것**
- `FScriptMapHelper::AddPair` 는 키가 있으면 값을 덮어쓴다 — 재바인딩은 Add 한 번으로 끝난다. `ReconstructNode` 뒤 `PinType`·`bIsPromotion` 이 채워진다(`promotion:false` — float→float).
- 함수 경로(`["GetDeltaSeconds"]`, BlueprintPure·ThreadSafe)도 같은 경로로 묶이고 컴파일된다(`type: Function`).
- **사전 검증은 같은 배치의 앞선 op 결과를 모른다** — 링크를 끊는 op(`remove_node`·`disconnect`) 뒤에 `bind_pin` 을 같은 배치에 두면 `PIN_LINKED` 로 거부된다. 두 배치로 나눈다(테스트 E 정리). 기존 노드의 없는 핀도 사전 검증에서 걸리므로 롤백 테스트는 6-1 때처럼 같은 배치 ref 노드로 만든다.
- 사전 검증 실패 봉투는 op 별 오류를 `details.planned[i].error` 에 중첩한다 — `reason` 을 읽을 때 그 안을 본다.

**Phase 6-4b / 6-5 착수 조건**: 본 결과 검토. **§12-C(Linked Anim Layer)** 를 사용자와 확정 — 저작까지 하려면 레이어 인터페이스 애셋(`UAnimLayerInterface` BP) 생성 · ABP 의 인터페이스 구현(`FBlueprintEditorUtils::ImplementNewInterface` → 레이어 그래프 생성) · `UAnimGraphNode_LinkedAnimLayer::SetLayerName` 까지 세 단계가 필요하고, 운영 애셋은 Linked Layer 0 이다. 조회(`linked_anim_layers[]`)로 종료하면 6-5 검증 자동화로 간다.

---

## Phase 6-4b 결과 (2026-10-17, 브랜치 `feat/ai_auto_ABP`) — Linked Anim Layer 저작

**§12-C 사용자 확정 (2026-10-17)**: Lyra 식 레이어 분리를 쓸 계획 → 저작까지 구현. 범위 = Tool 2개(`create_anim_layer_interface` · `implement_anim_layer_interface`) + op(`add_node layer` · `set_linked_layer`) + 조회 확장, **포즈 입력만**(값 파라미터 없음). `phase6_4b_test.py` 8개 절 **PASS** + 회귀(phase3/4/5/6-1/6-3/6-4/6-2) PASS + 재시작 `--recheck` PASS(5 · 6-1 · 6-3 · 6-4 · 6-4b · 6-2). Development · DebugGame 빌드 성공, 경고 0. Tool 13 → **15개** (세션 재시작 전에는 HTTP 로만 검증됨).

**엔진 경로 (소스로 확인)**
- **인터페이스 애셋**: `UAnimLayerInterfaceFactory` 는 `UAnimBlueprintFactory` 에 `BlueprintType = BPTYPE_Interface` 만 더한 것(AnimBlueprintFactory.cpp:514-517). `FactoryCreateNew`(:451-503) 는 인터페이스면 부모를 `UAnimLayerInterface` 로 바꿔 `FKismetEditorUtilities::CreateBlueprint(..., BPTYPE_Interface, UAnimBlueprint, UBlueprintGeneratedClass)`. 스켈레톤 없음(도구는 `TargetSkeleton=nullptr`, info 에 `NO_SKELETON` 경고 — 인터페이스에선 정상).
- **레이어 = UAnimationGraph 함수 그래프**: 에디터 "Animation Layer" 추가 = `CreateNewGraph(BP, Name, UAnimationGraph, UAnimationGraphSchema)` + `AddDomainSpecificGraph`(BlueprintEditor.cpp:9714-9719 → BlueprintEditorUtils.cpp:2418-2430: `CreateDefaultNodesForGraph`(Root) + `FunctionGraphs.Add` + 구조 변경). 그룹 = `UAnimGraphNode_Root::Node.SetGroup`(기본 `FAnimNode_Root::DefaultSharedGroup` = "DefaultSharedGroup", AnimNode_Root.cpp:13). 입력 포즈 = 레이어 그래프 안의 `UAnimGraphNode_LinkedInputPose`(디테일 패널 "Add Input Pose" = `SpawnNode<UAnimGraphNode_LinkedInputPose>`, AnimGraphDetails.cpp:285-304; `IsCompatibleWithGraph` 가 AnimGraph 만 허용하는 것은 팔레트 제한이고 프로그램 생성은 `FGraphNodeCreator` 로 가능). 이름은 `Node.Name`(PostPlacedNewNode 가 "InPose" 기본 이름을 주므로 Finalize 뒤 덮어쓰고 ReconstructNode).
- **컴파일**: 레이어마다 스텁 함수 그래프가 만들어지고 생성 클래스 함수에 `MD_AnimBlueprintFunction` 메타가 붙는다(AnimBlueprintCompiler.cpp:1570-1725, :1761/:1791). 입력 포즈는 함수의 포즈 파라미터, 그룹은 함수 Category. **구현 단계는 이 메타를 보므로 인터페이스를 먼저 컴파일**해야 한다(도구는 생성 Tool 안에서 항상 컴파일).
- **구현**: `FBlueprintEditorUtils::ImplementNewInterface(ABP, 클래스 경로)`(BlueprintEditorUtils.cpp:6414-6510) — anim 함수마다 `CreateNewGraph(UAnimationGraph)` + `InterfaceGuid` + `AddInterfaceGraph` → `UAnimationGraphSchema::CreateFunctionGraphTerminators`(AnimationGraphSchema.cpp:423-482) 가 **Root + 입력 포즈 노드를 함수 시그니처에서 자동 생성**(FunctionReference 외부 멤버, 읽기 전용) 하고 그룹을 전파. 그래프는 `ImplementedInterfaces[].Graphs` 에만 있다(`FunctionGraphs` 아님). 이후 구조 변경 때 `ConformAnimGraphToInterface`(:1117) 가 입력 포즈를 동기화.
- **노드**: `SetupFromLayerId`(AnimGraphNode_LinkedAnimLayer.cpp:974-1006) = `Node.Layer` · `FunctionReference.SetSelfMember` · `Node.Interface = GetInterfaceForLayer()`(그 이름의 인터페이스 그래프 소유 인터페이스, 없으면 self) · `InterfaceGuid = 그래프 InterfaceGuid` · self 면 `InstanceClass=null` → 핀은 `CreateCustomPins`(:676) 가 스켈레톤 클래스의 `FAnimBlueprintFunction.InputPropertyData` 로 만든다. `SetupFromLayerId`·`SetLayerName`·`GetLayerName` 은 MinimalAPI 클래스의 비내보내기/protected 라 호출 불가, `FunctionReference` 는 protected(AnimGraphNode_LinkedAnimGraphBase.h:96-98) → **리플렉션으로 재현**(`Node.Layer/Interface/InstanceClass`·`InterfaceGuid` 는 공개 UPROPERTY).

| 산출물 | 위치 |
| :--- | :--- |
| 레이어 기계 | `Core/AnimMcpAnimLayer.{h,cpp}` (신규) — `ParseCreateInterfaceParams`(이름 검증 `FName::IsValidXName`·중복·`AnimGraph` 예약) · `CreateLayerInterface`(보호/overwrite → CreateBlueprint(UAnimLayerInterface, BPTYPE_Interface) → 레이어 그래프 + 그룹 + 입력 포즈 → MarkStructurallyModified → AssetCreated) · `ValidateLayerInterface`(BPTYPE_Interface·부모·생성 클래스·anim 함수 ≥1) · `ImplementInterface`(이미 구현·그래프 이름 충돌·대상이 인터페이스 거부 → `ImplementNewInterface`) · `FindLayerGraph`/`ValidateLayerName`/`ValidateLayerAssignable` · `SetLinkedLayer`/`RestoreLinkedLayer` · `DescribeImplementedInterfaces`/`DescribeLayers`/`DescribeLinkedLayerNode` |
| Tool 2개 | `Tools/AnimMcpTools_Layers.cpp` (신규) — `create_anim_layer_interface {asset_path, layers[{name, group?, input_poses?}], overwrite?, save?}` → info + `layers` + `compile`(항상) + `created` · `implement_anim_layer_interface {asset_path, interface, compile?=true, save?}` → info + `implemented_interfaces` + `layers` + `compile` + `implemented` |
| op | `add_node {class:"AnimGraphNode_LinkedAnimLayer", layer}` (다른 클래스에 `layer` 는 BAD_REQUEST; 응답 `linked_layer{}`) · `set_linked_layer {node\|ref, layer}` (응답 `old_layer`; 되돌리기 = 이전 레이어 참조 복원) — op 19종 |
| Inspector | `CollectGraphs` 가 `ImplementedInterfaces[].Graphs` 를 포함 · `graphs[].interface_guid` · `FindRootAnimGraph` 가 인터페이스 BP 에선 null(레이어를 루트로 오인하지 않게) · info `implemented_interfaces[{interface, blueprint, graphs[]}]` · `layers[{name, graph_guid, interface\|null, interface_guid, group, input_poses[]}]` · 노드 `linked_layer{layer, interface, instance_class, interface_guid}` |
| 테스트 | `Tools/mcp/phase6_4b_test.py` — A 인터페이스 생성(레이어 3, 그룹·입력 포즈, 컴파일) · B 구현(그래프 3 자동, 입력 포즈·그룹 전파) · C AnimGraph 에 레이어 노드 2 + 연결 컴파일 0 에러 · D 구현 그래프 채우기(SequencePlayer→Root · InPose→Root 통과) · E 공급자 ABP(같은 인터페이스 구현 — Lyra `ABP_ItemAnimLayersBase` 패턴) · F set_linked_layer(PINS_LINKED → 링크 해제 → 재지정·복귀·롤백·같은 배치 ref) · G 거부 14종 · H 저장 · `--recheck`. 테스트 애셋 `ALI_McpTest`·`ABP_McpLayerBase`·`ABP_McpLayerProvider` |

**실측으로 바로잡은 것 2건 (컴파일 규칙)**
- **"layers can be used only once in an animation blueprint"** — 같은 ABP 안에서 한 레이어를 두 LinkedAnimLayer 노드가 쓰면 컴파일 오류. `ValidateLayerAssignable` 이 다른 노드의 사용을 선검사(`LAYER_IN_USE`, `add_node layer`·`set_linked_layer` 공통).
- **"In use pin 'In Pose' no longer exists on node"** — 입력 포즈 핀이 링크된 채 레이어를 바꾸면 사라진 핀이 고아로 남아 컴파일 오류(에디터 UI 도 같은 상태를 만든다). `set_linked_layer` 는 입력 포즈 핀에 링크가 있으면 `PINS_LINKED` 로 거부 — 먼저 `disconnect`.
- 적용 중 실패의 `reason` 은 `details.cause`(실패 op 의 details) 와 `details.applied[i].error` 에, 사전 검증 실패는 `details.planned[i].error` 에 있다 — 테스트 헬퍼가 셋을 다 본다.

**Phase 6-5 착수 조건**: 본 결과 검토. 범위는 핸드오프 §12 "6-5 검증 자동화" — `run_automation_tests` Tool · AnimBP 런타임 스모크 Automation 테스트 · 통합 러너 `Tools/mcp/run_all.py`.

---

## Phase 6-5 결과 (2026-10-17, 브랜치 `feat/ai_auto_ABP`) — 검증 자동화

**사용자 확정 설계 (2026-10-17)**: `FAutomationTestFramework` 직접 구동(`run_automation_tests` 가 잡을 시작하고 FTSTicker 로 진행, 동기 완료면 응답에 결과, 아니면 `poll_automation_tests`) · 스모크 테스트는 플러그인 안(`AnimGraphMcp.Smoke.AnimBlueprint`, ini 경로 아래 ABP 전부 — 컴파일·빈 상태·끊긴 캐시·빈 레이어) · `run_all.py` 통합 러너. `phase6_5_test.py` 5개 절 **PASS**, `run_all.py` 로 단계 9개 + 재시작 `--recheck` 7개 **ALL PASS**(결과 `Tools/mcp/results/`). Development · DebugGame 빌드 성공, 경고 0. Tool 15 → **17개** (세션 재시작 전에는 HTTP 로만 검증됨).

**엔진 경로 (소스로 확인, `Runtime/Core/Public/Misc/AutomationTest.h` · `Runtime/Core/Private/Misc/AutomationTest.cpp`)**
- **목록**: `FAutomationTestFramework::Get()` → `SetRequestedTestFilter(EAutomationTestFlags_FilterMask)`(필터를 안 열면 ProductFilter 테스트가 빠진다) → `LoadTestModules()` → `GetValidTestNames(TArray<FAutomationTestInfo>&)`. `FAutomationTestInfo` 의 `GetDisplayName`(전체 경로 `A.B.C`)·`GetTestName`(명령 = complex 테스트의 파라미터)·`GetSourceFile/GetSourceFileLine`. 도구 필터 = 전체 경로의 접두 또는 부분 문자열(대소문자 무시), 정렬.
- **실행**: `StartTestByName(Command, RoleIndex=0, FullTestPath)` — 내부에서 `GIsSlowTask`/PIE 면 시작하지 않는다(`GIsAutomationTesting` 이 세워졌는지로 판정 → `not_started`). 이후 프레임마다 `ExecuteNetworkCommands()` 와 `ExecuteLatentCommands()` 를 부르고 둘 다 true(큐 비움)가 되면 `StopTest(FAutomationTestExecutionInfo&)` 로 수집: `bSuccessful` · `Duration` · `GetEntries()` 의 `FAutomationExecutionEntry{Event{Type, Message, Context}, Filename, LineNumber}` (Error/Warning 분리). 테스트별 타임아웃은 `DequeueAllCommands()` 뒤 `StopTest` + state `timeout`. 완료 델리게이트는 쓰지 않는다(❓ 해소 — 지연 명령 큐가 비는 것이 완료 조건).
- **동기/비동기**: 잡은 `StartJob` 에서 한 번 `Advance` 하고, 지연 명령 없이 전부 끝나면 응답에 결과(`done=true`). 남으면 `FTSTicker` "AnimGraphMcp.AutomationJob" 이 프레임마다 `Advance`. 잡은 한 번에 하나(다른 잡 진행 중·`GIsAutomationTesting` 이면 BAD_REQUEST), 최근 16개 보관 → `poll_automation_tests {job_id}`.
- **스모크 테스트**: `IMPLEMENT_COMPLEX_AUTOMATION_TEST(..., "AnimGraphMcp.Smoke.AnimBlueprint", EditorContext | ProductFilter)` — `GetTests` 가 AssetRegistry(`FARFilter` UAnimBlueprint 재귀, `[AnimGraphMcp] SmokeTestPaths`, 기본 `/Game/Animation`)로 ABP 를 열거(이름 = 애셋 이름, 명령 = 오브젝트 경로). `RunTest`: `LoadObject` → `FKismetEditorUtilities::CompileBlueprint(BP, SkipGarbageCollection, &FCompilerResultsLog)` 오류 → `AddError` · 인터페이스 BP 는 여기서 끝 · 루트 `UAnimGraphNode_Root` "Result" 미연결 → 오류(**레이어 제공자 — `ImplementedInterfaces` 에 UAnimLayerInterface 파생 + 그래프 — 는 경고**) · 구현 레이어 그래프의 Root 미연결 → 경고 · 모든 그래프의 `UAnimStateNode` BoundGraph 의 `UAnimGraphNode_StateResult` "Result" 미연결 → 오류("빈 상태") · `UAnimGraphNode_UseCachedPose::SaveCachedPoseNode` 무효 → 오류 · `UAnimGraphNode_LinkedAnimLayer` 의 `Node.Layer` 가 `AnimMcpAnimLayer::FindLayerGraph` 로 안 풀리면 → 오류. `AddWarning` 은 실패가 아니다(`bElevateLogWarningsToErrors` 기본 false, AutomationTest.cpp:176).

| 산출물 | 위치 |
| :--- | :--- |
| 구동 기계 | `Core/AnimMcpAutomationRunner.{h,cpp}` (신규) — `FindTests(Filter)` · `StartJob(Filter, Timeout, Error)` · `Advance(Job)`(시작 → 명령 큐 실행 → `FinishCurrent` → 다음) · `FindJob` · `DescribeJob`/`DescribeTestInfo`(JSON) |
| Tool 2개 | `Tools/AnimMcpTools_Automation.cpp` (신규) — `run_automation_tests {filter(필수), timeout=120, dry_run=false}` → `{job_id, filter, total, completed, passed, failed, done, ok, elapsed, running?, tests[{name, state, duration, errors[], warnings[]}]}`(`dry_run` 은 `tests[{name, display_name, command, source_file, source_line}]`, 매칭 0 → 진단 `NO_TESTS`) · `poll_automation_tests {job_id}` |
| 스모크 | `Tests/AnimMcpSmokeTests.cpp` (신규, `WITH_DEV_AUTOMATION_TESTS`) · ini `[AnimGraphMcp] +SmokeTestPaths=/Game/Animation` |
| 러너 | `Tools/mcp/run_all.py` — 기동(`UnrealEditor.exe` 분리 프로세스, 브리지 폴링 600초, 25초 대기) → phase3/4/5/6-1/6-3/6-4/6-4b/6-5/6-2(`--no-quit`) → `quit_editor discard_dirty` + `wait_for_exit` → 재기동 → `--recheck` 5/6-1/6-3/6-4/6-4b/6-2/6-5 → quit → `Tools/mcp/results/<date>.json`(단계별 verdict·초·`[FAIL]` 줄·꼬리) · 종료 코드. `--attach` · `--only` · `--skip-recheck` · `--engine` · `--project` |
| 테스트 | `Tools/mcp/phase6_5_test.py` — A dry_run(ABP 9개: ABP_Hero_Base · ABP_Hero_McpBuild · 테스트 ABP 6 · ALI_McpTest) · B 스모크 전부 passed(동기, 0.3초) + 제공자 경고 · C `AstralBreak.` 18/18 + poll + 부분 필터(`AstralBreak.Targeting` 4) · D 거부 3종 · E 음성(빈 상태 ABP → 그 애셋만 failed, "State 'EmptyState' … is empty" → 삭제 → 다시 전부 passed) · `--recheck` |

**실측으로 바로잡은 것**
- **레이어 제공자 ABP 는 루트 Output Pose 가 비어 있다** — `ABP_McpLayerProvider`(Lyra `ABP_ItemAnimLayersBase` 역)는 인터페이스 구현만 하고 루트 그래프를 쓰지 않으므로 첫 실행에서 "Output Pose not connected" 로 실패했다. `ImplementedInterfaces` 에 UAnimLayerInterface 파생 인터페이스(그래프 포함)가 있으면 경고로 낮춘다. 구현 레이어 그래프가 빈 것도 경고(베이스 ABP 의 기본 구현은 비어 있을 수 있다).
- 러너의 recheck 순서: 6-5 스모크는 6-2 recheck(ABP_McpDup 삭제) 뒤 — 아니면 ABP 가 하나 더 잡힌다(테스트는 `total >= 저장값` 으로 본다).
- **미검증 경로**: 지연(latent) 명령이 있는 테스트의 FTSTicker 진행·타임아웃 — 프로젝트 테스트 18개와 스모크는 전부 동기 완료라 `poll` 은 완료된 잡 재조회만 실측됐다.

**Phase 6-6 착수 조건**: 본 결과 검토 + §12-D(두 번째 프로젝트) 사용자 확정. 범위는 핸드오프 "최종 지시 (Phase 6-6)".

---

## Phase 6-6 결과 (2026-10-17, 브랜치 `feat/ai_auto_ABP`) — 범용화 (축소판)

**사용자 결정 (2026-10-17)**: 두 번째 프로젝트 재현(§12-D)은 생략하고 README 2종만 갱신해 6-6 을 닫는다. 근거: 플러그인 코드에 프로젝트 의존이 없음이 Grep 으로 확인됐고, 재현의 가치는 "다른 프로젝트에서 확인" 이라는 포트폴리오 문구뿐이다.

- **Grep**: `Plugins/AnimGraphMcp` 에서 `AstralBreak`·`/Game/Animation/Hero`·`AstralAnimInstance`·`SKEL_UE5_F`·`IdaFaber` → 코드 0건. 걸린 것은 설명 문자열 4곳(uplugin `CreatedBy`, `run_automation_tests` 설명의 필터 예시, `AnimMcpBlueprintFactory.h`·`AnimMcpAssetProtection.h` 주석 예시)과 `server.py` docstring 예시 4곳 → 전부 범용 예시(`/Game/Characters/Hero/ABP_Hero`, `/Script/MyGame.MyAnimInstance`, `MyGame.`)로 교체. Development · DebugGame 빌드 성공.
- **`Plugins/AnimGraphMcp/README.md` 신설**: 설치(C++ 프로젝트 전제·uproject 등록·빌드) · ini 설정 6키 · 통신 규약(봉투·request_id 캐시·타임아웃) · Tool 17개 표 · op 19종 표 · `set_property` 허용 목록 · 규칙 AST · 안전 장치 · 오류 코드 표 · 스모크 테스트 · 제약 · 소스 구조.
- **`Tools/mcp/README.md` 갱신**: 이식 절차(복사 대상·토큰 위치·`ANIMGRAPH_MCP_PROJECT_DIR`) · `.mcp.json` 본문 · 전형적 작업 흐름 · 플러그인 README 링크.
- **이식 시 알려진 전제**: C++ 프로젝트(에디터 모듈 빌드) · venv 재생성 · ini `[AnimGraphMcp]` 섹션(생략 가능) · `SmokeTestPaths` 기본 `/Game/Animation`. 실제로 다른 프로젝트에 넣을 때 가장 쉬운 재료는 엔진 `Templates/TemplateResources/High/Characters/Content/Mannequins`(`SK_Mannequin`·`ABP_Unarmed` 포함, 약 125MB).

**Phase 6 종료.** 후속 후보는 핸드오프 §12 "Phase 6 이후 후속 후보".

---

## Phase 7-1 결과 (2026-10-17, 브랜치 `feat/ai_auto_ABP`) — BP 변수 · 규칙 AST access/param · set_update_function

**사용자 확정 (2026-10-17)**: 로드맵 §1 을 세 묶음 전부로 — `add/remove_blueprint_variable` Tool · 규칙 AST `access` 잎 · `set_update_function`(BlueprintThreadSafeUpdateAnimation 전체 재생성). 노드 단위 EventGraph 편집 op 는 두지 않는다(규칙 AST 와 같은 화이트리스트 철학). `phase7_1_test.py` 6개 절 **PASS**, `run_all.py` 단계 10 + recheck 8 **ALL PASS**. Development · DebugGame 빌드 성공, 경고 0. Tool 17 → **20개** (세션 재시작 전에는 HTTP 로만 검증됨).

**엔진 경로 (소스로 확인)**
- **BP 변수**: `FBlueprintEditorUtils::AddMemberVariable(BP, 이름, FEdGraphPinType, 기본값 문자열)` (BlueprintEditorUtils.cpp:4645-4703) — `GetClassVariableList` 로 중복 검사 → `NewVariables` 추가(플래그 `CPF_Edit | CPF_BlueprintVisible | CPF_DisableEditOnInstance`) → `MarkBlueprintAsStructurallyModified` 가 스켈레톤 클래스를 재생성. 그래서 `SkeletonGeneratedClass` 에서 해석하는 기존 규칙 `var` · `K2Node_VariableGet` · `bind_pin` 은 **수정 없이** 새 변수를 본다(로드맵이 예상한 해석 경로 추가는 불필요했다). 삭제 `RemoveMemberVariable`(:4706-4719)은 `RemoveVariableNodes` 로 참조 노드까지 지운다 → 도구는 `IsVariableUsed`(:5926)로 선거부, `force` 면 진단과 함께 허용. 이름 검증은 에디터와 같은 `FKismetNameValidator`(Kismet2NameValidators.h:83-94, 결과 enum :24-40). 카테고리 `SetBlueprintVariableCategory`(bDontRecompile).
- **ThreadSafeUpdateAnimation 오버라이드 = 함수 그래프**: `BlueprintThreadSafe` 메타가 붙은 `BlueprintImplementableEvent`(AnimInstance.h:566-567)는 Persona 가 이벤트가 아니라 함수 그래프로 구현한다 — `IsFunctionConvertableToEvent` 가 `HasFunctionBlueprintThreadSafeMetaData` 면 false(BlueprintEditorUtils.cpp:2242) → `CreateNewGraph(BP, 이름, UEdGraph, UEdGraphSchema_K2)` + `AddFunctionGraph<UClass>(BP, Graph, false, 선언 클래스)`(SMyBlueprint.cpp:2874-2878; 템플릿은 BlueprintEditorUtils.h:343-399 — `CreateFunctionGraphTerminators(Graph, UClass*)` 가 그래프 이름으로 함수를 찾아 Entry 를 만든다). 선언 클래스는 `GetOverrideFunctionClass`. Entry 의 출력 핀 = 파라미터(`DeltaTime`) + `then`. 컴파일러는 함수 안 호출의 스레드 안전성을 검사해 아니면 경고 + `bUseMultiThreadedAnimationUpdate=false`(AnimBlueprintCompiler.cpp:1084-1151) — 테스트는 경고 0 으로 이를 확인.
- **Property Access 노드**: `UK2Node_PropertyAccess` 는 엔진 플러그인 `Engine/Plugins/Developer/PropertyAccessNode`(uplugin EnabledByDefault, 모듈 UncookedOnly·PreDefault)의 **비공개 헤더**(Private/K2Node_PropertyAccess.h, MinimalAPI) → 포함·`SetPath` 호출 불가. 클래스는 `/Script/PropertyAccessNode.K2Node_PropertyAccess` 로 찾고, `UPROPERTY TArray<FString> Path`(:63) 를 `FArrayProperty`/`FScriptArrayHelper` 로 쓴 뒤 `FGraphNodeCreator::Finalize` 의 `AllocateDefaultPins → AllocatePins`(K2Node_PropertyAccess.cpp:170-217) 가 `IPropertyAccessEditor::ResolvePropertyAccess` 로 경로를 해석해 `ConvertPropertyToPinType` 타입의 `Value` 출력 핀과 `TextPath` 를 만든다(미해석이면 와일드카드 → 도구는 노드를 지우고 `PATH_UNRESOLVED`). 그래프 허용은 `IsCompatibleWithGraph`(:278-296) → `IPropertyAccessBlueprintBinding::CanBindToContext` → AnimGraph 구현은 **AnimBP 의 모든 그래프 허용**(PropertyAccessAnimBlueprintBinding.cpp:22-30) — ❓ 해소. 경로 해석은 6-4a 와 같은 `IPropertyAccessEditor`(SkeletonGeneratedClass 기준; `FPropertyAccessResolveResult.bIsThreadSafe` :332-338).
- **VariableSet**: `UK2Node_VariableSet` + `SetFromProperty(Property, true, VarClass)`; 핀 = `execute`·`then`(K2Node_VariableSet.cpp:101-102) + 변수 이름 입력 + `Output_Get` 출력(:400-402). exec 사슬은 스키마 `TryCreateConnection`.

| 산출물 | 위치 |
| :--- | :--- |
| Property Access 헬퍼 | `Core/AnimMcpPropertyAccessNode.{h,cpp}` (신규) — `NodeClass` · `ParsePath`("A.B" / 배열) · `ResolvePath`(잎·스레드 안전·함수 여부) · `GetPath`/`SetPath`(리플렉션) · `Spawn` |
| 변수 기계 | `Core/AnimMcpVariables.{h,cpp}` (신규) — `ParsePinType`(type 문자열 → FEdGraphPinType, `object:`·`class:`·`struct:`·`enum:` 경로) · `PinTypeToText` · `AddVariable` · `RemoveVariable` · `DescribeDeclaration` · `AppendRevisionLines`(`BV|이름|타입|기본값`, NewVariables 있을 때만 → 기존 revision 호환) |
| 업데이트 함수 | `Core/AnimMcpUpdateFunction.{h,cpp}` (신규) — `FindGraph` · `ParseAndValidate`(assignments → 변수 해석·READ_ONLY·DUPLICATE·식 검증·타입 호환) · `Apply`(FScopedTransaction: 그래프 생성(없으면) → 멱등 검사(마커 `AnimGraphMcp update_source v1`) → Entry 외 노드 분리 보관 + 링크 스냅샷 → Set 사슬 + 식 트리 → 전체를 Entry 오른쪽으로 이동 → 주석 → 실패 시 복구+Cancel) · `Remove` · `Describe` |
| 식 엔진 확장 | `Core/AnimMcpTransitionRule` — `ECat::Other`(벡터·구조체·오브젝트: 비교 불가, call 인자·대입엔 흐름) · `FExpr.Type` · `access`/`param` 잎 · 공개 `FExpressionParams`/`ValidateExpression`/`LiteralForPin`/`FExpressionBuild`/`BuildExpressionInto` · `HashRuleGraph` 제목에 VariableSet·FunctionEntry·access 경로 · `ReadSource(Graph, Marker)` |
| Tool 3개 | `Tools/AnimMcpTools_Variables.cpp` (신규) — `add_blueprint_variable {asset_path, name, type, default?, category?, instance_editable?, compile?, save?}` · `remove_blueprint_variable {asset_path, name, force?, compile?, save?}` · `set_update_function {asset_path, assignments[] \| remove, compile?=true, save?}` |
| Inspector | `variables[].declaration{type, default_value, category, instance_editable}`(BP 변수만) · `update_function{graph_guid, function, generated, source, modified, node_count, assignments[]}` · revision `BV|` 줄 |
| 테스트 | `Tools/mcp/phase7_1_test.py` — A 변수 6종 · B 거부 10종 · C access 경로 후보 탐색 + 규칙 · D 업데이트 함수(대입 4 · 멱등 · 축소 · 거부 7종) · E 삭제 · F 저장 · `--recheck`. 테스트 애셋 `ABP_McpVarTest` |

**실측으로 바로잡은 것 · 확인한 것**
- **이 프로젝트의 벡터 Property Access 경로**: `UAstralAnimInstance` 에 BlueprintVisible 폰 참조가 없고 `TryGetPawnOwner`·`GetOwningActor` 는 BlueprintCallable(비 pure)이라 경로 해석 밖이다. 첫 후보 `GetOwningComponent.ComponentVelocity` 가 해석됐고(테스트는 후보 목록을 순서대로 preview 로 탐색), 규칙과 업데이트 함수 모두 **컴파일 0 에러 0 경고**(스레드 안전 판정 통과).
- 배치 사전 검증 실패의 **상세 메시지**는 `details.planned[i].error.message` 에 있다(바깥 message 는 "One or more operations failed validation") — 테스트 헬퍼 `msg()` 가 planned/applied/cause 를 본다.
- `MakeShared<FJsonValueObject>` 와 `MakeShared<FJsonValueNull>` 을 삼항식에 섞으면 `TSharedRef` 타입이 달라 컴파일 오류 — `TSharedPtr<FJsonValue>` 로 먼저 승격한다.
- `remove_blueprint_variable force` 뒤 생성된 업데이트 함수는 Set 노드가 사라져 `modified=true` 가 된다 — 다시 `set_update_function` 으로 재생성(테스트 E).
- 미검증: `object:`·`struct:`·`enum:` 변수의 기본값 ImportText(테스트는 기본값 없이 추가만) · `param` 이 `DeltaTime` 외 파라미터(현재 시그니처엔 하나뿐).

**다음**: 로드맵 §2(허용 목록 확장) 또는 §3(몽타주 슬롯/섹션·스켈레톤 슬롯·AimOffset). 핸드오프 "최종 지시 (Phase 7 후속)".

---

## Phase 7-2 결과 (2026-10-17, 브랜치 `feat/ai_auto_ABP`) — set_property 허용 목록 확장

**사용자 확정 (2026-10-17)**: 로드맵 §2 를 제안 범위 그대로 — 노드 10종 허용 목록 + 오브젝트 참조 값 + 본 이름/스켈레톤 검증. `phase7_2_test.py` 5개 절 **PASS**, `run_all.py` 단계 11 + recheck 9 **ALL PASS**. Development · DebugGame 빌드 성공, 경고 0. Tool 추가 없음(Tool 20개 유지, MCP 재시작 불필요).

**엔진 경로 (소스로 확인)** — 프로퍼티 이름·타입은 전부 헤더에서: `AnimNodes/AnimNode_RotationOffsetBlendSpace.h`(:27-52), `AnimNode_BlendSpacePlayer.h`(FAnimNode_BlendSpacePlayerBase :137-180 — X/Y/PlayRate/bLoop/StartPosition/싱크 그룹이 베이스에 있어 AimOffset 이 상속), `AnimNode_SequenceEvaluator.h`(:113-160), `Animation/AnimNode_SequencePlayer.h`(:94-107, :145), `AnimNodes/AnimNode_ApplyAdditive.h`(:22-52), `BoneControllers/AnimNode_SkeletalControlBase.h`(:35-61 — Alpha 묶음은 베이스), `AnimNode_TwoBoneIK.h`(:25-100), `AnimNode_ModifyBone.h`(:36-73), `AnimNodes/AnimNode_Mirror.h`(:125-145), `Animation/AnimNode_Inertialization.h`(:318-348), `AnimNodes/AnimNode_BlendListBase.h`(:50-69), `AnimNodes/AnimNode_LayeredBoneBlend.h`(:42-43, :97-110). 구조체: `Animation/InputScaleBias.h`(FInputScaleBias :14-22 · FInputScaleBiasClamp :73-110 · FInputAlphaBoolBlend :285-307 — `CustomCurve` 오브젝트 포함), `Public/Animation/BoneSocketReference.h`(FBoneSocketTarget :93-104 {bUseSocket, BoneReference, SocketReference}), `Public/BoneContainer.h`(FBoneReference). 블렌드 프로파일: `Animation/BlendProfile.h`(`GetSkeleton` :174 · `IsBlendMask` :266 · `GetMode` :268), 스켈레톤 소유 목록 `Animation/Skeleton.h:527`(`BlendProfiles`). `UMirrorDataTable::Skeleton`(MirrorDataTable.h:213-214)은 리플렉션으로 읽는다.

| 산출물 | 위치 |
| :--- | :--- |
| 허용 표 | `Core/AnimMcpPropertyRules.cpp` — 공통 조상에 규칙을 두는 상속 활용(`AnimGraphNode_BlendSpaceBase`, `AnimGraphNode_SkeletalControlBase`) · 노드 10종 추가 |
| 오브젝트 참조 | `AnimMcpPropertyRules::ResolveObjectValue`(경로 → FindObject/LoadObject, "/Game/A/B" 는 ".B" 를 붙여 먼저 — 아니면 UPackage 가 잡힌다 · PropertyClass 검사 → `Class'Path'`) · `JsonToImportText` 가 object 에 `null` → `None` 허용 · `PropertyToJson` 은 오브젝트 경로 문자열/null |
| 값 트리 검증 | `AnimMcpGraphMutator::ValidatePropertyValueOnNode` — LayerSetup(기존) · BlendMasks(모드·포즈 수·마스크 여부) · 재귀 `ValidateValueTree`(FBoneReference.BoneName ∈ TargetSkeleton · 오브젝트의 소유 스켈레톤 일치). `SetPropertyFromJson` 과 Operations 사전 검증(노드가 있을 때) 양쪽에서 호출 |
| Inspector | `get_anim_blueprint_info.skeleton_blend_profiles[{name, path, mode, is_blend_mask}]` |
| 테스트 | `Tools/mcp/phase7_2_test.py` — A 노드 13종 생성 + 컴포넌트 공간 체인 컴파일 0 에러 · B 43개 설정 → 컴파일 0 에러 0 경고 → 재조회 일치(본·enum·벡터·로테이터·중첩 구조체·배열·오브젝트·null) · 노출 핀 Alpha 동기화 · C 거부 13종(BONE_NOT_FOUND ×3 · OBJECT_NOT_FOUND · OBJECT_CLASS_MISMATCH ×2 · COUNT_MISMATCH · BAD_BLEND_MODE · enum · PROPERTY_NOT_ALLOWED · null · 구조체에 문자열) · D 혼합 배치 사전 검증 롤백 · E 저장 · `--recheck`. 테스트 애셋 `ABP_McpPropTest` |

**실측으로 바로잡은 것 · 확인한 것**
- **Mirror 노드는 MirrorDataTable 없이 루트에 연결되면 컴파일 오류**("does not have a mirror data table selected"). 비연결 노드는 컴파일에서 잘리므로 테스트는 Mirror 를 비연결로 두고 설정만 검증했다. 프로젝트에 MirrorDataTable 애셋이 없다.
- **"/Game/A/B" 경로는 `FindObject` 에서 UPackage 로 풀린다** → `.B` 를 붙인 오브젝트 경로를 먼저 보고, 결과가 UPackage 면 실패로 본다. 조회는 항상 오브젝트 경로(`/Game/A/B.B`)를 돌려준다.
- `ComponentToLocalSpace` 의 출력 핀 이름은 `Pose`(입력 `ComponentPose`), `LocalToComponentSpace` 는 `LocalPose` → `ComponentPose`. 컴포넌트 공간 노드(TwoBoneIK·ModifyBone)는 이 둘로 감싸면 Root 까지 컴파일된다.
- 사전 검증은 같은 배치의 앞선 op 를 모른다(6-4a 와 같은 성질) → `BlendMode = BlendMask` 와 `BlendMasks` 는 두 배치. 반대로 "BranchFilter 로 바꾼 뒤 BlendMasks" 는 사전 검증을 통과하고 적용 중 `BAD_BLEND_MODE` 로 롤백된다.
- 배치 사전 검증 실패의 op 별 오류 **코드**(`PROPERTY_NOT_ALLOWED`)는 `details.planned[i].error.code` 에 있다 — 테스트 헬퍼 `code()` 가 planned/applied 를 먼저 본다.
- `SKEL_UE5_F` 에는 블렌드 프로파일이 없어(`skeleton_blend_profiles: []`) BlendProfile/BlendMasks 의 양성 경로와 다른 스켈레톤 애셋의 `SKELETON_MISMATCH` 는 **미검증**(거부 경로와 `[null]` 마스크만 실측). 프로파일이 있는 프로젝트에서 같은 테스트가 자동으로 양성 경로를 돈다.

**다음**: 로드맵 §3(몽타주 슬롯/섹션 · 스켈레톤 슬롯 · AimOffset 생성) 또는 §4/§5. 핸드오프 "최종 지시 (Phase 7 후속)".

---

## Phase 7-3 결과 (2026-10-17, 브랜치 `feat/ai_auto_ABP`) — 몽타주 슬롯·섹션 · 최소형 몽타주 생성 · 스켈레톤 슬롯 · AimOffset

**사용자 확정 (2026-10-17, 4건)**: ① 몽타주 생성은 **최소형 `create_anim_montage` 추가**(시퀀스 1개 → 몽타주; 노티파이는 계속 Python `ab_montage.py`) ② AimOffset 은 **`create_blendspace` 의 `aim_offset` 플래그**(새 Tool 없음) ③ `set_montage_slots` 는 스켈레톤에 없는 슬롯을 **거부**(SLOT_NOT_IN_SKELETON; 등록은 `add_skeleton_slot {confirm:true}` 만) ④ 몽타주 스모크 테스트 **추가**. `phase7_3_test.py` 6개 절 **PASS**, `run_all.py` 단계 12 **전부 PASS** + recheck 10 — 첫 실행(`results/20261017-203936.json`)에서 7-3 recheck 만 실패했는데 원인은 테스트 비교 버그(state 파일의 JSON 왕복이 튜플을 리스트로 바꿈 → `jsonic()` 정규화로 수정), 수정 뒤 재기동 recheck **PASS**(에디터 재시작 뒤 몽타주·AimOffset 요약 동일, 임시 슬롯 사라짐, 스모크 6/6). Development · DebugGame 빌드 성공, 경고 0. Tool 20 → **24개** (세션 재시작 전에는 HTTP 로만 검증됨).

**엔진 경로 (소스로 확인)**
- **몽타주 생성**: `UAnimMontageFactory::FactoryCreateNew`(AnimMontageFactory.cpp:72-104) 재현 — `NewObject<UAnimMontage>`(생성자가 DefaultSlot 트랙 1개를 만든다, AnimMontage.cpp:77) → `FAnimSegment::SetAnimReference(Seq, true)` → `SlotAnimTracks[0].AnimTrack.AnimSegments.Add` → `SetCompositeLength(Seq->GetPlayLength())` → `UpdateCommonTargetFrameRate`(**UAnimMontage 가 private 으로 내린 오버라이드**, AnimMontage.h:994 → 베이스 `UAnimCompositeBase` 포인터로 호출, AnimCompositeBase.h:344) → `SetSkeleton` → 시작 섹션 `AddAnimCompositeSection("Default", 0)`(EnsureStartingSection :116-136 과 동치) → `BlendIn/Out.SetBlendTime`(AlphaBlend.h:100) → `PostEditChange`. 팩토리 객체는 `ConfigureProperties` 가 피커 창을 띄우므로 쓰지 않는다.
- **슬롯 이름**: `SlotAnimTracks[i].SlotName` 직접 대입 + `Modify`/`PostEditChange`(Persona `SAnimMontagePanel::RenameSlotNode`, SAnimMontagePanel.cpp:470-486). Persona 는 `RegisterSlotNode` 로 스켈레톤에 자동 등록하지만(:478) 도구는 거부한다(확정 ③). 노티파이·섹션은 `FAnimLinkableElement::SlotIndex`(AnimLinkableElement.cpp:354-375)로 링크되므로 이름 변경에 영향 없음.
- **섹션**: `AddAnimCompositeSection(이름, 시작)`(AnimMontage.cpp:325-365 — 이름 중복이면 INDEX_NONE, **앞 섹션의 빈 NextSectionName 을 자동으로 채운다** :353-362 → 도구가 스펙으로 덮어쓴다) · `NextSectionName` 직접 대입(SAnimMontageSectionsPanel.cpp:548-560 SetNextSectionIndex · :574-588 RemoveLink) · 삭제는 `CompositeSections.RemoveAt` + 참조 Next 정리(SAnimMontagePanel.cpp:434-459) → 도구는 **전체 교체**(비우고 정렬 순서로 재추가). `FCompositeSection::GetTime()` 이 시작 시간, `GetSectionLength(i)`.
- **스켈레톤 슬롯**: `USkeleton::ContainsSlotName` · `AddSlotGroupName`(없으면 생성, :1625-1638) · `SetSlotGroupName`(그룹 없으면 생성, 다른 그룹에 있으면 이동, :1592-1623) · `GetSlotGroups()`(Skeleton.cpp:1575-1650). 슬롯·그룹은 같은 이름 공간(Persona SSkeletonSlotNames.cpp:453 `!ContainsSlotName(NewGroupName)`) → `SLOT_IS_GROUP`/`GROUP_IS_SLOT`. `DefaultSlot`(`FAnimSlotGroup::DefaultSlotName`, Skeleton.cpp:62)은 항상 유효로 본다.
- **AimOffset**: `UAimOffsetBlendSpaceFactoryNew/1D::FactoryCreateNew`(EditorFactories.cpp:7461-7477, :7489-7505)는 BlendSpace 팩토리와 **클래스만** 다르다 → 6-3 `CreateBlendSpace` 에 클래스 선택만 추가. 샘플 조건 `IsValidAdditiveType == AAT_RotationOffsetMeshSpace`(AimOffsetBlendSpace.cpp:16-24) → 사전 검증 `ADDITIVE_TYPE`. `UAimOffsetBlendSpace` 는 MinimalAPI 지만 `StaticClass()`·`IsA` 는 쓸 수 있다.

| 산출물 | 위치 |
| :--- | :--- |
| 몽타주·스켈레톤 기계 | `Core/AnimMcpMontage.{h,cpp}` (신규) — `ParseCreateParams`/`CreateMontage` · `ParseSlotSpecs`/`SetSlots`(전부 검증 뒤 적용, 바뀐 트랙 수) · `ParseSectionSpecs`/`SetSections`(전체 교체 · 멱등 · 실패 시 백업 복원) · `AddSkeletonSlot` · `SkeletonHasSlot` · `SlotGroupsArray` · `DescribeMontage` · `SaveAsset` |
| Tool 4개 | `Tools/AnimMcpTools_Montage.cpp` (신규) — `create_anim_montage {asset_path, animation, slot?, blend_in?, blend_out?, preview_mesh?, overwrite?, save?}` · `set_montage_slots {asset_path, slots[{index?, slot} \| "name"], save?}` · `set_montage_sections {asset_path, sections[{name, start, next?}], save?}` · `add_skeleton_slot {skeleton, slot, group?, confirm, save?}` |
| AimOffset | `Core/AnimMcpBlendSpaceFactory` — `FCreateParams.bAimOffset` · 클래스 선택 · 사전 검증 `ADDITIVE_INVALID`(아래 실측)·`ADDITIVE_TYPE` · `DescribeBlendSpace.aim_offset` · 실패 경로를 임시 패키지 이동으로 수정 |
| 조회 | `list_animation_assets details` 가 AnimMontage → `montage{}`(DescribeMontage), AnimSequence → `additive_type`·`additive_valid`·`ref_pose_type`·`ref_pose_sequence`·`length`; `get_anim_blueprint_info.skeleton_slot_groups[{group, slots[]}]` |
| 스모크 | `Tests/AnimMcpSmokeTests.cpp` — `AnimGraphMcp.Smoke.AnimMontage`(SmokeTestPaths 아래 몽타주마다: 슬롯 미등록(오류) · 빈 트랙(경고) · 섹션 없음/범위 밖/Next 미존재(오류) · 0 미시작(경고) · 호환 스켈레톤 ABP 에 Slot 노드 없음(경고)). ABP 목록 수집은 `ListSmokeAssets` 로 공용화 |
| 테스트 | `Tools/mcp/phase7_3_test.py` — A 스켈레톤 슬롯(UpperBody 멱등 · 임시 슬롯/그룹 생성·이동 · 거부 6종) · B 생성(거부 6종) · C 슬롯(양방향 · 축약형 · 멱등 · 거부 5종) · D 섹션(체인+루프 · 멱등 · 정렬 · 거부 6종 · NO_SECTION_AT_ZERO) · E 저장·list details·스모크(미사용 슬롯 경고) · F AimOffset(2D 8샘플 · 1D 빈 · ADDITIVE_INVALID · ADDITIVE_TYPE) · `--recheck`(임시 슬롯 사라짐 · UpperBody 유지 · 요약 동일 · 스모크). 테스트 애셋 `AM_McpTest` · `AO_McpTest` · `AO_McpTest1D`. `run_all.py` PHASES 는 7-2 뒤·6-5 앞, RECHECKS 도 같은 자리 |

**실측으로 바로잡은 것 · 확인한 것**
- **프로젝트에 같은 이름의 스켈레톤이 둘 있다**: `/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F`(ABP_Hero_Base · AS_Hero_Finisher1 · AS_Hero_Jump · AM_Attack0 · AM_Hero_Finisher1)와 `/Game/IdaFaber/Meshes/Girl/SKEL_UE5_F`(AS_Hero_Attack1~3 · AO_Rifle 9종 · 로코모션 대부분 · **AM_Hero_Attack1~3**). 몽타주는 소스 시퀀스의 스켈레톤을 따르므로 테스트 소스를 `AS_Hero_Finisher1` 로 바꿨고, AimOffset 은 `/Game/IdaFaber` 쪽 스켈레톤으로 만든다. 두 스켈레톤은 `IsCompatibleForEditor` 가 아니어서 몽타주 스모크가 `AM_Hero_Attack1~3` 에 "DefaultSlot Slot 노드 없음" **경고**를 낸다(오류 아님) — 콘텐츠 정리 대상.
- **기준 포즈 없는 additive 시퀀스는 엔진이 그 다음 샘플부터 거부한다**: `AS_Hero_AO_RifleCC` 가 `ABPT_AnimFrame` 인데 `RefPoseSeq` 가 비어 `IsValidAdditive()` false(AnimSequence.cpp:2615-2637). `AddSample` 은 새 샘플이 아니라 **기존 샘플**의 `IsValidAdditive` 를 본다(`ContainsMatchingSamples`, BlendSpace.cpp:2253-2268)라 CC 자신은 들어가고 6번째가 ENGINE_REJECTED 로 떨어졌다 → 사전 검증 `ADDITIVE_INVALID`(RefPoseType·RefPoseSeq 를 메시지에) 추가, `list_animation_assets details` 에 `additive_valid` 노출. AimOffset 테스트는 유효 8샘플로 만든다. **AS_Hero_AO_RifleCC 는 Additive Settings 의 기준 포즈를 지정해야 한다**(콘텐츠).
- **6-3 실패 경로의 잠복 결함**: `AddSample` 거부 뒤 `MarkAsGarbage` 만 하면 GC 전까지 `AssetExists` 가 참이라 다음 `create_blendspace overwrite` 의 `DeleteAsset` 이 실패했다 → 거부된 애셋을 임시 패키지로 `Rename` 한 뒤 버린다(Stale 처리와 같은 방식).
- `UAnimMontage::UpdateCommonTargetFrameRate` 는 private 오버라이드 → 베이스 포인터로 호출(위). `PostEditChangeProperty` 도 같은 것을 부른다(AnimMontage.cpp:802).
- 같은 에디터에서 테스트를 두 번 돌리면 저장하지 않은 임시 스켈레톤 슬롯이 메모리에 남는다 → 테스트는 시작 상태 기준으로 `added`/`group_created` 를 기대한다.
- 미검증: 다중 트랙 몽타주의 `DUPLICATE_SLOT`(테스트 몽타주는 트랙 1개 — 로직은 전체 이름 비교) · 보호 스켈레톤 편집(보호 목록은 파괴 연산 전용이라 `add_skeleton_slot` 은 `/Game/Assets/` 스켈레톤도 편집한다 — 의도) · 섹션 변경 뒤 브랜칭 포인트 트리거 오프셋 재계산은 `PostEditChange → RefreshCacheData` 에 맡김(코드 경로 확인, 실측 없음).

**다음**: 로드맵 §4(Linked Layer 값 파라미터·InstanceClass·인터페이스 레이어 추가/삭제) → §5(PIE 런타임 검증). 운영 적용 후보(사용자 승인 배치): `AM_Hero_Attack1~3`·`Finisher1` 슬롯을 `UpperBody` 로(`set_montage_slots`), 콤보 섹션(`set_montage_sections`). 핸드오프 "최종 지시 (Phase 7 후속)".

---

## Phase 7-4 결과 (2026-10-17, 브랜치 `feat/ai_auto_ABP`) — 레이어 값 파라미터 · InstanceClass · 인터페이스 레이어 추가/삭제

**사용자 확정 (2026-10-17, 4건)**: ① 값 파라미터는 **`set_layer_inputs` 전체 교체**(Input Pose 노드의 Inputs 통째 교체, 멱등) ② 인터페이스 레이어 삭제는 구현 ABP 가 쓰면 **거부, `force` 로만 강행** ③ 인터페이스 변경 뒤 **참조 ABP 자동 로드·conform·재컴파일**(`conform_implementers=true` 기본) ④ InstanceClass 는 **새 op `set_layer_instance_class`**, **자식 ABP 오버라이드는 제외**(엔진 경로 미확정 — 아래). `phase7_4_test.py` 7개 절 **PASS**, `run_all.py` 단계 13 + recheck 11 **ALL PASS**(`results/20261017-213437.json`). Development · DebugGame 빌드 성공, 경고 0. Tool 24 → **27개**, op 19 → **20종** (세션 재시작 전에는 HTTP 로만 검증됨).

**엔진 경로 (소스로 확인)**
- **값 파라미터 = Input Pose 노드에 붙는다**: `UAnimGraphNode_LinkedInputPose::Inputs`(`TArray<FAnimBlueprintFunctionPinInfo{Name, FEdGraphPinType}>`, AnimGraphNode_LinkedInputPose.h:55). 컴파일러가 Input Pose 노드의 비-포즈 출력 핀을 함수 파라미터로 만든다(AnimBlueprintCompiler.cpp:1660-1676) → **입력 포즈 없는 레이어는 값 파라미터를 가질 수 없다**(`NO_INPUT_POSE`). 변경은 Persona 디테일 패널과 같은 `PostEditChangeProperty(Inputs)`(:131-149 — HandleInputPinArrayChanged → ReconstructNode → MarkStructurallyModified → self 레이어 노드 재구성) 를 `FPropertyChangedEvent` 로 직접 부른다. 이름 유일성은 BP 안의 모든 Input Pose Inputs 기준(:217-259 `CreateUniqueName` 과 같은 범위). 구현 ABP 의 Input Pose 는 편집 불가(`IsEditable()` = 그래프 `bAllowDeletion`, :190-195)라 스텁 함수에서 핀을 만든다(`CreatePinsFromStubFunction` :308-322) → 구현 그래프에 `set_layer_inputs` 는 `NOT_EDITABLE`.
- **구현 ABP 쪽 값 핀**: LinkedAnimLayer 노드는 대상 스켈레톤 클래스의 `FAnimBlueprintFunction.InputPropertyData` 를 `CustomPinProperties`(protected UPROPERTY, AnimGraphNode_CustomProperty.h:88) 옵션 핀으로 만든다(AnimGraphNode_LinkedAnimLayer.cpp:676-726, 기본 숨김). `SetCustomPinVisibility`(:373-384)는 protected → 리플렉션으로 `bShowPin` + `ReconstructNode` 재현. 노출한 핀에 `connect`(VariableGet 등)로 값을 넣으면 컴파일러가 프로퍼티 복사를 만든다(컴파일 0 에러 실측). `bind_pin` 은 `ShowPinForProperties` 전용 그대로(커스텀 핀 바인딩은 범위 밖).
- **InstanceClass**: `SetupFromLayerId`(:974-1006) — `Node.InstanceClass` 가 있으면 `FunctionReference.SetExternalMember(레이어, 클래스, GetFunctionGuidFromClassByFieldName(GetMostUpToDateClass(클래스)))`, 없으면 `SetSelfMember` → `ReconstructNode`(핀은 InstanceClass 의 스켈레톤 클래스 함수에서, `GetTargetSkeletonClass` AnimGraphNode_CustomProperty.cpp:348-363). self 레이어는 InstanceClass 를 가질 수 없다(:905-909 → `SELF_LAYER`). 컴파일 규칙을 사전 검증으로: 자기 클래스 금지(AnimGraphNode_LinkedAnimGraphBase.cpp:226-229 → `SELF_CLASS`) · `UAnimBlueprint::IsCompatible`(:232-238 → `INCOMPATIBLE`) · 인터페이스 구현(`Class->ImplementsInterface` → `NOT_IMPLEMENTING`) · 링크된 값 핀은 재구성 뒤 고아(`PINS_LINKED`, 6-4b 와 같은 성질). 클래스 경로는 AnimBP 애셋 경로(`GeneratedClass`)와 `_C` 클래스 경로 둘 다 받는다.
- **레이어 추가/삭제와 구현 전파**: 추가는 6-4b 와 같은 `CreateNewGraph(UAnimationGraph)+AddDomainSpecificGraph`(공용화 `AddLayerGraphs`), 삭제는 `FBlueprintEditorUtils::RemoveGraph(MarkTransient)`. 구현 ABP 는 **자기 컴파일 때** `ConformImplementedInterfaces`(BlueprintCompilationManager.cpp:3909 → `ConformInterfaceByName`, BlueprintEditorUtils.cpp:7364-7427)로 동기화된다 — 새 anim 함수는 `UAnimationGraph` 그래프를 만들고(:7372-7380), 함수가 사라진 그래프는 이름을 비우고 `bEditable=false` 로 남긴다(:7397-7427, 내용 유실). 그래서 도구가 AssetRegistry 참조자 중 구현 ABP 를 로드해 `ConformImplementedInterfaces` + 컴파일한다(`ConformImplementers`; 디스크 참조자만 — 저장 안 된 새 구현 ABP 는 못 본다). `ConformImplementedInterfaces` 는 인터페이스 BP 의 **SkeletonGeneratedClass** 를 본다(:7302-7307) → 인터페이스를 먼저 컴파일.
- **자식 ABP 오버라이드(제외)**: 에디터의 "Override" 는 `SMyBlueprint::ImplementFunction`(SMyBlueprint.cpp:2808-2883)이 **K2 `UEdGraph`** 를 만든다(:2877) — 애니 레이어용 `UAnimationGraph` 생성 경로는 `AddFunctionGraph<UClass>` + `UAnimationGraphSchema::CreateFunctionGraphTerminators(Graph, 부모 클래스)`(:423-482) 로 추정되지만 에디터 코드에서 확인하지 못해 ❓ 로 남긴다.

| 산출물 | 위치 |
| :--- | :--- |
| 레이어 기계 확장 | `Core/AnimMcpAnimLayer.{h,cpp}` — `FLayerParams.InputPoses` 가 `{Name, Inputs[{Name, Type}]}` · `ParseLayerList`/`ParseInputParams`(create·add 공용, 타입은 `AnimMcpVariables::ParsePinType`) · `AddLayerGraphs`(인터페이스/자체 공용, 이름 충돌 선검증) · `RemoveLayerGraphs`(참조 ABP 로드 → `usage[]` → force) · `SetLayerInputs`(NOT_EDITABLE·NO_INPUT_POSE·AMBIGUOUS_INPUT_POSE·UNKNOWN_INPUT_POSE·DUPLICATE_NAME·BAD_TYPE·멱등) · `ConformImplementers` · `IsLayerInterface` · `ResolveAnimInstanceClass`/`ValidateInstanceClass`/`SetInstanceClass`/`RestoreInstanceClass`(`FInstanceRef` = 클래스 + `FMemberReference` 통째) · `DescribeLayers` 에 `editable`·`inputs[{name, type, input_pose}]` |
| Tool 3개 | `Tools/AnimMcpTools_Layers.cpp` — `set_layer_inputs {asset_path, layer, input_pose?, inputs[], compile?=true, save?, conform_implementers?=true}` · `add_anim_layers {asset_path, layers[], compile?, save?, conform_implementers?}`(인터페이스면 인터페이스 레이어, ABP 면 자체 레이어) · `remove_anim_layers {asset_path, layers[names], force?, compile?, save?, conform_implementers?}`. 응답 = info + `compile` + `implementers[{asset_path, conformed, compile}]` (+ `unchanged` / `added[]` / `removed[]·usage[]·forced`) |
| op | `set_layer_instance_class {node\|ref, instance_class: 경로 \| null}` — `Core/AnimMcpOperations.cpp`(사전 검증 = `ValidateInstanceClass`, 적용 = `SetInstanceClass`, 되돌리기 = `RestoreInstanceClass`; 응답 `old_instance_class`·`linked_layer`) — op 20종 |
| 커스텀 핀 | `Core/AnimMcpGraphMutator` — `CustomPinsOf`(리플렉션)·`FindCustomPinIndex`·`HasOptionalPin`(expose_pin 사전 검증)·`SetPinVisible` 가 커스텀 핀도 · Inspector `optional_pins[]` 에 `custom:true` 항목 · revision `C|이름|show` 줄(없으면 줄 없음 → 기존 호환) |
| 테스트 | `Tools/mcp/phase7_4_test.py` — A 인터페이스(값 파라미터 포함) 생성 · B `set_layer_inputs`(2개·unchanged·축소·비움·거부 8종) · C 구현(값 핀 전파·custom 핀 노출·Speed 연결 컴파일 0 에러·Prov 에서 InPose.AimYaw→PlayRate·NOT_EDITABLE) · D `set_layer_instance_class`(PINS_LINKED·애셋/클래스 경로·거부 5종·혼합 배치 무변경·null 해제·지정+재연결 한 배치) · E `add_anim_layers`(implementers 2 컴파일 0·거부 4종·자체 레이어·SELF_LAYER) · F `remove_anim_layers`(LAYER_IN_USE_BY usage 2종·빈 삭제·force·NOT_EDITABLE·자체 레이어) · G 저장 · `--recheck`. 테스트 애셋 `ALI_McpTest74`·`ABP_McpLayer74Base`·`ABP_McpLayer74Prov`(6-4b 애셋은 건드리지 않는다). `run_all.py` PHASES/RECHECKS 7-3 뒤 |

**실측으로 바로잡은 것 · 확인한 것**
- 자체(편집 가능) 레이어 그래프의 Input Pose 노드 **포즈 출력 핀 이름은 `Pose`**, 구현(스텁 함수) 그래프에서는 **파라미터 이름(`InPose`)** — 테스트는 타입이 Pose 인 출력 핀을 고른다(6-4b 와 같은 주의).
- `set_layer_instance_class` 는 값 핀이 링크된 채로는 거부(`PINS_LINKED`) — "클래스 지정 + 값 핀 재연결" 은 **한 배치**로 가능하다(사전 검증 시점엔 링크 없음, 적용은 순서대로). 해제(null)는 링크가 있어도 허용.
- `remove_anim_layers` 의 usage 는 **구현 그래프가 채워진 ABP 마다** 1건 — Base·Prov 가 모두 Lower 를 채웠으면 2건.
- `ConformImplementers` 는 AssetRegistry 참조자 기준이라 **저장하지 않은 구현 ABP 는 동기화되지 않는다**(테스트는 구현 뒤 저장). 응답 `implementers` 의 컴파일 결과로 force 삭제의 여파(노드 "invalid layer")를 본다.
- 미검증: `INCOMPATIBLE`(다른 스켈레톤의 구현 ABP 재료 없음 — 두 스켈레톤이 있으나 같은 인터페이스를 구현한 ABP 가 없다) · 자식 ABP 오버라이드(제외) · 커스텀 핀 `bind_pin`(범위 밖).

**다음**: 로드맵 §5(PIE 런타임 검증 Automation 테스트). 핸드오프 "최종 지시 (Phase 7 후속)".

---

## Phase 7-5 결과 (2026-10-17, 브랜치 `feat/ai_auto_ABP`) — PIE 런타임 검증 (축소판)

**사용자 확정 (2026-10-17, 2건) + 소스 해소 1건**: ① 시나리오 파라미터는 **테스트 명령 문자열 "<클래스 이름> <JSON>"** 에 싣는다(전역 슬롯 아님 — 결과 `command` 에 시나리오가 남아 재현 가능) ③ **본 트랜스폼 비교는 제외**(상태머신 현재 상태·슬롯 활성만). ② 검증 대상 ABP 는 소스로 해소 — `UAstralAnimInstance::NativeThreadSafeUpdateAnimation` 이 `Speed`·`bIsFalling` 등을 매 프레임 스냅샷에서 덮어써(AstralAnimInstance.cpp:75-88; 폰 없이 스폰하면 Speed 0) 운영 `ABP_Hero_Base` 로는 "Speed 300 → Run" 을 볼 수 없다 → 변수 주도 시나리오는 부모 `UAnimInstance` + BP 변수의 전용 테스트 ABP `ABP_McpRuntimeTest`, 운영 ABP 는 변수 없이 "진입 상태(Idle)" 만 읽는다. 자식 ABP 레이어 오버라이드(7-4 ❓)는 프로젝트가 인터페이스 + InstanceClass 방식이라 **범위 밖**으로 정리. `phase7_5_test.py` 5개 절 **PASS**, `run_all.py` 단계 14 + recheck 12 **ALL PASS**(`results/20261017-232334.json` — 결과·상태 JSON 은 gitignore 생성물이라 로컬 기록; 앞선 두 번은 6-2 레지스트리 타이밍 플레이크와 그 잔여 애셋 때문에 실패 — 아래 실측). Development · DebugGame 빌드 성공, 경고 0. Tool 27 → **28개** (세션 재시작 전에는 HTTP 로만 검증됨). **6-5 에서 미검증이던 지연(latent) 명령의 FTSTicker 진행과 테스트별 타임아웃 경로가 여기서 처음 실측됐다.**

**엔진 경로 (소스로 확인)**
- **파라미터 전달**: `FAutomationTestFramework::StartTestByName(InTestToRun)` 은 첫 공백 앞을 등록된 테스트 이름, 뒤를 `Parameters` 로 나눠(AutomationTest.cpp:631, InternalStartTest :1273) `CurrentTest->SetTestContext(Parameters)` → `RunTest(Parameters)`(:1292-1311). 등록 이름 = `IMPLEMENT_SIMPLE_AUTOMATION_TEST` 의 클래스 이름(AutomationTest.h:4104-4118). `FAutomationTestInfo` 생성자가 공개라(AutomationTest.h:298) Tool 이 `{DisplayName, FullTestPath, TestName="FAnimMcpRuntimeAnimBlueprintTest <JSON>", Flags, 1, ParameterName}` 를 직접 조립해 6-5 잡 기계(`StartJobWithTests`)에 넣는다. 지연 명령에서 `AddError` 한 것도 `InternalStopTest` 의 `HasAnyErrors` 로 실패가 된다(:1371).
- **지연 명령**: `ADD_LATENT_AUTOMATION_COMMAND(X)` 매크로(AutomationTest.h:4070)는 인자의 쉼표를 보호하지 않아 람다 본문에 취약 → `FAutomationTestFramework::Get().EnqueueLatentCommand(MakeShared<FFunctionLatentCommand>(람다))`(:1085, FFunctionLatentCommand :4717) 로 직접 큐잉. `ExecuteLatentCommands` 는 호출 시점에 명령이 있었으면 false 를 돌려주므로(:674-711) 마지막 명령이 끝난 다음 프레임에 `StopTest`.
- **PIE**: 엔진 `FStartPIECommand`(AutomationEditorCommon.cpp:859-878) 와 같이 `FRequestPlaySessionParams`(PlayInEditorDataTypes.h:126-205, 기본 `WorldType = PlayInEditor`) 로 `GEditor->RequestPlaySession` → 다음 에디터 Tick 에 `StartQueuedPlaySessionRequest` 가 동기로 시작. `GlobalMapOverride`(:200) 는 PIE 게임 인스턴스의 `OverrideMapURL` 이 된다(PlayLevel.cpp:1828). 종료는 `RequestEndPlayMap`(PlayLevel.cpp:1391, `bRequestEndPlayMapQueued`) → 다음 Tick 에 `EndPlayMap`. 코어 티커(러너)는 엔진 루프에서 에디터 Tick **앞**이라 "요청 → PlayWorld·`HasBegunPlay` 대기 → 작업" 세 단계로 나눈다. `IsPlaySessionInProgress()`(EditorEngine.h:1808)로 요청이 버려졌는지 본다.
- **상태·슬롯 조회**: `UAnimInstance::GetStateMachineIndex(FName)`(AnimInstance.h:1159, 프록시) · `GetCurrentStateName(int32)`(:1233 — `AnimNodeProperties` 역순 인덱스로 `FAnimNode_StateMachine::GetCurrentStateName`, AnimInstance.cpp:1890-1904) · `GetInstanceCurrentStateElapsedTime`(:1077) · `IsSlotActive(FName)`(:601 — 프록시 `MontageEvaluationData` 의 활성 몽타주 슬롯, AnimInstance.cpp:2369-2383) · `Montage_Play`(:613, 실패 0) · `Montage_IsPlaying`(:679). 상태머신 목록은 `IAnimClassInterface::GetFromClass(Class)->GetBakedStateMachines()`(AnimClassInterface.h:196, `FBakedAnimationStateMachine{MachineName, States[{StateName}]}` AnimStateMachineTypes.h:363-377, :325).
- **스폰·할당**: `ASkeletalMeshActor`(SkeletalMeshActor.h:22, `GetSkeletalMeshComponent` :93) → `SetSkeletalMesh` → `SetAnimInstanceClass`(SkeletalMeshComponent.cpp:3458-3480: 클래스가 바뀌면 `ClearAnimScriptInstance` + `InitAnim(true)` 즉시 → 같은 프레임에 `GetAnimInstance()` 유효). **엔진이 인스턴스를 만들지 말지는 `NeedToSpawnAnimScriptInstance` 의 `AnimSkeleton->IsCompatibleMesh(MeshAsset, false)`**(:883 — Skeleton.cpp:640-670, 본 이름 집합 비교, 부모 사슬 검사 없음) → Tool 의 메시 검사도 같은 호출. `VisibilityBasedAnimTickOption = AlwaysTickPoseAndRefreshBones`(SkinnedMeshComponent.h:737)로 화면에 안 보여도 평가. 변수는 `UClass::FindPropertyByName` + `AnimMcpPropertyRules::JsonToImportText` + `FProperty::ImportText_Direct`. 프리뷰 메시는 `UAnimBlueprint::GetPreviewMesh(true)`(AnimBlueprint.cpp:312, 에디터 전용 `PreviewSkeletalMesh`) → `USkeleton::GetPreviewMesh(true)`.
- **슬롯과 Source 갱신**: `FAnimNode_Slot::Update_AnyThread` 는 `bAlwaysUpdateSourcePose || IsRelevant(SourceWeight)` 일 때만 Source 를 Update 한다(AnimNode_Slot.cpp:67-72, 기본 false :145) — 몽타주가 슬롯을 가중치 1 로 덮는 동안 그 뒤의 상태머신은 멈춘다.

| 산출물 | 위치 |
| :--- | :--- |
| 계약 | `Core/AnimMcpRuntimeScenario.{h,cpp}` (신규) — `TestClassName`·`TestPath`·`MakeTestCommand` · 관측 슬롯 `SetObservation`/`TakeObservation`(JSON **문자열** — 같은 FJsonObject 를 run·poll 두 응답에 넣지 않으려고 응답마다 파싱) |
| 테스트 | `Tests/AnimMcpRuntimeTests.cpp` (신규, `WITH_DEV_AUTOMATION_TESTS`) — `AnimGraphMcp.Runtime.AnimBlueprint`(EditorContext · ProductFilter). 파라미터 없으면 경고+통과(필터로 직접 돌릴 때). 로드(ABP GeneratedClass·메시·몽타주, `TStrongObjectPtr` 로 PIE 기동 중 GC 방어) → 지연 7단계: ① `RequestPlaySession`(`map` → GlobalMapOverride) ② PlayWorld `HasBegunPlay` 대기(5프레임 뒤에도 세션이 없으면 오류·중단) ③ 스폰·메시·`SetAnimInstanceClass`·변수(`variables_applied`)·`Montage_Play`(`montage_length`, 0 이면 오류) ④ `wait_frames` ⑤ 모든 BakedStateMachines 의 `{state, elapsed}` · 기대 슬롯 ∪ 몽타주 슬롯의 `IsSlotActive` · `montage_playing` → 기대값 불일치마다 `AddError("expected 'Run' but it is in 'Idle' after 10 frames")` ⑥ 관측 기록 + `RequestEndPlayMap` ⑦ PlayWorld 소멸 대기 |
| Tool | `Tools/AnimMcpTools_Automation.cpp` — `run_anim_scenario {asset_path, mesh?, map?, set_variables?, montage?, wait_frames=10, expect?{state_machines, slots_active}, timeout=120}`: `PIE_ACTIVE` · `NOT_ANIM_BLUEPRINT` · `NOT_COMPILED` · 메시(지정 > ABP 프리뷰 > 스켈레톤 프리뷰, `NO_PREVIEW_MESH`) · `SKELETON_MISMATCH`(메시 `IsCompatibleMesh(,false)`, 몽타주 `IsCompatibleForEditor`) · 변수 존재·`JsonToImportText` 선검증(`VARIABLE_NOT_FOUND` details.variables · `BAD_VALUE`) · 기대 상태머신·상태 이름을 BakedStateMachines 로 선검증(`STATE_MACHINE_NOT_FOUND` details.state_machines · `STATE_NOT_FOUND` details.states) · `BAD_WAIT_FRAMES`(1..100000 정수) · `BAD_SLOT` · 몽타주 없이 슬롯 기대 → 경고 `NO_MONTAGE`. 응답 = 잡(항상 `done:false`) + `scenario`(정규화 JSON) + `state_machines[]` |
| 러너 | `Core/AnimMcpAutomationRunner` — `StartJobWithTests(Label, Tests[], Timeout)`(`StartJob` 은 이것의 `FindTests` 래퍼) · `FTestResult.ObservedJson`(`Record` 가 `TakeObservation`) → `DescribeJob` 의 `tests[].observed` · `FinishCurrent(강제)` 뒤 `GEditor->PlayWorld` 면 `RequestEndPlayMap`(타임아웃이 지연 명령을 버려 테스트가 못 닫는 PIE) |
| 6-2 플레이크 수정 | `Core/AnimMcpAssetOps` — `FindReferencersIncludingMemory`(레지스트리 참조자 ∪ `FReferencerFinder::GetAllReferencers(패키지 안 모든 객체)` 의 콘텐츠 패키지; /Temp·Transient·CompiledIn·스크립트 제외) · `delete_animation_blueprint` 만 이것을 쓴다(레이어 conform 은 디스크 참조자가 필요해 `FindReferencers` 유지) |
| 테스트 스크립트 | `Tools/mcp/phase7_5_test.py` — A 준비(Tool 28 · dry_run 1 · 직접 실행 passed+경고 · `ABP_McpRuntimeTest` 생성: `/Script/Engine.AnimInstance` + `Speed:float` + `Locomotion`(Idle·Run, `Speed > 150`/`<= 150`, AS_Idle·AS_Hero_Jump) → Slot `UpperBody{bAlwaysUpdateSourcePose}` → Root, 컴파일 0 에러·저장) · B 양성(Idle · Run+`AM_McpTest`→UpperBody 활성·montage_playing · PIE 닫힘) · C 음성(상태 불일치 failed+observed · NO_MONTAGE+failed) · D 거부 8종 · UEFN 마네킹 메시 통과 · 잡 진행 중 2종 · wait_frames 300 완료 · timeout 3초 → `timeout` · PIE 닫힘 · 다음 시나리오 정상 · E 운영 `ABP_Hero_Base` → `Locomotions` Idle. `--recheck` 는 B·E 관측(상태·슬롯·몽타주) 동일. `run_all.py` PHASES/RECHECKS 7-4 뒤·6-5 앞 |

**실측으로 바로잡은 것 · 확인한 것**
- **몽타주가 덮은 슬롯 뒤의 상태머신은 멈춘다** — 첫 실행에서 Speed 300 + 몽타주 시나리오가 `Locomotion = Idle, elapsed 0` 으로 실패했다. 테스트 ABP 는 Root ← Slot(UpperBody) ← 상태머신 이고 `AM_McpTest` 가 그 슬롯을 가중치 1 로 덮으니 `FAnimNode_Slot` 이 Source 를 갱신하지 않은 것(AnimNode_Slot.cpp:67). 테스트 ABP 의 Slot 에 `bAlwaysUpdateSourcePose=true` 를 주고 통과. 운영 ABP 처럼 상체 레이어가 `FullBody` 캐시 뒤에 있으면 전신 상태머신은 영향이 없지만, **전신 슬롯 뒤 상태머신을 몽타주 중에 검증하려면 이 플래그가 필요**하다 — 도구가 바로 보여준 설계 함정.
- **메시 호환은 본 이름 집합이다** — 처음엔 UEFN 마네킹(`SKM_UEFN_Mannequin`)이 `SKELETON_MISMATCH` 로 거부될 것으로 기대했으나 통과해 인스턴스가 생기고 Idle 까지 갔다. 엔진 `NeedToSpawnAnimScriptInstance` 가 `IsCompatibleMesh(mesh, false)` 를 쓰고 UE5 마네킹 계열은 본 이름이 같기 때문. 도구도 같은 호출로 맞췄고 테스트는 "통과" 를 검증한다. 같은 이름의 두 `SKEL_UE5_F` 도 마찬가지로 메시로는 구분되지 않고 몽타주(`IsCompatibleForEditor`)로만 갈린다. 본 이름이 다른 메시가 프로젝트에 없어 `SKELETON_MISMATCH(mesh)` 양성은 미검증.
- `SK_UEFN_Mannequin` 은 스켈레톤, 메시는 `SKM_UEFN_Mannequin`(`LoadAssetOfClass` 가 클래스 불일치로 거부).
- **6-2 플레이크(7-5 와 무관한 타이밍)** — 첫 `run_all` 에서 `phase6_2_test` 의 "자식 ABP 저장 → 부모 삭제 → `ASSET_REFERENCED`" 가 참조자 0 으로 통과해 버려 삭제가 됐고(이후 recheck 2건도 연쇄 실패: `ABP_McpDup` 없음 · 부모 잃은 `ABP_McpChild` 가 스모크 22번째로 잡혀 failed). 7-5 → 6-2 를 단독으로 돌리면 PASS — AssetRegistry 의 패키지 의존성이 저장 직후 디렉터리 워처·게더러를 거쳐 **비동기**로 갱신되는 창(AssetRegistry.cpp:8706-8723 `OnFilesChanged` 경로)에 걸린 것. 삭제 거부가 결정적이도록 `FReferencerFinder`(ReferencerFinder.h:29) 로 메모리 참조자를 합쳤다. 남은 `ABP_McpChild` 는 Tool 로 지웠다.
- 시나리오 한 건은 PIE 기동 포함 **약 1.4초**(테스트 ABP) · 운영 맵(CombatTestMap, 기본 에디터 월드)에서 GameMode·히어로 스폰이 함께 돌아도 문제 없음 · `wait_frames 300` 은 3.0초. 타임아웃 3초 시나리오는 3.7초에 `timeout` 으로 끝나고 러너가 PIE 를 닫아 바로 다음 시나리오가 정상.
- 잡 진행 중 `run_anim_scenario` 재호출은 PIE 가 이미 열려 `PIE_ACTIVE`, `run_automation_tests` 는 "job … still running".
- 운영 `ABP_Hero_Base` 는 `UAstralAnimInstance` 로 PIE 의 `ASkeletalMeshActor` 위에서도 인스턴스가 생기고(`TryGetPawnOwner` null 경로) `Locomotions` 가 Idle 로 진입한다.
- 미검증: PIE 가 외부에서 켜진 상태의 `StartTestByName` 거부(`not_started`, 테스트 중엔 재현 불가) · `map` 오버라이드 양성(기본 월드만 실측) · `SKELETON_MISMATCH(mesh)` 양성 · 네이티브 변수 덮어쓰기 뒤의 값(시나리오는 기록만).

**로드맵 §1~§5 종료.** 핸드오프 "최종 지시 (로드맵 종료 이후)".

---

## Phase 7-6 결과 (2026-10-19, 브랜치 `feat/character_ABP`) — 스켈레톤 재할당 · 시퀀스 additive (히어로 전투 ABP 선행)

**배경**: 히어로 전투 ABP([hero-combat-abp.md](hero-combat-abp.md), 사용자 확정 4건) 를 만들려니 라이플·AimOffset 애셋 40개가 두 번째 `SKEL_UE5_F`(`/Game/IdaFaber/…`)에 있어 ABP(`/Game/Assets/…` 스켈레톤)가 참조할 수 없었고, `AS_Hero_AO_RifleCC` 는 기준 포즈가 없어 AimOffset 샘플이 안 됐다(7-3 실측). Python 원격 실행은 에디터 기동 직후 멀티캐스트 발견이 실패하던 때가 있어(재기동 뒤 성공) 두 작업을 Tool 로 만들었다. 사용자 확정: 스켈레톤 통합은 **새 Tool**(에디터 수동 아님). Tool 28 → **30개**. Development · DebugGame 빌드 경고 0(`StackingType` deprecated 는 런타임 setter 가 없어 pragma).

**엔진 경로 (소스로 확인)**
- **제자리 리타겟**: `EditorAnimUtils::RetargetAnimations(Old, New, TArray<TWeakObjectPtr<UObject>>, bRetargetReferredAssets, NameRule=nullptr, bConvertSpace)`(EditorAnimUtils.h:92, .cpp:365-369) → `FAnimationRetargetContext::RetargetAnimations`(.cpp:256-316): 시퀀스마다 `UAnimationBlueprintLibrary::CopyAnimationCurveNamesToSkeleton(Old, New, Seq)` + 트랜스폼 커브 제거 + `ReplaceSkeleton(New, bConvertSpaces)` + `MarkPackageDirty`. NameRule 이 없으면 복제 없이 제자리, Slate 알림만 띄운다(:392-431). AnimBP 도 받지만(TargetSkeleton 교체) 도구는 애니 애셋만.
- **참조 전파는 선택이 아니다**: `UAnimationAsset::ReplaceSkeleton`(AnimationAsset.cpp:460-482) 이 `GetAllAnimationSequencesReferred(AnimAssetsToReplace)` 로 세그먼트·샘플·기준 포즈를 모아 **항상** 함께 바꾼다 — 첫 테스트에서 `include_referred=false` 로 몽타주만 보냈는데 `AS_Idle` 이 따라갔다. 옵션을 없애고 `referred[]`(각 후보의 `GetAllAnimationSequencesReferred(…, bRecursive=true)`, AnimationAsset.h:1158)를 계획과 저장 목록에 넣었다. 원본 스켈레톤별로 묶어 호출한다(커브 복사가 Old 기준).
- **본 트랙 검증**: `UAnimSequenceBase::GetDataModel()`(AnimSequenceBase.h:258, `IAnimationDataModel*`) → `GetBoneTrackNames(TArray<FName>&)`(IAnimationDataModel.h:257; `GetBoneAnimationTracks` 는 5.2 deprecated) ↔ `USkeleton::GetReferenceSkeleton().FindBoneIndex` → 없는 트랙이 있으면 `BONES_MISSING`(`ReplaceSkeleton` 은 그 트랙을 조용히 버린다).
- **additive 설정**: `UAnimSequence::AdditiveAnimType · RefPoseType · RefPoseSeq · RefFrameIndex`(AnimSequence.h:283-297, :293, 전부 EditAnywhere) → `PostEditChangeProperty`(AnimSequence.cpp:1277-1331): `RefPoseSeq` 의 스켈레톤이 다르면 **조용히 null**(:1296-1302) → 도구가 `SKELETON_MISMATCH` 선거부 · additive 관련 프로퍼티 이름이면 `bAdditiveSettingsChanged` → 재압축(:1317-1331). 도구는 바뀐 프로퍼티마다 `FPropertyChangedEvent(Property, ValueSet)` 로 호출.
- **AssetRegistry `Skeleton` 태그**는 export 텍스트(`/Script/Engine.Skeleton'/Game/X.X'`) → `FPackageName::ExportTextPathToObjectPath` 로 비교(7-3 의 list 와 같은 방법).

| 산출물 | 위치 |
| :--- | :--- |
| Tool | `Tools/AnimMcpTools_Skeleton.cpp` — `reassign_skeleton {skeleton, assets[] \| from_skeleton + path_prefix, confirm, dry_run, allow_missing_bones, convert_spaces, save=true}`: 후보 수집(명시 목록 또는 레지스트리 수집) → `already_on_target`/`other_skeleton`/`no_skeleton` skipped → 본 트랙 검증 → `referred[]` → dry_run 이면 `planned[]` → `confirm` → 원본 스켈레톤별 `RetargetAnimations` → 검증(`changed_assets[]`/`failed[]`) → 저장(변경 애셋 + referred + 더티면 대상 스켈레톤 `skeleton_saved`). `assets` 원소는 `EJson::String` 만(숫자는 `TryGetString` 이 문자열로 바꿔 버려 처음엔 `ASSET_NOT_FOUND` 로 샜다) |
| Tool | `Tools/AnimMcpTools_Sequence.cpp` — `set_sequence_additive {asset_path, additive_type?, ref_pose_type?, ref_pose_sequence?(경로\|null), ref_frame_index?, save}`: enum 은 접두(`AAT_`/`ABPT_`) 생략 허용(`BAD_ENUM` 에 허용 목록) · 생략 = 유지 · 같은 값 = `unchanged` · 응답에 `additive_valid` |
| 서버 · 러너 | `server.py` Tool 2개 · `run_all.py` PHASES/RECHECKS 에 `phase7_6_test`(7-5 뒤 · 6-5 앞) |
| 테스트 | `Tools/mcp/phase7_6_test.py` 7절 PASS(핸드오프 §8). 운영 시퀀스 `AS_Idle` 을 A→B→A 왕복하는 점(참조 전파 때문에 피할 수 없음)과 `restore_idle` 안전망 |
| 기존 테스트 수정 | `phase7_3_test.py` `SKELETON_AO = SKELETON`(AO 샘플이 A 로 옮겨짐) · `phase7_5_test.py` 다른 스켈레톤 몽타주를 `AM_McpOtherSkel`(UEFN `M_Neutral_Walk_Loop_F` 로 생성)로 — `/Game/IdaFaber` 몽타주가 더는 없다 · `phase3_test.py` BlendSpace 선택에서 AimOffset 제외(`AO_Hero_Rifle` 이 알파벳순 첫째가 되어 BlendSpacePlayer preview 가 거부됨) · `phase7_4_test.py` 레이어 값 파라미터 `AimYaw`/`AimPitch` → `LayerYaw`/`LayerPitch`(`UAstralAnimInstance` 에 같은 이름 네이티브 변수가 생겨 구현 ABP 컴파일 "property already exists") |
| 콘텐츠 적용 | `Tools/mcp/reassign_hero_skeleton.py --apply` — 40개 → A(+ 첫 테스트가 끌고 갔다가 미저장으로 남은 AO 8개를 재기동 뒤 다시). `/Game` 전체 B 애셋 0 · `ABP_Hero_Base` 컴파일 0 에러 · 스모크의 `AM_Hero_Attack1~3` "Slot 노드 없음" 경고도 사라짐(이제 같은 스켈레톤) |

**실측으로 바로잡은 것 · 확인한 것**
- **참조 애셋은 항상 따라간다** (위). 첫 7-6 테스트의 E 절이 `/Game/Animation/Test` 의 B 애셋을 수집하면서 7-3 이 B 로 만들어 둔 `AO_McpTest` 를 A 로 옮겼고, 그 샘플 `AS_Hero_AO_Rifle*` 8개가 메모리에서만 A 가 됐다(저장 목록 밖) → `quit_editor discard_dirty` 에서 버려져 디스크는 B 그대로 → 재기동 뒤 `reassign_hero_skeleton.py --apply` 가 8개를 다시 잡았다. 교훈: **referred 를 저장 목록에 넣지 않으면 메모리와 디스크가 갈린다** — 수정본은 넣는다.
- `AssetRegistry` 의 `Skeleton` 태그는 저장 직후 바로 갱신됐다(테스트가 저장 뒤 즉시 `list_animation_assets` 로 확인) — 6-2 의 의존성 지연과 달리 태그는 동기 경로.
- `RetargetAnimations` 의 Slate 알림은 에디터 안에서만 뜨고 응답에는 영향 없다. `skeleton_saved` 는 두 번 다 false — 커브 이름이 이미 대상 스켈레톤에 있었다.
- **UE ExecuteFile 원격 실행 함정 재확인**: 스크립트 소스 앞부분(주석 포함)에 ".py" 가 있으면 엔진이 소스 전체를 파일 경로로 오인한다(lockon_input.py 주석에 기록된 그대로). 7-6 에서 두 번 걸렸다 — 주석에 확장자를 쓰지 않는다.
- **대상 스켈레톤 저장은 "우리가 더럽혔을 때만"** — 전체 `run_all` 에서 7-3(임시 슬롯 `McpTestSlot`/`McpTestGroup` 을 저장하지 않고 남김) 뒤에 7-6 이 돌자, 이미 더티였던 `SKEL_UE5_F` 를 `skeleton_saved` 경로가 저장해 임시 그룹이 디스크에 남았다(7-3 recheck "임시 슬롯 사라짐" 실패). 수정: 호출 전 `IsDirty` 를 기억해 이미 더티면 저장하지 않고 `SKELETON_DIRTY_NOT_SAVED` 경고. 디스크의 스켈레톤은 `git checkout` 으로 복원.
- **BlendListByBool 은 `BlendPose_0` 이 True Pose** (AnimGraphNode_BlendListByBool.cpp:37) — 히어로 공급자 ABP 에서 거꾸로 꽂아 세 번째 PIE 까지 "조준 중 전진 Jog" 로 보였다(사용자가 그래프 스크린샷으로 발견). 도구 조회 응답은 `BlendPose_0/1` 만 주고 표시 이름(True/False)을 주지 않는다 → 후속 후보: 핀 표시 이름(`display_name`)을 `pins[]` 에 싣기.
- **네이티브 변수 이름은 레이어 값 파라미터·BP 변수와 한 이름 공간**: 테스트 인터페이스의 값 파라미터 `AimYaw` 가 새 네이티브 `UAstralAnimInstance::AimYaw` 와 충돌해 구현 ABP 가 "Tried to create a property AimYaw … already exists" 로 깨졌다(스모크 2건 failed). 프로젝트 ABP 변수·레이어 파라미터를 지을 때 네이티브 이름을 피한다.
- 미검증: `convert_spaces=true`(기준 포즈가 다른 스켈레톤 — 재료 없음) · `allow_missing_bones=true` 양성(트랙이 버려지는 경우) · 대상 스켈레톤이 더티가 되는 경우(`skeleton_saved=true`).

**히어로 전투 ABP(같은 날)** — [hero-combat-abp.md](hero-combat-abp.md). 도구만으로 AO(9)·BlendSpace 2·ALI·베이스·공급자 생성, 스모크 3 passed · 상태머신 운영 1:1 · PIE Idle 진입. 런타임 C++ 4건. 사용자 PIE 확인 대기. → 2026-10-19 밤 사용자 PIE 확인 완료.

**제자리 회전(2026-10-20, 같은 브랜치)** — [hero-combat-abp.md](hero-combat-abp.md) §7. 도구 변경은 한 줄: 전이 허용 목록에 `LogicType`(`Core/AnimMcpPropertyRules.cpp`; TEnumAsByte 는 기존 FByteProperty+Enum setter 가 `TLT_Inertialization` 이름으로 받는다). 실측: ① `bind_pin` 의 enum(FEnumProperty uint8) → BlendListByEnum `ActiveEnumValue`(uint8) 는 호환(GetPropertyCompatibility) ② 같은 배치 안에서 `add_state` ref 로 만든 상태에 `set_property bAlwaysResetOnEntry`·`graph:{ref}` 노드 채우기·`add_transition` 53 op 한 번에 적용 ③ 함수 경로 바인딩 `GetMainAnimInstance.X`(BlueprintThreadSafe BlueprintPure 가 다른 인스턴스를 돌려주는 경우)와 규칙 `{"access": "GetMainAnimInstance.bWantsTurnInPlace"}` 모두 컴파일·런타임 동작 ④ 조회 응답의 바인딩은 `optional_pins[].bound/binding` (검증 스크립트가 `pins[]` 를 봐서 헛 FAIL) ⑤ 전이 조회에 `logic_type` 없음(후속) ⑥ 링크된 레이어 안 상태머신의 관성 전이 요청은 베이스 루트의 Inertialization 노드가 받는다(PIE 첫 프레임 w=1.00). ⑦ 허용 목록에 SequencePlayer/BlendSpace `bIgnoreForRelevancyTest`(상태 안 보조 플레이어를 자동 전이의 관련 플레이어에서 제외) ⑧ 상태 그래프의 출력 노드는 `AnimGraphNode_StateResult`(루트 AnimGraph 의 Root 가 아님) ⑨ 프로브용 에디터는 `-unattended` 로 띄운다(백그라운드 CPU 스로틀 해제, EditorEngine.cpp:5014).

---

## 부록 — 확인에 사용한 파일

**엔진 (Phase 7-6 추가)**: `Editor/UnrealEd/Public/EditorAnimUtils.h`(FAnimationRetargetContext :33-58 · RetargetAnimations :92/:103/:114), `Editor/UnrealEd/Private/EditorAnimUtils.cpp`(Initialize :90-135 · FAnimationRetargetContext::RetargetAnimations :256-316 · RetargetAnimations :365-437), `Runtime/Engine/Classes/Animation/AnimationAsset.h`(SetSkeleton :1101 · ReplaceSkeleton :1147 · GetAllAnimationSequencesReferred :1158 · RemapTracksToNewSkeleton :1225), `Runtime/Engine/Private/AnimationAsset.cpp`(ReplaceSkeleton :460-482), `Runtime/Engine/Classes/Animation/AnimSequence.h`(AdditiveAnimType/RefPoseType/RefFrameIndex/RefPoseSeq :283-297 · RemapTracksToNewSkeleton :728), `Runtime/Engine/Private/Animation/AnimSequence.cpp`(PostEditChangeProperty :1277-1331), `Runtime/Engine/Classes/Animation/AnimSequenceBase.h`(GetDataModel :258 · GetDataModelInterface :261), `Runtime/Engine/Classes/Animation/AnimData/IAnimationDataModel.h`(GetBoneAnimationTracks(deprecated) :185-187 · GetNumBoneTracks :249 · GetBoneTrackNames :257), `Runtime/Engine/Classes/Components/SkeletalMeshComponent.h`(LinkAnimClassLayers :1105 · UnlinkAnimClassLayers :1116 · GetLinkedAnimLayerInstanceByClass :1130), `Runtime/Net/Core/Classes/Net/Serialization/FastArraySerializer.h`(PostReplicatedReceive :131/:518-536), `Plugins/Runtime/GameplayAbilities/Source/GameplayAbilities/Public/GameplayEffect.h`(FGameplayEffectModifierMagnitude(FSetByCallerFloat) :304 · StackingType deprecated :2403 · Stack* :2407-2425 · SetStackingType WITH_EDITOR :2432 · GEComponents protected :2459-2462 · AddComponent/FindOrAddComponent :2493-2518), `…/Private/GameplayEffect.cpp`(PostInitProperties 네이티브 GE 검사 :175-230 · PostLoad→OnGameplayEffectChanged :350-391), `…/Public/GameplayEffectComponents/TargetTagsGameplayEffectComponent.h`(SetAndApplyTargetTagChanges :28 · InheritableGrantedTagsContainer private :53), `…/Private/GameplayEffectComponents/TargetTagsGameplayEffectComponent.cpp`(:24-28 · :60-76), `Runtime/CoreUObject/Private/UObject/UObjectGlobals.cpp`(IsInConstructor-- :4086/:4159 → PostConstructInit :4239)

**프로젝트 (Phase 7-6 · 히어로 전투 ABP)**: `Source/AstralBreak/Animation/AstralAnimInstance.{h,cpp}`, `AbilitySystem/Abilities/Hero/Combat/AstralGA_Hero_BasicAttack_Ranged.{h,cpp}`, `AbilitySystem/Abilities/AstralGameplayAbility.cpp`(ApplySetByCallerEffect :52-71), `AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.cpp`(ApplyRegenBlockEffect :89-107), `Character/Hero/Components/AstralHeroMovementComponent.{h,cpp}`, `Character/Components/AstralCharacterMovementComponent.h`, `Character/AstralCharacter.cpp`(:24-52 회전 기본값), `Equipment/AstralEquipmentFamily.h`, `Equipment/AstralEquipmentManagerComponent.{h,cpp}`, `Character/Components/AstralLoadoutComponent.cpp`(RefreshAppearance :95-121), `Character/AstralCharacterDefinition.h`, `Player/AstralPlayerState.cpp`(:21 Mixed), `Tools/ue_exec.py`, `Tools/scripts/setup/lockon_input.py`(ExecuteFile 함정 주석)

**엔진 (Phase 7-5 추가)**: `Runtime/Core/Public/Misc/AutomationTest.h`(FAutomationTestInfo 생성자 :298 · EnqueueLatentCommand :1085 · GetCurrentTest :1260 · ADD_LATENT_AUTOMATION_COMMAND :4070 · IMPLEMENT_SIMPLE_AUTOMATION_TEST_PRIVATE :4104-4118 · FFunctionLatentCommand :4717), `Runtime/Core/Private/Misc/AutomationTest.cpp`(StartTestByName :620-659 · StopTest :661 · ExecuteLatentCommands :674-711 · InternalStartTest :1267-1311 · InternalStopTest :1362-1392), `Runtime/Engine/Public/Tests/AutomationCommon.h`(GetAnyGameWorld :190), `Runtime/Engine/Private/Tests/AutomationCommon.cpp`(:709-723), `Editor/UnrealEd/Public/Tests/AutomationEditorCommon.h`(FStartPIECommand :224 · FEndPlayMapCommand :229), `Editor/UnrealEd/Private/Tests/AutomationEditorCommon.cpp`(:711-725 RunPIE · :859-887 · :1297-1310), `Editor/UnrealEd/Public/PlayInEditorDataTypes.h`(FRequestPlaySessionParams :126-205), `Editor/UnrealEd/Classes/Editor/EditorEngine.h`(PlayWorld :518 · RequestPlaySession :1783 · IsPlaySessionRequestQueued/InProgress :1806-1808 · RequestEndPlayMap :1840), `Editor/UnrealEd/Private/PlayLevel.cpp`(RequestEndPlayMap :1391 · OverrideMapURL :1828), `Runtime/Engine/Classes/Animation/AnimInstance.h`(IsSlotActive :601 · Montage_Play :613 · Montage_IsPlaying :679 · GetInstanceCurrentStateElapsedTime :1077 · GetStateMachineIndex :1159 · GetCurrentStateName :1233), `Runtime/Engine/Private/Animation/AnimInstance.cpp`(GetCurrentStateName :1890 · IsSlotActive :2369 · Montage_Play :2469 · GetStateMachineIndex :4415), `Runtime/Engine/Classes/Animation/{AnimClassInterface(:196), AnimStateMachineTypes(:307-377), SkeletalMeshActor(:22-93), AnimBlueprint(:204, :275), Skeleton(:579-685, :707, :771)}.h`, `Runtime/Engine/Private/AnimBlueprint.cpp`(GetPreviewMesh :312-336), `Runtime/Engine/Private/Animation/Skeleton.cpp`(IsCompatibleMesh :640-670), `Runtime/Engine/Private/Components/SkeletalMeshComponent.cpp`(NeedToSpawnAnimScriptInstance :867-886 · SetAnimInstanceClass :3458-3480 · SetAnimationMode :3988), `Runtime/Engine/Classes/Components/SkinnedMeshComponent.h`(:96, :737), `Runtime/AnimGraphRuntime/Public/AnimNodes/AnimNode_Slot.h`(:21), `Runtime/AnimGraphRuntime/Private/AnimNodes/AnimNode_Slot.cpp`(Update_AnyThread :38-72 · :145), `Source/AstralBreak/Animation/AstralAnimInstance.cpp`(:35-88)

**엔진 (Phase 7-4 추가)**: `Editor/AnimGraph/Public/{AnimGraphNode_LinkedInputPose, AnimGraphNode_CustomProperty, AnimGraphNode_LinkedAnimLayer}.h`, `Editor/AnimGraph/Private/{AnimGraphNode_LinkedInputPose, AnimGraphNode_LinkedAnimLayer, AnimGraphNode_LinkedAnimGraphBase, AnimGraphNode_CustomProperty, AnimationGraphSchema, AnimBlueprintCompiler, AnimGraphDetails}.cpp`, `Editor/UnrealEd/Public/Kismet2/BlueprintEditorUtils.h`(AddFunctionGraph 템플릿 :343-399, EGraphRemoveFlags :42-56), `Editor/UnrealEd/Private/Kismet2/BlueprintEditorUtils.cpp`(ImplementNewInterface :6440-6510, RemoveInterface :6594-6718, ConformInterfaceByName :7300-7427, ConformImplementedInterfaces :7432-7490), `Editor/Kismet/Private/{BlueprintCompilationManager(:3896-3914), SMyBlueprint(:1060-1150, :1515-1550, :2789-2883), BlueprintEditor(:9717)}.cpp`, `Runtime/Engine/Classes/Animation/AnimBlueprint.h`(IsCompatible :235)

**엔진 (Phase 7-3 추가)**: `Runtime/Engine/Classes/Animation/{AnimMontage, AnimCompositeBase, AnimLinkableElement, Skeleton, AimOffsetBlendSpace, AimOffsetBlendSpace1D, AnimSequence}.h`, `Runtime/Engine/Private/Animation/{AnimMontage, AnimLinkableElement, Skeleton, AimOffsetBlendSpace, BlendSpace, AnimSequence}.cpp`, `Runtime/Engine/Public/AlphaBlend.h`, `Runtime/AnimGraphRuntime/Public/AnimNodes/AnimNode_Slot.h`, `Editor/AnimGraph/Public/AnimGraphNode_Slot.h`, `Editor/UnrealEd/Private/Factories/{AnimMontageFactory, EditorFactories}.cpp`, `Editor/Persona/Private/{SAnimMontagePanel, SAnimMontageSectionsPanel, SSkeletonSlotNames}.cpp`, `Editor/SkeletonEditor/Private/EditableSkeleton.cpp`

**엔진 (Phase 7-2 추가)**: `Runtime/AnimGraphRuntime/Public/AnimNodes/{AnimNode_RotationOffsetBlendSpace, AnimNode_BlendSpacePlayer, AnimNode_SequenceEvaluator, AnimNode_ApplyAdditive, AnimNode_Mirror, AnimNode_BlendListBase, AnimNode_LayeredBoneBlend}.h`, `Runtime/AnimGraphRuntime/Public/BoneControllers/{AnimNode_SkeletalControlBase, AnimNode_TwoBoneIK, AnimNode_ModifyBone}.h`, `Runtime/Engine/Classes/Animation/{AnimNode_SequencePlayer, AnimNode_Inertialization, InputScaleBias, BlendProfile, MirrorDataTable, Skeleton}.h`, `Runtime/Engine/Public/Animation/BoneSocketReference.h`, `Runtime/Engine/Public/BoneContainer.h`, `Editor/AnimGraph/Public/AnimGraphNode_{RotationOffsetBlendSpace, SequenceEvaluator, ApplyAdditive, TwoBoneIK, ModifyBone, Mirror, Inertialization, BlendSpaceBase, SkeletalControlBase}.h`

**엔진 (Phase 7-1 추가)**: `Editor/UnrealEd/Public/Kismet2/BlueprintEditorUtils.h`(AddMemberVariable :848 · RemoveMemberVariable :887 · IsVariableUsed :1336 · FindNewVariableIndex :1256 · GetClassVariableList :821 · CreateNewGraph :328 · CreateFunctionGraph/AddFunctionGraph :343-399 · GetOverrideFunctionClass :417 · RemoveGraph :448 · SetBlueprintVariableCategory :1189), `Editor/UnrealEd/Private/Kismet2/BlueprintEditorUtils.cpp`(AddMemberVariable :4645-4703 · RemoveMemberVariable :4706-4719 · IsVariableUsed :5926 · IsFunctionConvertableToEvent :2242 · HasFunctionBlueprintThreadSafeMetaData :10589-10603), `Editor/UnrealEd/Public/Kismet2/Kismet2NameValidators.h`(:24-40, :83-94), `Editor/Kismet/Private/SMyBlueprint.cpp`(ImplementFunction :2808-2883), `Runtime/Engine/Classes/Animation/AnimInstance.h`(BlueprintThreadSafeUpdateAnimation :566-567 · TryGetPawnOwner :451 · GetOwningActor :532), `Editor/AnimGraph/Private/AnimBlueprintCompiler.cpp`(:1084-1151 스레드 안전 검사), `Editor/BlueprintGraph/Classes/EdGraphSchema_K2.h`(PC_* :391-410 · PN_Execute/PN_Then :421-422 · ConfigureVarNode :654 · CreateFunctionGraphTerminators :1014/:1022 · ArePinTypesCompatible :1128), `Editor/BlueprintGraph/Classes/K2Node_Variable.h`(SetFromProperty :120), `Editor/BlueprintGraph/Classes/K2Node_FunctionTerminator.h`(FunctionReference :31-32), `Editor/BlueprintGraph/Private/K2Node_VariableSet.cpp`(:101-102, :400-402), `Runtime/Engine/Classes/EdGraph/EdGraph.h`(FGraphNodeCreator :274-313), `Runtime/Engine/Private/EdGraph/EdGraph.cpp`(CreateNode :216), `Engine/Plugins/Developer/PropertyAccessNode/{PropertyAccessNode.uplugin, Source/PropertyAccessNode/PropertyAccessNode.Build.cs, Source/PropertyAccessNode/Private/K2Node_PropertyAccess.h(:14-131), K2Node_PropertyAccess.cpp(:116-158, :170-236, :278-296)}`, `Editor/AnimGraph/Private/PropertyAccessAnimBlueprintBinding.cpp`(:22-30), `Editor/UnrealEd/Public/IPropertyAccessEditor.h`(:332-338, :422-473)

**엔진 (Phase 6-5 추가)**: `Runtime/Core/Public/Misc/AutomationTest.h`(FAutomationTestFramework: SetRequestedTestFilter · LoadTestModules · GetValidTestNames · StartTestByName · ExecuteNetworkCommands/ExecuteLatentCommands · StopTest · DequeueAllCommands; FAutomationTestInfo; FAutomationTestExecutionInfo/FAutomationExecutionEntry; IMPLEMENT_COMPLEX_AUTOMATION_TEST), `Runtime/Core/Private/Misc/AutomationTest.cpp`(:174-176 경고 승격 플래그 · StartTestByName · StopTest :1880-1909), `Runtime/Core/Public/Misc/AutomationEvent.h`, `Runtime/Core/Public/Containers/Ticker.h`(FTSTicker), `Editor/AnimGraph/Public/AnimStateNodeBase.h`(:41 GetStateName), `Runtime/Engine/Classes/Engine/Blueprint.h`(FBPInterfaceDescription :261-271 · ImplementedInterfaces :604), `Source/AstralBreak/Tests/*.cpp`(프로젝트 테스트 형식)

**프로젝트**: `AstralBreak.uproject`, `Source/AstralBreak.Build.cs`, `Source/AstralBreakEditor.Target.cs`, `Config/DefaultEngine.ini`, `Config/DefaultGame.ini`, `Source/AstralBreak/Animation/AstralAnimInstance.{h,cpp}`, `Tools/ue_exec.py`, `Tools/lib/ab_blueprint.py`, `.claude/settings.json`, `Content/Animation/**`, `Content/Characters/**`

**엔진 (Phase 6-4b 추가)**: `Runtime/Engine/Classes/Animation/{AnimLayerInterface,AnimNode_LinkedAnimLayer,AnimNode_LinkedAnimGraph,AnimNode_LinkedInputPose,AnimNode_Root,AnimClassInterface}.h`, `Runtime/Engine/Private/Animation/AnimNode_Root.cpp`(:13), `Editor/UnrealEd/Classes/Factories/{AnimLayerInterfaceFactory,BlendSpaceFactoryNew}.h`, `Editor/UnrealEd/Private/Factories/AnimBlueprintFactory.cpp`(:451-503, :514-517), `Editor/UnrealEd/Private/Kismet2/BlueprintEditorUtils.cpp`(AddDomainSpecificGraph :2418 · ImplementNewInterface :6414-6510 · ConformImplementedInterfaces ~:7181), `Editor/Kismet/Private/BlueprintEditor.cpp`(:9714-9719), `Editor/AnimGraph/Public/{AnimGraphNode_LinkedAnimLayer,AnimGraphNode_LinkedAnimGraphBase,AnimGraphNode_LinkedInputPose,AnimGraphNode_Root,AnimationGraphSchema}.h`, `Editor/AnimGraph/Private/AnimGraphNode_LinkedAnimLayer.cpp`(:676-716, :754-774, :813-881, :974-1006), `Editor/AnimGraph/Private/AnimGraphNode_LinkedInputPose.cpp`(:113-149, :268-322, :347-391, :687-690), `Editor/AnimGraph/Private/AnimationGraphSchema.cpp`(CreateFunctionGraphTerminators :423-482 · ConformAnimGraphToInterface :1117-1199), `Editor/AnimGraph/Private/AnimGraphDetails.cpp`(:55-137, :285-325), `Editor/AnimGraph/Private/AnimBlueprintCompiler.cpp`(:1570-1725, :1758-1792)

**엔진 (Phase 6-4a 추가)**: `Editor/AnimGraph/Public/AnimGraphNode_Base.h`(FAnimGraphNodePropertyBinding :137-191 · Binding :232 · SetPinVisibility :470 · GetPinProperty :523 · HasBinding/RemoveBindings :556-568 · protected GetPinBindingInfo/RecalculateBindingType/EnsureBindingsArePresent :640-658), `Editor/AnimGraph/Internal/AnimGraphNodeBinding.h`, `Editor/AnimGraph/Private/AnimGraphNodeBinding_Base.{h,cpp}`(:28-128 · OnAddBinding :428-507 · OnRemoveBinding :509-521), `Editor/AnimGraph/Private/AnimGraphNode_Base.cpp`(EnsureBindingsArePresent :200 · PinConnectionListChanged :1010), `Editor/AnimGraph/Private/AnimBlueprintExtension_Base.cpp`(:190-255), `Editor/AnimGraph/Private/AnimBlueprintExtension.cpp`(:75-83), `Editor/UnrealEd/Public/IPropertyAccessEditor.h`(ResolvePropertyAccess :422/:449 · GetPropertyCompatibility :459 · MakeTextPath :473), `Runtime/CoreUObject/Public/UObject/UnrealType.h`(FScriptMapHelper :4703, :5306-5423)

**엔진 (Phase 6-3 추가)**: `Runtime/Engine/Classes/Animation/{BlendSpace,BlendSpace1D}.h`(FBlendParameter :113-159 · FBlendSample :164 · AddSample :617-618 · BlendParameters :907), `Runtime/Engine/Private/Animation/BlendSpace.cpp`(PostEditChangeProperty :155 · ValidateSampleData :1461 · ExpandRangeForSample :1610 · AddSample :1647 · ValidateAnimationSequence :1812 · IsSameSamplePoint :2270 · ResampleData :2650 · ResampleData2D :2742), `Runtime/Engine/Private/Animation/BlendSpace1D.cpp`(:11-15), `Editor/UnrealEd/Private/Factories/EditorFactories.cpp`(BlendSpace 팩토리 :7353-7369, :7427-7443), `Editor/Persona/Private/Customization/BlendSpaceDetails.cpp`(:208-217), `Editor/Persona/Private/SAnimationBlendSpace.cpp`(:181-199, :345-351)

**엔진 (Phase 6-2 추가)**: `Editor/UnrealEd/Private/Subsystems/EditorAssetSubsystem.cpp`(DeleteAsset :795 · DuplicateAsset :945), `Editor/UnrealEd/Private/ObjectTools.cpp`(DuplicateSingleObject :799 · CleanupAfterSuccessfulDelete :2498), `Editor/UnrealEd/Private/Kismet2/BlueprintEditorUtils.cpp`(PostDuplicateBlueprint :1513-1688), `Editor/UnrealEd/Public/Kismet2/BlueprintEditorUtils.h`(FBlueprintDuplicationScopeFlags :1996), `Editor/UnrealEd/Public/{FileHelpers,PackageTools}.h`, `Editor/UnrealEd/Private/{UnrealEdEngine,EditorServer}.cpp`(CloseEditor · QUIT_EDITOR), `Editor/MainFrame/Private/Frame/MainFrameHandler.h`(CanCloseEditor), `Developer/AssetTools/Private/AssetTools.cpp`(PerformDuplicateAsset :2138), `Runtime/Core/Private/Misc/MessageDialog.cpp`(:128,:172 unattended), `Runtime/Online/HTTPServer/Private/HttpConnection.cpp`(:170-246), `Runtime/Launch/Private/LaunchEngineLoop.cpp`(:6072-6078), `Runtime/Engine/Private/EdGraph/EdGraph.cpp`(PostInitProperties :141)

**엔진** (`Engine/Source/`): `Editor/UnrealEd/Classes/Factories/{AnimBlueprintFactory,BlendSpaceFactoryNew}.h`, `Editor/UnrealEd/Private/Factories/AnimBlueprintFactory.cpp`, `Editor/UnrealEd/Private/Kismet2/Kismet2.cpp`, `Editor/UnrealEd/Public/Kismet2/{KismetEditorUtilities,BlueprintEditorUtils,CompilerResultsLog}.h`, `Editor/UnrealEd/Public/{ScopedTransaction,FileHelpers}.h`, `Editor/UnrealEd/Private/ScopedTransaction.cpp`, `Editor/UnrealEd/Public/Subsystems/EditorAssetSubsystem.h`, `Editor/UnrealEd/Classes/Editor/EditorEngine.h`, `Editor/AnimGraph/AnimGraph.Build.cs`, `Editor/AnimGraph/Public/{AnimationGraph,AnimationGraphSchema,AnimGraphNode_Base,AnimGraphNode_SequencePlayer,AnimGraphNode_BlendSpacePlayer,AnimGraphNode_Slot,AnimGraphNode_LayeredBoneBlend,AnimGraphNode_BlendListByBool,AnimGraphNode_BlendListByEnum,AnimGraphNode_SaveCachedPose,AnimGraphNode_UseCachedPose,AnimGraphNode_Root,AnimGraphNode_AssetPlayerBase,AnimGraphNode_StateMachine,AnimGraphNode_StateMachineBase,AnimGraphNode_TransitionResult,AnimationStateMachineGraph,AnimationStateMachineSchema,AnimStateNode,AnimStateNodeBase,AnimStateEntryNode,AnimStateTransitionNode,AnimationTransitionGraph,AnimationStateGraph}.h`, `Editor/AnimGraph/Private/{AnimGraphNode_Base,AnimGraphNode_StateMachineBase,AnimStateNode,AnimStateTransitionNode,AnimationStateMachineSchema,AnimationGraphSchema,AnimationStateGraphSchema,AnimationTransitionSchema,AnimationStateGraph,AnimationTransitionGraph}.cpp`, `Editor/BlueprintGraph/Classes/{EdGraphSchema_K2,K2Node_Variable,K2Node_VariableGet,K2Node_CallFunction,K2Node_PromotableOperator}.h`, `Editor/BlueprintEditorLibrary/Public/BlueprintEditorLibrary.h`, `Editor/AnimationBlueprintLibrary/Public/AnimationBlueprintLibrary.h`, `Runtime/Engine/Classes/EdGraph/{EdGraph,EdGraphNode,EdGraphSchema}.h`, `Runtime/Engine/Classes/Animation/{AnimBlueprint,AnimInstance,AnimNode_SequencePlayer,AnimNode_Root,AnimNode_TransitionResult}.h`, `Runtime/Engine/Classes/Engine/{Blueprint,MemberReference}.h`, `Runtime/Engine/Classes/Kismet/KismetMathLibrary.h`, `Runtime/Core/Public/Async/Async.h`, `Runtime/Online/HTTPServer/Public/*.h`, `Runtime/Online/HTTPServer/Private/{HttpServerModule,HttpListener,HttpServerConfig}.{h,cpp}`, `Runtime/Online/HTTPServer/HttpServer.Build.cs`

**엔진 플러그인** (`Engine/Plugins/`): `Experimental/PythonScriptPlugin/PythonScriptPlugin.uplugin`, `.../Private/{PyGenUtil,PyWrapperObject}.cpp`, `.../Private/PythonScriptRemoteExecution.h`, `Editor/EditorScriptingUtilities/EditorScriptingUtilities.uplugin`, `VirtualProduction/RemoteControl/Source/WebRemoteControl/Private/WebRemoteControl.h`
