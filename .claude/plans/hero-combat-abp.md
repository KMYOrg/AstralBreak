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
  Locomotion_Idle:  BlendListByBool(bActiveValue←bIsAiming)  false: AS_Hero_Rifle_Idle · true: AS_Hero_Rifle_Idle (= AO 기준 포즈. 처음엔 AS_IdleRifleAiming_02 였으나 AO 를 얹으면 상체가 비틀려 교체 — §5)
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
