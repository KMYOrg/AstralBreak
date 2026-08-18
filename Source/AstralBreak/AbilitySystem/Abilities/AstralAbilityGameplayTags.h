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

	// 공격 계열 부모 태그 — asset tag 매칭용 (CancelAbilities/BlockAbilitiesWithTag가 계층 매칭)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Attack);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Attack_Basic);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Attack_Basic_Melee);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Attack_Basic_Ranged);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Attack_Empowered);

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Defense);

	// 사망 시 CancelAbilities에서 제외되는 어빌리티 표시 (GA_Death 자신, 추후 자가 부활 등)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Behavior_SurvivesDeath);

	// 방어 진입 캔슬에서 제외되는 공격 표시 — 예약(M4 오의), 현재 사용처 없음
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Behavior_SurvivesDefenseCancel);

	/**
	 * State
	 */

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_CombatStyle);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_CombatStyle_Melee);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_CombatStyle_Ranged);

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Movement_Sprinting);

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Stamina_RegenBlocked);

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Death);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Death_Dying);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Death_Dead);

	// 방어 페이즈 — 루즈 태그로 부여/해제 (ActivationOwnedTags는 활성 중 변경 불가)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Defense_Parrying);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Defense_Guarding);

	// 적 예고 공격의 텔레그래프 구간 표시
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Telegraphing);

	/**
	 * Damage
	 */

	// 가드/패링이 통하지 않는 데미지 GE의 asset tag — 예약(M5 보스 강공격·잡기), 현재 사용처 없음
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Damage_Type_Unblockable);
}
