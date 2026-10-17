# AnimBP 자동화 — Phase 7 후속 로드맵 (캐릭터·적 애니메이션 자동화를 위해 남은 것)

> 작성 2026-10-17 · 브랜치 `feat/ai_auto_ABP` · Phase 1~6 종료 시점
> 기준 문서: [animbp-automation-handoff-phase6-2.md](animbp-automation-handoff-phase6-2.md)(현재 상태·작업 규칙) · [animbp-automation-phase1.md](animbp-automation-phase1.md)(근거) · `Plugins/AnimGraphMcp/README.md`(Tool·op 참조)
> 이 문서는 "다음에 무엇을 더 만들면 캐릭터·적 AnimBP 를 사람 손 없이 끝까지 만들 수 있나" 에 대한 답이다. 항목마다 **왜 필요한가(캐릭터/적 관점) · 범위 · 엔진에서 확인할 것 · 테스트 · 규모** 를 적었다. 착수 순서는 사용자가 고른다.

---

## 0. 지금 할 수 있는 것과 없는 것 (캐릭터·적 하나를 만든다고 할 때)

| 단계 | 지금 | 비고 |
| :--- | :---: | :--- |
| 스켈레톤·애니 애셋 목록 파악 | ✅ | `list_animation_assets {skeleton, details}` |
| ABP 생성(부모 클래스·스켈레톤·프리뷰 메시) | ✅ | `create_animation_blueprint` |
| 로코모션 BlendSpace 생성 | ✅ | `create_blendspace` 1D/2D (AimOffset 은 ❌ → §3) |
| 루트 그래프(캐시·슬롯·레이어드 블렌드·블렌드 리스트) | ✅ | op 사전 |
| 상태머신(상태·전이·규칙·conduit·alias) | ✅ | 운영 애셋 1:1 재현 실증 |
| 전이 규칙의 조건 변수 | 🔶 | **C++ AnimInstance 변수만**(`var`·`bind_pin`). BP 변수 추가 ❌ → §1 |
| Lyra 식 레이어(인터페이스·구현·레이어 노드) | ✅ | 포즈 입력만. 값 파라미터 ❌ → §4 |
| 공격·피격 몽타주와 슬롯 | 🔶 | 슬롯 노드는 ✅, **몽타주·노티파이·스켈레톤 슬롯 생성 ❌** → §3 |
| IK·본 수정·Additive·Mirror 노드 설정 | 🔶 | 생성·연결 ✅, **세부 설정 ❌**(허용 목록 밖) → §2 |
| 컴파일·구조 검증 | ✅ | `compile` + `run_automation_tests "AnimGraphMcp.Smoke"` |
| 실제 포즈가 맞는지 | ❌ | 사람이 PIE 로 → §5 |
| 적마다 다른 스켈레톤 | 🔶 | 도구는 스켈레톤 무관. **리타게팅은 범위 밖**(IK Retargeter 는 별도 에디터 기능) |

결론: **구조는 도구만으로 세울 수 있고, "조건 변수 · 공격 콘텐츠 · 세부 노드 설정 · 런타임 확인" 네 곳에서 사람이 남는다.** 아래 §1~§5 가 그 네 곳을 메우는 순서다.

---

## 1. ABP 변수 · EventGraph 최소 지원 ← 가장 큰 구멍

**왜** — 적 AI 는 `bIsAttacking`·`bIsStunned`·`TargetDistance` 같은 변수를 AnimBP 에 넘겨야 하고, 지금은 그 변수를 **적 종류마다 C++ AnimInstance 서브클래스에 추가**해야 규칙 `var` 와 `bind_pin` 이 쓸 수 있다. BP 변수를 도구가 만들 수 있으면 C++ 변경 없이 적 ABP 하나가 닫힌다. 프로젝트 정책("복잡 조건은 C++ 에서 bool 로")은 유지하되, 단순 변수·단순 계산까지는 BP 에서 허용하는 것이 목표.

**범위**
- Tool `add_blueprint_variable {asset_path, name, type(bool|float|int|name|vector|object:<class>), default?, category?, exposed?}` · `remove_blueprint_variable`. 조회 `variables[]` 에 `source:"blueprint"|"native"` 구분.
- op `add_node class:"K2Node_VariableGet"` 이 BP 변수도 받게(지금은 SkeletonGeneratedClass 의 네이티브 변수 기준 — 컴파일 전 BP 변수는 `NewVariables[]` 에만 있으므로 해석 경로 추가).
- **`BlueprintThreadSafeUpdateAnimation` 함수 그래프 편집(최소)**: op `set_variable_from_property_access {variable, path}` — Property Access 노드(`UK2Node_PropertyAccess`) + `VariableSet`. 이것만으로 "Pawn 의 속도/가속도를 매 프레임 ABP 변수로" 가 된다. 임의 K2 노드 편집은 범위 밖(규칙 AST 와 같은 화이트리스트 철학).

**엔진 확인** — `FBlueprintEditorUtils::AddMemberVariable`(BlueprintEditorUtils.cpp, `NewVariables`), `FEdGraphPinType` 조립, `UAnimBlueprint` 의 ThreadSafe 함수 생성(`FBlueprintEditorUtils::CreateNewGraph` + `UAnimationBlueprintLibrary`? 또는 Persona 의 "Create Thread Safe Update Animation" 경로 — `AnimBlueprintCompiler` 의 `MD_ThreadSafe` 메타), `UK2Node_PropertyAccess`(Editor/AnimGraph? → BlueprintGraph `K2Node_PropertyAccess.h`) 의 경로 설정 API(`IPropertyAccessEditor`, 6-4a 에서 이미 사용). 규칙 그래프처럼 **주석에 원문 기록 → 멱등·사람 편집 감지** 재사용.

**테스트** — `phase7_1_test.py`: 변수 3종 추가 → 규칙 `var` 로 사용 → 컴파일 0 에러 → recheck 에서 변수 유지 · 중복 이름·예약어 거부 · 삭제 시 참조 중이면 거부.

**규모** — 중(Tool 2 + op 2 + Inspector, 엔진 조사 반나절).

---

## 2. `set_property` 허용 목록 확장 + 노드별 실측

**왜** — 적·캐릭터 ABP 에 실제로 들어가는 노드 중 설정이 막힌 것: **AimOffset 플레이어**(조준), **TwoBoneIK·ModifyBone**(무기 손 위치·시선), **ApplyAdditive**(피격 반응), **Mirror**, **Inertialization 의 BlendProfile**, **BlendListByBool/Enum 의 BlendProfile**, **SequenceEvaluator**(공격 타이밍 제어). 생성은 되지만 본 이름·공간·알파 같은 값을 못 넣는다.

**범위** — `Core/AnimMcpPropertyRules.cpp` 허용 목록에 노드별 항목 추가 + 값 타입 검증(본 이름은 TargetSkeleton 존재 확인, 공간 enum, `FBoneReference` 구조체, `FBlendProfile*` 애셋 참조). 노드 목록(우선순위): RotationOffsetBlendSpace(AimOffset) · SequenceEvaluator · ApplyAdditive · TwoBoneIK · ModifyBone · Mirror · Inertialization(BlendProfile) · BlendListByBool/Enum(BlendProfile) · LayeredBoneBlend(BlendProfile 이미 일부). 각 노드는 **엔진 Setter 가 있으면 Setter, 없으면 리플렉션**(기존 원칙 ①②③).

**엔진 확인** — 노드 헤더의 `UPROPERTY(EditAnywhere)` 와 `FAnimNode_*` 멤버(`Editor/AnimGraph/Public/AnimGraphNode_*.h`, `Runtime/AnimGraphRuntime/Public/BoneControllers/AnimNode_*.h`), `FBoneReference::Initialize`(본 인덱스 캐시), `PostEditChangeProperty` 가 핀을 재구성하는 노드(`bEnableDebugDraw` 등 제외).

**테스트** — `phase7_2_test.py`: 노드마다 생성 → 설정 → 컴파일 0 에러 → 재조회 값 일치 → 잘못된 본 이름 거부. 운영 애셋이 아닌 테스트 ABP.

**규모** — 중(노드 하나당 1~2시간, 전부 하면 2일).

---

## 3. 콘텐츠 애셋 — AimOffset · 몽타주 슬롯/섹션 · 스켈레톤 슬롯 (기존 Python 몽타주 파이프라인은 유지)

**이미 있는 것 (2026-10-17 확인)** — 몽타주·노티파이는 이 프로젝트에 **별도의 검증된 파이프라인**이 있다: `Tools/lib/ab_montage.py`(에디터 안 Python, `unreal.AnimationLibrary`) + JSON 스펙(`Tools/data/montages.json`·`facing_warp.json`·`input_facing.json`·`pawn_collision.json`) + `Tools/scripts/build_montages.py`·`lockon_apply_*.py` 를 `Tools/ue_exec.py`(Python 원격 실행)로 돌린다. 몽타주 생성·블렌드·노티파이/노티파이 스테이트·트랙·프로젝트 전용 클래스(GameplayEvent 창·MotionWarping·PawnCollisionPolicy·InputFacing 의 modifier 서브오브젝트 설정)·멱등 재적용·덤프 검증까지 된다. **이것을 MCP 로 다시 만들지 않는다** — 노티파이 클래스와 modifier 설정은 프로젝트 고유라 범용 플러그인에 넣으면 6-6 의 범용화와 충돌하고, Python 쪽이 이미 실측 검증돼 있다.

**Python 이 못 하는 것 두 가지(`ab_montage.py` 머리말의 제약)** — 이것만 C++ Tool 로 메운다:
- **슬롯 이름 변경 불가**(`slot_anim_tracks` 미노출 → 몽타주가 전부 `DefaultSlot`). Phase 5 에서 ABP 에 `UpperBody` 슬롯을 만들고도 공격 몽타주가 전신 슬롯에 남은 이유가 이것이다.
- **다중 섹션 불가**(`composite_sections` 미노출 → 몽타주 1개당 1섹션). 콤보 섹션 점프·루프 섹션을 못 만든다.

**범위**
- `set_montage_slots {asset_path, slots:[{index?, slot}]}` — `UAnimMontage::SlotAnimTracks[i].SlotName`(스켈레톤에 슬롯이 없으면 거부 또는 `add_skeleton_slot` 선행) + `PostEditChange` + 더티.
- `set_montage_sections {asset_path, sections:[{name, start, next?}]}` — `AddAnimCompositeSection(이름, 시작)`(`AnimMontage.h:898`) + `CompositeSections[i].NextSectionName`(루프·체인) + 기존 섹션 정리.
- `add_skeleton_slot {skeleton, group, slot}` — `USkeleton::AddSlotGroupName`·`SetSlotGroupName`·`ContainsSlotName`(`Skeleton.h:558-565`). 스켈레톤 수정이므로 보호 목록·`confirm` 대상.
- `create_aim_offset {asset_path, skeleton, axes, samples}` — `UAimOffsetBlendSpaceFactoryNew`/`…Factory1D` 는 BlendSpace 팩토리 파생이라 6-3 재사용(샘플은 Mesh-space additive 검증).
- 싱크 그룹: 애셋 플레이어 노드의 `SyncGroup` 은 §2 허용 목록으로, 몽타주의 `SyncGroup` 은 Python 이 이미 설정.

**흐름** — JSON 스펙 → `ue_exec.py build_montages.py`(생성·노티파이) → MCP `set_montage_slots`/`set_montage_sections`(슬롯·섹션) → ABP 슬롯 노드와 이름 대조(스모크 확장: 몽타주 슬롯이 스켈레톤과 ABP 에 존재하는지). 원하면 `build_montages.py` 가 끝에 MCP 를 호출하도록 한 줄 이어 붙여 한 명령으로 만든다.

**테스트** — `phase7_3_test.py`: 테스트 몽타주(Python 파이프라인으로 생성) → 슬롯을 `UpperBody` 로 → 섹션 2 + Next 체인 → 재조회 일치 → 스켈레톤에 없는 슬롯 거부.

**규모** — 소~중(Tool 3~4개, 구조체 직접 채우기. 하루).

---

## 4. Linked Layer 값 파라미터 · InstanceClass · 인터페이스 레이어 추가/삭제

**왜** — Lyra 식으로 무기/적 타입마다 레이어 ABP 를 바꿔 끼우려면 **InstanceClass 지정**(기본 구현 ABP)과 **값 파라미터**(예: 레이어에 `AimYaw` 전달)가 필요하다. 지금은 포즈 입력만 되고 레이어 ABP 는 런타임 `LinkAnimClassLayers` 로만 바꾼다(C++).

**범위** — `create_anim_layer_interface.layers[].inputs[{name, type}]`(값 파라미터 = 함수 입력 파라미터), `add_node layer` 의 `instance_class`, `add_layer_to_interface`/`remove_layer_from_interface`(구현 ABP 들의 `ConformAnimGraphToInterface` 전파 확인), 자식 ABP 의 레이어 오버라이드.

**엔진 확인** — 6-4b 결과 절의 경로(`AnimGraphNode_LinkedAnimLayer.cpp`, `AnimationGraphSchema::ConformAnimGraphToInterface`), 값 파라미터는 함수 시그니처의 비-포즈 입력(`FAnimBlueprintFunction.InputProperties`), `UAnimGraphNode_LinkedAnimLayer::Node.InstanceClass` 설정 시 핀 재생성.

**규모** — 중.

---

## 5. 런타임 검증 — PIE 에서 실제 포즈·상태 확인

**왜** — 지금 검증은 "구조가 말이 되는가"까지다. "Idle 에서 Speed 를 300 으로 올리면 Run 상태로 가는가", "공격 몽타주가 상체만 덮는가" 는 사람이 PIE 로 본다. Phase 5 에서 배선 실수를 사람이 PIE 에서 발견한 것이 그 사례다.

**범위** — Automation 테스트 `AnimGraphMcp.Runtime.AnimBlueprint`(파라미터: ABP 경로 + 시나리오 JSON): PIE 시작(`FStartPIECommand`) → 스켈레탈 메시 액터 스폰 + ABP 할당 → 변수 세팅(§1 의 BP 변수 또는 네이티브 변수 리플렉션) → N 프레임 대기(지연 명령) → `UAnimInstance::GetCurrentStateName`·`GetInstanceCurrentStateElapsedTime`·슬롯 활성·특정 본의 컴포넌트 공간 트랜스폼 기대값 비교 → PIE 종료. 시나리오는 `run_automation_tests` 의 `filter` 로 고르거나 새 Tool `run_anim_scenario`. **6-5 에서 실측 못 한 지연 명령 경로·타임아웃이 여기서 검증된다.**

**엔진 확인** — `Runtime/Engine/Public/Tests/AutomationCommon.h`(`FStartPIECommand`·`FWaitLatentCommand`·`FEndPlayMapCommand`), `UAnimInstance` 의 상태 조회 API(`AnimInstance.h`: `GetCurrentStateName`, `IsSlotActive`, `Montage_IsPlaying`), `USkeletalMeshComponent::GetBoneTransform`. PIE 중엔 `StartTestByName` 이 거부되므로 **테스트가 PIE 를 열어야** 한다(바깥에서 PIE 를 켜 두면 안 됨).

**규모** — 대(지연 명령·PIE 수명 관리). Phase 6-5 의 러너가 그대로 쓰인다.

---

## 6. 두 번째 프로젝트 재현 (포트폴리오용, 독립)

6-6 에서 생략한 §12-D. README 절차대로 새 C++ 프로젝트에 `Plugins/AnimGraphMcp` + `Tools/mcp` + `.mcp.json` 을 넣고, 엔진 `Templates/TemplateResources/High/Characters/Content/Mannequins`(`SK_Mannequin`·`ABP_Unarmed`, 약 125MB)로 Phase 2.5 시나리오 + 스모크를 돌린다. 반나절.

---

## 7. 캐릭터·적 하나를 도구만으로 만드는 흐름 (§1~§3 뒤)

```text
① list_animation_assets {skeleton}                 애셋 파악
② create_blendspace / create_aim_offset (§3)       로코모션·조준
③ create_animation_blueprint                        ABP
④ add_blueprint_variable ×N (§1)                    bIsAttacking · TargetDistance …  (적 AI 가 쓰는 값)
⑤ set_variable_from_property_access (§1)            Speed ← Pawn 속도 (매 프레임)
⑥ implement_anim_layer_interface                    Lyra 식 레이어(공용 인터페이스 재사용)
⑦ apply_graph_operations                            루트 그래프 + 상태머신 + 규칙(var) + IK·Additive 설정(§2)   ← 배치 1~2개
⑧ create_anim_montage ×N (§3)                       공격·피격·사망 + 슬롯·노티파이
⑨ compile + save + run_automation_tests Smoke       구조 검증
⑩ run_automation_tests Runtime (§5)                 "Speed 300 → Run", "공격 중 상체 슬롯 활성"
```

사람이 남는 곳: 애니메이션 자체(리타게팅·클립 선택), 수치 튜닝(블렌드 시간·IK 알파), 최종 PIE 확인. **구조·배선·조건·콘텐츠 뼈대는 전부 도구 범위**가 된다.

---

## 8. 착수 규칙 (핸드오프 §9 그대로)

범위 정리 → 설계 선택지가 갈리면 코드 전 사용자 확정 → 엔진 소스로 API 확인(경로 기록) → 구현 → 두 구성 빌드(에디터 내리고) → `phase7_N_test.py`(새 Tool 은 HTTP 직접 호출) → `run_all.py` 에 추가 → ALL PASS → phase1 "Phase 7-N 결과" · 핸드오프 §1·§4·§6·§8·§9·§12·§13 · README 2종 · 메모리 → 변경 파일 목록과 커밋 메시지 초안(커밋은 사용자). 운영 애셋 `ABP_Hero_Base` 는 읽기만.
