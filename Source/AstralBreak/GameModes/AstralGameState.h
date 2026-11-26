#pragma once

#include "CoreMinimal.h"
#include "Equipment/AstralEquipmentTypes.h"
#include "GameFramework/GameStateBase.h"
#include "GameModes/AstralLobbyRules.h"
#include "UI/Foundation/AstralUITypes.h"
#include "AstralGameState.generated.h"

class UAstralAbilitySet;
class UUserWidget;

/**
 * 문맥(월드) 정책의 소유자 — 장비 정책 · 공통 어빌리티 · 이 맵에서 뜨는 화면.
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

	/** 이 맵에서 늘 떠 있는 HUD 위젯 — 배열 순서대로 아래에서 위로. UAstralRootLayout 이 읽는다 */
	const TArray<TSoftClassPtr<UUserWidget>>& GetContextHUDWidgets() const { return ContextHUDWidgets; }

	/** 이 맵에서 UI 액션으로 여는 화면. UAstralRootLayout 이 읽는다 */
	const TArray<FAstralContextScreen>& GetContextScreens() const { return ContextScreens; }

	/**
	 * 방장 — 봇 · 관전자를 뺀 PlayerArray 에서 PlayerId 최소(가장 먼저 들어온 사람, 리슨에선 호스트).
	 * 저장하지 않고 매번 계산한다: PlayerId 는 엔진이 복제하고 시임리스 이동이 옮기므로 새 복제 상태가 필요 없다.
	 * 클라이언트도 같은 값을 얻지만 표시용이다 — 권한 판정은 서버 RPC 안(AAstralPlayerController::IsPartyLeader)에서만 한다.
	 * 참가자가 없으면 nullptr
	 */
	APlayerState* GetPartyLeader() const;

	/**
	 * 로비 판정 입력 — 지금 PlayerArray(번호 · 봇 · 관전자 · 준비)와 이 맵의 로비 상태(허브만). 서버 RPC 와 화면이 같은 모양으로 만들어
	 * AstralLobby::Check… 에 넣는다. Requester 는 판정받는 사람(명단에 없으면 RequesterIndex = INDEX_NONE).
	 * OutMemberStates 를 주면 Members 와 같은 순서의 PlayerState 를 채운다(화면이 이름을 읽는다)
	 */
	FAstralLobbySnapshot MakeLobbySnapshot(const APlayerState* Requester, TArray<APlayerState*>* OutMemberStates = nullptr) const;

	/**
	 * 명단이 바뀌었다 — 누가 들어오고 나갔나, 번호 · 이름, 어느 것이 내 PlayerState 인가. 서버 · 클라이언트 모두에서 난다.
	 * 화면(동료 줄)은 이 통지를 받아 PlayerArray 에서 다시 뽑는다(폴링 없음). 클라이언트에서는 PlayerArray 에 들어오는 순간(번호 · 이름이 아직 없다)과
	 * 값이 복제된 순간에 각각 나므로, 받는 쪽은 아직 번호가 없는 항목을 건너뛰면 된다
	 */
	FSimpleMulticastDelegate OnPlayerRosterChanged;

	/** AAstralPlayerState 가 번호 · 이름 · 소유가 정해질 때 부른다 */
	void NotifyPlayerRosterChanged() { OnPlayerRosterChanged.Broadcast(); }

	//~AGameStateBase interface
	virtual void AddPlayerState(APlayerState* PlayerState) override;
	virtual void RemovePlayerState(APlayerState* PlayerState) override;
	//~End of AGameStateBase interface

protected:

	/** 이 맵의 로비 상태를 스냅숏에 더한다 — 허브(AAstralHubGameState)만 채운다. 기본은 '허브 아님' */
	virtual void FillLobbyState(FAstralLobbySnapshot& Snapshot) const {}

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Context")
	EAstralEquipmentPolicy EquipmentPolicy = EAstralEquipmentPolicy::Full;

	/**
	 * 공통 어빌리티 세트 — "이 맵에서 누구나 갖는 능력"(이동·점프·스프린트 등).
	 * AAstralPlayerState::SetPawnData가 PawnData 세트에 이어 부여한다
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Context")
	TArray<TObjectPtr<const UAstralAbilitySet>> ContextAbilitySets;

	/** 이 맵의 HUD — 어느 맵에 무엇이 뜨는가는 위젯이 스스로 가리지 않고 여기서 정한다. 편집 기본값이라 복제하지 않는다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Context")
	TArray<TSoftClassPtr<UUserWidget>> ContextHUDWidgets;

	/** 이 맵에서 여는 화면 — UI 액션 태그 → 화면 클래스 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Context", meta = (TitleProperty = "ActionTag"))
	TArray<FAstralContextScreen> ContextScreens;
};
