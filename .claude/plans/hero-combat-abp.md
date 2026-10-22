# 히어로 전투 AnimBP — 근접(낫) · 원거리(총) · 조준 strafe (설계 근거 · 2026-10-19)

> 브랜치 `feat/character_ABP` · 사용자 확정 4건(2026-10-19): **Lyra 식 Linked Anim Layer** · **새 애셋 `ABP_Hero_Combat`**(운영 `ABP_Hero_Base` 는 보존) · **런타임 C++ 포함**(AnimInstance 변수 · 조준 유지 GE · 회전 모드) · **스켈레톤 통합은 새 Tool `reassign_skeleton`**.
> 생성은 전부 도구(`Tools/mcp/build_hero_combat.py`, Tool 30개), 런타임 배선은 `Tools/scripts/setup/hero_abp_wire_data.py`. 관련: [animbp-automation-handoff-phase6-2.md](animbp-automation-handoff-phase6-2.md) · [animbp-automation-phase1.md](animbp-automation-phase1.md) "Phase 7-6 결과".

## 1. 요구

총을 **일정 시간 안에 계속 쏘는 동안**: 서 있으면 조준 Idle + AimOffset, 움직이면 8방향 strafe + AimOffset. 그 밖(근접 낫 · 쏘지 않는 총): 이동 방향을 향하는 보통 로코모션, AimOffset 없음. 유지보수(무기 추가)·최적화(스레드 안전) 우선.

## 2. 선행 제약과 해결

| 제약 (실측) | 해결 |
| :--- | :--- |
| 히어로 애니 애셋이 같은 본 이름의 **두 스켈레톤**(`/Game/Assets/IdaFaber/…/SKEL_UE5_F` = 메시·ABP, `/Game/IdaFaber/…/SKEL_UE5_F` = AO_Rifle·Rifle_Jog·M_Neutral·Jump_*·Attack1~3·몽타주 40개)으로 갈라져 ABP 가 B 애셋을 참조할 수 없었다 | Tool `reassign_skeleton`(엔진 `EditorAnimUtils::RetargetAnimations` 제자리) — `Tools/mcp/reassign_hero_skeleton.py --apply` 로 40개 → A. `/Game` 전체에 B 애셋 0. `/Game/IdaFaber/` 폴더(머티리얼·텍스처·메시 중복 79파일)는 남아 있다 — 삭제는 사용자 판단 |
| `AS_Hero_AO_RifleCC` 만 additive 기준 포즈가 없어 AimOffset 샘플 거부(`ADDITIVE_INVALID`) | Tool `set_sequence_additive` — `AS_Hero_Rifle_Idle` 프레임 0 기준 |
| 런타임에 "사격 중" 신호·조준 각·회전 모드가 없었다(`bOrientRotationToMovement=true` 고정 → strafe 자세 불가, 2026-10-10 보류 S-A/B/C) | C++ 4건 (§4) |

## 3. ABP 구조

```text
ALI_HeroCombat (인터페이스)         Locomotion_Idle · Locomotion_Move (입력 없음) · Aim_UpperBody (입력 포즈 InPose) — 그룹 DefaultSharedGroup(공급자 인스턴스 1개 공유)

ABP_Hero_Combat (베이스, 부모 UAstralAnimInstance, DA_CD_Vesper.AnimInstanceClass)
  루트:  Locomotions SM → Slot DefaultSlot → SaveCachedPose FullBody → ┬ UseCachedPose → BasePose      ┐
                                                                       └ UseCachedPose → Slot UpperBody → BlendPoses_0 ┘ LayeredBoneBlend(spine_01, 메시 공간 회전)
         → LinkedAnimLayer Aim_UpperBody(InPose) → Inertialization → Output        (운영 ABP_Hero_Base 와 같은 뼈대 + 조준 레이어 한 단)
  SM:    운영과 1:1 — 상태 5 · conduit 2 · alias 4 · 전이 12 · Entry Idle. Idle/Move 상태 내부 = LinkedAnimLayer(Locomotion_Idle / Locomotion_Move). 점프 3상태는 시퀀스 그대로
  기본 구현(= 근접 낫 세트): Idle AS_Idle · Move BS_Hero_Locomotion1D(X←Speed) · Aim 통과

ABP_HeroLayers_Rifle (공급자, DA_EF_Rifle.AnimLayerClass — 장비 매니저가 Ranged 스타일 활성 시 LinkAnimClassLayers)
  Locomotion_Idle:  BlendListByBool(bActiveValue←bIsAiming)  false: AS_Hero_Rifle_Idle · true: 상태머신 IdleTurn(Idle = AS_IdleRifleAiming_02 = AO 기준 포즈 — §7 10-20 교정; 10-19 의 Rifle_Idle 교체는 AO 기준이 잘못 잡힌 탓)
  Locomotion_Move:  BlendListByBool(bIsAiming)  false: BS_Hero_Rifle_Jog(1D Speed: Idle→JogFwd) · true: BS_Hero_Rifle_Strafe(2D Direction×Speed: Idle 5 + Jog 8방향 9)
  Aim_UpperBody:    InPose → AimOffset AO_Hero_Rifle(2D Yaw×Pitch 9샘플; X←AimYaw · Y←AimPitch · Alpha(bool)←bIsAiming, 0.15초 블렌드) → Output
```

- 변수는 전부 `UAstralAnimInstance` 네이티브(스레드 안전 스냅샷) → 핀 **Property Binding**(`bind_pin`)으로 읽는다. EventGraph 없음.
- 근접 공급자 ABP 는 따로 만들지 않았다 — 베이스 기본 구현이 곧 근접 세트이고 `LinkAnimClassLayers(null)` 이 기본으로 복귀한다. 세 번째 무기부터는 공급자 ABP + `Family.AnimLayerClass` 지정만.
- 조준 레이어를 LayeredBoneBlend **뒤**에 둔 이유: 전신 몽타주·상체 슬롯 결과 위에 AimOffset 이 얹혀야 사격 몽타주 중에도 조준 각이 유지된다.

## 4. 런타임 (C++, 2026-10-19)

| 파일 | 변경 |
| :--- | :--- |
| `AstralAnimInstance.{h,cpp}` | `bIsAiming`(ASC 태그 `State.Ranged.Aiming`, 게임 스레드 스냅샷) · `AimYaw`/`AimPitch`(`GetBaseAimRotation − ActorRotation`, 정규화). `BoundASC` 약참조는 `InitializeWithAbilitySystem` 에서. **스타일 플래그는 두지 않는다**(`bIsRangedStyle` 은 2026-10-20 제거 — 어떤 그래프도 읽지 않았고, 무기별 분기는 장비 계열의 `AnimLayerClass` 링크가 담당. 근접 전용 영웅은 조준 변수가 false 로 머물 뿐). 조준 변수를 공급자 전용 파생 클래스(`UAstralRangedLayersAnimInstance`)로 옮기는 것은 선택 과제 |
| `AstralGE_RangedAimHold.{h,cpp}` (신규) | 네이티브 GE — HasDuration(`SetByCaller.Duration`) · 스택 1 · 재적용 시 지속 시간 갱신 · `State.Ranged.Aiming` 부여(생성자에서 `UTargetTagsGameplayEffectComponent` 기본 서브오브젝트 + `SetAndApplyTargetTagChanges`; 네이티브 GE 는 PostLoad 를 거치지 않는다) |
| `AstralGA_Hero_BasicAttack_Ranged.{h,cpp}` | `AimHoldEffect`(기본 위 GE) · `AimHoldSeconds=2` · `ApplyAimHold` — 활성화(커밋 직후, 서버)마다 적용 → "계속 쏘는 동안" 창 |
| `AstralHeroMovementComponent.{h,cpp}` | `State.Ranged.Aiming` 구독 → `ApplyAimingRotationMode`: 조준 중 `bOrientRotationToMovement=false` + `bUseControllerRotationYaw=true`, 아니면 원복 (S-A). 결합 시 현재 값 적용, 해제 시 원복 |
| `AstralEquipmentFamily.h` | `AnimLayerClass` (TSubclassOf<UAnimInstance>) |
| `AstralEquipmentManagerComponent.{h,cpp}` | `RefreshAnimLayers()` — 활성 계열의 공급자를 `LinkAnimClassLayers`, 없으면 기본으로. 트리거: 스타일 태그 변경 · 서버 Equip/Unequip · 클라 `FAstralEquipmentList::PostReplicatedReceive` · ASC 결합 · 외형 교체. `LinkedAnimLayerClass` 캐시로 no-op, AnimInstance 교체로 링크가 사라졌으면 다시 건다 |
| `AstralLoadoutComponent.cpp` | 메시와 AnimBP 를 **따로** 비교해 적용(`GetAnimClass() != AnimInstanceClass` 면 `SetAnimInstanceClass`), 바뀌면 `RefreshAnimLayers`. 첫 PIE 실측(2026-10-19): 원래 코드는 메시가 다를 때만 AnimBP 를 적용해 `BP_Hero_Vesper` 메시의 기본 AnimClass(`ABP_Hero_Base`)가 그대로 돌았고, 레이어 노드가 없으니 `LinkAnimClassLayers` 가 무효였다 — 사용자가 "Link 는 실행되는데 기본 이동" 으로 보고 |
| 태그 | `State.Ranged.Aiming` · `SetByCaller.Duration` |

네트워크: 태그는 PlayerState ASC(Mixed) 복제 → 소유 클라·관찰자 모두 같은 `bIsAiming`. 회전 플래그는 서버·소유 클라가 같은 태그로 계산하고 시뮬 프록시는 이동 복제로 회전을 받는다. 공급자 링크는 머신마다 자기 메시 기준(복제 없음).

## 5. 검증 상태

- 도구: `build_hero_combat.py` PASS — AO 9샘플 · strafe 14샘플 · jog 2샘플 · ALI 3 레이어 · 베이스/공급자 컴파일 0 에러 0 경고 · 스모크 3 passed(공급자 루트 미연결은 경고) · 상태머신 운영과 1:1(상태 11 · 전이 12) · PIE 에서 `Locomotions=Idle` 진입(공급자 미링크).
- `phase7_6_test.py` PASS (reassign_skeleton · set_sequence_additive). Development · DebugGame 빌드 경고 0.
- 첫 PIE(2026-10-19): 총 전환 뒤에도 기본 이동 → 위 LoadoutComponent 수정으로도 그대로. 두 번째 원인: `RefreshAppearanceFromLoadout` 은 PlayerState 로드아웃의 `CharacterId` 가 있을 때만(로비 경유) CD 를 적용하므로, 로비 없는 `CombatTestMap` 에서는 **`BP_Hero_Vesper` 메시 컴포넌트의 기본 AnimClass** 가 실제로 쓰인다 — 그 값이 `ABP_Hero_Base` 였다. `hero_abp_wire_data.py` 가 이제 BP 메시 AnimClass 도 `ABP_Hero_Combat_C` 로 바꾼다(적용·저장 완료, REVERT 로 복귀). 진단 스크립트 `Tools/scripts/probe_hero_animclass.py`(BP 메시 AnimClass vs CD). 교훈: 외형의 단일 원본은 CD 가 아니라 "CD(로비) ∨ BP 기본값(단독 맵)" 둘이다 — 둘 다 바꿔야 한다.
- 두 번째 PIE(2026-10-19): 라이플 모션은 나오나 "전투 상태에서 strafe 없음" 보고 → `Tools/scripts/pie_aim_probe.py`(ue_exec, STEP = begin/arm/sample/end — 전환 GA·원거리 공격 GA 를 클래스로 활성화해 실제 경로를 탄다)로 PIE 실측: 발사 직후 `State.Ranged.Aiming` 부여 · 회전 모드 전환(orient=false, ctrl_yaw=true) · +1.5초에 베이스와 링크된 `ABP_HeroLayers_Rifle` 인스턴스 둘 다 `bIsAiming=true` · +3초에 태그 만료·복귀. **파이프라인은 정상** — 조준 창이 `AimHoldSeconds=2` 초라 "한 발 쏘고 이동" 하면 이미 닫혀 전진 Jog 가 나온다. strafe 는 발사 후 2초 안(연사 중)에 이동할 때만. 조정은 GA BP(`GA_Hero_BasicAttack_Projectile`)의 `AimHoldSeconds`. 확인은 콘솔 `showdebug abilitysystem` 의 Owned Tags.
- 세 번째(2026-10-19, 사용자가 그래프 스크린샷으로 지적): 공급자의 `Blend Poses by bool` 이 **거꾸로** 꽂혀 있었다 — 엔진은 `BlendPose_0` 이 **True** Pose(`AnimGraphNode_BlendListByBool.cpp:37` "intentionally flipped, true as the topmost"). 그래서 조준 중엔 전진 Jog, 평소엔 strafe(몸이 이동 방향을 향하니 Direction≈0 → 전진 샘플) = 언제나 전진. Idle·Move 두 레이어의 연결을 뒤집어 적용·컴파일·저장(revision `ae905ec4…`), `build_hero_combat.py` 도 수정. 도구가 핀 의미를 알려 주지 않아 생긴 실수 — 조회 응답에 BlendListByBool 핀 표시 이름(True/False Pose)을 싣는 것이 후속 후보.
- 네 번째(2026-10-19): strafe 정상. 조준 Idle 이 비틀림 — `AS_IdleRifleAiming_02` 위에 AimOffset(기준 포즈 = `AS_Hero_Rifle_Idle` 프레임 0)을 얹은 조합 때문(수정 전엔 Blend 가 거꾸로라 이 조합이 안 나왔다). 사용자 확정: **조준 Idle 도 `AS_Hero_Rifle_Idle` + AimOffset**(True Pose 애셋 교체, revision `1409aabf…`, 컴파일 0 에러·저장). 교훈: AimOffset 은 기준 포즈 클립 위에서만 쓴다.
- **사용자 PIE 확인 완료(2026-10-19)**: 낫 로코모션 · 총 전환 · 발사 중 strafe · 조준 Idle(Rifle_Idle + AimOffset) 정상. 미확인: 멀티플레이(리슨 2클라) 관찰자 자세 · 창(2초)이 닫힌 뒤 복귀 연출의 느낌.
- (확인 항목 원안) 낫 로코모션이 운영과 같은가 · 총 전환 시 라이플 Idle/Jog · 발사 뒤 2초 동안 조준 Idle/strafe + AimOffset(Pitch 반응) · 창이 닫히면 복귀 · 멀티플레이(리슨 2클라)에서 관찰자도 같은 자세. 수치 튜닝(AimHoldSeconds · 블렌드 0.15/0.2 · strafe Speed 축 500)은 데이터.
- 되돌리기: `hero_abp_wire_data.py` 의 `REVERT = True` 로 실행하면 `ABP_Hero_Base` 로 복귀(`AnimLayerClass` 비움).

## 6. 남은 것 / 범위 밖

- 사격 몽타주(`FireMontage`)·`AS_RifleRecoil_01`(additive) 연결 — 현재 원거리 GA 는 몽타주 미지정(즉발)일 수 있음. 반동은 UpperBody 슬롯 몽타주나 ApplyAdditive 로 후속.
- 조준 중 점프 상태는 무기 무관 시퀀스 그대로(라이플 점프 없음).
- `/Game/IdaFaber/` 중복 폴더 정리(사용자 판단) · 운영 몽타주 UpperBody 슬롯·콤보 섹션(기존 후보 그대로).
- Python 원격 실행(`ue_exec`)은 에디터 기동 직후 UDP 멀티캐스트 발견이 간헐적으로 실패했다(5초 → 30초로 늘려도 0건이던 때가 있음, 재기동 뒤 성공). 실패 시 재기동하거나 `Tools/mcp` 도구를 쓴다.

## 7. 제자리 회전 — TurnInPlace (2026-10-20, 사용자 요구: Lyra 식 Yaw AimOffset + RotateRootBone + 턴 클립, 조준 중에만)

**선택(사용자 "너 생각에?" → 내 추천 → "이대로 진행")**: 전용 부모 클래스도 합성 컴포넌트도 아닌 **베이스 `UAstralAnimInstance` 안의 순수 계산 구조체 + Property Access 접근자**.
`FAstralTurnInPlaceState::Update(Settings, Input)` 는 월드·UObject 를 모르는 순수 함수(단위 테스트 4개), 정책(언제 누적하나)은 AnimInstance 가 입력으로 넘긴다.
계산은 **메인 인스턴스 하나만** 하고, 링크된 공급자 ABP 는 `GetMainAnimInstance.*`(BlueprintThreadSafe BlueprintPure, 메인이면 this) 경로로 읽기만 한다 — Lyra 의 `GetMainAnimBPThreadSafe` 역할.

| 층 | 내용 |
| :--- | :--- |
| C++ 계산 | `Animation/AstralTurnInPlace.{h,cpp}` — `EAstralTurnInPlaceKind{None, Left90, Left180, Right90, Right180}` · `FAstralTurnInPlaceSettings`(클램프 120 · 턴 임계 50 · 180 임계 135 · 스프링 80/1.0 · 활성 임계 0.001 · 종료 허용 1°) · `FAstralTurnInPlaceInput` · `FAstralTurnInPlaceState`(순서: ① 커브 처리 — `RemainingTurnYaw / TurnYawWeight` 가중 해제, 첫 활성 프레임 델타 건너뜀, `RootYawOffset -= Δ`, `bRotationFinished = \|남은 각\| ≤ 1` ② 누적이면 `RootYawOffset -= 액터 Yaw 델타`, 아니면 `FloatSpringInterp` 로 0 ③ 클램프 ④ `bWantsTurn = 누적 ∧ \|오프셋\| > 50`, 클립 종류는 상승 에지에서 래치) |
| C++ 정책 | `UAstralAnimInstance` — 스냅샷에 `YawDeltaSinceLastUpdate`·`bFullBodyMontagePlaying`(`GetSlotMontageGlobalWeight(FullBodyMontageSlot="DefaultSlot")`; 상체 슬롯 사격 몽타주는 누적을 막지 않는다) · 누적 조건 = `bAiming ∧ 지상 ∧ Speed < 10 ∧ 이동 입력 없음 ∧ 전신 몽타주 없음` · 출력 `RootYawOffset · bWantsTurnInPlace · bTurnInPlaceRotationFinished · TurnInPlaceKind · TurnInPlaceAnimTime`(+디버그 `TurnYawCurveValue · TurnInPlaceDebugWeight/Remaining · bTurnInPlaceAccumulating`) · `AimYaw = (조준 − 몸).Yaw − RootYawOffset`(루트를 돌려 둔 만큼 상체가 되돌아 조준) · `GetMainAnimInstance()` |
| 테스트 | `Tests/AstralTurnInPlaceTests.cpp` — `AstralBreak.TurnInPlace.{Accumulate, BlendOut, Curve, Kind}` 4/4 (run_automation_tests 로 에디터 안에서) |
| 애셋 | `Content/MF_Rifle_Turn{Left,Right}_{90,180}`(루트, 스켈레톤 B) → `reassign_skeleton` 으로 A → `Tools/scripts/setup/hero_abp_move_turn_assets.py`(ue_exec) 로 `/Game/Animation/Hero/Anims/TurnInPlace/`. 커브 이름은 소문자 `turnyawweight`·`remainingturnyaw`(FName 비교는 대소문자 무시 — C++ `GetCurveValue("TurnYawWeight")` 그대로 읽힌다) |
| 그래프 | `Tools/mcp/build_hero_turninplace.py`(제자리 패치·멱등·`--verify-only`; `build_hero_combat.main` 이 끝에 호출) — 베이스 루트 `LayeredBoneBlend → Aim_UpperBody → RotateRootBone(Yaw ← RootYawOffset) → Inertialization`(2026-10-21 순서 교정 — 아래 "AO 순서") · 공급자 `Locomotion_Idle` 조준(true=BlendPose_0) 가지에 상태머신 **IdleTurn**: `Idle(Rifle_Idle)` ─bWantsTurnInPlace→ `TurnInPlaceRotation`(BlendListByEnum(EAstralTurnInPlaceKind ← GetMainAnimInstance.TurnInPlaceKind) · 기본 Rifle_Idle + 턴 클립 4, 루프 없음, bAlwaysResetOnEntry) ─bTurnInPlaceRotationFinished→ `TurnInPlaceRecovery`(같은 구성 + 클립 StartPosition ← GetMainAnimInstance.TurnInPlaceAnimTime) ─자동(클립 끝)→ Idle, Recovery ─bWantsTurnInPlace→ Rotation. **전이 4개 전부 LogicType = Inertialization** |
| 플러그인 | `Core/AnimMcpPropertyRules.cpp` 전이 허용 목록에 `LogicType`(TEnumAsByte 는 기존 setter 가 이름으로 받는다). 조회 응답에는 아직 logic_type 이 없다(후속) |

**왜 관성 블렌드인가**: 표준 크로스페이드는 클립↔클립(Recovery → Rotation 재진입) 블렌드 중 두 클립의 커브가 가중 합산되어 `Remaining/Weight` 가 "남은 각이 커지는" 가짜 델타를 만들고 RootYawOffset 을 반대로 민다. 관성 블렌드는 새 상태 가중치가 즉시 1 이라 첫 프레임 건너뛰기만으로 충분(Lyra 도 inertial). 요청은 링크된 레이어 → 메인 그래프의 Inertialization 노드로 전파된다(PIE 실측: 전이 직후 첫 프레임부터 w=1.00).
**활성 임계는 사실상 0**(처음 0.5 로 뒀다가 내림): 가중 해제가 블렌드 인 첫 프레임부터 온전한 각을 주므로 임계를 올리면 그만큼 보정 없는 회전이 새어 발이 미끄러진다.

**PIE 실측(`Tools/scripts/pie_turn_probe_run.py`, 2026-10-20, 틱 ≈150Hz)** — 조준 중 컨트롤러·액터 Yaw +90:
`t=1.31 off=-90 kind=Right90 wants=1 w=1.00 rem=90.0 animT=0.03` → `1.56 off=-55` → `1.76 off=-9.1` → `1.87 off=-0.3 fin=1 animT=0.59` → `1.92 off=+0.8 w=0 rem=0`(Recovery — 클립 커브가 회전 구간 뒤 0 이라 정상) … 그대로 유지. 즉 **회전 요청 → 클립 선택 → 커브로 오프셋 0 수렴 → Recovery 전이 모두 설계대로**, 방향 부호도 맞음(오른쪽 회전 → 오프셋 음수 → Right 클립 → 오프셋 증가). 턴 클립 커브 실측: `TurnYawWeight` 는 처음 ~0.6초만 1, 그 뒤 0 · `RemainingTurnYaw` 는 Right 양수(90→0) · Left 음수(−180→0) — C++ 은 `-=(cur−prev)` 와 `|·|` 로 양쪽 다 맞는다.
**프로브 함정(실측)**: ① 파이썬 PIE 에선 `PlayerTick`→`UpdateRotation`(FaceRotation) 이 액터를 안 돌린다(컨트롤러 −90, 액터 −180 유지) → 프로브는 액터 Yaw 도 직접 돌린다(제자리 회전 입력은 액터 Yaw 델타라 같은 자극) ② AimHold 2초라 arm→turn 사이가 길면 조준이 풀려 누적이 꺼진다 → arm→record→fire→turn 즉시, 기록 중 0.6초마다 fire ③ 백그라운드 에디터는 8Hz(CPU 절약) → `EditorPerformanceSettings` CDO(파이썬 래퍼 없음, `find_object` 경로 + `set_editor_property("bThrottleCPUWhenNotForeground", False)`) ④ slate post-tick 샘플은 병렬 애님 작업 중 찢긴 값(off=−90 인데 aimYaw=0) → **pre-tick** 콜백 ⑤ **`anim.call_method("GetCurrentStateName", args=(0,))` 를 부른 실행 3번 모두 에디터 크래시**(로그는 `Saved/` 권한으로 못 읽음) → 상태 이름은 읽지 않는다 ⑥ `get_anim_graph_structure` 의 핀 바인딩은 `pins[]` 가 아니라 `optional_pins[].bound/binding{path,…}` 에 실린다.

**검증 상태**: `build_hero_turninplace.py --verify-only` PASS(구조 7 · 스모크 2 · 단위 4/4 · PIE Idle 진입) · 두 구성 빌드 경고 0 · 위 프로브. **미확인(사용자 PIE)**: 발이 실제로 붙어 보이는가(RotateRootBone 방향이 눈에 맞는가 — 반대면 RotateRootBone.Yaw 에 −RootYawOffset 를 바인딩하거나 Kind 부호를 뒤집는다) · Recovery 꼬리(정착) → Idle 자동 전이 시점 · 180° 클립 · 멀티플레이 관찰자. 튜닝은 ABP 클래스 기본값 `TurnInPlaceSettings`·`TurnInPlaceAccumulateMaxSpeed`·`FullBodyMontageSlot`.
**사용자 1차 PIE(2026-10-20 저녁) 보고 → 수정 3건 (같은 날)**: ① 상체가 접힌 포즈(스크린샷) ② 연속 회전 때 "휙" 끊김 ③ 가끔 메시가 180° 뒤집힌 채 이어짐.
- 실측: 턴 클립은 `EnableRootMotion`+`ForceRootLock`(루트 고정, 골반이 돈다)으로 Lyra 그대로라 루트는 무관. 원인은 세 가지 —
  (a) **커브 재진입 버그**: Recovery → Rotation 즉시 재진입(연속 회전)에서 이전 커브값이 꼬리값(0.3)이라 Lyra 의 "이전 0 이면 건너뜀" 이 안 걸려 새 클립 첫 값(90·−180)과의 차이를 통째로 오프셋에 넣었다 = 180° 휙. → `NewClipTolerance`: 남은 각의 크기가 커지거나 부호가 바뀌면 새 클립으로 보고 그 프레임 델타를 버린다(클립 안에서 남은 각은 단조 감소).
  (b) **±180 정규화 뒤집힘**: 누적 합을 NormalizeAxis 하면 클램프 120 에서 더 돌 때 120 → −120(240° 점프). → 델타만 정규화, 합은 클램프(<180)로만 자른다. 클램프 120 → **150**(180 임계 135 보다 커야 180 클립이 나온다 — 전엔 영영 90 클립). **10-22 다시 120** — 150 이면 빠른 플릭에서 |AimYaw| 가 AO 90 + 보정 30 을 넘어 총열이 25° 어긋남(아래 총구 정렬 "후속 ②"). 정규화 수정은 그대로라 뒤집힘은 재발하지 않는다.
  (c) **포즈**: 턴 클립(Lyra 라이플 자세)의 상체가 AimOffset 기준 포즈 `Rifle_Idle` 과 척추 Yaw 40° 쯤 달라 그 위에 AO ±90 을 얹으면 접힌다. → Rotation/Recovery 상태 그래프에 `LayeredBoneBlend(spine_01, 메시 공간, CurveBlendOption=UseBasePose)`: 하체·골반은 턴 클립, 상체는 `Rifle_Idle`. 커브는 베이스(턴 클립)에서. 상태 안 보조 Idle 플레이어는 `bIgnoreForRelevancyTest`(플러그인 허용 목록 추가)로 자동 전이의 관련 플레이어 선정에서 제외.
- 재검증: `build_hero_turninplace.py` PASS(상체 블렌드 2 · 플레이어 14 · 단위 4/4 — Kind 는 요청이 켜진 순간 고정이라 클램프까지 더 돌아도 안 바뀜·한 프레임 160 이면 Right180) · `pie_turn_probe_run.py 90 4.0 2 0.25`(**에디터는 `-unattended` 로 띄워야 백그라운드 스로틀이 꺼진다** — EditorEngine.cpp:5014 `ShouldThrottleCPUUsage` 가 `FApp::IsUnattended()` 면 false; CDO 설정 변경은 실제로 안 먹혔다): 80Hz 에서 0.25초 간격 3회 회전, **액터가 안 돈 프레임 사이 오프셋 최대 변화 6°**(수정 전엔 83.5), 세 번 다 −90 → 0 수렴·fin·Recovery. 재진입 때 커브는 Inertialization 노드가 0 → 1 로 0.2초 블렌드하지만 Remaining 도 같은 비율로 블렌드되어 가중 해제 값(비율)은 정확하다.
- 남은 잔여 오프셋 +0.5~0.8°(관성 블렌드된 커브 꼬리의 음수값) — 무시 가능.
**사용자 2차 PIE 보고(2026-10-20 밤) → 진짜 원인 = AimOffset 기준 포즈**: "턴 중 가끔 부자연스러운 팔 + 연속 회전이 매끄럽지 않음"(스크린샷: 총을 왼손에 낮게 들고 오른손이 떨어짐).
- 실측(프로브에 두 손 거리 지표 `hands` 추가, 마우스식 점진 회전 `spin`): 두 손 거리가 **턴 클립이 시작되기 전부터 AimYaw 에 비례해** 줄었다(0→23cm · 42→15 · 75→6; 왼쪽 회전은 33 으로 벌어짐). 즉 턴이 아니라 AimOffset 이 Yaw 가 커질수록 팔을 무너뜨리는데, 평소엔 몸이 카메라를 따라 Yaw 가 작아 안 보였고 턴 중엔 AimYaw = −RootYawOffset 이 ±80 까지 가서 드러난 것.
- 원인: AO 9샘플은 `AS_IdleRifleAiming_02` 프레임 0 을 기준으로 저작된 포즈다(CC 샘플과 그 클립의 상체 본 회전차 0.0°, 위치 동일) — 그런데 additive 기준이 총 내린 `AS_Hero_Rifle_Idle` 로 잡혀 있어 델타가 "총 들기 + 회전" 으로 거대해지고 샘플 사이(Yaw 30~85)의 보간이 무너진다(양 끝 샘플 자체는 손 거리 19~33 으로 멀쩡). 10-19 의 "AimingIdle + AO 비틀림 → Rifle_Idle 로 교체" 는 잘못된 기준 위에서 내린 결정이었다 — **교훈: AO 의 기준 포즈는 샘플이 저작된 클립이어야 하고, 조준 중 상체도 그 클립이어야 CC 가 항등이 된다.**
- 수정(`build_hero_turninplace.py` A0, 멱등): ① 9샘플 `set_sequence_additive ref_pose_sequence = AS_IdleRifleAiming_02 프레임 0`(저장) ② 조준 가지의 Idle 클립 5개(IdleTurn Idle · Rotation/Recovery 기본·상체) → AimingIdle ③ Move 조준 가지(strafe)에도 상체 LayeredBoneBlend(spine_01·메시 공간·UseBasePose, AimingIdle) — Jog 클립은 총 내린 자세(손 z≈105/95)라 재기준한 AO 를 그대로 얹으면 총이 안 올라간다. 비조준 가지(Rifle_Idle · Jog)·strafe BS 샘플은 그대로. `build_hero_combat.py` 도 새로 만들 때 같은 기준.
- 재검증: PASS(조준 가지 플레이어 5 = AimingIdle · Move 상체 LBB 1) · 점진 회전 4회 프로브 **두 손 거리 23cm 유지(최대 27)**, 오프셋 점프 2.1°, 링크 인스턴스 불변. AO 단독 프로브 `Tools/scripts/pie_ao_probe_run.py`(컨트롤러만 돌림) — `-unattended` 에디터에선 FaceRotation 이 액터를 돌려 결과적으로 턴 프로브가 됐다(기록용).
- 연속 회전 "매끄럽지 않음" 은 같은 원인(팔 붕괴가 회전마다 반복) + Recovery→Rotation 재진입의 클립 재시작(관성 0.2초) — 후자는 Lyra 와 같다. 더 부드럽게 하려면 재진입 전이의 CrossfadeDuration(관성 시간)을 0.3~0.4 로.
**AO 순서 교정 (2026-10-21, 사용자 PIE 스크린샷 "회전 중 가끔 목·상체 꺾임 · 왼손이 총열에서 떨어짐" → 사용자 A안 승인)**:
- 원인: 베이스 루트가 `RotateRootBone → Aim_UpperBody` 순서였다. AimOffset 노드(`FAnimNode_RotationOffsetBlendSpace`)는 가산 회전을 `ConvertPoseToMeshRotation`(루트 회전 포함, AnimationRuntime.cpp:1145) 뒤 `Rotation = Additive * Base`(TransformNonVectorized.h:1029)로 앞곱한다. 샘플 델타는 루트 0 기준으로 저작됐으므로 루트를 돌린 뒤 얹으면 Yaw 외 성분(Pitch · 팔 보정)이 RootYawOffset 만큼 틀어진 축으로 들어간다 — 오프셋 0 이면 무해, 오프셋 × Pitch 가 클 때만 깨져 "가끔". 엔진에도 같은 문제용 옵션이 있다(`FAnimNode_ApplyMeshSpaceAdditive::bRootSpaceAdditive` — 루트를 0 으로 두고 가산 후 복원).
- 근거: 새 프로브 `Tools/scripts/pie_pose_probe_run.py`(오프셋 0/±45 × Pitch 0/±40/−60 구간 평균, 가슴·목 기울기·손 선 Pitch 추가) + 읽기 전용 오프라인 모델(애셋 데이터에 엔진 공식 적용 — 현재 순서 예측이 PIE 를 0.6° 안에서 재현). 수정 전 오프셋 −45 · Pitch 0 에서 손 선 Pitch −29.5°(카메라 0), Pitch +40 에서 두 손 14.7cm·총 27°. 모델상 오프셋 −90 이면 총 Yaw 오차 −54°, 오프셋 +90 · Pitch +40 이면 고개 80° 숙임. 10-20 의 "AO 실제 비틀림 명목의 ~70%" 도 이 순서의 산물(AO 단독은 Yaw 45→46°, 90→90.4°).
- 수정: `LayeredBoneBlend → Aim_UpperBody → RotateRootBone → Inertialization`(`build_hero_turninplace.py` A1 `patch_aim_before_root` 이행 + 새 빌드의 `patch_base` 도 같은 위치, verify 순서 갱신). C++·공급자 무변경 — 순서가 베이스 한 곳이라 이후 무기 공급자도 자동으로 맞다. 수학: AO 를 루트 0 에서 얹고 합성 포즈를 통째로 돌리므로 AimYaw(= −RootYawOffset) 가 상체에서 정확히 상쇄된다.
- 재검증: verify PASS(순서 · 스모크 · 단위 6/6 · PIE 진입). 수정 후 PIE = "AO 단독" 모델과 1.6° 안에서 일치(오프셋 −45 · Pitch 0 손 21.7 · 총 −11.4 · Yaw 오차 0.4° / Pitch +40 손 21.5 · 총 43.4). 점진 회전 프로브: 회전 중 손 선 Yaw − 카메라가 기준 ±2.5° 안(AimYaw 78 에서 0.6°), 발·오프셋 지표 불변. 멀티(`pie_mp_probe_run.py 3 pose`, 리슨+클라2): 호스트 폰이 서버·클라 시뮬 프록시 세 월드에서 같은 값(오프셋 −45 · Pitch +40 손 21.5 · 총 42.6), 단일 PIE 와도 같다.
- **남은 것(콘텐츠)**: AO 샘플 자체 — 코너 샘플의 실제 총 Pitch 가 명목 ±90 이 아닌 −55~−63 / +67~+73, 사분면 안은 삼각분할(실측상 변-변 대각선) 보간이라 Yaw·Pitch 가 함께 큰 곳에서 오차: Yaw +45 · Pitch −40 손 16.1 · 총 −61.6(카메라 −40), Yaw +45 · Pitch −60 손 17.9 · 총 −79. Yaw ±45 · Pitch 0 에서도 총 −11.6°(CC·RC 중간 보간). 후보 = 왼손 IK(손 간격만, 총 방향은 오른손을 따름) · AO 샘플 보강/재저작. 오프셋 클램프 150 > AO 90 은 이제 자세가 아닌 조준 일시 이탈만(빠른 연속 회전에서 오프셋 −150 · 상체가 카메라에서 ~60° 벗어남 실측).
- **왼손 IK (같은 날, 2판)** — 1판(조준 중에만 · AimingIdle 파지점 상수 · 위치만)을 사용자 PIE 가 반려: "비조준에선 적용 안 됨 · 조준 왼손 약간 조절 필요". 사용자 A안(무기 소켓 단일 원천) 승인으로 교체.
  - **런타임(C++)**: 무기 액터 `AAstralWeaponActor::LeftHandGripSocket`(계열 액터 클래스의 관례 이름, 비우면 한손 무기) · `GetLeftHandGrip(ReferenceBone)` = 소켓을 부착된 캐릭터 메시의 hand_r 공간으로 환산(무기는 손 본에 붙은 강체 → 자세 무관 상수).
    `UAstralEquipmentManagerComponent::RefreshWeaponAnimData()`(10-22 이름 변경 — 옛 `RefreshLeftHandGrip`, 총구도 같이) 이 손에 든 무기(부착 기준으로 찾음 — 클라는 인스턴스 스폰 목록이 비어 있음)의 값을 메인 `UAstralAnimInstance::SetLeftHandGrip` 으로 넣는다(없으면 Clear).
    트리거 = 이벤트만: `RefreshAnimLayers` 끝(AnimBP 교체 포함) · `AAstralEquipmentActor::NotifyPresentationChanged`(서버 재부착 직후 `EquipmentInstance::ApplyAttachState` · 클라 `OnRep_AttachmentReplication` · 외형 `ApplyMeshInfo`) — 부착·상태·메시 복제 순서와 무관하게 마지막 호출로 수렴.
    AnimInstance 는 게임 스레드 `PendingLeftHandGrip` → 스냅샷 → 스레드 안전 업데이트가 `bHasLeftHandGrip · LeftHandGripLocation/Rotation` 노출(애님 워커와 경합 없음). 기준 본 `WeaponReferenceBone = hand_r`(10-22 이름 변경 — 옛 `LeftHandGripReferenceBone`, 총구도 이 본 공간).
  - **그래프(공급자 Aim_UpperBody, AimOffset 뒤)**: `LayeredBoneBlend(hand_l 이하 ← AS_IdleRifleAiming_02, 로컬, 커브 UseBasePose)`(손가락 = 쥔 모양 — 비조준 애니는 손가락이 펴져 있다) → L2C → `CopyBone(hand_r → ik_hand_gun, 컴포넌트)` → `ModifyBone(ik_hand_l, 부모 공간 Replace ← GetMainAnimInstance.LeftHandGripLocation/Rotation)` → `TwoBoneIK(hand_l → ik_hand_l 본, 회전도 목표에서, 팔꿈치 = lowerarm_l, 늘이기 최대 10%, Alpha bool ← GetMainAnimInstance.bHasLeftHandGrip 0.15초)` → C2L (`build_hero_turninplace.py` A2·A3 — 1판이 있으면 지우고 교체, verify 포함). 플러그인 허용 목록에 `CopyBone` 추가. TwoBoneIK 단독은 목표 회전 = 기준 본 회전뿐이라(AnimNode_TwoBoneIK.cpp:181) 회전 오프셋은 UE5 ik 본 체인으로 준다.
  - **데이터**: `Tools/scripts/setup/rifle_left_hand_grip.py`(ue_exec, 멱등) — 총 스켈레톤 `SK_RifleScifi` 의 키트 소켓 `LeftHandIK`(원래 위치 표식뿐, 회전 Yaw 180)를 hand_l 트랜스폼으로 다시 정의(키트 원래 값일 때만 — 조정값 보존, `RESET_SOCKET`) + `BP_Weapon_Rifle.LeftHandGripSocket = LeftHandIK` + **BP 컴파일**. 초기값 = AimingIdle 의 hand_r 기준 파지(손가락 쥔 모양과 맞는 손 각도)를 총열 방향 7cm 앞(핸드가드) — **10-22 교체**: 7cm 는 무기 배치 이중 적용(아래 "총구 정렬")으로 저작 손이 뒤로 밀려 있던 걸 메운 값이었다. 배치 교정 뒤 초기값 = AimingIdle hand_l 그대로(키트 LeftHandIK 와 2.9cm, 조준 Idle IK 보정 0, 두 손 거리 23.0 = 저작값). 스크립트는 이전 자동값이면 갱신·손 조정값은 보존. 키트 `HandGripTransformLeft` 는 손 축이 이 스켈레톤과 달라 손바닥이 감싸지 않았다(스크린샷) — 쓰지 않음.
  - **결과**: PIE 왼손 = 소켓 0.0cm · 0.0°(조준·비조준). 두 손 거리(목표 29.2) 오프셋 0/±45 × Pitch 0/±40/−60 전부 29.1~29.2(늘이기 전엔 오른쪽 비틂 + 숙임에서 25.5 — 팔 길이 부족), AO 범위 밖 빠른 회전 최저 27.0. 점진 회전 29.1~29.5 · 비조준 29. 멀티(리슨+클라2): 호스트 폰·클라 자기 폰·서로의 시뮬 프록시 전부 29.2, 낫 든 폰은 IK 없음. 프로젝트 테스트 24/24 · 두 구성 빌드 경고 0. 손 클로즈업은 PIE 에서 스프링 암을 손 중심으로 돌려 `AutomationLibrary.take_high_res_screenshot` 으로 확인.
  - **함정(실측)**: ① 파이썬으로 BP CDO 프로퍼티만 바꾸면 스폰 인스턴스엔 안 들어간다 — BP 생성 클래스는 컴파일 때 만든 "네이티브 기본값과 다른 프로퍼티 목록"(CustomPropertyListForPostConstruction)만 복사 → 바꾼 뒤 `BlueprintEditorLibrary.compile_blueprint` ② `SkeletalMeshSocket.SocketName/BoneName` 은 파이썬 읽기 전용(VisibleAnywhere) — 새 소켓 이름을 못 준다 ③ `SkeletalMesh.find_socket` 은 메시 → 스켈레톤 순 — 키트 소켓은 총 스켈레톤 소유라 메시를 저장해도 반영 안 됨(소켓의 outer 를 저장) ④ 무기 월드 소켓을 매 프레임 IK 목표로 쓰면 부착이 애님 뒤에 갱신돼 1프레임 지연 — 손 본 공간 상수로 넘긴다.
  - **남은 것**: 장전(`AS_ReloadRifle_01` — 손이 총을 떠남)·탄창 교체 몽타주를 연결하면 IK 를 끄는 커브 · 손 모양 미세 조정은 총 스켈레톤의 `LeftHandIK` 소켓을 옮기면 된다(PIE 재시작 또는 스타일 전환 시 반영). 총 방향 오차는 아래 "총구 정렬"로 해결.
- **총구 정렬 (2026-10-21 진단 → 10-22 사용자 추천안 승인·적용)** — 증상: 조준 중 총열이 투사체 방향과 어긋남(AO 가 모자랄 때 · 제자리 회전 중 가끔).
  - **지표**: 총열 = 무기 `Muzzle` 소켓 +X(SKM_RifleScifi_01: WeaponRoot 기준 Yaw 180 — 총열이 −X) ↔ 실제 발사 방향(총구 → 카메라 조준점, `ResolveShot` 과 같은 계산). 발사 틱 총열 ↔ 투사체 속도로 지표 검증. 프로브 `pie_muzzle_probe_run.py [구간] [grip] [타임라인 구간]`(정지 · Pitch ±40/±60/−80 · 오프셋 ±45 × Pitch · 턴 90° · 빠른 360° · strafe 4방향) · `pie_mp_probe_run.py 3 pose [grip]`(PIE_MP_MUZZLE — 서버 조준점 기준, 월드 간 폰은 위치로 짝). `err3d` = 총열 ↔ 실제 발사 방향, `vsCam` = 총열 ↔ 카메라 방향(시차 제외 자세 오차).
  - **원인 분해(수정 전, vsCam)**: ① **무기 배치 데이터 — 최대 원인** `DA_WD_Rifle1.AttachOffset` 이 손 소켓 `WeaponHandR` 상대값과 똑같아(위치 (−3.51, 3.39, −1.03), 회전 (P −0.82, Y 4.74, R −12.85)) 소켓 + 오프셋으로 **이중 적용** → 정지 조준에서 총열 Yaw +10.3 · Pitch +4.9, 전 구간 ~9°. 오프라인(AimingIdle 프레임 0): 현재 +10.15/+4.83 · 한 번만 +5.44/+3.80 · 무기 루트 = hand_r(키트 저작 기준 — 애니의 ik_hand_gun == hand_r) +1.09/+1.74 ② AO 콘텐츠 — 대각(±45, ±40) Yaw 과회전 8~12° · Pitch 극단 3~7° ③ AO 범위 포화 — 오프셋 클램프 150 > AO ±90, 빠른 회전에서만 28~37° ④ 가까운 표적 시차(3m 6~8°, 1m ~20°) ⑤ 네트워크는 원인 아님(시뮬 프록시 = 서버 0.01°), 턴 메커니즘 자체도 추가 오차 거의 없음.
  - **업계 관행 비교 후 선택**: Lyra = AO + 카메라 레이 판정 + 총구→탄착(총열 보정 없음) · AAA TPS = AO(거친 조준) + 절차적 최종 보정(척추·팔, 최대각·블렌드; UE5 는 Control Rig 또는 커스텀 스켈레탈 컨트롤). 엔진 `AimOffset LookAt` 은 기준 포즈 편향만 한 번에 보정(AO 이득 오차 못 고침, 총구 소켓이 캐릭터 메시에 있어야 함) · LookAt(손목만) · ModifyBone + 지난 프레임 피드백(1프레임 지연)은 기각.
  - **1단계 데이터**(`Tools/scripts/setup/rifle_weapon_grip.py`, 멱등·REVERT): `DA_EF_Rifle.ActorsToSpawn[0].AttachSocket` WeaponHandR(낫과 공유) → **hand_r** · `DA_WD_Rifle1.AttachOffset` → 항등(이중 적용값일 때만 — 조정값 보존). 구조체 멤버가 EditDefaultsOnly 라 파이썬 `set_editor_property` 가 거부 → `export_text`/`import_text`. 라이플 홀스터는 별도 HolsterOffset(override)이라 무관. 왼손 소켓 재유도(`rifle_left_hand_grip.py` 새 초기값). 결과: 정지 2.3 · AO ±45 1.5/2.4 · strafe 2.4~2.7 · 대각 8.6~9.6.
  - **2단계 최종 조준 보정** — 베이스 루트 `RotateRootBone → L2C → Astral Aim Correction → C2L → Inertialization`(`build_hero_turninplace.py` A4 `patch_aim_correction` + verify):
    - 순수 계산 `Animation/AstralAimCorrection.{h,cpp}` `AstralAimCorrection::Solve` — 체인 본(뿌리→끝)마다 같은 축의 회전을 가중치로 나눔(합 = 전체 보정), 회전 중심(체인 피벗 가중 평균) 기준으로 "총열 직선이 조준점을 지나는" 회전을 이차방정식으로 정확히 풀고(시차 포함) 피벗 차이로 남는 잔차는 반복 3회. 최대각 30°. 단순 "총구→조준점 방향 맞추기" 반복은 2m 표적에서 진동하며 느리게 수렴(손 계산 15 → −6.4 → +2.7 → −1.2)해서 바꿈. 테스트 `AstralBreak.AimCorrection.{Aligned, Far, NearParallax, Clamp, Weights}` 5/5(솔버 밖 독립 검증 포함).
    - 노드 `FAnimNode_AstralAimCorrection`(SkeletalControlBase, 기본 체인 spine_03·04·05 = 0.25·0.35·0.4 · WeaponBone hand_r · 순서·조상 관계 검증 실패면 평가 안 함) + 그래프 노드 `UAnimGraphNode_AstralAimCorrection` — **새 에디터 모듈 `AstralBreakEditor`(UncookedOnly, .uproject · Editor.Target 등록)**. 런타임 Build.cs 에 AnimGraphRuntime. MCP 는 노드 클래스를 이름으로 찾아 추가 가능, 알파 규칙은 SkeletalControlBase 상속으로 허용.
    - 척추에 두는 이유: 두 팔의 공통 조상이라 손·총·왼손 IK 결과가 강체로 함께 돈다. RotateRootBone 뒤 = 최종 컴포넌트 공간이라 조준점 변환이 단순하고 무기 계열과 무관.
    - 입력(`UAstralAnimInstance`): 총구 = 무기 `Muzzle` 소켓을 `WeaponReferenceBone` 공간으로(`AAstralRangedWeaponActor::GetMuzzleInReferenceBone` — 왼손 파지점과 공용 `GetSocketInReferenceBone`, 장비 매니저 `RefreshWeaponAnimData` 이벤트 → `SetMuzzle`). 조준점 = 게임 스레드에서 메인 ∧ 조준 중 ∧ 총구 있음일 때만: PlayerController 가 있으면(로컬·서버의 원격 플레이어) 발사와 **같은 함수** `AstralRangedAim::ComputeCameraAimPoint`(GA `ComputeAimTarget` 본문을 옮긴 단일 원천, 사거리 상수 `DefaultTraceRange` 공유), 아니면(시뮬 프록시·AI) BaseAimRotation 방향 먼 점. 거리는 `AimCorrectionMinDistance` 50cm 아래로 안 가고, **역거리로 보간**(`AimCorrectionDistanceInterpSpeed` 12/s — 시차 각 ∝ 1/거리라 각도 기준으로 고르게 수렴; 거리 그대로 보간하면 100m → 1m 전환이 0.45초 끌렸다). 노출 `bAimCorrectionActive · AimCorrectionTarget · MuzzleLocation/Rotation`(알파 bool 0.15초).
  - **결과(err3d, 단일 PIE)**: 정지 0.00 · AO ±45 0.00 · 대각 0.9~1.4(p95 ≤ 4) · Pitch ±40/±60 0.9~1.9(p95 ≤ 4.6) · 1m 표적 0.17초에 0.00 · 턴 90° 0.45/0.78 · strafe 0.1~0.6 · 정지 조준 발사 틱 총열 ↔ 투사체 p50 0.00. 남는 것: 빠른 360°(|AimYaw| > 90) 평균 7.8(최대각 30 으로 37 → 8) · 이동 + 1m 바닥 조준 ~3. 멀티(리슨+클라2): 서버 0.00, 시뮬 프록시 먼 표적 0.2, **가까운 바닥 조준 10~15**(관찰자는 카메라·거리를 몰라 BaseAimRotation 먼 점을 겨눔 — 조준 거리 복제가 후속 후보). 왼손 = 소켓, 두 손 23.0. 프로젝트 테스트 29/29, verify PASS, 두 구성 빌드 경고 0.
  - **프로브 함정**: 맵이 좁아 조준 트레이스가 3m 안 정적 메시에 자주 맞음 → 자세 오차는 vsCam, 탄도 오차는 err3d 로 나눠 본다 · `aim` 단계는 카메라를 한 틱에 꺾어 1프레임 40~110° 스파이크(인공물 — hold 는 mark 먼저) · 스크린샷용으로 카메라 붐을 옮기면 보정이 **그 카메라 방향**을 조준점으로 삼아 상체가 숙여진다(측면 컷 금지, 플레이 카메라 + 디버그 선으로 확인) · 이 에디터의 PIE 인원 설정이 3 이었다 · 빠른 회전 뒤 뒤로 걸어 장애물에 박히면 프로브 트레이스 시작점이 지형 뒤가 돼 85° 인공물(10-22 재확인: `strafe_b` 0.2초 동안 조준점 16cm < 최소 거리 50 — 설계상 허용 구간).
  - **후속 (2026-10-22 오후 — 측정 → 대안 비교 → 사용자 "1-A · 2-(a) · 3 설계만" 승인)**:
    - **① 관찰자 근거리 시차 → 서버가 조준점을 복제**. 원인 재확인: 카메라 붐 `SocketOffset (0, 40, 60)` — 카메라 레이가 눈보다 오른쪽 40 · 위 60cm 라 BaseAimRotation 먼 점을 겨누는 관찰자는 가까운 표적에서 그만큼 시차(바닥 Pitch −40 10.5°). 대안 비교: 거리만 복제(uint16)는 카메라 레이 원점을 몰라 같은 오차 · 프록시가 붐을 흉내 내 트레이스는 붐 충돌(벽에 붙을 때 = 근거리 상황)·카메라 랙·락온 카메라에서 틀리고 카메라 로직 이중화 · 눈 위치 트레이스는 손계산 ~11° · 압축 레이(측면 오프셋 int16×2 + 거리, ~5B)는 가능하나 재구성 수학이 더 많음 → **조준점 자체**.
      구현: `AAstralCharacter_Hero::ObservedAimTarget`(`FAstralObservedAimTarget{FVector_NetQuantize10 TargetComponentSpace(메시 컴포넌트 공간 — 관찰자 쪽 보간된 메시를 따라감), bValid}`, `COND_SimulatedOnly` — `InputFacingPresentation` 선례). 서버 `PreReplication`(엔진이 `RemoteViewPitch16` 을 채우는 자리 → 같은 패킷의 이동·Pitch 와 같은 시점)에서 조준 태그 ∧ PlayerController ∧ 손에 든 원거리 무기(`UAstralEquipmentManagerComponent::GetHeldRangedWeapon` — RefreshWeaponAnimData 와 같은 부착 기준)일 때 발사와 **같은 함수·인자** `AstralRangedAim::ComputeCameraAimPoint(PC, 폰, 무기, 총구)` → 양자화 단위(0.1cm) 넘게 바뀔 때만 씀(카메라가 멈추면 전송 없음), 조준이 끝나면 bValid 만 한 번. 원격 플레이어의 카메라는 서버가 ServerUpdateCamera(이동 패킷마다 MarkForClientCameraUpdate, ≥16.6ms)로 안다.
      `UAstralAnimInstance::ComputeAimCorrectionTarget` 시뮬 프록시 분기: 복제점 T 를 지나는 BaseAimRotation 방향 직선을 카메라 레이로 보고 `Distance = (T − 총구)·D`, `TraceStart = T − D·Distance` → 기존 최소 거리 · 역거리 보간 공통 경로(수렴하면 T 그대로). 복제 전·AI 는 예전 먼 점. 대역폭 ~8B/업데이트(조준 중 카메라가 움직일 때만, 관찰자에게만).
      결과(`pie_mp_probe_run.py 3 pose` · 새 `client_pose` 모드 — 클라가 조준한 폰을 다른 클라가 볼 때 = 서버가 원격 카메라로 계산한 점): 시뮬 프록시 정면 0.75 → **0.00** · 바닥 10.49 → **0.02** · 왼쪽 45+바닥 16.63 → **0.02** · 하늘 0.18 → 0.00 · 클라 폰 바닥 10.49/10.60 → **0.02**. 서버 0.00 · 소유 클라 ≤ 0.11 그대로.
    - **② 빠른 회전 포화 → `RootYawOffsetClamp` 150 → 120**(C++ 기본값). 실측식 `잔차 = |AimYaw| − 90(AO Yaw) − 30(보정 최대각)` — 빠른 360°(~240°/s)에서 |AimYaw| ≤ 120 구간은 ≤1.8°, 120 넘는 0.45초만 13~27°. 느린 360°(2°/틱)는 90 턴 4회·클램프 도달 0 → 클램프는 플릭에만 영향. 대안: 보정 최대각 60(척추 최대 60° 추가 비틀림 — 10-21 "상체 꺾임" 계열) · 절충 135/130/45 · AO Yaw 확장(원본 샘플 없음). **불변식: 클램프 ≤ AO Yaw 범위 + 보정 최대각**.
      결과(`pie_muzzle_probe_run.py spin`): `ao_sat` 평균 15.2 → **0.41**(p95 1.38) · spin 구간 p95 24.7 → **1.39**. 대가: 클램프 미끄러짐 84~96° → 120°(플릭 1회 +~30°, 클램프 프레임의 느린 발 평균 78 → 47cm/s), 턴은 Right90@−54 · Right180@−150 → Right90 ×3(180 클립은 180 임계 135 > 클램프라 안 나옴 — 쓰려면 클램프·AO 범위·보정 최대각을 함께 올린다). 느린 회전·정지/AO/Pitch/턴/strafe 구간 수치 회귀 없음. 테스트 `TurnInPlace.Accumulate` 갱신(기본 클램프 160° 한 프레임 → Right90, 클램프 150 명시 → Right180).
    - **③ 반동·장전 몽타주 알파 — 설계만(몽타주 없음: 원본 `AS_ReloadRifle_01`·`AS_RifleRecoil_01` 시퀀스뿐, `FireMontage` 미지정)**:
      반동 = 보정 노드 **뒤**(C2L 다음, Inertialization 앞)에 additive 슬롯 `UpperBodyAdditive` — 보정이 조준을 맞춘 포즈 위에 킥이 얹혀 되돌려지지 않는다(커브 불필요). `AS_RifleRecoil_01` → 프레임 0 기준 로컬 additive(`set_sequence_additive`) 몽타주. 기존 UpperBody 슬롯(보정 앞)에 비-additive 로 넣으면 보정이 저작 반동을 지운다.
      손이 총을 떠나는 동작(장전) = 몽타주 커브 `DisableAimCorrection` · `DisableLHandIK`(Lyra 명명, 0 → 1, 경사 0.1~0.15초). 메인 AnimInstance 가 `GetCurveValue` 로 읽는다(상체 슬롯 → LayeredBoneBlend 커브 Override → 메인 출력, 턴 커브와 같은 1프레임 늦은 경로). 알파 = 켜짐 블렌드 × (1 − 커브) float — 노드 알파 바인딩을 bool(0.15초) → float 로 바꾸고 블렌드는 C++. `FireMontage` 는 UpperBody 슬롯(전신이면 누적이 꺼진다). 왼손 IK 커브는 IK 세션 결과 뒤.
    - 측정 도구: `pie_aim_probe.py` dump 에 `PIE_TURNS`(wants 상승 에지마다 클립·오프셋) · `PIE_CLAMP`(누적 중 클램프에 붙은 프레임의 액터 Yaw 합 = 발 대신 미끄러진 각) · 진단 `console` 단계(`PROBE_CONSOLE`). **함정**: 에디터는 `set` 콘솔 명령을 막는다(`UUnrealEdEngine::Exec` "Set commands not allowed in the editor") · BP CDO 를 메모리에서 바꿔도 인스턴스엔 안 간다(커스텀 프로퍼티 목록은 컴파일 때 — 값이 네이티브와 같으면 목록에 없다) → 튜닝 변형은 코드/애셋을 바꿔 전후 비교.
- 프로브 함정: 원격 실행 클라이언트는 8KB 미만 조각을 받으면 응답 끝으로 본다(`remote_execution.py:465`) → 큰 덤프가 무작위로 잘려 "Failed to deserialize JSON" — 덤프 타임라인 ~200 줄 상한, 기록은 `unreal` 모듈에 남으니 재덤프 가능. 멀티 PIE 는 단계 하나가 ~0.7초라 사격을 회전 단계 안에서(AimHold 2초 · 진입 피벗 0.3초).

**남은 것**: 원거리 `FireMontage` 를 저작하면 **UpperBody 슬롯**이어야 한다(DefaultSlot 이면 매 발 누적이 꺼져 스프링이 오프셋을 되돌린다) · 조회 응답 `logic_type` · 프로브의 상태 이름 조회 대안 · 조준 보정: 반동·장전 몽타주를 저작할 때 위 ③ 설계 구현(반동 additive 슬롯 · `DisableAimCorrection`/`DisableLHandIK` 커브 → float 알파) · 180 턴 클립을 다시 쓰려면 클램프 ≥ 135 와 함께 AO Yaw 범위 또는 보정 최대각 상향(불변식 클램프 ≤ AO + 보정). 관찰자 시차·빠른 회전 포화는 10-22 오후 해결(위 "후속").

