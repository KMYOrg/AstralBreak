#include "AstralAbilityGameplayTags.h"

namespace AstralGameplayTags
{
	/**
	 * Ability
	 */
	
	UE_DEFINE_GAMEPLAY_TAG(Ability_Action_Jump, "Ability.Action.Jump");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Action_Sprint, "Ability.Action.Sprint");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Action_Dodge, "Ability.Action.Dodge");

	UE_DEFINE_GAMEPLAY_TAG(Ability_Attack, "Ability.Attack");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Attack_Basic, "Ability.Attack.Basic");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Attack_Basic_Melee, "Ability.Attack.Basic.Melee");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Attack_Empowered, "Ability.Attack.Empowered");

	UE_DEFINE_GAMEPLAY_TAG(Ability_Defense, "Ability.Defense");

	UE_DEFINE_GAMEPLAY_TAG(Ability_Behavior_SurvivesDeath, "Ability.Behavior.SurvivesDeath");
	UE_DEFINE_GAMEPLAY_TAG(Ability_Behavior_SurvivesDefenseCancel, "Ability.Behavior.SurvivesDefenseCancel");

	/**
	 * State
	 */

	UE_DEFINE_GAMEPLAY_TAG(State_CombatStyle_Melee, "State.CombatStyle.Melee");

	UE_DEFINE_GAMEPLAY_TAG(State_Movement_Sprinting, "State.Movement.Sprinting");

	UE_DEFINE_GAMEPLAY_TAG(State_Stamina_RegenBlocked, "State.Stamina.RegenBlocked");

	UE_DEFINE_GAMEPLAY_TAG(State_Death, "State.Death");
	UE_DEFINE_GAMEPLAY_TAG(State_Death_Dying, "State.Death.Dying");
	UE_DEFINE_GAMEPLAY_TAG(State_Death_Dead, "State.Death.Dead");

	UE_DEFINE_GAMEPLAY_TAG(State_Defense_Parrying, "State.Defense.Parrying");
	UE_DEFINE_GAMEPLAY_TAG(State_Defense_Guarding, "State.Defense.Guarding");

	UE_DEFINE_GAMEPLAY_TAG(State_Telegraphing, "State.Telegraphing");

	/**
	 * Damage
	 */

	UE_DEFINE_GAMEPLAY_TAG(Damage_Type_Unblockable, "Damage.Type.Unblockable");
}