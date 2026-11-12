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

	// 적 어빌리티 — StateTree 의 ActivateAbility Task 가 스펙을 찾는 키 (asset tag). 사망 취소용 Ability.Attack 과 함께 단다
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Enemy_Attack_Melee);

	// 수호병의 공격 2종 — 트리의 Attack 그룹이 자식마다 다른 태그를 부른다 (m3-enemy-ai.md §10 C2 ②). GA BP 의 asset tag 에 단다
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Enemy_Attack_Combo);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Enemy_Attack_Heavy);

	// 적의 피격 반응 · 경직 — 경직 GA 가 피격 반응을 취소할 때 찾는 키 (asset tag)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Enemy_HitReact);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Ability_Enemy_Stagger);

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
	
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Ranged_Aiming);

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Stamina_RegenBlocked);

	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Death);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Death_Dying);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Death_Dead);

	// 방어 페이즈 — 루즈 태그로 부여/해제 (ActivationOwnedTags는 활성 중 변경 불가)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Defense_Parrying);
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Defense_Guarding);

	// 적 예고 공격의 텔레그래프 구간 표시
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Telegraphing);

	// 적이 공격 어빌리티를 쓰는 중 — 공격 GA BP 의 ActivationOwnedTags. 피격 반응이 이 동안 버틴다(발동 차단)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Enemy_Attacking);

	// 적이 행동할 수 없다(피격 반응 · 경직 GA 가 켜져 있는 동안) — 컨트롤러가 이 태그의 변화를 구독해 트리에 AI.Event.Staggered 를 보낸다
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(State_Enemy_Staggered);

	/**
	 * Damage
	 */

	// 가드만 뚫는 데미지 — 패링은 통한다 (스펙의 동적 asset tag, UAstralCombatStatics::ApplyAttackHit 의 DamageTags 인자로 싣는다)
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Damage_Type_Unguardable);

	// 가드/패링이 통하지 않는 데미지 GE의 asset tag — 예약(M5 보스 강공격·잡기), 현재 사용처 없음
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(Damage_Type_Unblockable);
}
