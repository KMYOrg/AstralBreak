#pragma once

#include "NativeGameplayTags.h"

namespace AstralGameplayTags
{
	/**
	 * GameplayEvent
	 */

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_Hit);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_Death);

	// 콤보 입력 윈도우 — GameplayEventWindow NotifyState로 섹션별 1개 배치 (Begin=WindowOpen, End=Branch)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_ComboWindowOpen);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(GameplayEvent_ComboBranch);
}
