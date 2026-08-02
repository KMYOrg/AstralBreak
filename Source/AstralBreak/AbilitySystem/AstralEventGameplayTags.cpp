#include "AstralEventGameplayTags.h"

namespace AstralGameplayTags
{
	/**
	 * GameplayEvent
	 */
	
	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Hit, "GameplayEvent.Hit");
	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Death, "GameplayEvent.Death");

	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_ComboWindowOpen, "GameplayEvent.ComboWindowOpen");
	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_ComboBranch, "GameplayEvent.ComboBranch");

	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_WeaponTrace_Begin, "GameplayEvent.WeaponTrace.Begin");
	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_WeaponTrace_End, "GameplayEvent.WeaponTrace.End");

	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Parried, "GameplayEvent.Parried");
	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Guarded, "GameplayEvent.Guarded");
	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Staggered, "GameplayEvent.Staggered");

}