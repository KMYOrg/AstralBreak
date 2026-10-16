# Phase 5 — ABP_Hero_McpBuild vs ABP_Hero_Base 구조 비교

> 생성 `Tools/mcp/phase5_build_hero.py` · 빌드 애셋 `/Game/Animation/Hero/ABP_Hero_McpBuild` (revision `sha1:222ac9e449c20cb3d57ae66a0b36407a2a79708e`) · 운영 애셋 `/Game/Animation/Hero/ABP_Hero_Base` (revision `sha1:3c146b5f04c1648922feca885ba1eb8a0a52e118`, 읽기만)
> 빌드 애셋은 도구(apply_graph_operations)만으로 빈 AnimBP 에서 구성했다. 운영 애셋은 사람이 만든 것이며 변경하지 않았다.

## 1. 수치

| | 운영 | 빌드 |
| :--- | ---: | ---: |
| 그래프 | 21 | 21 |
| 노드 | 74 | 88 |
| 연결 | 54 | 54 |
| 상태 (alias·conduit 포함) | 11 | 11 |
| 전이 | 12 | 12 |

## 2. 루트 그래프 (Output Pose 에서 거슬러 올라감)

- 운영: `Root ← Inertialization ← LayeredBoneBlend[LayerSetup=[{"BranchFilters": [{"BoneName": "spine_01", "BlendDepth": 0}]}]] ← UseCachedPose`
- 빌드: `Root ← Inertialization ← LayeredBoneBlend[LayerSetup=[{"BranchFilters": [{"BoneName": "spine_01", "BlendDepth": 0}]}]] ← UseCachedPose`

빌드는 전신 슬롯(`DefaultSlot`) **출력**을 SaveCachedPose `FullBody` 로 캐시해 BasePose 와 상체 슬롯(`UpperBody`) 두 갈래로 나눈 뒤 LayeredBoneBlend(`spine_01` 이하, 메시 공간 회전 블렌드)로 합친다. 상체 슬롯이 비어 있으면 전신 슬롯 출력(몽타주 포함)이 그대로 통과해 블렌드가 항등이다 — 상체 슬롯을 전신 슬롯과 나란히 두면 전신 몽타주의 상체가 로코모션으로 덮인다(2026-10-16 PIE 실측). 몽타주 5개는 전부 DefaultSlot 을 쓰므로 UpperBody 슬롯은 몽타주 슬롯을 바꾸기 전까지 비어 있다(콘텐츠 작업). 운영 애셋에도 같은 레이어가 적용돼 있다(§5).

## 3. 상태머신 — 운영 `Locomotions` / 빌드 `Locomotions`

| 상태 | 운영 | 빌드 |
| :--- | :--- | :--- |
| Idle | state: SequencePlayer(AS_Idle) | state: SequencePlayer(AS_Idle) |
| Move | state: BlendSpacePlayer(BS_Hero_Locomotion1D), K2Node_VariableGet | state: K2Node_VariableGet, BlendSpacePlayer(BS_Hero_Locomotion1D) |
| JumpSources | alias: — | alias: — |
| JumpSelector | conduit: TransitionResult | conduit: TransitionResult, EdGraphNode_Comment |
| JumpStart | state: SequencePlayer(AS_Hero_Jump) | state: SequencePlayer(AS_Hero_Jump) |
| FallLoop | state: SequencePlayer(AS_Hero_FallLoop) | state: SequencePlayer(AS_Hero_FallLoop) |
| FallLand | state: SequencePlayer(AS_Hero_Land) | state: SequencePlayer(AS_Hero_Land) |
| EndInAir | conduit: TransitionResult | conduit: TransitionResult, EdGraphNode_Comment |
| JumpFallInterruptSources | alias: — | alias: — |
| IdleAlias | alias: — | alias: — |
| MoveAlias | alias: — | alias: — |

### 전이 — 운영

| from | to | 규칙 | xfade | prio |
| :--- | :--- | :--- | ---: | ---: |
| Idle | Move | Get bHasMovementInput | 0.25 | 1 |
| Move | Idle | Get bHasMovementInput · NOT Boolean · AND Boolean · Get Speed · float < float(B=10.000000) | 0.3 | 1 |
| JumpSources | JumpSelector | (노드 없음 → Result 기본값 true) | 0.2 | 1 |
| JumpSelector | JumpStart | Get bIsJumping | 0.2 | 1 |
| JumpSelector | FallLoop | Get bIsFalling | 0.2 | 2 |
| JumpStart | FallLoop | automatic | 0.2 | 1 |
| FallLoop | FallLand | Get GroundDistance · float < float(B=25.000000) | 0.2 | 1 |
| FallLand | EndInAir | automatic | 0.2 | 1 |
| FallLand | EndInAir | Get bIsOnGround | 0.2 | 1 |
| JumpFallInterruptSources | EndInAir | Get bIsOnGround | 0.2 | 1 |
| EndInAir | IdleAlias | Get Speed · float >= float(B=20.000000) | 0.2 | 1 |
| EndInAir | MoveAlias | Get Speed · float < float(B=20.000000) | 0.2 | 1 |

### 전이 — 빌드 (규칙은 도구 AST 원문)

| from | to | 규칙 | xfade | prio |
| :--- | :--- | :--- | ---: | ---: |
| Idle | Move | `{"var": "bHasMovementInput"}` | 0.25 | 1 |
| Move | Idle | `{"and": [{"not": {"var": "bHasMovementInput"}}, {"compare": {"op": "<", "left": {"var": "Speed"}, "right": {"literal": 10}}}]}` | 0.3 | 1 |
| JumpSources | JumpSelector | `{"literal": true}` | 0.2 | 1 |
| JumpSelector | JumpStart | `{"var": "bIsJumping"}` | 0.2 | 1 |
| JumpSelector | FallLoop | `{"var": "bIsFalling"}` | 0.2 | 2 |
| JumpStart | FallLoop | `automatic` | 0.2 | 1 |
| FallLoop | FallLand | `{"compare": {"op": "<", "left": {"var": "GroundDistance"}, "right": {"literal": 25}}}` | 0.2 | 1 |
| FallLand | EndInAir | `automatic` | 0.2 | 1 |
| FallLand | EndInAir | `{"var": "bIsOnGround"}` | 0.2 | 1 |
| JumpFallInterruptSources | EndInAir | `{"var": "bIsOnGround"}` | 0.2 | 1 |
| EndInAir | IdleAlias | `{"compare": {"op": ">=", "left": {"var": "Speed"}, "right": {"literal": 20}}}` | 0.2 | 1 |
| EndInAir | MoveAlias | `{"compare": {"op": "<", "left": {"var": "Speed"}, "right": {"literal": 20}}}` | 0.2 | 1 |

## 4. 의도한 차이

1. **상태머신은 운영과 1:1** (Phase 6-1) — 상태 5 · conduit 2 · alias 4 · 전이 12 · 이름 `Locomotions` · 상태 내부까지 배치 하나로. 운영의 전이 규칙은 사람이 만든 K2 노드, 빌드는 도구 AST(rule_source) 라는 차이만 있다.
2. **UpperBody 레이어** — §2. 운영 애셋에도 적용돼 있다(§5) (Slot `UpperBody` + LayeredBoneBlend LayerSetup `spine_01`).
3. **Move 상태의 Speed 바인딩** — 운영과 같이 K2 VariableGet → BlendSpacePlayer.X 핀 연결 (Property Binding 아님).
4. **Inertialization** — 운영과 같이 루트 끝에 둔다. 허용 목록 프로퍼티는 없고 기본값 그대로.

## 5. 운영 애셋 적용 상태

- §4-3 UpperBody 레이어는 2026-10-16 사용자 승인으로 운영 애셋에 적용됐다 (Locomotion·Jump 는 운영에 이미 있음). 첫 적용은 상체 슬롯을 전신 슬롯과 나란히 둬 공격 몽타주 상체가 깨졌고, 같은 날 전신 슬롯 뒤 `FullBody` 캐시 배선으로 재적용했다. 운영 루트 사슬은 §2 참조. PIE 확인은 사용자가 한다.
- 운영 애셋 관찰: `EndInAir → IdleAlias` 규칙이 `Speed >= 20`, `EndInAir → MoveAlias` 가 `Speed < 20` 으로 읽힌다(덤프 기준). 의도가 반대라면 사람이 고칠 항목 — 도구는 건드리지 않았다.
