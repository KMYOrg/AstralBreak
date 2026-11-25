// 화면 체계 시험 — 한 프로세스 멀티 PIE 2인 (설계 Docs/Design/ui-autogen-pipeline.md §11 'Phase 3 설계' ③ · 'Phase 3-1 결과')
//
// 리슨 서버 · Dedicated 를 PIE 로 띄워 허브에서 C++ 시험 화면을 열고 닫고, 레이드로 옮긴다. A = 첫 클라이언트 자리, B = 다른 자리(리슨이면 호스트).
// 키는 실제 길로 넣는다 — 게임 키 · 뒤로는 자리의 뷰포트 클라이언트(UCommonGameViewportClient::InputKey → 라우터)로, 방향키 · 뒤로 한 번은 Slate 로.
// 편집기 PIE 에서는 초점이 있는 창의 라우터만 입력 설정을 바꾸므로(UIActionRouterTypes.cpp IsViewportWindowInFocusPath) 자리를 쓸 때마다 그 창에 초점을 준다.
//
//   U0  허브: 자리마다 루트 레이아웃이 화면에 있고 켜져 있다. HUD 층은 비었다(허브 목록 없음 — 전투 HUD 도 이제 없다). 여닫는 액션의 키가 ini 에 있다
//   U1  열기 전: W 를 누르면 A 의 폰이 움직인다
//   U2  W 를 누른 채 A 에서 열기: 메뉴 입력 · 커서 · 마우스 안 잡음 · 첫 초점 = 첫 버튼, 눌려 있던 W 가 풀리고 폰이 선다. 다시 눌러도 게임에 안 간다
//   U3  그동안 B: 메뉴 입력이 아니고 화면이 없다. W 로 B 의 폰이 움직인다(자리끼리 간섭 없음)
//   U4  키보드 방향키로 초점이 둘째 버튼으로 옮겨 간다 — 그때의 모양(올림인가)을 적는다
//   U5  둘째 화면을 겹쳐 열면 첫 화면은 꺼지고 둘째에 초점. 뒤로(게임패드 B) = 둘째만 닫히고 첫 화면이 다시 켜진다(그 사이 Game 입력으로 떨어지지 않는다).
//       뒤로 한 번 더 = 다 닫히고 Game 으로 복구
//   U6  메뉴 위에 Modal: 뒤로 = Modal 만 닫힘(메뉴는 그대로 켜져 있다 · 그 사이 Game 입력으로 떨어지지 않는다), 한 번 더 = 메뉴도 닫힘
//   U7  맵의 목록(ContextScreens)에 넣은 액션으로 열기: Game 입력에서 키 → 열림, 같은 키(뒤로) → 닫힘. B 자리는 그대로
//   U8  A 의 화면을 연 채 레이드로 이동: 두 자리의 레이아웃이 새로 서고(옛 것은 화면에 없음) 화면은 남지 않으며 HUD 둘이 HUD 층에 있다. 입력은 게임으로 돌아왔다.
//       HUD 층의 HUD 는 같은 WBP 를 뷰포트에 직접 올린 것(예전 방식)과 모든 위젯의 그려진 자리 · 크기가 같다
//   U9  레이드에서도 열고 닫힌다

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AstralPieTestHelpers.h"
#include "AstralScreenStackTestWidgets.h"
#include "AstralUITestHelpers.h"

#include "Blueprint/WidgetTree.h"
#include "CommonGameViewportClient.h"
#include "CommonInputModeTypes.h"
#include "CommonInputSubsystem.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "Engine/UserInterfaceSettings.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/InputDeviceSubsystem.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerState.h"
#include "GameModes/AstralHubGameState.h"
#include "GenericPlatform/GenericPlatformInputDeviceMapper.h"
#include "Input/CommonUIActionRouterBase.h"
#include "Input/CommonUIInputSettings.h"
#include "InputCoreTypes.h"
#include "InputKeyEventArgs.h"
#include "Player/AstralPlayerController.h"
#include "UI/Foundation/AstralRootLayout.h"
#include "UI/Foundation/AstralUISubsystem.h"
#include "UI/HUD/AstralCombatHUDWidget.h"
#include "UI/HUD/AstralStatusHUDWidget.h"
#include "UObject/StrongObjectPtr.h"
#include "UnrealClient.h"
#include "Widgets/SViewport.h"

namespace AstralScreenStackPie
{
	using namespace AstralPieTest;

	const TCHAR* const HubMapPath = TEXT("/Game/Maps/HubMap");
	const TCHAR* const HubMap = TEXT("HubMap");
	const TCHAR* const RaidMap = TEXT("RaidMap");
	const TCHAR* const BackTagName = TEXT("UI.Action.Back");

	constexpr int32 NumPlayers = 2;
	/** 움직인다고 볼 속력 · 섰다고 볼 속력(cm/s) */
	constexpr double MovingSpeed = 50.0;
	constexpr double StillSpeed = 5.0;

	struct FContext : FContextBase
	{
		bool bDedicated = false;

		/** [0] = A(첫 클라이언트 자리), [1] = B */
		TArray<int32> Ids;

		/** U8 — 이동 전 레이아웃(이동 뒤 화면에 없어야 한다) */
		TMap<int32, TWeakObjectPtr<UAstralRootLayout>> OldLayouts;
		TMap<int32, TWeakObjectPtr<APlayerController>> OldControllers;

		/** A 의 라우터가 입력 모드를 바꾼 차례 — 화면을 겹쳐 열고 닫는 동안 Game 으로 떨어지면 안 된다 */
		TArray<ECommonInputMode> ModeChanges;
		FDelegateHandle ModeChangedHandle;

		/** U8 — HUD 와 같은 WBP 를 예전 방식으로 띄운 것(자리 · 크기 비교) */
		TArray<TStrongObjectPtr<UUserWidget>> Twins;
	};

	// ─── 조회 ───

	AAstralPlayerController* GetLocalPC(const UWorld* World)
	{
		const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
		return GameInstance ? Cast<AAstralPlayerController>(GameInstance->GetFirstLocalPlayerController(World)) : nullptr;
	}

	TArray<UWorld*> GetSeatWorlds()
	{
		TArray<UWorld*> Out;
		for (UWorld* World : GetPieWorlds())
		{
			const ENetMode NetMode = World->GetNetMode();
			if (NetMode == NM_ListenServer || NetMode == NM_Client)
			{
				Out.Add(World);
			}
		}
		return Out;
	}

	int32 LocalPlayerIdIn(const UWorld* World)
	{
		const APlayerController* PC = GetLocalPC(World);
		return (PC && PC->PlayerState) ? PC->PlayerState->GetPlayerId() : 0;
	}

	/** 자리의 로컬 컨트롤러 — 월드가 바뀌므로 매번 찾는다 */
	AAstralPlayerController* SeatPC(int32 PlayerId)
	{
		for (const UWorld* World : GetSeatWorlds())
		{
			if (LocalPlayerIdIn(World) == PlayerId)
			{
				return GetLocalPC(World);
			}
		}
		return nullptr;
	}

	UAstralUISubsystem* UIOf(int32 PlayerId) { return UAstralUISubsystem::Get(SeatPC(PlayerId)); }

	UAstralRootLayout* LayoutOf(int32 PlayerId)
	{
		const UAstralUISubsystem* UI = UIOf(PlayerId);
		return UI ? UI->GetRootLayout() : nullptr;
	}

	UCommonUIActionRouterBase* RouterOf(int32 PlayerId)
	{
		const AAstralPlayerController* PC = SeatPC(PlayerId);
		return PC ? ULocalPlayer::GetSubsystem<UCommonUIActionRouterBase>(PC->GetLocalPlayer()) : nullptr;
	}

	UGameViewportClient* ViewportOf(int32 PlayerId)
	{
		const AAstralPlayerController* PC = SeatPC(PlayerId);
		const ULocalPlayer* LocalPlayer = PC ? PC->GetLocalPlayer() : nullptr;
		return LocalPlayer ? ToRawPtr(LocalPlayer->ViewportClient) : nullptr;
	}

	/** 라우터에 걸린 입력 — 아직 아무 설정도 안 걸렸으면 None(기본값을 돌려주므로 두 기본값으로 가른다) */
	enum class EMode : uint8 { None, Game, Menu, All };
	EMode ModeOf(int32 PlayerId)
	{
		const UCommonUIActionRouterBase* Router = RouterOf(PlayerId);
		if (!Router || Router->GetActiveInputMode(ECommonInputMode::All) != Router->GetActiveInputMode(ECommonInputMode::Menu))
		{
			return EMode::None;
		}
		switch (Router->GetActiveInputMode())
		{
		case ECommonInputMode::Game: return EMode::Game;
		case ECommonInputMode::Menu: return EMode::Menu;
		default: return EMode::All;
		}
	}

	const TCHAR* ModeName(EMode Mode)
	{
		switch (Mode)
		{
		case EMode::Game: return TEXT("Game");
		case EMode::Menu: return TEXT("Menu");
		case EMode::All: return TEXT("All");
		default: return TEXT("None");
		}
	}

	UAstralActivatableWidget* TopOf(int32 PlayerId, EAstralUILayer Layer)
	{
		const UAstralRootLayout* Layout = LayoutOf(PlayerId);
		return Layout ? Layout->GetTopScreen(Layer) : nullptr;
	}

	UAstralScreenTestMenu* MenuOf(int32 PlayerId, EAstralUILayer Layer = EAstralUILayer::Menu) { return Cast<UAstralScreenTestMenu>(TopOf(PlayerId, Layer)); }

	double SpeedOf(int32 PlayerId)
	{
		const AAstralPlayerController* PC = SeatPC(PlayerId);
		const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
		return Pawn ? Pawn->GetVelocity().Size2D() : -1.0;
	}

	bool IsKeyDown(int32 PlayerId, const FKey& Key)
	{
		const AAstralPlayerController* PC = SeatPC(PlayerId);
		return PC && PC->IsInputKeyDown(Key);
	}

	/** 그 버튼(안쪽 SButton 포함)에 초점이 있는가 */
	bool HasFocus(int32 PlayerId, const UAstralScreenTestButton* Button)
	{
		AAstralPlayerController* PC = SeatPC(PlayerId);
		return PC && Button && (Button->HasUserFocus(PC) || Button->HasUserFocusedDescendants(PC));
	}

	bool IsGameRestored(int32 PlayerId)
	{
		const AAstralPlayerController* PC = SeatPC(PlayerId);
		const UGameViewportClient* Viewport = ViewportOf(PlayerId);
		return PC && Viewport && ModeOf(PlayerId) == EMode::Game && !PC->ShouldShowMouseCursor()
			&& Viewport->GetMouseCaptureMode() == EMouseCaptureMode::CapturePermanently_IncludingInitialMouseDown
			&& !TopOf(PlayerId, EAstralUILayer::Menu) && !TopOf(PlayerId, EAstralUILayer::Modal);
	}

	FString DescribeSeat(int32 PlayerId)
	{
		const AAstralPlayerController* PC = SeatPC(PlayerId);
		const UGameViewportClient* Viewport = ViewportOf(PlayerId);
		const UAstralRootLayout* Layout = LayoutOf(PlayerId);
		const UAstralActivatableWidget* Menu = TopOf(PlayerId, EAstralUILayer::Menu);
		const UAstralActivatableWidget* Modal = TopOf(PlayerId, EAstralUILayer::Modal);
		const TSharedPtr<SWidget> Focused = FSlateApplication::Get().GetUserFocusedWidget(0);
		return FString::Printf(TEXT("%d: map '%s' layout %d(active %d, screen %d) mode %s cursor %d capture %d menu %s(%d) modal %s(%d) speed %.0f | slate focus %s app active %d"), PlayerId,
			PC ? *MapOf(PC->GetWorld()) : TEXT("-"), Layout ? 1 : 0, (Layout && Layout->IsActivated()) ? 1 : 0, AstralUITest::IsOnScreen(Layout) ? 1 : 0, ModeName(ModeOf(PlayerId)),
			(PC && PC->ShouldShowMouseCursor()) ? 1 : 0, Viewport ? static_cast<int32>(Viewport->GetMouseCaptureMode()) : -1,
			*GetNameSafe(Menu), (Menu && Menu->IsActivated()) ? 1 : 0, *GetNameSafe(Modal), (Modal && Modal->IsActivated()) ? 1 : 0, SpeedOf(PlayerId),
			Focused ? *Focused->GetTypeAsString() : TEXT("-"), FSlateApplication::Get().IsActive() ? 1 : 0);
	}

	FString Describe(const FContext& Ctx)
	{
		FString Out = FString::Printf(TEXT("server map '%s'"), *MapOf(FindServerWorld()));
		for (const int32 PlayerId : Ctx.Ids)
		{
			Out += TEXT(" | seat ") + DescribeSeat(PlayerId);
		}
		return Out;
	}

	void Wait(const TSharedRef<FContext>& Ctx, const FString& What, double TimeoutSeconds, TFunction<bool()> Condition)
	{
		WaitUntil(Ctx, *What, TimeoutSeconds, MoveTemp(Condition), [Ctx]() { return Describe(*Ctx); });
	}

	// ─── 조작 ───

	/** 자리의 창에 초점 — 사람이 그 창을 누른 것과 같다 */
	void FocusSeat(int32 PlayerId)
	{
		if (const UGameViewportClient* Viewport = ViewportOf(PlayerId))
		{
			FSlateApplication::Get().SetUserFocus(0, Viewport->GetGameViewportWidget(), EFocusCause::SetDirectly);
		}
	}

	/** 자리의 뷰포트 클라이언트에 키 하나 — 돌려주는 값은 '처리됨'(게임에 안 갔거나 게임이 먹었다) */
	bool SendKey(int32 PlayerId, const FKey& Key, EInputEvent Event)
	{
		UGameViewportClient* Viewport = ViewportOf(PlayerId);
		if (!Viewport || !Viewport->Viewport)
		{
			return false;
		}
		const FInputDeviceId Device = IPlatformInputDeviceMapper::Get().GetDefaultInputDevice();
		return Viewport->InputKey(FInputKeyEventArgs(Viewport->Viewport, Device, Key, Event, FPlatformTime::Cycles64()));
	}

	void Tap(int32 PlayerId, const FKey& Key)
	{
		SendKey(PlayerId, Key, IE_Pressed);
		SendKey(PlayerId, Key, IE_Released);
	}

	/** Slate 로 들어가는 키 — 초점이 있는 위젯부터 */
	void SlateTap(const FKey& Key)
	{
		const FKeyEvent Event(Key, FModifierKeysState(), /*UserIndex*/ 0, /*bIsRepeat*/ false, 0, 0);
		FSlateApplication::Get().ProcessKeyDownEvent(Event);
		FSlateApplication::Get().ProcessKeyUpEvent(Event);
	}

	template <class ScreenT>
	ScreenT* Open(const TSharedRef<FContext>& Ctx, int32 PlayerId, EAstralUILayer Layer = EAstralUILayer::Menu)
	{
		UAstralUISubsystem* UI = UIOf(PlayerId);
		ScreenT* Screen = UI ? Cast<ScreenT>(UI->OpenScreen(ScreenT::StaticClass(), Layer)) : nullptr;
		if (!Ctx->Test->TestNotNull(TEXT("the screen opened"), Screen))
		{
			Ctx->bAborted = true;
		}
		return Screen;
	}

	bool SetContextScreens(const TSharedRef<FContext>& Ctx, int32 PlayerId, const TArray<FAstralContextScreen>& Screens)
	{
		AAstralPlayerController* PC = SeatPC(PlayerId);
		AAstralGameState* GameState = PC ? PC->GetWorld()->GetGameState<AAstralGameState>() : nullptr;
		const FArrayProperty* Property = FindFProperty<FArrayProperty>(AAstralGameState::StaticClass(), TEXT("ContextScreens"));
		UAstralRootLayout* Layout = LayoutOf(PlayerId);
		if (!Ctx->Test->TestNotNull(TEXT("game state on the seat"), GameState) || !Ctx->Test->TestNotNull(TEXT("ContextScreens property"), Property) || !Ctx->Test->TestNotNull(TEXT("layout"), Layout))
		{
			Ctx->bAborted = true;
			return false;
		}
		*Property->ContainerPtrToValuePtr<TArray<FAstralContextScreen>>(GameState) = Screens;
		Layout->ApplyContext(GameState);
		return true;
	}

	/** A 의 입력 모드 변화를 적기 시작 · 그만 */
	void WatchModes(const TSharedRef<FContext>& Ctx, bool bWatch)
	{
		UCommonUIActionRouterBase* Router = RouterOf(Ctx->Ids[0]);
		if (!Router)
		{
			return;
		}
		if (bWatch)
		{
			Ctx->ModeChanges.Reset();
			TWeakPtr<FContext> WeakCtx = Ctx;
			Ctx->ModeChangedHandle = Router->OnActiveInputModeChanged().AddLambda([WeakCtx](ECommonInputMode Mode)
			{
				if (const TSharedPtr<FContext> Pinned = WeakCtx.Pin())
				{
					Pinned->ModeChanges.Add(Mode);
				}
			});
		}
		else
		{
			Router->OnActiveInputModeChanged().Remove(Ctx->ModeChangedHandle);
		}
	}

	// ─── 단계 ───

	void EnqueueSetup(const TSharedRef<FContext>& Ctx)
	{
		RequestPie(Ctx, HubMapPath, Ctx->bDedicated ? PIE_Client : PIE_ListenServer, NumPlayers);
		Wait(Ctx, TEXT("both players in HubMap with a pawn and a layout"), 240.0, []()
		{
			const UWorld* ServerWorld = FindServerWorld();
			if (!ServerWorld || !ServerWorld->HasBegunPlay() || MapOf(ServerWorld) != HubMap || GetSeatWorlds().Num() != NumPlayers)
			{
				return false;
			}
			for (const UWorld* World : GetSeatWorlds())
			{
				const AAstralPlayerController* PC = GetLocalPC(World);
				const UAstralUISubsystem* UI = UAstralUISubsystem::Get(PC);
				if (LocalPlayerIdIn(World) == 0 || !PC->GetPawn() || !World->GetGameState() || !UI || !UI->GetRootLayout())
				{
					return false;
				}
			}
			return true;
		});
		Hold(Ctx, 1.0);   // 폰 초기화 · 첫 그리기

		// U0
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			TArray<int32> ClientIds;
			TArray<int32> AllIds;
			for (const UWorld* World : GetSeatWorlds())
			{
				AllIds.Add(LocalPlayerIdIn(World));
				if (World->GetNetMode() == NM_Client)
				{
					ClientIds.Add(LocalPlayerIdIn(World));
				}
			}
			ClientIds.Sort();
			if (!Test.TestTrue(TEXT("a client seat exists"), ClientIds.Num() > 0))
			{
				Ctx->bAborted = true;
				return;
			}
			Ctx->Ids = { ClientIds[0] };
			for (const int32 PlayerId : AllIds)
			{
				if (PlayerId != ClientIds[0])
				{
					Ctx->Ids.Add(PlayerId);
				}
			}

			for (const int32 PlayerId : Ctx->Ids)
			{
				const UAstralRootLayout* Layout = LayoutOf(PlayerId);
				Test.TestTrue(TEXT("U0: the layout is on the screen"), AstralUITest::IsOnScreen(Layout));
				Test.TestTrue(TEXT("U0: the layout is always active"), Layout && Layout->IsActivated());
				Test.TestTrue(TEXT("U0: the viewport client is CommonUI's"), Cast<UCommonGameViewportClient>(ViewportOf(PlayerId)) != nullptr);
				Test.TestNull(TEXT("U0: no combat HUD in the hub"), SeatPC(PlayerId)->GetCombatHUDWidget());
				Test.TestNull(TEXT("U0: no status HUD in the hub"), SeatPC(PlayerId)->GetStatusHUDWidget());
				Test.TestNull(TEXT("U0: no menu screen at start"), TopOf(PlayerId, EAstralUILayer::Menu));
			}

			const FUIInputAction* Back = UCommonUIInputSettings::Get().FindAction(FUIActionTag::TryConvert(FGameplayTag::RequestGameplayTag(BackTagName)));
			if (Test.TestNotNull(TEXT("U0: the back action is in DefaultInput.ini"), Back))
			{
				const auto Has = [Back](const FKey& Key) { return Back->KeyMappings.ContainsByPredicate([Key](const FUIActionKeyMapping& M) { return M.Key == Key; }); };
				Test.TestTrue(TEXT("U0: back = Escape"), Has(EKeys::Escape));
				Test.TestTrue(TEXT("U0: back = gamepad B"), Has(EKeys::Gamepad_FaceButton_Right));
			}
			Note(Test, FString::Printf(TEXT("U0: %s — %s"), Ctx->bDedicated ? TEXT("dedicated") : TEXT("listen"), *Describe(*Ctx)));
		});
	}

	void EnqueueOpen(const TSharedRef<FContext>& Ctx)
	{
		// U1
		Do(Ctx, [Ctx]()
		{
			FocusSeat(Ctx->Ids[0]);
			SendKey(Ctx->Ids[0], EKeys::W, IE_Pressed);
		});
		Wait(Ctx, TEXT("U1: W moves A's pawn before any screen is open"), 5.0, [Ctx]() { return IsKeyDown(Ctx->Ids[0], EKeys::W) && SpeedOf(Ctx->Ids[0]) > MovingSpeed; });

		// U2 — W 를 누른 채 연다
		Do(Ctx, [Ctx]() { Open<UAstralScreenTestMenu>(Ctx, Ctx->Ids[0]); });
		Wait(Ctx, TEXT("U2: menu input, cursor, no mouse capture, first focus on the first button"), 5.0, [Ctx]()
		{
			const int32 A = Ctx->Ids[0];
			const UAstralScreenTestMenu* Menu = MenuOf(A);
			return Menu && Menu->IsActivated() && AstralUITest::IsOnScreen(Menu) && ModeOf(A) == EMode::Menu && SeatPC(A)->ShouldShowMouseCursor()
				&& ViewportOf(A)->GetMouseCaptureMode() == EMouseCaptureMode::NoCapture && HasFocus(A, Menu->FirstButton);
		});
		Wait(Ctx, TEXT("U2: the key held while opening is released and the pawn stops"), 5.0, [Ctx]() { return !IsKeyDown(Ctx->Ids[0], EKeys::W) && SpeedOf(Ctx->Ids[0]) < StillSpeed; });
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestTrue(TEXT("U2: the router swallows W while the menu is open"), SendKey(Ctx->Ids[0], EKeys::W, IE_Pressed));
			Note(*Ctx->Test, FString::Printf(TEXT("U2: open — %s"), *Describe(*Ctx)));
		});
		Hold(Ctx, 0.5);
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestFalse(TEXT("U2: W does not reach the game"), IsKeyDown(Ctx->Ids[0], EKeys::W));
			Ctx->Test->TestTrue(TEXT("U2: the pawn stays"), SpeedOf(Ctx->Ids[0]) < StillSpeed);
			SendKey(Ctx->Ids[0], EKeys::W, IE_Released);
			UAstralUISubsystem* UI = UIOf(Ctx->Ids[0]);
			Ctx->Test->TestTrue(TEXT("U2: opening the same screen again returns the one on top"), UI && UI->OpenScreen(UAstralScreenTestMenu::StaticClass()) == TopOf(Ctx->Ids[0], EAstralUILayer::Menu));
		});

		// U3 — 그동안 B
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const int32 B = Ctx->Ids[1];
			Test.TestTrue(TEXT("U3: B is not in menu input"), ModeOf(B) != EMode::Menu);
			Test.TestNull(TEXT("U3: B has no screen"), TopOf(B, EAstralUILayer::Menu));
			SendKey(B, EKeys::W, IE_Pressed);
		});
		Wait(Ctx, TEXT("U3: W still moves B's pawn while A's menu is open"), 5.0, [Ctx]() { return IsKeyDown(Ctx->Ids[1], EKeys::W) && SpeedOf(Ctx->Ids[1]) > MovingSpeed; });
		Do(Ctx, [Ctx]()
		{
			SendKey(Ctx->Ids[1], EKeys::W, IE_Released);
			Ctx->Test->TestTrue(TEXT("U3: A's menu is still open"), ModeOf(Ctx->Ids[0]) == EMode::Menu && MenuOf(Ctx->Ids[0]) && MenuOf(Ctx->Ids[0])->IsActivated());
			Note(*Ctx->Test, FString::Printf(TEXT("U3: %s"), *Describe(*Ctx)));
		});
	}

	/** 버튼이 지금 어떤 모양인가 — 기록용 */
	FString DescribeButton(int32 PlayerId, const UAstralScreenTestButton* Button)
	{
		const TSharedPtr<SWidget> Inner = Button ? Button->GetInnerSlateButton() : nullptr;
		const TSharedPtr<SWidget> Outer = Button ? Button->GetCachedWidget() : nullptr;
		const auto ShowsFocus = [](const TSharedPtr<SWidget>& Widget) { const TOptional<EFocusCause> Cause = Widget ? Widget->HasUserFocus(0) : TOptional<EFocusCause>(); return Cause.IsSet() ? static_cast<int32>(Cause.GetValue()) : -1; };
		return FString::Printf(TEXT("focus %d hovered %d(umg %d) focus cause outer %d inner %d"), HasFocus(PlayerId, Button) ? 1 : 0, (Inner && Inner->IsHovered()) ? 1 : 0, (Button && Button->IsHovered()) ? 1 : 0,
			ShowsFocus(Outer), ShowsFocus(Inner));
	}

	void EnqueueKeyboardFocus(const TSharedRef<FContext>& Ctx)
	{
		// U4
		Do(Ctx, [Ctx]()
		{
			const UAstralScreenTestMenu* Menu = MenuOf(Ctx->Ids[0]);
			const UCommonInputSubsystem* Input = UCommonInputSubsystem::Get(SeatPC(Ctx->Ids[0])->GetLocalPlayer());
			Note(*Ctx->Test, FString::Printf(TEXT("U4: before — first [%s] second [%s], input type %d, RenderFocusRule %d"), *DescribeButton(Ctx->Ids[0], Menu->FirstButton), *DescribeButton(Ctx->Ids[0], Menu->SecondButton),
				Input ? static_cast<int32>(Input->GetCurrentInputType()) : -1, static_cast<int32>(GetDefault<UUserInterfaceSettings>()->RenderFocusRule)));
			SlateTap(EKeys::Down);
		});
		Wait(Ctx, TEXT("U4: the down arrow moves the focus to the second button"), 3.0, [Ctx]() { const UAstralScreenTestMenu* Menu = MenuOf(Ctx->Ids[0]); return Menu && HasFocus(Ctx->Ids[0], Menu->SecondButton); });
		Hold(Ctx, 0.3);
		Do(Ctx, [Ctx]()
		{
			const UAstralScreenTestMenu* Menu = MenuOf(Ctx->Ids[0]);
			Note(*Ctx->Test, FString::Printf(TEXT("U4: after down arrow — first [%s] second [%s]"), *DescribeButton(Ctx->Ids[0], Menu->FirstButton), *DescribeButton(Ctx->Ids[0], Menu->SecondButton)));
			SlateTap(EKeys::Up);
		});
		Wait(Ctx, TEXT("U4: the up arrow moves the focus back"), 3.0, [Ctx]() { const UAstralScreenTestMenu* Menu = MenuOf(Ctx->Ids[0]); return Menu && HasFocus(Ctx->Ids[0], Menu->FirstButton); });
	}

	void EnqueueStack(const TSharedRef<FContext>& Ctx)
	{
		// U5
		Do(Ctx, [Ctx]()
		{
			WatchModes(Ctx, true);
			Open<UAstralScreenTestSubMenu>(Ctx, Ctx->Ids[0]);
		});
		Wait(Ctx, TEXT("U5: the second screen is on top with the focus"), 5.0, [Ctx]()
		{
			const UAstralScreenTestMenu* Top = MenuOf(Ctx->Ids[0]);
			return Top && Top->IsA<UAstralScreenTestSubMenu>() && Top->IsActivated() && ModeOf(Ctx->Ids[0]) == EMode::Menu && HasFocus(Ctx->Ids[0], Top->FirstButton);
		});
		Do(Ctx, [Ctx]() { SlateTap(EKeys::Gamepad_FaceButton_Right); });   // Slate 길 — 초점이 있는 버튼 → 뷰포트 → 라우터
		Wait(Ctx, TEXT("U5: back closes only the second screen"), 5.0, [Ctx]()
		{
			const UAstralScreenTestMenu* Top = MenuOf(Ctx->Ids[0]);
			return Top && !Top->IsA<UAstralScreenTestSubMenu>() && Top->IsActivated() && ModeOf(Ctx->Ids[0]) == EMode::Menu && HasFocus(Ctx->Ids[0], Top->FirstButton);
		});
		Hold(Ctx, 0.3);
		Do(Ctx, [Ctx]()
		{
			WatchModes(Ctx, false);
			Ctx->Test->TestTrue(TEXT("U5: the first screen stays open"), MenuOf(Ctx->Ids[0]) && MenuOf(Ctx->Ids[0])->IsActivated());
			Ctx->Test->TestEqual(TEXT("U5: stacking and going back never leave menu input in between"), Ctx->ModeChanges.Num(), 0);
			Tap(Ctx->Ids[0], EKeys::Gamepad_FaceButton_Right);
		});
		Wait(Ctx, TEXT("U5: back again closes the last screen and game input returns"), 5.0, [Ctx]() { return IsGameRestored(Ctx->Ids[0]); });
		Do(Ctx, [Ctx]() { SendKey(Ctx->Ids[0], EKeys::W, IE_Pressed); });
		Wait(Ctx, TEXT("U5: W moves A's pawn again"), 5.0, [Ctx]() { return IsKeyDown(Ctx->Ids[0], EKeys::W) && SpeedOf(Ctx->Ids[0]) > MovingSpeed; });
		Do(Ctx, [Ctx]()
		{
			SendKey(Ctx->Ids[0], EKeys::W, IE_Released);
			Note(*Ctx->Test, FString::Printf(TEXT("U5: closed — %s"), *Describe(*Ctx)));
		});

		// U6 — 메뉴 위에 Modal
		Do(Ctx, [Ctx]()
		{
			FocusSeat(Ctx->Ids[0]);
			Open<UAstralScreenTestMenu>(Ctx, Ctx->Ids[0]);
		});
		Wait(Ctx, TEXT("U6: the menu is open"), 5.0, [Ctx]() { return MenuOf(Ctx->Ids[0]) && ModeOf(Ctx->Ids[0]) == EMode::Menu && HasFocus(Ctx->Ids[0], MenuOf(Ctx->Ids[0])->FirstButton); });
		Do(Ctx, [Ctx]()
		{
			WatchModes(Ctx, true);
			Open<UAstralScreenTestDialog>(Ctx, Ctx->Ids[0], EAstralUILayer::Modal);
		});
		Wait(Ctx, TEXT("U6: the dialog has the focus above the menu"), 5.0, [Ctx]()
		{
			const UAstralScreenTestMenu* Dialog = MenuOf(Ctx->Ids[0], EAstralUILayer::Modal);
			return Dialog && Dialog->IsActivated() && HasFocus(Ctx->Ids[0], Dialog->FirstButton);
		});
		Do(Ctx, [Ctx]()
		{
			const UAstralScreenTestMenu* Menu = MenuOf(Ctx->Ids[0]);
			Ctx->Test->TestTrue(TEXT("U6: the menu below stays active"), Menu && Menu->IsActivated());
			Tap(Ctx->Ids[0], EKeys::Gamepad_FaceButton_Right);
		});
		Wait(Ctx, TEXT("U6: back closes only the dialog"), 5.0, [Ctx]()
		{
			const UAstralScreenTestMenu* Menu = MenuOf(Ctx->Ids[0]);
			return !TopOf(Ctx->Ids[0], EAstralUILayer::Modal) && Menu && Menu->IsActivated() && ModeOf(Ctx->Ids[0]) == EMode::Menu && HasFocus(Ctx->Ids[0], Menu->FirstButton);
		});
		Hold(Ctx, 0.3);
		Do(Ctx, [Ctx]()
		{
			WatchModes(Ctx, false);
			Ctx->Test->TestTrue(TEXT("U6: the menu is still open"), MenuOf(Ctx->Ids[0]) && MenuOf(Ctx->Ids[0])->IsActivated());
			Ctx->Test->TestEqual(TEXT("U6: the dialog never leaves menu input in between"), Ctx->ModeChanges.Num(), 0);
			Tap(Ctx->Ids[0], EKeys::Gamepad_FaceButton_Right);
		});
		Wait(Ctx, TEXT("U6: back again closes the menu and game input returns"), 5.0, [Ctx]() { return IsGameRestored(Ctx->Ids[0]); });
	}

	void EnqueueContextScreens(const TSharedRef<FContext>& Ctx)
	{
		// U7 — 뒤로 태그를 여는 액션으로도 쓴다(Game 입력에서는 열기, Menu 입력에서는 닫기) — ini 에 있는 액션이 이것뿐이다
		Do(Ctx, [Ctx]()
		{
			FAstralContextScreen Screen;
			Screen.ActionTag = FUIActionTag::TryConvert(FGameplayTag::RequestGameplayTag(BackTagName));
			Screen.ScreenClass = UAstralScreenTestMenu::StaticClass();
			if (SetContextScreens(Ctx, Ctx->Ids[0], { Screen }))
			{
				FocusSeat(Ctx->Ids[0]);
			}
		});
		Hold(Ctx, 0.3);   // 묶음은 다음 틱에 나무에 붙는다
		Do(Ctx, [Ctx]()
		{
			Tap(Ctx->Ids[0], EKeys::Gamepad_FaceButton_Right);
			Tap(Ctx->Ids[1], EKeys::Gamepad_FaceButton_Right);
		});
		Wait(Ctx, TEXT("U7: the action opens the screen of the map's list"), 5.0, [Ctx]()
		{
			const UAstralScreenTestMenu* Menu = MenuOf(Ctx->Ids[0]);
			return Menu && Menu->IsActivated() && ModeOf(Ctx->Ids[0]) == EMode::Menu && HasFocus(Ctx->Ids[0], Menu->FirstButton);
		});
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestNull(TEXT("U7: B has no such screen"), TopOf(Ctx->Ids[1], EAstralUILayer::Menu));
			Tap(Ctx->Ids[0], EKeys::Gamepad_FaceButton_Right);
		});
		Wait(Ctx, TEXT("U7: the same key closes it (and does not reopen it)"), 5.0, [Ctx]() { return IsGameRestored(Ctx->Ids[0]); });
		Hold(Ctx, 0.3);
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestTrue(TEXT("U7: it stays closed"), IsGameRestored(Ctx->Ids[0]));
			SetContextScreens(Ctx, Ctx->Ids[0], {});
		});
		Hold(Ctx, 0.2);
		Do(Ctx, [Ctx]() { Tap(Ctx->Ids[0], EKeys::Gamepad_FaceButton_Right); });
		Hold(Ctx, 0.3);
		Do(Ctx, [Ctx]() { Ctx->Test->TestNull(TEXT("U7: an emptied list opens nothing"), TopOf(Ctx->Ids[0], EAstralUILayer::Menu)); });
	}

	void EnqueueTravel(const TSharedRef<FContext>& Ctx)
	{
		// U8 — A 의 화면을 연 채 이동
		Do(Ctx, [Ctx]()
		{
			FocusSeat(Ctx->Ids[0]);
			Open<UAstralScreenTestMenu>(Ctx, Ctx->Ids[0]);
		});
		Wait(Ctx, TEXT("U8: A's menu is open before the travel"), 5.0, [Ctx]() { return ModeOf(Ctx->Ids[0]) == EMode::Menu; });
		Do(Ctx, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Ids)
			{
				Ctx->OldLayouts.Add(PlayerId, LayoutOf(PlayerId));
				Ctx->OldControllers.Add(PlayerId, SeatPC(PlayerId));
			}
			const AAstralGameState* GameState = FindServerWorld()->GetGameState<AAstralGameState>();
			const APlayerState* Leader = GameState ? GameState->GetPartyLeader() : nullptr;
			AAstralPlayerController* LeaderPC = Leader ? SeatPC(Leader->GetPlayerId()) : nullptr;
			if (!Ctx->Test->TestNotNull(TEXT("leader seat"), LeaderPC))
			{
				Ctx->bAborted = true;
				return;
			}
			LeaderPC->ServerSelectRaid(RaidMap);
			for (const int32 PlayerId : Ctx->Ids)
			{
				SeatPC(PlayerId)->ServerSetReady(true);
			}
		});
		Wait(Ctx, TEXT("U8: everyone ready"), 20.0, []()
		{
			const AAstralHubGameState* HubGameState = FindServerWorld() ? FindServerWorld()->GetGameState<AAstralHubGameState>() : nullptr;
			return HubGameState && HubGameState->AreAllPlayersReady() && HubGameState->GetSelectedRaid().IsSet();
		});
		Do(Ctx, [Ctx]()
		{
			const APlayerState* Leader = FindServerWorld()->GetGameState<AAstralGameState>()->GetPartyLeader();
			SeatPC(Leader->GetPlayerId())->ServerStartRaid();
		});
		Wait(Ctx, TEXT("U8: both seats are in RaidMap with a new layout and both HUDs"), 180.0, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Ids)
			{
				const AAstralPlayerController* PC = SeatPC(PlayerId);
				if (!PC || MapOf(PC->GetWorld()) != RaidMap || !PC->GetPawn() || !LayoutOf(PlayerId) || LayoutOf(PlayerId) == Ctx->OldLayouts.FindRef(PlayerId).Get()
					|| !PC->GetCombatHUDWidget() || !PC->GetStatusHUDWidget())
				{
					return false;
				}
			}
			return true;
		});
		Hold(Ctx, 1.0);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			for (const int32 PlayerId : Ctx->Ids)
			{
				AAstralPlayerController* PC = SeatPC(PlayerId);
				const UAstralRootLayout* Layout = LayoutOf(PlayerId);
				Test.TestTrue(TEXT("U8: the new layout is on the screen and active"), AstralUITest::IsOnScreen(Layout) && Layout->IsActivated());
				const UAstralRootLayout* OldLayout = Ctx->OldLayouts.FindRef(PlayerId).Get();
				Test.TestFalse(TEXT("U8: the old layout is gone from the screen"), OldLayout && OldLayout->IsInViewport());
				Test.TestNull(TEXT("U8: no screen came along"), TopOf(PlayerId, EAstralUILayer::Menu));
				Test.TestTrue(TEXT("U8: the HUDs are on the screen"), AstralUITest::IsOnScreen(PC->GetCombatHUDWidget()) && AstralUITest::IsOnScreen(PC->GetStatusHUDWidget()));
				Test.TestTrue(TEXT("U8: menu input did not come along"), ModeOf(PlayerId) != EMode::Menu);
				Test.TestFalse(TEXT("U8: the move input is not left ignored"), PC->IsMoveInputIgnored());
				// 엔진(AGameModeBase::HandleSeamlessTravelPlayer)이 컨트롤러를 새로 만든다 — 레이아웃을 다시 세우는 통지(PlayerControllerChanged)가 여기에 기댄다
				Test.TestTrue(TEXT("U8: the travel replaced the controller"), Ctx->OldControllers.FindRef(PlayerId).Get() != PC);
				SendKey(PlayerId, EKeys::W, IE_Pressed);
			}
			Note(Test, FString::Printf(TEXT("U8: %s"), *Describe(*Ctx)));
		});
		Wait(Ctx, TEXT("U8: W moves both pawns in the raid"), 10.0, [Ctx]()
		{
			return SpeedOf(Ctx->Ids[0]) > MovingSpeed && SpeedOf(Ctx->Ids[1]) > MovingSpeed;
		});
		Do(Ctx, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Ids)
			{
				SendKey(PlayerId, EKeys::W, IE_Released);
			}

			// 같은 WBP 를 예전 방식(뷰포트에 직접)으로 나란히 띄운다
			AAstralPlayerController* PC = SeatPC(Ctx->Ids[0]);
			for (UUserWidget* Hud : { static_cast<UUserWidget*>(PC->GetStatusHUDWidget()), static_cast<UUserWidget*>(PC->GetCombatHUDWidget()) })
			{
				UUserWidget* Twin = CreateWidget<UUserWidget>(PC, Hud->GetClass());
				Twin->AddToViewport(0);
				Ctx->Twins.Add(TStrongObjectPtr<UUserWidget>(Twin));
			}
		});
		Hold(Ctx, 0.7);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			AAstralPlayerController* PC = SeatPC(Ctx->Ids[0]);
			const UUserWidget* Huds[] = { PC->GetStatusHUDWidget(), PC->GetCombatHUDWidget() };
			for (int32 Index = 0; Index < Ctx->Twins.Num(); ++Index)
			{
				int32 Compared = 0;
				int32 Painted = 0;
				FString Different;
				Ctx->Twins[Index]->WidgetTree->ForEachWidget([&](UWidget* TwinPart)
				{
					const UWidget* Part = Huds[Index]->GetWidgetFromName(TwinPart->GetFName());
					if (!Part)
					{
						Different += FString::Printf(TEXT(" %s(missing)"), *TwinPart->GetName());
						return;
					}
					const FGeometry& A = Part->GetPaintSpaceGeometry();
					const FGeometry& B = TwinPart->GetPaintSpaceGeometry();
					++Compared;
					Painted += A.GetAbsoluteSize().IsNearlyZero() ? 0 : 1;
					if (!FVector2D(A.GetAbsolutePosition()).Equals(FVector2D(B.GetAbsolutePosition()), 0.01) || !FVector2D(A.GetAbsoluteSize()).Equals(FVector2D(B.GetAbsoluteSize()), 0.01))
					{
						Different += FString::Printf(TEXT(" %s(%s %s / %s %s)"), *TwinPart->GetName(), *FVector2D(A.GetAbsolutePosition()).ToString(), *FVector2D(A.GetAbsoluteSize()).ToString(),
							*FVector2D(B.GetAbsolutePosition()).ToString(), *FVector2D(B.GetAbsoluteSize()).ToString());
					}
				});
				Test.TestTrue(*FString::Printf(TEXT("U8: %s is drawn where a viewport widget would be:%s"), *Huds[Index]->GetClass()->GetName(), *Different), Different.IsEmpty());
				Test.TestTrue(TEXT("U8: ... and it is really painted"), Painted > 0);
				Note(Test, FString::Printf(TEXT("U8: %s geometry — %d widgets compared, %d painted, different:%s"), *Huds[Index]->GetClass()->GetName(), Compared, Painted, Different.IsEmpty() ? TEXT(" none") : *Different));
				Ctx->Twins[Index]->RemoveFromParent();
			}
			Ctx->Twins.Reset();

			// U9
			FocusSeat(Ctx->Ids[0]);
			Open<UAstralScreenTestMenu>(Ctx, Ctx->Ids[0]);
		});
		Wait(Ctx, TEXT("U9: the screen opens in the raid"), 5.0, [Ctx]()
		{
			const UAstralScreenTestMenu* Menu = MenuOf(Ctx->Ids[0]);
			return Menu && Menu->IsActivated() && ModeOf(Ctx->Ids[0]) == EMode::Menu && SeatPC(Ctx->Ids[0])->ShouldShowMouseCursor() && HasFocus(Ctx->Ids[0], Menu->FirstButton);
		});
		Do(Ctx, [Ctx]() { Tap(Ctx->Ids[0], EKeys::Gamepad_FaceButton_Right); });
		Wait(Ctx, TEXT("U9: back closes it and game input returns"), 5.0, [Ctx]() { return IsGameRestored(Ctx->Ids[0]); });
		Do(Ctx, [Ctx]() { Note(*Ctx->Test, FString::Printf(TEXT("U9: %s"), *Describe(*Ctx))); });
	}

	void EnqueueAll(FAutomationTestBase& Test, bool bDedicated)
	{
		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;
		Ctx->bDedicated = bDedicated;
		EnqueueSetup(Ctx);
		EnqueueOpen(Ctx);
		EnqueueKeyboardFocus(Ctx);
		EnqueueStack(Ctx);
		EnqueueContextScreens(Ctx);
		EnqueueTravel(Ctx);
		EndPie(Ctx);
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralScreenStackListenPieTest, "AstralBreak.UI.ScreenStack.ListenPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralScreenStackListenPieTest::RunTest(const FString& Parameters)
{
	AstralScreenStackPie::EnqueueAll(*this, /*bDedicated*/ false);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralScreenStackDedicatedPieTest, "AstralBreak.UI.ScreenStack.DedicatedPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralScreenStackDedicatedPieTest::RunTest(const FString& Parameters)
{
	AstralScreenStackPie::EnqueueAll(*this, /*bDedicated*/ true);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
