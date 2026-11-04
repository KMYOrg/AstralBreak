# 히어로 전투 AnimBP — 근접(낫) · 원거리(총) · 조준 strafe (설계 근거 · 2026-10-19)

> 브랜치 `feat/character_ABP` · 사용자 확정 4건(2026-10-19): **Lyra 식 Linked Anim Layer** · **새 애셋 `ABP_Hero_Combat`**(운영 `ABP_Hero_Base` 는 보존) · **런타임 C++ 포함**(AnimInstance 변수 · 조준 유지 GE · 회전 모드) · **스켈레톤 통합은 새 Tool `reassign_skeleton`**.
> 생성은 전부 도구(`Tools/mcp/build_hero_combat.py`, Tool 30개), 런타임 배선은 `Tools/scripts/setup/hero_abp_wire_data.py`. 관련: [animbp-automation-handoff-phase6-2.md](animbp-automation-handoff-phase6-2.md) · [animbp-automation-phase1.md](animbp-automation-phase1.md) "Phase 7-6 결과".
> 2026-10-22 애님 애셋 정리: 애니 콘텐츠는 `/Game/Animation/Hero/Vesper/<계열>/<용도>/`, 이름 `AS_Vesper_<계열>_<동작>` (로직 ABP·ALI 는 `Hero/` 루트 그대로) — 규칙·근거·옛→새 매핑 [anim-asset-naming.md](anim-asset-naming.md). 이 문서의 애셋 이름은 새 이름으로 치환됨.

## 1. 요구

총을 **일정 시간 안에 계속 쏘는 동안**: 서 있으면 조준 Idle + AimOffset, 움직이면 8방향 strafe + AimOffset. 그 밖(근접 낫 · 쏘지 않는 총): 이동 방향을 향하는 보통 로코모션, AimOffset 없음. 유지보수(무기 추가)·최적화(스레드 안전) 우선.

## 2. 선행 제약과 해결

| 제약 (실측) | 해결 |
| :--- | :--- |
| 히어로 애니 애셋이 같은 본 이름의 **두 스켈레톤**(`/Game/Assets/IdaFaber/…/SKEL_UE5_F` = 메시·ABP, `/Game/IdaFaber/…/SKEL_UE5_F` = AO_Rifle·Rifle_Jog·M_Neutral·Jump_*·Attack1~3·몽타주 40개)으로 갈라져 ABP 가 B 애셋을 참조할 수 없었다 | Tool `reassign_skeleton`(엔진 `EditorAnimUtils::RetargetAnimations` 제자리) — `Tools/mcp/reassign_hero_skeleton.py --apply` 로 40개 → A. `/Game` 전체에 B 애셋 0. `/Game/IdaFaber/` 폴더(머티리얼·텍스처·메시 중복 79파일)는 남아 있다 — 삭제는 사용자 판단 |
| `AS_Vesper_Rifle_AO_CC` 만 additive 기준 포즈가 없어 AimOffset 샘플 거부(`ADDITIVE_INVALID`) | Tool `set_sequence_additive` — `AS_Vesper_Rifle_Idle` 프레임 0 기준 |
| 런타임에 "사격 중" 신호·조준 각·회전 모드가 없었다(`bOrientRotationToMovement=true` 고정 → strafe 자세 불가, 2026-10-10 보류 S-A/B/C) | C++ 4건 (§4) |

## 3. ABP 구조

```text
ALI_HeroCombat (인터페이스)         Locomotion_Idle · Locomotion_Move (입력 없음) · Aim_UpperBody (입력 포즈 InPose) — 그룹 DefaultSharedGroup(공급자 인스턴스 1개 공유)
                                   + Locomotion_WeaponOverlay(InPose, 2026-10-22 §9 — 베이스 SM 출력 뒤·DefaultSlot 앞, 라이플 = 조준 상체)

ABP_Hero_Combat (베이스, 부모 UAstralAnimInstance, DA_CD_Vesper.AnimInstanceClass)
  루트:  Locomotions SM → Slot DefaultSlot → SaveCachedPose FullBody → ┬ UseCachedPose → BasePose      ┐
                                                                       └ UseCachedPose → Slot UpperBody → BlendPoses_0 ┘ LayeredBoneBlend(spine_01, 메시 공간 회전)
         → LinkedAnimLayer Aim_UpperBody(InPose) → Inertialization → Output        (운영 ABP_Hero_Base 와 같은 뼈대 + 조준 레이어 한 단)
  SM:    운영과 1:1 — 상태 5 · conduit 2 · alias 4 · 전이 12 · Entry Idle. Idle/Move 상태 내부 = LinkedAnimLayer(Locomotion_Idle / Locomotion_Move). 점프 3상태는 시퀀스 그대로
  기본 구현(= 근접 낫 세트): Idle AS_Idle · Move BS_Vesper_Locomotion1D(X←Speed) · Aim 통과

ABP_HeroLayers_Rifle (공급자, DA_EF_Rifle.AnimLayerClass — 장비 매니저가 Ranged 스타일 활성 시 LinkAnimClassLayers)
  Locomotion_Idle:  BlendListByBool(bActiveValue←bIsAiming)  false: AS_Vesper_Rifle_Idle · true: 상태머신 IdleTurn(Idle = AS_Vesper_Rifle_AimIdle = AO 기준 포즈 — §7 10-20 교정; 10-19 의 Rifle_Idle 교체는 AO 기준이 잘못 잡힌 탓)
  Locomotion_Move:  BlendListByBool(bIsAiming)  false: BS_Vesper_Rifle_Jog(1D Speed: Idle→JogFwd) · true: BS_Vesper_Rifle_Strafe(2D Direction×Speed: Idle 5 + Jog 8방향 9)
  Aim_UpperBody:    InPose → AimOffset AO_Vesper_Rifle(2D Yaw×Pitch 9샘플; X←AimYaw · Y←AimPitch · Alpha(bool)←bIsAiming, 0.15초 블렌드) → Output
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
- 네 번째(2026-10-19): strafe 정상. 조준 Idle 이 비틀림 — `AS_Vesper_Rifle_AimIdle` 위에 AimOffset(기준 포즈 = `AS_Vesper_Rifle_Idle` 프레임 0)을 얹은 조합 때문(수정 전엔 Blend 가 거꾸로라 이 조합이 안 나왔다). 사용자 확정: **조준 Idle 도 `AS_Vesper_Rifle_Idle` + AimOffset**(True Pose 애셋 교체, revision `1409aabf…`, 컴파일 0 에러·저장). 교훈: AimOffset 은 기준 포즈 클립 위에서만 쓴다.
- **사용자 PIE 확인 완료(2026-10-19)**: 낫 로코모션 · 총 전환 · 발사 중 strafe · 조준 Idle(Rifle_Idle + AimOffset) 정상. 미확인: 멀티플레이(리슨 2클라) 관찰자 자세 · 창(2초)이 닫힌 뒤 복귀 연출의 느낌.
- (확인 항목 원안) 낫 로코모션이 운영과 같은가 · 총 전환 시 라이플 Idle/Jog · 발사 뒤 2초 동안 조준 Idle/strafe + AimOffset(Pitch 반응) · 창이 닫히면 복귀 · 멀티플레이(리슨 2클라)에서 관찰자도 같은 자세. 수치 튜닝(AimHoldSeconds · 블렌드 0.15/0.2 · strafe Speed 축 500)은 데이터.
- 되돌리기: `hero_abp_wire_data.py` 의 `REVERT = True` 로 실행하면 `ABP_Hero_Base` 로 복귀(`AnimLayerClass` 비움).

## 6. 남은 것 / 범위 밖

- 사격 몽타주(`FireMontage`)·`AS_Vesper_Rifle_Recoil`(additive) 연결 — 현재 원거리 GA 는 몽타주 미지정(즉발)일 수 있음. 반동은 UpperBody 슬롯 몽타주나 ApplyAdditive 로 후속.
  → 2026-10-25 AI 애니 생성 Phase 7: 반동 concat 루프 + additive + UpperBody 루프 몽타주를 anim-gen 이 후보 경로에 만들고 `ABP_Hero_Combat` **복제본**에서
  `slots_active[UpperBody]` 를 확인했다(운영 ABP 는 revision · 미리보기만, SHA-256 불변). 운영 적용 절차(승격 → 노티파이 → 바인딩을 정식 경로로 →
  `apply_graph_operations(expected_revision)` → 스모크 · 시나리오 · `AstralBreak.*` → GA `FireMontage` 지정은 별도 승인)는
  `Docs/AIAnimation/DevelopmentGuide.md` §12. 실제 운영 적용은 사용자 결정으로 Phase 7 완료 기준 밖.
- 조준 중 점프 상태는 무기 무관 시퀀스 그대로(라이플 점프 없음). → 2026-10-22 §9 무기 포즈 오버레이로 조준 상체 유지 · 비조준 공중 왼손 놓음.
- `/Game/IdaFaber/` 중복 폴더 정리(사용자 판단) · 운영 몽타주 UpperBody 슬롯·콤보 섹션(기존 후보 그대로 — 슬롯 · 섹션 편집 Tool 은
  `set_montage_slots` · `set_montage_sections`, 생성 몽타주는 옵트인 `generation_guard`).
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
| 애셋 | `Content/AS_Vesper_Rifle_Turn{Left,Right}_{90,180}`(루트, 스켈레톤 B) → `reassign_skeleton` 으로 A → `Tools/scripts/setup/hero_abp_move_turn_assets.py`(ue_exec) 로 `/Game/Animation/Hero/Vesper/Rifle/TurnInPlace/`. 커브 이름은 소문자 `turnyawweight`·`remainingturnyaw`(FName 비교는 대소문자 무시 — C++ `GetCurveValue("TurnYawWeight")` 그대로 읽힌다) |
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
- 원인: AO 9샘플은 `AS_Vesper_Rifle_AimIdle` 프레임 0 을 기준으로 저작된 포즈다(CC 샘플과 그 클립의 상체 본 회전차 0.0°, 위치 동일) — 그런데 additive 기준이 총 내린 `AS_Vesper_Rifle_Idle` 로 잡혀 있어 델타가 "총 들기 + 회전" 으로 거대해지고 샘플 사이(Yaw 30~85)의 보간이 무너진다(양 끝 샘플 자체는 손 거리 19~33 으로 멀쩡). 10-19 의 "AimingIdle + AO 비틀림 → Rifle_Idle 로 교체" 는 잘못된 기준 위에서 내린 결정이었다 — **교훈: AO 의 기준 포즈는 샘플이 저작된 클립이어야 하고, 조준 중 상체도 그 클립이어야 CC 가 항등이 된다.**
- 수정(`build_hero_turninplace.py` A0, 멱등): ① 9샘플 `set_sequence_additive ref_pose_sequence = AS_Vesper_Rifle_AimIdle 프레임 0`(저장) ② 조준 가지의 Idle 클립 5개(IdleTurn Idle · Rotation/Recovery 기본·상체) → AimingIdle ③ Move 조준 가지(strafe)에도 상체 LayeredBoneBlend(spine_01·메시 공간·UseBasePose, AimingIdle) — Jog 클립은 총 내린 자세(손 z≈105/95)라 재기준한 AO 를 그대로 얹으면 총이 안 올라간다. 비조준 가지(Rifle_Idle · Jog)·strafe BS 샘플은 그대로. `build_hero_combat.py` 도 새로 만들 때 같은 기준.
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
  - **그래프(공급자 Aim_UpperBody, AimOffset 뒤)**: `LayeredBoneBlend(hand_l 이하 ← AS_Vesper_Rifle_AimIdle, 로컬, 커브 UseBasePose)`(손가락 = 쥔 모양 — 비조준 애니는 손가락이 펴져 있다) → L2C → `CopyBone(hand_r → ik_hand_gun, 컴포넌트)` → `ModifyBone(ik_hand_l, 부모 공간 Replace ← GetMainAnimInstance.LeftHandGripLocation/Rotation)` → `TwoBoneIK(hand_l → ik_hand_l 본, 회전도 목표에서, 팔꿈치 = lowerarm_l, 늘이기 최대 10%, Alpha bool ← GetMainAnimInstance.bHasLeftHandGrip 0.15초)` → C2L (`build_hero_turninplace.py` A2·A3 — 1판이 있으면 지우고 교체, verify 포함). 플러그인 허용 목록에 `CopyBone` 추가. TwoBoneIK 단독은 목표 회전 = 기준 본 회전뿐이라(AnimNode_TwoBoneIK.cpp:181) 회전 오프셋은 UE5 ik 본 체인으로 준다.
  - **데이터**: `Tools/scripts/setup/rifle_left_hand_grip.py`(ue_exec, 멱등) — 총 스켈레톤 `SK_RifleScifi` 의 키트 소켓 `LeftHandIK`(원래 위치 표식뿐, 회전 Yaw 180)를 hand_l 트랜스폼으로 다시 정의(키트 원래 값일 때만 — 조정값 보존, `RESET_SOCKET`) + `BP_Weapon_Rifle.LeftHandGripSocket = LeftHandIK` + **BP 컴파일**. 초기값 = AimingIdle 의 hand_r 기준 파지(손가락 쥔 모양과 맞는 손 각도)를 총열 방향 7cm 앞(핸드가드) — **10-22 교체**: 7cm 는 무기 배치 이중 적용(아래 "총구 정렬")으로 저작 손이 뒤로 밀려 있던 걸 메운 값이었다. 배치 교정 뒤 초기값 = AimingIdle hand_l 그대로(키트 LeftHandIK 와 2.9cm, 조준 Idle IK 보정 0, 두 손 거리 23.0 = 저작값). 스크립트는 이전 자동값이면 갱신·손 조정값은 보존. 키트 `HandGripTransformLeft` 는 손 축이 이 스켈레톤과 달라 손바닥이 감싸지 않았다(스크린샷) — 쓰지 않음.
  - **결과**: PIE 왼손 = 소켓 0.0cm · 0.0°(조준·비조준). 두 손 거리(목표 29.2) 오프셋 0/±45 × Pitch 0/±40/−60 전부 29.1~29.2(늘이기 전엔 오른쪽 비틂 + 숙임에서 25.5 — 팔 길이 부족), AO 범위 밖 빠른 회전 최저 27.0. 점진 회전 29.1~29.5 · 비조준 29. 멀티(리슨+클라2): 호스트 폰·클라 자기 폰·서로의 시뮬 프록시 전부 29.2, 낫 든 폰은 IK 없음. 프로젝트 테스트 24/24 · 두 구성 빌드 경고 0. 손 클로즈업은 PIE 에서 스프링 암을 손 중심으로 돌려 `AutomationLibrary.take_high_res_screenshot` 으로 확인.
  - **함정(실측)**: ① 파이썬으로 BP CDO 프로퍼티만 바꾸면 스폰 인스턴스엔 안 들어간다 — BP 생성 클래스는 컴파일 때 만든 "네이티브 기본값과 다른 프로퍼티 목록"(CustomPropertyListForPostConstruction)만 복사 → 바꾼 뒤 `BlueprintEditorLibrary.compile_blueprint` ② `SkeletalMeshSocket.SocketName/BoneName` 은 파이썬 읽기 전용(VisibleAnywhere) — 새 소켓 이름을 못 준다 ③ `SkeletalMesh.find_socket` 은 메시 → 스켈레톤 순 — 키트 소켓은 총 스켈레톤 소유라 메시를 저장해도 반영 안 됨(소켓의 outer 를 저장) ④ 무기 월드 소켓을 매 프레임 IK 목표로 쓰면 부착이 애님 뒤에 갱신돼 1프레임 지연 — 손 본 공간 상수로 넘긴다.
  - **남은 것**: 장전(`AS_Vesper_Rifle_Reload` — 손이 총을 떠남)·탄창 교체 몽타주를 연결하면 IK 를 끄는 커브 · 손 모양 미세 조정은 총 스켈레톤의 `LeftHandIK` 소켓을 옮기면 된다(PIE 재시작 또는 스타일 전환 시 반영). 총 방향 오차는 아래 "총구 정렬"로 해결.
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
    - **③ 반동·장전 몽타주 알파 — 설계만(몽타주 없음: 원본 `AS_Vesper_Rifle_Reload`·`AS_Vesper_Rifle_Recoil` 시퀀스뿐, `FireMontage` 미지정)**:
      반동 = 보정 노드 **뒤**(C2L 다음, Inertialization 앞)에 additive 슬롯 `UpperBodyAdditive` — 보정이 조준을 맞춘 포즈 위에 킥이 얹혀 되돌려지지 않는다(커브 불필요). `AS_Vesper_Rifle_Recoil` → 프레임 0 기준 로컬 additive(`set_sequence_additive`) 몽타주. 기존 UpperBody 슬롯(보정 앞)에 비-additive 로 넣으면 보정이 저작 반동을 지운다.
      손이 총을 떠나는 동작(장전) = 몽타주 커브 `DisableAimCorrection` · `DisableLHandIK`(Lyra 명명, 0 → 1, 경사 0.1~0.15초). 메인 AnimInstance 가 `GetCurveValue` 로 읽는다(상체 슬롯 → LayeredBoneBlend 커브 Override → 메인 출력, 턴 커브와 같은 1프레임 늦은 경로). 알파 = 켜짐 블렌드 × (1 − 커브) float — 노드 알파 바인딩을 bool(0.15초) → float 로 바꾸고 블렌드는 C++. `FireMontage` 는 UpperBody 슬롯(전신이면 누적이 꺼진다). 왼손 IK 커브는 IK 세션 결과 뒤.
    - 측정 도구: `pie_aim_probe.py` dump 에 `PIE_TURNS`(wants 상승 에지마다 클립·오프셋) · `PIE_CLAMP`(누적 중 클램프에 붙은 프레임의 액터 Yaw 합 = 발 대신 미끄러진 각) · 진단 `console` 단계(`PROBE_CONSOLE`). **함정**: 에디터는 `set` 콘솔 명령을 막는다(`UUnrealEdEngine::Exec` "Set commands not allowed in the editor") · BP CDO 를 메모리에서 바꿔도 인스턴스엔 안 간다(커스텀 프로퍼티 목록은 컴파일 때 — 값이 네이티브와 같으면 목록에 없다) → 튜닝 변형은 코드/애셋을 바꿔 전후 비교.
- 프로브 함정: 원격 실행 클라이언트는 8KB 미만 조각을 받으면 응답 끝으로 본다(`remote_execution.py:465`) → 큰 덤프가 무작위로 잘려 "Failed to deserialize JSON" — 덤프 타임라인 ~200 줄 상한, 기록은 `unreal` 모듈에 남으니 재덤프 가능. 멀티 PIE 는 단계 하나가 ~0.7초라 사격을 회전 단계 안에서(AimHold 2초 · 진입 피벗 0.3초).

**남은 것**: 원거리 `FireMontage` 를 저작하면 **UpperBody 슬롯**이어야 한다(DefaultSlot 이면 매 발 누적이 꺼져 스프링이 오프셋을 되돌린다) · 조회 응답 `logic_type` · 프로브의 상태 이름 조회 대안 · 조준 보정: 반동·장전 몽타주를 저작할 때 위 ③ 설계 구현(반동 additive 슬롯 · `DisableAimCorrection`/`DisableLHandIK` 커브 → float 알파) · 180 턴 클립을 다시 쓰려면 클램프 ≥ 135 와 함께 AO Yaw 범위 또는 보정 최대각 상향(불변식 클램프 ≤ AO + 보정). 관찰자 시차·빠른 회전 포화는 10-22 오후 해결(위 "후속").

## 8. 원거리 사격 네트워크 (2026-10-22 밤 — ④ 조준 GE 예측 · ② 클라 조준 방향 전송)

### 8.1 지금 구조 (커밋 2ec8923 시점, 즉발 = `FireMontage` 없음)

| 머신 | 흐름 |
| :-- | :-- |
| 소유 클라 | 입력 → 예측 활성화(키 K) → `WaitAimAligned`(\|컨트롤 Yaw − 몸 Yaw\| ≤ 10°, 최대 0.3초) → `WaitNetSync(OnlyServerWait)` 신호(신뢰성 `ServerSetReplicatedEvent`) → 연출만 → `EndAbility`(신뢰성 `ServerEndAbility`) |
| 서버(원격 폰) | 활성화 → `ApplyAimHold`(GE, `State.Ranged.Aiming` 2초) → 신호만 기다림 → `OnFireSynced`: 몸이 10° 밖이면 Yaw 를 컨트롤러에 맞춤(총구 위치용) → `ResolveShot`(자유 조준 = **서버가 아는 카메라** `ServerUpdateCamera` 캐시) → 투사체 |
| 호스트 | 로컬 권위 — 정렬 뒤 같은 프레임 발사 |

신호 방식의 이유: 서버가 자기 정렬을 따로 기다리면 먼저 끝난 클라의 `EndAbility`(복제, `RemoteEndOrCancelAbility`)가 대기 중인 서버 인스턴스를 끝내 투사체가 안 나갔다. 신호와 `ServerEndAbility` 는 같은 ASC(PlayerState 채널)의 신뢰성 RPC 라 순서대로 도착 → 서버가 반드시 먼저 쏜다.

### 8.2 ④ 조준 GE 예측 (적용 · 미커밋)

- 문제: GE 를 서버만 적용 → 소유 클라의 조준 태그·회전 모드·`bIsAiming` 이 왕복(RTT) 뒤에 켜진다. 그동안 몸이 안 돌아 정렬 대기(0.3초)가 시간 초과 → **등진 채 발사**.
- 수정: `ApplyAimHold` 의 `IsNetAuthority` 가드 제거 — 권한 판정은 `ApplyGameplayEffectSpecToOwner` 의 `HasAuthorityOrPredictionKey`(GameplayAbility.cpp:2057). 호출 자리(`ActivateAbility` 동기 스택)가 활성화 예측 창이라 클라는 활성화 키로 적용(`GetPredictionKeyForNewAction`), 서버는 같은 키(`InternalServerTryActivateAbility` 의 창)로 적용.
- 엔진 근거(5.7 — 태그는 GE 가 아니라 **태그 카운트 컨테이너 복제**가 관리):
  - 소유 클라 예측 GE 는 태그 +1(`InternalOnActiveGameplayEffectAdded`, GameplayEffect.cpp:4577 `!bPostPredictObject`). 같은 키의 복제 GE 는 `bPostPredictObject`(자기 키) 라 태그를 다시 더하지 않는다(:2822, :4577).
  - 예측본이 키 따라잡기로 지워질 때 태그를 빼지 않는다 — "예측 제거가 아니면 서버 복제가 태그를 맡는다"(:4872 `IsNetAuthority() || bPredictionRejected`). 거부(`ClientActivateAbilityFailed`)면 `OnRejectedActiveGameplayEffect` → 태그 제거 = 롤백.
  - 서버의 `GameplayTagCountContainer`(GE 부여 태그 = `CountToOwner`) 가 소유자에게 **절대 개수**로 복제된다(GameplayEffectTypes.cpp:537-708, 수신은 `SetTagCount`) → 만료도 서버 복제가 끈다.
  - 연사 재적용: 기존 GE 위 예측 스택(`AllowPredictiveStackingGEs` 기본 true, :93)은 지속 시간 타이머를 다시 걸지 않는다(:4236) — 2초 창 갱신은 서버 재적용의 복제가 한다.
- 측정(`Tools/scripts/pie_fire_net_probe_run.py timing 100 3 3` — 리슨 + 클라 2, 모든 월드 `NetEmulation.PktLag 100` = 왕복 ≈ 200ms+프레임, 비조준·등진 175° 첫 발, 클라 활성화 시각 기준):

  | | 클라 조준 태그 | 클라 발사 | 발사 때 몸 | 서버 투사체 |
  | :-- | --: | --: | :-- | --: |
  | 수정 전 (3회) | +245 / +248 / +229ms | +265 / +286 / +281ms (0.3초 시간 초과) | **등짐**(정렬은 +466/+381/+374) | +466 / +421 / +417ms |
  | 수정 후 (3회) | **같은 프레임** | **+130 / +135 / +129ms (정렬 뒤)** | 정렬(≤10°) | +363 / +275 / +268ms |

  연사(0/0.5/1.0/1.5초): 클라 태그 누름 프레임부터 끊김 없이 유지, 서버 해제 = 마지막 수신 + 2.0초(3.684), 클라 해제 +115ms(3.799). 거부(`AbilitySystem.DenyClientActivations 2`): 클라 태그 누름 프레임 켜짐 → +241ms(RTT) 롤백, 서버 태그·투사체 없음. 투사체 방향 오차 0.00~0.03°(정지 카메라).
  서버 회전 모드는 여전히 활성화 수신 뒤 켜지므로 서버 쪽 몸은 신호 수신 때 6~9° 뒤처져 있다 — `OnFireSynced` 몸 Yaw 보정(10° 밖이면)은 유지.
- 관찰(수정의 부작용 아님, 엔진 기본): `ReplicateActivationOwnedTags`(GameplayAbilitiesDeveloperSettings, 기본 true) 로 서버 인스턴스의 `Ability.Attack.Basic.Ranged` 개수도 소유자에게 절대값 복제된다. 클라가 이제 서버 활성화보다 먼저 끝나므로 [누름+RTT, 발사+RTT] 동안 클라에 이 태그가 다시 보인다(전엔 클라 자신의 활성 구간에 묻혔다). `Ability.Attack` 을 보는 방어(`CanActivateAbility`)·스타일 전환(`ActivationBlockedTags`)이 그 구간 소유 클라에서 미뤄진다 — 방어는 WhileInputActive 재시도라 그 끝에 들어간다.
- 남는 경계: 직전 창이 서버에서 만료되는 순간(± 반 RTT)에 누르면 서버의 "태그 제거" 복제가 예측 태그를 지웠다가 새 GE 복제로 다시 켠다(≤ RTT 깜빡임). 예측 전에도 같은 깜빡임이 있었다.
- 호스트·시뮬 프록시: 변화 없음(호스트 = 로컬 권위, 관찰자 = 서버 태그 복제 +편도).

### 8.3 ② 클라 조준 방향 전송 (2026-10-22 밤 설계 → 사용자 승인 "45° · 몽타주 통일" → 적용 · 미커밋)

**측정으로 본 실체**(`pie_fire_net_probe_run.py flick 100 3 N <손실%>` — 조준·정렬 상태에서 카메라 Yaw ±8/±60·Pitch ±15 를 꺾고 **다음 프레임** 사격):
- 지연만(왕복 ≈ 200ms, 손실 0%)으로는 오차 0(24발 ≤ 0.02°) — 클라 발사는 직전 프레임 카메라 캐시를 쓰고, 그 카메라는 직전 프레임 이동 패킷과 함께 이미 서버에 있다.
- 클라 송신 손실 20%: 36발 중 **7발이 플릭 전 방향**(오차 = 플릭 전체 7.7~15.2°). 그 순간 서버 카메라 캐시는 플릭 전, **서버 컨트롤 회전은 이미 새 값**.
- 원인: 서버의 원격 카메라는 `ServerUpdateCamera`(비신뢰성 PlayerController RPC) 캐시인데 클라는 "직전 프레임 대비 바뀌었을 때만" 보낸다(PlayerCameraManager.cpp:810-828, 무변화 재전송은 `ServerUpdateCameraTimeout` 2초) → 그 패킷이 빠지면 다음 카메라 변화까지 낡는다. 고프레임에서 이동 전송이 묶이면(`ClientNetSendMoveDeltaTime` 1/60초) 같은 일이 손실 없이도 난다. 반면 `ServerMove` 는 이전 이동을 겹쳐 보내고 매 이동마다 컨트롤 회전을 갱신한다(CharacterMovementComponent.cpp:9905-9907). 발사 신호(PlayerState 채널 신뢰성)와 카메라(PlayerController 채널 비신뢰성)는 순서 관계도 없다.
- 프로브 함정: 플릭과 사격 주입을 같은 콜백에 넣으면 클라 자신도 플릭 전 카메라 캐시로 쏜다(=본 화면 그대로, 오차 아님).

**데이터** — `Combat/AstralRangedAttackTypes` 에 기존 활성화 페이로드와 같은 관례로:
`FAstralRangedFireData { FVector_NetQuantize10 AimPoint; FVector_NetQuantizeNormal AimDirection; }` + `FGameplayAbilityTargetData_AstralRangedFire`(NetSerialize · `Extract` = 정확히 1개 · 타입 · 유한 · 방향 정규 · `MakeHandle`). AimPoint = 소유 클라가 발사 순간 돌린 `AstralRangedAim::ComputeCameraAimPoint` 의 TargetPoint(발사·보정 애니·관찰자와 같은 함수), AimDirection = 그 카메라 방향. ~14B.

**흐름**(즉발·몽타주 공통 `CommitFire`, `WaitNetSync` 제거):
- 소유 클라: 발사 순간(즉발 = 정렬 뒤, 몽타주 = 발사 노티파이) 조준 계산 → `FScopedPredictionWindow`(WaitNetSync 와 같은 종속 키) 안에서 `CallServerSetReplicatedTargetData(스펙, 활성화 키, 데이터, 빈 태그, ScopedPredictionKey)` → 연출 → 즉발이면 `EndAbility`.
- 서버(원격 폰): `ActivateAbility` 에서 `AbilityTargetDataSetDelegate(스펙, 활성화 키)` 바인딩 + `CallReplicatedTargetDataDelegatesIfSet` → 수신 시 추출·검증 → 몸 Yaw 보정(현행 10° 규칙, 기준을 확정된 발사 방향 Yaw 로) → `ProcessFire` → `ConsumeClientReplicatedTargetData` → 즉발이면 종료. 원격 폰의 서버 쪽 발사 노티파이는 쏘지 않는다. `EndAbility` 에서 바인딩 해제.
- 호스트: RPC 없이 로컬 즉시(지금과 같음). 락온(`PinnedTarget`)·`FallbackAimPoint` 는 서버 해석 그대로 — 보고 조준점은 자유 조준에서만 쓴다(신호 역할은 항상).

**순서 보장 근거**: `ServerTryActivateAbilityWithEventData` · `ServerSetReplicatedTargetData` · `ServerEndAbility` 는 전부 `UFUNCTION(Server, reliable)`(AbilitySystemComponent.h:1725, 1570, 1734)이고 같은 ASC = 같은 PlayerState 액터 채널 → 신뢰성 번치는 채널 안에서 보낸 순서대로 처리된다. RPC 배칭(`ShouldDoServerAbilityRPCBatch`)은 기본 false 이고 Astral ASC 가 재정의하지 않는다(배칭 중이면 `CallServerSetReplicatedTargetData` 가 배치에 싣는다 :4217). 클라는 같은 콜스택에서 데이터 → `EndAbility` 순서로 보낸다 → 서버는 활성화 → 데이터 → 종료 순으로 받는다(지금의 `ServerSetReplicatedEvent` 와 같은 성질). 데이터가 인스턴스보다 먼저 와도 ASC 가 (스펙, 키)로 보관한다(`ServerSetReplicatedTargetData_Implementation` :3944) → 바인딩 직후 `CallReplicatedTargetDataDelegatesIfSet`.

**검증·실패 처리**(원격 폰 · 자유 조준):
1. 구조 — `Extract` 실패(개수·타입·NaN·비정규 방향) = 거부.
2. 기준 방향 = **서버 컨트롤 회전**(ServerMove — 위 측정대로 카메라 캐시보다 손실에 강하다. 이 게임은 카메라 회전 = 컨트롤 회전: 스프링 암 `bUsePawnControlRotation`, 회전 지연 없음, 락온도 `SetControlRotation`).
3. 각(보고 방향, 기준) ≤ `MaxReportedAimDivergence`(제안 45°) → **수락**: 보고 조준점(서버 총구 기준 전방 보장 · 사거리 클램프만). 밖이면 **클램프**: 기준에서 보고 쪽으로 최대각만큼 돌린 방향으로 서버가 트레이스. 거부(1)면 기준 방향 그대로 트레이스.
- 폴백이 아니라 클램프인 이유: 허용각을 넘는 정상 경우(큰 손실 공백 + 빠른 플릭)에 폴백은 바로 ②의 증상(옛 방향)이고, 클램프는 플레이어가 겨눈 쪽에 가장 가까운 탄. 악용 상한은 둘 다 같다(PvE).
- 45° 근거: 정상 발산 = 카메라 각속도 × (마지막 처리된 이동 이후 시간). 손실 한 번 + 1프레임(≈ 50ms)에 ~900°/s 플릭까지 수락.
- 순수 함수 `AstralRangedAttack::CheckReportedAimDirection(Reported, Reference, MaxDeg) → {Accepted | Clamped | Rejected, Direction}` + 단위 테스트(`AstralBreak.Ranged.ReportedAim` · `AstralBreak.Ranged.FirePayload`). 트레이스는 `AstralRangedAim::ComputeCameraAimPoint` 를 "뷰(위치·방향) 지정" 함수 위 래퍼로 나눠 같은 규칙(총구 투영 시작 · Visibility · 전방 보장)을 재사용.

**몽타주 경로**: 같은 데이터로 통일(위 흐름). 대안 "서버 노티파이 + 도착한 데이터가 있으면 사용" 은 출처가 도착 순서에 따라 갈려 기각. 지금 `FireMontage` 를 쓰는 무기는 없다 — 코드 경로 + 단위 테스트까지.

**단일 원천**: 정의는 하나(`ComputeCameraAimPoint`). 발사 = 소유 클라가 발사 순간 돌린 값(이벤트·신뢰성, 서버는 컨트롤 회전으로 상한만 건다). 표현(관찰자 `ObservedAimTarget` · 서버 쪽 조준 보정 애니) = 서버가 원격 카메라로 돌린 값(연속·근사) — 묶지 않는다. 남는 차이: 카메라 갱신이 빠진 동안 관찰자 총열이 옛 방향(표현만). 없애려면 서버의 원격 플레이어 뷰 회전을 컨트롤 회전으로 바꾸는 별도 변경(`AstralRangedAim`, 다른 세션들 공용) — 선택 사항.

**허용각의 의미(사용자 질문에 답한 정리)**: 비교 대상 = 클라가 보낸 카메라 방향 ↔ 서버 컨트롤 회전. ≤ 45° 면 클라 조준점 그대로(정상 플레이 거의 전부), 넘으면 서버 방향에서 클라 쪽으로 45° 까지만(예: 서버 0°·클라 70° → 45°), 데이터 손상이면 서버 방향. 영향 범위 = 원격 클라의 자유 조준 투사체 방향만(호스트·락온·몸 회전·애니 무관).

**구현** (빌드 Development·DebugGame 경고 0, 테스트 31/31 — 새 `Ranged.FirePayload`·`Ranged.ReportedAim`):
- `Combat/AstralRangedAttackTypes.{h,cpp}` — `FAstralRangedFireData` · `FGameplayAbilityTargetData_AstralRangedFire`(NetSerialize·Extract·MakeHandle) · `EAstralReportedAimResult`/`FAstralReportedAimCheck{Result, Direction, Divergence}` · 순수 `CheckReportedAimDirection`(정반대·수직 기준까지 축 처리, 180 = 검증 없음) · `ClampReportedAimPoint`(서버 총구 기준 전방 보장 · 사거리 1.1배 밖은 사거리로).
- `Combat/AstralRangedAim.{h,cpp}` — 트레이스 규칙을 `ComputeAimPointAlongView(뷰 위치, 방향, …)` 로 분리, `ComputeCameraAimPoint` 는 `GetPlayerViewPoint` 뒤 그 함수를 부르는 래퍼(동작 동일 — 관찰자 복제·보정 애니 무변경).
- GA `GetRangedWeaponActor` — 어빌리티 SourceObject(장비 인스턴스 스폰 목록)가 **클라에선 비어** null 이었다(첫 PIE 에서 보고가 전부 `Rejected` = 방향 0). 실패하면 `UAstralEquipmentManagerComponent::GetHeldRangedWeapon()`(부착 기준 — 보정 애니·관찰자 복제와 같은 조회).
- GA — `WaitNetSync` 제거. 로컬 `CommitFire`(즉발 = 정렬 뒤 · 몽타주 = 발사 노티파이): 소유 클라는 `SendFireTargetData`(종속 예측 창 + `CallServerSetReplicatedTargetData`) 후 연출, 호스트는 바로 발사, 즉발이면 종료. 원격 폰의 서버: 활성화에서 `AbilityTargetDataSetDelegate` 바인딩 + `CallReplicatedTargetDataDelegatesIfSet` → `OnFireTargetDataReceived`: 추출(보관분으로 불렸을 수 있어 소비는 추출 뒤) · 컨트롤 회전 대비 검증 · 몸 Yaw 보정(자유 조준 = 확정 방향, 락온 = 컨트롤러) · 발사 · 즉발이면 종료. 서버 쪽 발사 노티파이는 원격 폰이면 무시. `ResolveShot` 자유 조준: 원격 = `ResolveReportedAimPoint`(수락 = 보고 조준점, 클램프·거부 = 서버 카메라 위치에서 확정 방향으로 같은 규칙 트레이스), 로컬 = 카메라. 로그: 수락 Verbose · 클램프/거부 Log (`Report=… Divergence=…`). 노브 `MaxReportedAimDivergence` 45. `EndAbility` 에서 바인딩 해제·보관분 소비.

**측정**(`pie_fire_net_probe_run.py flick 100 3 3 20` — 왕복 ≈ 200ms + 클라 송신 손실 20%, 조준·정렬 상태에서 카메라 Yaw ±8/±60 · Pitch ±15 를 꺾고 다음 프레임 사격, 클라 2 × 6종 × 3라운드):

| | 플릭 사격 | 1° 넘게 빗나감 | 최대 오차 | 그때 서버 카메라 캐시가 낡은 발 |
| :-- | --: | --: | --: | --: |
| 단계 2 전 | 35 | **7** (15.2° ×5 · 7.7° · 1.4°) | 15.23° | 6 (≤15°) |
| 단계 2 후 | 36 | **0** | 0.53° | 13 (최대 60° — 그래도 정확) |

보고 74건 전부 Accepted. 서버 컨트롤 회전 대비 차이 > 0 은 4건(8, 8, 15, 15° = 플릭 한 번, 이동 패킷까지 빠진 경우) — 45° 상한엔 한 번도 안 걸렸다. 0.5° 안팎 잔차는 서버·클라 총구 위치 차. 신뢰성 재전송으로 0.4~0.9초 늦은 발 8(방향은 정확).
회귀(`timing 100 3 3`, 손실 0%): 비조준·등진 첫 발 클라 발사 +148/+147/+142ms(정렬 뒤) · 서버 투사체 +280/+276/+275ms · 방향 0.00° · 보고 Accepted 0.00° / 연사 4발 × 클라 2 전부 0.00°, 태그 서버 3.672 · 클라 3.778 해제 / 거부: 클라 태그 +231ms 롤백, 투사체·보고 없음. `host 100 3 2`: 호스트 누름 프레임 태그 · 정렬 뒤 +129/+149ms 같은 프레임 발사(오차 0, 보고 없음 = 로컬 경로), 관찰자 태그 = 서버 +~115ms. 테스트 31/31.
프로브 함정: 서버 활성화 태그의 소유자 복제 깜빡임(§8.2 관찰)이 active 1→0 으로 잡혀 "shot=none" 가짜 발사가 기록된다 — 집계는 플릭 발만.

## 9. 라이플 점프 — 무기 포즈 오버레이 · 왼손 IK 조건 (2026-10-22, 사용자 PIE 2건 → 추천안 승인 · 미커밋)

**증상**: ① 조준 중 점프하면 상체가 조준 자세를 유지하지 않는다 ② 비조준 점프에서 왼손이 계속 총을 잡아 부자연스럽다("특정 조건일 때만 잡도록").

**원인(MCP 조회 + PIE 실측 `pie_jump_probe_run.py`)**: 베이스 SM 의 JumpStart · FallLoop · FallLand 는 무기 무관 시퀀스(`AS_Vesper_Jump_Start/FallLoop/Land`)이고 Idle/Move 만 레이어였다. 조준 상체(`AS_Vesper_Rifle_AimIdle` = AO 기준 포즈)는 공급자가 **지상 상태마다** 덮었다(IdleTurn 회전·Recovery LBB · Move strafe LBB) — 공중엔 없어 AO 가산이 점프 클립 팔에 얹혔다. 왼손 TwoBoneIK 알파는 `bHasLeftHandGrip`(무기 듦)만 봤다.

| 수정 전 (제자리 점프, 호스트) | 지상 | 공중 |
| :-- | :-- | :-- |
| 조준 | 총열↔카메라 0.7° | 상체 편차(가슴 공간 두 손 위치, 지상 기준과의 거리 합) 평균 83cm · 최대 100 · 총열↔카메라 하강 중 최대 45°(보정 노드 30° 초과) |
| 비조준 | 왼손↔파지 소켓 0 | 0 그대로(공중 내내 IK, 이륙 때 팔이 모자라 최대 5.3cm) · 총 Pitch 최대 +47°(오른팔 = 점프 클립) |

**대안 비교 → 선택**: ① 조준 상체 — (a) 점프 3상태 레이어화(Lyra 상태별 레이어; 무기 전용 점프 클립이 없어 같은 클립 + 같은 덮기를 3번 반복) · (b) 베이스 루트에서 공중∧조준 덮기(무기 무관 베이스가 라이플 포즈를 알아야 함 — 기각) · **(c) 상태머신 출력 뒤 공용 레이어**(Lyra `LeftHandPose_OverrideState` 처럼 SM 뒤 오버레이) + 지상 중복 덮기 3곳 제거. ② 왼손 — (b) 상태 규칙(공중∧비조준 → 놓기; 콘텐츠 무변경, 나중에 두 손 점프 클립·장전 때 규칙 수정) · **(c) 커브 + 조준 조합**(§7 ③ 장전 설계와 같은 경로).

**구현**:
- C++ `UAstralAnimInstance`: `AimPoseAlpha`(bIsAiming 을 `AimPoseBlendTime` 0.2초 등속으로 따라감) · `LeftHandIKAlpha` = 파지점 ? 보간(1 − `DisableLHandIK` 커브 × (1 − AimPoseAlpha), `LeftHandIKBlendTime` 0.15) : 0. 메인이 계산(커브 = 메인의 지난 프레임 최종 포즈, 턴 커브와 같은 경로), 링크 인스턴스는 같은 프레임 메인 값을 복사(bIsAiming 과 같은 방식) — 공급자 그래프는 자기 변수를 읽는다. 설정 `LeftHandIKDisableCurve`("DisableLHandIK", Lyra 명명).
- 인터페이스 `ALI_HeroCombat` + `Locomotion_WeaponOverlay(InPose)` (도구 `add_anim_layers` + conform). 베이스 루트 `Locomotions → LinkedAnimLayer Locomotion_WeaponOverlay → Slot DefaultSlot` — **슬롯 앞**이라 전신·상체 몽타주는 계속 이긴다(Aim_UpperBody 안에 두면 상체 몽타주를 덮는다). 베이스 기본 구현 = 통과(근접·맨손).
- 라이플 오버레이 = `LayeredBoneBlend(spine_01↑ ← AS_Vesper_Rifle_AimIdle, 메시 공간, 커브 UseBasePose)` 가중치 ← `AimPoseAlpha`(VariableGet — 도구 `bind_pin` 은 배열 원소 핀 BlendWeights_0 을 바인딩 못 한다). 커브가 베이스 것이라 턴 클립 `TurnYawWeight` · 점프 클립 `DisableLHandIK` 가 지나간다.
- 지상 중복 제거: Move strafe LBB · IdleTurn Rotation/Recovery LBB 와 그 보조 AimingIdle 플레이어(공급자 플레이어 14 → 12). 조준 상체 = 오버레이 한 곳(무기마다 이 레이어 하나).
- 공급자 `Aim_UpperBody`: TwoBoneIK 알파 bool(`GetMainAnimInstance.bHasLeftHandGrip`) → float `LeftHandIKAlpha` · 왼손 손가락(쥔 모양) LBB 가중치도 `LeftHandIKAlpha` — 놓으면 손가락도 클립 그대로.
- 콘텐츠: `AS_Vesper_Jump_Start/FallLoop/Land` 에 `DisableLHandIK` = 1 (`Tools/scripts/setup/hero_jump_lhand_curve.py`, 멱등 · REVERT). 클립은 낫·맨손도 쓰지만 커브를 읽는 쪽은 파지점이 있을 때뿐(운영 `ABP_Hero_Base` 는 안 읽음). 나중에 무기 전용 두 손 점프 클립엔 커브를 안 넣으면 계속 잡는다 — 판단은 콘텐츠.
- 스크립트: `build_hero_turninplace.py` A5 `patch_weapon_overlay` · A6 `patch_left_hand_alpha` + verify(오버레이 체인 · 기본 구현 통과 · 라이플 오버레이 · 플레이어 12 · IK float), B2·A0-Move 는 오버레이가 있으면 건너뜀, `turn_state_ops` 기본(None) 플레이어 `bIgnoreForRelevancyTest`(새 빌드에서 빠져 있던 것), A1 이행 판정이 A4(보정 노드) 뒤에서도 통과하도록, 베이스 루트 레이어 노드 선택은 레이어 이름으로(`layer_node` — 이제 2개). `build_hero_combat.py` verify 레이어 3 → 4.

**결과**(`pie_jump_probe_run.py [move]` 단일 · `pie_mp_probe_run.py 3 jump` 멀티):

| | 수정 전 | 수정 후 |
| :-- | :-- | :-- |
| 조준 점프 상체 편차 | 평균 83 · 최대 100cm | **0.6 · 0.8cm** (달리기 점프 0.5) |
| 조준 점프 총열↔카메라 | 평균 15 · 최대 45° | **0.9 · 1.7°** (달리기 1.9 · 4.3) |
| 조준 점프 왼손 IK 알파 | (bool 1) | 1.00 내내 · 왼손↔소켓 0 |
| 비조준 점프 왼손 | 공중 내내 소켓 0 | 이륙 **0.11초** 뒤 놓음(알파 < 0.5) · 공중 평균 알파 0.13 · 소켓에서 평균 40cm · 착지 **0.13초** 뒤 다시 잡음 |
| 멀티(리슨 + 클라 2, 호스트·클라 폰 동시) | — | 같은 폰은 서버 · 소유 클라 · 시뮬 프록시가 같은 값 — 조준 aimPose 1 · 알파 1 · 총열↔BaseAim ≤ 1.7° / 비조준 알파 평균 0.14~0.18 · 소켓 38~40cm |

전환 속도(가슴 공간 손 속도): 착지 왼손 최대 664cm/s · 같은 순간 오른손 542 — IK 와 무관한 기존 착지 크로스페이드(FallLand 는 `bIsOnGround` 에서 바로 0.2초 블렌드로 끝남, 총 Pitch +31 → −38)와 같은 크기. 이륙 왼손 491(오른손 220) = 놓는 동작. 회귀: `pie_muzzle_probe_run.py` 전 구간 이전 기록 범위 안(정지·AO ±45 0.00 · 대각 0.6~1.05 · Pitch 0.67~1.48 · 턴 0.35/0.68 · spin ao_sat 0.50 · strafe f/r/l 0.09~0.46; strafe_b 5.75 는 기존 장애물 인공물) · 두 손 23.0 전 구간 · 턴 Right90 정상. verify PASS(스모크 · 단위 11) · 프로젝트 테스트 31/31 · 두 구성 빌드 경고 0.

**후속 — 비조준 공중 휴대 팔 (같은 날, 사용자 "후속안도 구현")**: 왼손을 놓자 총이 오른손 혼자 점프 클립 팔을 따라 최대 +48° 들렸다(스크린샷: 낙하 중 두 손을 얼굴 앞에 든 채 총이 위를 향함).
- 사용자 질문 "무기별로 확장성 있는 구조인가" → 예: 덮을 자리(오버레이 레이어)는 베이스, 무엇을 덮을지는 무기 공급자, 조건은 상태 규칙이 아니라 클립 표시(같은 `DisableLHandIK`) — 무기 전용 두 손 점프 클립이 생기면 커브만 뺀다. 장전처럼 손이 떠나는 몽타주는 슬롯이 오버레이 뒤라 계속 이긴다.
- C++ `HandsFreeAlpha` = `DisableLHandIK` × (1 − AimPoseAlpha) 를 0.15초 등속 보간(왼손 IK 를 끄는 것과 같은 신호 — 파지점과 무관해 무기 교체 순간에도 휴대 팔이 튀지 않게 LeftHandIKAlpha 와 따로 보간). 메인 계산, 링크 복사.
- 라이플 오버레이 = InPose → `LayeredBoneBlend(clavicle_r↓ ← AS_Vesper_Rifle_Idle 프레임 0 SequenceEvaluator, 메시 공간 — 몸통이 숙여도 총은 휴대 방향, 커브 베이스)` 가중치 ← HandsFreeAlpha → 조준 상체 블렌드 → Output (`build_hero_turninplace.py` A7 `patch_weapon_carry` + verify). 정지 프레임인 이유: Rifle_Idle 은 8.9초 대기 클립이라 공중 1초 안에 몸짓이 섞이지 않게.
- 결과(`pie_jump_probe_run.py` 의 PIE_JUMPHANDS 추가 지표, 전 → 후): 비조준 공중 총 Pitch −38..+48 → **−38..−36**(지상 휴대 −37) · 오른손 지상 휴대 대비 평균 29.4/최대 46.6 → **11.8/17.2cm**(남은 건 몸통 움직임) · 총구 위치 편차 98 → 35cm · 착지 오른손 최대 속도 512~542 → **266cm/s**(총 스냅 절반) · 이륙 219 → 150. 왼손은 그대로 놓음(알파 0.13 · 소켓에서 38cm). 조준 점프 무변화(상체 편차 0.6 · 총열↔카메라 ≤ 1.7°). 달리기 점프 같음. 멀티 전 월드 총 Pitch −41..−36 · 같은 값. verify PASS · 31/31 · 두 구성 빌드 경고 0.

**남은 것**: 장전 몽타주를 저작하면 커브 `DisableLHandIK` 만 넣으면 같은 경로로 왼손 IK 가 꺼진다(§7 ③). 무기 전용 점프 클립이 생기면 그때 점프 상태를 레이어화(Lyra (a))해도 오버레이·커브는 그대로 쓴다.

