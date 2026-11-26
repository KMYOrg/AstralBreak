#include "AstralHubGameState.h"

#include "Net/UnrealNetwork.h"
#include "UI/Foundation/AstralActivatableWidget.h"
#include "UI/Foundation/AstralUIGameplayTags.h"

#define LOCTEXT_NAMESPACE "AstralLobby"

AAstralHubGameState::AAstralHubGameState()
{
	// 로비 = 액터 스폰만(홀스터 표시), 어빌리티·스탯 부여 없음
	EquipmentPolicy = EAstralEquipmentPolicy::VisualOnly;

	// 목적지 — 이름은 game-plan 7-5 의 콘셉트 이름(기획 요소 · 잠정)
	FAstralRaidDestination Raid;
	Raid.MapName = TEXT("RaidMap");
	Raid.DisplayName = LOCTEXT("Destination_RaidMap", "봉인된 유적");
	RaidDestinations.Add(Raid);

	// 허브에서 여는 화면 — 승격본(uigen promote_widget). 소프트 참조라 애셋이 없어도 클래스 로드는 깨지지 않는다(UAstralRootLayout 이 경고만). BP 에서 덮어쓸 수 있다
	FAstralContextScreen HubReady;
	HubReady.ActionTag = AstralGameplayTags::MakeUIActionTag(AstralGameplayTags::UI_Action_HubReady);
	HubReady.ScreenClass = TSoftClassPtr<UAstralActivatableWidget>(FSoftObjectPath(TEXT("/Game/UI/Screens/HubReady/WBP_HubReady.WBP_HubReady_C")));
	ContextScreens.Add(HubReady);
}

void AAstralHubGameState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AAstralHubGameState, SelectedRaid);
}

void AAstralHubGameState::SetSelectedRaid(const FAstralRaidRequest& InRequest)
{
	if (!HasAuthority() || SelectedRaid.MapName.Equals(InRequest.MapName, ESearchCase::CaseSensitive))
	{
		return;
	}
	SelectedRaid = InRequest;
	OnSelectedRaidChanged.Broadcast();
	ForceNetUpdate();
}

void AAstralHubGameState::OnRep_SelectedRaid()
{
	OnSelectedRaidChanged.Broadcast();
}

const FAstralRaidDestination* AAstralHubGameState::FindRaidDestination(const FString& MapName) const
{
	return RaidDestinations.FindByPredicate([&MapName](const FAstralRaidDestination& Destination)
	{
		return Destination.MapName.Equals(MapName, ESearchCase::CaseSensitive);
	});
}

bool AAstralHubGameState::AreAllPlayersReady() const
{
	return AstralLobby::AreAllMembersReady(MakeLobbySnapshot(nullptr));
}

void AAstralHubGameState::FillLobbyState(FAstralLobbySnapshot& Snapshot) const
{
	Snapshot.bInHub = true;
	Snapshot.SelectedRaid = SelectedRaid.MapName;
	for (const FAstralRaidDestination& Destination : RaidDestinations)
	{
		Snapshot.AllowedRaids.Add(Destination.MapName);
	}
}

#undef LOCTEXT_NAMESPACE
