# 락온 5단계 — 타겟 서버 전달과 방향 보정 권위화

> 작업 세션 핸드오프 문서. 작성 2026-09-14 · 기준 브랜치 `feat/lockon_sync` (26b6e86 시점)
> 선행 문서: `root-motion-pawn-collision-policy.md` (4단계 충돌 정책 — 리플레이 문제의 원형)

---

## 1. 목표

**원격 클라이언트에서도 공격 방향 보정이 동작하게 한다.**

현재 방향 보정은 리슨 호스트(또는 Standalone)에서만 걸린다. 원격 클라는 자기 화면에서도,
다른 사람 화면에서도 회전하지 않는다.

### 완료 기준

| | 자율 프록시 (조작 중인 클라) | 서버 인스턴스 | 시뮬 프록시 (남의 화면) |
| :--- | :---: | :---: | :---: |
| 워프 설치 주체 | 자기 자신 (예측) | 자기 자신 (권위) | 복제 수신 |
| 락온 타겟 인지 | 로컬 선정 | **RPC 수신 (신규)** | 불필요 |
| 회전 관측 | ✅ | ✅ | ✅ |

- 리슨 서버 2인(호스트 + 원격 클라) PIE에서 **양쪽 다** 락온 후 근접 콤보 시 타겟을 향해 회전
- 원격 클라의 공격 중 위치 보정(뒤로 튐)이 눈에 띄지 않는다
- 4단계 게이트(`AstralGameplayAbility.cpp:72`)가 제거된다

---

## 2. 지금 왜 안 되는가

```cpp
// AstralGameplayAbility.cpp:71
// 4단계 게이트 — (Standalone, 리슨 호스트 캐릭터). 5단계에서 제거
const bool bWarpAuthorized = CurrentActorInfo->IsLocallyControlled() && CurrentActorInfo->IsNetAuthority();
```

`&&` 조건을 만족하는 건 **리슨 호스트가 조종하는 캐릭터뿐**이다.

게이트가 존재하는 이유는 **서버가 클라의 락온 타겟을 모르기 때문**이다.
`UAstralTargetingComponent`는 복제되지 않고(`AstralTargetingComponent.cpp:21`),
`TickComponent`가 비로컬 제어 폰에서 즉시 return하므로(`:57-61`)
원격 폰의 서버 인스턴스는 `Mode == Idle` · `HardLockTarget` 빈 채로 남는다.
따라서 `ResolveEffectiveTarget()`이 서버에서 항상 빈 핸들을 돌려주고,
게이트를 그냥 풀면 서버는 회전하지 않는데 클라만 회전해 **매 공격마다 위치 보정**이 난다.

→ **타겟을 서버로 옮기는 것이 5단계의 전부다.** 게이트 제거는 그 결과일 뿐이다.

---

## 3. 확정된 설계 결정

### 결정 1 — 서버가 받는 것은 **타겟 액터 참조** (facing 각도가 아니라)

서버는 받은 액터의 **자기 시점 위치**로 facing을 재계산한다.

**근거**
- 클라가 계산한 각도를 그대로 받으면 서버가 "이 각도가 정당한가"를 판단하려면 결국 타겟을 알아야 한다 — 각도만 받는 설계는 검증을 포기하거나 타겟을 중복 전송하게 된다
- M5 보스 약점 부위(`FAstralTargetHandle::TargetPointId`)로 확장할 때 각도로는 표현되지 않는다. 액터 참조는 그대로 부위 ID를 얹을 수 있다
- 위치 권위가 서버에 있으므로 임의 각도 주입이 불가능하다

**감수하는 것** — RTT/2 동안 타겟이 움직이면 클라·서버 facing이 미세하게 갈린다.
루트모션 전진이 회전에 종속되므로 위치 차이로 번지고, CMC 표준 보정이 흡수한다.
타겟이 빠르게 횡이동할 때만 체감되며, 이는 §7 검증 항목이다.

### 결정 2 — 전달 경로는 **타게팅 컴포넌트의 서버 RPC** (GAS TargetData가 아니라)

`CommitTargetingState`(이미 단일 쓰기 경로)에서 락 상태가 바뀔 때 1회 발신한다.

**근거**
- 콤보는 **스테이지마다 스냅샷을 다시 뜨는데**, TargetData는 활성화 단위이고 예측 키가 활성화당 하나라 슬롯이 하나뿐이다 — 스테이지별 재전송이 구조적으로 안 맞는다
- 락 변경 시에만 발신하므로 공격당 네트워크 비용이 0이다 (TargetData는 활성화마다 전송)
- `ResolveEffectiveTarget()`이 클라·서버에서 **동일하게** 동작하게 되므로, `MarkFinisher`·7단계·앞으로 추가될 GA가 배선 없이 혜택을 받는다
- 프로젝트의 "상태마다 쓰기 경로는 하나" 원칙과 일치 — 새 게이트를 만들지 않고 기존 게이트에 한 줄 얹는다

**감수하는 것** — 락 변경 RPC와 공격 진행의 순서 레이스 (§6-③).

> README §5의 "서버에 타겟을 넘길 필요가 생기면 GAS `TargetData` 경로로 보내 검증하면 됩니다"는
> 이 결정으로 갱신된다. README 수정은 5단계 완료 후 별도 커밋.

---

## 4. 검증된 엔진 제약

작업 전 반드시 인지할 것. 엔진 소스(5.7.4)에서 확인했다.

### ① 워프 타겟은 자율 프록시에 복제되지 않는다

```cpp
// MotionWarpingComponent.cpp:295
Params.Condition = COND_SimulatedOnly;
DOREPLIFETIME_WITH_PARAMS_FAST(UMotionWarpingComponent, WarpTargets, Params);
```

**시뮬 프록시는 서버 값을 받지만 조작 중인 클라는 못 받는다.**
따라서 클라는 반드시 자기 워프를 스스로 설치해야 하고(예측),
서버 값으로 덮어써지는 경로가 없으므로 **클라·서버가 각자 계산한 값으로 끝까지 간다.**
= 두 값이 다르면 조정되지 않고 위치 보정으로만 해소된다.

### ② MotionWarping은 클라 보정 리플레이 중에도 다시 돈다

```cpp
// CharacterMovementComponent.cpp:13052 — FSavedMove_Character::PrepMoveFor
RootMotionMontageInstance->SimulateAdvance(DeltaTime, RootMotionTrackPosition, RootMotionMovement);
```
```cpp
// CharacterMovementComponent.cpp:13303 — 리플레이된 move의 이동 적용
RootMotionParams.Set(ConvertLocalRootMotionToWorld(RootMotionParams.GetRootMotionTransform(), DeltaSeconds));
// → ProcessRootMotionPreConvertToWorld (CMC.cpp:2069) → MotionWarping 훅
```

`bClientResimulateRootMotion`이 서면 루트모션이 **재시뮬**되고, 그 값이 월드 변환을 타면서
MotionWarping 훅이 다시 호출된다. 이때 참조하는 워프 타겟은 **"지금" 컴포넌트에 남아 있는 것**이다
(`SimulateAdvance`는 노티파이를 재발화하지 않는다).

→ **워프 타겟이 리플레이 시점까지 살아 있어야 한다.**
폰 충돌 정책에서 `SavedMove`에 값을 기록해 해결한 것과 **같은 종류의 문제**다.

현재 코드는 이미 부분적으로 대비되어 있다:
- `PlayComboStage`는 이전 스테이지 워프를 지우지 않고 `EndAbility`에서 일괄 해제한다 (`AstralGA_Hero_BasicAttack_Melee.cpp:297, 498-507`)
- `ValidateComboStageMontages`가 스테이지별 워프 이름 중복을 Error로 잡는다 (`:185-206`) — 이름이 겹치면 다음 스테이지가 이전 타겟을 덮어써 이 대비가 무너지기 때문

**남은 구멍** — `EndAbility` 이후에 도착한 보정이 마지막 스테이지를 리플레이하면 워프 타겟이 이미 없다.
5단계에서 새로 생기는 문제는 아니지만(4단계에도 있었다), 원격 클라가 생기면서 **실제로 발생하기 시작한다.**
§6-④ 참조.

### ③ GA는 시뮬 프록시에서 실행되지 않는다

`LocalPredicted` GA는 소유 클라와 서버에서만 인스턴스화된다.
게이트를 `IsLocallyControlled() || IsNetAuthority()`로 바꾸든 아예 제거하든 결과는 같지만,
의도를 남기기 위해 명시적 조건을 유지할 것.

---

## 5. 구현 순서

각 단계가 독립 커밋이 되도록 배열했다.

### 단계 1 — 타게팅 컴포넌트를 RPC 라우팅 가능하게

`AstralTargetingComponent.cpp:21`

```cpp
// 상태는 여전히 로컬 전용 — 복제 프로퍼티 0개.
// 켜는 이유는 오직 서버 RPC 라우팅 (컴포넌트 RPC는 복제 등록된 컴포넌트만 전달된다)
SetIsReplicatedByDefault(true);
```

> **주의**: "복제 켜기 ≠ 상태 복제"다. `GetLifetimeReplicatedProps`는 추가하지 않는다.
> `HardLockTarget`·`Mode`는 각 머신이 자기 경로로 채운다.
> 소유 폰이 PlayerController 소유라 클라→서버 RPC 권한은 이미 성립한다.

### 단계 2 — 락 상태 서버 전달

`AstralTargetingComponent.h/.cpp`

```cpp
/**
 * 클라 → 서버. 락 타겟 전달 (nullptr = 해제).
 * Reliable — 상태 전이라 유실되면 서버가 영구히 어긋난다 (다음 락 변경까지 복구 불가)
 */
UFUNCTION(Server, Reliable)
void ServerSetLockTarget(AActor* NewTarget);
```

**발신** — `CommitTargetingState` 말미, 타겟이 바뀌었을 때만:

```cpp
// 단일 쓰기 경로가 서버 통지까지 함께 책임진다 (호출처가 잊을 수 없도록)
if (bTargetChanged && GetOwnerRole() == ROLE_AutonomousProxy)
{
    ServerSetLockTarget(NewTarget.TargetActor.Get());
}
```

> 리슨 호스트는 `ROLE_Authority`라 발신하지 않는다 — 이미 자기가 권위다.

**수신 (서버)** — 검증 후 동일한 단일 쓰기 경로로:

```cpp
void UAstralTargetingComponent::ServerSetLockTarget_Implementation(AActor* NewTarget)
{
    if (!NewTarget)
    {
        CommitTargetingState(EAstralTargetingMode::Idle, FAstralTargetHandle());
        return;
    }

    const APawn* Pawn = GetPawn<APawn>();
    if (!Pawn || !UAstralCombatStatics::CanDamage(Pawn, NewTarget))
    {
        return; // 거부 — 서버는 기존 상태 유지
    }

    FAstralTargetHandle Handle;
    Handle.TargetActor = NewTarget;
    if (FVector::Dist(Pawn->GetActorLocation(), Handle.GetAimLocation()) > Params.MaintainRange)
    {
        return;
    }

    CommitTargetingState(EAstralTargetingMode::HardLocked, Handle);
}
```

**검증 범위에 대한 결정** (근거를 남길 것):

| 검사 | 하는가 | 이유 |
| :--- | :---: | :--- |
| `CanDamage` (팀·사망) | ✅ | 아군/시체 락온 차단. 수신 1회뿐이라 비용 무시 가능 |
| 거리 ≤ `MaintainRange` | ✅ | 획득은 `AcquireRange`(1500)지만 서버 검증은 유지 반경(2000)으로 — 히스테리시스가 이미 클라·서버 위치차의 여유를 표현하고 있다 |
| LOS | ❌ | 서버·클라 위치차로 위양성이 나고, 벽 뒤 락온으로 얻는 이득이 **회전뿐**이다. 트레이스는 여전히 벽에 막히므로 실익이 없다 |
| 각도 (`MaxAcquireYaw`) | ❌ | 유지 조건에 각도 제한이 없다 (`CheckMaintainConditions` 참조) — 획득 전용 필터를 검증에 쓰면 등 뒤 타겟이 거부된다 |

> **중요**: 서버는 **워프 설치 시점에 재검증하지 않는다.** RPC 수신 시점 1회만 검증한다.
> 설치 시점에 `CanDamage`를 다시 보면, 사망 태그가 서버 먼저·클라 나중이라
> RTT/2 동안 서버만 워프를 건너뛰어 정합이 깨진다.
> `AstralCombatStatics::AreHostile`이 폰 충돌 정책을 위해 `CanDamage`에서 분리된 것과 같은 이유
> (`AstralCombatStatics.h:20-26`).

### 단계 3 — 카메라가 서버에서 깨어나지 않도록 차단

`UAstralHeroCameraComponent::HandleTargetingChanged`는 `OnTargetingChanged`를 **무조건** 구독한다
(`AstralHeroCameraComponent.cpp:33-36`). 단계 2가 서버에서 `CommitTargetingState`를 부르는 순간
**원격 폰의 서버 인스턴스에서 카메라 틱이 켜진다** — 서버가 남의 카메라 붐을 돌리게 된다.

```cpp
void UAstralHeroCameraComponent::HandleTargetingChanged()
{
    // 로컬 표현 — 서버 인스턴스의 락 상태(5단계 RPC)는 카메라를 깨우지 않는다
    const APawn* Pawn = GetPawn<APawn>();
    const bool bLocked = Pawn && Pawn->IsLocallyControlled() && IsTrackingTarget();
    SetComponentTickEnabled(bLocked);
    ...
}
```

> 이 단계를 빠뜨리면 증상이 서버 프레임 저하로만 나타나 원인 추적이 오래 걸린다. **단계 2와 같은 커밋으로 묶을 것.**

### 단계 4 — 워프 게이트 제거

`AstralGameplayAbility.cpp:71-76`

```cpp
// 자율 프록시는 예측으로, 서버 권위 인스턴스는 권위로 각자 설치한다.
// 시뮬 프록시는 설치하지 않는다 — 서버 값이 COND_SimulatedOnly로 복제되므로 (GA 자체가 안 돌지만 의도를 남긴다)
const bool bWarpAuthorized = CurrentActorInfo->IsLocallyControlled() || CurrentActorInfo->IsNetAuthority();
```

`AstralTargetingComponent.cpp:20`·`AstralHeroCameraComponent.cpp:18`의
"5단계의 TargetData" 주석도 실제 경로(컴포넌트 RPC)로 고쳐 둘 것.

### 단계 5 — 정리 (별도 커밋)

`AstralTargeting::ClampFacingYaw`는 26b6e86에서 프로덕션 호출부가 사라졌고
현재 참조는 `AstralTargetingStaticsTests.cpp:85`의 자기 테스트뿐이다.
그 테스트는 아직 `"락온 4단계 완료 기준 3"`을 근거로 폐기된 설계를 지키고 있다.

7단계(이동 입력 방향 소스)도 클램프하지 않을 것이므로 되살아날 자리가 없다.
→ **함수와 테스트를 함께 삭제.** 5단계 본체와 섞지 말 것.

---

## 6. 함정

### ① `ROLE_AutonomousProxy` 체크를 빼먹으면 리슨 호스트가 자기에게 RPC를 보낸다
호스트는 `ROLE_Authority`다. 조건 없이 발신하면 `CommitTargetingState` → RPC → `CommitTargetingState`로
같은 값이 한 번 더 흐른다. 무한 루프는 아니지만(`bTargetChanged`가 false라 조기 return) 의미 없는 경로다.

### ② 서버의 락은 스스로 풀리지 않는다
서버 인스턴스의 `TickComponent`는 비로컬 제어라 즉시 return하므로 `CheckMaintainConditions`가 돌지 않는다.
서버 락을 푸는 경로는 셋뿐이다:
- 클라의 `ClearLock` → RPC (정상 경로)
- `HandleOwnerDeathStarted` — `BeginPlay`에서 로컬 여부와 무관하게 바인딩되므로 서버에서도 동작 ✅
- `EndPlay` ✅

타겟이 서버에서 먼저 죽으면, 클라가 `MaintainInterval`(0.15초) 안에 감지해 `ClearLock` RPC를 보낼 때까지
서버는 시체를 향해 회전한다. **자가 치유되므로 방치한다** — 서버에서 능동적으로 풀면
§5-단계2의 "설치 시점 재검증 금지"와 같은 이유로 정합이 깨진다.

### ③ 콤보 도중 타겟 전환은 한 스테이지 어긋날 수 있다
스테이지 전환은 각 머신이 자기 몽타주로 독립 진행한다(RPC 아님).
`CycleTarget` RPC가 서버의 다음 스테이지 시작보다 늦게 도착하면 그 스테이지만 구 타겟으로 회전한다.

락온 변경과 공격 활성화는 같은 연결의 신뢰 채널이라 **순서가 보장**되므로
"락온 → 공격" 순서는 안전하다. 어긋나는 건 **공격 중 전환**뿐이고, 1스테이지에 국한되며
CMC 보정이 흡수한다. → **수용하고 문서화.** 막으려면 스테이지 시작을 서버 이벤트로 묶어야 하는데
콤보의 예측 구조 전체를 다시 설계해야 한다.

### ④ `EndAbility` 이후 도착한 보정은 워프 타겟을 못 찾는다
§4-② 참조. 마지막 스테이지 재생 중 보정이 걸리면 `ClearFacingWarps`가 이미 돌았을 수 있고,
리플레이된 루트모션은 회전 없이 계산되어 위치가 어긋난다.

4단계에도 있던 구멍이지만 원격 클라가 생기며 실제로 발생하기 시작한다.
**먼저 §7-C로 재현을 시도하고, 관측되지 않으면 손대지 말 것.**
관측된다면 해법은 폰 충돌 정책과 동일한 구조다 —
`FAstralSavedMove_Hero`에 그 move의 facing을 기록하고 `PrepMoveFor`에서 되돌리는 방식.
`SetReplayPawnCollisionPolicy`(`AstralCharacterMovementComponent.h:88`)가 그대로 참고 대상이다.

---

## 7. 검증 시나리오

PIE **Play As Listen Server · 2 players**. 서버·클라 창 양쪽에서 관측한다.
디버그 위젯의 `[LockOn]` 섹션(`AstralDebugWidget::BuildLockOnString`)이 관측 지점이다.

| | 시나리오 | 기대 |
| :---: | :--- | :--- |
| **A** | 원격 클라가 락온 후 제자리 더미에 콤보 3단 | 클라·호스트 두 화면 모두에서 회전. 위치 보정 없음 |
| **B** | 원격 클라가 락온 후 **타겟 뒤를 돌며** 콤보 | 각 스테이지가 타겟을 다시 향한다. 미끄러지며 공전하지 않는다 (충돌 정책 회귀 확인) |
| **C** | 원격 클라가 **마지막 스테이지 도중** 강제 지연 (`Net PktLag=150`) | §6-④ 재현 시도. 공격 종료 직후 뒤로 튀는지 |
| **D** | 원격 클라가 **콤보 도중** 타겟 전환 | §6-③ — 한 스테이지 구 타겟 회전 후 복귀. 영구 어긋남이 아닐 것 |
| **E** | 락온 중 타겟 사망 | 0.15초 내 양쪽 해제. 서버 락 잔존 없음 (위젯 확인) |
| **F** | 호스트 캐릭터로 A·B 반복 | 4단계 동작 회귀 없음 |
| **G** | 락온 없이 콤보 | 워프 미설치 — 회전 없음 (7단계 전까지 정상) |

`Net PktLag=150` / `Net PktLoss=5`는 콘솔에서 켠다.
자동화 테스트는 추가하지 않는다 — 월드·네트워크 의존이라 순수 함수 분리 대상이 아니다.

---

## 8. 범위 밖

| | |
| :--- | :--- |
| **7단계** | 락온이 없을 때 이동 입력 방향을 보정 소스로. `InstallStageFacingWarp`의 "타겟 없음 = 워프 없음" 분기가 그 자리 (`AstralGA_Hero_BasicAttack_Melee.cpp:318-323`) |
| **부위 조준** | `TargetPointId`는 계속 `NAME_None`. RPC 시그니처에 지금 넣지 말 것 — M5에서 핸들째 넘기도록 바꾸면 된다 |
| **원거리 GA** | `BasicAttack_Ranged`는 워프를 쓰지 않는다. 투사체 조준 보정은 별건 |
| **소프트 트래킹** | `EAstralTargetingMode::SoftTracking`은 계속 자리만 |
| **README 갱신** | §5의 TargetData 언급 수정 — 5단계 완료 후 별도 커밋 |

---

## 9. 예상 변경 파일

```
Source/AstralBreak/Character/Hero/Components/AstralTargetingComponent.h    RPC 선언
Source/AstralBreak/Character/Hero/Components/AstralTargetingComponent.cpp  복제 on · 발신 · 수신 검증
Source/AstralBreak/Character/Hero/Components/AstralHeroCameraComponent.cpp 로컬 게이트
Source/AstralBreak/AbilitySystem/Abilities/AstralGameplayAbility.cpp       워프 게이트 제거
Source/AstralBreak/Combat/AstralTargetingStatics.h/.cpp                    ClampFacingYaw 삭제 (별도 커밋)
Source/AstralBreak/Tests/AstralTargetingStaticsTests.cpp                   해당 테스트 삭제 (별도 커밋)
```

에디터 애셋 변경 없음. `Tools/` 스크립트 변경 없음.

### 커밋 분할

1. `Feat: 락온 타겟 서버 전달 및 방향 보정 권위화` — 단계 1~4
2. `Refactor: 사용처가 사라진 방향 클램프 제거` — 단계 5
