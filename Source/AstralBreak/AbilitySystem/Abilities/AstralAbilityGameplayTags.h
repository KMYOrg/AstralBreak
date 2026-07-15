#pragma once

#include "NativeGameplayTags.h"

namespace AstralGameplayTags
{
	/**
	 * Ability
	 */
	
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Action_Jump);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Action_Sprint);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Action_Dodge);

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Attack_Basic);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Attack_Basic_Melee);

	/**
	 * State
	 */

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_CombatStyle_Melee);

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Movement_Sprinting);

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Stamina_RegenBlocked);
}
