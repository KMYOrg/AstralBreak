#include "AstralEventGameplayTags.h"

namespace AstralGameplayTags
{
	/**
	 * GameplayEvent
	 */
	
	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Damaged, "GameplayEvent.Damaged");
	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Death, "GameplayEvent.Death");

	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_ComboWindowOpen, "GameplayEvent.ComboWindowOpen");
	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_ComboBranch, "GameplayEvent.ComboBranch");

	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_WeaponTrace_Begin, "GameplayEvent.WeaponTrace.Begin");
	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_WeaponTrace_End, "GameplayEvent.WeaponTrace.End");

	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Parried, "GameplayEvent.Parried");
	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Guarded, "GameplayEvent.Guarded");
	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Staggered, "GameplayEvent.Staggered");

	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_ActivateFromInput, "GameplayEvent.Ability.ActivateFromInput");

	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Ranged_Fire, "GameplayEvent.Ranged.Fire");

	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Enemy_AttackHit, "GameplayEvent.Enemy.AttackHit");
	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Enemy_AttackSwing, "GameplayEvent.Enemy.AttackSwing");

	UE_DEFINE_GAMEPLAY_TAG(GameplayEvent_Ult_Hit, "GameplayEvent.Ult.Hit");

	/**
	 * AI.Event
	 */

	UE_DEFINE_GAMEPLAY_TAG(AIEvent_TargetLost, "AI.Event.TargetLost");
	UE_DEFINE_GAMEPLAY_TAG(AIEvent_Retarget, "AI.Event.Retarget");
	UE_DEFINE_GAMEPLAY_TAG(AIEvent_Staggered, "AI.Event.Staggered");

}