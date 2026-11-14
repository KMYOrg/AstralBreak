#pragma once

#include "CoreMinimal.h"
#include "Equipment/AstralEquipmentTypes.h"
#include "GameFramework/GameStateBase.h"
#include "AstralGameState.generated.h"

class UAstralAbilitySet;

/**
 * 문맥(월드) 정책의 소유자 — 
 * 로비 상태(SelectedRaid·준비 집계)는 AstralHubGameState, 레이드 상태(체인 버스트 · 이후 목표·진행도)는 AstralRaidGameState.
 */
UCLASS()
class ASTRALBREAK_API AAstralGameState : public AGameStateBase
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintPure, Category = "Astral|Context")
	EAstralEquipmentPolicy GetEquipmentPolicy() const { return EquipmentPolicy; }

	const TArray<TObjectPtr<const UAstralAbilitySet>>& GetContextAbilitySets() const { return ContextAbilitySets; }

	/**
	 * 방장 — 봇 · 관전자를 뺀 PlayerArray 에서 PlayerId 최소(가장 먼저 들어온 사람, 리슨에선 호스트).
	 * 저장하지 않고 매번 계산한다: PlayerId 는 엔진이 복제하고 시임리스 이동이 옮기므로 새 복제 상태가 필요 없다.
	 * 클라이언트도 같은 값을 얻지만 표시용이다 — 권한 판정은 서버 RPC 안(AAstralPlayerController::IsPartyLeader)에서만 한다.
	 * 참가자가 없으면 nullptr
	 */
	APlayerState* GetPartyLeader() const;

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
