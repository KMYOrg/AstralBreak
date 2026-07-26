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
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Attack_Empowered);

	// 사망 시 CancelAbilities에서 제외되는 어빌리티 표시 (GA_Death 자신, 추후 자가 부활 등)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Behavior_SurvivesDeath);

	/**
	 * State
	 */

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_CombatStyle_Melee);

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Movement_Sprinting);

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Stamina_RegenBlocked);

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Death);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Death_Dying);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Death_Dead);
}
