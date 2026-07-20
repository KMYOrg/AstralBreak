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

	// 사망 상태 — 부모(State.Death)로 매칭하면 Dying/Dead 둘 다 걸림 (어빌리티 차단 / 히트 필터 / 수급 차단)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Death);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Death_Dying);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Death_Dead);
}
