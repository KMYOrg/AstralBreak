#include "AstralAbilityGameplayTags.h"

namespace AstralGameplayTags
{
	/**
	 * Ability
	 */
	
	UE_DEFINE_GAMEPLAY_TAG(Ability_Action_Jump, "Ability.Action.Jump");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Action_Sprint, "Ability.Action.Sprint");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Action_Dodge, "Ability.Action.Dodge");

	UE_DEFINE_GAMEPLAY_TAG(Ability_Attack_Basic, "Ability.Attack.Basic");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Attack_Basic_Melee, "Ability.Attack.Basic.Melee");

	/**
	 * State
	 */

	UE_DEFINE_GAMEPLAY_TAG(State_CombatStyle_Melee, "State.CombatStyle.Melee");

	UE_DEFINE_GAMEPLAY_TAG(State_Movement_Sprinting, "State.Movement.Sprinting");

	UE_DEFINE_GAMEPLAY_TAG(State_Stamina_RegenBlocked, "State.Stamina.RegenBlocked");
}