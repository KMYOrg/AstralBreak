#include "AstralPlayerController.h"

#include "AstralLocalPlayer.h"
#include "AstralLogChannels.h"
#include "AstralPlayerState.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "Engine/World.h"
#include "Equipment/AstralEquipmentManagerComponent.h"
#include "GameModes/AstralGameMode.h"
#include "GameModes/AstralGameState.h"
#include "System/AstralAssetManager.h"
#include "System/AstralPartySubsystem.h"
#include "UI/Debug/AstralDebugWidget.h"

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

	if (IsLocalController() && DebugWidgetClass && !DebugWidget)
	{
		DebugWidget = CreateWidget<UAstralDebugWidget>(this, DebugWidgetClass);
		if (DebugWidget)
		{
			DebugWidget->AddToViewport(100);
		}
	}

	// 로드아웃 재발신 (2단) — 어느 서버에 도착했든 클라 캐시가 있으면 발신. 서버 측 적용은 멱등이라 중복 무해
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
	// MVP: 리슨 호스트 = 서버에서 로컬 컨트롤러인 PC
	return HasAuthority() && IsLocalController();
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

	// 세션 캐시 (1단) — 같은 프로세스 travel 대비
	if (UAstralPartySubsystem* Party = GetGameInstance()->GetSubsystem<UAstralPartySubsystem>())
	{
		Party->CacheLoadout(AstralPS->GetUniqueId(), InLoadout);
	}
}

void AAstralPlayerController::ServerSetReady_Implementation(bool bInReady)
{
	if (AAstralPlayerState* AstralPS = GetAstralPlayerState())
	{
		AstralPS->SetReady(bInReady);
	}
}

void AAstralPlayerController::ServerSelectRaid_Implementation(const FString& MapName)
{
	if (!IsPartyLeader())
	{
		UE_LOG(LogAstral, Warning, TEXT("ServerSelectRaid: 방장이 아님 — 거부 (%s)"), *GetNameSafe(this));
		return;
	}

	FAstralRaidRequest Request;
	Request.MapName = MapName;

	if (AAstralGameState* AstralGS = GetWorld()->GetGameState<AAstralGameState>())
	{
		AstralGS->SetSelectedRaid(Request);
	}
	if (UAstralPartySubsystem* Party = GetGameInstance()->GetSubsystem<UAstralPartySubsystem>())
	{
		Party->SetSelectedRaid(Request);
	}
}

void AAstralPlayerController::ServerStartRaid_Implementation()
{
	if (!IsPartyLeader())
	{
		UE_LOG(LogAstral, Warning, TEXT("ServerStartRaid: 방장이 아님 — 거부 (%s)"), *GetNameSafe(this));
		return;
	}

	AAstralGameState* AstralGS = GetWorld()->GetGameState<AAstralGameState>();
	if (!AstralGS || !AstralGS->GetSelectedRaid().IsSet())
	{
		UE_LOG(LogAstral, Warning, TEXT("ServerStartRaid: 목적지 미선택 — SelectRaid <MapName> 먼저"));
		return;
	}
	if (!AstralGS->AreAllPlayersReady())
	{
		UE_LOG(LogAstral, Warning, TEXT("ServerStartRaid: 전원 준비 아님 — 거부"));
		return;
	}

	// 리슨 유지 travel — seamless 여부는 GameMode.bUseSeamlessTravel (검증 A에서 실경로 확인)
	GetWorld()->ServerTravel(AstralGS->GetSelectedRaid().MapName + TEXT("?listen"));
}

void AAstralPlayerController::ServerReturnToHub_Implementation()
{
	if (!IsPartyLeader())
	{
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

	// 클라 원본 캐시 (2단의 소스) + 즉시 발신
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



