#include "AstralPlayerController.h"

#include "AstralLocalPlayer.h"
#include "AstralLogChannels.h"
#include "AstralPlayerState.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "Engine/World.h"
#include "Equipment/AstralEquipmentManagerComponent.h"
#include "GameModes/AstralGameMode.h"
#include "GameModes/AstralHubGameState.h"
#include "System/AstralAssetManager.h"
#include "System/AstralPartySubsystem.h"
#include "UI/Debug/AstralDebugWidget.h"
#include "UI/Foundation/AstralUISubsystem.h"
#include "UI/HUD/AstralCombatHUDWidget.h"
#include "UI/HUD/AstralStatusHUDWidget.h"

namespace
{
	/** 타입 접두 생략 축약형 — 후보 타입 중 스캔에 실재하는 ID로 해석 (스캔 데이터는 클라에도 있음) */
	FPrimaryAssetId ResolveShortAssetId(const FString& IdString, std::initializer_list<const TCHAR*> CandidateTypes)
	{
		FPrimaryAssetId AssetId = FPrimaryAssetId::FromString(IdString);
		if (AssetId.IsValid() && UAstralAssetManager::Get().GetPrimaryAssetPath(AssetId).IsValid())
		{
			return AssetId;
		}

		for (const TCHAR* Type : CandidateTypes)
		{
			const FPrimaryAssetId Candidate{ FName(Type), FName(*IdString) };
			if (UAstralAssetManager::Get().GetPrimaryAssetPath(Candidate).IsValid())
			{
				return Candidate;
			}
		}
		return FPrimaryAssetId();
	}

	/** 거부 로그용 — 현재 방장. 액터 이름은 프로세스마다 다르므로 창끼리 맞춰 볼 키는 PlayerId 다 */
	FString DescribePartyLeader(const UWorld* World)
	{
		const AAstralGameState* AstralGS = World ? World->GetGameState<AAstralGameState>() : nullptr;
		const APlayerState* Leader = AstralGS ? AstralGS->GetPartyLeader() : nullptr;
		return Leader
			? FString::Printf(TEXT("%s (PlayerId %d)"), *Leader->GetName(), Leader->GetPlayerId())
			: FString(TEXT("없음"));
	}
}

AAstralPlayerController::AAstralPlayerController(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

void AAstralPlayerController::PreInitializeComponents()
{
	Super::PreInitializeComponents();
}

void AAstralPlayerController::BeginPlay()
{
	Super::BeginPlay();
}

void AAstralPlayerController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	Super::EndPlay(EndPlayReason);
}

void AAstralPlayerController::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
}

AAstralPlayerState* AAstralPlayerController::GetAstralPlayerState() const
{
	return CastChecked<AAstralPlayerState>(PlayerState, ECastCheckedType::NullAllowed);
}

UAstralAbilitySystemComponent* AAstralPlayerController::GetAstralAbilitySystemComponent() const
{
	const AAstralPlayerState* AstralPS = GetAstralPlayerState();
	return (AstralPS ? AstralPS->GetAstralAbilitySystemComponent() : nullptr);
}

UAstralCombatHUDWidget* AAstralPlayerController::GetCombatHUDWidget() const
{
	const UAstralUISubsystem* UISubsystem = UAstralUISubsystem::Get(this);
	return UISubsystem ? UISubsystem->FindHUDWidget<UAstralCombatHUDWidget>() : nullptr;
}

UAstralStatusHUDWidget* AAstralPlayerController::GetStatusHUDWidget() const
{
	const UAstralUISubsystem* UISubsystem = UAstralUISubsystem::Get(this);
	return UISubsystem ? UISubsystem->FindHUDWidget<UAstralStatusHUDWidget>() : nullptr;
}

void AAstralPlayerController::PostProcessInput(const float DeltaTime, const bool bGamePaused)
{
	if (UAstralAbilitySystemComponent* AstralASC = GetAstralAbilitySystemComponent())
	{
		AstralASC->ProcessAbilityInput(DeltaTime, bGamePaused);
	}

	Super::PostProcessInput(DeltaTime, bGamePaused);
}

void AAstralPlayerController::BeginPlayingState()
{
	Super::BeginPlayingState();

	// 화면 — 만드는 것은 화면의 주인(UAstralUISubsystem)이고, HUD 는 맵의 목록(AAstralGameState::ContextHUDWidgets)이 정한다.
	// 여기서는 컨트롤러가 이어진 채 월드만 바뀐 경우를 받치고, 개발용 글자를 맡긴다(HUD 위 · 메뉴 아래)
	if (UAstralUISubsystem* UISubsystem = UAstralUISubsystem::Get(this))
	{
		UISubsystem->EnsureLayout();
		DebugWidget = Cast<UAstralDebugWidget>(UISubsystem->ShowDebugWidget(DebugWidgetClass));
	}

	// 로드아웃 재발신 (1단 PS.Loadout을 채운다) — 어느 서버에 도착했든 클라 캐시가 있으면 발신. 서버 측 적용은 멱등이라 중복 무해
	if (IsLocalController())
	{
		if (const UAstralLocalPlayer* AstralLP = Cast<UAstralLocalPlayer>(GetLocalPlayer()))
		{
			if (AstralLP->CachedLoadout.IsSet())
			{
				ServerSetLoadout(AstralLP->CachedLoadout);
			}
		}
	}
}

bool AAstralPlayerController::IsPartyLeader() const
{
	// 방장 = GameState 가 계산한 사람(PlayerId 최소). 넷 모드 분기 없음 — 리슨에선 호스트, Dedicated 에선 먼저 들어온 클라이언트.
	// 권한 판정으로는 서버 RPC 안에서만 쓴다 (클라이언트에서 부르면 표시용 값)
	const UWorld* World = GetWorld();
	const AAstralGameState* AstralGS = World ? World->GetGameState<AAstralGameState>() : nullptr;
	return AstralGS && PlayerState && AstralGS->GetPartyLeader() == PlayerState;
}

void AAstralPlayerController::ServerSetLoadout_Implementation(FAstralPlayerLoadout InLoadout)
{
	// ID 해석 검증 — 실재하지 않는 ID는 버린다 (쓰레기/조작 차단, 백엔드 검증은 이후)
	if (InLoadout.CharacterId.IsValid() && !UAstralAssetManager::Get().GetPrimaryAssetPath(InLoadout.CharacterId).IsValid())
	{
		UE_LOG(LogAstral, Warning, TEXT("ServerSetLoadout: 해석 불가 CharacterId %s — 무시"), *InLoadout.CharacterId.ToString());
		InLoadout.CharacterId = FPrimaryAssetId();
	}
	InLoadout.Equipment.RemoveAll([](const FPrimaryAssetId& ItemId)
	{
		const bool bInvalid = (UAstralEquipmentManagerComponent::ResolveItemDefinition(ItemId) == nullptr);
		if (bInvalid)
		{
			UE_LOG(LogAstral, Warning, TEXT("ServerSetLoadout: 해석 불가 장비 ID %s — 제외"), *ItemId.ToString());
		}
		return bInvalid;
	});

	AAstralPlayerState* AstralPS = GetAstralPlayerState();
	if (!AstralPS)
	{
		return;
	}

	AstralPS->SetLoadout(InLoadout);

	// 세션 캐시 (2단 폴백) — 같은 프로세스 travel 대비
	if (UAstralPartySubsystem* Party = GetGameInstance()->GetSubsystem<UAstralPartySubsystem>())
	{
		Party->CacheLoadout(AstralPS->GetUniqueId(), InLoadout);
	}
}

FAstralLobbySnapshot AAstralPlayerController::MakeLobbySnapshot(TArray<APlayerState*>* OutMemberStates) const
{
	const UWorld* World = GetWorld();
	const AAstralGameState* AstralGS = World ? World->GetGameState<AAstralGameState>() : nullptr;
	if (!AstralGS)
	{
		if (OutMemberStates)
		{
			OutMemberStates->Reset();
		}
		return FAstralLobbySnapshot();
	}
	return AstralGS->MakeLobbySnapshot(PlayerState, OutMemberStates);
}

void AAstralPlayerController::ServerSetReady_Implementation(bool bInReady)
{
	// 허브로 막지 않는다 — 레이드 · 시험 맵에서도 이 값을 신호로 쓰는 별도 프로세스 시험이 있고, 준비 값은 이동 때 넘어가지 않는다
	if (const EAstralLobbyDenial Denial = AstralLobby::CheckReady(MakeLobbySnapshot()); Denial != EAstralLobbyDenial::None)
	{
		UE_LOG(LogAstral, Warning, TEXT("ServerSetReady: %s — 거부 (%s)"), AstralLobby::LexToString(Denial), *GetNameSafe(this));
		ClientLobbyRequestDenied(Denial);
		return;
	}

	if (AAstralPlayerState* AstralPS = GetAstralPlayerState())
	{
		AstralPS->SetReady(bInReady);
	}
}

void AAstralPlayerController::ServerSelectRaid_Implementation(const FString& MapName)
{
	// 판정 순서 = 방장 아님 → 허브 아님 → 목록에 없음(AstralLobby::CheckSelect). 로그 문구는 시험이 센다(Tools/net_test/run_party_flow.py · AstralPartyFlowPieTests) — 바꾸지 않는다.
	// 목록은 허브 GameState 에 있으므로 허브가 아니면 목록을 보기 전에 거절한다(예전에는 게임모드의 목록을 먼저 봤다 — 허브 안에서는 결과가 같다)
	const EAstralLobbyDenial Denial = AstralLobby::CheckSelect(MakeLobbySnapshot(), MapName);
	switch (Denial)
	{
	case EAstralLobbyDenial::None:
		break;
	case EAstralLobbyDenial::NotLeader:
		UE_LOG(LogAstral, Warning, TEXT("ServerSelectRaid: 방장이 아님 — 거부 (%s, 현재 방장 = %s)"), *GetNameSafe(this), *DescribePartyLeader(GetWorld()));
		break;
	case EAstralLobbyDenial::NotInHub:
		UE_LOG(LogAstral, Warning, TEXT("ServerSelectRaid: HubGameState 없음 (로비가 아님) — 거부"));
		break;
	case EAstralLobbyDenial::RaidNotAllowed:
		// 클라이언트가 보낸 문자열이 그대로 ServerTravel 주소가 된다 — 목록과 정확히 같은 이름만 (임의 맵 · ?옵션 주입 차단)
		UE_LOG(LogAstral, Warning, TEXT("ServerSelectRaid: 허용 목록에 없는 맵 '%s' — 거부 (%s)"), *MapName, *GetNameSafe(this));
		break;
	default:
		UE_LOG(LogAstral, Warning, TEXT("ServerSelectRaid: %s — 거부 (%s)"), AstralLobby::LexToString(Denial), *GetNameSafe(this));
		break;
	}

	AAstralHubGameState* HubGS = GetWorld()->GetGameState<AAstralHubGameState>();
	if (Denial != EAstralLobbyDenial::None || !HubGS)
	{
		ClientLobbyRequestDenied(Denial != EAstralLobbyDenial::None ? Denial : EAstralLobbyDenial::NotInHub);
		return;
	}

	FAstralRaidRequest Request;
	Request.MapName = MapName;
	HubGS->SetSelectedRaid(Request);
	if (UAstralPartySubsystem* Party = GetGameInstance()->GetSubsystem<UAstralPartySubsystem>())
	{
		Party->SetSelectedRaid(Request);
	}
}

void AAstralPlayerController::ServerStartRaid_Implementation()
{
	// 판정 순서 = 방장 아님 → 허브 아님 → 목적지 미선택 → 목록에 없음 → 전원 준비 아님(AstralLobby::CheckStart). 로그 문구는 시험이 센다 — 바꾸지 않는다
	const FAstralLobbySnapshot Snapshot = MakeLobbySnapshot();
	const EAstralLobbyDenial Denial = AstralLobby::CheckStart(Snapshot);
	switch (Denial)
	{
	case EAstralLobbyDenial::None:
		break;
	case EAstralLobbyDenial::NotLeader:
		UE_LOG(LogAstral, Warning, TEXT("ServerStartRaid: 방장이 아님 — 거부 (%s, 현재 방장 = %s)"), *GetNameSafe(this), *DescribePartyLeader(GetWorld()));
		break;
	case EAstralLobbyDenial::NotInHub:
	case EAstralLobbyDenial::NoRaidSelected:
		UE_LOG(LogAstral, Warning, TEXT("ServerStartRaid: 로비가 아니거나 목적지 미선택 — SelectRaid <MapName> 먼저"));
		break;
	case EAstralLobbyDenial::RaidNotAllowed:
		UE_LOG(LogAstral, Warning, TEXT("ServerStartRaid: 허용 목록에 없는 맵 '%s' — 거부 (%s)"), *Snapshot.SelectedRaid, *GetNameSafe(this));
		break;
	case EAstralLobbyDenial::NotAllReady:
		UE_LOG(LogAstral, Warning, TEXT("ServerStartRaid: 전원 준비 아님 — 거부"));
		break;
	default:
		UE_LOG(LogAstral, Warning, TEXT("ServerStartRaid: %s — 거부 (%s)"), AstralLobby::LexToString(Denial), *GetNameSafe(this));
		break;
	}
	if (Denial != EAstralLobbyDenial::None)
	{
		ClientLobbyRequestDenied(Denial);
		return;
	}

	// 리슨 유지 travel — seamless 여부는 GameMode.bUseSeamlessTravel (검증 A에서 실경로 확인)
	GetWorld()->ServerTravel(Snapshot.SelectedRaid + TEXT("?listen"));
}

void AAstralPlayerController::ClientLobbyRequestDenied_Implementation(EAstralLobbyDenial Reason)
{
	OnLobbyRequestDenied.Broadcast(Reason);
}

void AAstralPlayerController::ServerReturnToHub_Implementation()
{
	if (!IsPartyLeader())
	{
		UE_LOG(LogAstral, Warning, TEXT("ServerReturnToHub: 방장이 아님 — 거부 (%s, 현재 방장 = %s)"), *GetNameSafe(this), *DescribePartyLeader(GetWorld()));
		return;
	}

	if (const AAstralGameMode* GameMode = GetWorld()->GetAuthGameMode<AAstralGameMode>())
	{
		GetWorld()->ServerTravel(GameMode->GetHubMapName() + TEXT("?listen"));
	}
}

void AAstralPlayerController::SetLoadout(const FString& CharacterName, const FString& Weapon1, const FString& Weapon2)
{
#if !UE_BUILD_SHIPPING
	FAstralPlayerLoadout NewLoadout;

	if (!CharacterName.IsEmpty())
	{
		NewLoadout.CharacterId = ResolveShortAssetId(CharacterName, { TEXT("AstralCharacterDefinition") });
		if (!NewLoadout.CharacterId.IsValid())
		{
			UE_LOG(LogAstral, Warning, TEXT("SetLoadout: 캐릭터 '%s' 해석 실패"), *CharacterName);
		}
	}

	for (const FString& WeaponName : { Weapon1, Weapon2 })
	{
		if (WeaponName.IsEmpty())
		{
			continue;
		}
		const FPrimaryAssetId WeaponId = ResolveShortAssetId(WeaponName, { TEXT("AstralWeaponDefinition"), TEXT("AstralRangedWeaponDefinition") });
		if (WeaponId.IsValid())
		{
			NewLoadout.Equipment.Add(WeaponId);
		}
		else
		{
			UE_LOG(LogAstral, Warning, TEXT("SetLoadout: 무기 '%s' 해석 실패"), *WeaponName);
		}
	}

	// 클라 원본 캐시 (재발신의 소스) + 즉시 발신
	if (UAstralLocalPlayer* AstralLP = Cast<UAstralLocalPlayer>(GetLocalPlayer()))
	{
		AstralLP->CachedLoadout = NewLoadout;
	}
	ServerSetLoadout(NewLoadout);
#endif
}

void AAstralPlayerController::SetReady(int32 bReady)
{
#if !UE_BUILD_SHIPPING
	ServerSetReady(bReady != 0);
#endif
}

void AAstralPlayerController::SelectRaid(const FString& MapName)
{
#if !UE_BUILD_SHIPPING
	ServerSelectRaid(MapName);
#endif
}

void AAstralPlayerController::StartRaid()
{
#if !UE_BUILD_SHIPPING
	ServerStartRaid();
#endif
}

void AAstralPlayerController::ReturnToHub()
{
#if !UE_BUILD_SHIPPING
	ServerReturnToHub();
#endif
}

void AAstralPlayerController::ToggleDebugWidget()
{
#if !UE_BUILD_SHIPPING
	if (DebugWidget)
	{
		const bool bShown = DebugWidget->GetVisibility() != ESlateVisibility::Collapsed;
		DebugWidget->SetVisibility(bShown ? ESlateVisibility::Collapsed : ESlateVisibility::SelfHitTestInvisible);
	}
#endif
}



