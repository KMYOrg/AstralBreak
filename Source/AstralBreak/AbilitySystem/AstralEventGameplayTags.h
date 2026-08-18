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
}
