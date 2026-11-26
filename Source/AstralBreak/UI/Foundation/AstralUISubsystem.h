#pragma once

#include "CoreMinimal.h"
#include "Subsystems/LocalPlayerSubsystem.h"
#include "UI/Foundation/AstralUITypes.h"
#include "AstralUISubsystem.generated.h"

class AGameStateBase;
class UAstralActivatableWidget;
class UAstralRootLayout;
class UUserWidget;

/**
 * 화면의 주인 — 로컬 플레이어마다 하나. 화면 전체(UAstralRootLayout)를 갖고, 화면을 여는 길을 하나로 모은다
 * (Lyra GameUIManagerSubsystem · GameUIPolicy 를 프로젝트 크기로 줄인 것, 설계 Docs/Design/ui-autogen-pipeline.md §11 'Phase 3 설계' ③).
 *
 *   만드는 때   로컬 컨트롤러가 정해질 때(PlayerControllerChanged). 시임리스 이동도 컨트롤러를 새로 만들므로(AGameModeBase::HandleSeamlessTravelPlayer) 이것으로 충분하고,
 *               컨트롤러가 그대로 이어지는 경우는 AAstralPlayerController::BeginPlayingState 의 EnsureLayout 이 받친다
 *   걷는 때     월드가 정리될 때 · 컨트롤러가 바뀔 때. 열린 화면은 맵을 넘어가지 않는다
 *   무엇을      어느 맵에 무슨 HUD · 화면이 있는가는 그 맵의 GameState(AAstralGameState)가 정한다 — 클라이언트에는 늦게 오므로 GameStateSetEvent 로 받는다
 */
UCLASS()
class ASTRALBREAK_API UAstralUISubsystem : public ULocalPlayerSubsystem
{
	GENERATED_BODY()

public:
	/** 이 컨트롤러의 로컬 플레이어의 것 — 로컬이 아니면 nullptr */
	static UAstralUISubsystem* Get(const APlayerController* PlayerController);

	//~USubsystem interface
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;
	//~End of USubsystem interface

	//~ULocalPlayerSubsystem interface
	virtual void PlayerControllerChanged(APlayerController* NewPlayerController) override;
	//~End of ULocalPlayerSubsystem interface

	/** 지금 월드 · 컨트롤러의 화면이 서 있게 한다. 이미 서 있으면 아무 일도 하지 않는다 */
	void EnsureLayout();

	UAstralRootLayout* GetRootLayout() const { return RootLayout; }

	/** 화면을 연다. 같은 종류가 그 층의 맨 위에 이미 켜져 있으면 그것을 돌려준다. 닫기는 화면의 DeactivateWidget */
	UAstralActivatableWidget* OpenScreen(TSubclassOf<UAstralActivatableWidget> ScreenClass, EAstralUILayer Layer = EAstralUILayer::Menu);

	/** HUD 층에 떠 있는 위젯 — 이 맵의 목록에 없으면 nullptr */
	template <class WidgetT>
	WidgetT* FindHUDWidget() const { return Cast<WidgetT>(FindHUDWidget(WidgetT::StaticClass())); }
	UUserWidget* FindHUDWidget(const UClass* WidgetClass) const;

	/** 개발용 위젯 — HUD 위 · 메뉴 아래 */
	UUserWidget* ShowDebugWidget(TSubclassOf<UUserWidget> WidgetClass);

private:
	void DestroyLayout();

	void HandleWorldCleanup(UWorld* World, bool bSessionEnded, bool bCleanupResources);
	void HandleGameStateSet(AGameStateBase* GameState);

	UPROPERTY(Transient)
	TObjectPtr<UAstralRootLayout> RootLayout;

	/**
	 * 화면의 주인 컨트롤러 — 로컬 플레이어가 받은(PlayerControllerChanged) 것만. ULocalPlayer::PlayerController 를 그대로 쓰지 않는 까닭:
	 * 클라이언트가 맵을 여는 동안에는 거기에 입력이 없는 임시 컨트롤러가 들어 있다(ULocalPlayer::SpawnPlayActor)
	 */
	TWeakObjectPtr<APlayerController> OwningController;

	/** 화면이 선 월드 · 컨트롤러 — 위젯의 GetWorld 는 만들 때의 월드를 기억하므로 따로 적어 둔다 */
	TWeakObjectPtr<UWorld> LayoutWorld;
	TWeakObjectPtr<APlayerController> LayoutController;

	FDelegateHandle WorldCleanupHandle;
	FDelegateHandle GameStateSetHandle;
};
