# M3 적 AI 설계

작성일: 2026-11-05 · 대상: UE 5.7.4 · 기준 커밋: `6e2e2ee` · 앞 단계: [StateTree Phase2Report](../StateTree/Phase2Report.md) · 기획 원문: [game-plan.md](game-plan.md)
상태: **1번 설계 승인(2026-11-05, 권장안 그대로) · 구현 · 자동 검증 완료 · 커밋 `8b8a5fd`(2026-11-08). 남은 것 = V9 더미 사용자 눈 확인. 2번부터 미착수.** **2026-11-11 착수 전 검토를 반영했다 — [§0](#0-착수-전-검토-2026-11-11) 과 2 ~ 7번의 '설계 때 정할 것'.** **선행 단위(§7-1 · §7-2)는 구현 · 검증 완료 · 커밋 `0e04049`(2026-11-11) — 남은 것 = P7(사용자).** **단위 A([§8](#8-단위-a--쫓아와-때리는-적-한-마리))는 구현 · 자동 검증 완료 · 커밋 `dbe2fd1`(2026-11-11) · A11 조작감 사용자 확인 완료(2026-11-11).** **단위 B([§9](#9-단위-b--여럿이-때리면-타깃이-바뀐다))는 구현 · 자동 검증 완료 · 커밋 `29d963c`(2026-11-12).** **단위 C 는 C1 · C2 로 나눴다 — C1 은 [§10](#10-단위-c--수호병의-모습과-공격) 구현 · 자동 검증 완료 · 커밋 `ff2ffa9`(2026-11-12). C2 는 같은 절에 잠정안으로 설계 · 구현 · 자동 검증 완료(2026-11-12, 미커밋) · H7 눈 확인 사용자 완료(2026-11-12).** **단위 D 는 [§11](#11-단위-d--수호병-여러-마리가-나온다) 설계안 — 사용자 승인 대기.**

M3(일반 몬스터 AI · 어그로) 설계를 이 문서 하나에 순서대로 쌓는다. 앞 항목이 뒤 항목의 전제가 되도록 사용자와 순서를 합의했다. 생명주기를 어그로보다 먼저 정해야 그 위에 얹는 것을 다시 고치지 않는다.

| # | 항목 | 상태 |
| ---: | :--- | :--- |
| 1 | 적 생명주기 | **이 문서 §1 — 구현 · 검증 완료, 결과는 §1-7** |
| 2 | 타깃 · 어그로 (`UAstralThreatComponent`) | 미착수 |
| 3 | 적 공격 실행 (단발 GA 전환 · 수호병 패턴 5종 · 피격 반응 · 패링 → 경직 → 약점) | 미착수 |
| 4 | StateTree 연결 노드 | 미착수 |
| 5 | `ST_Enemy_Melee` 구성 | 미착수 |
| 6 | 스폰 · 콘텐츠 (적 PawnData · 메시 · 애니 · 스폰/디스폰 인터페이스) | 미착수 |
| 7 | 네트워크 종료 조건 (3단계 테스트 · `IsPartyLeader`) | 선행 단위만 [§7-1](#7-1-선행-단위--dedicated-에서-레이드-시작) · [§7-2](#7-2-네트워크-단계-자동-시험-p2--p5) — 구현 · 검증 완료 · 커밋 `0e04049`, P7(사용자)만 남음. 나머지 미착수 |
| 8 | 단위 A (2 최소 · 3 일부 · 4 · 5 최소를 한 번에) | [§8](#8-단위-a--쫓아와-때리는-적-한-마리) — 구현 · 자동 검증 완료 · 커밋 `dbe2fd1`, A11 조작감 사용자 확인 완료 |
| 9 | 단위 B (2 의 나머지 — 어그로 규칙 · 타깃 전환) | [§9](#9-단위-b--여럿이-때리면-타깃이-바뀐다) — 구현 · 자동 검증 완료 · 커밋 `29d963c` |
| 10 | 단위 C (3 의 나머지 + 6 의 메시 · 애니) — C1 모습 · 몽타주 공격 / C2 공격 확장 · 방어 규칙 | [§10](#10-단위-c--수호병의-모습과-공격) — C1 구현 · 자동 검증 완료 · 커밋 `ff2ffa9`, C2 잠정안으로 구현 · 자동 검증 완료(2026-11-12, 미커밋) · H7 눈 확인 사용자 완료 |
| 11 | 단위 D (6 의 나머지 — 스폰 · 여러 마리) | [§11](#11-단위-d--수호병-여러-마리가-나온다) — 설계안 · 사용자 승인 대기 |

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
| 선행 | Dedicated 에서 레이드 시작 — 방장 판정 교체 + `ServerSelectRaid` 맵 이름 검증. **구현 · 자동 검증 완료(2026-11-11, 커밋 `0e04049` — [§7-1](#7-1-선행-단위--dedicated-에서-레이드-시작)). 1 ~ 3단계 파티 흐름(허브 → 레이드 → 허브 · 방장 이탈)은 자동 시험으로 [실측] 통과([§7-2](#7-2-네트워크-단계-자동-시험-p2--p5)). 히어로 전투를 3단계에서 훑는 P7 은 아직이다 — 이 칸의 '전투가 돈다' 는 그 뒤에 쓴다** | 7 의 일부 | 3단계 구성에서 히어로 전투(M1 · M2)가 돈다 |
| A | 최소 타깃(가장 가까운 생존 플레이어) + 추격 + 단발 공격 1종 + 트리. 판정은 기존 전방 스윕, 메시는 임시. **구현 · 자동 검증 완료(커밋 `dbe2fd1`) — [§8](#8-단위-a--쫓아와-때리는-적-한-마리)** | 2 최소 · 3 일부 · 4 · 5 최소 | 적 한 마리가 쫓아와 때리고, 맞으면 죽는다 |
| B | 어그로 규칙 · 4인 타깃 전환. **구현 · 자동 검증 완료(미커밋) — [§9](#9-단위-b--여럿이-때리면-타깃이-바뀐다)** | 2 | 여럿이 때리면 타깃이 바뀐다 |
| C | 공격 확장 · 피격 반응 · 패링 → 경직. **2026-11-12 C1(메시 · 로코모션 · 몽타주 공격 1종 · 사망 모습) / C2(공격 여러 종 · 피격 반응 · 방어 규칙)로 나눴다 — [§10](#10-단위-c--수호병의-모습과-공격)** | 3 · 6 일부 | 방어 3종 연습이 된다 |
| D | PawnData · 스폰/디스폰(적 메시 · 애니는 C1 로 옮겼다) | 6 | 수호병 모습으로 여러 마리가 나온다 |
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

> 미착수. 아래는 설계가 아니라 **설계 때 정할 것** 이다(2026-11-11 검토, 전부 [소스]). **단위 A 가 먼저 정한 것(타깃의 단일 원천 · 컴포넌트 위치 · 죽은 타깃 제외)은 [§8](#8-단위-a--쫓아와-때리는-적-한-마리) ① · ②. 나머지(선정 규칙 · 위협 입력 · Modifier 노브 · 인지 범위)는 단위 B 설계안 [§9](#9-단위-b--여럿이-때리면-타깃이-바뀐다).**

- **위협 입력은 이미 있는 이벤트로 받는다.** `UAstralHealthSet::OnDamaged` 가 서버에서 가해자 · 피해량을 준다(`AstralHealthSet.cpp:137`). 구독하면 되고 폴링이 필요 없다. 정리 시점은 `OnDeathStarted`(§1-8).
- **첫 인지(피해를 받기 전).** 거리 판정과 AIPerception 중 고른다. 단위 A 는 '가장 가까운 생존 플레이어' 로 시작한다. 컨트롤러 팀 동기화는 AIPerception 을 쓸 때만 필요하다 — 데미지 판정은 폰의 `TeamId` 를 본다(`AstralCombatStatics.cpp:58`).
- **죽은 플레이어 · 전원 사망.** 죽은 플레이어를 타깃에서 빼고, 남은 타깃이 없을 때 적이 무엇을 하는지 정한다. 플레이어 부활 · 전멸 규칙 자체는 계획서에 없다([game-plan 부록 D](game-plan.md#부록-d-2026-11-11-착수-전-검토-메모)) — 여기서는 타깃 제외까지만 다룬다.
- **레벨 배치의 첫 `EnterState`** 에 플레이어 폰이 없을 수 있다(§1-2 미해결).
- **컴포넌트를 폰과 컨트롤러 중 어디에 두는가.** 트리 노드가 외부 데이터로 받으려면 컨트롤러 쪽이어야 한다 — 스키마는 트리 소유자(컨트롤러)에서 `FindComponentByClass` 로 찾는다(`StateTreeComponentSchema.cpp:215`). 폰에 두면 컨텍스트 Actor 를 거쳐 찾아야 한다. §4 의 타깃 주입 방식과 함께 정한다.
- **Modifier 노브의 위치.** 계획서 예약 '어그로 가중치 Modifier 방식' 을 받을 배율을 어느 Attribute 세트에 둘지 정한다. 지금은 없다.
- **기획(잠정):** 무엇으로 위협을 쌓는지, 타깃 전환 조건, 전환 히스테리시스. 원문에 없다 — 사용자와 정한다.

## 3. 적 공격 실행 (단발 GA 전환 · 수호병 패턴 5종 · 피격 반응 · 패링 → 경직 → 약점)

> 미착수. 아래는 설계가 아니라 **설계 때 정할 것** 이다(2026-11-11 검토, 전부 [소스]). **단위 A 의 단발 공격 1종 · 회전 · 경직 임시 처리는 [§8](#8-단위-a--쫓아와-때리는-적-한-마리) ④ · ⑤.**

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

> 미착수. 아래는 설계가 아니라 **설계 때 정할 것** 이다(2026-11-11 검토, 전부 [소스]). **타깃 주입 · GA 실행 Task 는 [§8](#8-단위-a--쫓아와-때리는-적-한-마리) ① · ③ 이 정했다. 경직 대기는 단위 C 에 남는다.**

- **타깃 주입은 두 안을 비교한다.** Phase2Report §6 의 4번은 커스텀 Evaluator 또는 Task 출력을 말했다. 다른 길이 하나 더 있다 — AI 스키마의 `AIControllerClass`(`StateTreeAIComponentSchema.h:37`)를 `AAstralEnemyController` 로 두면 컨트롤러의 프로퍼티를 `MoveTo.TargetActor` 에 직접 묶을 수 있다. 위협 컴포넌트가 타깃이 바뀔 때만 그 값을 갱신하면 매 틱 도는 노드 없이 단일 원천이 된다. 지침서 D-6 이 이미 '`AllowPrivateAccess` 또는 Evaluator 출력' 두 길을 열어 뒀다. 묶인 값이 실행 중인 `MoveTo` 에 언제 다시 복사되는지는 확인하지 않았다.
- **GA 실행 Task.** 태그로 활성화 → 종료 대기. `ExitState` 에서 취소하고, 사망 때는 이미 취소돼 있으므로 몇 번 불려도 같아야 한다(§1-8).
- **경직 대기.** 공격 GA 가 취소로 끝났을 때 트리가 경직이 풀릴 때까지 기다리는 수단(태그 조건 또는 이벤트 전환).

## 5. `ST_Enemy_Melee` 구성

> 미착수. 설계 때 Phase2Report §6 의 5 · 6 · 7번(`MoveTo` 실패 전환 · `AcceptableRadius` 와 공격 거리 · `Get Actor Location` 입력 확인)과 §1-8 의 '트리에 사망 상태를 두지 않는다' 를 그대로 받는다. 단위 A 는 타깃 없음 → 추격 → 공격 → 회복의 최소 트리다 — 구성은 [§8](#8-단위-a--쫓아와-때리는-적-한-마리) ⑥.

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

상태: **구현 · 자동 검증 완료(2026-11-11) · 커밋 `0e04049`. P1 ~ P6 [실측] 통과 — P2 ~ P5 는 [§7-2](#7-2-네트워크-단계-자동-시험-p2--p5) 의 자동 시험으로 돌렸다. 남은 것 = P7(전투 조작감, 사용자).** 아래 '결정' · '근거' 는 설계 때 [소스] 로 쓴 그대로 두었고, 실행으로 확인된 것은 §7-2 의 결과에 적었다. 구현 결과는 이 절의 [구현 결과](#구현-결과-2026-11-11).

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

상태: **설계 승인(2026-11-11, 사용자 — "둘 다 진행") · 구현 · 검증 완료 · 커밋 `0e04049`. 결과는 이 절 끝의 [결과](#결과-2026-11-11).** §7-1 의 'P2 ~ P5 를 자동으로 돌릴 수단이 없다' 를 이 절이 대신한다. 단위 A 때 판단하려던 '3단계 반복 수단' 을 선행 단위로 당긴 것이다.

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

## 8. 단위 A — 쫓아와 때리는 적 한 마리

상태: **설계 승인(2026-11-11, 사용자 — 설계안 그대로) · 구현 · 자동 검증 완료 · 커밋 `dbe2fd1`. A11 조작감은 사용자가 확인했다(2026-11-11 — 값 변경 요청 없음).** 아래 '결론' ~ '검증 계획' 은 설계 때 [소스] 로 쓴 그대로 두었고, 실행으로 확인된 것은 [구현 결과](#구현-결과-2026-11-11-1)에 있다. 마스터 세션이 변경 코드를 설계 ① ~ ⑧ 과 대조해 일치를 확인했다(2026-11-11 — 시험을 다시 돌리지는 않았다). 실행으로 먼저 확인할 것은 [검증 계획](#검증-계획-1)의 A0 로 모았다. §0-2 의 단위 A 이고, 목차의 2(최소) · 3(일부) · 4 · 5(최소)를 이 단위가 필요한 만큼만 정한다.

끝나면 보이는 것: **적 한 마리가 가장 가까운 플레이어를 쫓아와 예고 뒤 때리고, 맞으면 죽는다. 1 · 3단계 네트워크 구성에서 같다.**

### 결론

| 질문 | 결정 |
| :--- | :--- |
| 트리가 타깃을 어디서 읽는가 | `AAstralEnemyController::CurrentTarget` 프로퍼티 하나. 트리는 이 값에 직접 바인딩한다(Evaluator 없음) |
| 타깃을 언제 고르는가 | 트리의 `Acquire` 상태가 들어올 때마다 — 시작 · 공격 한 사이클 뒤 · 타깃을 잃었을 때. 매 틱 고르지 않는다 |
| 타깃을 잃는 것은 누가 아는가 | 컨트롤러가 타깃의 `OnDeathStarted` · `OnDestroyed` 를 구독하고, 오면 값을 비우고 트리에 이벤트를 보낸다 |
| A 의 선정 규칙 | 죽지 않은 플레이어 폰 중 가장 가까운 것. 순수 함수 + 자동 시험 |
| `UAstralThreatComponent` | **A 에서는 만들지 않는다.** 자리는 컨트롤러로 정해 두고, B 가 만들어 `AcquireTarget()` 의 안쪽만 바꾼다 |
| 공격 | 새 단발 GA `UAstralGA_Enemy_MeleeAttack` — 예고 → 전방 스윕 → 종료. 기존 루프 GA 는 건드리지 않는다 |
| 트리가 GA 를 부르는 법 | 커스텀 Task 가 태그로 스펙을 찾아 타깃을 실은 이벤트 데이터로 발동하고, GA 종료 통지로 끝난다. 틱 없음 |
| 적이 도는 규칙 | 추격 중에는 경로 방향, 예고 앞부분에는 타깃 방향, 그 뒤 판정까지는 고정. 엔진 포커스 경로를 쓴다 |
| 패링당했을 때 | A 에서는 공격 GA 가 끝나기 전에 경직 시간만큼 더 머문다. 경직 GA 로 떼는 것은 단위 C |
| 네트워크 | 전부 서버 전용. 새 복제 프로퍼티 0 |

### 결정

**① 타깃의 단일 원천 = 컨트롤러 프로퍼티, 트리는 직접 바인딩.** (§0-5 의 8번)

- `AAstralEnemyController` 에 `CurrentTarget`(`TObjectPtr<AActor>`, `VisibleAnywhere` · public · `Transient`)을 둔다. 쓰는 곳은 `SetCurrentTarget()` 하나다.
- 트리 스키마의 `AIControllerClass` 를 `AAstralEnemyController` 로 지정하면 `AIController` 컨텍스트의 프로퍼티로 보인다(`StateTreeAIComponentSchema.cpp:26` · `.h:37`). 저작 도구의 `create_state_tree` 가 `schema_properties.AIControllerClass` 를 받는다(`AnimMcpTools_StateTree.cpp:114`). 메뉴에 나오는 조건은 `CPF_Edit` + public 이다([지침서 §2-7](../StateTree/DevelopmentGuide.md) · D-6).
- `MoveTo.TargetActor` 와 GA 실행 Task 의 `TargetActor` 가 이 값에 묶인다.
- **`MoveTo` 는 묶인 값을 들어올 때만 읽는다.** `bShouldCopyBoundPropertiesOnTick = false` 이고(`StateTreeMoveToTask.cpp:19`), 틱 복사는 `Destination` 추적 모드에서만 켜진다(`:26` · `:172` ~ `:181`). 같은 타깃이 움직이는 것은 경로 추종이 따라간다 — `bTrackMovingGoal` 기본값이 참이라 `SetGoalActor` 로 넘긴다(`:109` ~ `:113`). **다른 타깃으로 바뀌는 것은 `Chase` 를 다시 들어와야 반영된다** — ② 의 `Acquire` 재진입과 타깃 상실 이벤트가 그 경로다.

**② 타깃은 트리의 판단 지점에서 고르고, 상실만 이벤트로 받는다.** (§0-5 의 6번 일부)

- 컨트롤러에 `AcquireTarget()` 을 둔다. 서버 `GameState->PlayerArray` 의 폰에서 죽었거나 죽는 중인 것을 빼고 가장 가까운 것을 골라 `SetCurrentTarget()` 에 넘긴다. 고르는 산술은 월드 없는 순수 함수(`AstralEnemyTargeting::SelectNearestIndex`)로 뗀다 — `AstralTargeting` · `AstralParty` 와 같은 관용구다.
- 부르는 쪽은 커스텀 Task `FAstralStateTreeTask_AcquireTarget` 하나다. 들어올 때 `AcquireTarget()` 을 부르고 타깃이 있으면 성공, 없으면 실패로 바로 끝난다.
- `SetCurrentTarget()` 은 앞 타깃의 구독을 풀고 새 타깃의 `UAstralHealthComponent::OnDeathStarted` 와 `AActor::OnDestroyed` 를 구독한다. 둘 중 하나가 오면 값을 비우고 트리에 `TargetLost` 이벤트를 보낸다(`UStateTreeComponent::SendStateTreeEvent`). 접속 종료는 폰 파괴로 온다.
- 컨트롤러의 `OnUnPossess` 와 `HandlePawnDeathStarted` 가 타깃을 비운다(구독 정리).
- **타깃이 없을 때의 재시도만 시간에 맡긴다.** `Wait` 상태가 0.5초(잠정) 쉰 뒤 `Acquire` 로 돌아간다. 전원 사망 · 아직 아무도 없음 · 경로 실패가 이 경로다. 이벤트로 바꾸려면 '플레이어가 타깃이 될 수 있게 됐다'(스폰 · 부활)를 알리는 명부가 필요한데 지금은 없다. B 의 위협 표가 같은 명부를 요구하므로 그때 다시 본다.
- **`UAstralThreatComponent` 의 자리는 컨트롤러다.** 서버에만 있고 폰과 수명이 같다(폰 파괴 때 컨트롤러도 파괴 — `Controller.cpp:434`). A 에서는 만들지 않는다. B 가 만들어 `AcquireTarget()` 의 안쪽을 '가장 가까운' 에서 '위협 최대' 로 바꾸고, 트리 · Task · 바인딩은 그대로 둔다.

**③ GA 실행 Task — `FAstralStateTreeTask_ActivateAbility`.** (§4)

- 입력: 컨텍스트 `Actor`(폰), 파라미터 `AbilityTag`, 입력 `TargetActor`(선택).
- 들어올 때: 폰의 ASC 에서 태그로 스펙을 찾는다(`GetActivatableGameplayAbilitySpecsByAllMatchingTags` — `AbilitySystemComponent.h:1014`). `OnAbilityEnded`(`:542`)를 구독한 뒤 `TriggerAbilityFromGameplayEvent`(`:1043`)로 그 스펙을 발동하며 이벤트 데이터의 `Target` 에 타깃을 싣는다. 프로젝트의 입력 경로가 이미 같은 함수를 쓴다(`AstralGameplayAbility.h:35`).
- 스펙이 없거나 발동이 거부되면 실패, 발동 호출 안에서 이미 끝났으면 그 자리에서 결과를 돌려준다.
- 끝날 때: `OnAbilityEnded` 에서 핸들을 대조해 `FinishTask` — 취소면 실패, 아니면 성공. 약한 실행 컨텍스트를 쓰는 것은 `MoveTo` 와 같다(`StateTreeMoveToTask.cpp:150` ~ `:155`).
- 나갈 때: 구독을 풀고, 아직 활성이면 `CancelAbilityHandle`(`:1053`). 사망 때는 `GA_Death` 가 이미 취소했으므로 아무 일도 하지 않는다 — 몇 번 불려도 같다(§1-8). 이 시점에 ASC 는 살아 있다 [실측 V4 · V6 · V7].
- 틱하지 않는다(`bShouldCallTick = false`).
- 두 Task 는 런타임 모듈(`Source/AstralBreak/AI/StateTree/`)에 둔다. 스키마가 받는 조상은 `FStateTreeTaskCommonBase` 또는 `FStateTreeAITaskBase` 다(`StateTreeComponentSchema.cpp:41` · `StateTreeAIComponentSchema.cpp:38`).

**④ 단발 공격 GA — `UAstralGA_Enemy_MeleeAttack`.** (§3 일부, §0-5 의 9번 일부)

- `ServerOnly` · `InstancedPerActor` · `ActivationPolicy = Manual`(`AstralGameplayAbility.h:26`). 애셋 태그는 `Ability.Attack`(사망 때 취소 대상 — 루프 GA 와 같다) + 새 태그 `Ability.Enemy.Attack.Melee`(Task 가 찾는 키).
- 흐름: 발동 → `State.Telegraphing` 루즈 태그 + 기존 `MulticastDrawTelegraphDebug` → 예고 시간 뒤 `ApplyDamageSweep` → 종료.
- **패링당하면 경직만큼 더 머문다.** `Staggered` 는 스윕 호출 안에서 동기로 온다(`AstralCombatStatics.cpp:313` 의 `SendGameplayEventToActor`). GA 는 받은 것을 기억했다가 스윕 뒤 `StaggerRecovery` 만큼 기다리고 끝난다. 트리는 GA 종료를 기다리고 있으므로 경직 동안 아무것도 하지 않는다 — 노드를 더하지 않고 M2 의 '패링 → 적이 멈춘다' 가 유지된다. 단위 C 가 이벤트로 발동하는 경직 GA 로 뗀다.
- 값은 전부 GA 프로퍼티(데이터)이고 **잠정** 이다: 피해 15 · 예고 1.0초 · 경직 2.0초 · 스윕 80 / 200 / 50(더미 값 그대로) · 타깃 추적 0.7초(⑤).
- **기존 `UAstralGA_Enemy_TelegraphAttack` 은 한 줄도 건드리지 않는다.** 더미의 `bTelegraphAttackEnabled` 동작도 그대로다. 새 적의 AbilitySet 에는 루프 GA 를 넣지 않는다(넣으면 공격이 둘이 된다).
- 가드 · 패링 가능 여부 태그, 피격 반응, 약점 노출, 회피 무적, 클라이언트용 예고(몽타주 · GameplayCue)는 단위 C 다. A 의 클라이언트는 지금 더미와 같은 DrawDebug 를 본다.

**⑤ 회전 — 엔진 포커스 경로.** (§0-5 의 10번)

- 적 BP 의 이동 컴포넌트 기본값을 `bOrientRotationToMovement = false` · `bUseControllerDesiredRotation = true` · Yaw 회전 속도 360°/초(잠정)로 둔다. **베이스는 바꾸지 않는다** — `AAstralCharacter` 는 `bOrientRotationToMovement = true` 이고(`AstralCharacter.cpp:38`) 엔진은 이 값이 참이면 컨트롤러 회전을 보지 않는다(`CharacterMovementComponent.cpp:6549`).
- 추격 중: 경로 추종이 경로 앞쪽을 Move 우선순위 포커스로 준다(`PathFollowingComponent.cpp:1683` ~ `:1692`). 적은 가는 방향을 본다.
- 예고 중: 공격 GA 가 발동 때 `SetFocus(타깃, Gameplay)` 를 걸고(`AIController.cpp:275`), `FacingTrackDuration` 뒤와 종료 때 `ClearFocus(Gameplay)` 한다(`:291`). 포커스가 없으면 컨트롤 회전이 폰 방향을 따라가므로 회전이 멈춘다(`:439`).
- 그래서 **예고 앞 0.7초는 타깃을 따라 돌고 마지막 0.3초는 방향이 고정된다**(잠정). 고정 뒤 옆으로 빠지면 스윕이 빗나간다 — 회피 무적 없이 위치 이탈로 피하는 창이다.
- GA 가 아는 타입은 엔진의 `AAIController` 뿐이다. 타깃은 이벤트 데이터로 받는다.

**⑥ 트리 — `ST_Enemy_Melee`.** (§5)

| 상태 | Task | 전환 |
| :--- | :--- | :--- |
| `Acquire` | `AcquireTarget` | 성공 → `Chase` · 실패 → `Wait` |
| `Wait` | Delay 0.5초 | 완료 → `Acquire` |
| `Chase` | `MoveTo`(`TargetActor` ← `AIController.CurrentTarget`) | 성공 → `Attack` · 실패 → `Wait` · 이벤트 `TargetLost` → `Acquire` |
| `Attack` | `ActivateAbility`(태그, `TargetActor` ← 같은 값) | 성공 · 실패 → `Recovery` |
| `Recovery` | Delay 1.0초 | 완료 → `Acquire` |

- 사망 상태는 두지 않는다(§1-8). `MoveTo` 실패 전환을 둔다(Phase2Report §6 의 5번).
- `Attack` 중에 타깃을 잃어도 공격은 끝까지 간다. 그 뒤 `Recovery` → `Acquire` 가 다시 고른다.
- **도착 거리와 공격 거리.** `MoveTo` 의 `AcceptableRadius`(잠정 150)는 스윕이 닿는 거리(시작 50 + 길이 200 + 반경 80)보다 안쪽이어야 한다. 둘 다 데이터다(Phase2Report §6 의 6번).
- 저작은 `state-tree-mcp` 로 한다(`/Game/AI/Enemy/` — 편집 허용 경로 `/Game/AI/` 안, `DefaultEngine.ini:174`).

**⑦ 애셋.** 전부 새로 만든다. 기존 애셋 수정 0 · 맵 수정 0.

| 애셋 | 내용 |
| :--- | :--- |
| `GA_Enemy_MeleeAttack` | C++ GA 의 BP 자식 — 값 |
| `DA_AbilitySet_Enemy_Melee` | `GA_Death` + `GA_Enemy_MeleeAttack` |
| `BP_Enemy_Melee` | 부모 `AAstralCombatCharacter`. 메시는 더미와 같은 것(임시), `AutoPossessAI = PlacedInWorldOrSpawned`, 컨트롤러 · AbilitySet 지정, ⑤ 의 이동 값 |
| `BP_EnemyController_Melee` | 부모 `AAstralEnemyController`. 트리 참조 |
| `ST_Enemy_Melee` | ⑥ |

**⑧ 눈으로 볼 수단 — 디버그 명령 `SpawnEnemy`.** 플레이어 앞에 `BP_Enemy_Melee` 를 서버에서 스폰한다. 기존 디버그 명령과 같은 모양이다(`Exec` → 서버 RPC, `#if !UE_BUILD_SHIPPING` — `AstralCharacter.cpp:225` ~ `:241`). 맵에 배치하지 않으므로 어느 맵 · 어느 넷 구성에서도 쓸 수 있고 B · C 의 수동 확인에도 쓴다. 스폰 시스템은 단위 D 다.

### 대안과 기각 이유

| 대안 | 기각 이유 |
| :--- | :--- |
| 커스텀 Evaluator 가 타깃을 출력 | 매 틱 도는 노드가 하나 생기고, 그래도 `MoveTo` 는 들어올 때만 읽는다. 값이 이미 컨트롤러에 있으면 한 번 더 옮기는 일이다. **A0 에서 직접 바인딩이 안 되면 이쪽으로 물러난다** |
| `AcquireTarget` Task 의 출력을 `MoveTo` 에 바인딩 | Task 출력은 그 상태가 활성일 때만 산다. 타깃을 상태 계층에 묶게 되고, 타깃 상실 구독을 둘 곳이 없다 |
| 타깃 없이 조건만으로 전환(컨트롤러가 알아서 고름) | 다시 고르는 시점을 컨트롤러가 따로 가져야 한다 — 타이머 아니면 틱이다. 트리의 판단 지점이 이미 그 시계다 |
| A 에서 `UAstralThreatComponent` 를 미리 만든다 | 상태 없는 껍데기에 쓰는 곳이 하나다. B 에서 위협 표의 실제 모양에 맞춰 만든다 |
| 컴포넌트를 폰에 둔다 | 클라이언트에도 생긴다. 트리가 읽으려면 컨텍스트 Actor 를 거쳐야 한다 |
| 매 틱 가장 가까운 플레이어로 갱신 | 폴링이고, 두 플레이어 사이에서 타깃이 떨린다. A 는 사이클마다 한 번이면 된다 |
| AIPerception | 시야 · 팀 설정과 컨트롤러 팀 동기화가 따라온다. '가장 가까운 플레이어' 에는 과하다. 인지 범위가 필요해지는 B · D 에서 다시 본다 |
| 루프 GA 를 고쳐 단발 모드를 더한다 | 더미 경로(V9 눈 확인 전)를 건드린다. 부록 C 도 '더미 검증용으로 유지' 다 |
| 두 GA 의 공통 조상을 뽑는다 | 겹치는 것은 태그 켜고 끄기와 스윕 한 줄이다. 단위 C 가 판정을 몽타주 · 무기 트레이스로 바꾸면 그나마 사라진다 |
| `TryActivateAbilitiesByTag` 로 발동 | 타깃을 실을 수 없고, 어느 스펙이 켜졌는지 돌려주지 않아 종료를 대조할 수 없다 |
| GA 가 `AbilityTriggers` 로 이벤트에 반응 | 발동은 되지만 Task 가 핸들을 모른다. 이벤트 태그와 GA 를 애셋에서 따로 맞춰야 한다 |
| Task 가 틱에서 GA 활성 여부를 본다 | 폴링이다. 종료 델리게이트가 있다 |
| 베이스 이동 컴포넌트의 회전 모드를 바꾼다 | 히어로 · 더미로 번진다 |
| 컨트롤러가 타깃을 항상 포커스 | 추격 중 경로가 꺾이면 타깃을 본 채 옆걸음한다 |
| GA 가 매 틱 `SetActorRotation` | 이동 컴포넌트의 회전과 싸우고, 회전 속도 제한을 따로 구현하게 된다 |
| 회전 없이 스윕 방향만 타깃 쪽으로 | 보이는 방향과 판정이 어긋난다. 플레이어가 읽을 것이 없다 |
| 적을 `CombatTestMap` 에 배치 | 맵 애셋을 고치고, 다른 맵 · 다른 넷 구성에서 볼 수 없다 |

### 영향

| 대상 | 변경 | 상속 · 공용 영향 |
| :--- | :--- | :--- |
| `AAstralEnemyController` | 프로퍼티 1 · 함수 2(`AcquireTarget` · `SetCurrentTarget`) · 핸들러 2 · `OnUnPossess` 와 사망 처리에 타깃 비우기 | 자식 BP(`BP_P2_*` · `BP_M3_*` 컨트롤러)가 물려받는다. 그 트리들은 타깃을 쓰지 않아 값이 빈 채로 남고 이벤트도 나가지 않는다 |
| 새 파일: 순수 함수 1쌍 · Task 2쌍 · GA 1쌍 · 시험 | 추가 | 없음 |
| 게임플레이 태그 | 2개 추가(`Ability.Enemy.Attack.Melee` · 트리 이벤트 `TargetLost`) | 없음 |
| 디버그 명령 | `Exec` 1 + 서버 RPC 1(⑧) | Shipping 에서 빠진다 |
| `AAstralCombatCharacter` · `AAstralCharacter` · 히어로 · 더미 · 루프 GA | **변경 없음** | |
| 플러그인(`AnimGraphMcp`) | 변경 없음을 기대한다. 필요해지면 단위 세션이 마스터에 묻는다 | |
| 복제 | **새 프로퍼티 0** | |

- 클라이언트가 보는 것: 이동 · 회전(이동 컴포넌트 복제), 예고(기존 멀티캐스트 DrawDebug), HP · 사망(기존 복제). 클라이언트에 새 경로는 없다.

### 미해결

- **직접 바인딩이 실제로 되는가** — A0 의 첫 항목이다. 안 되면 Evaluator 로 물러난다.
- **닿을 수 없는 가장 가까운 플레이어.** 경로가 없으면 `Chase` 실패 → `Wait` → 같은 타깃을 다시 고른다. 다른 플레이어로 넘어가지 않는다. B 의 선정 규칙에서 다룬다.
- **인지 범위가 없다.** 스폰되면 거리와 무관하게 쫓는다. B · D 에서 정한다.
- **사이클마다 가장 가까운 사람으로 바뀐다.** 여럿이 붙으면 타깃이 자주 바뀔 수 있다. B 가 규칙을 바꾼다.
- **추격 중 타깃이 스윕 거리 밖으로 계속 달아나면** 공격하지 못하고 계속 쫓는다. 돌진은 단위 C 다.
- **타깃이 죽은 뒤 부활하면**(`ReviveSelf`) 다음 `Acquire` 에서 다시 후보가 된다. 따로 구독하지 않는다.
- **레벨 배치의 첫 `Acquire` 에 플레이어가 없을 수 있다**(§1-2 미해결). `Wait` 재시도가 받는다.
- 값(예고 · 추적 · 회전 속도 · 도착 거리 · 회복)은 전부 잠정이다. 조작감 확인 뒤 사용자가 정한다.

### 검증 계획

**A0 — 먼저 실행으로 확인한다(구현 본체 전).** 이 절이 [소스] 로만 적은 것 중 틀리면 설계가 바뀌는 것들이다. §1 의 '대조군부터' 와 같은 순서다.

| # | 확인할 것 | 틀리면 |
| :--- | :--- | :--- |
| A0-1 | `AIController.CurrentTarget` 이 `list_state_tree_bindable_sources` 에 나오고 `MoveTo.TargetActor` 바인딩이 컴파일된다 | Evaluator 출력으로 바꾼다(마스터 확인) |
| A0-2 | 묶인 타깃이 움직이면 적이 따라간다(Phase2Report §5 의 '움직이는 목표 추격' — 돌려 본 적 없음) | `MoveTo` 를 다시 들어오게 하는 전환을 더한다 |
| A0-3 | 타깃을 바꾼 뒤 `Chase` 를 다시 들어오면 새 타깃을 쫓는다 | ① 을 다시 본다 |
| A0-4 | ⑤ 의 이동 값에서 적이 추격 중 경로 방향을, 포커스 중 타깃을 본다. 포커스를 지우면 멈춘다 | 회전 방식을 다시 정한다(마스터 확인) |

**본 검증.** 사람 몫은 조작감뿐이다.

| # | 확인할 것 | 방법 | 판정 |
| :--- | :--- | :--- | :--- |
| A1 | 가장 가까운 것 선택 · 죽은 후보 제외 · 빈 목록 · 동률 | `AstralBreak.Enemy.SelectNearest` | 자동 |
| A2 | `Acquire → Chase → Attack → Recovery → Acquire` 순서, 폰이 플레이어 쪽으로 이동 | `run_state_tree_scenario`(`CombatTestMap`, 런타임 스폰) | 자동 |
| A3 | 추격 중 사망 → 트리 정지 · 경고 0(§1 V6 을 실제 트리로) | 같은 도구의 `damage` | 자동 |
| A4 | 리슨 · Dedicated 한 프로세스: 적의 공격으로 히어로 HP 가 서버에서 줄고 같은 값이 클라이언트에 온다 | 멀티 PIE 자동 시험 `AstralBreak.Net.EnemyCombat.*`(선행 단위의 틀 재사용) | 자동 |
| A5 | 타깃이 죽으면 다른 플레이어로 넘어간다 · 전원이 죽으면 공격하지 않는다 | A4 와 같은 시험 | 자동 |
| A6 | 적 HP 0 → 서버 · 클라이언트에서 폰이 사라진다 | A4 와 같은 시험 | 자동 |
| A7 | 패링하면 피해 0 · 적이 경직 동안 다음 공격을 하지 않는다 | A4 와 같은 시험에서 방어 태그를 직접 세운다 | 자동(시도). 안 되면 사용자 |
| A8 | Dedicated 에서 클라이언트 히어로의 실제 공격으로 적이 피해를 받는다 — P7 의 기능 부분 | A4 와 같은 시험에서 클라이언트 ASC 로 발동 | 자동(시도). 무인 PIE 에서 안 되면 P7 로 남긴다 |
| A9 | 별도 프로세스(2단계 리슨 · 실제 Dedicated)에서 A4 · A6 | `run_party_flow.py` 에 전투 시나리오 추가 | 자동. 한 프로세스가 다 통과한 뒤 마지막에 한다 |
| A10 | 회귀 | `AstralBreak.` 전체 · 두 구성 빌드 · Development 는 `-DisableAdaptiveUnity` 로도 한 번(새 cpp) | 자동 |
| A11 | 조작감 — 예고 1초에 가드 · 패링 · 옆걸음 회피가 되는가, 적의 회전이 자연스러운가 | `SpawnEnemy` 로 PIE | 사용자 |

- 시험이 떨어질 수 있는지도 본다 — 선행 단위처럼 하나를 일부러 깨뜨려 실패를 확인한다(예: 공격 GA 의 피해를 0 으로).
- A9 는 범위가 넘치면 단위 E 로 미룰 수 있다. 미루면 §0-2 의 '단위마다 2 · 3단계' 에서 벗어나므로 마스터에 먼저 묻는다.

### 구현 결과 (2026-11-11)

단위 A 구현 세션이 덧붙인다. 위의 결정 · 근거는 설계 때 쓴 그대로다. **A0 는 전부 설계대로 나왔고, A1 ~ A10 은 [실측] 통과, A11(조작감)은 사용자 몫으로 남았다. 사용자가 커밋했다(`dbe2fd1`).**
실행은 전부 DebugGame 에디터 · `-unattended` 이고, Development 는 빌드와 별도 프로세스 실행 1회다. 수치는 에디터를 `-stdout -FullStdOutLogOutput` 로 띄워 `ASTRAL_PIETEST` 줄에서 읽은 것이다(자동 시험 러너의 결과에는 오류 · 경고만 실린다).

#### 바뀐 파일

| 파일 | 변경 |
| :--- | :--- |
| `Character/Enemy/AstralEnemyController.h` · `.cpp` | `CurrentTarget` · `AcquireTarget()` · `SetCurrentTarget()` · 타깃 사망 · 파괴 핸들러 → `AI.Event.TargetLost`, `OnUnPossess` · 사망 처리에서 타깃 비우기 |
| `AI/AstralEnemyTargeting.h` · `.cpp` (새 파일) | 순수 함수 `AstralEnemyTargeting::SelectNearestIndex` |
| `AI/StateTree/AstralStateTreeTask_AcquireTarget.h` · `.cpp` · `AstralStateTreeTask_ActivateAbility.h` · `.cpp` (새 파일) | Task 2개 |
| `AbilitySystem/Abilities/Enemy/AstralGA_Enemy_MeleeAttack.h` · `.cpp` (새 파일) | 단발 공격 GA |
| `AbilitySystem/Abilities/AstralAbilityGameplayTags.h` · `.cpp` · `AbilitySystem/AstralEventGameplayTags.h` · `.cpp` | 태그 `Ability.Enemy.Attack.Melee` · `AI.Event.TargetLost` |
| `Character/AstralCharacter.h` · `.cpp` | 디버그 명령 `SpawnEnemy`(`Exec`) + `ServerSpawnEnemy`(서버 RPC). 기존 함수는 그대로 |
| `Tests/AstralEnemyTargetingTests.cpp` (새 파일) | `AstralBreak.Enemy.SelectNearest` |
| `AstralBreakEditor/Private/Tests/AstralPieTestHelpers.h` (새 파일) | PIE 시험 공용 틀(단계 큐 · PIE 시작/종료 · 월드 조회 · 실측값 기록) |
| `AstralBreakEditor/Private/Tests/AstralEnemyAssumptionsPieTests.cpp` (새 파일) | A0-2 ~ A0-4 — `AstralBreak.Enemy.Assumptions.ChaseAndFocusPIE` |
| `AstralBreakEditor/Private/Tests/AstralEnemyCombatPieTests.cpp` (새 파일) | A4 ~ A8 — `AstralBreak.Net.EnemyCombat.{ListenPIE, DedicatedPIE}` |
| `AstralBreakEditor/Private/Tests/AstralPartyFlowPieTests.cpp` | 공용 틀을 쓰도록 정리(시험 내용은 그대로) |
| `AstralBreakEditor/Private/Tests/AstralPartyFlowTestController.h` · `.cpp` | Gauntlet 컨트롤러에 `EnemyCombat` 시나리오(A9) |
| `AstralBreakEditor/AstralBreakEditor.Build.cs` | 시험이 쓰는 모듈 의존 추가(AI · GAS · StateTree · NavigationSystem) |
| `Tools/net_test/run_party_flow.py` | `--scenario enemy_combat` |
| `Tools/scripts/setup/enemy_melee_assets.py` (새 파일) | 아래 애셋 4개를 만든 스크립트(`-ExecutePythonScript`) |
| 애셋(전부 새로) | `/Game/AbilitySystem/Abilities/Enemy/GA_Enemy_MeleeAttack` · `/Game/AbilitySystem/AbilitySets/Enemy/DA_AbilitySet_Enemy_Melee` · `/Game/Characters/Enemy/BP_Enemy_Melee` · `/Game/AI/Enemy/BP_EnemyController_Melee` · `/Game/AI/Enemy/ST_Enemy_Melee` · 시험용 `/Game/AI/Test/ST_A0_Chase` |

건드리지 않은 것: `UAstralGA_Enemy_TelegraphAttack` · `AAstralCombatCharacter` · 히어로 코드 · `BP_TargetDummy` 와 기존 애셋 · 맵 · `Plugins/AnimGraphMcp`. 새 복제 프로퍼티 0. 새 RPC 는 디버그용 `ServerSpawnEnemy` 하나다(본문은 `#if !UE_BUILD_SHIPPING`).

트리 두 개는 `state-tree-mcp` 로 저작했다 — `ST_Enemy_Melee` 는 `create_state_tree` 1회 + `apply_state_tree_operations` 1회(연산 20개, 미리보기가 태그 값 형식 오류 1건을 잡았다)에 컴파일 · 저장됐고 fixups 0, 바인딩 2개(`MoveTo.TargetActor` · `ActivateAbility.TargetActor` ← `AIController.CurrentTarget`)가 `inspect` 에 남아 있다 [실측].

#### A0 결과 [실측]

Standalone PIE `CombatTestMap`, 시험 트리 `ST_A0_Chase`(`Idle` -이벤트→ `Chase`(MoveTo ← `CurrentTarget`) → `Idle`), 폰 · 컨트롤러는 네이티브 클래스에 ⑤ 의 이동 값을 준 것, 타깃은 컨트롤러 없는 폰이다.

| # | 결과 |
| :--- | :--- |
| A0-1 | **설계대로.** `list_state_tree_bindable_sources` 의 `AIController` 소스에 `CurrentTarget`(`TObjectPtr<AActor>`)이 나오고, 바인딩이 컴파일 · 저장됐다(fixups 0) |
| A0-2 | **설계대로.** 추격 1.00초 시점에 타깃을 뒤쪽으로 옮기자 1.66초에 옮긴 타깃에서 183 cm 지점에 멈췄다(원래 자리에서 920 cm) |
| A0-3 | **설계대로.** 타깃을 바꾸고 `Chase` 를 다시 들어오자 새 타깃에서 173 cm 에 멈췄다. **대조:** 추격 중 값만 바꾸고 다시 들어오지 않으면 처음 타깃에서 181 cm 에 멈췄다 — ① 의 '`MoveTo` 는 들어올 때만 읽는다' 가 실측됐다 |
| A0-4 | **설계대로.** 추격 중 몸 방향 − 속도 방향이 중앙값 0.0° · 최대 9.4°(표본 115, 꺾이는 경로 포함)이고 포커스 액터는 없었다. `SetFocus(타깃, Gameplay)` 뒤 90° 를 0.250초 · 180° 를 0.500초에 돌았고(360°/초 그대로), `ClearFocus` 뒤 타깃을 옮겨도 1초 동안 0.00° 였다. **대조:** 베이스 이동 기본값의 폰은 포커스를 걸어도 0.00° — ⑤ 의 값이 필요하다 |

마스터 세션에는 A0 결과를 메시지로 알렸다(브리프의 id 가 틀려 한 번 실패했고, 정정된 id 로 전달).

#### 검증 결과

| # | 결과 | 구분 |
| :--- | :--- | :--- |
| A1 | **통과.** `AstralBreak.Enemy.SelectNearest` — 가장 가까운 것 · Origin 기준 · 죽은 후보 제외(더 가까워도) · 빈 목록 · 전원 사망 · 동률(앞쪽) · 높이 포함 | [실측] |
| A2 | **통과.** `run_state_tree_scenario`(`CombatTestMap`, `BP_Enemy_Melee` 런타임 스폰): `Acquire → Chase → Attack → Recovery → Attack → Recovery → Attack` 7/7, 경고 0. 폰이 419 cm 이동해 플레이어에서 181 cm 에 멈췄고, `Attack` 은 1.00초, `Recovery` 는 1.00초였다. 회복 뒤에는 `Acquire` · `Chase` · `Attack` 이 한 프레임에 지나간다(진입 횟수 +3 — 이미 닿는 거리라 `MoveTo` 가 바로 성공). 20초 실행에서는 7번 맞은 플레이어가 죽자 `Wait`(0.5초) ↔ `Acquire` 재시도로 넘어갔다 | [실측] |
| A3 | **통과.** 추격 중 `damage` → 같은 프레임에 트리 정지(`run_status` `Unset`) · 폰이 사망 위치에 멈춤 · 5.00초 뒤 소멸 · 경고 0. 공격(예고) 중 `damage` 도 같다(리슨 + 클라이언트 1) | [실측] |
| A4 | **통과(리슨 · Dedicated).** 클라이언트의 `SpawnEnemy` 로 부른 적이 가까운 쪽 히어로를 타깃으로 잡고 스폰 0.84 ~ 0.86초 뒤(600 cm 밖에서 177 ~ 187 cm 까지 온 뒤) 예고를 시작, 1.00 ~ 1.01초 예고 뒤 피해 15.0. 먼 쪽 히어로는 맞지 않았다. 서버 HP 와 같은 값이 모든 클라이언트(맞은 본인 · 다른 사람)에 왔다. 클라이언트에는 적 폰만 있고 컨트롤러는 없다. 패링 없는 주기 = 판정 뒤 1.00초에 다음 예고 | [실측] |
| A5 | **통과(리슨 · Dedicated).** 타깃이 죽자 다른 플레이어로 넘어갔다. 그 추격 중에 그 타깃마저 죽이자 같은 호출 안에서 타깃이 비고 0.02초 뒤(10 cm) 멈췄다(시체까지 995 ~ 996 cm 남김). 전원 사망 4초 동안 공격 · 예고 · 타깃 없음, 트리는 계속 돈다. 부활(`ReviveSelf`)시키자 0.50초 뒤(`Wait` 재시도) 다시 타깃이 됐고 쫓아가 15.0 을 깎았다 | [실측] |
| A6 | **통과(리슨 · Dedicated).** 적 HP 0 → 그 호출 안에서 트리 정지 · 타깃 비움 → 5.00초 뒤 서버와 모든 클라이언트에서 폰이 사라지고 서버의 컨트롤러도 없어졌다 | [실측] |
| A7 | **통과(리슨 · Dedicated).** 서버에서 방어 태그(`State.Defense.Parrying`)를 세운 채 맞으면 피해 0, 공격 어빌리티가 판정 뒤 2.00 ~ 2.01초 더 활성으로 남고(패링 없을 때 0.00초), 다음 예고는 판정 3.02 ~ 3.05초 뒤에 시작했다(패링 없을 때 1.00초). 패링 입력 자체(히어로 방어 GA)는 쓰지 않았다 — 태그를 직접 세웠다 | [실측] |
| A8 | **통과(리슨 · Dedicated).** 클라이언트 월드의 ASC 에 기본 공격 입력을 넣자 서버의 적 HP 가 100 → 68.8 이 됐다. 히어로는 서버에서 적 110 cm 앞으로 옮기고 클라이언트의 몸 · 시점을 적 쪽으로 돌린 뒤 넣었다. 무인 PIE 에서 됐다 — P7 의 '기능' 부분만이고 조작감은 아니다 | [실측] |
| A9 | **통과.** `run_party_flow.py dedicated --scenario enemy_combat`(서버 + 클라이언트 2) · `listen --scenario enemy_combat`(호스트 + 클라이언트 1): 클라이언트 한 프로세스가 `SpawnEnemy` 를 부르고, 모든 프로세스가 같은 피해자 · HP 85.0 을 봤다. 적 폰은 모든 프로세스에, 컨트롤러는 서버에만 있다. 서버가 적을 죽이자 모든 프로세스에서 사라졌다. 여기서는 히어로의 공격이 아니라 서버의 `DamageSelf` 로 죽였다 | [실측] |
| A10 | **통과.** 최종 코드로 `AstralBreakEditor Win64` DebugGame · Development 둘 다 `Result: Succeeded`, Development 는 `-DisableAdaptiveUnity` 로도 `Result: Succeeded`(새 런타임 cpp 가 유니티 파일에 합쳐진 상태. 에디터 모듈 파일은 평소에도 파일별로 컴파일돼 이 빌드에서 다시 컴파일되지 않았다). 그 뒤 다시 돌린 것: `AstralBreak.` 39/39(선행 단위의 35 + 새 시험 4) · A9 세 번(DebugGame 리슨 · Dedicated, Development Dedicated) · 기존 `run_party_flow.py dedicated`(검사 10/10) · `dedicated --scenario leader_leaves`. 기존 `listen`(flow)은 다시 돌리지 않았다 | [실측] |
| A11 | **미실행 — 사용자 몫.** 순서는 아래 | |

**시험이 실패할 수 있는가 — 대조 실험.** `AAstralEnemyController::HandleTargetLost` 에서 `SendStateTreeEvent` 를 뺀 빌드로 `EnemyCombat.DedicatedPIE` 를 돌렸다(확인 뒤 원복 · 재빌드). **실패 3건** [실측]: 타깃이 추격 중에 죽은 뒤 적이 1.37초 동안 820 cm 를 더 걸어 시체에서 186 cm 까지 갔고('바로 멈춘다' 실패), 전원 사망 중에 예고가 한 번 더 나갔다(예고 횟수 6 → 7 · '공격 없음' 실패). 이벤트가 없으면 `MoveTo` 가 죽은 폰을 끝까지 쫓아가 헛공격을 한 뒤에야 `Acquire` 로 돌아온다는 뜻이다 — ② 의 '상실만 이벤트로' 가 실제로 일을 한다. A0 의 대조 2건(재진입 없는 타깃 변경 · 베이스 이동 값의 포커스)과 A7 의 패링 있음/없음 비교도 같은 시험 안에 들어 있다.

#### 설계가 정하지 않아 구현하며 고른 것

| 항목 | 고른 것 | 이유 |
| :--- | :--- | :--- |
| 트리 이벤트 태그 이름 | `AI.Event.TargetLost`(`AIEvent_TargetLost`), 기존 `AstralEventGameplayTags` 에 새 절 | `GameplayEvent.*` 는 ASC 로 가는 이벤트다. 트리로 가는 것은 뿌리를 나눴다. 새 파일은 만들지 않았다 |
| 순수 함수 · Task 의 폴더 | `Source/AstralBreak/AI/` · `AI/StateTree/` | 브리프가 Task 폴더를 정했고 순수 함수는 그 위에 뒀다 |
| 후보 수집 | `PlayerArray` 에서 봇(`IsABot`)을 빼고, 사망은 `UAstralHealthComponent::IsDeadOrDying` 으로 본다. 거리는 3D | 사망 판정을 구독하는 것(`OnDeathStarted`)과 같은 원천에 뒀다. 적대 여부는 보지 않는다(설계의 규칙 그대로) |
| `SpawnEnemy` 의 자리와 클래스 | `AAstralCharacter` 에 `DamageSelf` 들과 나란히. 클래스는 **이름으로** 받는다 — `SpawnEnemy [BP 이름] [거리]`, `/Game/Characters/Enemy/<이름>` 만 로드하고 생략하면 `BP_Enemy_Melee` · 400 cm | `EquipWeapon WD_…` 과 같은 관용구다. `GameData` 에 참조를 두면 기존 애셋(`DA_GameData`)을 고쳐야 한다. 폴더를 고정해 클라이언트가 보낸 문자열로 임의 경로를 로드하지 않는다. 베이스가 파생 클래스를 include 하지 않게 `APawn` 으로 스폰한다 |
| 발동 이벤트의 태그 | Task 가 `AbilityTag` 를 그대로 `EventTag` 로 싣는다 | 엔진은 이 태그를 라우팅하지 않고 찍기만 한다. 세 번째 태그를 만들지 않았다 |
| 스펙 찾기 | 태그 요건(차단 태그)은 찾을 때 거르지 않고 발동이 거부하게 둔다 | '스펙 없음' 과 '발동 거부' 는 둘 다 실패이고, 거부 판단을 한 곳에 둔다 |
| 발동 호출 안에서 끝난 경우 | 람다와 Task 가 나눠 쥐는 작은 상태(`FAstralAbilityRunState`)에 적어 두고 `EnterState` 가 직접 결과를 돌려준다 | `EnterState` 안에서는 약한 컨텍스트로 Task 를 끝낼 수 없다(엔진 `StateTreeMoveToTask.cpp:143` 의 주석과 같은 이유) |
| Task 의 `TargetActor` | `Category = Input` + `Optional` | 설계의 '입력(선택)' 그대로. 안 묶어도 컴파일된다 [소스 — `StateTreeCompiler.cpp:2802`. 안 묶은 트리는 만들지 않았다] |
| 예고 표시 | `MulticastDrawTelegraphDebug` 를 두 번 부른다 — 발동 때(추적 시간만큼) · 방향을 고정할 때(남은 시간만큼) | 추적 중에 몸이 도므로 발동 때 한 번만 그리면 마지막 표시가 실제 판정 볼륨과 어긋난다. 기존 멀티캐스트는 고치지 않았다 |
| 판정 전에 온 `Staggered` | 예고를 끊고 바로 경직으로 간다 | A 에서는 자기 스윕만 `Staggered` 를 부르므로 일어나지 않는 경로다 [소스 — 실행 안 함] |
| 컨트롤러 BP 의 자리 | `/Game/AI/Enemy/`(트리 옆) | 폰은 `/Game/Characters/Enemy/`(더미 옆) |
| 애셋 만드는 법 | 스크립트(`enemy_melee_assets.py`). GA 는 에디터의 '게임플레이 어빌리티 블루프린트' 와 같은 팩토리로 만들었다 | 재현할 수 있게 저장소에 남겼다. 이미 있으면 건너뛴다 |
| A0 의 고정물 | 시험 BP 없이 네이티브 폰 · 컨트롤러 + 트리 1개. 시험은 지우지 않고 회귀로 남겼다 | 엔진을 올렸을 때 ① · ⑤ 의 전제가 깨지면 여기서 먼저 떨어진다 |
| PIE 시험 틀 | 선행 단위 시험 파일 안에 있던 단계 큐 · PIE 시작/종료를 헤더(`AstralPieTestHelpers.h`)로 빼고 세 시험 파일이 나눠 쓴다 | 같은 코드를 세 번 두지 않으려고. `PartyFlow` 3개는 정리 뒤에도 통과했다 [실측] |

#### 설계와 달라진 것

- **`AAstralCharacter` 가 바뀌었다.** 위 '영향' 표는 '변경 없음' 이었다. 디버그 명령을 기존 명령과 같은 자리에 두느라 `Exec` 1 + 서버 RPC 1 이 더해졌다(브리프가 허용한 예외). 기존 함수 · 동작은 그대로다.
- **A5 를 계획보다 넓혔다.** '추격 중 타깃 사망 → 즉시 정지' 와 '부활 뒤 재타깃' 을 더했다. 처음 쓴 A5 는 적이 타깃 옆에 붙어 있을 때만 죽여서 `Chase` 의 `TargetLost` 전환을 지나지 않았다.
- **A9 에서 적을 죽이는 것은 히어로가 아니다.** 프로세스가 스스로 도는 대본이라 서버의 `DamageSelf` 로 죽였다. 히어로의 실제 공격은 A8(한 프로세스)이 본다.
- 그 밖의 결정 ① ~ ⑧ 은 설계대로다.

#### 실측이 더한 것

- **멈추는 거리.** 도달 판정은 `AcceptableRadius` 에 두 캡슐 반경을 더한 중심 간 218 cm 에서 나고, 제동 뒤 실제로는 173 ~ 187 cm 에 선다 [실측]. 스윕이 닿는 범위(앞 50 ~ 250 cm, 반경 80) 안이다.
- **도달 판정에 높이가 든다.** A0 시험의 타깃을 처음에 공중(z 100)의 `ATargetPoint` 로 뒀더니 반경 판정이 한 번도 나지 않고 경로 끝(타깃 바로 아래, 거리 0)까지 갔다 [실측]. 시험 쪽 실수였고 타깃을 폰으로 바꿨다. 점프 중인 플레이어를 쫓을 때 같은 일이 날 수 있다 [추론 — 실행 안 함].
- **`MoveTo` 의 `bAllowPartialPath` 기본값은 참이다**(트리 `inspect`). 닿을 수 없는 타깃이면 실패가 아니라 갈 수 있는 데까지 간 뒤 끝날 수 있다 [소스 — 실행 안 함]. 위 '미해결' 의 '닿을 수 없는 가장 가까운 플레이어' 와 같은 자리다.
- **시나리오 타임라인의 첫 0.4초.** Standalone 시나리오에서 `Acquire` 가 t = 0.017, `Chase` 가 t = 0.417 로 찍힌다. 트리의 지연이 아니라 PIE 첫 프레임이 길어 엔진이 프레임 시간을 0.4초로 자른 것으로 본다 [추론] — 리슨 시나리오에서는 0.02초였고, 멀티 PIE 시험에서는 스폰 0.84초 뒤 예고가 시작됐다(이동 시간과 같다) [실측].
- **히어로 기본 공격 한 번이 적에게 31.2** 를 넣었다(A8) [실측].
- `Attack` 중에 온 `TargetLost` 는 전환이 없어 버려진다. 공격은 끝까지 가고 `Recovery → Acquire` 가 다시 고른다(설계 ⑥ 그대로) [소스 — 이 경로만 따로 재지는 않았다. A5 의 첫 전환이 이 경로이거나 `Recovery` 중이다].
- PIE 를 시작할 때 엔진이 `LogCrowdFollowing: Unable to find RecastNavMesh instance …` 경고를 한 번 낸다. 새 시험 3개는 이 줄을 무시하게 했고, `PartyFlow` 3개의 결과에는 경고로 남는다(통과에는 영향 없음) [실측].

#### 돌리지 않은 것

- **A11(조작감)** — 사용자.
- Development 구성의 에디터 자동 시험(빌드와 별도 프로세스 A9 1회만 했다) · 4인 · 쿠킹 빌드 · 지연이 있는 망.
- 레벨에 배치한 `BP_Enemy_Melee`(전부 런타임 스폰이다) · 적 여러 마리 동시 · 닿을 수 없는 타깃 · 가드(패링이 아닌) · 히어로의 실제 패링 입력 · 타깃의 접속 종료(파괴 구독은 [소스]).
- 플러그인 회귀(`AnimGraphMcp.*`) — 플러그인을 건드리지 않았다. 시나리오 도구는 A2 · A3 에서 4번 썼다.

#### 정리한 것 (2026-11-11, 사용자 승인 뒤 휴지통으로)

이 단위의 실행이 남긴 일회성 파일이다(전부 git 제외 경로). 8개 모두 휴지통으로 보냈다.

- `Tools/mcp/results/net_test/` 의 실행 기록 7개: `1111_212609_dedicated_enemy_combat` · `1111_212645_listen_enemy_combat` · `1111_214501_dedicated_enemy_combat` · `1111_214652_dedicated_enemy_combat` · `1111_214738_listen_enemy_combat` · `1111_214819_dedicated_flow` · `1111_214910_dedicated_leader_leaves`
- `Tools/mcp/results/enemy_melee_assets.json`(애셋 스크립트의 결과 기록)

남기는 것: `/Game/AI/Test/ST_A0_Chase`(상설 — `Assumptions` 시험이 읽는다). 이 단위는 `AnimGraphMcp.StateTree` 를 돌리지 않아 `ST_P1_*` 는 생기지 않았고, 스크래치 폴더에 쓴 것도 없다.

#### A11 — 사용자가 볼 순서

1. 에디터에서 `CombatTestMap` 을 열고 PIE(혼자 또는 리슨 · Dedicated 아무 구성).
2. 콘솔에서 `SpawnEnemy` — 내 앞 400 cm 에 적이 나온다. 멀리서 오는 것을 보려면 `SpawnEnemy BP_Enemy_Melee 1200`.
3. 볼 것: 쫓아올 때 가는 방향을 보는가 · 붙으면 빨간 캡슐(예고)이 1초 뜨고 앞 0.7초는 나를 따라 돌다가 마지막 0.3초는 방향이 굳는가 · 그 0.3초에 옆으로 빠지면 안 맞는가 · 가드하면 덜 아프고 패링하면 피해 없이 적이 2초 멈추는가 · 때리면 죽고 5초 뒤 사라지는가.
4. 값을 바꾸려면: 피해 · 예고 · 추적 · 경직 · 스윕 = `GA_Enemy_MeleeAttack` 의 디폴트, 회전 속도 = `BP_Enemy_Melee` 의 CharacterMovement `Rotation Rate`, 도착 거리 · 회복 · 재시도 = `ST_Enemy_Melee`.

적 메시는 더미와 같은 임시 마네킹이고 애니메이션이 없다(서 있는 자세로 미끄러진다) — 단위 D.

#### 다시 돌리는 법

```
에디터:  AstralBreak.Enemy   (SelectNearest · Assumptions)      AstralBreak.Net.EnemyCombat   (리슨 · Dedicated)
별도 프로세스(에디터를 내리고, 저장소 루트에서):
Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/net_test/run_party_flow.py listen --scenario enemy_combat
Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/net_test/run_party_flow.py dedicated --scenario enemy_combat
```

## 9. 단위 B — 여럿이 때리면 타깃이 바뀐다

상태: **설계 승인(2026-11-11, 사용자 — 설계안 그대로 · 검증은 필수 범위로) · 구현 · 자동 검증 완료(미커밋). 남은 것 = B9 느낌(사용자).** 아래 '결론' ~ '검증 계획' 은 설계 때 [소스] 로 쓴 그대로 두었고, 실행으로 확인된 것은 이 절 끝의 '구현 결과' 에 있다. 마스터 세션이 변경 코드(위협 컴포넌트 · 컨트롤러 · `Hostility`)를 설계 ① ~ ⑧ 과 대조해 일치를 확인했다(2026-11-11 — 시험을 다시 돌리지는 않았다). **'닿을 수 없는 타깃' 중 부분 경로 경우는 실행하지 못해 [소스] 로 남았다 — 단위 E 에서 본다.** §0-2 의 단위 B 이고 목차 2번의 나머지다. 단위 A(§8)의 트리 · Task · 바인딩 위에서 `AcquireTarget()` 의 안쪽을 바꾼다.

끝나면 보이는 것: **적이 한 사람만 끝까지 쫓지 않는다. 많이 때린 사람이 더 자주 노려지고, 몇 초마다 타깃을 다시 뽑는다.**

### 기준 — 사용자 방침과 참고작에서 확인한 것

**사용자 방침(2026-11-11):** 어그로는 그랑블루 판타지 리링크, 또는 비슷한 장르의 멀티플레이 보스 레이드에서 타깃이 바뀌는 방식으로 한다.

참고작에서 확인한 것과 못 한 것:

| 항목 | 내용 | 출처 |
| :--- | :--- | :--- |
| 리링크에는 '적대심' 수치가 있다 | 스킬(진) `Provoke` = '적에게 노려지기 쉬워진다', 적대심 +3(Lv 1) ~ +50(Lv 20). `Low Profile` = '노려지기 어려워진다', 최대 −50 | [Fextralife — Traits](https://granbluefantasyrelink.wiki.fextralife.com/Traits) · [アルテマ — 挑発](https://altema.jp/grablurelink/skill/28) |
| 표현이 '확률' 이다 | 두 효과 모두 '노려질 가능성' 을 올리고 내린다고 적는다. 누적 수치가 가장 높은 한 명을 고정으로 노리는 방식(MMO 식 탱킹)의 표현이 아니다 | 위와 같음 |
| 원작(브라우저판)의 적대심 | 캐릭터마다 '노려지기 쉬움' 값이 있고, 보정이 없으면 네 명이 같은 확률로 노려진다고 설명한다 | [神ゲー攻略 — 敵対心](https://kamigame.jp/%E3%82%B0%E3%83%A9%E3%83%96%E3%83%AB/%E3%82%AD%E3%83%A3%E3%83%A9%E3%82%AF%E3%82%BF%E3%83%BC/index-%E6%95%B5%E5%AF%BE%E5%BF%83.html) |
| **확인하지 못한 것** | 리링크의 실제 계산식 · 피해량이 확률에 드는지 · 타깃을 다시 뽑는 주기. 공개 자료를 찾지 못했다. 몬스터 헌터류의 식도 찾지 못했다 | — |

그래서 이 절의 규칙은 **'적대심 가중 추첨' 이라는 뼈대만 참고작을 따르고, 나머지(피해 가중 · 유지 시간 · 추격 중 재추첨)는 작성자가 고른 잠정안** 이다. 값은 전부 데이터에 둔다(§0-4).

### 결론

| 질문 | 결정 |
| :--- | :--- |
| 고르는 방식 | **가중 추첨.** 후보마다 가중치를 매기고 그 비율로 한 명을 뽑는다. 가장 높은 한 명을 고정으로 노리지 않는다 |
| 가중치 | 적대심 × (1 + 피해 가중 × 최근 피해 점유율). 잠정: 적대심 기본 100, 피해 가중 2.0, 최근 = 10초 |
| 아직 아무에게도 안 맞았으면 | 추첨하지 않고 가장 가까운 후보(단위 A 규칙 그대로) |
| 언제 다시 뽑는가 | 트리의 판단 지점(`Acquire`)에서, 현재 타깃을 잡은 지 유지 시간(잠정 6초)이 지났을 때. 그 전에는 유지 |
| 추격 중에 다른 사람에게 맞으면 | 유지 시간과 무관하게 바로 다시 뽑는다(잠정: 3초에 한 번까지). 공격 중이면 공격은 끝까지 간다 |
| 닿을 수 없는 타깃 | `MoveTo` 의 부분 경로를 끄고, 추격이 실패하면 그 타깃을 5초(잠정) 후보에서 뺀다 |
| 인지 범위 | **두지 않는다.** 스폰이 곧 교전이다. 깨우는 시점이 필요해지면 단위 D 의 스포너가 정한다 |
| Modifier 노브 | 히어로 Attribute `Hostility`(기본 100, 비복제). 도발 · 탱커는 이 값을 올리는 GE 로 얹는다. B 는 노브와 읽는 쪽만 만든다 |
| 위협 기록을 누가 갖는가 | 컨트롤러의 서버 전용 `UAstralThreatComponent`(§8 ② 가 정한 자리) |
| 타깃 없음 재시도(0.5초) | 그대로 둔다 — 아래 ⑦ |
| 네트워크 | 전부 서버 전용. 새 복제 프로퍼티 0 |

### 결정

**① 가중 추첨.** (참고작의 뼈대)

- 후보 = 죽지 않았고 제외 중이 아닌 플레이어 폰(수집은 A 와 같은 `PlayerArray`).
- 가중치 `W = max(0, 적대심) × (1 + DamageWeight × 점유율)`. 점유율 = 최근 창 안에서 이 후보가 이 적에게 넣은 피해 ÷ 후보 전체가 넣은 피해(아무도 안 때렸으면 0).
- 뽑기는 순수 함수(`AstralEnemyTargeting::SelectWeightedIndex` — 가중치 배열과 0 ~ 1 값 하나를 받는다)로 떼어 자동 시험한다. 난수는 호출하는 쪽이 넣는다.
- 잠정값으로 두 사람이 같은 적대심일 때: 혼자 때린 사람 75 % · 안 때린 사람 25 %. 반반 때리면 50 % · 50 %. `Provoke` +50 인 사람과 아닌 사람이 똑같이 때리면 60 % · 40 %.
- **피해 기록이 하나도 없으면 추첨하지 않고 가장 가까운 후보를 고른다.** 스폰된 적이 옆 사람을 두고 먼 사람에게 달려가지 않게 한다. A 의 `SelectNearestIndex` 가 그대로 이 규칙이다.
- 적 여러 마리는 각자 따로 뽑는다. 분산시키는 규칙은 따로 두지 않는다.

**② 다시 뽑는 시점 — 유지 시간.**

- `AcquireTarget()` 이 불렸을 때 현재 타깃이 아직 유효하고(생존 · 제외 아님) 잡은 지 `HoldTime`(잠정 6초) 안이면 **그대로 유지** 한다. 지났으면 ① 로 뽑는다(같은 사람이 다시 뽑힐 수 있다).
- 시간은 타깃을 잡은 시각과 비교만 한다. 타이머 · 틱이 없다.
- 판단 지점은 A 와 같다 — 공격 한 사이클 뒤 · 타깃 상실 · 시작. 공격 한 사이클이 3초 안팎이므로 6초는 '두 번쯤 때리고 다시 본다' 에 해당한다.

**③ 추격 중 피격 재추첨.**

- 적이 현재 타깃이 아닌 후보에게 피해를 받으면 컴포넌트가 '다시 뽑기' 를 표시하고 트리에 `AI.Event.Retarget` 을 보낸다. `Chase` 만 이 이벤트로 `Acquire` 에 간다 — A 의 `TargetLost` 와 같은 모양이다.
- 표시가 서 있으면 다음 `AcquireTarget()` 은 유지 시간을 무시하고 ① 로 뽑는다. `Attack` · `Recovery` 중이면 이벤트는 버려지고 표시만 남아, 그 사이클이 끝난 뒤 반영된다.
- 연속 요청은 `RetargetCooldown`(잠정 3초)에 한 번만 받는다. 두 사람이 번갈아 때릴 때 추격 방향이 프레임마다 뒤집히지 않게 한다.
- 달아나는 한 사람만 쫓느라 아무도 못 때리는 상황을 이 규칙이 푼다 — 다른 사람이 때리면 돌아선다.

**④ 위협 입력 — `OnDamaged` 구독.**

- 컨트롤러가 빙의 때 폰 ASC 의 `UAstralHealthSet::OnDamaged`(`AstralHealthSet.cpp:137`, 서버)를 구독해 컴포넌트의 `RecordDamage(가해 폰, 피해량)` 에 넘긴다. 언포제션 · 사망 때 푼다. 폴링이 없다.
- 기록은 가해 폰별 (시각, 피해량)이고, 창 밖 기록은 읽을 때 버린다.
- **확인할 것:** 히어로가 준 피해의 `Instigator` 가 폰인지 PlayerState 인지. 히어로 ASC 의 오너는 PlayerState 다. 기록의 키는 폰으로 통일한다 — B0 에서 실측한다.

**⑤ Modifier 노브 — `Hostility`.** (§0-5 의 11번)

- `UAstralHeroResourceSet` 에 `Hostility` 를 더한다. 기본 100, 0 미만으로 내려가지 않는다. 같은 세트의 `BreakContributionMultiplier` · `UltGainMultiplier` 와 같은 예약 노브다.
- **복제하지 않는다.** 읽는 쪽이 서버의 적뿐이다(같은 세트의 `UltGain` · `MarkGain` 도 비복제다). UI 가 보여 줘야 하면 그때 복제를 켠다.
- 적은 후보의 ASC 에서 이 값을 읽고, 세트가 없으면 100 으로 본다 — `ResolveIncomingDamage` 가 `GuardDamageMultiplier` 를 읽는 방식과 같다(`AstralCombatStatics.cpp:320`).
- 리링크의 +50 / −50 을 그대로 얹을 수 있는 눈금이다(100 → 150 / 50).
- 도발 스킬 · 진 · 강제 타깃은 만들지 않는다. B 가 만드는 것은 노브와 읽는 쪽, 그리고 값이 추첨에 반영된다는 시험이다.

**⑥ 닿을 수 없는 타깃.** (§8 미해결)

- 트리의 `MoveTo.bAllowPartialPath` 를 끈다. 켜 두면 실패가 아니라 갈 수 있는 데까지 간 뒤 '성공' 해서 헛공격을 반복한다(§8 '실측이 더한 것').
- `Chase` 실패 → 새 상태 `Reject` → `Acquire`. `Reject` 의 Task(`FAstralStateTreeTask_ExcludeTarget`)가 현재 타깃을 `ExcludeTime`(잠정 5초) 후보에서 뺀다. 만료는 읽을 때 시각을 비교한다.
- 남은 후보가 없으면 `Acquire` 실패 → `Wait` 로 간다(A 와 같다).

**⑦ 타깃 없음 재시도는 그대로 둔다.** (§8 ② 가 B 로 넘긴 것)

- §8 은 '이벤트로 바꾸려면 명부가 필요하고 B 의 위협 표가 같은 명부를 요구할 것' 이라고 적었다. **이 설계에서는 요구하지 않는다** — 후보는 판단 시점에 `PlayerArray` 에서 모으고 피해 기록은 가해 폰 키로 둔다.
- 그러면 명부를 쓰는 곳은 '전원 사망 뒤 누가 부활했다' 를 깨우는 것 하나다. 만들려면 히어로 쪽에 등록 코드가 들어간다(베이스 또는 히어로 클래스 변경).
- 인지 범위를 두지 않으므로 `Wait` 는 평소 상태가 아니다. 전원 사망 · 전원 제외 · 아직 아무도 없음일 때만 돈다.
- 그래서 0.5초 재시도를 유지한다. **이벤트로 바꾸는 쪽을 원하면 승인 때 말해 달라** — 범위는 서버 전용 명부 서브시스템 1개 + 히어로 등록 + `Wait` 의 이벤트 전환이다.

**⑧ 구조.**

- `UAstralThreatComponent`(새 파일, 컨트롤러의 기본 서브오브젝트, 서버 전용): `RecordDamage` · `SelectTarget` · `ExcludeTarget` · `Reset`. 값(`DamageWeight` · `DamageWindow` · `HoldTime` · `RetargetCooldown` · `ExcludeTime`)은 이 컴포넌트의 프로퍼티라 `BP_EnemyController_Melee` 에서 고친다.
- `AAstralEnemyController::AcquireTarget()` 의 안쪽이 컴포넌트를 부르도록 바뀐다. `CurrentTarget` · `SetCurrentTarget()` · `TargetLost` 경로는 그대로다.
- 트리 `ST_Enemy_Melee` 의 바뀌는 곳: `Chase` 에 `Retarget` 이벤트 전환 · `Chase` 실패 전환을 `Wait` 에서 `Reject` 로 · `MoveTo.bAllowPartialPath = false` · 새 상태 `Reject`. 나머지 상태와 바인딩 2개는 그대로다.

### 대안과 기각 이유

| 대안 | 기각 이유 |
| :--- | :--- |
| 누적 위협이 가장 높은 한 명을 고정으로(MMO 식) | 사용자 방침과 다르다. 참고작의 표현은 '노려질 가능성' 이고, 액션 게임에서 한 명만 맞으면 나머지는 방어 3종을 쓸 일이 없다 |
| 피해와 무관한 순수 추첨(적대심만) | §0-2 가 B 의 결과로 적은 '여럿이 때리면 타깃이 바뀐다' 가 보이지 않는다. 피해 가중은 `DamageWeight = 0` 으로 끌 수 있게 둔다 |
| 사이클마다 무조건 다시 뽑기 | 3초마다 타깃이 바뀌어 적이 갈팡질팡한다. A 에서 이미 '사이클마다 바뀐다' 를 미해결로 적었다 |
| 유지를 '공격 N 회' 로 센다 | 공격이 끝났다는 것을 컴포넌트에 알리는 경로가 하나 더 필요하다. 시각 비교는 경로가 없다 |
| 유지 시간이 지나면 타이머로 깨운다 | 타이머가 하나 생기고, 공격 중에 깨우면 어차피 버려진다. 판단 지점이 이미 3초 안팎마다 온다 |
| 가중치에 거리를 넣는다 | 노브가 둘 더 는다. '첫 타깃은 가까운 사람' 으로 가장 어색한 경우만 막는다 |
| 인지 범위 + 주기 탐색 | 범위 밖 대기가 평소 상태가 되어 0.5초 재시도가 실제 폴링이 된다. 이벤트로 하려면 오버랩 컴포넌트나 AIPerception 이 필요하다. 참고 장르는 스폰이 곧 교전이다 |
| `Hostility` 를 공용 `UAstralCombatSet` 에 | 적이 적을 노릴 일이 없다. 히어로 전용 노브다 |
| `Hostility` 를 복제 | 클라이언트에 읽는 곳이 없다 |
| 닿을 수 없는 타깃을 경로 질의로 미리 거른다 | 후보마다 경로 탐색을 돌린다. 실패한 뒤 빼는 쪽이 싸고, 실패 통지는 이미 온다 |
| 명부 서브시스템(⑦) | 쓰는 곳이 하나이고 히어로 코드를 건드린다. 사용자 선택으로 남긴다 |

### 영향

| 대상 | 변경 | 상속 · 공용 영향 |
| :--- | :--- | :--- |
| `UAstralThreatComponent` (새 파일) | 추가 | 컨트롤러 자식 BP 전부가 물려받는다. `AcquireTarget()` 을 부르지 않는 트리(`BP_P2_*` · `BP_M3_*`)에서는 기록만 쌓이고 쓰이지 않는다 |
| `AAstralEnemyController` | 컴포넌트 생성 · `OnDamaged` 구독/해제 · `AcquireTarget()` 안쪽 · `Retarget` 이벤트 | 위와 같음 |
| `AstralEnemyTargeting` | 순수 함수 추가(`SelectWeightedIndex` 등). `SelectNearestIndex` 는 그대로 | 없음 |
| `UAstralHeroResourceSet` | Attribute 1(`Hostility`, 비복제) · 초기값 · 클램프 | 히어로 전원이 값을 갖는다. 읽는 곳은 적뿐이다. **히어로 코드에서 바뀌는 곳은 이것 하나** |
| StateTree Task 1 (새 파일) · 태그 1(`AI.Event.Retarget`) | 추가 | 없음 |
| `ST_Enemy_Melee` | ⑧ 의 네 곳 | 단위 A 의 시험(`EnemyCombat` · 시나리오)이 이 트리를 쓴다 — 회귀로 다시 돌린다 |
| `AAstralCombatCharacter` · `AAstralCharacter` · 더미 · 공격 GA · 플러그인 | **변경 없음** | |
| 복제 | **새 프로퍼티 0** | |

- **단위 A 의 시험이 달라질 수 있다.** A4 · A9 는 '가까운 쪽이 맞는다' 를 본다. 피해 기록이 없을 때는 가까운 사람이므로 그대로여야 한다. A5 의 '타깃이 죽으면 다른 사람' 도 후보가 한 명이라 그대로다. 달라지면 원인을 따진다.

### 미해결

- **누가 노려지는지 플레이어가 알 방법이 없다.** 지금은 적이 도는 방향과 예고뿐이다. 표시하려면 타깃을 복제해야 한다 — 단위 C 의 클라이언트 예고와 함께 본다.
- **회복 · 버프는 위협이 아니다.** 지원 스킬이 없다.
- **강제 타깃(도발 스킬)** 은 만들지 않는다. 얹을 자리는 `Hostility` 를 크게 올리는 GE, 또는 컴포넌트에 강제 타깃 함수다 — 스킬을 만들 때 정한다.
- **적 여러 마리가 한 사람에게 몰릴 수 있다.** 각자 따로 뽑기 때문이다. 4인 · 여러 마리로 돌려 본 뒤(단위 D · E) 분산 규칙이 필요한지 본다.
- **피해 기록이 없는 한 가까운 사람만 계속 노린다.** 아무도 안 때리는 적은 유지 시간이 지나도 같은 사람을 고른다.
- 값(가중 2.0 · 창 10초 · 유지 6초 · 재추첨 간격 3초 · 제외 5초 · 적대심 100)은 전부 잠정이다.

### 검증 계획

**B0 — 먼저 실행으로 확인한다.**

| # | 확인할 것 | 틀리면 |
| :--- | :--- | :--- |
| B0-1 | 히어로가 적을 때렸을 때 `OnDamaged` 의 `Instigator` 가 무엇인가(폰 / PlayerState) — 리슨 · Dedicated | 기록 키를 폰으로 바꾸는 변환을 넣는다(설계 변경 아님) |
| B0-2 | `bAllowPartialPath = false` 에서 닿을 수 없는 타깃이면 `MoveTo` 가 실패로 끝난다 | ⑥ 을 다시 본다(마스터 확인) |

**본 검증.** 추첨이 들어가므로 시험은 난수를 고정하거나 분포로 본다.

| # | 확인할 것 | 방법 | 판정 |
| :--- | :--- | :--- | :--- |
| B1 | 가중 뽑기 — 경계값 · 가중치 0 제외 · 전부 0 · 한 명 · 분포(시드 고정 N 회가 비율 안) | `AstralBreak.Enemy.SelectWeighted` | 자동 |
| B2 | 가중치 산술 — 점유율 · 피해 없음 → 가까운 사람 · 창 밖 기록 버림 · 유지 시간 · 제외 만료 | 순수 함수 시험(시각을 인자로) | 자동 |
| B3 | 추격 중 다른 사람이 때리면 타깃이 그 사람으로 간다(난수 고정) · 공격 중이면 공격이 끝난 뒤 | 멀티 PIE `AstralBreak.Net.EnemyAggro.*`(리슨 · Dedicated — A 의 틀) | 자동 |
| B4 | 유지 시간 안에는 타깃이 안 바뀌고, 지나면 다시 뽑는다 | 같은 시험 | 자동 |
| B5 | `Hostility` 를 올린 사람이 뽑힌다(난수 고정) · 0 이면 안 뽑힌다 | 같은 시험에서 서버가 값을 바꾼다 | 자동 |
| B6 | 닿을 수 없는 타깃 → 제외 → 다른 사람 · 제외가 풀리면 다시 후보 | 같은 시험. 맵에 닿을 수 없는 자리가 없으면 [소스] 로 남기고 이유를 적는다 | 자동(시도) |
| B7 | 회귀 — 에디터 자동 시험 `AstralBreak.` 전체를 **한 번** 돌린다(새 시험 + 단위 A 의 `EnemyCombat` 2 · `Assumptions` · `SelectNearest` + 선행 단위 시험이 같은 실행에 들어 있다) | B1 ~ B6 과 같은 에디터 실행 | 자동 |
| B8 | 빌드 — DebugGame(시험용) · Development 각 한 번, `Result:` 줄 확인 | 시험 전에 둘 다 빌드해 '빌드 뒤 재시험' 을 없앤다 | 자동 |
| B9 | 느낌 — 둘이 번갈아 때릴 때 타깃 전환이 납득되는가, 너무 자주 / 드물게 바뀌지 않는가 | 2인 PIE + `SpawnEnemy` | 사용자 |

- 난수를 고정하는 수단은 컴포넌트 안의 한 곳(추첨 값을 뽑는 함수)에 둔다. 시험이 그 값을 정할 수 있어야 하고, Shipping 에는 남지 않아야 한다 — 모양은 단위 세션이 고른다.
- 대조는 **다시 빌드하지 않는 것 1건** 만 둔다 — 시험 안에서 `DamageWeight` 를 0 으로 바꾸면 '때린 사람이 뽑힌다' 가 성립하지 않는 것을 같은 시험이 확인한다. 코드를 깨뜨렸다 되돌리는 대조 실험은 하지 않는다.

**검증 범위를 줄였다(2026-11-11, 사용자 방침 — 회귀에 사용량이 너무 든다. 필수만).** 사용량은 시험 개수가 아니라 에디터를 띄우고 내리는 횟수 · 빌드 횟수 · 로그를 읽는 횟수에서 나온다. 그래서 '에디터 한 번 · 빌드 두 번' 에 들어가는 것만 남겼다.

| 뺀 것 | 그래서 못 보는 것 | 언제 드러나는가 |
| :--- | :--- | :--- |
| 별도 프로세스 실행(`run_party_flow.py` 의 `enemy_combat` 등) | 실제 Dedicated 프로세스 · 2단계 리슨에서의 회귀 | 단위 E(3단계 전체)에서 돌린다. B 의 규칙은 서버 전용이라 넷 구성으로 달라질 것이 가해자 전달(B0-1)뿐이고, 그것은 한 프로세스 Dedicated 시험이 본다 |
| `-DisableAdaptiveUnity` 빌드 | 커밋 뒤 유니티로 합쳐질 때의 이름 충돌 | 다음 단위의 첫 빌드에서 난다(고치는 것은 이름 변경). 새 cpp 의 익명 네임스페이스에 흔한 이름을 두지 않는 것으로 예방한다 |
| 시나리오 도구 재실행(A2 · A3) | 고친 트리의 상태 순서 타임라인 | 같은 흐름을 `EnemyCombat` 시험이 결과로 본다 |
| 코드를 깨뜨리는 대조 실험 · 최종 빌드 뒤 전체 재실행 · Development 구성 실행 · 플러그인 회귀 | 시험이 실제로 떨어지는지의 추가 확인 · 구성 차이 | 플러그인은 건드리지 않는다. 구성 차이는 단위 E |

이 방침은 뒤 단위(C · D)에도 같이 적용하고, 뺀 것은 단위 E 에서 한꺼번에 돌린다.

### 구현 결과 (2026-11-11)

단위 B 구현 세션이 덧붙인다. 위의 결정 · 근거는 설계 때 쓴 그대로다. **결정 ① ~ ⑧ 을 설계대로 구현했고, B1 ~ B8 은 [실측] 통과다(B6 · B0-2 는 아래 단서). B9(느낌)는 사용자 몫이다. 커밋하지 않았다.**
실행은 전부 DebugGame 에디터 · `-unattended` 이고 Development 는 빌드만 했다. 수치는 `-stdout -FullStdOutLogOutput` 출력의 `ASTRAL_PIETEST` 줄에서 읽었다. 리슨 · Dedicated 의 수치는 아래 표에서 한 값이면 둘이 같았다는 뜻이다.

#### 바뀐 파일

| 파일 | 변경 |
| :--- | :--- |
| `AI/AstralEnemyTargeting.h` · `.cpp` | 순수 함수 추가: `SelectWeightedIndex` · `ComputeThreatWeight` · `IsWithinDuration` · `SumDamageInWindow` · `IsThreatEligible` · `SelectThreatIndex`. `SelectNearestIndex` 는 그대로 |
| `AI/AstralThreatComponent.h` · `.cpp` (새 파일) | `UAstralThreatComponent` — `RecordDamage` · `SelectTarget` · `ExcludeTarget` · `Reset` + 조회 3개, 프로퍼티 5개(잠정값) |
| `Character/Enemy/AstralEnemyController.h` · `.cpp` | 컴포넌트 생성, `OnDamaged` 구독/해제, `AcquireTarget()` 안쪽, `AI.Event.Retarget` 전송, 언포제션 · 사망 때 `Reset`. `CurrentTarget` · `SetCurrentTarget()` · `TargetLost` 경로는 그대로 |
| `AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h` · `.cpp` | Attribute `Hostility`(초기 100, 0 미만 클램프, 비복제) — 히어로 코드에서 바뀐 곳은 이것 하나 |
| `AI/StateTree/AstralStateTreeTask_ExcludeTarget.h` · `.cpp` (새 파일) | Task 1개 |
| `AbilitySystem/AstralEventGameplayTags.h` · `.cpp` | 태그 `AI.Event.Retarget` |
| `Tests/AstralEnemyTargetingTests.cpp` | `AstralBreak.Enemy.SelectWeighted` · `AstralBreak.Enemy.ThreatRules` 추가 |
| `AstralBreakEditor/Private/Tests/AstralEnemyAggroPieTests.cpp` (새 파일) | `AstralBreak.Net.EnemyAggro.{ListenPIE, DedicatedPIE}` |
| 애셋 `/Game/AI/Enemy/ST_Enemy_Melee` | `state-tree-mcp` 로 연산 7개 1회: 새 상태 `Reject`(ExcludeTarget → `Acquire`) · `Chase` 실패 전환 `Wait` → `Reject` · `Chase` 에 `AI.Event.Retarget` → `Acquire` · `MoveTo.bAllowPartialPath = false`. 컴파일 · 저장 fixups 0, 바인딩 2개 그대로(`inspect` 확인) [실측] |

건드리지 않은 것: `AAstralCombatCharacter` · `AAstralCharacter` · 더미 · 공격 GA 2종 · `ActivateAbility` · `AcquireTarget` Task · 맵 · 플러그인 · `Tools/net_test` · 단위 A 의 시험 파일. 새 복제 프로퍼티 0 · 새 RPC 0.

#### B0 결과

| # | 결과 | 구분 |
| :--- | :--- | :--- |
| B0-1 | **폰이다 — 변환을 넣지 않았다.** 클라이언트 히어로의 실제 기본 공격 입력에서 `OnDamaged` 의 `Instigator` 는 그 히어로의 서버 폰(`BP_Hero_Vesper_C`)이었고 PlayerState · 컨트롤러가 아니었다. 리슨 · Dedicated 같다. 피해 31.2 가 그대로 기록에 들어갔다. 소스로도 피해 경로가 `ApplyAttackHit` 하나이고 여기서 폰을 싣는다(`AstralCombatStatics.cpp:174`) | [실측] + [소스] |
| B0-2 | **부분 경로 경우는 실행하지 못했다.** 소스로는 설계대로다 — 부분 경로가 허용되지 않으면 탐색 결과가 `Fail` 이 되고(`RecastNavMesh.cpp:3394`), 경로가 없으면 이동 요청이 실패하며(`AIController.cpp:744` · `:890`), `MoveTo` 는 들어오는 자리에서 실패를 돌려준다(`StateTreeMoveToTask.cpp:145` ~ `:147`). 실행한 것은 다른 경우다 — 아래 B6 | [소스] |

#### 검증 결과

| # | 결과 | 구분 |
| :--- | :--- | :--- |
| B1 | **통과.** `AstralBreak.Enemy.SelectWeighted` — 경계값(300 : 100 에서 0.7499 / 0.75) · 범위 밖 값 · 가중치 0(앞 · 가운데 · 뒤) · 음수 · 전부 0 · 빈 배열 · 한 명 · 분포(시드 고정 2만 회가 60 / 30 / 0 / 10 % 에서 1.5 %p 안) | [실측] |
| B2 | **통과.** `AstralBreak.Enemy.ThreatRules` — 가중치 산술(설계 ① 의 75 / 25 · 50 / 50 · 60 / 40) · 피해 없음 → 가까운 사람(적대심 900 이어도) · 창 밖 기록 버림 · 유지 시간과 제외 만료의 시각 비교 · 죽은 후보 / 제외 중 / 적대심 0 은 어느 경로에서도 안 뽑힘 · 후보 없음. 월드에서도 확인: 기록이 없을 때 스폰된 적이 가까운 쪽(600 cm, 먼 쪽 1432 cm)을 잡았다 | [실측] |
| B3 | **통과(리슨 · Dedicated).** ① 추격 중: 가까운 쪽을 쫓는 적(556 cm 남음)을 먼 쪽이 때리자 0.017초 뒤(한 프레임) 타깃이 먼 쪽으로 바뀌었다. 예고는 한 번도 없었다. 추첨 값은 '피해 가중이 있어야만 때린 사람이 뽑히는' 값이다. ② 공격 중: 예고 중에 다른 사람이 때리자 표시만 서고 타깃은 그대로, 그 공격은 원래 타깃에게 15.0 을 넣었고, 판정 1.00초 뒤(회복 뒤 `Acquire`) 타깃이 바뀌었다 — 앞 타깃을 뽑은 지 3.73초로 유지 시간 안이었다. ③ 현재 타깃에게 맞은 것(B0-1 의 실제 공격)은 표시를 세우지 않았다. ④ 재추첨 간격: 받아들인 요청 2.00초 뒤의 다른 요청은 기록만 되고 표시가 서지 않았다 | [실측] |
| B4 | **통과(리슨 · Dedicated).** 다시 뽑으면 다른 사람이 나오게 값을 고정해 둔 상태에서 타깃이 6.23초 유지됐다(유지 시간 6.0초). 그 안에 판단 지점(`Acquire`)이 한 번 있었고 바뀌지 않았다. 유지 시간이 지난 뒤 첫 판단 지점에서 다시 뽑았다 | [실측] |
| B5 | **통과(리슨 · Dedicated).** 같은 추첨 값 0.5 에서 적대심 100 / 100 이면 때린 사람, 안 때린 쪽을 900 으로 올리면 그쪽이 뽑혔다. −50 을 넣으면 0 으로 읽혔고, 0 이면 그쪽을 가리키는 값으로도 안 뽑혔다. 초기값은 둘 다 100. 서버가 `SetNumericAttributeBase` 로 바꿨다(GE 는 만들지 않았다) | [실측] |
| 대조 | **통과.** 같은 시험 · 같은 추첨 값에서 `DamageWeight` 2 → 때린 사람, 0 → 안 때린 사람. 다시 빌드하지 않는 1건이다 | [실측] |
| B6 | **통과(리슨 · Dedicated) — 단, '경로 끝을 NavMesh 에 내릴 수 없는' 경우다.** 적이 옆에서 예고하는 동안 타깃 히어로를 3000 cm 위에 띄워 두자, 2.00초 뒤(남은 예고 1.0 + 회복 1.0 — 그 사이클이 끝난 자리)에 그 히어로가 제외되고 타깃이 다른 사람으로 바뀌었다(`Chase` 실패 → `Reject` → `Acquire`). 제외 중에는 그쪽을 가리키는 값으로도 안 뽑혔고, 내려놓은 뒤 제외 시간(5.0초)이 지나자 다시 뽑혔다. **맵에 섬(NavMesh 는 있지만 이어지지 않은 자리)을 만들 수 없어 '부분 경로' 경우는 돌리지 못했다** — `CombatTestMap` 을 고치지 않고 만들 방법이 없고(런타임 NavMesh 재생성을 쓰지 않는다), 그쪽은 B0-2 의 [소스] 로 남는다. 두 경우 모두 `Reject` 로 들어오는 전환은 같다 | [실측] / 부분 경로 [소스] |
| B7 | **통과.** `AstralBreak.` 전체 1회 = 43개 중 41 통과 · 2 실패(새 `EnemyAggro` 2개 — 시험 쪽 문제 2건, 아래). 시험만 고쳐 그 2개를 다시 돌려 2 / 2 통과. 단위 A 의 `EnemyCombat` 2개 · `Assumptions` · `SelectNearest` 와 선행 단위 `PartyFlow` 3개는 첫 실행에서 그대로 통과했다(런타임 코드는 두 실행 사이에 바뀌지 않았다) | [실측] |
| B8 | **통과.** `AstralBreakEditor Win64` DebugGame · Development 둘 다 `Result: Succeeded` — 구현 뒤 한 번씩, 시험 파일을 고친 뒤 한 번씩(파일 1개 컴파일) | [실측] |
| 사망 정리 | **통과.** 적이 죽는 호출 안에서 기록 · 표시 · 타깃이 비었다. 죽인 피해(`DamageSelf` — 가해자가 적 자신)는 기록되지 않았다 | [실측] |
| B9 | **미실행 — 사용자 몫.** 순서는 아래 | |

**첫 실행의 실패 2건은 시험 쪽이었다.** ① 히어로를 띄울 때 이동을 먼저 끄고 텔레포트했더니 엔진이 이동 모드를 낙하로 되돌려(`UCharacterMovementComponent::OnTeleported`) '공중에 머물렀다' 전제 검사가 떨어졌다(흐름 자체는 낙하 중에도 같은 결과였다). 순서를 바꿨다. ② 실제 공격 직후 PIE 를 내려, 끝나지 않은 공격 몽타주의 종료 노티파이가 풀린 ASC 로 이벤트를 보내 오류 로그가 남았다. 몽타주가 끝나도록 5초를 둔다.

#### 설계가 정하지 않아 구현하며 고른 것

| 항목 | 고른 것 | 이유 |
| :--- | :--- | :--- |
| 규칙의 순서 | 유지 시간을 먼저 본다 → 지났으면 ①(기록 없음 → 가까운 사람 / 아니면 추첨) | 설계 ② 의 문장 그대로다. 그래서 기록이 없을 때도 유지 시간 안에는 타깃이 안 바뀐다 — 단위 A 의 '사이클마다 가까운 사람으로 바뀐다' 가 함께 풀린다. 단위 A 시험은 그대로 통과했다 |
| '기록 없음' 의 범위 | 자격 있는 후보들의 최근 피해 합이 0 | 죽었거나 제외 중인 사람이 넣은 피해는 점유율의 분모에도 들지 않는다 |
| 적대심 0 | 추첨 · 가까운 사람 · 유지 어느 경로에서도 후보가 아니다. 전원이 0 이면 타깃 없음 → `Wait` | 'B5: 0 이면 안 뽑힌다' 가 경로와 무관하게 성립하게 |
| `RecordDamage` 의 모양 | `RecordDamage(가해 폰, 피해량, 현재 타깃)` → 다시 뽑기 요청이 섰으면 `true`. 이벤트는 컨트롤러가 보낸다 | 컴포넌트는 트리를 모른다. 타깃이 없을 때는 요청을 세우지 않는다(트리가 이미 고르는 중) |
| 기록하는 가해자 | 플레이어의 폰만(봇 · 다른 적 · 자기 자신 제외) | 후보 수집과 같은 기준 |
| 추첨 값 고정 | `SetRollOverrideForTest(값)` — 0 ~ 1 이면 고정, 음수면 해제. 함수와 멤버가 `#if !UE_BUILD_SHIPPING` 안이고, 값을 뽑는 곳은 `DrawRoll()` 하나(평소 `FMath::FRand`) | Shipping 에 남지 않는다. Shipping 빌드는 하지 않았다 [소스] |
| 다시 뽑아 같은 사람이 나왔을 때 | 유지 시간을 새로 센다. 요청 표시는 뽑든 유지하든 그 판단이 소비한다 | 설계 ② 의 '같은 사람이 다시 뽑힐 수 있다' |
| 시각 비교 | 유지 · 제외 · 재추첨 간격 · 피해 창이 전부 `IsWithinDuration(시작, 지금, 길이)` 하나 | 순수 함수 하나만 시험하면 된다 |
| 기록 정리 | `SelectTarget` 때 전체, `RecordDamage` 때 그 가해자 것 | `AcquireTarget()` 을 안 부르는 트리에서도 쌓이지 않는다 |
| `ExcludeTarget` Task | 컨트롤러의 컴포넌트를 직접 부르고 항상 성공. `CurrentTarget` 은 건드리지 않는다 | 비우거나 바꾸는 것은 다음 `Acquire` 의 몫이다(제외된 현재 타깃은 유지 조건에서 빠진다) |
| `Reject` 의 자리 | Root 의 마지막 자식 | 시작 상태(`Acquire`)의 선택 순서를 바꾸지 않는다 |
| 세트가 없는 후보의 적대심 | `AstralEnemyTargeting::DefaultHostility`(100) 상수 | Attribute 초기값과 같은 값을 읽는 쪽 한 곳에 둔다 |
| 시험이 넣는 '다른 사람의 피해' | 서버에서 `ApplyAttackHit`(실제 무기 판정이 쓰는 함수)를 1.0 으로 호출. 실제 클라이언트 입력은 B0-1 한 번 | 프레임 단위로 시점을 맞춰야 한다 |
| B5 · 대조의 추첨 | 한 프레임 안에서 유지 시간을 0 으로 두고 컨트롤러의 `AcquireTarget()` 을 직접 여러 번 부른다 | 트리 사이클을 기다리지 않고 실제 수집 · Attribute 읽기 · 추첨 경로를 탄다 |
| PIE 시험의 조회 함수 | 새 시험 파일 안에 따로 둔다(단위 A 시험 파일과 같은 모양의 사본) | 단위 A 의 시험 파일을 건드리지 않으려고. 공용 헤더로 빼는 것은 후속 후보다 |

#### 설계와 달라진 것

- **에디터를 두 번 띄웠고 빌드는 네 번이다**(계획은 한 번 · 두 번). 첫 실행의 시험 쪽 실패 2건을 고치느라 시험 파일 1개를 두 구성으로 다시 빌드하고 에디터를 다시 띄워 그 2개만 돌렸다.
- **B6 은 '부분 경로' 가 아니라 '경로 끝을 내릴 수 없는' 경우를 돌렸다**(위 표). `bAllowPartialPath = false` 가 실제로 일을 하는 장면은 실행하지 못했다.
- B2 의 시험 이름은 `AstralBreak.Enemy.ThreatRules` 다(설계는 이름을 정하지 않았다).
- 그 밖의 결정 ① ~ ⑧ 은 설계대로다.

#### 실측이 더한 것

- **히어로가 넣은 피해는 요청 값의 1.25배로 들어온다** — 1.00 을 넣자 1.25 가 기록됐다 [실측]. 기본 공격 31.2 도 같은 배율로 보인다 [추론 — 원인은 찾아보지 않았다]. 점유율은 비율이라 영향이 없다.
- 추격 중 재추첨은 한 프레임(0.017초)에 끝난다 [실측]. 닿을 수 없는 타깃의 `Chase` 실패 → `Reject` → `Acquire` 는 회복이 끝난 시각과 같은 표본에 잡혀 추가 지연이 없다 [실측] — 한 프레임 안이라는 것은 [추론].
- 유지 시간 6초 안에 판단 지점이 한 번 들어갔다(먼 쪽까지 추격한 뒤 한 번 공격) [실측]. 처음부터 붙어 있으면 두 번이 된다 [추론].
- `ThreatComponent` 의 값이 `BP_EnemyController_Melee` 디폴트에서 고쳐지는지는 에디터에서 열어 보지 않았다 [소스 — `EditAnywhere` 프로퍼티]. 시험은 인스턴스 값을 직접 바꿨다.
- 서버가 캐릭터를 텔레포트하면 바닥이 없을 때 이동 모드가 낙하로 바뀐다. 이동을 끈 상태(`MOVE_None`)도 예외가 아니다 [실측 — 시험 함정].

#### 돌리지 않은 것

- **B9(느낌)** — 사용자.
- 설계의 '검증 범위를 줄였다' 표 그대로: 별도 프로세스(`run_party_flow.py`) · `-DisableAdaptiveUnity` 빌드 · 시나리오 도구 · 코드를 깨뜨리는 대조 · Development 구성 실행 · 플러그인 회귀. 최종 빌드 뒤 전체 재실행도 하지 않았다(다시 돌린 것은 `EnemyAggro` 2개).
- 섬 위의 타깃(부분 경로) · 추격 도중에 타깃이 닿을 수 없게 되는 경우(시험은 서 있는 적 옆에서 띄웠다) · 3인 이상 · 적 여러 마리 · 접속 종료한 가해자의 기록(약한 참조라 정리 때 빠진다 [소스]) · 실제 추첨(`FMath::FRand`)의 분포 · Shipping 빌드.
- `Hostility` 를 올리는 GE — 만들지 않았다(설계 범위 밖). 시험은 서버에서 기본값을 직접 바꿨다.

#### 정리할 것

이 단위가 남긴 일회성 파일은 없다 — 스크래치 · `Tools/mcp/results` 에 쓴 것이 없고, 별도 프로세스 실행을 하지 않아 실행 기록 폴더도 생기지 않았다. 새 애셋도 없다(`ST_Enemy_Melee` 수정뿐).

#### B9 — 사용자가 볼 순서

1. 에디터에서 `CombatTestMap` 을 열고 **2인 PIE**(리슨 또는 Dedicated — New Editor Window 2개).
2. 한쪽 콘솔에서 `SpawnEnemy BP_Enemy_Melee 800`. 처음에는 가까운 사람을 쫓는다.
3. 볼 것:
   - 쫓기지 않는 사람이 때리면 적이 바로 돌아서는가(추격 중) · 예고 중에 때리면 그 공격은 끝내고 돌아서는가.
   - 둘이 번갈아 때릴 때 방향이 너무 자주 뒤집히지 않는가(재추첨 간격 3초) · 한 사람만 때리면 대체로 그 사람을 노리되 가끔 다른 사람에게도 가는가(75 % · 25 %).
   - 아무도 안 때리고 붙어 있으면 6초쯤마다(공격 두세 번) 다시 고르는 것이 납득되는가.
4. 값을 바꾸려면: `BP_EnemyController_Melee` 의 `ThreatComponent` 디폴트 — `Damage Weight` 2 · `Damage Window` 10 · `Hold Time` 6 · `Retarget Cooldown` 3 · `Exclude Time` 5. 적대심 기본값은 `UAstralHeroResourceSet` 의 초기값 100(C++)이고, 실행 중에 바꾸는 콘솔 명령은 만들지 않았다.

누가 노려지는지는 적이 도는 방향과 빨간 예고 캡슐로만 보인다(설계 '미해결').

#### 다시 돌리는 법

```
에디터:  AstralBreak.Enemy   (SelectNearest · SelectWeighted · ThreatRules · Assumptions)      AstralBreak.Net.EnemyAggro   (리슨 · Dedicated, 각 약 30초)
```

## 10. 단위 C — 수호병의 모습과 공격

상태: **C1 설계 승인(2026-11-12, 사용자 — 설계안 그대로) · 구현 · 자동 검증 완료(미커밋) · 남은 것 = G7 눈 확인(사용자). C2 는 정할 것만 적었다.** C1 의 실행 결과는 이 절의 'C1 구현 결과' 에 있고, 마스터 세션이 공격 GA 의 변경을 설계 ④ 와 대조해 일치를 확인했다(2026-11-12 — 시험을 다시 돌리지는 않았다). 이 절의 판단은 [소스] 다 — 에디터를 띄우지 않았고 애니메이션을 눈으로 보지 않았다(파일 목록과 애셋 안의 이름만 읽었다).

§0-2 의 단위 C 를 둘로 나눈다. 한 세션에 담기에 크고, 뒤쪽은 기획 답이 먼저 필요하다.

| 단위 | 내용 | 끝나면 보이는 것 |
| :--- | :--- | :--- |
| **C1** | 메시 · 로코모션 · 지금 있는 공격 1종을 몽타주로 · 사망 모습 | 미끄러지는 마네킹 대신 걷고 휘두르고 쓰러지는 수호병 |
| **C2** | 공격 여러 종 + 고르기 · 피격 반응 · 경직 GA · 가드 / 패링 태그 분리 · 약점 노출 | 방어 3종 연습이 된다(§0-2 C 의 원래 결과) |

§0-2 가 D 에 둔 '적 메시 · 애니' 는 C1 로 온다. D 에는 PawnData · 스폰이 남는다.

### 받은 애셋 (2026-11-12 사용자 지정)

메시 `SK_SciFi_Beast06_Skin1`, 팩 위치 `/Game/Assets/SciFi_Beast06/`. 사용자가 말한 것(공격 1 ~ 6 · Idle · Walk)보다 많이 들어 있다.

| 종류 | 애셋(`Anim_SciFi_Beast06_` 생략) | 쓰는 곳 |
| :--- | :--- | :--- |
| 대기 · 이동 | `Idle1` · `Idle2` · `WalkF` · `WalkF2` · `WalkB` · `WalkL` · `WalkR` · `Run` · `Turn180` | C1 — `Idle1` · `WalkF` · `Run` 만 |
| 공격 | `Attack1` ~ `Attack6` | C1 은 1개, C2 가 나머지 |
| 피격 | `GetHitF` · `B` · `L` · `R` (각 2종) | C2 |
| 사망 | `Death1` · `Death2` | C1 — `Death1` |
| 그 밖 | `Rage` · `JumpStart` · `JumpLoop` · `JumpEnd` | C2 후보(`Rage` = 경직 · 약점 노출 연출 후보) |

- 스켈레톤은 팩 고유(`SKEL_SciFi_Beast06_Skeleton`)이고 손가락 · 발가락 · 턱 본이 있다. 히어로 스켈레톤과 무관하다 — 히어로 애니 · AI 애니 생성 도구는 쓸 수 없다.
- 공격 애니에 루트 모션 관련 프로퍼티 이름이 들어 있다. 켜져 있는지, 각 공격이 어떤 동작인지, 타격 시점이 언제인지는 **확인하지 않았다**.

### C1 결론

| 질문 | 결정 |
| :--- | :--- |
| 어느 폰에 입히는가 | **새 BP `BP_Enemy_Guardian`.** 지금의 `BP_Enemy_Melee`(마네킹 · 타이머 공격)는 AI 규칙 시험의 고정물로 그대로 둔다 |
| 컨트롤러 · 트리 · 어그로 | `BP_EnemyController_Melee` · `ST_Enemy_Melee` 를 그대로 쓴다. C1 은 트리를 고치지 않는다 |
| 로코모션 | 새 ABP + 작은 네이티브 AnimInstance(속도 · 사망). 대기 — 걷기 — 달리기를 속도로 섞는다 |
| 공격 | 기존 단발 GA 에 **몽타주 방식** 을 더한다. 몽타주가 없으면 지금의 타이머 방식 그대로다 |
| 판정 | 지금의 전방 스윕을 몽타주의 타격 노티파이 시점에 낸다. 본 · 무기 트레이스는 쓰지 않는다 |
| 예고 | 몽타주의 준비 동작이 예고다. 클라이언트는 복제된 몽타주로 본다. 빨간 캡슐은 끌 수 있는 값으로 남긴다 |
| 사망 | ABP 가 복제되는 사망 상태를 보고 `Death1` 을 낸다. `GA_Death` 는 고치지 않는다 |
| 네트워크 | 새 복제 프로퍼티 0 |

### C1 결정

**① 새 폰 `BP_Enemy_Guardian`, 마네킹은 고정물로 남긴다.**

- 단위 A · B 의 시험(`EnemyCombat` · `EnemyAggro` · 시나리오)은 `BP_Enemy_Melee` 의 타이밍(예고 1.00초 · 회복 1.00초)에 맞춰져 있다. 그 폰을 바꾸면 시험을 전부 다시 맞춰야 한다. 새 폰을 두면 **기존 시험은 한 줄도 안 바뀐다.**
- 둘은 컨트롤러 · 트리 · 어그로 컴포넌트가 같다. 다른 것은 메시 · ABP · 캡슐 · AbilitySet(공격 GA 의 BP)뿐이다.
- `SpawnEnemy` 의 기본값은 그대로 `BP_Enemy_Melee` 다. 수호병은 `SpawnEnemy BP_Enemy_Guardian` 으로 부른다. 기본값을 바꾸는 것은 단위 D 에서 스폰을 정할 때 본다.

**② 메시 · 캡슐 · 거리.**

- 메시 `SK_SciFi_Beast06_Skin1`. 캡슐 크기와 메시 오프셋은 메시 경계에서 정한다(단위 세션이 재서 적는다).
- 캡슐이 커지면 `MoveTo` 가 멈추는 거리(`AcceptableRadius` + 두 캡슐 반경 — §8 실측)가 달라진다. 스윕이 닿는 거리 안에 서도록 **공격 GA 의 스윕 값을 수호병 쪽에서 맞춘다.** 트리의 `AcceptableRadius` 는 마네킹과 함께 쓰므로 건드리지 않는다.
- 이동 값(회전 모드 · 회전 속도)은 `BP_Enemy_Melee` 와 같게 둔다(§8 ⑤).

**③ 로코모션 — `ABP_Enemy_Guardian` + `UAstralEnemyAnimInstance`.**

- 네이티브 AnimInstance(새 파일)는 값 두 개만 낸다: 지면 속도, 사망 여부(`UAstralHealthComponent` 의 복제되는 사망 상태). 히어로의 `UAstralAnimInstance` 는 조준 · 제자리 회전 · 무기 파지까지 계산하는 히어로 전용이라 쓰지 않는다.
- 그래프: 1D 블렌드 스페이스(`Idle1` — `WalkF` — `Run`, 축 = 속도) → 몽타주 슬롯 → 사망이면 `Death1`(반복 없음).
- 적은 추격 중 가는 방향을 본다(§8 ⑤ 실측). 그래서 앞으로 걷는 애니만 있으면 된다. 옆 · 뒤 걸음과 `Turn180` 은 쓰지 않는다 — 제자리에서 돌 때는 대기 자세로 돈다.
- 블렌드 스페이스의 속도 눈금은 애니의 실제 이동 속도에 맞춘다(발 미끄러짐). 적의 `MaxWalkSpeed` 를 걷기와 달리기 중 어디에 맞출지는 단위 세션이 애니 속도를 재서 정하고 적는다.
- ABP · 블렌드 스페이스 · 몽타주는 `anim-graph-mcp` 도구와 `astral-ue-montage` 로 만든다(§6 의 'AI 활용 산출물' — 쓴 도구와 연산을 결과에 적는다).

**④ 공격 — 기존 GA 에 몽타주 방식을 더한다.**

- `UAstralGA_Enemy_MeleeAttack` 에 `AttackMontage`(선택)와 타격 이벤트 태그를 더한다.
  - **몽타주가 비어 있으면 지금 코드 그대로** 다(타이머로 예고 → 스윕). `GA_Enemy_MeleeAttack` 애셋은 손대지 않으므로 마네킹과 기존 시험은 영향이 없다.
  - 몽타주가 있으면: 몽타주 재생 → 몽타주의 노티파이가 보내는 타격 이벤트마다 스윕 1회 → 몽타주가 끝나면 종료. 취소되면 몽타주를 멈춘다.
- 타격 이벤트를 '마다' 로 받으므로 한 몽타주에 노티파이를 여러 개 두면 연타가 된다 — C2 가 이 모양을 그대로 쓴다.
- 타깃 추적(`FacingTrackDuration`) · `State.Telegraphing` · 패링당했을 때 경직만큼 머무는 임시 처리는 두 방식이 같은 코드를 쓴다. 예고 태그는 첫 타격 이벤트에서 내린다.
- 새 태그 1개: 타격 이벤트(`GameplayEvent.Enemy.AttackHit` — 이름은 기존 규칙에 맞춘다). 히어로의 `WeaponTrace.Begin` / `End` 는 구간이고 이것은 한 시점이라 따로 둔다.
- 새 애셋: `AM_Guardian_Attack`(몽타주 + 타격 노티파이), `GA_Guardian_Attack`(위 C++ GA 의 BP 자식 — 몽타주 · 스윕 값), `DA_AbilitySet_Enemy_Guardian`(`GA_Death` + `GA_Guardian_Attack`). 발동 태그는 `Ability.Enemy.Attack.Melee` 그대로라 트리가 바뀌지 않는다.
- **어느 공격 애니를 쓸지는 단위 세션이 고른다.** 여섯 개의 길이와 타격 시점을 재고, 준비 동작이 사용자가 A11 에서 확인한 1초에 가까운 것을 고른다(재생 속도 값으로 맞출 수 있다). 여섯 개의 표(길이 · 타격 시점 · 루트 모션 여부)를 결과에 남긴다 — C2 가 쓴다.
- C1 의 공격은 제자리다. 고른 애니에 루트 모션이 켜져 있으면 몽타주에서 끈다. 돌진은 C2.

**⑤ 클라이언트가 보는 것.**

- 몽타주는 `RepAnimMontageInfo` 로 복제된다(§0-1 — 적 ASC 가 Minimal 모드여도 조건 없이). 서버 전용 GA 의 몽타주를 클라이언트가 실제로 재생하는지는 **C1-0 에서 실측한다.**
- 빨간 예고 캡슐(DrawDebug 멀티캐스트)은 GA 의 값으로 켜고 끈다. 수호병은 처음엔 켜 둔다 — 준비 동작과 판정 범위가 맞는지 눈으로 보려는 것이고, 확인 뒤 사용자가 끈다.

**⑥ 사망.**

- ABP 가 사망 상태를 보고 `Death1` 을 낸다. 사망 상태는 이미 복제되므로(§1-6) 모든 머신이 같은 모습을 본다. `GA_Death` · 사망 시간(3초 + 제거 2초)은 그대로다.
- `Death1` 이 5초보다 길면 끝나기 전에 사라진다. 길이를 재고, 맞지 않으면 적 전용 `GA_Death` BP 자식으로 시간만 바꾼다(데이터).

### C1 대안과 기각 이유

| 대안 | 기각 이유 |
| :--- | :--- |
| `BP_Enemy_Melee` 를 수호병으로 바꾼다 | 단위 A · B 의 시험이 타이머 타이밍에 맞춰져 있어 전부 다시 맞춰야 한다. 회귀를 줄이라는 방침과 반대다 |
| 히어로의 무기 트레이스 Task(`AttackTraceWindows`)를 쓴다 | 무기 액터의 소켓 구간을 샘플링하는 Task 다. 맨몸 적에 쓰려면 Task 를 일반화하거나(히어로와 공용 코드 변경) 보이지 않는 무기를 손에 붙여야 한다. 전방 스윕은 이미 방어 판정 · 팀 필터를 탄다 |
| 몽타주용 GA 를 새 클래스로 | 예고 태그 · 타깃 추적 · 경직 처리가 세 번째로 복사된다. 한 클래스의 두 방식이면 공용 코드가 하나다 |
| 타이머는 그대로 두고 몽타주만 겹쳐 튼다 | 판정 시점이 애니의 타격 프레임과 따로 논다 |
| ABP 이벤트 그래프로 값 계산(네이티브 없이) | 값 두 개라 어느 쪽도 되지만, 사망 상태를 읽는 프로젝트 타입 접근은 C++ 이 짧고 시험하기 쉽다 |
| 사망을 몽타주로(`GA_Death` 자식) | §1-3 미해결의 `bAutoStartDeath = false` 경로를 연다. ABP 상태는 GA 를 건드리지 않는다 |
| 8방향 걷기 · 제자리 회전 애니 | 적이 가는 방향을 보므로 쓰이지 않는다. 회전 연출은 C2 에서 필요하면 |

### C1 영향

| 대상 | 변경 | 상속 · 공용 영향 |
| :--- | :--- | :--- |
| `UAstralGA_Enemy_MeleeAttack` | 프로퍼티 2(몽타주 · 타격 태그) + 몽타주 경로 | `GA_Enemy_MeleeAttack` 애셋은 몽타주가 비어 타이머 경로 그대로. **기존 시험이 이 불변을 확인한다** |
| `UAstralEnemyAnimInstance` (새 파일) · 태그 1 | 추가 | 없음 |
| 새 애셋 6: `BP_Enemy_Guardian` · `ABP_Enemy_Guardian` · 블렌드 스페이스 · `AM_Guardian_Attack` · `GA_Guardian_Attack` · `DA_AbilitySet_Enemy_Guardian` | 추가(`/Game/Characters/Enemy/Guardian/` 아래) | 팩 애셋(`/Game/Assets/SciFi_Beast06/`)은 읽기만 한다 |
| 컨트롤러 · 트리 · 어그로 · `AAstralCombatCharacter` · 히어로 · 루프 GA · `BP_Enemy_Melee` · 맵 | **변경 없음** | |
| 복제 | **새 프로퍼티 0** | |

### C1 미해결

- 여섯 공격이 각각 어떤 동작인지 모른다. C1 은 하나만 고르고 표를 남긴다.
- 제자리에서 돌 때 발이 미끄러진다(대기 자세로 돈다).
- 피격 반응이 없어 맞아도 움찔하지 않는다 — C2.
- 스윕은 전방 캡슐이라 팔이 지나가는 궤적과 다르다. 어색하면 C2 에서 공격별 스윕 값으로 맞추고, 그래도 안 되면 본 트레이스를 다시 본다.

### C1 검증 계획 — 줄인 범위(§9 의 방침 그대로)

**C1-0 — 먼저 실행으로 확인한다(첫 시험 실행에 포함).**

| # | 확인할 것 | 틀리면 |
| :--- | :--- | :--- |
| C1-0a | Dedicated 서버에서 몽타주 노티파이가 불려 피해가 난다(§0-1 의 [소스] — 메시가 항상 포즈를 갱신한다) | 타격 시점을 몽타주의 노티파이 시각에서 읽어 타이머로 낸다(마스터 확인) |
| C1-0b | 서버 전용 GA 의 몽타주를 클라이언트가 재생한다 | 멀티캐스트로 재생을 알린다(마스터 확인) |

| # | 확인할 것 | 방법 | 판정 |
| :--- | :--- | :--- | :--- |
| G1 | 서버 · 클라이언트의 수호병 폰에 메시와 ABP 가 붙어 있다 | 멀티 PIE `AstralBreak.Net.EnemyGuardian.{ListenPIE, DedicatedPIE}`(A 의 틀) | 자동 |
| G2 | 추격 중 클라이언트 AnimInstance 의 속도 값이 0 보다 크고, 멈추면 0 | 같은 시험 | 자동 |
| G3 | 공격: 클라이언트에서 몽타주가 재생 중이고, 서버 HP 가 타격 노티파이 시각에 준다 | 같은 시험 | 자동 |
| G4 | 사망: 클라이언트 AnimInstance 가 사망을 보고, 폰이 사라진다 | 같은 시험 | 자동 |
| G5 | 패링하면 피해 0 · 경직 동안 다음 공격 없음(A7 과 같은 것을 몽타주 방식에서) | 같은 시험 | 자동 |
| G6 | 회귀 — `AstralBreak.` 전체 1회(마네킹 고정물의 A · B 시험이 그대로 통과) · DebugGame / Development 빌드 각 1회 | 같은 에디터 실행 | 자동 |
| G7 | 눈 확인 — 발 미끄러짐 · 준비 동작이 예고로 읽히는가 · 크기와 판정 범위 · 쓰러지는 모습 | `CombatTestMap` 에서 `SpawnEnemy BP_Enemy_Guardian` | 사용자 |

- 하지 않는 것: 별도 프로세스 · `-DisableAdaptiveUnity` · 시나리오 도구 · 코드를 깨뜨리는 대조 · Development 실행 · 플러그인 회귀(단위 E).
- 에디터는 애셋 저작과 시험을 한 번에 한다. 저작 뒤 C++ 을 고쳐야 하면 에디터를 내리고 빌드한다(메모리 규칙이 우선).

### C1 구현 결과 (2026-11-12)

단위 C1 구현 세션이 덧붙인다. 위의 결정 · 근거는 설계 때 쓴 그대로다. **C1-0 은 둘 다 설계대로 나왔고, G1 ~ G6 은 [실측] 통과, G7(눈 확인)은 사용자 몫으로 남았다. 커밋하지 않았다.**
실행은 DebugGame 에디터 · `-unattended` 이고 수치는 `-stdout -FullStdOutLogOutput` 출력의 `ASTRAL_PIETEST` 줄에서 읽었다. Development 는 빌드만 했다.

#### 바뀐 파일 · 애셋

| 파일 · 애셋 | 변경 |
| :--- | :--- |
| `AbilitySystem/Abilities/Enemy/AstralGA_Enemy_MeleeAttack.h` · `.cpp` | 몽타주 방식. 프로퍼티 4(`AttackMontage` · `HitEventTag` · `MontagePlayRate` · `bDrawTelegraphDebug`) + 읽기 함수 5. 몽타주가 비면 기존 타이머 경로다(스윕 호출만 `SweepOnce()` 로 묶었다) |
| `AbilitySystem/AstralEventGameplayTags.h` · `.cpp` | 태그 `GameplayEvent.Enemy.AttackHit` |
| `Animation/AstralEnemyAnimInstance.h` · `.cpp` (새 파일) | `GroundSpeed` · `bDead` 두 값 |
| `AstralBreakEditor/Private/Tests/AstralEnemyGuardianPieTests.cpp` (새 파일) | `AstralBreak.Net.EnemyGuardian.{ListenPIE, DedicatedPIE}` — 기대값은 GA CDO 와 몽타주에서 읽는다 |
| `Tools/scripts/setup/enemy_guardian_assets.py` (새 파일) | 아래 애셋 중 노티파이 · GA · AbilitySet · 폰 BP 를 만든 스크립트. 잠정값이 맨 위에 모여 있다 |
| `/Game/Characters/Enemy/Guardian/BS_Guardian_Locomotion` | 1D, 축 `Speed` 0 ~ 300 — `Idle1` 0 · `WalkF` 180 · `Run` 300 |
| `/Game/Characters/Enemy/Guardian/ABP_Enemy_Guardian` | 부모 `UAstralEnemyAnimInstance`. 블렌드 스페이스(X ← `GroundSpeed`) → `DefaultSlot` → 불 블렌드(`bDead` 면 `Death1` 반복 없음, 블렌드 0.1초) |
| `/Game/Characters/Enemy/Guardian/AM_Guardian_Attack` | `Attack1` 1개, 블렌드 인 0.15 · 아웃 0.2, 0.45초에 타격 노티파이 1개(트랙 `Combat`) |
| `/Game/Characters/Enemy/Guardian/GA_Guardian_Attack` | 몽타주 · 재생 속도 0.45 · 피해 15 · 추적 0.7 · 스윕 45 / 165 / 75 · 빨간 캡슐 켬 |
| `/Game/Characters/Enemy/Guardian/DA_AbilitySet_Enemy_Guardian` | `GA_Death` + `GA_Guardian_Attack` |
| `/Game/Characters/Enemy/BP_Enemy_Guardian` | 부모 `AAstralCombatCharacter`. 캡슐 45 / 100 · 메시 z −100 · yaw −90 · `MaxWalkSpeed` 300. 컨트롤러 · 빙의 · 회전 값은 `BP_Enemy_Melee` 의 CDO 에서 읽어 그대로 넣었다 |

건드리지 않은 것: `BP_Enemy_Melee` · `GA_Enemy_MeleeAttack` · `DA_AbilitySet_Enemy_Melee` · 컨트롤러 · 트리 · 어그로 · Task · `AAstralCombatCharacter` · `AAstralCharacter` · 히어로 코드 · 기존 시험 파일 · 맵 · 팩 애셋 · 플러그인. 새 복제 프로퍼티 0 · 새 RPC 0. `GA_Death` 자식은 만들지 않았다(`Death1` 1.33초 < 5초).

#### 잰 값

방법: `anim-graph-mcp` 의 `inspect_skeleton`(geometry) · `validate_animation`(profile_bones · profile_positions — 30 fps 프레임마다 본의 컴포넌트 공간 위치와 속도). 메시 전방은 +Y 다. **동작 설명은 궤적에서 읽은 추정이다 — 눈으로 보지 않았다.**

| 메시(기준 자세) | 값 |
| :--- | :--- |
| 경계 | 폭 232(팔을 편 자세) · 앞뒤 −36 ~ +86 · 높이 −0.3 ~ 208 cm(머리 181, 등이 가장 높다) |
| 몸통 · 다리 폭 | 몸통 ±30 · 발 ±52 |
| 본 | 71개, UE4 마네킹 본 이름과 100 % 일치(`hand_r` · `foot_l` 등). 소켓 없음 |

| 이동 | 길이 | 루트 | 이동 속도 |
| :--- | ---: | :--- | :--- |
| `Idle1` | 6.67초 | 이동 0 | — |
| `WalkF` | 0.93초 | 이동 0(제자리) | **약 180 cm/s** — 디딤 구간(발 높이 최저) `foot_l` 의 뒤로 가는 속도 평균 179 |
| `Run` | 0.67초 | 이동 0(제자리) | **약 300 cm/s** — 디딤 구간 가운데 3프레임 평균 307 |
| `Death1` | 1.33초 | 이동 0 | — |

| 공격 | 길이 | 동작(추정) | 타격 시점 — 손 속도 최대 / 전방 최대 도달 | 정한 시각 |
| :--- | ---: | :--- | :--- | ---: |
| `Attack1` | 0.67 | 오른손을 뒤로 뺐다(0.33초, 뒤 73 cm) 앞으로 내지른다 | 0.43초(2,304 cm/s) / 0.47초(앞 122 cm) | **0.45** |
| `Attack2` | 1.00 | 몸을 한 바퀴 돌리며 왼손으로 휘두른다(손이 몸 뒤 194 cm 까지 돈다) | 0.50초(2,412) / 정면을 지나는 때 0.53 ~ 0.57초 | 0.55 |
| `Attack3` | 1.00 | 두 손을 뒤로 당겼다(0.30초) 함께 앞으로 민다 | 0.40 ~ 0.43초(1,559 · 1,294) / 0.50초(앞 108 · 119) | 0.47 |
| `Attack4` | 0.67 | 손은 낮고 느리다(최대 644). 가장 빠른 본이 종아리 — 발차기나 밟기 | 손으로는 못 잰다. 다리 회전 최대 0.33초 | 0.33(약함) |
| `Attack5` | 2.17 | 3연타 — 오른손 · 왼손 · 오른손 가로 휘두르기 | 0.43초(2,312, 앞 89) · 0.95초(2,463, 앞 96) · 1.30초(2,610, 앞 101) | 0.43 · 0.95 · 1.30 |
| `Attack6` | 0.67 | 오른손을 머리 위로 들었다(0.20초, 높이 160) 앞으로 내리친다 | 0.27초(1,689) / 0.40초(앞 128) | 0.35 |

- 열 개(위 표의 것) 모두 `bEnableRootMotion` = 거짓이고 루트 본 이동 0 이다 — **끌 루트 모션이 없다.** 전부 제자리 동작이다(돌진은 C2 에서 이동을 코드로 줘야 한다).
- 준비 동작은 여섯 개 모두 0.3 ~ 0.55초다. 1초짜리는 없다.

#### C1-0 결과 [실측]

| # | 결과 |
| :--- | :--- |
| C1-0a | **설계대로.** Dedicated 서버에서 몽타주의 노티파이가 불려 피해 15.0 이 났다. 몽타주 시작 1.01초 뒤(노티파이 0.45초 ÷ 재생 속도 0.45 = 1.00초) |
| C1-0b | **설계대로.** 서버 전용 GA 의 몽타주를 모든 클라이언트(리슨 1 · Dedicated 2)의 AnimInstance 가 재생했다. 멈춤(패링 · 사망)도 클라이언트에 왔다 |

#### 검증 결과

| # | 결과 | 구분 |
| :--- | :--- | :--- |
| G1 | **통과(리슨 · Dedicated).** 서버와 모든 클라이언트의 수호병에 메시 `SK_SciFi_Beast06_Skin1` · `ABP_Enemy_Guardian_C` · 캡슐 45 / 100. 컨트롤러는 서버에만 | [실측] |
| G2 | **통과.** 추격 중 클라이언트 AnimInstance 의 속도 최대 300, 선 뒤 0 | [실측] |
| G3 | **통과.** 히어로에서 198 ~ 199 cm 에 서서 공격. 서버 HP 가 몽타주 시작 1.00 ~ 1.01초 뒤 15.0 줄고 예고 태그가 같은 때 내려갔다. 먼 쪽 히어로는 안 맞았다. 클라이언트가 같은 HP 를 봤다. 어빌리티는 1.29 ~ 1.30초에 끝났다(몽타주 1.48초 — 블렌드 아웃이 시작될 때 끝난다). 다음 공격은 끝난 뒤 1.00 ~ 1.01초 | [실측] |
| G4 | **통과.** 세 번째 공격의 준비 동작 중에 죽였다 — 그 호출 안에서 몽타주 · 어빌리티 · 트리가 멈추고, 0.02초 뒤 모든 머신의 AnimInstance 가 사망을 봤고, 5.02 ~ 5.03초 뒤 폰이 사라졌다 | [실측] |
| G5 | **통과.** 방어 태그를 서버에서 직접 세운 채 맞으면 피해 0, 0.6초 안에 서버 · 클라이언트에서 몽타주가 멈췄고, 어빌리티는 판정 뒤 2.00 ~ 2.01초 더 머물렀고, 다음 공격은 3.03 ~ 3.04초 뒤. 히어로의 실제 패링 입력은 쓰지 않았다 | [실측] |
| G6 | **통과.** `AstralBreak.` 45/45(기존 43 + 새 2) — `EnemyCombat` · `EnemyAggro` · `Enemy.*` · `PartyFlow` 그대로 통과, 한 번에. `AstralBreakEditor Win64` DebugGame · Development `Result: Succeeded` | [실측] |
| G7 | **미실행 — 사용자 몫.** 순서는 아래 | |

#### 설계가 정하지 않아 고른 것

| 항목 | 고른 것 | 이유 |
| :--- | :--- | :--- |
| 공격 애니 | `Attack1`, 재생 속도 0.45 | 정면으로 한 번 내지르는 동작이라 전방 스윕과 모양이 맞고 가장 짧다. 준비 동작이 가장 긴 `Attack2`(0.55초)는 등을 보이며 도는 동작이라 타깃 추적 · 전방 판정과 어긋난다. 연타 · 회전 · 내리찍기는 C2 몫으로 남겼다. 0.45 ÷ 0.45 = 예고 1.00초(A11 에서 확인한 길이). **휘두르는 구간도 같이 느려진다(0.13 → 0.30초)** — 어색하면 재생 속도를 올리거나 C2 에서 준비 · 타격 구간을 나눠 속도를 따로 준다 |
| 패링당했을 때 몽타주 | **멈춘다**(블렌드 아웃) | 휘두르던 동작이 끊기는 것이 패링 성공의 표시다. 끝까지 재생하면 막았는데도 맞은 것처럼 보인다. 경직 동안은 대기 자세다(경직 애니는 C2) |
| 예고 길이의 원천 | 몽타주의 첫 타격 노티파이 시각 ÷ 재생 속도. `TelegraphDuration` 은 몽타주 방식에서 쓰지 않는다 | 시간의 원천을 몽타주 하나로 둔다. 타깃 추적(`FacingTrackDuration`)과 빨간 캡슐 길이가 이 값을 쓴다 |
| 어빌리티 종료 시점 | 블렌드 아웃이 시작될 때 | 히어로 GA 들과 같은 관용구(`OnBlendOut` · `OnCompleted` 를 같은 함수로) |
| 몽타주가 밀려났을 때 | 취소로 끝낸다(트리는 `Recovery` 로) | C2 의 피격 반응이 공격을 끊는 자리다 [소스 — 이 경로는 실행하지 않았다] |
| `MaxWalkSpeed` | **300**(= `Run` 의 속도). 마네킹은 600 | 블렌드 스페이스의 끝과 맞춰 최고 속도에서 발이 미끄러지지 않게 했다. 히어로보다 느린지는 기획이다 — 잠정 |
| 캡슐 | 반경 45 · 반높이 100 | 몸통 · 다리 폭과 높이. 팔을 편 폭(232)은 쓰지 않았다 |
| 스윕 | 시작 45 · 길이 165 · 반경 75(앞 285 cm) | 선 거리 199 + 여유. 마네킹(50 / 200 / 80, 앞 330)보다 조금 짧다 |
| 사망 값 읽기 | 이벤트 구독이 아니라 `NativeUpdateAnimation` 에서 매번 `IsDeadOrDying()` | 속도 때문에 어차피 매 프레임 도는 함수다. 원천을 그대로 읽으면 클라이언트 초기 복제 · 부활 때 값이 어긋날 자리가 없다 |
| 시험의 기대값 | GA CDO · 몽타주에서 읽는다(읽기 함수 5개를 GA 에 더했다) | 잠정값을 바꿔도 시험을 고치지 않는다 |

#### 설계와 달라진 것

- **GA 프로퍼티가 4개다.** 영향 표는 2개(몽타주 · 타격 태그)였다. 재생 속도 · 빨간 캡슐 표시 여부는 브리프가 더했다.
- **끌 루트 모션이 없었다.** 팩의 공격은 전부 제자리다.
- **에디터를 세 번 띄웠다**(계획은 한 번). 에디터 안 파이썬 원격 실행(`Tools/ue_exec.py`)이 여전히 에디터를 찾지 못해, MCP 저작 → `-ExecutePythonScript`(스스로 닫힌다) → 시험으로 나눴다. 빌드는 구성마다 한 번, `AstralBreak.` 은 한 번이다.
- 그 밖의 결정 ① ~ ⑥ 은 설계대로다.

#### 실측이 더한 것

- **손이 닿지 않는 거리에 선다.** 도달 판정은 중심 간 229 cm(150 + 캡슐 45 + 히어로 34)에서 나고 수호병은 제동 뒤 198 ~ 199 cm 에 선다 [실측]. `Attack1` 의 손 본은 앞 122 cm 까지 간다. 히어로 표면까지 30 ~ 40 cm 가 빈다 [추론 — 눈으로 보지 않았다]. 판정(앞 285 cm)은 닿는다. 캡슐을 줄여도 150 이 남아 풀리지 않는다 — 트리의 `AcceptableRadius` 를 적마다 주거나(트리 파라미터, C2 · D) 메시 스케일로 푼다. G7 의 '크기와 판정 범위' 에서 볼 것.
- 클라이언트가 몽타주를 본 시각이 서버와 0.00초 차이로 찍힌 것은 한 프로세스 PIE 라서다. 실제 망의 지연은 재지 않았다.
- NavMesh 는 기본 에이전트 크기로 구워져 있다. 캡슐 반경 45 인 폰이 좁은 곳을 지날 때는 보지 않았다(`CombatTestMap` 의 열린 바닥만) [추론].

#### 돌리지 않은 것

- **G7(눈 확인)** — 사용자. 애니메이션을 한 번도 눈으로 보지 않았다(캡처 도구도 쓰지 않았다).
- Development 실행 · 별도 프로세스(`run_party_flow.py`) · `-DisableAdaptiveUnity` 빌드 · 시나리오 도구 · 코드를 깨뜨리는 대조 실험 · 플러그인 회귀 — §10 의 줄인 범위대로.
- 가드(패링이 아닌) · 히어로의 실제 패링 입력 · 히어로가 수호병을 때려서 죽이기(`DamageSelf` 로 죽였다) · 수호병 여러 마리 · 레벨 배치.

#### G7 — 사용자가 볼 순서

1. 에디터에서 `CombatTestMap` → PIE(혼자 · 리슨 · Dedicated 아무 구성).
2. 콘솔 `SpawnEnemy BP_Enemy_Guardian 1200` — 멀리서 달려오는 것부터 본다. 가까이는 `SpawnEnemy BP_Enemy_Guardian`.
3. 볼 것: ① 달릴 때 · 멈출 때 발이 미끄러지는가 ② 팔을 뒤로 빼는 1초가 예고로 읽히는가, 느린 재생이 어색한가 ③ 선 자리에서 손이 나에게 닿아 보이는가(위 '실측이 더한 것'), 빨간 캡슐과 팔의 궤적이 맞는가 ④ 크기(높이 2 m) ⑤ 패링하면 팔이 멈추고 2초 서 있는가 ⑥ 죽으면 쓰러지고 5초 뒤 사라지는가(쓰러지는 데 1.3초) ⑦ 제자리에서 돌 때의 발(대기 자세로 돈다 — C1 미해결).
4. 값을 바꾸는 곳

| 바꿀 것 | 곳 |
| :--- | :--- |
| 예고 길이 · 휘두르는 속도 | `GA_Guardian_Attack` 의 `Montage Play Rate`(예고 = 0.45초 ÷ 이 값) |
| 타격 시점 | `AM_Guardian_Attack` 의 `Combat` 트랙 노티파이 위치. 하나 더 달면 연타 |
| 피해 · 추적 시간 · 경직 · 스윕 · 빨간 캡슐 끄기 | `GA_Guardian_Attack` 의 디폴트(`Draw Telegraph Debug`) |
| 공격 애니 바꾸기 | `AM_Guardian_Attack` 의 시퀀스를 바꾸고 노티파이를 위 표의 '정한 시각' 으로 |
| 이동 속도 · 회전 속도 · 캡슐 · 메시 위치 | `BP_Enemy_Guardian`(`Max Walk Speed` 를 바꾸면 `BS_Guardian_Locomotion` 의 `Run` 눈금도 같이) |
| 걷기 · 달리기 눈금 | `BS_Guardian_Locomotion` 의 샘플 위치 |
| 선 거리 · 회복 | `ST_Enemy_Melee`(마네킹과 함께 쓴다 — 바꾸면 `EnemyCombat` 시험의 값도 본다) |

#### 애셋을 만든 도구

| 도구 | 호출 | 한 일 |
| :--- | :--- | :--- |
| `anim-graph-mcp` `inspect_skeleton` | 1 | 메시 경계 · 본 |
| `anim-graph-mcp` `validate_animation` | 4 | 이동 4개 · 발 궤적 2개 · 공격 6개(손 궤적) |
| `anim-graph-mcp` `create_blendspace` | 1 | 블렌드 스페이스(축 1 · 샘플 3), 저장 |
| `anim-graph-mcp` `create_anim_montage` | 1 | 몽타주(슬롯 `DefaultSlot`), 저장 |
| `anim-graph-mcp` `create_animation_blueprint` | 1 | ABP |
| `anim-graph-mcp` `preview_graph_operations` → `apply_graph_operations` | 1 → 1 | **연산 10개**(노드 4 · 프로퍼티 바인딩 2 · 연결 4), 컴파일 오류 0 · 경고 0 · 저장. 미리보기가 바인딩 연산의 노드 지정 형식 오류 2건을 잡았다 |
| `Tools/scripts/setup/enemy_guardian_assets.py`(`ab_montage` · `ab_blueprint` = `astral-ue-montage` · `astral-ue-blueprint` 스킬의 헬퍼) | 1 | 노티파이 1 · GA BP · AbilitySet · 폰 BP. `-ExecutePythonScript` 로 실행 |

플러그인은 고치지 않았다. ABP 의 이벤트 그래프에는 노드가 없다(값은 네이티브 AnimInstance 가 낸다).

#### 정리한 것 (2026-11-12, 사용자 승인 뒤 휴지통으로)

이 단위가 남긴 일회성 파일은 `Tools/mcp/results/enemy_guardian_assets.json`(애셋 스크립트의 결과 기록, git 제외 경로) 하나였고 휴지통으로 보냈다. 스크립트를 다시 돌리면 다시 생긴다.

#### 다시 돌리는 법

```
에디터:  AstralBreak.Net.EnemyGuardian   (리슨 · Dedicated, 각 17초)
애셋을 다시 만들 때: 위 표의 MCP 호출 3종 → 에디터를 내리고
UnrealEditor-Win64-DebugGame.exe <uproject> -ExecutePythonScript=D:/UE5Projects/AstralBreak/Tools/scripts/setup/enemy_guardian_assets.py -unattended
```

### C2 — 공격 2종 · 방어 규칙 · 피격 반응 · 경직

상태: **구현 · 자동 검증 완료(2026-11-12, 미커밋) · 남은 것 = H7 눈 확인(사용자). 마스터 세션이 공용 피해 함수 · 컨트롤러의 변경을 결정 ④ · ⑦ 과 대조해 일치를 확인했다(시험을 다시 돌리지는 않았다).** 사용자 지시로 착수했다(2026-11-12 — "c2 세션 진행"). 기획 답 여섯 가지는 받지 않았다 — 아래 '잠정 기획' 은 전부 마스터가 고른 잠정안이고 값은 데이터에 둔다(§0-4).** 이 절의 판단은 [소스] 다. C1 은 커밋 `ff2ffa9`.

끝나면 보이는 것: **수호병이 연타와 강공격을 섞어 쓴다. 연타는 가드로 버티고, 강공격은 가드를 뚫어 패링이나 회피가 필요하다. 패링하면 수호병이 비틀거리며 그동안 더 아프게 맞는다. 맞으면 움찔한다.**

#### 잠정 기획 (여섯 가지의 답)

| # | 정할 것 | 잠정안 |
| ---: | :--- | :--- |
| 1 | 공격 매핑 | 기본 연타 = `Attack5`(3타), 강공격 = `Attack6`(내리찍기). `Attack1` 은 C1 의 것을 남겨 두되 수호병은 쓰지 않는다. **돌진은 넣지 않는다** — 팩의 공격이 전부 제자리라 이동을 코드로 줘야 하고, 부록 D 의 컷 라인에서 '선택' 이다 |
| 2 | 가드 · 패링 | 연타 = 가드 가능 · 패링 가능. 강공격 = **가드 불가 · 패링 가능** |
| 3 | 피격 반응 | 공격 중(공격 어빌리티가 켜져 있는 동안)에는 버틴다. 그 밖에는 맞은 방향으로 움찔하고, 한 번 움찔하면 2.5초 동안 다시 움찔하지 않는다 |
| 4 | 경직 · 약점 노출 | 패링당하면 2.0초 경직(`Rage` 재생 — 잠정). 경직 동안 받는 피해 1.5배 |
| 5 | 회피 무적 | **넣지 않는다.** 히어로 코드를 건드리는 일이고, 지금은 방향이 굳은 뒤 옆으로 빠지는 창이 있다 |
| 6 | 타깃 표시 | **넣지 않는다.** 복제 프로퍼티가 는다. 단위 D · E 에서 4인으로 돌려 본 뒤 정한다 |

값(잠정): 연타 타당 피해 8 · 강공격 30 · 강공격 예고 1.2초 · 연타 예고 1.0초 · 고르는 비율 반반.

#### C2 결정

**① 수호병 전용 트리 · 컨트롤러 BP.** `ST_Enemy_Guardian` · `BP_EnemyController_Guardian` 을 새로 만든다(`ST_Enemy_Melee` 와 같은 구조에서 시작). `BP_Enemy_Guardian` 의 `AIControllerClass` 만 바꾼다. 마네킹과 트리를 함께 쓰면 공격 고르기 · 경직 상태가 마네킹 시험을 깨뜨린다. **마네킹 쪽(`BP_Enemy_Melee` · `ST_Enemy_Melee` · `BP_EnemyController_Melee` · 그 GA)은 계속 불변이다.** 선 거리(`AcceptableRadius`)도 여기서 수호병에 맞게 줄인다 — 손이 닿아 보이는 거리로(C1 실측: 199 cm 에 서고 손은 122 cm).

**② 공격 고르기는 트리가 한다.** (부록 C 의 `SelectAttack`)

- `Attack` 을 그룹 상태로 바꾸고 자식 둘(`Attack_Combo` · `Attack_Heavy`)을 둔다. 고르는 방식은 엔진의 자식 무작위 선택(`TrySelectChildrenAtRandom`)이다. 저작 도구가 `SelectionBehavior` 를 쓸 수 있다(`AnimMcpTools_StateTree.cpp:28`).
- 자식마다 `ActivateAbility` Task 가 다른 태그를 부른다 — 새 태그 `Ability.Enemy.Attack.Combo` · `Ability.Enemy.Attack.Heavy`. Task 코드는 그대로다.
- 비율을 반반에서 바꾸려면 엔진의 가중 무작위(`TrySelectChildrenAtRandomWeightedByUtility` + 상수 Consideration)로 간다. C2 는 반반으로 시작한다.

**③ 공격 GA 는 C1 의 클래스 그대로, BP 둘.** `GA_Guardian_Combo`(`AM_Guardian_Combo` — `Attack5`, 타격 노티파이 3개) · `GA_Guardian_Heavy`(`AM_Guardian_Heavy` — `Attack6`, 노티파이 1개). 연타는 C1 이 만든 '타격 이벤트마다 스윕' 을 그대로 쓴다.

- **준비는 느리게, 휘두름은 원래 속도로.** C1 은 몽타주 전체를 0.45배속으로 틀어 휘두름까지 느렸다. 몽타주의 애니 세그먼트를 준비 구간 / 나머지로 나눠 준비 구간에만 느린 재생 속도를 준다(데이터 — 코드 없음). 도구나 스크립트로 세그먼트를 못 나누면, '휘두름 시작' 노티파이에서 GA 가 재생 속도를 올리는 방식으로 한다(코드 — 태그 1 · 프로퍼티 1). 어느 쪽을 썼는지 결과에 적는다.
- GA 클래스에 더하는 것: **피해에 실을 태그**(`DamageTags`), 공격 중임을 알리는 소유 태그(⑤ 가 쓴다). 수호병의 공격 GA 는 `StaggerRecovery = 0` 으로 둔다 — 경직은 ⑥ 의 GA 가 맡는다. 마네킹은 지금처럼 공격 GA 안에서 머문다.

**④ 가드 불가 · 패링 가능 — 태그 하나를 더한다.** (§0-5 의 2번)

- 새 태그 `Damage.Type.Unguardable`. `ResolveIncomingDamage`(`AstralCombatStatics.cpp:266`)에 한 갈래를 더한다: 패링 판정은 그대로 하고, **가드만** 이 태그가 있으면 감쇄 없이 통과시킨다. 기존 `Damage.Type.Unblockable`(둘 다 뚫음)은 그대로다.
- 태그를 싣는 길: `ApplyDamageSweep` · `ApplyAttackHit` 에 선택 인자(동적 애셋 태그, 기본 비어 있음)를 더해 스펙에 붙인다. **히어로와 함께 쓰는 함수다 — 기본값이 비어 있어 히어로 경로는 달라지지 않는다.** 히어로 공격은 이 태그를 쓰지 않는다.

**⑤ 피격 반응 GA — `UAstralGA_Enemy_HitReact`.** (§0-5 의 3번)

- `GameplayEvent.Damaged` 로 발동한다(HealthSet 이 피해 때마다 보낸다 — `AstralHealthSet.cpp:142`). 서버 전용. 맞은 방향(가해자 위치와 내 전방)으로 `GetHitF/B/L/R` 중 하나를 몽타주로 튼다 — 클라이언트는 복제된 몽타주로 본다(C1-0b 실측).
- 버티는 조건 = 발동 차단 태그다: 공격 중 태그 · 경직 중 태그 · 사망. 2.5초 간격은 GA 의 쿨다운(데이터)이다.
- 켜져 있는 동안 '행동 불가' 태그(`State.Enemy.Staggered`)를 갖는다 — ⑦ 이 본다.
- 피해 0(패링)은 이벤트가 오지 않으므로 반응하지 않는다.

**⑥ 경직 GA — `UAstralGA_Enemy_Stagger`.** (§0-5 의 9번, §4 의 '경직 대기')

- `GameplayEvent.Staggered` 로 발동한다. 진행 중인 공격 어빌리티를 취소하고, 경직 몽타주를 틀고, 켜져 있는 동안 '행동 불가' 태그와 **약점 노출 GE**(`IncomingDamageMultiplier` × 1.5 — 새 애셋 `GE_Enemy_Exposed`)를 건다. 2.0초 뒤 끝난다.
- 피격 반응보다 우선한다 — 경직 중에는 움찔하지 않는다(⑤ 의 차단 태그).

**⑦ 트리의 경직 대기 — 태그 이벤트로.**

- 컨트롤러가 폰 ASC 의 `State.Enemy.Staggered` 태그 변화를 구독한다(GAS 의 태그 이벤트 — 폴링 없음). 붙으면 트리에 `AI.Event.Staggered` 를 보낸다.
- 트리: Root 에 `AI.Event.Staggered` → `Stagger` 전환 하나(어느 상태에 있든 받는다). `Stagger` 의 Task(`FAstralStateTreeTask_WaitTagRemoved` — 새 파일, 태그 이벤트로 끝남 · 틱 없음)가 태그가 떨어질 때까지 기다리고 `Acquire` 로 간다.
- 움찔 · 경직 동안 이동과 공격이 멈춘다(상태를 나가며 `MoveTo` · 공격 GA 가 취소된다 — §1-8).

#### C2 영향

| 대상 | 변경 | 상속 · 공용 영향 |
| :--- | :--- | :--- |
| `UAstralCombatStatics` — `ApplyDamageSweep` · `ApplyAttackHit` · `ResolveIncomingDamage` | 선택 인자 1 · 가드 갈래 1 | **히어로와 공용.** 기본 인자가 비어 히어로 · 더미 · 마네킹 경로는 그대로여야 한다 — 기존 시험이 확인한다 |
| `UAstralGA_Enemy_MeleeAttack` | 프로퍼티 2(피해 태그 · 공격 중 태그) | 마네킹 · C1 의 GA BP 는 기본값이라 그대로 |
| `AAstralEnemyController` | 태그 구독 → 이벤트 1 | 자식 BP 전부가 물려받는다. `Stagger` 전환이 없는 트리(마네킹 등)에서는 이벤트가 버려진다 |
| 새 GA 2 · 새 Task 1 · 태그 5 안팎 | 추가 | 없음 |
| 새 애셋: 트리 · 컨트롤러 BP · 몽타주 2(공격) + 5(피격 4 · 경직 1) · GA BP 4 · GE 1 | 추가(`/Game/Characters/Enemy/Guardian/` · `/Game/AI/Enemy/`) | `DA_AbilitySet_Enemy_Guardian` · `BP_Enemy_Guardian` 은 수정(수호병 것) |
| 마네킹 쪽 애셋 · 히어로 코드 · `AAstralCombatCharacter` · 맵 · 팩 애셋 · 플러그인 | **변경 없음** | |
| 복제 | **새 프로퍼티 0** | 클라이언트가 보는 것은 복제된 몽타주와 HP 다 |

- **C1 의 시험(`EnemyGuardian`)은 고쳐야 한다.** 수호병의 공격이 바뀌기 때문이다. 마네킹 시험(`EnemyCombat` · `EnemyAggro`)은 그대로 통과해야 한다.

#### C2 미해결

- 경직 애니(`Rage`)와 공격 매핑은 궤적 추정으로 골랐다 — 눈으로 본 사람이 없다. 사용자 눈 확인에서 바꾼다(몽타주 교체 = 데이터).
- 연타 3타 사이에 타깃을 따라 돌지 않는다(첫 타 전에 방향이 굳는다). 옆으로 빠지면 2 · 3타가 빗나간다.
- 무작위 반반이라 강공격이 연달아 나올 수 있다.
- 4인이 계속 때릴 때 2.5초 간격이 적절한지는 단위 D · E 에서 본다.

#### C2 검증 계획 — 줄인 범위

**C2-0 — 첫 시험 실행에서 함께 본다.** 틀리면 우회하지 말고 마스터에 묻는다.

| # | 확인할 것 |
| :--- | :--- |
| C2-0a | 그룹 상태의 무작위 선택으로 두 자식이 다 골라진다 |
| C2-0b | Root 의 이벤트 전환이 `Chase` · `Attack` · `Recovery` 어느 상태에서 와도 `Stagger` 로 간다(공격이 취소로 끝나는 같은 틱에 와도) |

| # | 확인할 것 | 방법 | 판정 |
| :--- | :--- | :--- | :--- |
| H1 | 연타: 타격 3번 · 가드하면 감쇄 · 패링하면 0 + 남은 타격 없음 | 멀티 PIE `EnemyGuardian` 시험을 고친다. 방어 규칙은 트리를 멈추고 GA 를 직접 발동해 본다(무작위에 기대지 않는다) | 자동 |
| H2 | 강공격: 가드해도 전액 · 패링하면 0 | 같은 시험 | 자동 |
| H3 | 경직: 패링 뒤 2초 동안 공격 · 이동 없음, 그동안 받는 피해 1.5배, 끝나면 다시 쫓는다 | 같은 시험 | 자동 |
| H4 | 피격 반응: 맞으면 클라이언트에서 몽타주 재생 · 2.5초 안의 두 번째는 반응 없음 · 공격 중에는 반응 없음 | 같은 시험 | 자동 |
| H5 | 트리가 두 공격을 다 쓴다(C2-0a) | 같은 시험 — 제한 시간 안에 두 태그가 다 관측되는지 | 자동 |
| H6 | 회귀 — `AstralBreak.` 전체 1회(마네킹 · 히어로 시험 그대로) · 두 구성 빌드 각 1회 | 같은 에디터 실행 | 자동 |
| H7 | 눈 확인 — 두 공격이 구분되는가 · 준비 / 휘두름 속도 · 선 거리 · 움찔과 경직의 모습 | `SpawnEnemy BP_Enemy_Guardian` | 사용자 |

- 하지 않는 것은 §9 의 표 그대로다(별도 프로세스 · `-DisableAdaptiveUnity` · 시나리오 도구 · 코드를 깨뜨리는 대조 · Development 실행 · 플러그인 회귀 — 단위 E).

### C2 구현 결과 (2026-11-12)

단위 C2 구현 세션이 덧붙인다. 위의 결정 · 근거는 설계 때 쓴 그대로다. **C2-0 은 둘 다 설계대로 나왔고, H1 ~ H6 은 [실측] 통과(첫 실행에), H7(눈 확인)은 사용자 몫으로 남았다. 커밋하지 않았다.**
실행은 DebugGame 에디터 · `-unattended` 이고 수치는 `-stdout -FullStdOutLogOutput` 출력의 `ASTRAL_PIETEST` 줄에서 읽었다. Development 는 빌드만 했다. 아래 수치는 `Dedicated / 리슨` 순이다(같으면 하나만).

#### 바뀐 파일 · 애셋

| 파일 · 애셋 | 변경 |
| :--- | :--- |
| `AbilitySystem/AstralCombatStatics.h` · `.cpp` | `ApplyDamageSweep` · `ApplyAttackHit` 에 선택 인자 `DamageTags`(기본 빈 컨테이너 — 스펙의 동적 asset tag 로 붙는다). `ResolveIncomingDamage` 에 한 갈래: 패링 판정 뒤, `Damage.Type.Unguardable` 이면 가드 감쇄 · `Guarded` 이벤트 없이 통과. 기존 호출부는 고치지 않았다 |
| `AbilitySystem/Abilities/Enemy/AstralGA_Enemy_MeleeAttack.h` · `.cpp` | 프로퍼티 2(`DamageTags` · `SwingPlayRate`) + 읽기 함수 3. 휘두름 시작 노티파이를 받으면 재생 속도를 바꾼다. 기본값은 지금 동작 그대로다(그 노티파이가 없는 몽타주에서는 불리지 않는다) |
| `AbilitySystem/Abilities/Enemy/AstralGA_Enemy_HitReact.h` · `.cpp` (새 파일) | 결정 ⑤ |
| `AbilitySystem/Abilities/Enemy/AstralGA_Enemy_Stagger.h` · `.cpp` (새 파일) | 결정 ⑥ |
| `AI/StateTree/AstralStateTreeTask_WaitTagRemoved.h` · `.cpp` (새 파일) | 결정 ⑦ — 태그 이벤트로 끝남 · 틱 없음 |
| `Character/Enemy/AstralEnemyController.h` · `.cpp` | `BindPawnStaggered` · `UnbindPawnStaggered` · 핸들러 — `OnDamaged` 구독과 같은 세 자리(빙의 · 언포제션 · 사망)에서 걸고 푼다 |
| 태그 파일 2개 | 9개: `Ability.Enemy.Attack.Combo` · `.Heavy` · `Ability.Enemy.HitReact` · `Ability.Enemy.Stagger` · `State.Enemy.Attacking` · `State.Enemy.Staggered` · `Damage.Type.Unguardable` · `GameplayEvent.Enemy.AttackSwing` · `AI.Event.Staggered` |
| `AstralBreakEditor/Private/Tests/AstralEnemyGuardianPieTests.cpp` | H1 ~ H5 · C2-0 으로 다시 썼다(G1 · G2 · G4 는 이어 본다). 기대값은 GA CDO · 몽타주 · GE 에서 읽는다 |
| `Tools/scripts/setup/enemy_guardian_c2_assets.py` (새 파일) | 아래 애셋 중 노티파이 · GA · GE · AbilitySet · 컨트롤러 BP · 폰 BP. 잠정값이 맨 위에 모여 있고, 고쳐서 다시 돌리면 값이 다시 써진다 |
| `/Game/Characters/Enemy/Guardian/AM_Guardian_Combo` · `AM_Guardian_Heavy` | `Attack5` · `Attack6`. 트랙 `Combat` 에 휘두름 시작 1 + 타격 3 / 1 |
| `…/AM_Guardian_HitF` · `HitB` · `HitL` · `HitR` · `AM_Guardian_Stagger` | `GetHitF/B/L/R`(각 0.80초) · `Rage`(1.33초 — 섹션이 자신으로 이어져 반복한다) |
| `…/GA_Guardian_Combo` · `GA_Guardian_Heavy` · `GA_Guardian_HitReact` · `GA_Guardian_Stagger` · `GE_Enemy_Exposed` | 값은 아래 '고른 것' |
| `…/DA_AbilitySet_Enemy_Guardian` (수정) | `GA_Death` + 위 GA 4개. `GA_Guardian_Attack` 은 뺐다(애셋은 남아 있다) |
| `/Game/AI/Enemy/ST_Enemy_Guardian` · `BP_EnemyController_Guardian` | 전용 트리 · 컨트롤러(위협 값 5개는 마네킹 컨트롤러 BP 에서 읽어 같은 값) |
| `/Game/Characters/Enemy/BP_Enemy_Guardian` (수정) | `AIControllerClass` 만 |

건드리지 않은 것: 마네킹 쪽 애셋 5개와 그 시험 3개 · `ST_Enemy_Melee` · 히어로 코드 · `AAstralCombatCharacter` · `AAstralCharacter` · `UAstralThreatComponent` · 루프 GA · 맵 · 팩 애셋 · 플러그인 · `Tools/net_test`(`git status` 로 확인). 새 복제 프로퍼티 0 · 새 RPC 0.

#### C2-0 결과 [실측]

| # | 결과 |
| :--- | :--- |
| C2-0a | **설계대로.** 트리가 두 자식을 다 골랐다 — 고른 순서 `HHHC` / `CCCCH`(C 연타 · H 강공격). 반반 무작위라 같은 것이 3 ~ 4번 이어지기도 했다 |
| C2-0b | **설계대로.** 세 상태 모두에서 `Stagger` 로 갔다 — 행동으로 판정했다(아래 '고른 것'). ① `Chase`: 달리던 중(300 cm/s) 맞자 움찔하는 0.65초 동안 속도 0, 히어로에서 562 / 587 cm 떨어진 채 ② `Attack`(패링 — 공격이 취소로 끝나는 같은 틱): 경직 2.01 / 2.00초 동안 공격 시작 0, 다음 공격은 패링 2.01 / 2.00초 뒤(`Recovery` 로 갔다면 1.0초) ③ `Recovery`: 0.68초째(남은 0.32초)에 맞자 움찔이 끝난 0.66 / 0.65초 뒤에 다음 공격(전환이 안 먹었다면 0.32초 뒤 태그가 붙은 채 시작). 시험 전체에서 '행동 불가 태그가 붙은 채 시작한 공격' 은 0 |

#### 검증 결과

| # | 결과 | 구분 |
| :--- | :--- | :--- |
| H1 | **통과.** 직접 발동한 연타: 막지 않으면 8.0 × 3(발동 1.00 ~ 1.02 · 1.52 ~ 1.53 · 1.87 ~ 1.88초 — 기대 1.00 / 1.52 / 1.87) · 가드하면 4.0 × 3(히어로의 `GuardDamageMultiplier` 0.50) · 패링하면 히어로 피해 0, 첫 타격 시각(1.00초)에 연타가 취소되고 남은 타격 없음. 모든 클라이언트가 연타 몽타주를 재생 | [실측] |
| H2 | **통과.** 강공격: 가드해도 30.0 전액(1.20 ~ 1.21초 — 기대 1.20) · 패링하면 피해 0 + 경직. 클라이언트가 강공격 몽타주를 재생 | [실측] |
| H3 | **통과.** 패링 → 경직 2.00 ~ 2.01초, 그동안 공격 시작 없음(이동이 멈추는 것은 C2-0b 의 `Chase` 경우에서 봤다 — 경직 때는 이미 서 있었다), 받는 피해 배율 1.50(10 피해 → 15.0, 경직 밖에서는 1 → 1.0), 끝나면 배율 1.00 으로 돌아오고 트리가 다시 공격. 클라이언트가 경직 몽타주를 재생. 경직 중에 맞아도 움찔하지 않는다 | [실측] |
| H4 | **통과.** 맞으면 움찔(0.65초 — 몽타주 0.80초의 블렌드 아웃 시작까지), 모든 클라이언트가 그 몽타주를 재생 · 0.65초 뒤의 두 번째 피해에는 반응 없음(간격 2.5초) · 강공격 0.3초째에 맞아도 반응 없이 공격이 이어짐(마지막 움찔에서 9초 뒤 — 간격이 아니라 공격 중 태그가 막았다). '죽는 타격에는 움찔하지 않는다' 는 따로 가르지 못했다(시험의 사망은 공격 중이라 태그가 먼저 막는다) [소스] | [실측] |
| H5 | **통과** — C2-0a | [실측] |
| H6 | **통과.** `AstralBreak.` 45/45, 한 번에(`EnemyCombat` · `EnemyAggro` · `Enemy.*` · `PartyFlow` 그대로). `AstralBreakEditor Win64` DebugGame · Development `Result: Succeeded`(경고 0) | [실측] |
| G1 · G2 · G4(이어 본 것) | 통과 — 메시 · ABP · 컨트롤러 `BP_EnemyController_Guardian_C` · 추격 속도 · 공격 중 사망(몽타주 멈춤, 5.00 ~ 5.02초 뒤 폰 제거) | [실측] |
| H7 | **미실행 — 사용자 몫.** 순서는 아래 | |

#### 설계가 정하지 않아 고른 것

| 항목 | 고른 것 | 이유 |
| :--- | :--- | :--- |
| 준비만 느리게 | **휘두름 시작 노티파이 방식(코드).** 몽타주에 `GameplayEvent.Enemy.AttackSwing` 노티파이를 달고, 공격 GA 가 그 앞은 `MontagePlayRate`, 받은 뒤는 `SwingPlayRate`(1.0)로 튼다(`ASC->CurrentMontageSetPlayRate` — 복제된다) | 몽타주의 세그먼트(`SlotAnimTracks`)는 `UPROPERTY()` 뿐이라 파이썬에 나오지 않고(`ab_montage.py` 머리말에도 같은 제약), `create_anim_montage` 는 세그먼트 1개만 만든다. 플러그인을 고치지 않는 쪽 — 설계 ③ 의 둘째 안 |
| 준비 구간의 끝 | 연타 0.27초(`hand_r` 이 뒤로 다 빠진 때 — 전방 −105 cm · 속도 최소, 0.267초 [실측 궤적]) · 강공격 0.20초(C1 표) | 준비 재생 속도는 스크립트가 예고 길이에서 계산한다: 연타 0.321(준비 0.84초) · 강공격 0.190(준비 1.05초). 휘두름은 0.16 / 0.15초 |
| 움찔 간격 | **시각 비교**(GA 인스턴스가 마지막 발동 시각을 쥐고 `CanActivateAbility` 에서 `MinInterval` 과 견준다) | 서버 전용 어빌리티라 클라이언트에 알릴 것이 없다 — 쿨다운 GE 는 애셋 1 + 복제되는 GE · 태그가 는다 |
| 죽는 타격 | 움찔하지 않는다(체력 0 이하면 발동 거부) | `Damaged` 이벤트가 사망 처리보다 먼저 온다 — 움찔 몽타주를 틀었다 바로 끊게 된다 |
| 움찔 방향 | 가해자가 앞 → `GetHitF`, 뒤 → `B`, 좌 / 우 → `L` / `R`(전방 · 우측 내적 중 큰 쪽) | 팩의 이름을 '맞은 쪽' 으로 읽었다 — 눈으로 보지 않았다. 반대면 GA BP 에서 몽타주를 바꿔 끼운다 |
| 경직 몽타주 | `Rage` 를 반복(섹션이 자신으로 이어짐), 끝은 경직 타이머 | 1.33초라 2.0초에 못 미친다 — 반복하지 않으면 0.7초를 대기 자세로 서 있는데 약점은 드러난 채다 |
| 공격 GA 의 태그 | asset tag · `State.Enemy.Attacking` · `DamageTags` 모두 **GA BP 에서** 준다(엔진의 `AbilityTags` · `ActivationOwnedTags` 프로퍼티). C++ 생성자는 그대로 | 마네킹 · C1 BP 의 값이 한 글자도 바뀌지 않는다 |
| 선 거리 · 판정 | `AcceptableRadius` 75 → **중심 간 122 cm 에 선다** [실측](C1 은 150 → 199). 스윕 45 / 100 / 65(앞 210 cm) | 손이 앞 89 ~ 128 cm 까지 가고 히어로 표면은 88 cm 다 [추론 — 눈으로 보지 않았다] |
| 타깃 추적 | 연타 0.7초 · 강공격 0.9초(둘 다 첫 타격 0.3초 전에 방향이 굳는다) | C1 과 같은 창 |
| 트리 | `Attack` = 그룹(`TrySelectChildrenAtRandom`), 완료 전환은 자식마다(→ `Recovery`), Root 의 `Staggered` 전환은 우선순위 High, `Stagger` 완료 → `Acquire`. 나머지 값은 `ST_Enemy_Melee` 그대로(`Wait` 0.5 · `Recovery` 1.0) | |
| 블렌드 | 공격 0.15 / 0.2 · 움찔 0.1 / 0.15 · 경직 0.15 / 0.25 | |
| 시험 — C2-0b | 상태 이름이 아니라 **행동**으로 판정(멈춤 · 공격 시작 시각 · '태그가 붙은 채 시작한 공격 수') | `UStateTreeComponent::GetActiveStateNames` 는 `WITH_GAMEPLAY_DEBUGGER` 안에만 있다(시험 모듈의 Build.cs 를 건드려야 한다) |
| 시험 — 그 밖 | 방어는 히어로의 방어 태그를 서버에서 직접 세움 · 수호병을 때리는 것은 `DamageSelf` · 히어로 체력은 시험이 채움(트리를 오래 돌려도 안 죽게) · 애셋 스크립트는 C1 것 옆에 새 파일 | C1 과 같은 방식 |

#### 설계와 달라진 것

- **세그먼트로 나누지 못했다** — 위 첫 줄. 설계가 적어 둔 둘째 안(코드: 태그 1 · 프로퍼티 1)이다.
- **태그가 9개다**(설계는 5개 안팎). 휘두름 시작 1 + 피격 반응 · 경직의 asset tag 2 가 늘었다.
- **`UAstralGA_Enemy_MeleeAttack` 의 새 프로퍼티는 `DamageTags` · `SwingPlayRate`** 다. 설계의 '공격 중 태그' 는 새 프로퍼티가 아니라 엔진의 `ActivationOwnedTags` 를 BP 에서 채웠다.
- **에디터를 세 번 띄웠다**(MCP 저작 → `-ExecutePythonScript` → 시험 — C1 과 같은 이유). 빌드는 DebugGame 2(첫 번은 시험 파일의 괄호 누락으로 실패) · Development 1, `AstralBreak.` 은 1회.
- 그 밖의 결정 ① ~ ⑦ 은 설계대로다.

#### 실측이 더한 것

- **경직 · 움찔이 끝나면 쉬지 않고 바로 공격을 시작한다.** `Stagger` → `Acquire` → `Chase`(이미 닿아 있음) → `Attack` 이 같은 프레임에 이어져, 경직이 끝난 그 순간(패링 2.00초 뒤) 다음 예고가 시작됐다. 예고가 1.0 ~ 1.2초라 반격 창은 경직 2초 + 예고다. 쉬게 하려면 `Stagger` 의 완료 전환을 `Recovery` 로 돌린다(트리 값).
- **움찔은 `Recovery` 를 새로 센다.** 쉬는 중에 맞으면 움찔(0.65초) 뒤 바로 공격이라, 맞은 시점에 따라 다음 공격이 빨라지기도 늦어지기도 한다. 간격 2.5초가 상한을 둔다.
- 클라이언트는 몽타주를 '재생했다' 까지만 봤다. 재생 속도가 바뀌는 시점이 클라이언트에서 서버와 얼마나 어긋나는지는 한 프로세스 PIE 라 재지 않았다.

#### 돌리지 않은 것

- **H7(눈 확인)** — 사용자. 애니메이션을 눈으로 보지 않았다(캡처 도구도 쓰지 않았다).
- 히어로의 실제 가드 · 패링 입력, 히어로가 실제 공격으로 수호병을 때리는 것(가해자 방향 → 뒤 · 좌 · 우 몽타주 선택은 [소스]. 시험의 `DamageSelf` 는 앞 몽타주만 탄다).
- `Damage.Type.Unblockable` 의 동작(코드는 그대로 — 쓰는 곳이 아직 없다), 수호병 여러 마리, 레벨 배치.
- Development 실행 · 별도 프로세스(`run_party_flow.py`) · `-DisableAdaptiveUnity` 빌드 · 시나리오 도구 · 코드를 깨뜨리는 대조 실험 · 플러그인 회귀 — 줄인 범위대로.

#### H7 — 사용자가 볼 순서

1. 에디터에서 `CombatTestMap` → PIE(혼자 · 리슨 · Dedicated 아무 구성) → 콘솔 `SpawnEnemy BP_Enemy_Guardian`(멀리서는 `… 1200`).
2. 볼 것: ① 두 공격이 구분되는가 — 연타(오른손을 뒤로 빼는 0.84초 뒤 3타) · 강공격(손을 머리 위로 드는 1.05초 뒤 내리찍기) ② 준비는 느리고 휘두름은 빠른가, 속도가 바뀌는 순간이 튀는가 ③ 선 거리(122 cm)에서 손이 닿아 보이는가, 빨간 캡슐과 맞는가 ④ 가드: 연타는 절반 · 강공격은 전액 ⑤ 패링: 팔이 멈추고 2초 포효(`Rage` 반복)하며 그동안 1.5배로 맞는가 ⑥ 때리면 맞은 쪽으로 움찔하는가(방향이 반대로 보이는지), 2.5초에 한 번만인가, 공격 중에는 버티는가 ⑦ 경직이 끝나자마자 다음 예고가 시작되는 것이 괜찮은가.
3. 값을 바꾸는 곳 — GA BP 를 직접 고치거나, 스크립트 맨 위의 잠정값을 고쳐 다시 돌린다

| 바꿀 것 | 곳 |
| :--- | :--- |
| 공격 비율 | `ST_Enemy_Guardian` 의 `Attack` — 선택 방식을 `TrySelectChildrenAtRandomWeightedByUtility` 로 바꾸고 자식에 상수 Consideration. 한 가지만 쓰려면 다른 자식을 끈다 |
| 피해 · 가드 불가 | `GA_Guardian_Combo` · `GA_Guardian_Heavy` 의 `Base Damage` · `Damage Tags` |
| 예고 길이 · 휘두름 속도 | 같은 GA 의 `Montage Play Rate`(준비 구간 — 예고 = 휘두름 시작 시각 ÷ 이 값 + 휘두름 구간) · `Swing Play Rate`. 스크립트에서는 `telegraph` 만 고치면 속도를 계산한다 |
| 타격 시점 · 준비 구간의 끝 | `AM_Guardian_Combo` · `AM_Guardian_Heavy` 의 `Combat` 트랙 노티파이(스크립트의 `hit_times` · `swing_start`) |
| 움찔 간격 · 몽타주 | `GA_Guardian_HitReact` 의 `Min Interval` · 몽타주 4개 |
| 경직 시간 · 몽타주 | `GA_Guardian_Stagger` 의 `Stagger Duration` · `Stagger Montage`(반복은 `AM_Guardian_Stagger` 의 섹션) |
| 약점 배율 | `GE_Enemy_Exposed` 의 Modifier(1.5) |
| 선 거리 · 쉬는 시간 | `ST_Enemy_Guardian` 의 `Chase` → `Move To` → `AcceptableRadius`(75) · `Recovery` 의 `Duration`(1.0 — 바꾸면 시험의 `RecoverySeconds` 도). 선 거리를 늘리면 공격 GA 의 스윕 값도 본다 |
| 몽타주 교체 | 새 몽타주를 만들어 GA 의 몽타주 칸에 끼운다(공격은 노티파이 2종을 단다) |
| 어그로 값 | `BP_EnemyController_Guardian` 의 `ThreatComponent` |

#### 애셋을 만든 도구

| 도구 | 호출 | 한 일 |
| :--- | :--- | :--- |
| `anim-graph-mcp` `validate_animation` | 2 | `Attack5` 의 `hand_r` 궤적(준비 구간의 끝) · 피격 4 + `Rage` 구조 검사 |
| `anim-graph-mcp` `create_anim_montage` | 7 | 몽타주 7개(슬롯 `DefaultSlot`), 저장 |
| `anim-graph-mcp` `set_montage_sections` | 1 | `AM_Guardian_Stagger` 반복 |
| `state-tree-mcp` `inspect_state_tree` · `create_state_tree` | 1 · 1 | `ST_Enemy_Melee` 읽기 · 빈 트리 |
| `state-tree-mcp` `preview_state_tree_operations` → `apply_state_tree_operations` | 1 → 1 | **연산 33개**(상태 9 · Task 8 · 바인딩 3 · 전환 13), 컴파일 오류 0 · 고침 0 · 저장 |
| `Tools/scripts/setup/enemy_guardian_c2_assets.py`(`ab_montage` · `ab_blueprint` = `astral-ue-montage` · `astral-ue-blueprint` 스킬의 헬퍼) | 1 | 노티파이 6 · GA BP 4 · GE 1 · AbilitySet · 컨트롤러 BP · 폰 BP. `-ExecutePythonScript` 로 실행, 한 번에 `ok` |

플러그인은 고치지 않았다.

#### 정리한 것 (2026-11-12, 사용자 승인 뒤 휴지통으로)

이 단위가 남긴 일회성 파일은 `Tools/mcp/results/enemy_guardian_c2_assets.json`(애셋 스크립트의 결과 기록) 하나였고 휴지통으로 보냈다. 스크립트를 다시 돌리면 다시 생긴다.

#### 다시 돌리는 법

```
에디터:  AstralBreak.Net.EnemyGuardian   (Dedicated · 리슨, 각 42 ~ 46초)
애셋을 다시 만들 때: 위 표의 MCP 호출 → 에디터를 내리고
UnrealEditor-Win64-DebugGame.exe <uproject> -ExecutePythonScript=D:/UE5Projects/AstralBreak/Tools/scripts/setup/enemy_guardian_assets.py -unattended      (C1 — 이미 있으면 건너뛴다)
UnrealEditor-Win64-DebugGame.exe <uproject> -ExecutePythonScript=D:/UE5Projects/AstralBreak/Tools/scripts/setup/enemy_guardian_c2_assets.py -unattended   (C2 — 값을 다시 쓴다)
```

## 11. 단위 D — 수호병 여러 마리가 나온다

상태: **설계안 — 사용자 승인 대기(2026-11-12). 이 절의 판단은 [소스] 다 — 실행한 것은 없다.** §0-2 의 단위 D 이고 목차 6번의 나머지다. C2 는 사용자가 눈으로 확인했다(2026-11-12).

끝나면 보이는 것: **레이드 맵에서 정해 둔 구역에 들어서면 수호병 세 마리가 나타나 덤비고, 다 잡으면 그 구역이 끝났다는 신호가 난다. 리슨과 Dedicated 에서 같다.**

### 결론

| 질문 | 결정 |
| :--- | :--- |
| 무엇이 적을 내보내는가 | 맵에 놓는 `AAstralEnemySpawner`. 플레이어가 그 구역(상자)에 들어오면 서버에서 한 번 스폰한다 |
| 스폰 · 제거의 이음매 | 서버 전용 `UAstralEnemySpawnSubsystem` 하나. 스폰도 제거도 여기를 거친다 — 나중에 풀링을 넣을 자리다. MVP 의 안쪽은 지금과 같은 `SpawnActor` · `LifeSpan` 이다 |
| 사망 뒤 제거 | `AAstralCombatCharacter::HandleDeathFinished` 가 `SetLifeSpan` 을 직접 부르지 않고 위 서브시스템에 넘긴다. **동작은 같다** |
| 다 잡았다는 신호 | 스포너의 `OnCleared`(자기가 낸 적이 전부 죽기 시작했을 때 1회). 쓰는 곳은 아직 없다 — M6 의 구역 진행이 받을 자리 |
| 적 PawnData · InitState | **들이지 않는다.** 적이 한 종류이고 BP 가 이미 데이터 묶음이다 |
| 적끼리 겹침 | 수호병 BP 의 이동 컴포넌트에서 회피(RVO)를 켠다 — 값 하나 |
| 맵 | `RaidMap` 에 스포너 1개(수호병 3마리). 시작 지점에서 떨어진 곳에 둔다 |
| 디버그 명령 `SpawnEnemy` | 같은 서브시스템을 거치게 바꾼다 |
| 네트워크 | 전부 서버 전용. 새 복제 프로퍼티 0 |

### 결정

**① 스폰 · 제거의 이음매 — `UAstralEnemySpawnSubsystem`.** (계획서 M3 예약 '스폰/디스폰 인터페이스 분리', 부록 C '적 1종이 완성된 뒤 스포너를 붙이는 시점에 추출')

- 월드 서브시스템이고 서버에서만 만든다. 함수 둘:
  - `SpawnEnemy(클래스, 위치 · 회전)` → 폰. 안쪽은 `SpawnActor` + 컨트롤러가 없으면 `SpawnDefaultController`(§1-4 의 안전망).
  - `ReleaseEnemy(폰, 지연)` — 죽은 적을 치운다. 안쪽은 `SetLifeSpan(지연)`, 지연이 0 이하면 바로 `Destroy`.
- **풀링은 만들지 않는다.** 이 두 함수의 안쪽만 바꾸면 되도록 부르는 쪽을 여기로 모으는 것까지가 D 다.
- `AAstralCombatCharacter::HandleDeathFinished` 의 `SetLifeSpan(DestroyAfterDeathDelay)` 한 줄을 `ReleaseEnemy(this, DestroyAfterDeathDelay)` 로 바꾼다. 헤더가 이미 'M3 에서 스폰/디스폰 인터페이스로 교체 예정' 이라고 적어 둔 자리다(`AstralCombatCharacter.h:69`).
  - **베이스 변경이다 — 더미 · 마네킹 · 수호병이 전부 이 경로를 탄다.** 서브시스템의 안쪽이 같은 `SetLifeSpan` 이라 제거 시각은 그대로여야 하고(사망 5초 뒤), 기존 시험이 그 시각을 이미 재고 있다(A6 · G4 등).
  - §1-3 미해결의 `DestroyAfterDeathDelay = 0` 이면 영영 남는 문제는 여기서 닫힌다(0 이하 = 바로 제거).
- 사망 중인 폰을 다시 빙의하지 않는다(§1-3 · §1-8) — 서브시스템은 죽은 폰을 다시 내주지 않는다. 풀링을 넣을 때의 제약으로 주석에 남긴다.

**② 스포너 — `AAstralEnemySpawner`.**

- 맵에 놓는 액터. 프로퍼티: 적 클래스 · 스폰 지점들(스포너 기준 상대 위치 배열, 에디터에서 끌어 옮길 수 있게) · 발동 상자(크기 0 이면 없음) · `bActivateOnBeginPlay`.
- 발동은 **이벤트** 다 — 상자에 플레이어 폰이 겹칠 때(서버). 한 번만 발동한다. 수동 `Activate()` 도 있다(시험 · 나중의 구역 진행).
- 스폰은 ① 의 `SpawnEnemy` 로 한다. 스폰 지점은 NavMesh 에 내려 붙인다(못 내리면 그 지점은 건너뛰고 경고).
- 낸 적마다 `OnDeathStarted` 를 구독해 살아 있는 수를 센다. 0 이 되면 `OnCleared`(BlueprintAssignable)를 한 번 낸다. 접속 종료 · 파괴 같은 사망 아닌 제거도 센다(`OnDestroyed`).
- 스포너 자신은 복제하지 않는다. 낸 적은 지금처럼 복제된다.

**③ 적 PawnData 는 들이지 않는다.** (§1-5 가 6번으로 미룬 결정)

- §1-5 의 판단 그대로다: PawnData 를 들이면 부여 지점을 InitState 쪽으로 옮겨야 하고, 더미까지 PawnData 가 필요해지거나 경로가 갈린다.
- 지금 적은 한 종류이고 `BP_Enemy_Guardian` 이 메시 · ABP · AbilitySet · 컨트롤러를 이미 묶고 있다. 스포너는 클래스만 알면 된다.
- 보스(M5)가 적과 구조를 나눠 쓸 때 다시 본다. `AstralCombatCharacter.h:18` 의 주석은 그대로 맞다.

**④ 여러 마리.**

- **겹침:** `BP_Enemy_Guardian` 의 CharacterMovement 에서 `bUseRVOAvoidance` 를 켠다(값은 잠정). 같은 타깃에 몰릴 때 서로 밀어내며 둘러싼다. 실제로 그렇게 보이는지는 사용자 눈 확인이다.
- **몰림:** 피해 기록이 없으면 세 마리가 모두 가장 가까운 한 사람을 고른다(§9 미해결). **D 에서는 고치지 않는다** — 사용자가 어그로 조정을 뒤 단계로 미뤘다(2026-11-12, C2 세션).
- 적의 스윕은 다른 적을 때리지 않는다(`CanDamage` 가 적대만 통과).
- 수(3마리) · 지점 배치는 잠정이고 맵의 스포너 값이다.

**⑤ 맵 — `RaidMap` 에 스포너 1개.**

- M3 종료 조건('4인이 몬스터 여러 마리를 처치')이 실제 흐름(허브 → 레이드)에서 서려면 레이드 맵에 적이 있어야 한다. **맵 애셋을 고치는 첫 단위다.**
- 발동 상자는 시작 지점(PlayerStart)에서 떨어뜨린다 — 선행 단위의 파티 흐름 시험이 `RaidMap` 에 도착만 하고 움직이지 않으므로 그 시험에서는 발동하지 않는다.
- 위치는 단위 세션이 맵을 읽어 NavMesh 위로 정하고 결과에 좌표를 적는다. 배치는 `astral-ue-level` 헬퍼 · 스크립트로 한다(재현할 수 있게).
- `CombatTestMap` 은 건드리지 않는다(A ~ C 의 시험 맵).

**⑥ 디버그 명령.** `ServerSpawnEnemy` 가 `SpawnActor` 대신 ① 의 `SpawnEnemy` 를 부른다. 명령의 쓰임 · 인자는 그대로다.

### 대안과 기각 이유

| 대안 | 기각 이유 |
| :--- | :--- |
| 풀링까지 만든다 | 계획서가 'MVP 에선 풀링 없어도 된다' 고 했다. 재사용하려면 ASC · 트리 · 위협 기록 · 사망 상태를 되돌리는 경로가 필요하다 — 적이 몇 마리인 지금은 쓸 곳이 없다 |
| 이음매 없이 스포너가 `SpawnActor` 를 직접 | 사망 뒤 제거가 폰 안에 남아, 나중에 풀링을 넣을 때 폰 · 스포너 · 디버그 명령 세 곳을 고친다 |
| 인터페이스 클래스(`IAstralPoolable` 등)를 폰에 | 구현할 것이 아직 없다. 함수 두 개가 지나는 한 곳이면 충분하다 |
| 제거를 스포너가 맡는다 | 스포너 없이 나온 적(디버그 명령 · 레벨 배치 더미)은 다른 경로가 된다 |
| 베이스를 안 건드리고 `DestroyAfterDeathDelay = 0` 을 '스폰한 쪽이 치운다' 는 뜻으로 쓴다 | 지금의 결함(0 이면 영영 남음)에 기대는 약속이다. 더미는 치워 줄 쪽이 없다 |
| 적 PawnData 도입 | ③ |
| 게임 시작 때 전부 스폰 | 4인이 도착하기 전에 덤빈다. 구역 진입이 '협동 이동 구간 전투 압박'(game-plan 7-6)에 맞다 |
| 일정 시간마다 플레이어 거리를 재서 발동 | 폴링이다. 겹침 이벤트가 있다 |
| 웨이브 · 재스폰 | 종료 조건에 없다. `Activate()` 를 다시 부를 수 있게만 두지 않는다(한 번) — 필요해지면 그때 |
| DetourCrowd(`UCrowdFollowingComponent`) | 컨트롤러의 경로 추종 컴포넌트를 바꾸는 일이라 A 의 실측 전제(멈추는 거리 · 포커스)를 다시 봐야 한다. RVO 는 값 하나다 |
| `CombatTestMap` 에 스포너 | A ~ C 의 시험이 그 맵에서 히어로를 옮긴다 — 상자에 걸릴 수 있다 |

### 영향

| 대상 | 변경 | 상속 · 공용 영향 |
| :--- | :--- | :--- |
| `UAstralEnemySpawnSubsystem` · `AAstralEnemySpawner` (새 파일) | 추가 | 없음 |
| `AAstralCombatCharacter::HandleDeathFinished` | 한 줄 교체 | **더미 · 마네킹 · 수호병 공용.** 제거 시각 불변이어야 한다 — 기존 시험이 확인한다 |
| `AAstralCharacter::ServerSpawnEnemy` | 스폰 호출 한 곳 | 디버그 전용 |
| `BP_Enemy_Guardian` | RVO 값 | 수호병만 |
| `RaidMap` | 스포너 1개 | 파티 흐름 시험이 이 맵에 도착한다 — 발동하지 않아야 한다 |
| 컨트롤러 · 트리 · 어그로 · GA · 히어로 코드 · `CombatTestMap` · 마네킹 애셋 · 플러그인 | **변경 없음** | |
| 복제 | **새 프로퍼티 0** | |

### 미해결

- 세 마리가 한 사람에게 몰린다(④). 어그로 조정 단계에서 본다.
- 전원이 죽으면 적은 `Wait` 에서 기다린다. 전멸 · 부활 규칙은 계획서에 없다(부록 D).
- 구역을 벗어나 달아나면 끝까지 쫓아온다(인지 범위 · 복귀 없음 — §9).
- `OnCleared` 를 받는 쪽이 없다(M6).
- 늦게 들어온 플레이어는 이미 나와 있는 적을 본다(복제). 스포너가 이미 발동했는지는 클라이언트가 알 필요가 없다.

### 검증 계획 — 줄인 범위

**D-0 — 첫 시험 실행에서 함께 본다.** 틀리면 우회하지 말고 마스터에 묻는다.

| # | 확인할 것 |
| :--- | :--- |
| D-0a | 제거를 서브시스템으로 넘긴 뒤에도 더미 · 마네킹 · 수호병의 제거 시각이 그대로다(기존 시험의 5초) |
| D-0b | `RaidMap` 의 스포너가 파티 흐름 시험(도착만 하는 경우)에서 발동하지 않는다 |

| # | 확인할 것 | 방법 | 판정 |
| :--- | :--- | :--- | :--- |
| S1 | 스포너 발동 → 서버에 수호병 3 · 컨트롤러 3, 모든 클라이언트에 폰 3. 두 번 겹쳐도 한 번만 | 멀티 PIE `AstralBreak.Net.EnemySpawner.{ListenPIE, DedicatedPIE}` — `CombatTestMap` 에서 시험이 스포너를 직접 만들어 `Activate()` | 자동 |
| S2 | 상자에 플레이어 폰이 겹치면 발동한다 | 같은 시험(히어로를 상자 안으로 옮긴다) | 자동 |
| S3 | 셋을 다 죽이면 `OnCleared` 1회 · 그 전에는 0회 · 5초 뒤 폰이 모든 머신에서 사라짐 | 같은 시험 | 자동 |
| S4 | 세 마리가 각자 타깃을 잡고 공격한다(서로를 때리지 않는다) | 같은 시험 | 자동 |
| S5 | `RaidMap`: 시작 지점에서는 적 0, 상자로 들어가면 3 | `AstralBreak.Net.EnemySpawner.RaidMapPIE`(Dedicated 1개 구성만) | 자동 |
| S6 | 회귀 — `AstralBreak.` 전체 1회(파티 흐름 · 마네킹 · 수호병 · 히어로 시험 그대로) · 두 구성 빌드 각 1회 | 같은 에디터 실행 | 자동 |
| S7 | 눈 확인 — 레이드 흐름(허브 → `StartRaid` → 구역 진입)에서 세 마리가 나오는가 · 서로 겹치지 않고 둘러싸는가 · 2인 이상에서 싸울 만한가 | 사용자 | 사용자 |

- 하지 않는 것은 §9 의 표 그대로다(별도 프로세스 · `-DisableAdaptiveUnity` · 시나리오 도구 · 코드를 깨뜨리는 대조 · Development 실행 · 플러그인 회귀 — 단위 E).
