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
}
