#pragma once

#include "CoreMinimal.h"
#include "Equipment/AstralEquipmentTypes.h"
#include "GameFramework/GameStateBase.h"
#include "AstralGameState.generated.h"

class UAstralAbilitySet;

/**
 * 문맥(월드) 정책의 소유자 — 
 * 로비 상태(SelectedRaid·준비 집계)는 AstralHubGameState, 레이드 상태(목표·진행도)는 M3+의 RaidGameState.
 */
UCLASS()
class ASTRALBREAK_API AAstralGameState : public AGameStateBase
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintPure, Category = "Astral|Context")
	EAstralEquipmentPolicy GetEquipmentPolicy() const { return EquipmentPolicy; }

	const TArray<TObjectPtr<const UAstralAbilitySet>>& GetContextAbilitySets() const { return ContextAbilitySets; }

protected:

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Context")
	EAstralEquipmentPolicy EquipmentPolicy = EAstralEquipmentPolicy::Full;

	/**
	 * 공통 어빌리티 세트 — "이 맵에서 누구나 갖는 능력"(이동·점프·스프린트 등).
	 * AAstralPlayerState::SetPawnData가 PawnData 세트에 이어 부여한다
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Context")
	TArray<TObjectPtr<const UAstralAbilitySet>> ContextAbilitySets;
};
