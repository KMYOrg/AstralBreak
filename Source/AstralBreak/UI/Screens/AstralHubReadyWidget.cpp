// uigen 이 처음 한 번 만든 스텁 — 이제 사람 소유다. uigen 은 이 파일을 다시 쓰지 않는다.

#include "AstralHubReadyWidget.h"

#include "Engine/World.h"
#include "GameModes/AstralGameState.h"
#include "GameModes/AstralHubGameState.h"
#include "Input/CommonUIInputTypes.h"
#include "Player/AstralPlayerController.h"
#include "Player/AstralPlayerState.h"
#include "TimerManager.h"
#include "UI/Foundation/AstralButtonBase.h"
#include "UI/Foundation/AstralUIGameplayTags.h"
#include "UI/Screens/AstralHubMemberRowWidget.h"

UAstralHubReadyWidget::UAstralHubReadyWidget(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// 메뉴 화면 — 커서가 나오고 게임 입력이 막힌다(라우터)
	InputConfig = EAstralWidgetInputMode::Menu;
}

void UAstralHubReadyWidget::NativeOnInitialized()
{
	Super::NativeOnInitialized();   // 생성 베이스가 버튼 누름을 Handle…Clicked 에 묶는다

	// 연 키로 닫는다 — 루트 레이아웃의 여는 묶음은 게임 입력에서만이라, 메뉴 입력인 지금 같은 키는 이 묶음이 받는다
	RegisterUIActionBinding(FBindUIActionArgs(FUIActionTag::ConvertChecked(AstralGameplayTags::UI_Action_HubReady), /*bShouldDisplayInActionBar*/ false,
		FSimpleDelegate::CreateUObject(this, &ThisClass::HandleHubReadyAction)));
}

void UAstralHubReadyWidget::NativeConstruct()
{
	Super::NativeConstruct();

	UWorld* World = GetWorld();
	if (!GetOwningPlayer() || !World || !World->IsGameWorld())
	{
		return;
	}

	if (AAstralPlayerController* PC = GetAstralPlayerController())
	{
		BoundController = PC;
		RequestDeniedHandle = PC->OnLobbyRequestDenied.AddUObject(this, &ThisClass::HandleRequestDenied);
	}

	// GameState 는 클라이언트에서 늦게 올 수 있다 — 설정 통지를 계속 받고, 이미 있으면 바로 붙는다. 없어도 한 번 그려 컨셉 상태를 지운다
	GameStateSetHandle = World->GameStateSetEvent.AddUObject(this, &ThisClass::HandleGameStateSet);
	HandleGameStateSet(World->GetGameState());
}

void UAstralHubReadyWidget::NativeDestruct()
{
	UnbindAll();
	Super::NativeDestruct();
}

UWidget* UAstralHubReadyWidget::NativeGetDesiredFocusTarget() const
{
	return ReadyButton;
}

// ─── 화면 → 원천(요청만) ───

void UAstralHubReadyWidget::HandleReadyClicked()
{
	if (AAstralPlayerController* PC = GetAstralPlayerController())
	{
		PC->ServerSetReady(!IsLocalPlayerReady());
	}
}

void UAstralHubReadyWidget::HandleDestinationClicked()
{
	AAstralPlayerController* PC = GetAstralPlayerController();
	if (PC && !ShownDestination.IsEmpty())
	{
		PC->ServerSelectRaid(ShownDestination);
	}
}

void UAstralHubReadyWidget::HandleLaunchClicked()
{
	if (AAstralPlayerController* PC = GetAstralPlayerController())
	{
		PC->ServerStartRaid();
	}
}

void UAstralHubReadyWidget::HandleHubReadyAction()
{
	DeactivateWidget();
}

// ─── 연결 ───

void UAstralHubReadyWidget::HandleGameStateSet(AGameStateBase* GameState)
{
	AAstralGameState* AstralGameState = Cast<AAstralGameState>(GameState);
	if (AstralGameState != BoundGameState.Get())
	{
		if (AAstralGameState* OldGameState = BoundGameState.Get())
		{
			OldGameState->OnPlayerRosterChanged.Remove(RosterChangedHandle);
			if (AAstralHubGameState* OldHub = Cast<AAstralHubGameState>(OldGameState))
			{
				OldHub->OnSelectedRaidChanged.Remove(SelectedRaidChangedHandle);
			}
		}
		RosterChangedHandle.Reset();
		SelectedRaidChangedHandle.Reset();

		BoundGameState = AstralGameState;
		if (AstralGameState)
		{
			RosterChangedHandle = AstralGameState->OnPlayerRosterChanged.AddUObject(this, &ThisClass::HandleRosterChanged);
			if (AAstralHubGameState* Hub = Cast<AAstralHubGameState>(AstralGameState))
			{
				SelectedRaidChangedHandle = Hub->OnSelectedRaidChanged.AddUObject(this, &ThisClass::HandleLobbyValueChanged);
			}
		}
	}
	HandleRosterChanged();
}

void UAstralHubReadyWidget::HandleRosterChanged()
{
	// 들어오고 나간 사람의 준비 통지를 다시 붙인다 — 명단은 PlayerArray 그대로(거르기는 그릴 때 규칙이 한다)
	TArray<APlayerState*> States;
	if (const AAstralGameState* GameState = BoundGameState.Get())
	{
		GameState->MakeLobbySnapshot(nullptr, &States);
	}
	BindMembers(States);
	Refresh();
}

void UAstralHubReadyWidget::HandleLobbyValueChanged()
{
	Refresh();
}

void UAstralHubReadyWidget::BindMembers(const TArray<APlayerState*>& States)
{
	UnbindMembers();
	for (APlayerState* State : States)
	{
		if (AAstralPlayerState* AstralPS = Cast<AAstralPlayerState>(State))
		{
			BoundMembers.Emplace(AstralPS, AstralPS->OnReadyChanged.AddUObject(this, &ThisClass::HandleLobbyValueChanged));
		}
	}
}

void UAstralHubReadyWidget::UnbindMembers()
{
	for (const TPair<TWeakObjectPtr<AAstralPlayerState>, FDelegateHandle>& Bound : BoundMembers)
	{
		if (AAstralPlayerState* AstralPS = Bound.Key.Get())
		{
			AstralPS->OnReadyChanged.Remove(Bound.Value);
		}
	}
	BoundMembers.Reset();
}

void UAstralHubReadyWidget::UnbindAll()
{
	UWorld* World = GetWorld();
	if (World)
	{
		World->GameStateSetEvent.Remove(GameStateSetHandle);
		World->GetTimerManager().ClearTimer(DeniedReasonTimer);
	}
	GameStateSetHandle.Reset();
	bShowingDeniedReason = false;

	if (AAstralGameState* GameState = BoundGameState.Get())
	{
		GameState->OnPlayerRosterChanged.Remove(RosterChangedHandle);
		if (AAstralHubGameState* Hub = Cast<AAstralHubGameState>(GameState))
		{
			Hub->OnSelectedRaidChanged.Remove(SelectedRaidChangedHandle);
		}
	}
	RosterChangedHandle.Reset();
	SelectedRaidChangedHandle.Reset();
	BoundGameState.Reset();

	if (AAstralPlayerController* PC = BoundController.Get())
	{
		PC->OnLobbyRequestDenied.Remove(RequestDeniedHandle);
	}
	RequestDeniedHandle.Reset();
	BoundController.Reset();

	UnbindMembers();
}

// ─── 거절 ───

void UAstralHubReadyWidget::HandleRequestDenied(EAstralLobbyDenial Reason)
{
	UWorld* World = GetWorld();
	if (Reason == EAstralLobbyDenial::None || !World)
	{
		return;
	}
	bShowingDeniedReason = true;
	SetReason(AstralLobby::GetRequestDeniedText(Reason));
	World->GetTimerManager().SetTimer(DeniedReasonTimer, this, &ThisClass::HandleDeniedReasonExpired, DeniedReasonSeconds, /*bLoop*/ false);
}

void UAstralHubReadyWidget::HandleDeniedReasonExpired()
{
	bShowingDeniedReason = false;
	Refresh();
}

// ─── 원천 → 화면 ───

void UAstralHubReadyWidget::Refresh()
{
	AAstralPlayerController* PC = GetAstralPlayerController();
	TArray<APlayerState*> States;
	const FAstralLobbySnapshot Snapshot = PC ? PC->MakeLobbySnapshot(&States) : FAstralLobbySnapshot();

	// 줄 — 파티원을 PlayerId 순으로(방장이 맨 위). 빈 자리는 접는다(WBP 의 처음 상태는 컨셉 상태다)
	const TArray<int32> Rows = AstralLobby::SelectRowIndices(Snapshot, NumRows);
	const int32 LeaderIndex = AstralLobby::SelectLeaderIndex(Snapshot);
	for (int32 RowIndex = 0; RowIndex < NumRows; ++RowIndex)
	{
		UAstralHubMemberRowWidget* Row = GetRow(RowIndex);
		if (!Row)
		{
			continue;
		}
		if (Rows.IsValidIndex(RowIndex) && States.IsValidIndex(Rows[RowIndex]))
		{
			const int32 MemberIndex = Rows[RowIndex];
			Row->ShowMember(FText::FromString(States[MemberIndex]->GetPlayerName()), MemberIndex == LeaderIndex, Snapshot.Members[MemberIndex].bIsReady);
		}
		else
		{
			Row->ShowEmpty();
		}
	}

	// 준비 — 선택 모양 = 내가 준비됨
	const EAstralLobbyDenial ReadyDenial = AstralLobby::CheckReady(Snapshot);
	SetReadyEnabled(ReadyDenial == EAstralLobbyDenial::None);
	SetReadySelected(Snapshot.Members.IsValidIndex(Snapshot.RequesterIndex) && Snapshot.Members[Snapshot.RequesterIndex].bIsReady);

	// 목적지 — 글자는 목록의 보이는 이름(원천 하나). 고른 것이 목록에 없으면 목록의 첫째를 보인다
	const AAstralHubGameState* Hub = Cast<AAstralHubGameState>(BoundGameState.Get());
	const FAstralRaidDestination* Destination = Hub ? Hub->FindRaidDestination(Snapshot.SelectedRaid) : nullptr;
	if (!Destination && Hub && Hub->GetRaidDestinations().Num() > 0)
	{
		Destination = &Hub->GetRaidDestinations()[0];
	}
	ShownDestination = Destination ? Destination->MapName : FString();
	if (DestinationButton)
	{
		DestinationButton->SetButtonText(Destination ? Destination->DisplayName : FText::GetEmpty());
	}
	const EAstralLobbyDenial SelectDenial = AstralLobby::CheckSelect(Snapshot, ShownDestination);
	SetDestinationEnabled(SelectDenial == EAstralLobbyDenial::None);
	SetDestinationSelected(!ShownDestination.IsEmpty() && ShownDestination.Equals(Snapshot.SelectedRaid, ESearchCase::CaseSensitive));

	// 출정
	const EAstralLobbyDenial StartDenial = AstralLobby::CheckStart(Snapshot);
	SetLaunchEnabled(StartDenial == EAstralLobbyDenial::None);

	// 이유 한 줄 — 앞 단계부터 첫 까닭(준비 → 고르기 → 출정). 서버 거절 글을 띄우는 동안은 그대로 둔다
	if (!bShowingDeniedReason)
	{
		const EAstralLobbyDenial Shown = ReadyDenial != EAstralLobbyDenial::None ? ReadyDenial
			: SelectDenial != EAstralLobbyDenial::None ? SelectDenial
			: StartDenial;
		SetReason(AstralLobby::GetDenialText(Shown));
	}
}

UAstralHubMemberRowWidget* UAstralHubReadyWidget::GetRow(int32 RowIndex) const
{
	switch (RowIndex)
	{
	case 0: return GetMember1Row();
	case 1: return GetMember2Row();
	case 2: return GetMember3Row();
	case 3: return GetMember4Row();
	default: return nullptr;
	}
}

AAstralPlayerController* UAstralHubReadyWidget::GetAstralPlayerController() const
{
	return Cast<AAstralPlayerController>(GetOwningPlayer());
}

bool UAstralHubReadyWidget::IsLocalPlayerReady() const
{
	const AAstralPlayerController* PC = GetAstralPlayerController();
	const AAstralPlayerState* AstralPS = PC ? PC->GetAstralPlayerState() : nullptr;
	return AstralPS && AstralPS->IsReady();
}
