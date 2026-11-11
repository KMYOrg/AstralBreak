# M3 적 AI 설계

작성일: 2026-11-05 · 대상: UE 5.7.4 · 기준 커밋: `6e2e2ee` · 앞 단계: [StateTree Phase2Report](../StateTree/Phase2Report.md) · 기획 원문: [game-plan.md](game-plan.md)
상태: **1번 설계 승인(2026-11-05, 권장안 그대로) · 구현 · 자동 검증 완료 · 커밋 `8b8a5fd`(2026-11-08). 남은 것 = V9 더미 사용자 눈 확인. 2번부터 미착수.** **2026-11-11 착수 전 검토를 반영했다 — [§0](#0-착수-전-검토-2026-11-11) 과 2 ~ 7번의 '설계 때 정할 것'.** **선행 단위(§7-1)는 구현 · 자동 검증 완료(2026-11-11, 미커밋) — PIE 1 ~ 3단계 수동 확인 대기.**

M3(일반 몬스터 AI · 어그로) 설계를 이 문서 하나에 순서대로 쌓는다. 앞 항목이 뒤 항목의 전제가 되도록 사용자와 순서를 합의했다. 생명주기를 어그로보다 먼저 정해야 그 위에 얹는 것을 다시 고치지 않는다.

| # | 항목 | 상태 |
| ---: | :--- | :--- |
| 1 | 적 생명주기 | **이 문서 §1 — 구현 · 검증 완료, 결과는 §1-7** |
| 2 | 타깃 · 어그로 (`UAstralThreatComponent`) | 미착수 |
| 3 | 적 공격 실행 (단발 GA 전환 · 수호병 패턴 5종 · 피격 반응 · 패링 → 경직 → 약점) | 미착수 |
| 4 | StateTree 연결 노드 | 미착수 |
| 5 | `ST_Enemy_Melee` 구성 | 미착수 |
| 6 | 스폰 · 콘텐츠 (적 PawnData · 메시 · 애니 · 스폰/디스폰 인터페이스) | 미착수 |
| 7 | 네트워크 종료 조건 (3단계 테스트 · `IsPartyLeader`) | 선행 단위만 [§7-1](#7-1-선행-단위--dedicated-에서-레이드-시작) — 구현 · 자동 검증 완료(2026-11-11, 미커밋), PIE 1 ~ 3단계 수동 확인 대기. 나머지 미착수 |

**기획 근거:** [game-plan.md](game-plan.md) — M3 절(2부)이 범위 · 종료 조건 · 확장 포인트 예약, 7-6 절(1부)이 수호병 역할 · 기본 패턴, 부록 C 가 옛 구현 방향 메모(StateTree 확정 근거 · 단발 GA · 첫 수직 단위 · `UAstralThreatComponent` API)다. 2번부터는 이 문서를 근거로 쓴다. 어그로 수치 규칙과 패턴별 수치는 원문에 없으므로 해당 항목 설계 때 사용자와 정한다.

> 2026-11-05 ~ 11-08 에는 "기획서 원문이 저장소에 없다 — 사용자가 제공한 뒤 쓴다"로 2번 이후를 막아 뒀다. 원문은 10-09 대화에 붙여넣어진 마일스톤 계획서에 있었고, 2026-11-10 game-plan.md 로 옮겼다.

**표기:** **[실측]** = 실행으로 확인했다. **[소스]** = 소스를 읽어 판단했고 실행하지 않았다. 근거의 파일 이름은 프로젝트 또는 엔진(`D:/UnrealSource/UnrealEngine-5.7.4-release/Engine`) 소스다. 시나리오 번호(S1 ~ S6)는 [Phase2Report §3](../StateTree/Phase2Report.md) 의 실행이고, C · V 번호는 §1-7 의 실행이다.

**항목 형식:** 결정 → 대안과 기각 이유 → 근거 → 영향 → 미해결.

## 0. 착수 전 검토 (2026-11-11)

2번 착수 전에 [game-plan.md](game-plan.md) 와 이 문서를 런타임 코드 · 엔진 소스와 대조했다. **이 절의 판단은 전부 [소스] 다 — 실행한 것은 없다**(맵의 NavMesh 볼륨만 파일에서 세었다). 사용자가 문서 반영을 지시했다(2026-11-11). 계획서 쪽 관찰은 [game-plan.md 부록 D](game-plan.md#부록-d-2026-11-11-착수-전-검토-메모).

### 0-1. 그대로 서는 전제

| 전제 | 근거 |
| :--- | :--- |
| §1 구현이 이 문서와 같다 | `AstralEnemyController.cpp` · `AstralCombatCharacter.cpp:45` ~ `:72` |
| 계획서 M3 예약 '몬스터 스탯 Attribute 기반' 은 이미 충족 | 적이 `UAstralHealthSet` · `UAstralCombatSet` 을 CDO 서브오브젝트로 갖는다(`AstralCombatCharacter.cpp:19` · `:20`) |
| 패링 → 경직 통지 경로가 있다 | `ResolveIncomingDamage` 가 공격자에게 `GameplayEvent.Staggered` 를 보낸다(`AstralCombatStatics.cpp:313`) |
| 위협의 입력이 될 이벤트가 있다 | `UAstralHealthSet::OnDamaged` 가 서버에서 가해자 · 피해량을 준다(`AstralHealthSet.cpp:137`) |
| 전투 맵에 경로 탐색이 된다 | `RaidMap` · `CombatTestMap` 에 `NavMeshBoundsVolume` 이 있다. `HubMap` · `TestMap` 에는 없다 |
| Dedicated 에서도 소켓 트레이스 전제가 선다 | 베이스 메시가 `AlwaysTickPoseAndRefreshBones` 다(`AstralCharacter.cpp:43`) |
| 서버 전용 GA 의 몽타주가 클라이언트에 보인다 | `RepAnimMontageInfo` 는 조건 없이 복제된다(`AbilitySystemComponent.cpp:1786`). 적 ASC 가 Minimal 모드여도 같다 |
| AI 스키마가 커스텀 Evaluator · 컴포넌트 외부 데이터를 받는다 | `StateTreeComponentSchema.cpp:40` · `:53` ~ `:55` |

### 0-2. 구현 순서 — 수직 단위로 자른다

**위 표의 1 ~ 7 은 설계 목차다. 구현은 이 순서로 하지 않는다.** 층별로 쌓으면 5번이 끝날 때까지 움직이는 적이 없어, 계획서의 '각 마일스톤 끝에서 플레이 가능' 원칙과 부록 C 의 '첫 수직 단위' 에 어긋난다. 항목 설계는 각 단위가 필요한 만큼만 먼저 쓴다.

| 단위 | 내용 | 끌어오는 항목 | 끝나면 보이는 것 |
| :--- | :--- | :--- | :--- |
| 선행 | Dedicated 에서 레이드 시작 — 방장 판정 교체 + `ServerSelectRaid` 맵 이름 검증. **구현 · 자동 검증 완료(2026-11-11, 미커밋 — [§7-1](#7-1-선행-단위--dedicated-에서-레이드-시작)). 1 ~ 3단계 파티 흐름(허브 → 레이드 → 허브 · 방장 이탈)은 자동 시험으로 [실측] 통과([§7-2](#7-2-네트워크-단계-자동-시험-p2--p5)). 히어로 전투를 3단계에서 훑는 P7 은 아직이다 — 이 칸의 '전투가 돈다' 는 그 뒤에 쓴다** | 7 의 일부 | 3단계 구성에서 히어로 전투(M1 · M2)가 돈다 |
| A | 최소 타깃(가장 가까운 생존 플레이어) + 추격 + 단발 공격 1종 + 트리. 판정은 기존 전방 스윕, 메시는 임시 | 2 최소 · 3 일부 · 4 · 5 최소 | 적 한 마리가 쫓아와 때리고, 맞으면 죽는다 |
| B | 어그로 규칙 · 4인 타깃 전환 | 2 | 여럿이 때리면 타깃이 바뀐다 |
| C | 공격 확장 · 피격 반응 · 패링 → 경직 | 3 | 방어 3종 연습이 된다 |
| D | 적 메시 · 애니 · PawnData · 스폰/디스폰 | 6 | 수호병 모습으로 여러 마리가 나온다 |
| E | 3단계 네트워크 전체 | 7 | M3 종료 조건 |

- **단위마다 네트워크 1 · 2단계를 돌린다.** 3단계는 선행 단위가 뚫은 뒤부터 단위마다 돌린다.
- **C 는 D 의 일부에 기댄다.** 몽타주 · 무기 트레이스 공격은 적 메시 · 스켈레톤이 정해져야 저작할 수 있는데 적 애셋이 지금 0개다. 메시 · 스켈레톤 선택만 C 앞으로 당긴다. A 는 몽타주 없이 기존 스윕(`ApplyDamageSweep`)으로 간다.

### 0-3. 3단계 네트워크를 끝에 몰지 않는다

`IsPartyLeader` 는 `HasAuthority() && IsLocalController()` 다(`AstralPlayerController.cpp:110`). Dedicated 에는 로컬 컨트롤러가 없어 `ServerSelectRaid` · `ServerStartRaid` · `ServerReturnToHub` 가 전부 거부된다. **즉 계획서 M1 의 종료 조건(3단계 통과)이 아직 충족되지 않았다.** 문서 기준으로 M2 히어로 전투의 Dedicated 실행 기록도 없다(§1-7 · Phase2Report §5 의 '돌리지 않은 것').

7번을 끝에 두면 M1 · M2 의 빚과 M3 의 버그가 한 번에 섞여, 계획서 M8 의 '마지막에 몰아서 고치면 어디서 시작된 문제인지 추적이 어렵다' 가 그대로 일어난다. 방장 판정은 AI 와 무관한 작은 작업이라 선행 단위로 당긴다. 구체 설계는 §7.

### 0-4. 기획 값은 잠정이다

**사용자 방침(2026-11-11):** 표식처럼 기획에 속하는 요소는 수시로 바뀌거나 없어질 수 있다.

이 문서에서의 적용(작성자 해석):

- 아래 '정할 것' 중 **기획** 으로 표시한 것은 항목 설계 때 잠정값으로 정한다. 값은 코드가 아니라 데이터(GA 프로퍼티 · GE · 태그)에 두어, 기획이 바뀌어도 구조를 뜯지 않게 한다.
- 원문 안에서 읽기가 갈리는 기획 개념은 이 문서가 풀지 않는다. M3 구현이 어느 한쪽 해석에 기대지 않게만 한다. 예: 수호병의 '원거리 전환 사용 이유'(game-plan 7-6)는 표식 해석에 달려 있고, M3 종료 조건(4인 처치 · 3단계 통과)에는 들어 있지 않다.

### 0-5. 정할 것 한눈에

| # | 정할 것 | 성격 | 현재 코드 | 다룰 곳 |
| ---: | :--- | :--- | :--- | :--- |
| 1 | 수호병 '패턴 5종' 을 공격 몇 개로 읽는가 | 기획 | 공격은 전방 스윕 1종 | §3 |
| 2 | 공격별 가드 · 패링 가능 여부를 어디에 싣는가 | 구조 | `Damage.Type.Unblockable` 하나가 둘을 함께 뚫는다. 데미지 GE 는 전역 1개 | §3 |
| 3 | 피격 반응 규칙(경직 내성) | 기획 + 구조 | 피격 반응 코드 0 | §3 |
| 4 | 일반 몬스터 '약점 노출' 의 실체 | 기획 | 일반 몬스터에 Break 게이지 없음 | §3 |
| 5 | 회피 무적 프레임 | 기획 | 없음(`AstralGA_Hero_Dodge.h:15` 주석 '범위 밖') | §3 |
| 6 | 죽은 플레이어 · 전원 사망 때 적의 행동 | 구조(최소) | 플레이어 부활은 디버그 `ReviveSelf` 뿐 | §2 |
| 7 | 클라이언트가 보는 공격 예고 | 구조 | 서버 루즈 태그 + DrawDebug 멀티캐스트 | §3 |
| 8 | 타깃을 트리에 넣는 경로 | 구조 | 없음 | §4 |
| 9 | 단발 GA 전환 뒤 `Staggered` 를 받는 주체 | 구조 | 상주 루프 GA 가 받는다 | §3 · §4 |
| 10 | 적이 타깃을 향해 도는 규칙 | 구조 + 기획 | 없음. 스윕은 액터 전방 기준 | §3 · §5 |
| 11 | 어그로 가중치 Modifier 노브의 위치 | 구조 | 없음 | §2 |

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

**바뀐 파일 (커밋 `8b8a5fd`)**

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

> 미착수. 아래는 설계가 아니라 **설계 때 정할 것** 이다(2026-11-11 검토, 전부 [소스]).

- **위협 입력은 이미 있는 이벤트로 받는다.** `UAstralHealthSet::OnDamaged` 가 서버에서 가해자 · 피해량을 준다(`AstralHealthSet.cpp:137`). 구독하면 되고 폴링이 필요 없다. 정리 시점은 `OnDeathStarted`(§1-8).
- **첫 인지(피해를 받기 전).** 거리 판정과 AIPerception 중 고른다. 단위 A 는 '가장 가까운 생존 플레이어' 로 시작한다. 컨트롤러 팀 동기화는 AIPerception 을 쓸 때만 필요하다 — 데미지 판정은 폰의 `TeamId` 를 본다(`AstralCombatStatics.cpp:58`).
- **죽은 플레이어 · 전원 사망.** 죽은 플레이어를 타깃에서 빼고, 남은 타깃이 없을 때 적이 무엇을 하는지 정한다. 플레이어 부활 · 전멸 규칙 자체는 계획서에 없다([game-plan 부록 D](game-plan.md#부록-d-2026-11-11-착수-전-검토-메모)) — 여기서는 타깃 제외까지만 다룬다.
- **레벨 배치의 첫 `EnterState`** 에 플레이어 폰이 없을 수 있다(§1-2 미해결).
- **컴포넌트를 폰과 컨트롤러 중 어디에 두는가.** 트리 노드가 외부 데이터로 받으려면 컨트롤러 쪽이어야 한다 — 스키마는 트리 소유자(컨트롤러)에서 `FindComponentByClass` 로 찾는다(`StateTreeComponentSchema.cpp:215`). 폰에 두면 컨텍스트 Actor 를 거쳐 찾아야 한다. §4 의 타깃 주입 방식과 함께 정한다.
- **Modifier 노브의 위치.** 계획서 예약 '어그로 가중치 Modifier 방식' 을 받을 배율을 어느 Attribute 세트에 둘지 정한다. 지금은 없다.
- **기획(잠정):** 무엇으로 위협을 쌓는지, 타깃 전환 조건, 전환 히스테리시스. 원문에 없다 — 사용자와 정한다.

## 3. 적 공격 실행 (단발 GA 전환 · 수호병 패턴 5종 · 피격 반응 · 패링 → 경직 → 약점)

> 미착수. 아래는 설계가 아니라 **설계 때 정할 것** 이다(2026-11-11 검토, 전부 [소스]).

- **'패턴 5종' 의 해석(기획 · 잠정).** game-plan 7-6 의 목록(기본 연타 / 짧은 돌진 / 가드 가능한 공격 / 패링 가능한 강공격 / 약점 노출 가능한 동작)은 공격과 속성이 섞여 있다. 공격 3개(연타 · 돌진 · 강공격) + 약점 노출 상태 1개로 읽을 수 있다. 사용자 확정 전까지 절 제목의 '5종' 은 원문 표기다.
- **공격별 가드 · 패링 가능 여부를 실을 자리가 없다.** `Damage.Type.Unblockable` 하나가 가드와 패링을 함께 뚫는다(`AstralCombatStatics.cpp:280`). 데미지 GE 는 GameData 전역 1개이고 `ApplyAttackHit` 는 공격별 태그를 받지 않는다. '가드 불가 · 패링 가능' 을 만들려면 태그를 둘로 나누고 스펙에 공격별 태그를 실어야 한다. 히어로 공격과 공유하는 경로라 상속 · 공용 영향을 함께 본다.
- **`Staggered` 를 받을 주체.** 지금은 상주 루프 GA 가 받는다(`AstralGA_Enemy_TelegraphAttack.cpp:29`). 단발 GA 는 끝나면 사라지므로, 이벤트로 발동하는 경직 GA 와 트리 쪽 대기(§4)가 필요하다.
- **피격 반응 규칙.** 피격 반응 코드가 없다. 맞을 때마다 경직하면 4인이 때리는 동안 적이 공격하지 못해 수호병의 '방어 연습' 역할이 사라진다. 경직 내성 규칙을 정한다(구조는 여기서, 수치는 기획 · 잠정).
- **'약점 노출' 의 실체(기획 · 잠정).** 일반 몬스터에는 Break 게이지가 없다. 최소안은 경직 중 `IncomingDamageMultiplier` 를 올리는 GE 다 — 이미 예약된 노브다.
- **적 회전.** `ApplyDamageSweep` 은 액터 전방 기준이다(`AstralCombatStatics.cpp:115`). 예고 중 타깃을 따라 돌다가 판정 전 어느 시점에 고정하는지가 패링 · 회피 감각을 정한다.
- **클라이언트가 보는 예고.** `State.Telegraphing` 은 서버의 루즈 태그이고(`AstralGA_Enemy_TelegraphAttack.cpp:63`) 표시는 DrawDebug 멀티캐스트다. 적 ASC 는 Minimal 모드다(`AstralCombatCharacter.cpp:17`). 계획서 M3 검증 리스크 1번(레이턴시 속 방어 타이밍)을 판정하려면 클라이언트가 보는 예고(몽타주 선딜 + GameplayCue)가 있어야 한다.
- **회피 무적 프레임(기획 · 잠정).** 지금은 없다. 적 공격이 처음 생기는 시점이라 위치 이탈만으로 갈지 여기서 정한다. 계획서 M7 의 '완벽 회피 보너스' 는 판정 지점을 전제한다.
- **더미의 `bTelegraphAttackEnabled`** 동작을 어떻게 유지할지(§1-8).

## 4. StateTree 연결 노드

> 미착수. 아래는 설계가 아니라 **설계 때 정할 것** 이다(2026-11-11 검토, 전부 [소스]).

- **타깃 주입은 두 안을 비교한다.** Phase2Report §6 의 4번은 커스텀 Evaluator 또는 Task 출력을 말했다. 다른 길이 하나 더 있다 — AI 스키마의 `AIControllerClass`(`StateTreeAIComponentSchema.h:37`)를 `AAstralEnemyController` 로 두면 컨트롤러의 프로퍼티를 `MoveTo.TargetActor` 에 직접 묶을 수 있다. 위협 컴포넌트가 타깃이 바뀔 때만 그 값을 갱신하면 매 틱 도는 노드 없이 단일 원천이 된다. 지침서 D-6 이 이미 '`AllowPrivateAccess` 또는 Evaluator 출력' 두 길을 열어 뒀다. 묶인 값이 실행 중인 `MoveTo` 에 언제 다시 복사되는지는 확인하지 않았다.
- **GA 실행 Task.** 태그로 활성화 → 종료 대기. `ExitState` 에서 취소하고, 사망 때는 이미 취소돼 있으므로 몇 번 불려도 같아야 한다(§1-8).
- **경직 대기.** 공격 GA 가 취소로 끝났을 때 트리가 경직이 풀릴 때까지 기다리는 수단(태그 조건 또는 이벤트 전환).

## 5. `ST_Enemy_Melee` 구성

> 미착수. 설계 때 Phase2Report §6 의 5 · 6 · 7번(`MoveTo` 실패 전환 · `AcceptableRadius` 와 공격 거리 · `Get Actor Location` 입력 확인)과 §1-8 의 '트리에 사망 상태를 두지 않는다' 를 그대로 받는다. 단위 A 는 타깃 없음 → 추격 → 공격 → 회복의 최소 트리다.

## 6. 스폰 · 콘텐츠 (적 PawnData · 메시 · 애니 · 스폰/디스폰 인터페이스)

> 미착수. 아래는 설계가 아니라 **설계 때 정할 것** 이다(2026-11-11 검토).

- **메시 · 스켈레톤 선택만 단위 C 앞으로 당긴다**(§0-2).
- **AI 활용 산출물을 남긴다.** 트리는 `state-tree-mcp` 로 저작하고 시나리오로 판정, 적 애니는 생성 · 애님 그래프 도구로 만든다. 무엇을 도구로 만들었고 어떻게 검증했는지를 이 절의 결과로 기록한다([game-plan 부록 D](game-plan.md#부록-d-2026-11-11-착수-전-검토-메모) 2번).
- §1 이 넘긴 것: `AutoPossessAI` · `AIControllerClass` · `GA_Death` 포함 AbilitySet, `SpawnDefaultController` 안전망, PawnData · 부여 지점(§1-5), `LifeSpan` 교체와 `DestroyAfterDeathDelay = 0`, 사망 중 폰 재빙의 금지(§1-3).

## 7. 네트워크 종료 조건 (3단계 테스트 · `IsPartyLeader`)

> 미착수. 아래는 설계가 아니라 **설계 때 정할 것** 이다(2026-11-11 검토, 전부 [소스]).

- **방장 판정은 선행 단위로 당겼다**(§0-2 · §0-3). 판정을 바꿀 때 `ServerSelectRaid` 의 맵 이름 무검증을 함께 막는다(game-plan 부록 B).
- `ServerTravel` 주소에 `?listen` 이 고정돼 있다(`AstralPlayerController.cpp:204` · `:216`). Dedicated 에서 문제가 되는지는 확인하지 않았다.
- **3단계는 단위마다 돌린다.** 이 절에 남는 것은 M3 종료 조건으로서의 전체 통과와, §1-7 에서 돌리지 않은 것(지연 스폰 · 신호 전 제거 · 트리 틱 안의 사망 · Development 구성 · 클라이언트 2개 이상)이다.

### 7-1. 선행 단위 — Dedicated 에서 레이드 시작

상태: **구현 · 자동 검증 완료(2026-11-11) · 미커밋. P1 ~ P6 [실측] 통과 — P2 ~ P5 는 [§7-2](#7-2-네트워크-단계-자동-시험-p2--p5) 의 자동 시험으로 돌렸다. 남은 것 = P7(전투 조작감, 사용자).** 아래 '결정' · '근거' 는 설계 때 [소스] 로 쓴 그대로 두었고, 실행으로 확인된 것은 §7-2 의 결과에 적었다. 구현 결과는 이 절의 [구현 결과](#구현-결과-2026-11-11).

#### 결론

**방장은 저장하지 않고 계산한다 — 참가 중인 플레이어 가운데 `PlayerId` 가 가장 작은 사람이다.** 가장 먼저 들어온 사람이라는 뜻이고, 리슨 서버에서는 호스트다. 넷 모드로 갈리는 코드가 없다.

| 질문 | 결정 |
| :--- | :--- |
| 방장이 누구인가 | 봇 · 관전자를 뺀 `PlayerArray` 에서 `PlayerId` 최소. 새 복제 프로퍼티 0 |
| 어디서 계산하는가 | `AAstralGameState::GetPartyLeader()`. 산술은 순수 함수로 떼어 자동 시험한다 |
| 권한 판정 | `AAstralPlayerController::IsPartyLeader()` 의 구현만 바꾼다. 호출처 3곳(`ServerSelectRaid` · `ServerStartRaid` · `ServerReturnToHub`)은 그대로다 |
| 방장이 나가면 | 다음으로 작은 `PlayerId` 가 방장이 된다. 인계 코드 없음 |
| 맵 이동 뒤 | 시임리스 이동이 `PlayerId` 를 옮기므로 유지된다 |
| 맵 이름 검증 | `AAstralGameMode` 에 허용 목록을 두고 `ServerSelectRaid` 가 정확히 일치하는 이름만 받는다 |
| `?listen` | 그대로 둔다 |

#### 결정

**① 방장 = `PlayerId` 최소.**

- `PlayerId` 는 로그인 때 서버가 프로세스 단위 증가 카운터로 매긴다(`GameModeBase.cpp:798` → `GameSession.cpp:276` · `:258`). 리슨 호스트도 같은 경로로 가장 먼저 받는다 — 지금의 '서버에서 로컬인 PC' 와 결과가 같다.
- 시임리스 이동은 컨트롤러와 PlayerState 를 새로 만들지만 `CopyProperties` 가 `PlayerId` 를 옮긴다(`GameModeBase.cpp:615` ~ `:620` · `PlayerState.cpp:117`). 프로젝트의 `CopyProperties` 오버라이드는 `Super` 를 먼저 부른다(`AstralPlayerState.cpp:105`).
- `PlayerId` 는 엔진이 이미 복제하므로 클라이언트도 같은 계산을 할 수 있다. 판정 권한은 서버 RPC 안에만 있고, 클라이언트의 값은 표시용이다(계획서 'UI 는 상태를 요청 · 표시만').

**② 계산 위치.** `AAstralGameState` 에 `GetPartyLeader() const` 하나를 둔다. `PlayerArray` 를 이미 갖고 있고 허브 · 레이드 양쪽의 베이스다. 후보 수집(봇 · 관전자 제외)은 여기서 하고, '최소 ID 고르기' 는 월드 없는 순수 함수(`AstralParty::SelectLeaderIndex`)로 뗀다 — `AstralTargeting` 과 같은 관용구다.

**③ `IsPartyLeader()`.** `GameState->GetPartyLeader() == PlayerState` 로 바꾼다. `HasAuthority() && IsLocalController()` 를 없앤다. 헤더의 'TODO: 데디 전환 시 교체 지점' 이 이 자리다.

**④ 맵 이름 검증.** `AAstralGameMode` 에 `RaidMapNames`(기본값 `{ "RaidMap" }`)와 `IsRaidMapAllowed()` 를 둔다. 이미 있는 `HubMapName` 과 같은 자리 · 같은 모양이다. `ServerSelectRaid` 는 방장 확인 뒤 이 목록과 정확히 일치하지 않으면 거부한다. 지금은 클라이언트가 보낸 문자열이 그대로 `ServerTravel` 주소가 된다(`AstralPlayerController.cpp:166` → `:204`) — 임의 맵이나 `?` 옵션을 실을 수 있다.

**⑤ `?listen` 은 그대로 둔다.** Dedicated 는 옵션이 없어도 리슨한다(`UnrealEngine.cpp:16182` 의 `!GIsClient`). 반대로 한 프로세스 PIE 의 서버 월드는 에디터 프로세스라 `GIsClient` 가 참이어서 이 옵션이 있어야 이동 뒤에도 리슨한다. 떼면 1단계가 깨질 수 있다.

**⑥ 눈으로 볼 수단.** 디버그 위젯의 파티 목록에 방장 표시를 한 줄 더하고(`AstralDebugWidget.cpp:127`), 방장 거부 로그에 현재 방장 이름을 싣는다.

#### 대안과 기각 이유

| 대안 | 기각 이유 |
| :--- | :--- |
| GameState 에 방장 포인터를 복제하고 GameMode 가 로그인 · 로그아웃 때 갱신 | 상태가 하나 늘고 세 곳(로그인 · 로그아웃 · 시임리스 도착)에서 맞춰야 한다. GameState 는 맵마다 다시 만들어져 이월 수단이 또 필요하다 |
| PlayerState 에 `bPartyLeader` 플래그 + `CopyProperties` 이월 | '한 명만 참' 이 여러 액터에 흩어진다. 방장 이탈 때 인계 코드가 필요하다 |
| `UAstralPartySubsystem` 에 방장의 UniqueNetId 저장 | PIE · Null OSS 에서 UniqueNetId 가 무효일 수 있다(`AstralPartySubsystem.h:21` 주석). 클라이언트는 이 값을 모른다 |
| Dedicated 만 분기(`IsRunningDedicatedServer` 면 첫 플레이어) | 넷 모드 분기가 남는다. 계획서가 피하라고 한 '리슨에서만 우연히 맞는 처리' 를 하나 더 만드는 셈이다 |
| 방장을 없애고 전원 준비 때 자동 시작 | 기획(방장이 퀘스트를 고른다)을 구현 사정으로 바꾸는 일이다. 기획이 바뀌면 그때 `IsPartyLeader` 한 곳만 고치면 된다 |
| 맵 검증을 퀘스트 DataAsset(`FPrimaryAssetId`)로 | `ServerSetLoadout` 과 같은 관용구라 모양은 좋다. 다만 M6 의 퀘스트 구조를 지금 정하게 된다 |
| 맵 목록을 `UAstralGameData` 에 | 전역 단일 참조만 두는 곳이고(`AstralGameData.h:26`), M6 에서 어차피 바뀐다 |
| `?` 문자만 거르기 | 옵션 주입은 막지만 임의 맵 이동은 못 막는다 |

#### 근거

- 로그인: `GameModeBase.cpp:798` · `GameSession.cpp:252` ~ `:276`. 시임리스: `GameModeBase.cpp:607` ~ `:642` · `PlayerState.cpp:117`.
- 리슨 조건: `UnrealEngine.cpp:16182`.
- 현재 판정과 호출처: `AstralPlayerController.cpp:110` · `:159` · `:185` · `:209`.
- 게임모드 BP 3개는 `HubMapName` 을 덮어쓰지 않고, 허브 · 레이드가 각각 `BP_AstralGameState_Hub` · `_Raid` 를 지정한다(애셋 문자열 검색). 두 BP 의 부모 클래스는 확인하지 않았다.

#### 영향

| 대상 | 변경 | 상속 · 공용 영향 |
| :--- | :--- | :--- |
| `AAstralGameState` | const 함수 1 | `AAstralHubGameState` 와 GameState BP 2개는 그대로 물려받는다 |
| 새 파일 1쌍(순수 함수) + 시험 1 | 추가 | 없음 |
| `AAstralPlayerController` | `IsPartyLeader` 구현, `ServerSelectRaid` 에 검증 한 단락, 거부 로그 | RPC 서명 불변 |
| `AAstralGameMode` | 프로퍼티 1 · 함수 1 | 게임모드 BP 3개가 기본값을 물려받는다. 애셋 수정 없음 |
| `UAstralDebugWidget` | 방장 표시 한 줄 | 없음 |
| 복제 | **새 프로퍼티 0** | |

- **리슨 서버의 동작은 바뀌지 않는다** — 호스트가 여전히 방장이다. 달라지는 것은 Dedicated 에서 방장이 생긴다는 것뿐이다.
- `SelectRaid CombatTestMap` 처럼 `RaidMap` 이 아닌 맵을 고르던 사용은 거부된다. 필요하면 게임모드 BP 의 목록에 더한다.

#### 미해결

- **하드 트래블이면 방장이 바뀔 수 있다.** 재접속 순서대로 `PlayerId` 를 다시 받는다. 지금은 `bUseSeamlessTravel = true` 라 이 경로가 없다.
- **나갔다 돌아온 방장은 방장을 되찾지 못한다.** 새 `PlayerId` 를 받기 때문이다. 수동 위임도 없다.
- **`PlayerId` 가 아직 0 인 순간.** PlayerState 는 `PlayerId` 를 받기 전에 `PlayerArray` 에 들어간다. 로그인 · 시임리스 교체 모두 한 호출 안에서 값이 채워지므로 그 사이에 RPC 가 끼지 않는다고 판단했다. 실행으로 확인할 것이다.
- **전환 맵(TransitionMap)이 설정에 없다.** `AstralGameMode.cpp:19` 주석은 지정이 필요하다고 적는다. Dedicated 시임리스 이동에서 문제가 되는지는 확인하지 않았다.
- **지나가다 본 것.** `AstralGameMode.cpp:113` 의 주석 'seamless 경로는 HandleStartingNewPlayer 를 타지 않으므로' 는 엔진 소스와 다르다 — `HandleSeamlessTravelPlayer` 가 끝에서 부른다(`GameModeBase.cpp:640`). 뒤따르는 보강은 가드 때문에 아무 일도 하지 않는다. 동작에는 영향이 없고, 이번에 주석만 고칠지는 사용자 판단이다.

#### 검증 계획

| # | 확인할 것 | 방법 | 판정 주체 | 결과 (2026-11-11) |
| :--- | :--- | :--- | :--- | :--- |
| P1 | 최소 ID 선택 · 봇/관전자 제외 · 빈 목록 · 방장 이탈 뒤 다음 사람 | `AstralBreak.Party.SelectLeader` 자동 시험 | 자동 | **[실측] 통과** (DebugGame 에디터). 동률 · 재입장 · 비방장 이탈도 같은 시험에 넣었다 |
| P2 | 1단계(리슨 · 한 프로세스): 호스트가 방장, 비방장 `SelectRaid` 거부, 허용 밖 맵 거부, `SetReady` → `StartRaid` → 도착 뒤 방장 유지 → `ReturnToHub` | PIE + 콘솔 명령 + 디버그 위젯 · 로그 | 사용자 | **[실측] 통과** — 자동 시험 `ListenPIE`(§7-2). 디버그 위젯 표시는 눈으로 보지 않았다 |
| P3 | 2단계(리슨 · 별도 프로세스): P2 와 같음 | 같음 | 사용자 | **[실측] 통과** — `run_party_flow.py listen`(§7-2) |
| P4 | 3단계(Dedicated): 먼저 들어온 클라이언트가 방장, P2 의 흐름 전체, 서버 로그에 `NM_DedicatedServer` | 같음 | 사용자 | **[실측] 통과** — 한 프로세스 `DedicatedPIE` + 실제 서버 프로세스 `run_party_flow.py dedicated`(§7-2). 넷 모드는 시험이 직접 확인한다(서버 `NM_DedicatedServer` · 로컬 컨트롤러 없음) |
| P5 | Dedicated 에서 방장 클라이언트가 나가면 다음 사람이 방장 | P4 중 방장 창을 닫는다 | 사용자 | **[실측] 통과** — `LeaderLeavesPIE`(접속 끊기) + `run_party_flow.py dedicated --scenario leader_leaves`(프로세스 종료)(§7-2) |
| P6 | 회귀 | `AstralBreak.` 전체 + Development · DebugGame 빌드 | 자동 | **[실측]** `AstralBreak.` 32/32 통과(새 시험 포함) · `AstralBreakEditor Win64` Development · DebugGame 둘 다 `Result: Succeeded`. 플러그인 2 파일을 건드려 `AnimGraphMcp.StateTree` 20/20 · `.Runner` 4/4 · `.Smoke` 26/26 도 함께 돌렸다(아래 '설계 밖 변경') |
| P7 | M2 히어로 전투를 3단계에서 한 번 훑는다(공격 · 회피 · 가드 · 패링 · 전환 · 사격 · 락온) | P4 로 레이드 맵에 들어간 김에 | 사용자. 문제는 목록만 적고 수정은 따로 판단한다 | 미실행 |

> 2026-11-11 뒤늦게 덧붙임: 아래 문단은 설계 때의 판단이다. 사용자 지시로 같은 날 수단을 만들었다 — [§7-2](#7-2-네트워크-단계-자동-시험-p2--p5).

**P2 ~ P5 를 자동으로 돌릴 수단이 지금은 없다.** 시나리오 러너는 월드가 바뀌면 `world_lost` 로 끝낸다(Phase2Report §1). §0-2 가 '3단계를 단위마다' 로 정했으므로 반복할 수단이 필요해질 텐데, 이 단위에서는 수동으로 확인하고 도구 확장은 단위 A 설계 때 판단하는 것을 권한다.

#### 구현 결과 (2026-11-11)

**바뀐 것.** 설계 ① ~ ⑥ 그대로다. 새 복제 프로퍼티 0 · BP 애셋 수정 0 · RPC 서명 불변 · `?listen` 유지.

| 파일 | 내용 |
| :--- | :--- |
| `GameModes/AstralPartyStatics.h` · `.cpp` (새 파일) | `FAstralPartyMember`(PlayerId · 봇 · 관전자) + `AstralParty::SelectLeaderIndex` |
| `GameModes/AstralGameState.h` · `.cpp` | `GetPartyLeader() const` — `PlayerArray` 수집 뒤 위 함수 호출 |
| `Player/AstralPlayerController.h` · `.cpp` | `IsPartyLeader()` 교체, `ServerSelectRaid` 맵 검증, 거부 로그 3곳에 현재 방장 |
| `GameModes/AstralGameMode.h` · `.cpp` | `RaidMapNames`(기본 `{ "RaidMap" }`) · `IsRaidMapAllowed()` |
| `UI/Debug/AstralDebugWidget.cpp` | `[Party]` 에 `Leader: id N (ME)` 한 줄, 목록 행에 `*`(방장) · `>`(나) · `(id N)` |
| `Tests/AstralPartyStaticsTests.cpp` (새 파일) | `AstralBreak.Party.SelectLeader` |

**설계가 정하지 않아 구현하며 고른 것(작성자 판단).**

- **관전자 = `IsOnlyASpectator()`.** `IsSpectator()` 는 일시 상태라, 이쪽을 쓰면 나중에 '죽으면 관전' 같은 것이 생길 때 방장이 넘어간다. 지금 프로젝트에는 관전 경로가 없어 둘의 결과는 같다 [소스].
- **'정확히 일치' = 대소문자까지.** `FString ==` 는 대소문자를 무시하므로 `Equals(…, CaseSensitive)` 로 비교한다. `SelectRaid raidmap` 은 거부된다.
- **`PlayerId` 동률은 배열 앞쪽.** 시임리스 교체 한 호출 안에서 옛 · 새 PlayerState 가 같은 ID 로 잠깐 겹친다(`GameModeBase.cpp:607` ~ `:642`) [소스].
- **`ServerReturnToHub` 도 거부 로그를 남긴다.** 전에는 조용히 반환했다. 비방장 거부를 로그로 확인하려면 필요하다.
- **로그 · 위젯에서 사람을 가리키는 키는 `PlayerId` 다.** PlayerState 액터 이름은 프로세스마다 달라 창끼리 맞춰 볼 수 없다. `PlayerId` 는 프로세스 단위 카운터라 PIE 를 다시 돌리면 256 부터 다시 시작하지 않는다(`GameSession.cpp:258`) — '256' 이 아니라 '가장 작은 값' 으로 읽는다.

**수동 확인 때 볼 문장.** 서버 로그(`LogAstral`):

- `ServerSelectRaid: 방장이 아님 — 거부 (<PC>, 현재 방장 = <PlayerState> (PlayerId N))` · `ServerStartRaid: …` · `ServerReturnToHub: …` 같은 꼴
- `ServerSelectRaid: 허용 목록에 없는 맵 '<이름>' — 거부 (<PC>)`
- 이동 때 `[GameMode] HandleSeamlessTravelPlayer: …` 가 사람 수만큼. `ProcessServerTravel: Seamless travel is disabled in PIE` 가 보이면 하드 트래블이라 '미해결' 첫 항목(방장이 바뀔 수 있음)에 해당한다 — `DefaultEngine.ini` 에 `net.AllowPIESeamlessTravel=true` 가 있어 나오지 않아야 한다 [소스]

**설계 밖 변경 — 플러그인 유니티 빌드 이름 충돌 2건.** 선행 단위와 무관하지만 두 구성 빌드가 이것 때문에 `Result: Failed` 였다 [실측]. 커밋을 나눌지는 사용자 판단이다.

- 원인: `27702fc` ~ `8b8a5fd` 에서 커밋된 플러그인 파일들이 git 작업 집합에서 빠지자 adaptive non-unity 의 제외 대상이 아니게 돼 `Module.AnimGraphMcpEditor.4.cpp` 로 합쳐졌다. ① `AnimMcpTools_StateTree.cpp` 와 `AnimMcpTools_Graph.cpp` 가 같은 익명 네임스페이스에 `OperationsDoc` 를 정의(C2374), ② `AnimMcpStateTreeTests.cpp` 의 전역 범위 `Step(…)` 호출 6곳이 `AnimMcpRuntimeTests.cpp` 의 익명 네임스페이스 `Step` 과 모호(C2668).
- 수정(이름만, 동작 · 문자열 불변): `AnimMcpTools_StateTree.cpp` 의 `OperationsDoc` → `StateTreeOperationsDoc`(정의 1 · 사용 2), `AnimMcpStateTreeTests.cpp` 의 6곳을 `AnimMcpStateTreeTests::Step(…)` 으로 한정.
- 확인 [실측]: 수정 뒤에는 두 파일이 다시 작업 집합에 들어가 따로 컴파일되므로, 평소 빌드만으로는 '커밋 뒤' 를 증명하지 못한다. `-DisableAdaptiveUnity` 로 Development 를 한 번 빌드해 수정한 파일까지 유니티로 합친 상태에서 `Result: Succeeded` 를 확인했다(선행 단위의 새 파일도 이때 유니티에 들어갔다). DebugGame 은 이 형태로 빌드하지 않았다.
- **'깨끗한 main 도 같은 실패' 는 추론이다 [소스].** main 을 따로 체크아웃해 빌드하지 않았다. 근거는 실패한 유니티 파일에 이 단위의 파일이 하나도 없고, 충돌한 4 파일이 `HEAD` 와 같았다는 것이다.

### 7-2. 네트워크 단계 자동 시험 (P2 ~ P5)

상태: **설계 승인(2026-11-11, 사용자 — "둘 다 진행") · 구현 · 검증 완료 · 미커밋. 결과는 이 절 끝의 [결과](#결과-2026-11-11).** §7-1 의 'P2 ~ P5 를 자동으로 돌릴 수단이 없다' 를 이 절이 대신한다. 단위 A 때 판단하려던 '3단계 반복 수단' 을 선행 단위로 당긴 것이다.

#### 결론

| 구성 | 수단 | 덮는 것 |
| :--- | :--- | :--- |
| 한 프로세스(1단계 리슨 · Dedicated PIE) | 에디터 자동 시험 `AstralBreak.Net.PartyFlow.*` — 멀티 PIE 를 띄우고 각 클라이언트 컨트롤러로 실제 RPC 를 보낸다 | P2 · P4(한 프로세스) · P5 |
| 별도 프로세스(2단계 리슨 · 실제 Dedicated) | 프로세스마다 Gauntlet 시험 컨트롤러 + 실행 스크립트 `Tools/net_test/run_party_flow.py` | P3 · P4(실제 서버 프로세스) · P5 |
| 조작감 | 사용자 | P7 |

#### 결정

**① 한 프로세스는 자동 시험으로.** 한 프로세스 PIE 는 서버 · 클라이언트 월드가 모두 에디터 안에 있어 시험이 양쪽을 직접 본다. 요청은 클라이언트 월드의 컨트롤러에서 `Server*` RPC 를 부르므로 실제 넷 드라이버를 탄다. 거부는 '상태가 안 바뀜' 과 '거부 경고 로그가 정해진 횟수만큼 나옴'(`AddExpectedError`) 둘로 판정한다. 시임리스 이동은 '이동 뒤 `PlayerId` 집합이 그대로' 로 판정한다 — 하드 트래블이면 새 번호를 받는다(`GameSession.cpp:258`).

**② 별도 프로세스는 프로세스마다 스스로 도는 컨트롤러로.** `-ExecCmds` 는 접속 · 이동 시점을 맞출 수 없어 쓰지 않는다. 엔진 Gauntlet 런타임 컨트롤러(`-gauntlet=`)는 맵이 바뀌어도 살아 있고 끝날 때 `**** TEST COMPLETE. EXIT CODE: N ****` 을 남긴다(`GauntletTestController.cpp:81`). 각 프로세스는 복제된 상태만 보고 역할(방장 · 비방장 · 서버)을 정한다. 프로세스 사이 순서는 `bIsReady` 로 맞춘다 — 비방장은 '거부당할 요청' 을 먼저 보낸 뒤 준비를 켜고, 방장은 전원 준비를 본 뒤 다음으로 간다. `bIsReady` 는 이동 때 넘어가지 않아(`AstralPlayerState.cpp:103`) 맵마다 다시 쓸 수 있다.

**③ 판정은 표준 출력으로.** Windows 에서 종료 코드가 그대로 전달되는지 확인하지 않았다(`WindowsPlatformMisc.cpp:1366`). 실행 스크립트는 각 프로세스의 `ASTRAL_NETTEST RESULT PASS|FAIL` 줄과 서버 출력의 거부 로그 줄 수로 판정한다. 로그는 `Saved/Logs` 가 아니라 `-stdout -FullStdOutLogOutput` 로 받는다.

**④ 코드는 전부 `AstralBreakEditor`(UncookedOnly)에 둔다.** 런타임 모듈은 건드리지 않는다. UncookedOnly 모듈은 에디터 실행 파일의 `-game` · `-server` 에서도 올라간다(`ModuleDescriptor.cpp:707`). 대가는 쿠킹된 빌드에서는 이 시험을 못 돈다는 것이다.

#### 대안과 기각 이유

| 대안 | 기각 이유 |
| :--- | :--- |
| 시나리오 러너(`run_state_tree_scenario`) 확장 | 월드가 바뀌면 끝나는 구조이고 StateTree 관측용이다. 파티 흐름은 프로젝트 고유 규칙이라 범용 도구에 넣을 것이 아니다 |
| Gauntlet 전체(UAT `RunUnreal` + C# 노드) | 정석이지만 C# 자동화 프로젝트가 따로 필요하다. 지금은 런타임 컨트롤러만 쓰고, 같은 컨트롤러를 나중에 UAT 에 물릴 수 있게 둔다 |
| 직접 만든 서브시스템(Gauntlet 없이) | 플러그인을 켜지 않아도 되지만 같은 것을 다시 만드는 일이다 |
| 컨트롤러를 런타임 모듈에 | 게임 모듈이 시험 플러그인에 의존하게 된다 |
| 프로세스 사이 순서를 시간으로 | 느린 기기에서 거짓 통과 · 거짓 실패가 난다 |

#### 영향

- `AstralBreak.uproject` 에 Gauntlet 플러그인(엔진 Beta)이 켜진다. `-gauntlet=` 인자가 없으면 컨트롤러를 만들지 않는다(`GauntletModule.cpp:184`).
- `AstralBreakEditor` 가 `Gauntlet` 에 의존한다. 모듈 주석의 '애님 그래프 노드만' 은 '에디터 · 미쿠킹 전용 코드' 로 넓어진다.
- `AstralBreak.` 필터로 전체를 돌리면 PIE 시험 3개가 함께 돈다(수십 초 추가).

#### 미해결

- 쿠킹된 Dedicated 서버 빌드는 범위 밖이다(④).
- 2 ~ 4 프로세스를 같은 PC 에서 돌린다 — 지연 · 패킷 손실은 넣지 않는다.
- 사람 수는 흐름 2명 · 방장 이탈 3명으로만 돌렸다. 4인은 `--players 4` 로 돌릴 수 있게만 해 두었다(실행하지 않았다).

#### 결과 (2026-11-11)

전부 **[실측]** 이다. 최종 빌드(Development · DebugGame 둘 다 `Result: Succeeded`, Development 는 `-DisableAdaptiveUnity` 로도 한 번) 뒤에 다시 돌린 값이다.

| 구성 | 실행 | 결과 |
| :--- | :--- | :--- |
| 리슨 · 한 프로세스 (P2) | `AstralBreak.Net.PartyFlow.ListenPIE` | 통과 |
| Dedicated · 한 프로세스 (P4) | `AstralBreak.Net.PartyFlow.DedicatedPIE` | 통과 |
| Dedicated · 한 프로세스 · 방장 이탈 (P5) | `AstralBreak.Net.PartyFlow.LeaderLeavesPIE` (3명) | 통과 |
| 리슨 · 별도 프로세스 (P3) | `run_party_flow.py listen` (호스트 + 클라이언트 1) | 통과 — 검사 9/9, 45초 |
| Dedicated · 별도 프로세스 (P4) | `run_party_flow.py dedicated` (서버 + 클라이언트 2), DebugGame · Development 각 1회 | 통과 — 검사 10/10, 46 ~ 49초 |
| Dedicated · 별도 프로세스 · 방장 이탈 (P5) | `run_party_flow.py dedicated --scenario leader_leaves` (서버 + 클라이언트 3) | 통과 — 검사 6/6, 43초 |
| 회귀 | `AstralBreak.` 전체 | 35/35 (PIE 시험 3개 포함 22초) |

흐름 시험 하나가 확인하는 것: 방장 = 최소 `PlayerId`(리슨에서는 호스트) · 클라이언트가 복제된 번호로 같은 방장을 계산 · 비방장의 선택 · 시작 · 복귀 거부 · 허용 밖 맵 2종 거부(임의 맵 · `?game=` 옵션 주입) · 준비 전 시작 거부 · 허브 → 레이드 → 허브 이동 뒤 번호와 방장 유지 · 서버 넷 모드 유지.

**시험이 실패할 수 있는가 — 대조 실험 3건.** 통과만 본 시험은 믿을 수 없어, 일부러 깨뜨려 떨어지는지 봤다(확인 뒤 원복).

| 깨뜨린 것 | 실행 | 결과 |
| :--- | :--- | :--- |
| `IsPartyLeader()` 를 수정 전(`HasAuthority() && IsLocalController()`)으로 | `run_party_flow.py dedicated` | **실패** — 방장의 맵 선택이 4번 모두 '방장이 아님' 으로 거부, 이동 0회. §0-3 이 [소스] 로 적은 'Dedicated 에서 레이드를 시작할 수 없다' 의 재현이다 |
| 같음 | `DedicatedPIE` / `ListenPIE` | Dedicated **실패**(선택이 반영되지 않아 제한 시간 초과) / 리슨 통과 — 수정 전 코드가 리슨에서만 맞았다는 것과 일치 |
| 시험의 거부 로그 기대 횟수를 1 → 2 로 | `ListenPIE` | **실패** — '2번 기대, 1번 발견'. 횟수 검사가 실제로 적용된다 |

**이 시험으로 §7-1 에서 닫힌 것.**

- **⑤ `?listen` 유지:** 실제 Dedicated 프로세스와 리슨 호스트 프로세스 모두 두 번의 이동 뒤에도 클라이언트 접속이 유지됐다. `?listen` 을 뗀 경우는 돌리지 않았다 — '떼면 1단계가 깨진다' 는 여전히 [소스] 다.
- **미해결 '전환 맵이 설정에 없다':** 전환 맵 없이 실제 Dedicated 프로세스에서 시임리스 이동이 됐다(서버가 `HandleSeamlessTravelPlayer` 를 사람 수 x 2 번 처리, 번호 유지).
- **방장은 접속 순서로 정해진다:** 방장 이탈 실행에서 마지막에 띄운 클라이언트가 먼저 접속해 방장이 됐다. 프로세스를 띄운 순서와는 무관하다.

**다시 돌리는 법.** 에디터를 내리고(프로세스 3 ~ 4개가 뜬다) 저장소 루트에서:

```
Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/net_test/run_party_flow.py listen
Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/net_test/run_party_flow.py dedicated
Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/net_test/run_party_flow.py dedicated --scenario leader_leaves
```

프로세스별 로그와 `result.json` 은 `Tools/mcp/results/net_test/<시각>_<구성>_<시나리오>/`(git 제외)에 남는다. 한 프로세스 쪽은 에디터에서 `AstralBreak.Net` 필터로 돈다.

**바뀐 것.** 런타임 모듈 변경 0.

| 파일 | 내용 |
| :--- | :--- |
| `Source/AstralBreakEditor/Private/Tests/AstralPartyFlowPieTests.cpp` (새 파일) | 멀티 PIE 시험 3개 |
| `Source/AstralBreakEditor/Private/Tests/AstralPartyFlowTestController.h` · `.cpp` (새 파일) | 프로세스별 Gauntlet 컨트롤러 |
| `Tools/net_test/run_party_flow.py` (새 파일) | 서버 + 클라이언트 실행 · 판정 |
| `Source/AstralBreakEditor/AstralBreakEditor.Build.cs` | `Gauntlet` 의존, 모듈 주석 |
| `AstralBreak.uproject` | Gauntlet 플러그인 켬 |

**돌리지 않은 것.** 플러그인 회귀 중 `AnimGraphMcp.StateTree` · `.Smoke` 는 이 절 작업 뒤에 다시 돌리지 않았다(플러그인 코드는 §7-1 의 이름 수정 뒤 그대로이고, `.Runner` 4/4 만 다시 돌렸다). 4인 구성 · 쿠킹 빌드 · 지연이 있는 망.
