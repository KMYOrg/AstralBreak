# 제자리 회전(TurnInPlace) · 조준 애니 — 다음 세션 핸드오프 (2026-10-20 밤, 브랜치 `feat/character_ABP`, 전부 미커밋)

> 이 문서 하나로 이어서 작업할 수 있게 썼다. 근거·수치·엔진 경로는 [hero-combat-abp.md](hero-combat-abp.md) §7(제자리 회전 설계·실측·2차 수정) 과 §5(히어로 전투 ABP PIE 4회 원인),
> 도구 전반은 [animbp-automation-handoff-phase6-2.md](animbp-automation-handoff-phase6-2.md)(§13 미커밋 목록·커밋 초안 3건) + `Plugins/AnimGraphMcp/README.md`.
> 관련 메모리: `project_animbp-automation.md`. 커밋은 사용자가 한다 — 세션은 커밋·브랜치 변경 금지.

## 0. 남은 문제 3건 (사용자 3차 PIE 보고, 이 세션의 출발점)

| # | 증상 | 현재 이해 · 가설 | 접근 후보 |
| :-- | :-- | :-- | :-- |
| 1 | **연속 회전 때 발 쪽이 갑자기 전환**되는 느낌(오프셋 수치는 매끄럽다 — 프로브 점프 ≤2.4°) | Recovery → Rotation 재진입이 `bAlwaysResetOnEntry` 로 턴 클립을 **처음부터** 다시 틀어 발 위치가 "디딘 발 → 시작 자세" 로 되돌아간다. 관성 전이 0.2초가 이를 가리지만 발은 바닥 접촉이라 눈에 띈다. Lyra 도 같은 구조지만 Lyra 클립은 회전 구간이 짧고 발 위치 차가 작다 | (a) 재진입 전이(Recovery→Rotation, Idle→Rotation)의 `CrossfadeDuration`(= 관성 시간) 0.2 → 0.3~0.4 (`set_property`, 두 줄) (b) 재진입 허용 조건에 "Recovery 가 N초 이상 재생" 추가 — 규칙에 `{"call": {"function": "GetInstanceCurrentStateElapsedTime", ...}}` 는 머신 인덱스가 필요해 까다로움; 대신 C++ 에 `bTurnInPlaceRecoverySettled`(마지막 fin 뒤 경과 ≥ 0.25초 등) 출력을 추가해 규칙 `and` 로 (c) 180 클립 활용: 클램프 150 이라 한 프레임에 135 이상이면 180 클립 — 마우스 회전은 점진이라 90 클립이 연달아 뜬다. `TurnThreshold` 50 → 45 로 당겨 더 일찍 시작하면 한 번에 끝나는 비율이 는다 (d) 궁극: Lyra 처럼 Recovery 에 SequenceEvaluator(ExplicitTime=TurnInPlaceAnimTime) 를 쓰고 재진입 시 클립을 재시작하지 않는 대신 **이어서** 돌리는 "연속 턴" 설계 — 큰 변경 |
| 2 | **AimOffset Yaw 가 작동하지 않는 것처럼** 보인다 | 조준 중엔 `bUseControllerRotationYaw` 로 액터가 매 프레임 컨트롤러 Yaw 에 스냅되므로 `AimDelta.Yaw = 조준 − 몸 ≈ 0` 이다. 상체 Yaw 는 **RootYawOffset 이 쌓인 동안만** 보인다(`AimYaw = −RootYawOffset`, 임계 50 아래에서 최대 ±50, 회전 중 ±80 — 프로브로 수치 확인됨, 손 거리 23 유지). 즉 설계상 "카메라를 돌리면 발은 멈추고 상체만 따라가다 50도에서 발이 따라온다" 인데, 몸이 통째로 도는 것으로 보였다면 ① AimYaw 부호가 반대(상체가 오프셋 방향으로 더 돌아 통째로 도는 듯 보임) ② AO 샘플의 Yaw 폭이 작음(RC 에서 spine_03 Yaw 차 35°) ③ 블렌드스페이스 축 매핑(Yaw 축 −90..90, R = +90) 중 하나 | PIE 에서 `showdebug animation` 또는 `pie_turn_probe_run.py ... spin` 로 AimYaw 부호와 상체 회전 방향을 눈·수치로 대조. 부호가 반대면 `AstralAnimInstance.cpp` `AimYaw = NormalizeAxis(AimDelta.Yaw - RootYawOffset)` 의 부호(또는 AO X 바인딩)를 뒤집는다. 폭이 문제면 AO 축 범위·샘플(콘텐츠) |
| 3 | **비조준 상태에서 카메라를 등진 채 사격**하면 발사와 동시에 액터가 180° 스냅(조준 태그 → 회전 모드 전환) → 총알이 "반대로 이동하는" 듯 보인다 | `UAstralGA_Hero_BasicAttack_Ranged::ActivateAbility` 가 커밋 직후 `ApplyAimHold` → `State.Ranged.Aiming` → `UAstralHeroMovementComponent::ApplyAimingRotationMode` 가 `bUseControllerRotationYaw=true` 로 바꾸고 **같은 틱의 `PlayerController::UpdateRotation → FaceRotation` 이 액터를 즉시 컨트롤러 Yaw 로** 돌린다. 발사(노티파이 또는 즉발)는 몸이 돌기 전·중에 나간다 | (a) **회전이 끝난 뒤 발사**: 조준 모드 진입 시 `bUseControllerRotationYaw` 대신 `bUseControllerDesiredRotation + RotationRate`(예 720°/s)로 **부드럽게** 돌리고, GA 는 `|컨트롤 Yaw − 액터 Yaw| < 임계(10°)` 가 될 때까지 발사를 미룬다(타임아웃 0.3초). 턴 중 제자리 회전과도 자연스럽게 맞물린다(액터 Yaw 델타가 틱마다 작아져 RootYawOffset 누적 → 턴 클립) (b) GA 의 기존 **Facing 워프**(`FacingWarpTargetName="RangedAttack.Facing"`, `FireMontage` 의 MotionWarping 밴드·발사 노티파이 검증 `ValidateFacingWarpBand`)를 쓴다 — FireMontage 를 저작(UpperBody 슬롯!)하고 밴드 뒤에 발사 노티파이를 두면 몸 회전이 끝난 뒤 발사된다. 근접 GA 가 이미 같은 틀 (c) 임시: 카메라와 몸이 90° 이상 어긋나면 첫 발은 회전만 하고 발사하지 않음 |

셋 다 애니/GA 레이어 수정이고 도구는 그대로 쓴다. 3 은 GA·MovementComponent(C++) + 몽타주 저작(콘텐츠) 이 핵심이라 범위가 가장 크다.

## 1. 지금까지 한 것 (요약, 시간순)

1. **히어로 전투 ABP** (10-19): Lyra 식 Linked Anim Layer — `ALI_HeroCombat`(Locomotion_Idle · Locomotion_Move · Aim_UpperBody) · 베이스 `ABP_Hero_Combat`(부모 `UAstralAnimInstance`, 운영 `ABP_Hero_Base` 의 상태머신 1:1, 기본 구현 = 근접) · 공급자 `ABP_HeroLayers_Rifle`. 런타임: `UAstralGE_RangedAimHold`(State.Ranged.Aiming, 발사마다 2초) · `bIsAiming/AimYaw/AimPitch` · 회전 모드 전환 · 장비 계열 `AnimLayerClass` 링크. 사용자 PIE 확인 완료.
2. **제자리 회전** (10-20 낮): 순수 계산 `FAstralTurnInPlaceState` + `UAstralAnimInstance` 출력 + `GetMainAnimInstance()`; 베이스 `RotateRootBone(Yaw←RootYawOffset)`; 공급자 조준 Idle 가지에 상태머신 **IdleTurn**(Idle → Rotation(BlendListByEnum ← TurnInPlaceKind, 클립 4) → Recovery(StartPosition ← TurnInPlaceAnimTime) → 자동 Idle; Recovery → Rotation 재진입), 전이 4개 **Inertialization**; 턴 클립 `AS_Vesper_Rifle_Turn{Left,Right}_{90,180}` 스켈레톤 A 재할당 + `/Game/Animation/Hero/Vesper/Rifle/TurnInPlace/`.
3. **사용자 1차 보고 수정**(상체 접힘·휙·180° 뒤집힘): 커브 재진입 가짜 델타(`NewClipTolerance`) · 누적 합 정규화 뒤집힘 제거 · 클램프 120→150(180 클립 선택 가능) · Rotation/Recovery 상체 LayeredBoneBlend(spine_01, 메시 공간, 커브 UseBasePose) · 플러그인 허용 목록 `LogicType`·`bIgnoreForRelevancyTest`.
4. **사용자 2차 보고 수정**(팔 자세): 진짜 원인 = **AimOffset 기준 포즈**. AO 9샘플은 `AS_Vesper_Rifle_AimIdle` 프레임 0 기준 저작(CC 와 0.0°)인데 기준이 총 내린 `AS_Vesper_Rifle_Idle` → 델타 거대 → Yaw 30~85 에서 두 손이 붙음(23→6cm). 수정: 9샘플 재기준 + 조준 중 상체 전부 AimingIdle(IdleTurn Idle · Rotation/Recovery 기본·상체 · **Move strafe 가지에도 LBB**). 비조준 가지(Rifle_Idle·Jog)는 그대로. 프로브: 손 거리 23 유지.
5. 별도 세션: `get_anim_graph_structure` 전이에 `logic_type` 추가(미커밋, 같은 체크아웃).

## 2. 현재 구조 (그래프 · 코드)

```
ABP_Hero_Combat (베이스) 루트: SM Locomotions(Idle/Move 상태 = LinkedAnimLayer) → DefaultSlot → FullBody 캐시 → UpperBody 슬롯 → LayeredBoneBlend(spine_01)
                               → LinkedAnimLayer Aim_UpperBody → RotateRootBone(Yaw ← RootYawOffset) → Inertialization → Output
                               (2026-10-21 순서 교정: AO 가산은 루트 회전 전 — hero-combat-abp.md §7 "AO 순서")
ABP_HeroLayers_Rifle (공급자)
  Locomotion_Idle: BlendListByBool(bIsAiming)  true(BlendPose_0!) = SM IdleTurn  /  false = AS_Vesper_Rifle_Idle
     IdleTurn: Idle(AS_Vesper_Rifle_AimIdle) ─GetMainAnimInstance.bWantsTurnInPlace→ TurnInPlaceRotation ─bTurnInPlaceRotationFinished→ TurnInPlaceRecovery ─자동→ Idle, Recovery ─bWants→ Rotation
       Rotation/Recovery 포즈: BlendListByEnum(EAstralTurnInPlaceKind ← GetMainAnimInstance.TurnInPlaceKind; 기본 AimingIdle, Left90/Left180/Right90/Right180 = MF 클립, Recovery 는 StartPosition ← TurnInPlaceAnimTime)
                              → LayeredBoneBlend(BasePose=턴 클립, BlendPoses_0=AimingIdle, spine_01 depth 0, 메시 공간, CurveBlendOption=UseBasePose) → StateResult
       전이 4개 LogicType=Inertialization, Crossfade 0.2, Rotation 은 bAlwaysResetOnEntry
  Locomotion_Move: BlendListByBool(bIsAiming) true = BS_Vesper_Rifle_Strafe(Direction,Speed) → LayeredBoneBlend(상체 AimingIdle) / false = BS_Vesper_Rifle_Jog(Speed)
  Aim_UpperBody: InPose → AimOffset AO_Vesper_Rifle(X←AimYaw, Y←AimPitch, Alpha bool←bIsAiming)
                 → LayeredBoneBlend(hand_l 이하 ← AimingIdle 손가락) → L2C → CopyBone(hand_r→ik_hand_gun) → ModifyBone(ik_hand_l ← 무기 파지점) → TwoBoneIK(hand_l → ik_hand_l) → C2L   (2026-10-21 왼손 IK 2판, 파지점 = 총 소켓 LeftHandIK · 장비 매니저가 이벤트로 넣음)
```
- C++: `Source/AstralBreak/Animation/AstralTurnInPlace.{h,cpp}`(Settings: Clamp 150 · TurnThreshold 50 · Turn180Threshold 135 · 스프링 80/1 · AnimActiveWeightThreshold 0.001 · RotationFinishedTolerance 1 · NewClipTolerance 2; Update 순서: 커브 처리(가중 해제 rem/w, 새 클립 감지 시 델타 버림) → 누적(델타만 정규화, 합은 클램프) 또는 스프링 복귀 → 클램프 → wants·Kind 래치(상승 에지)) · `AstralAnimInstance.{h,cpp}`(스냅샷 YawDelta·전신 몽타주 슬롯 가중치 · 누적 조건 = 조준∧지상∧Speed<10∧입력 없음∧전신 몽타주 없음 · 출력 RootYawOffset/bWantsTurnInPlace/bTurnInPlaceRotationFinished/TurnInPlaceKind/TurnInPlaceAnimTime + 디버그 TurnYawCurveValue/TurnInPlaceDebugWeight/Remaining/bTurnInPlaceAccumulating · `AimYaw = NormalizeAxis(AimDelta.Yaw − RootYawOffset)` · `GetMainAnimInstance()` BlueprintThreadSafe) · 테스트 `Tests/AstralTurnInPlaceTests.cpp` 4개.
- 플러그인: `Core/AnimMcpPropertyRules.cpp` 전이 `LogicType`, 플레이어 `bIgnoreForRelevancyTest`; `Core/AnimMcpGraphInspector.cpp` 전이 `logic_type`(별도 세션).
- 스크립트: `Tools/mcp/build_hero_turninplace.py`(제자리 패치·멱등: A 베이스 RRB · B 공급자 SM · B2 상체 LBB · A0 AO 기준·조준 상체 · C 검증; `--verify-only`) · `build_hero_combat.py`(처음부터 생성, 끝에 patch 호출) · `Tools/scripts/pie_aim_probe.py`(ue_exec 단계 begin/arm/fire/turn/spin/aim/record/dump/sample/end) + 드라이버 `pie_turn_probe_run.py [yaw] [sec] [extra_turns] [interval] [spin]` · `pie_ao_probe_run.py` · `Tools/scripts/setup/hero_abp_move_turn_assets.py`.

## 3. 작업 절차 (이 프로젝트의 관례)

- 에디터는 세션이 띄우고 내린다(사용자 Rider 에디터가 떠 있으면 DLL 잠김 — `tasklist | findstr UnrealEditor` 로 먼저 확인, 더티 0 이면 `quit_editor`):
  `UnrealEditor.exe <uproject> -log -unattended`(**백그라운드 CPU 스로틀 해제 — 없으면 PIE 가 6~10Hz**) → `Tools/mcp/.venv/Scripts/python.exe Tools/mcp/wait_for_bridge.py 540 10` → 25초 대기 → 작업 → `quit_editor`.
- C++ 수정 → 에디터 내리고 **Development·DebugGame 둘 다** `Build.bat AstralBreakEditor Win64 <cfg> -Project=... -WaitMutex -NoHotReload`(경고 0 확인) → 재기동.
- 그래프는 MCP Tool(`apply_graph_operations` 등)로만, 멱등 스크립트에 누적. 검증은 `build_hero_turninplace.py --verify-only`(구조 · 스모크 · 단위 4/4 · PIE Idle). PIE 실측은 `pie_turn_probe_run.py 90 6.0 3 0.9 spin`(점진 회전 4회) — 출력 `PIE_JUMP`(액터 안 돈 프레임 사이 오프셋 최대 변화) · `PIE_HANDS`(두 손 최대 거리, 정상 23) · `PIE_LINK`(링크 인스턴스 변화) · `PIE_S`(틱 샘플).
- Git Bash 에서 `/Game/...` 인자는 `MSYS_NO_PATHCONV=1`, 한글 출력 `PYTHONIOENCODING=utf-8`. `Saved/`(로그) 는 권한상 읽을 수 없다.

## 4. 실측 함정 (반드시 피할 것)

- `AnimInstance.call_method("GetCurrentStateName", ...)` 를 파이썬 PIE 에서 부르면 **에디터 크래시**(3회) — 상태 이름은 읽지 않는다. 값(kind/wants/fin/animT/curve)으로 판단.
- UE ExecuteFile 원격 실행: 스크립트 소스 앞부분(주석 포함)에 ".py" 가 있으면 경로로 오인 — 주석에 확장자 금지.
- 조회 응답의 핀 바인딩은 `pins[]` 가 아니라 `optional_pins[].bound/binding{path}`; 상태 그래프 출력 노드는 `AnimGraphNode_StateResult`.
- LayeredBoneBlend 는 기본 `CurveBlendOption=Override` 라 상체 레이어가 커브를 지운다 → 턴 클립 커브(TurnYawWeight·RemainingTurnYaw, 소문자 이름이지만 FName 비교 무시)는 `UseBasePose`.
- 자동 전이는 상태 안 "가중치 최대 플레이어" 의 남은 시간 → 보조 Idle 플레이어는 `bIgnoreForRelevancyTest`.
- 턴 클립 커브: `TurnYawWeight` 는 처음 ~0.6초만 1(회전 구간), 그 뒤 0 — Recovery 에서 커브 0 은 정상. Right 는 Remaining +90→0, Left 는 −180→0(부호 다름; C++ 은 `-=(cur−prev)`·`|·|` 로 양쪽 처리).
- 표준 크로스페이드로 클립↔클립 전이를 하면 두 커브가 가중 합산돼 가짜 델타 → 전이는 Inertialization. 관성 블렌드는 커브도 0→1 로 블렌드하지만 Remaining 도 같은 비율이라 가중 해제 값은 정확.
- 파이썬 PIE(-unattended 아님)에선 `PlayerTick→UpdateRotation` 이 액터를 안 돌린 적이 있다 → 프로브는 액터 Yaw 도 직접 돌린다. `-unattended` 에선 돌았다.
- AimHold 는 발사마다 2초 — 프로브는 0.6초마다 `fire` 로 유지.
- `EditorPerformanceSettings` CDO 를 바꿔도 스로틀은 안 풀렸다 → `-unattended`.

## 5. 미커밋 파일 (커밋은 사용자; 핸드오프 §13 세 번째 묶음 + logic_type 세션 분)

C++ `Animation/AstralTurnInPlace.{h,cpp}` · `Animation/AstralAnimInstance.{h,cpp}` · `Tests/AstralTurnInPlaceTests.cpp` · 플러그인 `AnimMcpPropertyRules.cpp` · `AnimMcpGraphInspector.{h,cpp}` · README 2종 · `Tools/mcp/{build_hero_turninplace.py, build_hero_combat.py, anim_graph_mcp/server.py, phase4_test.py}` · `Tools/scripts/{pie_aim_probe.py, pie_turn_probe_run.py, pie_ao_probe_run.py, setup/hero_abp_move_turn_assets.py}` · 콘텐츠 `ABP_Hero_Combat` · `ABP_HeroLayers_Rifle` · `Anims/TurnInPlace/MF_*` ×4(이동) · `AS_Hero_AO_Rifle*` ×9(기준 포즈) · `Animation/Test/ABP_McpTest` · 문서 `.claude/plans/{hero-combat-abp.md, animbp-automation-handoff-phase6-2.md, animbp-automation-phase1.md, turninplace-handoff.md}`.
