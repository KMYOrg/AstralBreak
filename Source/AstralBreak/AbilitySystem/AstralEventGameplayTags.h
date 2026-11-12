#pragma once

#include "NativeGameplayTags.h"

namespace AstralGameplayTags
{
	/**
	 * GameplayEvent
	 */
	
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_Damaged);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_Death);

	// 콤보 입력 윈도우 — GameplayEventWindow NotifyState로 섹션별 1개 배치 (Begin=WindowOpen, End=Branch)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_ComboWindowOpen);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_ComboBranch);

	// 무기 트레이스 밴드 — GameplayEventWindow NotifyState로 스윙 구간에 배치 (Begin=태스크 시작, End=종료)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_WeaponTrace_Begin);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_WeaponTrace_End);

	// 방어 판정 결과 — ResolveIncomingDamage(서버)가 발송, GA가 수신해 보상/비용 처리
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_Parried);   // 방어자에게 — 패링 성공 (magnitude = 무효화한 데미지)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_Guarded);   // 방어자에게 — 가드 성공 (magnitude = 막은 양)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_Staggered); // 공격자에게 — 패링당해 경직

	// 입력 활성화에 초기 데이터(MakeActivationEventData)를 실어 보낼 때의 이벤트 태그 — ASC가 TriggerAbilityFromGameplayEvent(SpecHandle 지정)에 쓴다.
	// 엔진은 이 태그를 EventTag에 스탬프만 하고 라우팅하지 않는다. 데이터 종류(Facing 등)는 구체 GA가 정의하므로 태그는 의미를 갖지 않는다
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_ActivateFromInput);

	// 원거리 발사 시점 — FireMontage의 단발 UAstralAnimNotify_GameplayEvent (0초에 두지 않는다 — 엔진 추출 조건상 첫 틱에 누락된다)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_Ranged_Fire);

	// 적 근접 공격의 타격 시점 — 공격 몽타주의 단발 UAstralAnimNotify_GameplayEvent. 한 몽타주에 여러 개면 연타다 (0초에 두지 않는다 — 위와 같은 이유).
	// WeaponTrace.Begin / End 는 구간이고 이것은 한 시점이다
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_Enemy_AttackHit);

	// 적 근접 공격의 휘두름 시작 — 공격 몽타주의 단발 노티파이(선택). 받으면 공격 GA 가 재생 속도를 SwingPlayRate 로 바꾼다:
	// 준비 동작만 느리게(= 예고), 휘두름은 원래 속도로 (m3-enemy-ai.md §10 C2 ③)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_Enemy_AttackSwing);

	/**
	 * AI.Event — 적 컨트롤러가 자기 StateTree 에 보내는 이벤트 (SendStateTreeEvent). ASC 의 GameplayEvent 와 다른 경로다
	 */

	// 쫓던 타깃이 죽거나 사라졌다 — AAstralEnemyController 가 타깃을 비운 뒤 보낸다
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(AIEvent_TargetLost);

	// 현재 타깃이 아닌 후보에게 맞았다 — AAstralEnemyController 가 '다시 뽑기' 를 표시한 뒤 보낸다. Chase 만 받아 Acquire 로 간다
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(AIEvent_Retarget);

	// 폰에 State.Enemy.Staggered 가 붙었다(피격 반응 · 경직) — AAstralEnemyController 가 태그 이벤트를 받아 보낸다. Root 가 받아 Stagger 로 간다
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(AIEvent_Staggered);
}
