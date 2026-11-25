#include "AstralUISubsystem.h"

#include "AstralRootLayout.h"
#include "Blueprint/UserWidget.h"
#include "Engine/DebugCameraController.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "GameModes/AstralGameState.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(AstralUISubsystem)

namespace AstralUISubsystem
{
	/** 플레이어 화면 안에서의 순서 — 다른 위젯을 화면에 직접 올리지 않으므로 값 자체에는 뜻이 없다(Lyra 와 같은 값) */
	constexpr int32 RootLayoutZOrder = 1000;
}

UAstralUISubsystem* UAstralUISubsystem::Get(const APlayerController* PlayerController)
{
	return PlayerController ? ULocalPlayer::GetSubsystem<UAstralUISubsystem>(PlayerController->GetLocalPlayer()) : nullptr;
}

void UAstralUISubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	WorldCleanupHandle = FWorldDelegates::OnWorldCleanup.AddUObject(this, &ThisClass::HandleWorldCleanup);
}

void UAstralUISubsystem::Deinitialize()
{
	FWorldDelegates::OnWorldCleanup.Remove(WorldCleanupHandle);
	DestroyLayout();

	Super::Deinitialize();
}

void UAstralUISubsystem::PlayerControllerChanged(APlayerController* NewPlayerController)
{
	Super::PlayerControllerChanged(NewPlayerController);

	if (NewPlayerController && NewPlayerController->IsA<ADebugCameraController>())
	{
		return;   // 디버그 카메라(ToggleDebugCamera)는 잠깐 빌리는 컨트롤러다 — 화면은 원래 주인 것 그대로
	}
	OwningController = NewPlayerController;
	EnsureLayout();
}

void UAstralUISubsystem::EnsureLayout()
{
	const ULocalPlayer* LocalPlayer = GetLocalPlayer();
	APlayerController* Controller = OwningController.Get();
	UWorld* World = Controller ? Controller->GetWorld() : nullptr;

	if (RootLayout && (LayoutWorld.Get() != World || LayoutController.Get() != Controller))
	{
		DestroyLayout();
	}
	if (RootLayout || !World || !World->IsGameWorld() || !LocalPlayer || !LocalPlayer->ViewportClient)
	{
		return;
	}

	RootLayout = CreateWidget<UAstralRootLayout>(Controller, UAstralRootLayout::StaticClass());
	if (!RootLayout)
	{
		return;
	}
	LayoutWorld = World;
	LayoutController = Controller;
	RootLayout->AddToPlayerScreen(AstralUISubsystem::RootLayoutZOrder);

	// GameState 는 클라이언트에서 늦게 올 수 있다 — 설정 통지를 계속 받고, 이미 있으면 바로 쓴다
	GameStateSetHandle = World->GameStateSetEvent.AddUObject(this, &ThisClass::HandleGameStateSet);
	if (AGameStateBase* GameState = World->GetGameState())
	{
		HandleGameStateSet(GameState);
	}
}

UAstralActivatableWidget* UAstralUISubsystem::OpenScreen(TSubclassOf<UAstralActivatableWidget> ScreenClass, EAstralUILayer Layer)
{
	EnsureLayout();
	return RootLayout ? RootLayout->PushScreen(ScreenClass, Layer) : nullptr;
}

UUserWidget* UAstralUISubsystem::FindHUDWidget(const UClass* WidgetClass) const
{
	return RootLayout ? RootLayout->FindHUDWidget(WidgetClass) : nullptr;
}

UUserWidget* UAstralUISubsystem::ShowDebugWidget(TSubclassOf<UUserWidget> WidgetClass)
{
	EnsureLayout();
	return RootLayout ? RootLayout->ShowDebugWidget(WidgetClass) : nullptr;
}

void UAstralUISubsystem::DestroyLayout()
{
	if (UWorld* World = LayoutWorld.Get())
	{
		World->GameStateSetEvent.Remove(GameStateSetHandle);
	}
	GameStateSetHandle.Reset();
	LayoutWorld.Reset();
	LayoutController.Reset();

	if (RootLayout)
	{
		RootLayout->RemoveFromParent();
		RootLayout = nullptr;
	}
}

void UAstralUISubsystem::HandleWorldCleanup(UWorld* World, bool bSessionEnded, bool bCleanupResources)
{
	if (RootLayout && LayoutWorld.Get() == World)
	{
		DestroyLayout();
	}
}

void UAstralUISubsystem::HandleGameStateSet(AGameStateBase* GameState)
{
	if (RootLayout)
	{
		RootLayout->ApplyContext(Cast<AAstralGameState>(GameState));
	}
}
