#pragma once

#include "NativeGameplayTags.h"

namespace AstralGameplayTags
{
	/**
	 * Move
	 */
	
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(InputTag_Move);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(InputTag_Look_Mouse);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(InputTag_Look_Stick);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(InputTag_AutoRun);

	/**
	 * Combat
	 */
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(InputTag_Attack_Basic);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(InputTag_SwitchCombatStyle);
}
