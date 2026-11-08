# M3 적 AI 설계

작성일: 2026-11-05 · 대상: UE 5.7.4 · 기준 커밋: `6e2e2ee` · 앞 단계: [StateTree Phase2Report](../StateTree/Phase2Report.md)
상태: **1번 설계 승인(2026-11-05, 권장안 그대로) · 구현 · 자동 검증 완료(2026-11-05, 미커밋). 남은 것 = V9 더미 사용자 눈 확인.**

M3(일반 몬스터 AI · 어그로) 설계를 이 문서 하나에 순서대로 쌓는다. 앞 항목이 뒤 항목의 전제가 되도록 사용자와 순서를 합의했다. 생명주기를 어그로보다 먼저 정해야 그 위에 얹는 것을 다시 고치지 않는다.

| # | 항목 | 상태 |
| ---: | :--- | :--- |
| 1 | 적 생명주기 | **이 문서 §1 — 구현 · 검증 완료, 결과는 §1-7** |
| 2 | 타깃 · 어그로 (`UAstralThreatComponent`) | 기획서 제공 뒤 |
| 3 | 적 공격 실행 (텔레그래프 GA 전환 · 패링 → 경직 → 약점) | 기획서 제공 뒤 |
| 4 | StateTree 연결 노드 | 기획서 제공 뒤 |
| 5 | `ST_Enemy_Melee` 구성 | 기획서 제공 뒤 |
| 6 | 스폰 · 콘텐츠 (적 PawnData · 메시 · 애니) | 기획서 제공 뒤 |
| 7 | 네트워크 종료 조건 (3단계 테스트 · `IsPartyLeader`) | 기획서 제공 뒤 |

M3 기획서 원문은 저장소에 없다. 2번부터는 사용자가 제공한 뒤 쓴다. 지금 쓰면 규칙을 지어내게 된다.

**표기:** **[실측]** = 실행으로 확인했다. **[소스]** = 소스를 읽어 판단했고 실행하지 않았다. 근거의 파일 이름은 프로젝트 또는 엔진(`D:/UnrealSource/UnrealEngine-5.7.4-release/Engine`) 소스다. 시나리오 번호(S1 ~ S6)는 [Phase2Report §3](../StateTree/Phase2Report.md) 의 실행이고, C · V 번호는 §1-7 의 실행이다.

**항목 형식:** 결정 → 대안과 기각 이유 → 근거 → 영향 → 미해결.

## 1. 적 생명주기

### 결론

**트리는 폰이 전투 준비를 끝냈다는 신호로 시작하고, 폰이 죽기 시작할 때 멈춘다. 그 밖에 폰이 컨트롤러를 떠나는 모든 경로는 `OnUnPossess` 가 받는다.**

| 질문 | 결정 |
| :--- | :--- |
| 준비 완료 | 서버에서 ASC 결합 · `AbilitySets` 부여 · 기본 장비 장착 시도가 끝난 상태. `AAstralCombatCharacter::BeginPlay` 의 서버 블록 끝에서 폰이 알린다 |
| 트리 시작 | `AAstralEnemyController` 가 `OnPossess` 에서 폰 신호를 `RegisterAndCall` 로 구독해 `StartLogic` 을 부른다. `bStartAILogicOnPossess = false` |
| 트리 정지 | `UAstralHealthComponent::OnDeathStarted` 에서 `StopLogic` + `StopMovement`. `OnUnPossess` 를 오버라이드해 `Super` 전에 `StopLogic` |
| 상속 | 신호는 `AAstralCombatCharacter` 에 둔다. Hero 는 영향 없고 더미는 구독자 0 이다 |
| `AutoPossessAI` | 베이스 기본값은 그대로 둔다. 적 BP 가 지정하고, 6번 스폰 시스템이 `SpawnDefaultController` 를 안전망으로 부른다 |
| 적 PawnData · InitState | 6번으로 미룬다 |
| 네트워크 | 전부 서버 전용. 복제 프로퍼티 변경 없음 |

**Phase 2 권고와 달라진 점이 하나 있다.** [Phase2Report §6](../StateTree/Phase2Report.md) 의 1번은 'InitState 완료 뒤 `StartLogic`' 을 권했다. 소스를 따라가 보니 `GameplayReady` 는 어빌리티 부여보다 **먼저** 온다(§1-5). 그래서 InitState 를 기다리지 않고 부여가 끝나는 지점에서 직접 알린다.

### 1-0. 구현 전의 실제 순서

**런타임 스폰** [소스, 3 · 4단계 순서는 실측 S3, 4단계 상태는 실측 C1]

| # | 호출 | 근거 | 그 시점 |
| ---: | :--- | :--- | :--- |
| 1 | `PostActorConstruction` → 폰 `PostInitializeComponents` | `Actor.cpp:4474` | |
| 2 | `APawn::PostInitializeComponents` → `SpawnDefaultController` | `Pawn.cpp:155` | `AAstralCharacter` 쪽 `Super` 호출 안이다 |
| 3 | 컨트롤러 `SpawnActor` — 컨트롤러 `BeginPlay` 가 여기서 돈다 | `Pawn.cpp:377` · `Actor.cpp:4482` | 폰 없음 |
| 4 | `Possess` → `AAIController::OnPossess` → **`StartLogic`** | `Pawn.cpp:382` · `AIController.cpp:516` | PawnExt 결합 전 · 어빌리티 0. ASC 객체와 아바타는 있다 — 엔진이 `InitializeComponent` 에서 소유 액터로 채운다(`AbilitySystemComponent_Abilities.cpp:63`) |
| 5 | `AAstralCharacter::PostInitializeComponents` — 사망 델리게이트 바인딩 | `AstralCharacter.cpp:127` | |
| 6 | `AAstralCombatCharacter::PostInitializeComponents` — PawnExt 로 ASC 결합, Health · 이동 · 장비 연결 | `AstralCombatCharacter.cpp:42` | ASC 결합 |
| 7 | `DispatchBeginPlay` → 폰 `BeginPlay` | `Actor.cpp:4502` | |
| 8 | `Super::BeginPlay` — 컴포넌트 `BeginPlay`(PawnExt 가 `Spawned`), `ReceiveBeginPlay` | `Actor.cpp:4770` · `:4791` · `AstralPawnExtensionComponent.cpp:61` | 부여 전 |
| 9 | `AbilitySets` 부여 → 기본 장비 장착 | `AstralCombatCharacter.cpp:49` ~ `:67` | **준비 완료** |

구현 전에는 4단계에서 트리가 시작했다. 구현 뒤에는 9단계 뒤다. 4 ~ 9단계는 `SpawnActor` 호출 하나 안에서 끝나므로 런타임 스폰의 시작은 프레임 단위로 늦어지지 않는다 [실측 — `started_at` 0.017 그대로].

**레벨 배치** — 1 ~ 6단계는 같다. 7단계만 `AWorldSettings::NotifyBeginPlay` 의 일괄 순회로 미뤄지고(`WorldSettings.cpp:364`), 그때 월드는 아직 `SetBegunPlay(true)` 전이다(`:367`). 폰과 컨트롤러의 `BeginPlay` 순서는 액터 순회 순서를 따른다 [소스]. `Possess` 가 `BeginPlay` 보다 먼저인 것은 [실측 S3 · S4].

**폰이 컨트롤러를 떠나는 경로** [소스]

| 경로 | 호출 | 근거 |
| :--- | :--- | :--- |
| 폰 파괴 | `DestroyActor` → `APawn::Destroyed` → `DetachFromControllerPendingDestroy` → `PawnPendingDestroy` → `UnPossess` | `LevelActor.cpp:925` · `Pawn.cpp:531` · `:1096` · `Controller.cpp:429` |
| 그 밖의 `EndPlay` (PIE 종료 등) | `APawn::EndPlay` → 위와 같음 | `Pawn.cpp:540` |
| 다른 컨트롤러의 빙의 · 같은 컨트롤러의 다른 폰 빙의 | `AController::OnPossess` → `UnPossess` | `Controller.cpp:359` · `:370` |
| 컨트롤러 파괴 | `AController::Destroyed` → `UnPossess` | `Controller.cpp:605` |

넷 다 `UnPossess` → 가상 함수 `OnUnPossess` 를 지난다(`Controller.cpp:392`). 파괴 경로는 `Super::Destroyed`(`RouteEndPlay`) 앞(`Pawn.cpp:531` · `Actor.cpp:3286`), `EndPlay` 경로는 `Super::EndPlay` 앞(`Pawn.cpp:540` · `:543`)이다. 즉 PawnExt 의 ASC 해제(`AstralPawnExtensionComponent.cpp:67`)보다 먼저라 **이 시점에 ASC 는 살아 있다.**

**이번에 새로 확인한 것** [실측 C2 · 소스]

- **실패한 `StopLogic` 은 트리를 실행 중으로 남긴다.** `bIsRunning = false` 는 `StopTree` 람다 안에만 있다(`StateTreeComponent.cpp:221`). 컨텍스트 검사가 실패하면(`:254` → `:260`) 틱만 꺼지고(`:237`) `IsRunning()` 은 참, `TreeRunStatus` 는 `Running` 인 채로 남는다.
- **그래서 경고가 2줄이다.** `OnUnPossess` 의 `CleanupBrainComponent`(`AIController.cpp:544`)에서 1번, 컨트롤러 컴포넌트 `EndPlay`(`StateTreeComponent.cpp:107`)에서 다시 1번이다. `unpossess` 만 하면 1줄, 파괴하면 2줄이다.
- **`Stop` 이 돌면 `ExitState` 는 불린다.** `TreeRunStatus == Running` 이면 무조건 `ExitState` 를 부른다(`StateTreeExecutionContext.cpp:1609` ~ `:1616`). 문제는 `Stop` 까지 못 가는 것뿐이다.
- **같은 컨트롤러가 재빙의해야 이전 상태의 `ExitState` 가 돈다.** `Start` 가 실행 중 트리를 먼저 `Stop` 하기 때문이다(`StateTreeExecutionContext.cpp:1393`). 앞 폰의 정리가 언포제션 때가 아니라 다음 빙의 때, 뒤 폰 컨텍스트로 돈다.

### 1-1. 전투 준비 완료 신호

#### 결정

- **준비 완료의 정의:** 서버에서 ① ASC 결합 ② `AbilitySets` 부여 ③ `DefaultEquipment` 장착 시도가 끝난 상태.
- **기다릴 비동기가 없다.** ②는 `GiveAbility` 를 바로 부르고(`AstralAbilitySet.cpp:114`) ③은 정의를 동기 로드해 그 자리에서 부여 · 스폰한다(`AstralEquipmentManagerComponent.cpp:131` · `:177` ~ `:181`). 그래서 `BeginPlay` 서버 블록의 마지막 줄이 곧 완료 시점이다.
- **누가 어디서:** 폰이 `AAstralCombatCharacter::BeginPlay` 의 `HasAuthority()` 블록 끝에서 알린다. 세트와 장비가 비어 있어도 항상 알린다 — `BP_P2_Enemy` 처럼 부여할 것이 없는 폰도 시작해야 한다.
- **형태:** `IsCombatReady()` + `OnCombatReady_RegisterAndCall(Delegate)` + 구독 해제 함수. 기존 `OnAbilitySystemInitialized_RegisterAndCall` 과 같은 관용구다(`AstralPawnExtensionComponent.cpp:290`). 컨트롤러가 폰을 알 뿐, 폰은 컨트롤러 타입을 모른다.
- **장착 실패는 준비를 막지 않는다.** 정의를 찾지 못하면 이미 경고가 나간다(`AstralEquipmentManagerComponent.cpp:135`). 준비는 '시도가 끝났다' 는 뜻이다.
- 값은 서버에서만 참이 되고 복제하지 않는다. 쓰는 쪽이 서버 컨트롤러뿐이다.

#### 대안과 기각 이유

| 대안 | 기각 이유 |
| :--- | :--- |
| `OnAbilitySystemInitialized_RegisterAndCall` | ASC 결합만 알린다. 6단계라 부여(9단계)보다 앞선다 |
| InitState `GameplayReady` | PawnData 가 없으면 오지 않고, 있어도 부여보다 먼저 온다 — §1-5 |
| 엔진 `APawn::OnPawnBeginPlay` | `APawn::BeginPlay` 안에서 나간다(`Pawn.cpp:183`). `AAstralCombatCharacter::BeginPlay` 의 `Super` 호출 안이라 부여 전이다 |
| 부여를 `PostInitializeComponents` 로 앞당김 | 그래도 `StartLogic`(4단계)보다 뒤라 신호가 여전히 필요하다. 얻는 것 없이 더미의 OnSpawn GA 활성 시점만 `BeginPlay` 앞으로 옮긴다 |
| ASC 루즈 태그로 알림 | 4단계에 ASC 가 아직 결합되지 않아 구독 시점이 다시 문제가 된다. 같은 일을 돌아서 한다 |
| 다음 프레임 타이머 | 준비 조건이 아니라 시간에 맡긴다. 6번에서 준비가 늦어지면 조용히 깨진다 |
| 폰이 `GetController` 로 컨트롤러를 직접 호출 | 베이스 폰이 AI 컨트롤러 타입에 묶인다. 신호가 먼저 오는 경로는 어차피 `IsCombatReady` 가 필요하다 |
| 컨트롤러 폴링 | 사용자 작업 기준상 쓰지 않는다 |

#### 근거

`AstralCombatCharacter.cpp:42` · `:49` ~ `:67`, `AstralAbilitySet.cpp:114`, `AstralEquipmentManagerComponent.cpp:131` · `:140`, `Pawn.cpp:183`, `Actor.cpp:4770` · `:4791` [소스]. 신호 뒤 첫 `EnterState` 에서 PawnExt 결합 · 어빌리티 2개 · GA 활성화를 확인했다 [실측 V1 · V2].

#### 영향

- `AAstralCombatCharacter` 에 플래그 1 · 델리게이트 1 · 함수 3 · `BeginPlay` 두 줄. 상속 영향은 §1-4.

#### 미해결

- **신호 뒤에 부여가 생기면 깨진다.** 파생 C++ 가 `Super::BeginPlay` 뒤에 더 부여하면 신호가 앞선다. BP `ReceiveBeginPlay` 는 부여 전에 돈다(`Actor.cpp:4791`). 지금은 파생이 없다.
- **비동기 로드가 생기면 신호 위치를 옮겨야 한다.** 6번에서 적 데이터를 비동기로 불러오게 되면 그 완료 지점으로 옮긴다. 컨트롤러는 바뀌지 않는다.
- **`GA_Enemy_TelegraphAttack` 은 신호와 무관하게 돈다.** OnSpawn 이라 부여 즉시 활성화된다(`AstralGA_Enemy_TelegraphAttack.cpp:16` · `AstralGameplayAbility.cpp:211`). 트리가 아니라 GA 가 공격을 구동하는 구조는 3번에서 바꾼다.

### 1-2. 트리 시작

#### 결정

- `bStartAILogicOnPossess = false`. 엔진 경로로는 시작하지 않는다. 컴포넌트 자동 시작은 지금처럼 끈다.
- `OnPossess` 를 오버라이드한다. `Super` 뒤 `GetPawn() == InPawn` 을 확인하고(엔진이 무효 폰을 거부한다 — `AIController.cpp:468`):
  - `AAstralCombatCharacter` 면 `OnDeathStarted` 를 구독하고 `OnCombatReady_RegisterAndCall` 로 시작 함수를 건다.
  - 그 외 폰이면 바로 시작한다. 엔진 기본 동작과 같다.
- **시작 함수는 하나다.** 폰이 있고, 죽지 않았고, 실행 중이 아닐 때만 `StartLogic` 을 부른다. 실행 중 가드가 필요한 이유는 `StartLogic` 이 실행 중인 트리를 재시작하기 때문이다(`StateTreeExecutionContext.cpp:1393`).

| 경로 | 순서 | 시작 지점 | 지금 있는 경로인가 |
| :--- | :--- | :--- | :--- |
| 런타임 스폰 | Possess → 신호 | 폰 `BeginPlay` 끝. 같은 `SpawnActor` 안 | 있음 (S1) |
| 지연 스폰 | Possess → 신호 | `FinishSpawning` 안, 위와 같음 | Hero 만 씀(`AstralGameMode.cpp:51`) |
| 레벨 배치 | Possess → 월드 `BeginPlay` → 신호 | `NotifyBeginPlay` 순회 안 | 있음 (S2b) |
| 신호가 먼저 | 신호 → Possess | `OnPossess` 의 `RegisterAndCall` 즉시 | **없음.** `AutoPossessAI = Disabled` 또는 스폰 뒤 `SpawnDefaultController` 때 생긴다 |
| 재빙의 (산 폰) | UnPossess(정지) → Possess | `RegisterAndCall` 즉시 | 없음 |
| 재빙의 (죽은 폰) | Possess | 사망 가드로 시작하지 않음 | 없음 |
| 신호 전 제거 | Possess → UnPossess | 시작 안 함. `OnUnPossess` 가 구독을 푼다 | 없음 |

#### 대안과 기각 이유

| 대안 | 기각 이유 |
| :--- | :--- |
| Possess 시작 유지, 첫 상태를 항상 Delay 로 저작 | 트리 저작 규칙에 기대고, 시간에 맡기는 셈이다. 조건을 코드로 보장하지 않는다 |
| `OnNewPawn` · `OnPossessedPawnChanged` 구독 | `Possess` 끝에서 나가므로(`Controller.cpp:345`) 오버라이드보다 나을 것이 없다. 자기 자신의 이벤트를 구독하는 형태가 된다 |
| 폰 `BeginPlay` 에서 컨트롤러 생성 | 엔진 자동 빙의를 건너뛰어 `AutoPossessAI` 가 무의미해진다. 레벨 배치 · 런타임 스폰 공통 경로가 깨진다 |

#### 근거

`AIController.cpp:468` · `:516`, `Controller.cpp:338`, `Pawn.cpp:155` · `:365`. 런타임 · 배치 · 신호 선행 · 재빙의 · 죽은 폰 재빙의를 [실측 V1 ~ V5] 했다. 지연 스폰과 신호 전 제거는 실행하지 않았다.

#### 영향

- 런타임 스폰의 `started_at` 은 0.017 그대로다 [실측 V1 · S1].
- 레벨 배치는 시작이 레벨 초기화에서 `NotifyBeginPlay` 로 늦어진다. 관측은 `HasBegunPlay` 뒤에 붙으므로 시나리오 입장에서 차이가 없다 [실측 V2 · S2b].
- 레벨 배치에서는 `StartLogic` 이 컨트롤러 컴포넌트의 `BeginPlay` 보다 먼저일 수 있다. 다만 S2b 는 그보다 더 이른 레벨 초기화 때 시작해 통과했으므로 위험은 줄어드는 쪽이다 [소스 + S2b 에서 유추].
- `PathFollowing` · `GameplayTasks` 초기화(`AIController.cpp:483` ~ `:509`)는 지금 코드도 시작 전에 끝난다. 신호 경로는 그보다 뒤이므로 `MoveTo` 전제가 유지된다 [소스].

#### 미해결

- 레벨 배치의 첫 `EnterState` 시점에 플레이어 폰이 있는지 확인하지 않았다. 대상을 찾는 첫 상태가 생기는 2번에서 본다.

### 1-3. 트리 정지

#### 결정

**① 사망은 `OnDeathStarted` 에서 멈춘다.** 컨트롤러가 `OnPossess` 에서 구독한다. 폰 쪽 코드는 바뀌지 않는다.

| 시점(기본값) | 일 | 트리 |
| :--- | :--- | :--- |
| HP 0 | `HandleOutOfHealth` → `GameplayEvent.Death` (`AstralHealthComponent.cpp:145`) | 실행 중 |
| `GA_Death` 활성 | `CancelAbilities`(`AstralGA_Death.cpp:44`) → `StartDeath`(`:52`) | 실행 중 |
| `OnDeathStarted` | 폰: 콜리전 · 이동 끔. 컨트롤러: `StopLogic` · `StopMovement` | **여기서 정지** |
| +3초 | `FinishDeath` → `HandleDeathFinished` → `SetLifeSpan(2)` | 정지됨 |
| +5초 | `Destroy` → `OnUnPossess` → 컨트롤러 파괴(`Controller.cpp:434`) | 이미 정지 — `StopLogic` 은 바로 돌아온다 |

지금은 HP 0 뒤 약 5초 동안 트리가 돈다. 그동안 GA 는 `State.Death` 로 막히지만(`AstralGameplayAbility.cpp:44`) 트리 상태는 계속 바뀐다.

**② `OnUnPossess` 를 오버라이드해 `Super` 전에 `StopLogic` 을 부르고 구독 2개를 푼다.** §1-0 의 네 경로가 모두 지나는 유일한 지점이고, 그때는 폰이 아직 있다. 사망 경로에서는 이미 정지라 아무 일도 하지 않는다. `bStopAILogicOnUnposses` 는 기본값 `true` 로 둔다. 뒤따르는 `Cleanup` 은 `!bIsRunning` 으로 바로 돌아온다(`StateTreeComponent.cpp:232`).

**③ 이동 정지는 두 층이다.** `CharacterMovement` 는 기존 `HandleDeathStarted` 가 전 머신에서 끈다(`AstralCharacter.cpp:140`). 경로 추종은 트리 정지 → `MoveTo` `ExitState` → `ExternalCancel` → `AbortMove` 로 끊긴다(`StateTreeMoveToTask.cpp:76` · `AITask_MoveTo.cpp:276`). 컨트롤러는 그 뒤 `StopMovement` 를 한 번 더 부른다. 트리 밖에서 시작된 이동까지 같은 지점에서 끊으려는 것이고, 경로 추종이 `Idle` 이면 아무 일도 하지 않는다(`PathFollowingComponent.cpp:473`). 언포제션은 엔진이 `PathFollowingComponent->Cleanup` 으로 처리한다(`AIController.cpp:530`).

**④ 진행 중 GA 는 경로마다 다르다.**

| 경로 | 정리 주체 | Task `ExitState` 의 역할 |
| :--- | :--- | :--- |
| 사망 | `GA_Death` 가 `StartDeath` 전에 취소(`AstralGA_Death.cpp:44`) | 이미 끝났으므로 아무 일도 없어야 한다 |
| 산 채로 언포제션 | **Task `ExitState` 뿐** | 유일한 정리 지점 |
| 파괴 · `EndPlay` | Task `ExitState` 다음 `UninitializeAbilitySystem` 의 `CancelAbilities`(`AstralPawnExtensionComponent.cpp:163`) | 먼저 돈다. ASC 는 살아 있다 |

**⑤ 구독 순서에 기대지 않는다.** 폰의 `HandleDeathStarted` 와 컨트롤러 처리 중 무엇이 먼저 돌아도 결과가 같다. 런타임 스폰은 컨트롤러가 먼저 바인딩하고(2 ~ 4단계 → 5단계), 신호가 먼저인 경로는 반대다.

#### 대안과 기각 이유

| 대안 | 기각 이유 |
| :--- | :--- |
| `FinishDeath` · 제거 때 정지 | 죽은 폰에서 트리가 3 ~ 5초 돈다 |
| 트리 안에서 `State.Death` 로 `Dead` 상태 전환 | 트리마다 저작 규칙과 커스텀 노드가 필요하고, `OnUnPossess` 문제는 그대로다 |
| `HandleDeathStarted` 에서 `DetachFromControllerPendingDestroy` | 정지 경로가 하나로 줄지만 베이스를 고쳐 더미까지 번진다. `UnPossessed` 가 오너를 비우고(`Pawn.cpp:699`) `HandleControllerChanged` 가 `RefreshAbilityActorInfo` 를 `GA_Death` 활성 도중에 돌린다(`AstralPawnExtensionComponent.cpp:194`). 사망 연출 5초 동안 컨트롤러 없는 폰이 된다 |
| 폰 `EndPlay` · `Destroyed` 훅 | 베이스 변경인데 재빙의 · 컨트롤러 파괴 경로를 못 막는다 |
| `bStopAILogicOnUnposses = false` | 켜 둬도 뒤따르는 호출은 아무 일도 하지 않는다. 끌 이유가 없다 |
| 폰이 `HandleDeathStarted` 에서 컨트롤러 호출 | 베이스가 컨트롤러 타입을 알게 된다. `OnDeathStarted` 가 이미 단일 원천이다 |

#### 근거

- 실패 사슬: `AIController.cpp:526` → `Controller.cpp:412` · `:413` → `AIController.cpp:544` → `StateTreeComponent.cpp:267` → `:254` → `StateTreeComponentSchema.cpp:138`.
- 재진입: 트리 틱 안에서 죽어도 `StopLogic` 은 실행 중 컨텍스트로 처리하고(`StateTreeComponent.cpp:246`), `Stop` 은 틱 끝으로 미뤄진다(`StateTreeExecutionContext.cpp:1593`).
- 구현 전 경고 · `ExitState` 미호출은 [실측 C2], 사망 뒤에도 트리가 도는 것은 [실측 C3], 구현 뒤 정지는 [실측 V4 · V6 · V7 · V8 · V11]. 재진입 경로는 [소스].

#### 영향

- 사망 처리가 컨트롤러로 들어와도 `UAstralHealthComponent` · `UAstralGA_Death` · `AAstralCharacter` 는 바뀌지 않는다.
- 클라이언트는 영향 없다 — §1-6.

#### 미해결

- **부활.** `ResetDeathState` 뒤 트리를 다시 시작하지 않는다. 적 부활은 M3 범위에 없고 `ReviveSelf` 는 디버그다. 필요하면 `OnDeathReset` 구독 하나를 더한다.
- **`bAutoStartDeath = false` 서브클래스.** 취소와 `StartDeath` 사이에 트리가 돌아 GA 를 다시 띄울 수 있다(`AstralGA_Death.h:45`). 이 시점은 아직 `State.Death` 태그 전이다. 지금 쓰는 곳은 없고, 적 사망 몽타주를 넣는 6번에서 확인한다.
- **`GA_Death` 미부여.** HP 0 에서 경고만 나고 죽지 않으므로 트리도 멈추지 않는다(`AstralHealthComponent.cpp:148`). 적 AbilitySet 의 필수 항목이다.
- **`DestroyAfterDeathDelay = 0`.** `ClampMin 0` 을 허용하지만 `SetLifeSpan(0)` 은 타이머를 지워 폰이 영영 남는다(`AstralCombatCharacter.h:100` · `Actor.cpp:6527`). 제거 경로를 스폰 · 디스폰으로 바꾸는 6번에서 함께 본다.
- **죽은 폰 재빙의.** 트리는 시작하지 않지만 엔진 `ACharacter::Restart` 가 이동 모드를 되살려(`Character.cpp:977`) 콜리전이 꺼진 폰이 떨어진다 [실측 V5 — 이동 거리 1,237.7]. 지금 이 순서로 가는 게임 코드는 없고 폰은 사망 뒤 약 5초에 사라진다. 스폰 시스템이 사망 중 폰을 재빙의하지 않게 6번에서 확인한다.

### 1-4. 상속 영향

#### 결정

**신호는 `AAstralCombatCharacter` 에 둔다. `AutoPossessAI` 기본값은 바꾸지 않는다.**

- 신호는 적 BP 가 쓰고, `BP_TargetDummy` 에는 구독자가 없어 부르는 쪽이 비어 있는 델리게이트 호출 하나로 끝난다.
- `AutoPossessAI`: 적 BP 가 `PlacedInWorldOrSpawned` 와 `AIControllerClass` 를 갖는다(시험 BP 가 이미 이렇게 한다). 6번 스폰 시스템은 스폰 뒤 컨트롤러가 없으면 `SpawnDefaultController` 를 부른다 — 이미 있으면 무시되므로(`Pawn.cpp:365`) 안전망으로 쓸 수 있다. 시스템 구현은 6번 범위다.

#### 대안과 기각 이유

| 신호 위치 | 더미 | `BP_P2_*` | Hero | 판단 |
| :--- | :--- | :--- | :--- | :--- |
| **`AAstralCombatCharacter`** | 구독자 0, 동작 불변 | 재부모 없이 동작 | 무관 | **채택.** 부여 코드와 같은 곳이라 '끝났다' 를 말할 자격이 있다 |
| 새 파생 `AAstralEnemyCharacter` | 무관 | 재부모 필요 | 무관 | 부여는 베이스에 남아 파생이 끝을 덧붙이게 된다. 컨트롤러가 베이스 폰을 만나면 신호가 없어 분기가 하나 는다 |
| `AAstralCharacter` | 같음 | 같음 | **번짐** | Hero 는 InitState 로 이미 준비를 안다. 부여 코드도 없다 |
| `UAstralPawnExtensionComponent` | 같음 | 같음 | **번짐** | `BeginPlay` 가 부여보다 앞서고 부여를 알지 못한다 |

| `AutoPossessAI` 처리 | 판단 |
| :--- | :--- |
| 베이스 생성자에서 `PlacedInWorldOrSpawned` | 런타임 스폰하는 더미에 엔진 `AAIController` 가 붙는다. 얻는 것은 BP 한 줄이다 |
| 새 C++ 파생에서 지정 | 지금 필요한 파생이 아니다. 6번에서 적 공용 C++ 가 필요해지면 그때 옮긴다 |

#### 근거 · 영향

| 대상 | 현재 상태 | 영향 |
| :--- | :--- | :--- |
| `AAstralCharacter` · `AAstralCharacter_Hero` | `AAstralCharacter_Hero : AAstralCharacter` (`AstralCharacter_Hero.h:43`) | **변경 없음** |
| `BP_TargetDummy` | `DA_AbilitySet_Enemy` 참조, `AutoPossessAI` · `AIControllerClass` 저장값 없음(애셋 문자열 검색). 엔진 기본값 `PlacedInWorld` · `AAIController` 를 따른다(`Pawn.cpp:51` · `:65`) | `AAstralEnemyController` 를 쓰지 않으므로 구독자 0. 부여 · 사망 · `LifeSpan` 경로 불변 |
| `BP_P2_Enemy` | `AbilitySets` 없음(애셋 문자열 검색) | 빈 부여 뒤에도 신호가 오므로 시작한다. 시작 지점만 9단계로 옮겨진다 |
| `BP_P2_EnemyController` | `bStartAILogicOnPossess` 저장값 없음(애셋 문자열 검색) | C++ 기본값 `false` 를 따라 새 경로로 들어간다 |
| `BP_P2_EnemyController_AutoStart` | `bStartAILogicOnPossess` 저장값 있음 + 자동 시작 켬 | **대조군 의미가 바뀐다** — §1-7 |
| `GA_Enemy_TelegraphAttack` | `AAstralCombatCharacter` 로 캐스트 | 변경 없음 |

#### 미해결

- 더미의 부여 · 사망 불변은 소스 판단이다. 더미 전용 자동 시험이 없다 — §1-7 의 V9 (사용자 눈 확인 대기).

### 1-5. 적 PawnData 와의 관계

#### 결정

**InitState 체인과 적 PawnData 는 6번으로 미룬다.** 이번 신호는 둘 다 쓰지 않는다. 6번에서 도입해도 바뀌는 것은 `IsCombatReady` · `OnCombatReady_RegisterAndCall` 의 안쪽뿐이고 컨트롤러는 그대로다.

이유 셋:

1. **막힌 곳이 없다.** 체인이 `Spawned` 에 머물러도 적 쪽에서 기다리는 코드가 없다(`AstralCombatCharacter.h:18`). PawnExt 는 `PawnData` 없이 다음 단계로 못 간다(`AstralPawnExtensionComponent.cpp:238`).
2. **도입해도 신호로 못 쓴다.** 체인은 PawnExt `BeginPlay`(`AstralPawnExtensionComponent.cpp:61` · `:62`)에서 돌기 시작하고, 이것은 `AAstralCombatCharacter::BeginPlay` 의 `Super` 호출 안이다(`Actor.cpp:4770`). PawnData 와 컨트롤러가 준비돼 있으면 `GameplayReady` 까지 한 번에 가서 **부여(`AstralCombatCharacter.cpp:49`)보다 먼저 끝난다** [소스]. 신호로 쓰려면 부여를 `HandleChangeInitState` 쪽으로 옮겨야 하고, 그러면 더미까지 PawnData 가 필요해지거나 경로가 갈린다.
3. **PawnData 는 스폰과 한 덩어리다.** `UAstralPawnData` 는 `Abstract` 이고 구체 클래스는 `UAstralPawnData_Hero` 뿐이다(`AstralPawnData.h:14` · `AstralPawnData_Hero.h:15`). Hero 는 지연 스폰 사이에 `SetPawnData` 를 끼운다(`AstralGameMode.cpp:51` · `:63` · `:71`). 적도 같은 배선이 필요하고, 그것이 6번 스폰 시스템이다.

#### 대안과 기각 이유

| 대안 | 기각 이유 |
| :--- | :--- |
| 지금 적 PawnData + `RegisterAndCallForActorInitState` | 위 2 · 3번. 이득 없이 부여 이동과 스폰 배선을 앞당긴다 |
| PawnData 없이 `CanChangeInitState` 만 완화 | Hero 와 공유하는 체인의 규칙을 적 때문에 바꾼다 |

#### 근거

`AstralPawnExtensionComponent.cpp:235` ~ `:253` — 권위 쪽은 `Spawned` → `DataAvailable` 전이에 컨트롤러도 요구한다. `GameFrameworkComponentManager.h:391` — 6번에서 쓸 `RegisterAndCallForActorInitState` 가 같은 '이미 도달했으면 바로 호출' 모양이다. 전부 [소스].

#### 영향

- `AstralCombatCharacter.h:18` 의 주석 '적 PawnData 도입 시 자연 진행' 은 절반만 맞다. 체인은 진행하지만 부여 순서는 저절로 맞지 않는다. 구현 때 주석을 고친다.

#### 미해결 (6번에서 결정)

- PawnData 의 `AbilitySets` · `DefaultEquipment` 가 폰의 같은 이름 프로퍼티를 대체하는가.
- 부여 지점을 `BeginPlay` 에 둘 것인가, `DataInitialized` 처리로 옮길 것인가.

### 1-6. 서버 권위 · 네트워크

#### 결정

**신호 · 시작 · 정지는 전부 서버 전용이다. 복제 프로퍼티와 클라이언트 경로를 바꾸지 않는다.**

| 점검 | 결과 | 근거 | 판정 |
| :--- | :--- | :--- | :--- |
| AIController 존재 | 서버만. 클라이언트 월드는 인스턴스 0 | `Pawn.cpp:144` · `:365` · Phase 2 S6 | [실측] |
| Possess | 권위만 | `Controller.cpp:318` | [소스] |
| 신호 | `HasAuthority()` 블록 안, 복제 안 함. 클라이언트에서는 항상 거짓 | `AstralCombatCharacter.cpp:49` | [소스] |
| 부여 · 장비 | 시점 · 순서 불변. 이 설계는 트리 시작만 옮긴다 | `AstralCombatCharacter.cpp:49` ~ `:67` | [소스] |
| 사망 | 서버 `GA_Death` → `StartDeath`, 클라이언트는 `OnRep_DeathState` 리플레이. 클라이언트에는 구독할 컨트롤러가 없다 | `AstralHealthComponent.cpp:224` · V10 | 서버 정지와 양쪽 폰 제거는 [실측], 클라이언트 리플레이는 [소스] |
| 이동 정지 | `HandleDeathStarted` 는 기존대로 전 머신. `StopMovement` 는 서버 | `AstralCharacter.cpp:140` | [소스] |
| `TeamId` · `DeathState` · `EquipmentList` · ASC 복제 | 변경 없음 | | [소스] |

#### 대안과 기각 이유

대안 없음. 컨트롤러가 서버에만 있어 다른 구조가 나오지 않는다. 신호를 복제할 필요도 없다 — 쓰는 쪽이 서버뿐이다.

#### 영향

- 리슨 서버는 서버 월드 경로가 그대로 돈다.

#### 미해결

- Dedicated Server · 클라이언트 2개 이상은 Phase 2 에서도 돌리지 않았다. 7번에서 다룬다.

### 1-7. 검증 계획과 결과

#### 결정

**구현 전에 대조군부터 돌렸다.** [Phase2Report §6](../StateTree/Phase2Report.md) 의 두 문제는 소스 판단이 섞여 있었다. 시험 도구를 먼저 넣어 현재 코드로 C1 ~ C3 의 실패를 실측하고, 구현 뒤 같은 시험을 돌렸다. **결과: C1 ~ C3 는 실패를 보였고 V1 ~ V8 · V10 · V11 과 회귀는 통과했다.** 전부 DebugGame 에디터, `-unattended`, 2026-11-05 실행이다.

**구현한 시험 도구**

| 항목 | 내용 |
| :--- | :--- |
| 프로브 Task | `FAnimMcpLifecycleProbeTask` — `AnimMcpStateTreeTestTypes.h` · `.cpp` 의 `Hidden` 고정물. 값은 `Label` · `AbilityPath`. `EnterState`: ASC 유무 · 아바타 · PawnExt 결합 · 부여 어빌리티 수 · 지정 GA 의 `TryActivateAbilityByClass` 결과. `ExitState`: 같은 상태 + `Transition.CurrentRunStatus`. 결과는 `observed.probe` |
| 시나리오 `actions` | 시작 뒤 시간차 동작: `damage`(`DamageSelf` 를 `CallFunctionByNameWithArguments` 로 부른다 — 플러그인이 프로젝트 모듈에 의존하지 않게), `unpossess`, `repossess`, `destroy`, `spawn_controller`. `when_state` 조건 가능. 있으면 트리가 멈춰도 시나리오를 끝내지 않는다 |
| 시나리오 종료 | 시작 뒤 인스턴스 소멸은 `finished_because: instance_gone`. 0.5초 더 봐서 파괴가 클라이언트까지 복제된 월드 기록을 남긴다 |
| 플러그인 의존성 | `AnimGraphMcpEditor.Build.cs` · `AnimGraphMcp.uplugin` 에 `GameplayAbilities` 추가 |
| 시험 | `19_ScenarioActions` 추가(엔진 고정물로 `actions` · 프로브 · 소멸 경로), `17` · `18` 에 판정 · 거부 추가 |
| 시험 애셋 | `/Game/AI/Test/` 의 `ST_M3_Probe` · `BP_M3_Enemy` · `BP_M3_EnemyController` · `BP_M3_EnemyDeferred`(`AutoPossessAI = Disabled`) · `GA_M3_Probe` · `DA_AbilitySet_M3Probe`(`GA_Death` + `GA_M3_Probe`) · `L_M3_Placed`. 트리는 `state-tree-mcp` 로 저작했다. 재실행용으로 남긴다 |

**대조 — 구현 전 코드** [실측]

| # | 확인할 것 | 방법 | 결과 |
| :--- | :--- | :--- | :--- |
| **C1** | 첫 `EnterState` 에 어빌리티가 없다 | 프로브, 런타임 · 배치 | 양쪽 PawnExt 결합 거짓 · 어빌리티 0 · `TryActivate` 거짓. **ASC 객체 · 아바타는 있었다** — 뒤의 '실측이 바꾼 것' 참고 |
| **C2** | 언포제션 때 `ExitState` 가 안 불린다 | `unpossess` · `destroy` | `unpossess`: `ExitState` 0 · `run_status` `Running` 유지 · 경고 1줄. `destroy`: `ExitState` 0 · 경고 2줄. `repossess` 를 해야 그때 `ExitState` 가 돌았다 |
| **C3** | 사망 뒤 트리가 돈다 | `Chase` 중 `damage` | `MoveTo` 가 실패하며 `Idle` 로 재진입, `Running` 유지 · `activated` 거짓(`State.Death` 차단) |

**검증 — 구현 뒤 코드** [실측]

| # | 확인할 것 | 방법 | 결과 |
| :--- | :--- | :--- | :--- |
| V1 | 런타임 스폰 첫 상태에서 어빌리티 호출 | `CombatTestMap`, `spawn_location` | **통과.** `EnterState` 1회 · PawnExt 결합 · 어빌리티 2 · `TryActivate` 참 · `started_at` 0.017 |
| V2 | 레벨 배치 첫 상태 | `L_M3_Placed` | **통과.** V1 과 같음, `EnterState` 는 t = 0 |
| V3 | 신호가 먼저인 순서 | `Disabled` 변형 + `spawn_controller` | **통과.** t = 0.533 빙의 즉시 시작 · `EnterState` 1회 · `TryActivate` 참 |
| V4 | 재빙의 | `unpossess` → `repossess` | **통과.** t = 0.525 `ExitState`(`Stopped`) · `run_status` `Unset` → t = 1.025 `EnterState` · 경고 0 |
| V5 | 죽은 폰 재빙의 | `damage` → `unpossess` → `repossess` | **통과.** `EnterState` 가 늘지 않음. 다만 폰이 떨어진다 — §1-3 미해결 |
| V6 | **사망 때 `ExitState`** | `Chase`(MoveTo) 이동 중 `damage` | **통과.** t = 1.531 `ExitState`(`Stopped`) · 폰 끝 위치가 사망 프레임 위치(1128.9, -169.7)와 같음 · 경고 0 |
| V7 | 살아 있는 폰 파괴 | `destroy` | **통과.** `ExitState` 1 · `instance_gone` · 경고 0 |
| V8 | 사망 → 제거까지 | `damage` 뒤 관측 | **통과.** t = 0.526 정지, t = 5.532 소멸 — 설계의 약 5초 · 오류 0 |
| V9 | 더미 회귀 | `BP_TargetDummy` 를 PIE 에서 처치 | **사용자 눈 확인 대기** |
| V10 | 멀티 PIE | `clients: 1` + `damage` | **통과.** 서버 `ExitState` 1 · 클라이언트 인스턴스 0 · 끝에 서버 · 클라이언트 폰 0 |
| V11 | PIE 종료 경고 | 시나리오 5개 뒤 에디터 로그 | **통과.** `StopLogic` 의 `Context Requirements in ... failed` 0줄. 같은 로그에서 엔진 고정물(`16` · `19`)은 3줄 — 검색이 잡는다는 대조다 |

**회귀** [실측]: `AnimGraphMcp.StateTree` 20/20 · `Runner` 4/4 · `Smoke` 26/26 · `AstralBreak.` 31/31. S1 · S2b · S5 · S6 재실행 통과, 전환 순서 · `started_at` 그대로. Development · DebugGame 빌드 `Result: Succeeded`. 실행은 DebugGame 만이다.

**실측이 바꾼 것**

- **C1 의 기준이 틀렸다.** 'ASC 없음' 이 아니다. 엔진이 `InitializeComponent` 에서 ASC 아바타를 소유 액터로 채우므로(`AbilitySystemComponent_Abilities.cpp:63`) 객체도 아바타도 있다. 없는 것은 PawnExt 결합과 어빌리티다. ASC 유무로 준비를 판정하면 안 된다.
- **프로브 GA 는 끝나지 않는다.** 설계에는 '즉시 끝나는 수동 GA' 라고 적었으나 `GA_M3_Probe` 는 그래프가 없어 활성 상태로 남는다(`GameplayAbility.cpp:904` 의 기본 구현은 끝내지 않는다). 그래서 V4 의 재진입 `activated` 는 거짓이다. 프로브의 한계이고 V4 의 판정은 `EnterState` · `ExitState` 횟수다. 실제 Task 는 `ExitState` 에서 취소해야 한다는 §1-3 ④ 의 근거이기도 하다.

**S3 · S4 처리:** 대조를 살리려고 제품 코드에 시험용 플래그를 넣지 않았다. '런타임 스폰 + 자동 시작 = 실패' 는 이미 실측됐고 자동 시작을 다시 켤 이유가 없다. 재실행 목록에서 뺐고 이번에 돌리지 않았다. `_AutoStart` BP 2개는 지우지 않고 그대로 둔다 — §1-8.

#### 대안과 기각 이유

| 대안 | 기각 이유 |
| :--- | :--- |
| 프로브 없이 `run_status` 로만 판정 | `Stop` 실행은 보이지만 `ExitState` 호출과 첫 상태의 ASC 는 여전히 소스 판단으로 남는다. 이번 과제가 그것이다 |
| 프로브를 프로젝트 런타임 모듈에 둠 | 시험 코드가 게임 모듈에 들어간다. 기존 시험 Evaluator 와 같은 위치가 맞다 |
| 4번 커스텀 Task 가 나온 뒤 검증 | 1번을 검증 없이 쌓게 된다 |

#### 근거 — 구현 전 도구의 빈틈

| 빈틈 | 조치 |
| :--- | :--- |
| 시나리오는 StateTree 이벤트만 보냈다. 폰을 죽이거나 빙의를 풀 수 없었다 | `actions` |
| 시작 뒤 인스턴스가 사라지면 재탐색 끝에 `instance_not_found` 오류로 끝났다 | `instance_gone` |
| `EnterState` · `ExitState` 호출과 그 시점의 ASC 를 볼 수단이 없었다 | 프로브 Task |
| 정상 정지 뒤 `run_status` 는 `Stopped` 가 아니라 `Unset` 이다. `Stop` 이 실행 데이터를 지워 시작 전과 같은 값이 된다. `Stopped` 는 `OnStateTreeRunStatusChanged` 로만 나간다(`StateTreeExecutionContext.cpp:1632` · `StateTreeInstanceData.cpp:640` · `StateTreeExecutionTypes.h:1206`) | 그대로 둔다. 시작한 트리가 언포제션 뒤 `Running` 이면 `Stop` 이 실패한 것이고 `Unset` 이면 돈 것이다 [실측 C2 · V4] |
| PIE 종료 경고는 관측 뒤에 나와 `observed.log` 에 없다 | 그대로 둔다. `-stdout -FullStdOutLogOutput` 에디터 로그로 본다 |
| `BP_P2_Enemy` 에 어빌리티가 없다 | M3 시험 BP |

#### 영향 — Phase 2 시험 · 고정물

| 대상 | 영향 |
| :--- | :--- |
| `AnimGraphMcp.StateTree.01` ~ `15` | 없음. 애셋 저작만 한다. 프로젝트 클래스는 경로로만 쓴다(`AnimMcpStateTreeTests.cpp:52`) |
| **`16_RuntimeScenario` 고정물** | **제품 코드 영향 없음.** `AAIController` · `ADefaultPawn` 만 쓴다. 같은 이유로 이 고정물의 PIE 종료 경고는 남는다 — V11 대상에서 뺐다. 고정물은 함수로 뽑아 `19` 와 나눠 쓰고, `BrainComponent` 를 직접 넣어 언포제션 때 엔진이 트리를 멈추게 했다 |
| `17_ScenarioJudge` · `18_ScenarioRefused` | 판정 · 입력 추가분만 더했다 |
| S1 · S2b · S5 · S6 재실행 | 전환 순서 · `started_at` 그대로 |
| **S3 · S4 대조군** | **의미가 사라졌다.** `_AutoStart` 는 자동 시작이 켜져 있고 `AAstralEnemyController` 를 상속한다. 새 신호 경로가 트리를 시작하므로 S3 은 `started: true` 가 될 것이다(자동 시작 실패 로그는 남는다) [소스] |

#### 미해결

- V9 는 자동 판정이 없다. 더미에 트리가 없어 시나리오로 볼 수 없다.
- 이 세션의 MCP 서버는 `actions` 추가 전에 떠서 시나리오를 브리지로 직접 불렀다. 새 세션부터 `run_state_tree_scenario` 인자에 보인다.
- 돌리지 않은 것: 지연 스폰 경로, 신호 전 제거, 트리 틱 안의 사망(재진입), Development 구성 실행, Dedicated Server · 클라이언트 2개 이상.

### 1-8. 구현 결과 · 뒤 항목에 넘기는 제약

**바뀐 파일 (미커밋)**

| 파일 | 변경 |
| :--- | :--- |
| `AstralCombatCharacter.h` · `.cpp` | `IsCombatReady` · `OnCombatReady_RegisterAndCall` · `OnCombatReady_Unregister`, `BeginPlay` 끝 신호, `.h:18` 주석 |
| `AstralEnemyController.h` · `.cpp` | `OnPossess` · `OnUnPossess` · `TryStartLogic` · `HandlePawnDeathStarted`, 생성자 `bStartAILogicOnPossess = false` |
| `AnimMcpStateTreeRuntime` · `AnimMcpStateTreeTestTypes.h` · `.cpp` · `AnimMcpStateTreeTests.cpp` · `AnimMcpTools_StateTree.cpp` · `server.py` · `AnimGraphMcpEditor.Build.cs` · `AnimGraphMcp.uplugin` | 프로브 · `actions` · 종료 사유 · 시험 |
| `Content/AI/Test/` | M3 시험 애셋 7개 |
| `Docs/StateTree/DevelopmentGuide.md` · 이 문서 | 실측 결과 반영 |

**뒤 항목에 넘기는 제약**

| 항목 | 제약 |
| :--- | :--- |
| 2. 어그로 | 트리는 폰 `BeginPlay` 끝에서 시작한다. 레벨 배치에서는 플레이어가 아직 없을 수 있다고 보고 설계한다. 위협 정리 시점은 `OnDeathStarted` 를 쓸 수 있다 |
| 3. 적 공격 | 지금 `GA_Enemy_TelegraphAttack` 은 트리와 무관하게 돈다. 더미의 `bTelegraphAttackEnabled` 동작을 어떻게 유지할지 함께 정한다 |
| 4. 연결 노드 | GA 를 띄운 Task 는 `ExitState` 에서 정리한다. 사망 때는 이미 취소돼 있으므로 몇 번 불려도 같아야 한다. `ExitState` 시점에 ASC 는 살아 있다 [실측 V4 · V6 · V7] |
| 5. `ST_Enemy_Melee` | 트리에 사망 상태를 두지 않는다. 사망은 컨트롤러가 트리 밖에서 처리한다 |
| 6. 스폰 · 콘텐츠 | 적 BP 의 `AutoPossessAI` · `AIControllerClass` · `GA_Death` 포함 AbilitySet 이 필수다. 스폰 시스템의 `SpawnDefaultController`, PawnData · 부여 지점, `LifeSpan` 교체를 정한다. 사망 중인 폰을 재빙의하지 않는다 |
| 7. 네트워크 | Dedicated Server · 클라이언트 2개 이상을 여기서 돌린다 |

**사용자 결정 (2026-11-05 권장안 승인)**

1. 신호 위치 — `AAstralCombatCharacter`.
2. `AutoPossessAI` — 적 BP 지정 + 6번 스폰 시스템 안전망. 베이스 기본값은 바꾸지 않는다.
3. 시험 도구 확장(프로브 · `actions`)을 구현 범위에 넣고 대조군부터 돌린다.
4. S3 · S4 대조군은 재실행 목록에서 뺀다. `BP_P2_*_AutoStart` 2개는 **그대로 둔다**(2026-11-05 사용자 결정). 지우려면 `L_P2_Placed` 에 배치된 `BP_P2_Enemy_AutoStart` 인스턴스도 함께 정리해야 한다 — S2b 재실행의 `instances: 2` 가 이 두 번째 폰의 컨트롤러다.

## 2. 타깃 · 어그로 (`UAstralThreatComponent`)

## 3. 적 공격 실행 (텔레그래프 GA 전환 · 패링 → 경직 → 약점)

## 4. StateTree 연결 노드

## 5. `ST_Enemy_Melee` 구성

## 6. 스폰 · 콘텐츠 (적 PawnData · 메시 · 애니)

## 7. 네트워크 종료 조건 (3단계 테스트 · `IsPartyLeader`)
