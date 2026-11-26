// 허브 준비 화면 시험 — 한 프로세스 멀티 PIE 2인 + 늦은 입장 1 (설계 Docs/Design/ui-autogen-pipeline.md §11 'Phase 3 설계' ④ · 'Phase 3-4 결과')
//
// 리슨 · Dedicated 를 PIE 로 띄워 승격본 WBP_HubReady 를 허브 GameState 의 여는 액션(Tab)으로 열고, 실제 Slate 길로 누른다:
// 버튼 가운데 좌표로 그 자리의 창 히트 테스트(FSlateApplication::LocateWindowUnderMouse)를 하고 그 길로 마우스 이동 · 눌림 · 뗌을 흘린다
// (한 프로세스 다인 PIE 의 창끼리 겹치는 OS 창 순서만 건너뛴다 — 게임 창 하나에서는 없는 문제). 판정의 기대값은 서버 월드의 값으로 따로 계산한다.
// 사람(자리)은 PlayerId 로 부른다 — L = 처음 방장, N = 처음 방장 아닌 사람, J = 늦게 들어온 사람.
//
//   ⓗ  먼저 시험 도구가 틀린 것을 잡는가 — 버튼 밖 좌표 · 버튼을 덮은 visible 그림은 히트 길이 버튼에 안 닿고 눌러도 아무 일도 없다
//   ①  Tab 으로 열면 메뉴 입력 · 커서 · 마우스 안 잡음 · 첫 초점 = 준비, 눌러 둔 W 가 풀리고 폰이 선다. 처음 그림의 빈 줄은 접힌다
//   ②  N 이 준비를 누르면 서버 값 → 두 자리의 N 줄 '준비 완료' · N 의 준비 버튼 선택 모양
//   ③  N 의 목적지 · 출정은 꺼져 있고(가리는 것 없이 버튼 위인데 히트 길이 꺼진 버튼에서 잘린다) 눌러도 요청이 안 나간다
//   ④  L 이 목적지를 누르면 두 자리 선택 모양. 목적지 글자는 GameState 목록의 보이는 이름이다(목록 값을 바꾸면 따라 바뀐다)
//   ⑤  준비 안 된 채 서버에 직접 출정 → 거절 → 이유 줄에 거절 글 → 3초 뒤 지금 상태의 까닭
//   ⑥  늦게 들어온 J 가 지금 상태를 보고, 앞 두 자리에 J 줄이 생긴다
//   ⑦  (Dedicated) 방장이 나가면 다음 사람의 목적지가 켜진다 — 리슨은 방장 = 호스트라 나갈 수 없다
//   ⑧  게임패드 방향(위 · 아래) + A 로 준비
//   ⑩  닫기는 맨 위 화면만 — 위에 다른 화면이 있으면 Tab 은 아무것도 안 닫고, 뒤로가 위 화면만 닫고, 그다음 Tab 이 준비 화면을 닫는다(다시 열리지 않는다)
//   ⑨  모두 준비 → 방장이 출정 클릭 → RaidMap, 화면이 닫히고 입력이 게임으로 돌아온다

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AstralPieTestHelpers.h"
#include "AstralScreenStackTestWidgets.h"
#include "AstralUITestHelpers.h"

#include "Blueprint/WidgetTree.h"
#include "CommonButtonBase.h"
#include "CommonInputModeTypes.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/Image.h"
#include "Components/TextBlock.h"
#include "Engine/GameInstance.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/InputDeviceSubsystem.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerState.h"
#include "GameModes/AstralHubGameState.h"
#include "GameModes/AstralLobbyRules.h"
#include "GenericPlatform/GenericPlatformInputDeviceMapper.h"
#include "Input/CommonUIActionRouterBase.h"
#include "Input/CommonUIInputSettings.h"
#include "InputCoreTypes.h"
#include "InputKeyEventArgs.h"
#include "Layout/Children.h"
#include "Layout/WidgetPath.h"
#include "Player/AstralPlayerController.h"
#include "Player/AstralPlayerState.h"
#include "UI/Foundation/AstralButtonBase.h"
#include "UI/Foundation/AstralRootLayout.h"
#include "UI/Foundation/AstralUISubsystem.h"
#include "UI/Screens/AstralHubMemberRowWidget.h"
#include "UI/Screens/AstralHubReadyWidget.h"
#include "UnrealClient.h"
#include "Widgets/SViewport.h"
#include "Widgets/SWindow.h"

namespace AstralHubReadyPie
{
	using namespace AstralPieTest;

	const TCHAR* const HubMapPath = TEXT("/Game/Maps/HubMap");
	const TCHAR* const HubMap = TEXT("HubMap");
	const TCHAR* const RaidMap = TEXT("RaidMap");
	const TCHAR* const HubReadyTagName = TEXT("UI.Action.HubReady");
	const TCHAR* const HubReadyClassPath = TEXT("/Game/UI/Screens/HubReady/WBP_HubReady.WBP_HubReady_C");

	constexpr int32 NumPlayers = 2;
	constexpr int32 NumRows = 4;
	constexpr double MovingSpeed = 50.0;
	constexpr double StillSpeed = 5.0;

	const FName ReadyName(TEXT("ReadyButton"));
	const FName DestinationName(TEXT("DestinationButton"));
	const FName LaunchName(TEXT("LaunchButton"));

	struct FContext : FContextBase
	{
		bool bDedicated = false;

		int32 L = 0;   // 처음 방장
		int32 N = 0;   // 처음 방장 아닌 사람
		int32 J = 0;   // 늦게 들어온 사람
		int32 Leader = 0;   // 지금 방장(⑦ 뒤 N)

		/** 화면을 연 자리 — 서버 값과 견준다 */
		TArray<int32> Open;

		/** 자리별 거절 통지 횟수(OnLobbyRequestDenied) */
		TMap<int32, int32> Denials;

		/** 자리 · 버튼별 누름 횟수(버튼의 OnClicked) */
		TMap<FString, int32> Clicks;

		/** ⑤ 거절 글이 처음 보인 때 */
		double DeniedShownAt = 0.0;

		/** ⑧ A 를 누르기 전 방장의 준비 */
		bool bLeaderWasReady = false;

		/** ④ 바꿔 보기 전 목적지 이름 */
		FText OriginalDisplayName;

		/** ⑩ 위에 다른 화면이 올라온 준비 화면 */
		TWeakObjectPtr<UAstralHubReadyWidget> CoveredScreen;

		/** ⑨ 이동 전 레이아웃 */
		TMap<int32, TWeakObjectPtr<UAstralRootLayout>> OldLayouts;

		/** ⓗ 버튼을 덮는 시험 그림 */
		TWeakObjectPtr<UImage> Cover;
	};

	// ─── 조회 — 이동 · 늦은 입장으로 월드가 바뀌므로 매번 찾는다 ───

	AAstralPlayerController* GetLocalPC(const UWorld* World)
	{
		const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
		return GameInstance ? Cast<AAstralPlayerController>(GameInstance->GetFirstLocalPlayerController(World)) : nullptr;
	}

	/** 접속 중인 자리 — 리슨 호스트 · 클라이언트. 접속을 끊고 Standalone 이 된 월드는 뺀다 */
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

	AAstralPlayerController* SeatPC(int32 PlayerId)
	{
		for (const UWorld* World : GetSeatWorlds())
		{
			if (PlayerId != 0 && LocalPlayerIdIn(World) == PlayerId)
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

	UAstralActivatableWidget* TopOf(int32 PlayerId)
	{
		const UAstralRootLayout* Layout = LayoutOf(PlayerId);
		return Layout ? Layout->GetTopScreen(EAstralUILayer::Menu) : nullptr;
	}

	UAstralHubReadyWidget* ScreenOf(int32 PlayerId) { return Cast<UAstralHubReadyWidget>(TopOf(PlayerId)); }

	bool IsScreenOpen(int32 PlayerId)
	{
		const UAstralHubReadyWidget* Screen = ScreenOf(PlayerId);
		return Screen && Screen->IsActivated() && AstralUITest::IsOnScreen(Screen);
	}

	UAstralButtonBase* ButtonOf(int32 PlayerId, FName Name)
	{
		const UAstralHubReadyWidget* Screen = ScreenOf(PlayerId);
		return Screen ? Cast<UAstralButtonBase>(Screen->GetWidgetFromName(Name)) : nullptr;
	}

	FString ReasonOf(int32 PlayerId)
	{
		const UAstralHubReadyWidget* Screen = ScreenOf(PlayerId);
		const UTextBlock* Reason = Screen ? Cast<UTextBlock>(Screen->GetWidgetFromName(TEXT("ReasonText"))) : nullptr;
		return Reason ? Reason->GetText().ToString() : TEXT("<no reason text>");
	}

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

	bool HasFocus(int32 PlayerId, const UCommonButtonBase* Button)
	{
		AAstralPlayerController* PC = SeatPC(PlayerId);
		return PC && Button && (Button->HasUserFocus(PC) || Button->HasUserFocusedDescendants(PC));
	}

	bool IsGameRestored(int32 PlayerId)
	{
		const AAstralPlayerController* PC = SeatPC(PlayerId);
		const UGameViewportClient* Viewport = ViewportOf(PlayerId);
		return PC && Viewport && ModeOf(PlayerId) == EMode::Game && !PC->ShouldShowMouseCursor()
			&& Viewport->GetMouseCaptureMode() == EMouseCaptureMode::CapturePermanently_IncludingInitialMouseDown && !TopOf(PlayerId);
	}

	AAstralHubGameState* ServerHub()
	{
		const UWorld* ServerWorld = FindServerWorld();
		return ServerWorld ? ServerWorld->GetGameState<AAstralHubGameState>() : nullptr;
	}

	AAstralPlayerState* ServerPlayer(int32 PlayerId)
	{
		const AAstralHubGameState* Hub = ServerHub();
		if (Hub)
		{
			for (APlayerState* PS : Hub->PlayerArray)
			{
				if (PS && PS->GetPlayerId() == PlayerId)
				{
					return Cast<AAstralPlayerState>(PS);
				}
			}
		}
		return nullptr;
	}

	bool IsServerReady(int32 PlayerId)
	{
		const AAstralPlayerState* PS = ServerPlayer(PlayerId);
		return PS && PS->IsReady();
	}

	FString ServerSelected()
	{
		const AAstralHubGameState* Hub = ServerHub();
		return Hub ? Hub->GetSelectedRaid().MapName : FString(TEXT("<no hub>"));
	}

	bool IsShown(const UWidget* Widget)
	{
		return Widget && Widget->GetVisibility() != ESlateVisibility::Collapsed && Widget->GetVisibility() != ESlateVisibility::Hidden;
	}

	// ─── 화면이 보여 주는 것 ↔ 서버 값으로 따로 계산한 기대값 ───

	FString ShownState(int32 PlayerId)
	{
		const UAstralHubReadyWidget* Screen = ScreenOf(PlayerId);
		if (!Screen)
		{
			return TEXT("<no screen>");
		}
		FString Rows;
		for (int32 RowIndex = 0; RowIndex < NumRows; ++RowIndex)
		{
			const UAstralHubMemberRowWidget* Row = Cast<UAstralHubMemberRowWidget>(Screen->GetWidgetFromName(*FString::Printf(TEXT("MemberRow%d"), RowIndex + 1)));
			if (!Row)
			{
				Rows += TEXT("[missing]");
				continue;
			}
			if (!Row->IsShowingMember())
			{
				Rows += TEXT("[-]");
				continue;
			}
			const UTextBlock* NameText = Cast<UTextBlock>(Row->GetWidgetFromName(TEXT("MemberNameText")));
			Rows += FString::Printf(TEXT("[%s%s%s]"), NameText ? *NameText->GetText().ToString() : TEXT("?"),
				IsShown(Row->GetWidgetFromName(TEXT("LeaderMark"))) ? TEXT(" L") : TEXT(""), IsShown(Row->GetWidgetFromName(TEXT("ReadyLabel"))) ? TEXT(" R") : TEXT(""));
		}
		const UAstralButtonBase* Ready = ButtonOf(PlayerId, ReadyName);
		const UAstralButtonBase* Destination = ButtonOf(PlayerId, DestinationName);
		const UAstralButtonBase* Launch = ButtonOf(PlayerId, LaunchName);
		if (!Ready || !Destination || !Launch)
		{
			return Rows + TEXT(" <missing button>");
		}
		return FString::Printf(TEXT("%s ready(en %d sel %d) dest(en %d sel %d '%s') launch(en %d) reason '%s'"), *Rows,
			Ready->GetIsEnabled() ? 1 : 0, Ready->GetSelected() ? 1 : 0, Destination->GetIsEnabled() ? 1 : 0, Destination->GetSelected() ? 1 : 0, *Destination->GetButtonText().ToString(),
			Launch->GetIsEnabled() ? 1 : 0, *ReasonOf(PlayerId));
	}

	FString ExpectedState(int32 PlayerId)
	{
		const AAstralHubGameState* Hub = ServerHub();
		const AAstralPlayerController* PC = SeatPC(PlayerId);
		const AAstralHubGameState* SeatHub = PC ? PC->GetWorld()->GetGameState<AAstralHubGameState>() : nullptr;
		if (!Hub || !SeatHub)
		{
			return TEXT("<no hub>");
		}

		// 파티원 = 사람 · 번호 있음, 번호 순 — 방장 = 첫째
		TArray<const AAstralPlayerState*> Members;
		for (const APlayerState* PS : Hub->PlayerArray)
		{
			const AAstralPlayerState* AstralPS = Cast<AAstralPlayerState>(PS);
			if (AstralPS && !AstralPS->IsABot() && !AstralPS->IsOnlyASpectator() && AstralPS->GetPlayerId() != 0)
			{
				Members.Add(AstralPS);
			}
		}
		Members.Sort([](const AAstralPlayerState& A, const AAstralPlayerState& B) { return A.GetPlayerId() < B.GetPlayerId(); });

		FString Rows;
		bool bAllReady = Members.Num() > 0;
		bool bMeReady = false;
		for (int32 RowIndex = 0; RowIndex < NumRows; ++RowIndex)
		{
			if (Members.IsValidIndex(RowIndex))
			{
				const AAstralPlayerState* Member = Members[RowIndex];
				Rows += FString::Printf(TEXT("[%s%s%s]"), *Member->GetPlayerName(), RowIndex == 0 ? TEXT(" L") : TEXT(""), Member->IsReady() ? TEXT(" R") : TEXT(""));
			}
			else
			{
				Rows += TEXT("[-]");
			}
		}
		for (const AAstralPlayerState* Member : Members)
		{
			bAllReady &= Member->IsReady();
			bMeReady |= (Member->GetPlayerId() == PlayerId && Member->IsReady());
		}
		const bool bLeader = Members.Num() > 0 && Members[0]->GetPlayerId() == PlayerId;
		const bool bSelected = Hub->GetSelectedRaid().MapName == RaidMap;
		const FString DestinationText = SeatHub->GetRaidDestinations().Num() > 0 ? SeatHub->GetRaidDestinations()[0].DisplayName.ToString() : FString();
		const EAstralLobbyDenial Why = !bLeader ? EAstralLobbyDenial::NotLeader : !bSelected ? EAstralLobbyDenial::NoRaidSelected : !bAllReady ? EAstralLobbyDenial::NotAllReady : EAstralLobbyDenial::None;
		return FString::Printf(TEXT("%s ready(en 1 sel %d) dest(en %d sel %d '%s') launch(en %d) reason '%s'"), *Rows,
			bMeReady ? 1 : 0, bLeader ? 1 : 0, bSelected ? 1 : 0, *DestinationText, (bLeader && bSelected && bAllReady) ? 1 : 0, *AstralLobby::GetDenialText(Why).ToString());
	}

	FString Describe(const FContext& Ctx)
	{
		FString Out = FString::Printf(TEXT("server map '%s' selected '%s'"), *MapOf(FindServerWorld()), *ServerSelected());
		for (const UWorld* World : GetSeatWorlds())
		{
			const int32 PlayerId = LocalPlayerIdIn(World);
			const AAstralPlayerController* PC = GetLocalPC(World);
			const UGameViewportClient* Viewport = ViewportOf(PlayerId);
			Out += FString::Printf(TEXT(" | seat %d (%s) map '%s' mode %d cursor %d capture %d top %s"), PlayerId, World->GetNetMode() == NM_Client ? TEXT("client") : TEXT("host"), *MapOf(World),
				static_cast<int32>(ModeOf(PlayerId)), (PC && PC->ShouldShowMouseCursor()) ? 1 : 0, Viewport ? static_cast<int32>(Viewport->GetMouseCaptureMode()) : -1, *GetNameSafe(TopOf(PlayerId)));
			if (ScreenOf(PlayerId))
			{
				Out += FString::Printf(TEXT("\n    shown    %s\n    expected %s"), *ShownState(PlayerId), *ExpectedState(PlayerId));
			}
		}
		return Out;
	}

	void Wait(const TSharedRef<FContext>& Ctx, const FString& What, double TimeoutSeconds, TFunction<bool()> Condition)
	{
		WaitUntil(Ctx, *What, TimeoutSeconds, MoveTemp(Condition), [Ctx]() { return Describe(*Ctx); });
	}

	/** 화면을 연 자리 모두가 서버 값대로 보일 때까지 */
	void WaitScreensMatch(const TSharedRef<FContext>& Ctx, const FString& What, double TimeoutSeconds = 10.0)
	{
		Wait(Ctx, What, TimeoutSeconds, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Open)
			{
				if (!ScreenOf(PlayerId) || ShownState(PlayerId) != ExpectedState(PlayerId))
				{
					return false;
				}
			}
			return true;
		});
		Do(Ctx, [Ctx, What]()
		{
			for (const int32 PlayerId : Ctx->Open)
			{
				Note(*Ctx->Test, FString::Printf(TEXT("%s — seat %d: %s"), *What, PlayerId, *ShownState(PlayerId)));
			}
		});
	}

	// ─── 조작 ───

	void FocusSeat(int32 PlayerId)
	{
		if (const UGameViewportClient* Viewport = ViewportOf(PlayerId))
		{
			FSlateApplication::Get().SetUserFocus(0, Viewport->GetGameViewportWidget(), EFocusCause::SetDirectly);
		}
	}

	/** 자리의 뷰포트 클라이언트에 키 하나(UCommonGameViewportClient::InputKey → 라우터) — 돌려주는 값은 '처리됨' */
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

	/** Slate 로 들어가는 키 — 초점이 있는 위젯부터(입력 전처리기 · 내비게이션 포함) */
	void SlateTap(const FKey& Key)
	{
		const FKeyEvent Event(Key, FModifierKeysState(), /*UserIndex*/ 0, /*bIsRepeat*/ false, 0, 0);
		FSlateApplication::Get().ProcessKeyDownEvent(Event);
		FSlateApplication::Get().ProcessKeyUpEvent(Event);
	}

	/** 안쪽 SButton — UCommonButtonInternalBase 는 크기 상자(SBox)로 한 번 더 감싼다(3-1 함정 1) */
	TSharedPtr<SWidget> InnerSlateButton(const UCommonButtonBase* Button)
	{
		const UCommonButtonInternalBase* Root = Button && Button->WidgetTree ? Cast<UCommonButtonInternalBase>(Button->WidgetTree->RootWidget) : nullptr;
		const TSharedPtr<SWidget> Box = Root ? Root->GetCachedWidget() : nullptr;
		FChildren* Children = Box ? Box->GetChildren() : nullptr;
		return (Children && Children->Num() > 0) ? Children->GetChildAt(0).ToSharedPtr() : nullptr;
	}

	TSharedPtr<SWindow> SeatWindow(int32 PlayerId)
	{
		const UGameViewportClient* Viewport = ViewportOf(PlayerId);
		const TSharedPtr<SViewport> ViewportWidget = Viewport ? Viewport->GetGameViewportWidget() : nullptr;
		return ViewportWidget ? FSlateApplication::Get().FindWidgetWindow(ViewportWidget.ToSharedRef()) : nullptr;
	}

	FVector2D CenterOf(const UWidget* Widget)
	{
		return Widget ? FVector2D(Widget->GetCachedGeometry().GetAbsolutePositionAtCoordinates(FVector2f(0.5f, 0.5f))) : FVector2D::ZeroVector;
	}

	/** 그 자리 창의 히트 테스트 길(데스크톱 좌표). bIgnoreEnabledStatus 가 거짓이면 꺼진 위젯에서 잘린다 — 실제 마우스와 같다 */
	FWidgetPath PathAt(int32 PlayerId, const FVector2D& Position, bool bIgnoreEnabledStatus)
	{
		const TSharedPtr<SWindow> Window = SeatWindow(PlayerId);
		if (!Window)
		{
			return FWidgetPath();
		}
		return FSlateApplication::Get().LocateWindowUnderMouse(Position, { Window.ToSharedRef() }, bIgnoreEnabledStatus, /*UserIndex*/ 0);
	}

	bool Reaches(const FWidgetPath& Path, const UCommonButtonBase* Button)
	{
		const TSharedPtr<SWidget> Inner = InnerSlateButton(Button);
		return Inner && Path.IsValid() && Path.ContainsWidget(Inner.Get());
	}

	FString DescribePath(const FWidgetPath& Path)
	{
		return Path.IsValid() ? FString::Printf(TEXT("%d widgets, leaf %s"), Path.Widgets.Num(), *Path.GetLastWidget()->GetTypeAsString()) : FString(TEXT("empty"));
	}

	/** 실제 Slate 길로 마우스 왼쪽 누르고 떼기 — 같은 틱 안에서 이동(올림) · 눌림 · 뗌 */
	void ClickAt(int32 PlayerId, const FVector2D& Position)
	{
		const FWidgetPath Path = PathAt(PlayerId, Position, /*bIgnoreEnabledStatus*/ false);
		if (!Path.IsValid())
		{
			return;
		}
		FSlateApplication& Slate = FSlateApplication::Get();
		const uint32 User = 0;
		const uint32 Pointer = FSlateApplication::CursorPointerIndex;
		const TSet<FKey> NoButtons;
		const TSet<FKey> LeftDown = { EKeys::LeftMouseButton };
		Slate.RoutePointerMoveEvent(Path, FPointerEvent(User, Pointer, Position, Position, NoButtons, FKey(), 0.f, FModifierKeysState()), /*bIsSynthetic*/ false);
		Slate.RoutePointerDownEvent(Path, FPointerEvent(User, Pointer, Position, Position, LeftDown, EKeys::LeftMouseButton, 0.f, FModifierKeysState()));
		Slate.RoutePointerUpEvent(Path, FPointerEvent(User, Pointer, Position, Position, NoButtons, EKeys::LeftMouseButton, 0.f, FModifierKeysState()));
	}

	FString ClickKey(int32 PlayerId, FName Button) { return FString::Printf(TEXT("%d.%s"), PlayerId, *Button.ToString()); }

	/** 그 자리 화면의 버튼 셋이 눌린 횟수를 센다(화면을 다시 열면 다시 부른다) */
	void CountClicks(const TSharedRef<FContext>& Ctx, int32 PlayerId)
	{
		for (const FName Name : { ReadyName, DestinationName, LaunchName })
		{
			if (UAstralButtonBase* Button = ButtonOf(PlayerId, Name))
			{
				TWeakPtr<FContext> WeakCtx = Ctx;
				const FString Key = ClickKey(PlayerId, Name);
				Button->OnClicked().AddLambda([WeakCtx, Key]()
				{
					if (const TSharedPtr<FContext> Pinned = WeakCtx.Pin())
					{
						++Pinned->Clicks.FindOrAdd(Key);
					}
				});
			}
		}
	}

	void CountDenials(const TSharedRef<FContext>& Ctx, int32 PlayerId)
	{
		if (AAstralPlayerController* PC = SeatPC(PlayerId))
		{
			TWeakPtr<FContext> WeakCtx = Ctx;
			PC->OnLobbyRequestDenied.AddLambda([WeakCtx, PlayerId](EAstralLobbyDenial)
			{
				if (const TSharedPtr<FContext> Pinned = WeakCtx.Pin())
				{
					++Pinned->Denials.FindOrAdd(PlayerId);
				}
			});
		}
	}

	/** 버튼 가운데를 누른다 — 가리는 것이 없는지(꺼짐 무시 히트 길이 버튼에 닿음)부터 본다 */
	void ClickButton(const TSharedRef<FContext>& Ctx, int32 PlayerId, FName Name)
	{
		const UAstralButtonBase* Button = ButtonOf(PlayerId, Name);
		if (!Ctx->Test->TestNotNull(*FString::Printf(TEXT("seat %d has %s"), PlayerId, *Name.ToString()), Button))
		{
			Ctx->bAborted = true;
			return;
		}
		const FVector2D Center = CenterOf(Button);
		const FWidgetPath Path = PathAt(PlayerId, Center, /*bIgnoreEnabledStatus*/ true);
		Ctx->Test->TestTrue(*FString::Printf(TEXT("seat %d: nothing covers %s at its centre (%s) — %s"), PlayerId, *Name.ToString(), *Center.ToString(), *DescribePath(Path)), Reaches(Path, Button));
		ClickAt(PlayerId, Center);
	}

	/** 메뉴 입력 · 커서 · 마우스 안 잡음 · 첫 초점 = 준비 */
	bool IsOpenedForMenu(int32 PlayerId)
	{
		const UAstralHubReadyWidget* Screen = ScreenOf(PlayerId);
		return Screen && IsScreenOpen(PlayerId) && ModeOf(PlayerId) == EMode::Menu && SeatPC(PlayerId)->ShouldShowMouseCursor()
			&& ViewportOf(PlayerId)->GetMouseCaptureMode() == EMouseCaptureMode::NoCapture && HasFocus(PlayerId, ButtonOf(PlayerId, ReadyName));
	}

	/** 그 자리 창의 데스크톱 상자 · 화면 배율 — 기록용 */
	FString DescribeWindow(int32 PlayerId)
	{
		const TSharedPtr<SWindow> Window = SeatWindow(PlayerId);
		const UAstralHubReadyWidget* Screen = ScreenOf(PlayerId);
		return Window ? FString::Printf(TEXT("window %s size %s scale %.3f"), *FVector2D(Window->GetPositionInScreen()).ToString(), *FVector2D(Window->GetSizeInScreen()).ToString(),
			Screen ? Screen->GetCachedGeometry().Scale : -1.f) : FString(TEXT("no window"));
	}

	/**
	 * 게임패드 A 는 실제 커서 자리에 마우스 클릭을 흉내 낸다(CommonUI.ShouldVirtualAcceptSimulateMouseButton — 기본 켜짐, 커서는 초점 버튼 가운데로 옮겨 간다).
	 * 한 프로세스 다인 PIE 의 창이 그 자리를 덮으면 클릭이 다른 창에 가므로 덮는 PIE 창만 옆으로 옮긴다(게임 창 하나에서는 없는 일)
	 */
	void ClearOtherWindowsAt(int32 PlayerId, const FVector2D& Point)
	{
		const TSharedPtr<SWindow> Mine = SeatWindow(PlayerId);
		for (UWorld* World : GetPieWorlds())
		{
			UGameViewportClient* Viewport = World->GetGameViewport();
			const TSharedPtr<SWindow> Window = Viewport ? Viewport->GetWindow() : nullptr;
			if (Window && Window != Mine && Window->IsScreenspaceMouseWithin(Point))
			{
				Window->MoveWindowTo(FVector2D(Point.X + 60.0, FVector2D(Window->GetPositionInScreen()).Y));
			}
		}
	}

	/**
	 * PIE — 창은 16:9 960 × 540(화면 배율 0.5 로 1920 × 1080 화면이 꼭 들어간다). 편집기 개인 설정의 창 크기를 따르면 배율이 바닥(0.444, 짧은 변 480 이하)에 걸린 채
	 * 창이 더 작아 아래 · 오른쪽 버튼이 창 밖으로 잘린다 [실측 568 × 365 — 방향키 내비게이션이 준비 버튼에 못 닿음]. 마우스 클릭은 그 자리 창의 히트 테스트만 쓰므로 창이 겹쳐도 된다
	 */
	void RequestSeatPie(const TSharedRef<FContext>& Ctx, EPlayNetMode NetMode)
	{
		Step([Ctx, NetMode]() -> bool
		{
			if (!GEditor || GEditor->PlayWorld || GEditor->IsPlaySessionInProgress())
			{
				Ctx->Test->AddError(TEXT("PIE is already active — end it before running this test"));
				Ctx->bAborted = true;
				return true;
			}
			const FIntPoint WindowSize(960, 540);
			FRequestPlaySessionParams Params;
			Params.GlobalMapOverride = HubMapPath;
			ULevelEditorPlaySettings* Settings = NewObject<ULevelEditorPlaySettings>(GetTransientPackage());
			Settings->SetPlayNetMode(NetMode);
			Settings->SetPlayNumberOfClients(NumPlayers);
			Settings->SetRunUnderOneProcess(true);
			Settings->NewWindowWidth = WindowSize.X;
			Settings->NewWindowHeight = WindowSize.Y;
			Settings->CenterNewWindow = true;
			Settings->SetClientWindowSize(WindowSize);
			Params.EditorPlaySettings = Settings;
			GEditor->RequestPlaySession(Params);
			Ctx->bPieRequested = true;
			return true;
		});
	}

	/** 이 자리들이 허브에서 폰 · 레이아웃 · GameState 를 갖췄다 */
	bool AreSeatsSettled(int32 NumSeats)
	{
		const UWorld* ServerWorld = FindServerWorld();
		if (!ServerWorld || !ServerWorld->HasBegunPlay() || MapOf(ServerWorld) != HubMap || GetSeatWorlds().Num() != NumSeats)
		{
			return false;
		}
		for (const UWorld* World : GetSeatWorlds())
		{
			const AAstralPlayerController* PC = GetLocalPC(World);
			const UAstralUISubsystem* UI = UAstralUISubsystem::Get(PC);
			if (MapOf(World) != HubMap || LocalPlayerIdIn(World) == 0 || !PC->GetPawn() || !World->GetGameState<AAstralHubGameState>() || !UI || !UI->GetRootLayout()
				|| World->GetGameState()->PlayerArray.Num() != NumSeats)
			{
				return false;
			}
		}
		return true;
	}

	/**
	 * 자리에 초점을 주고 그 자리 라우터에 입력 설정이 걸려 있게 한다. 편집기 다중 창 PIE 에서는 화면이 켜질 때 초점이 있던 창의 라우터만 설정을 걸고
	 * (UIActionRouterTypes.cpp ApplyLeafmostNodeConfig 의 IsViewportWindowInFocusPath), 나중에 초점이 와도 다시 걸지 않는다 — PIE 를 시작할 때 초점은
	 * 마지막에 만든 창에만 있다. 설정이 안 걸린 자리는 루트 레이아웃을 껐다 켜 제품의 설정(UAstralRootLayout::GetDesiredInputConfig = Game)을 다시 걸게 한다
	 */
	/** 자리는 단계가 돌 때 정해진다(L · N 은 setup, J 는 늦은 입장) — 큐에 넣을 때가 아니라 돌 때 읽도록 멤버를 가리킨다 */
	using FSeatRef = int32 FContext::*;

	void PrepareSeat(const TSharedRef<FContext>& Ctx, FSeatRef Seat)
	{
		Do(Ctx, [Ctx, Seat]()
		{
			const int32 PlayerId = (*Ctx).*Seat;
			FocusSeat(PlayerId);
			UAstralRootLayout* Layout = LayoutOf(PlayerId);
			if (Layout && ModeOf(PlayerId) == EMode::None)
			{
				Note(*Ctx->Test, FString::Printf(TEXT("seat %d: no input config yet (editor multi-window PIE) — reactivating the root layout with the focus"), PlayerId));
				Layout->DeactivateWidget();
				Layout->ActivateWidget();
			}
		});
		Wait(Ctx, TEXT("the seat is in game input with the focus"), 5.0, [Ctx, Seat]() { return ModeOf((*Ctx).*Seat) == EMode::Game; });
	}

	/** Tab 으로 연다(게임 입력 → 루트 레이아웃의 여는 액션) */
	void OpenWithTab(const TSharedRef<FContext>& Ctx, FSeatRef Seat, const FString& What)
	{
		PrepareSeat(Ctx, Seat);
		Do(Ctx, [Ctx, Seat]()
		{
			FocusSeat((*Ctx).*Seat);
			Tap((*Ctx).*Seat, EKeys::Tab);
		});
		Wait(Ctx, What, 5.0, [Ctx, Seat]() { return IsOpenedForMenu((*Ctx).*Seat); });
		Do(Ctx, [Ctx, Seat]()
		{
			Ctx->Open.AddUnique((*Ctx).*Seat);
			CountClicks(Ctx, (*Ctx).*Seat);
		});
		Hold(Ctx, 0.3);   // 그려져야 히트 테스트 칸이 생긴다
	}

	// ─── 단계 ───

	void EnqueueSetup(const TSharedRef<FContext>& Ctx)
	{
		RequestSeatPie(Ctx, Ctx->bDedicated ? PIE_Client : PIE_ListenServer);
		Wait(Ctx, TEXT("both players in HubMap with a pawn and a layout"), 240.0, []() { return AreSeatsSettled(NumPlayers); });
		Hold(Ctx, 1.0);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const AAstralHubGameState* Hub = ServerHub();
			const APlayerState* Leader = Hub ? Hub->GetPartyLeader() : nullptr;
			if (!Test.TestNotNull(TEXT("server hub and leader"), Leader))
			{
				Ctx->bAborted = true;
				return;
			}
			Ctx->L = Leader->GetPlayerId();
			Ctx->Leader = Ctx->L;
			for (const UWorld* World : GetSeatWorlds())
			{
				if (LocalPlayerIdIn(World) != Ctx->L)
				{
					Ctx->N = LocalPlayerIdIn(World);
				}
			}
			Test.TestTrue(TEXT("a non-leader seat"), Ctx->N != 0);
			CountDenials(Ctx, Ctx->L);
			CountDenials(Ctx, Ctx->N);

			// 여는 키 · 화면 — ini 와 허브 GameState 의 목록
			const FUIInputAction* Action = UCommonUIInputSettings::Get().FindAction(FUIActionTag::TryConvert(FGameplayTag::RequestGameplayTag(HubReadyTagName)));
			if (Test.TestNotNull(TEXT("the HubReady action is in DefaultInput.ini"), Action))
			{
				const auto Has = [Action](const FKey& Key) { return Action->KeyMappings.ContainsByPredicate([Key](const FUIActionKeyMapping& M) { return M.Key == Key; }); };
				Test.TestTrue(TEXT("HubReady = Tab"), Has(EKeys::Tab));
				Test.TestTrue(TEXT("HubReady = gamepad Special_Left"), Has(EKeys::Gamepad_Special_Left));
			}
			const FAstralContextScreen* Entry = Hub->GetContextScreens().FindByPredicate([](const FAstralContextScreen& Screen) { return Screen.ActionTag.GetTagName() == FName(HubReadyTagName); });
			if (Test.TestNotNull(TEXT("the hub lists the HubReady screen"), Entry))
			{
				Test.TestEqual(TEXT("... the promoted WBP"), Entry->ScreenClass.ToString(), FString(HubReadyClassPath));
				const UClass* ScreenClass = Entry->ScreenClass.LoadSynchronous();
				Test.TestTrue(TEXT("... it loads and is a UAstralHubReadyWidget"), ScreenClass && ScreenClass->IsChildOf(UAstralHubReadyWidget::StaticClass()));
			}
			Note(Test, FString::Printf(TEXT("setup: %s — L %d N %d | %s"), Ctx->bDedicated ? TEXT("dedicated") : TEXT("listen"), Ctx->L, Ctx->N, *Describe(*Ctx)));
		});
	}

	void EnqueueOpen(const TSharedRef<FContext>& Ctx)
	{
		// ① W 를 누른 채 Tab 으로 연다
		PrepareSeat(Ctx, &FContext::N);
		Do(Ctx, [Ctx]() { SendKey(Ctx->N, EKeys::W, IE_Pressed); });
		Wait(Ctx, TEXT("①: W moves N's pawn before the screen is open"), 5.0, [Ctx]() { return IsKeyDown(Ctx->N, EKeys::W) && SpeedOf(Ctx->N) > MovingSpeed; });
		Do(Ctx, [Ctx]() { Tap(Ctx->N, EKeys::Tab); });
		Wait(Ctx, TEXT("①: Tab opens HubReady — menu input, cursor, no mouse capture, first focus on Ready"), 5.0, [Ctx]() { return IsOpenedForMenu(Ctx->N); });
		Wait(Ctx, TEXT("①: the key held while opening is released and the pawn stops"), 5.0, [Ctx]() { return !IsKeyDown(Ctx->N, EKeys::W) && SpeedOf(Ctx->N) < StillSpeed; });
		Do(Ctx, [Ctx]()
		{
			Ctx->Open.AddUnique(Ctx->N);
			CountClicks(Ctx, Ctx->N);
			Ctx->Test->TestTrue(TEXT("①: the router swallows W while the screen is open"), SendKey(Ctx->N, EKeys::W, IE_Pressed));
		});
		Hold(Ctx, 0.5);
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestFalse(TEXT("①: W does not reach the game"), IsKeyDown(Ctx->N, EKeys::W));
			Ctx->Test->TestTrue(TEXT("①: the pawn stays"), SpeedOf(Ctx->N) < StillSpeed);
			SendKey(Ctx->N, EKeys::W, IE_Released);
		});
		WaitScreensMatch(Ctx, TEXT("①: N's screen shows the server state (empty rows folded)"));

		OpenWithTab(Ctx, &FContext::L, TEXT("①: Tab opens HubReady for L"));
		WaitScreensMatch(Ctx, TEXT("①: both screens show the server state"));
		Do(Ctx, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Open)
			{
				Note(*Ctx->Test, FString::Printf(TEXT("①: seat %d %s, Ready centre %s"), PlayerId, *DescribeWindow(PlayerId), *CenterOf(ButtonOf(PlayerId, ReadyName)).ToString()));
				// 버튼 셋이 뷰포트 안에 그려졌다 — 창이 작아 잘리면 마우스 · 방향키가 못 닿는다
				const UGameViewportClient* Viewport = ViewportOf(PlayerId);
				const TSharedPtr<SViewport> ViewportWidget = Viewport ? Viewport->GetGameViewportWidget() : nullptr;
				for (const FName Name : { ReadyName, DestinationName, LaunchName })
				{
					Ctx->Test->TestTrue(*FString::Printf(TEXT("①: seat %d %s is inside its viewport"), PlayerId, *Name.ToString()),
						ViewportWidget && ViewportWidget->GetTickSpaceGeometry().IsUnderLocation(CenterOf(ButtonOf(PlayerId, Name))));
				}
			}
		});
	}

	void EnqueueHarnessCheck(const TSharedRef<FContext>& Ctx)
	{
		// ⓗ-a 버튼 밖 — 화면 가운데(컨셉의 빈 자리)
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const UAstralHubReadyWidget* Screen = ScreenOf(Ctx->N);
			const FVector2D Middle = CenterOf(Screen);
			const FWidgetPath Path = PathAt(Ctx->N, Middle, /*bIgnoreEnabledStatus*/ true);
			Test.TestTrue(*FString::Printf(TEXT("ⓗ: the hit path at the screen middle exists (%s)"), *DescribePath(Path)), Path.IsValid());
			for (const FName Name : { ReadyName, DestinationName, LaunchName })
			{
				Test.TestFalse(*FString::Printf(TEXT("ⓗ: the screen middle is not %s"), *Name.ToString()), Reaches(Path, ButtonOf(Ctx->N, Name)));
			}
			ClickAt(Ctx->N, Middle);

			// ⓗ-b 준비 버튼을 덮는 visible 그림(버튼보다 위)
			UCanvasPanel* Root = Screen ? Cast<UCanvasPanel>(Screen->GetWidgetFromName(TEXT("Root"))) : nullptr;
			const UAstralButtonBase* Ready = ButtonOf(Ctx->N, ReadyName);
			const UCanvasPanelSlot* ReadySlot = Ready ? Cast<UCanvasPanelSlot>(Ready->Slot) : nullptr;
			if (!Test.TestNotNull(TEXT("ⓗ: the screen root canvas"), Root) || !Test.TestNotNull(TEXT("ⓗ: the Ready slot"), ReadySlot))
			{
				Ctx->bAborted = true;
				return;
			}
			UImage* Cover = Screen->WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), TEXT("HarnessCover"));
			Cover->SetVisibility(ESlateVisibility::Visible);
			Cover->SetColorAndOpacity(FLinearColor(1.f, 0.f, 1.f, 0.01f));
			UCanvasPanelSlot* CoverSlot = Root->AddChildToCanvas(Cover);
			CoverSlot->SetAnchors(ReadySlot->GetAnchors());
			CoverSlot->SetAlignment(ReadySlot->GetAlignment());
			CoverSlot->SetOffsets(ReadySlot->GetOffsets());
			CoverSlot->SetZOrder(ReadySlot->GetZOrder() + 100);
			Ctx->Cover = Cover;
		});
		Hold(Ctx, 0.3);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const UAstralButtonBase* Ready = ButtonOf(Ctx->N, ReadyName);
			const FWidgetPath Path = PathAt(Ctx->N, CenterOf(Ready), /*bIgnoreEnabledStatus*/ true);
			const UImage* Cover = Ctx->Cover.Get();
			const TSharedPtr<SWidget> CoverWidget = Cover ? Cover->GetCachedWidget() : nullptr;
			// 빈 길(창 밖 · 못 그림)은 '가렸다'가 아니다 — 덮은 그림이 길에 있고 버튼은 없어야 한다
			Test.TestTrue(*FString::Printf(TEXT("ⓗ: the hit path at Ready's centre ends on the cover (%s)"), *DescribePath(Path)), CoverWidget && Path.IsValid() && Path.ContainsWidget(CoverWidget.Get()));
			Test.TestFalse(TEXT("ⓗ: ... and does not reach Ready"), Reaches(Path, Ready));
			ClickAt(Ctx->N, CenterOf(Ready));
		});
		Hold(Ctx, 0.5);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			Test.TestEqual(TEXT("ⓗ: neither wrong click pressed Ready"), Ctx->Clicks.FindRef(ClickKey(Ctx->N, ReadyName)), 0);
			Test.TestFalse(TEXT("ⓗ: N is still not ready on the server"), IsServerReady(Ctx->N));
			if (UImage* Cover = Ctx->Cover.Get())
			{
				Cover->RemoveFromParent();
			}
		});
		Hold(Ctx, 0.3);
		Do(Ctx, [Ctx]()
		{
			const UAstralButtonBase* Ready = ButtonOf(Ctx->N, ReadyName);
			Ctx->Test->TestTrue(TEXT("ⓗ: without the cover the hit path reaches Ready (enabled)"), Reaches(PathAt(Ctx->N, CenterOf(Ready), /*bIgnoreEnabledStatus*/ false), Ready));
		});
	}

	void EnqueueReadyAndSelect(const TSharedRef<FContext>& Ctx)
	{
		// ② N 이 준비를 누른다
		Do(Ctx, [Ctx]() { ClickButton(Ctx, Ctx->N, ReadyName); });
		Wait(Ctx, TEXT("②: the click makes N ready on the server"), 5.0, [Ctx]() { return IsServerReady(Ctx->N); });
		WaitScreensMatch(Ctx, TEXT("②: both screens show N ready, N's Ready selected"));
		Do(Ctx, [Ctx]() { Ctx->Test->TestEqual(TEXT("②: one click"), Ctx->Clicks.FindRef(ClickKey(Ctx->N, ReadyName)), 1); });

		// ③ N 의 목적지 · 출정은 꺼져 있다
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			for (const FName Name : { DestinationName, LaunchName })
			{
				const UAstralButtonBase* Button = ButtonOf(Ctx->N, Name);
				const FVector2D Center = CenterOf(Button);
				Test.TestFalse(*FString::Printf(TEXT("③: N's %s is disabled"), *Name.ToString()), Button && Button->GetIsEnabled());
				Test.TestTrue(*FString::Printf(TEXT("③: nothing covers N's %s"), *Name.ToString()), Reaches(PathAt(Ctx->N, Center, true), Button));
				Test.TestFalse(*FString::Printf(TEXT("③: the real hit path stops before the disabled %s"), *Name.ToString()), Reaches(PathAt(Ctx->N, Center, false), Button));
				ClickAt(Ctx->N, Center);
			}
		});
		Hold(Ctx, 1.0);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			Test.TestEqual(TEXT("③: Destination was not pressed"), Ctx->Clicks.FindRef(ClickKey(Ctx->N, DestinationName)), 0);
			Test.TestEqual(TEXT("③: Launch was not pressed"), Ctx->Clicks.FindRef(ClickKey(Ctx->N, LaunchName)), 0);
			Test.TestTrue(TEXT("③: no destination on the server"), ServerSelected().IsEmpty());
			Test.TestEqual(TEXT("③: no request reached the server (no denial)"), Ctx->Denials.FindRef(Ctx->N), 0);
			Test.TestEqual(TEXT("③: still in HubMap"), MapOf(FindServerWorld()), FString(HubMap));
		});

		// ④ L 이 목적지를 누른다
		Do(Ctx, [Ctx]() { ClickButton(Ctx, Ctx->L, DestinationName); });
		Wait(Ctx, TEXT("④: the click selects RaidMap on the server"), 5.0, []() { return ServerSelected() == RaidMap; });
		WaitScreensMatch(Ctx, TEXT("④: both screens show the destination selected"));

		// ④ 목적지 글자의 원천 — N 자리의 목록 값을 바꾸면 글자가 따라 바뀐다(WBP 에 구운 '봉인된 유적' 이 아니다)
		Do(Ctx, [Ctx]()
		{
			AAstralHubGameState* SeatHub = SeatPC(Ctx->N)->GetWorld()->GetGameState<AAstralHubGameState>();
			const FArrayProperty* Property = FindFProperty<FArrayProperty>(AAstralHubGameState::StaticClass(), TEXT("RaidDestinations"));
			if (!Ctx->Test->TestNotNull(TEXT("④: RaidDestinations property"), Property) || SeatHub->GetRaidDestinations().IsEmpty())
			{
				Ctx->bAborted = true;
				return;
			}
			TArray<FAstralRaidDestination>& Destinations = *Property->ContainerPtrToValuePtr<TArray<FAstralRaidDestination>>(SeatHub);
			Ctx->OriginalDisplayName = Destinations[0].DisplayName;
			Destinations[0].DisplayName = FText::FromString(TEXT("시험 목적지"));
			SeatHub->NotifyPlayerRosterChanged();
		});
		Wait(Ctx, TEXT("④: the destination text follows the list"), 3.0, [Ctx]()
		{
			const UAstralButtonBase* Destination = ButtonOf(Ctx->N, DestinationName);
			return Destination && Destination->GetButtonText().ToString() == TEXT("시험 목적지");
		});
		Do(Ctx, [Ctx]()
		{
			AAstralHubGameState* SeatHub = SeatPC(Ctx->N)->GetWorld()->GetGameState<AAstralHubGameState>();
			const FArrayProperty* Property = FindFProperty<FArrayProperty>(AAstralHubGameState::StaticClass(), TEXT("RaidDestinations"));
			(*Property->ContainerPtrToValuePtr<TArray<FAstralRaidDestination>>(SeatHub))[0].DisplayName = Ctx->OriginalDisplayName;
			SeatHub->NotifyPlayerRosterChanged();
		});
		WaitScreensMatch(Ctx, TEXT("④: the original name is back"));
	}

	void EnqueueDenied(const TSharedRef<FContext>& Ctx)
	{
		// ⑤ 준비 안 한 방장이 서버에 직접 출정 — 경합(출정을 누른 순간 누가 준비를 풂)과 같은 거절
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestFalse(TEXT("⑤: L is not ready"), IsServerReady(Ctx->L));
			SeatPC(Ctx->L)->ServerStartRaid();
		});
		Wait(Ctx, TEXT("⑤: the denial shows on L's reason line"), 5.0, [Ctx]()
		{
			const UAstralHubReadyWidget* Screen = ScreenOf(Ctx->L);
			return Screen && Screen->IsShowingDeniedReason() && ReasonOf(Ctx->L) == AstralLobby::GetRequestDeniedText(EAstralLobbyDenial::NotAllReady).ToString();
		});
		Do(Ctx, [Ctx]()
		{
			Ctx->DeniedShownAt = FPlatformTime::Seconds();
			Ctx->Test->TestEqual(TEXT("⑤: one denial reached L"), Ctx->Denials.FindRef(Ctx->L), 1);
			Note(*Ctx->Test, FString::Printf(TEXT("⑤: denied — '%s'"), *ReasonOf(Ctx->L)));
		});
		Wait(Ctx, TEXT("⑤: the reason line returns to the current state"), 8.0, [Ctx]()
		{
			const UAstralHubReadyWidget* Screen = ScreenOf(Ctx->L);
			return Screen && !Screen->IsShowingDeniedReason() && ReasonOf(Ctx->L) == AstralLobby::GetDenialText(EAstralLobbyDenial::NotAllReady).ToString();
		});
		Do(Ctx, [Ctx]()
		{
			const double Elapsed = FPlatformTime::Seconds() - Ctx->DeniedShownAt;
			const double Expected = ScreenOf(Ctx->L)->GetDeniedReasonSeconds();
			Ctx->Test->TestTrue(*FString::Printf(TEXT("⑤: the denial stayed about %.1f s (%.2f s)"), Expected, Elapsed), Elapsed > Expected - 0.5 && Elapsed < Expected + 0.6);
			Ctx->Test->TestEqual(TEXT("⑤: still in HubMap"), MapOf(FindServerWorld()), FString(HubMap));
			Note(*Ctx->Test, FString::Printf(TEXT("⑤: back after %.2f s — '%s'"), Elapsed, *ReasonOf(Ctx->L)));
		});
		WaitScreensMatch(Ctx, TEXT("⑤: both screens show the server state again"));
	}

	void EnqueueLateJoin(const TSharedRef<FContext>& Ctx)
	{
		// ⑥ 늦은 입장
		Do(Ctx, []() { GEditor->RequestLateJoin(); });
		Wait(Ctx, TEXT("⑥: the late player arrives in HubMap"), 120.0, []() { return AreSeatsSettled(NumPlayers + 1); });
		Hold(Ctx, 1.0);
		Do(Ctx, [Ctx]()
		{
			for (const UWorld* World : GetSeatWorlds())
			{
				const int32 PlayerId = LocalPlayerIdIn(World);
				if (PlayerId != Ctx->L && PlayerId != Ctx->N)
				{
					Ctx->J = PlayerId;
				}
			}
			if (!Ctx->Test->TestTrue(TEXT("⑥: the late seat has its own id"), Ctx->J != 0))
			{
				Ctx->bAborted = true;
				return;
			}
			CountDenials(Ctx, Ctx->J);
		});
		WaitScreensMatch(Ctx, TEXT("⑥: the open screens get J's row"));
		OpenWithTab(Ctx, &FContext::J, TEXT("⑥: Tab opens HubReady for J"));
		WaitScreensMatch(Ctx, TEXT("⑥: J sees the current state (N ready, destination selected)"));
	}

	void EnqueueLeaderLeaves(const TSharedRef<FContext>& Ctx)
	{
		// ⑦ Dedicated — 방장이 접속을 끊는다(콘솔 disconnect 와 같은 길)
		Do(Ctx, [Ctx]()
		{
			const UAstralButtonBase* Destination = ButtonOf(Ctx->N, DestinationName);
			AAstralPlayerController* LeaderPC = SeatPC(Ctx->L);
			if (!Ctx->Test->TestNotNull(TEXT("⑦: N's Destination"), Destination) || !Ctx->Test->TestNotNull(TEXT("⑦: L's seat"), LeaderPC))
			{
				Ctx->bAborted = true;
				return;
			}
			Ctx->Test->TestFalse(TEXT("⑦: before — N's Destination is disabled"), Destination->GetIsEnabled());
			LeaderPC->ConsoleCommand(TEXT("disconnect"));
		});
		Wait(Ctx, TEXT("⑦: the server and the remaining seats see two players"), 60.0, []()
		{
			const UWorld* ServerWorld = FindServerWorld();
			if (!ServerWorld || ServerWorld->GetGameState()->PlayerArray.Num() != NumPlayers || GetSeatWorlds().Num() != NumPlayers)
			{
				return false;
			}
			for (const UWorld* World : GetSeatWorlds())
			{
				if (World->GetGameState()->PlayerArray.Num() != NumPlayers)
				{
					return false;
				}
			}
			return true;
		});
		Do(Ctx, [Ctx]()
		{
			Ctx->Open.Remove(Ctx->L);
			Ctx->Leader = Ctx->N;
			const AAstralHubGameState* Hub = ServerHub();
			const APlayerState* Leader = Hub ? Hub->GetPartyLeader() : nullptr;
			Ctx->Test->TestTrue(TEXT("⑦: N is the leader now"), Leader && Leader->GetPlayerId() == Ctx->N);
		});
		WaitScreensMatch(Ctx, TEXT("⑦: N's Destination is enabled, L's row is gone"));
	}

	void EnqueueGamepad(const TSharedRef<FContext>& Ctx)
	{
		// ⑧ 방장 자리 — 준비 → 위(목적지) → 아래(준비) → A
		Do(Ctx, [Ctx]()
		{
			FocusSeat(Ctx->Leader);
			if (UAstralButtonBase* Ready = ButtonOf(Ctx->Leader, ReadyName))
			{
				Ready->SetUserFocus(SeatPC(Ctx->Leader));
			}
		});
		Wait(Ctx, TEXT("⑧: the leader's Ready has the focus"), 3.0, [Ctx]() { return HasFocus(Ctx->Leader, ButtonOf(Ctx->Leader, ReadyName)); });
		Do(Ctx, []() { SlateTap(EKeys::Gamepad_DPad_Up); });
		Wait(Ctx, TEXT("⑧: d-pad up moves the focus to Destination (focus look)"), 3.0, [Ctx]()
		{
			const UAstralButtonBase* Destination = ButtonOf(Ctx->Leader, DestinationName);
			return HasFocus(Ctx->Leader, Destination) && Destination->IsShowingFocusLook();
		});
		Do(Ctx, []() { SlateTap(EKeys::Gamepad_DPad_Down); });
		Wait(Ctx, TEXT("⑧: d-pad down moves the focus back to Ready"), 3.0, [Ctx]() { return HasFocus(Ctx->Leader, ButtonOf(Ctx->Leader, ReadyName)); });
		Do(Ctx, [Ctx]() { ClearOtherWindowsAt(Ctx->Leader, CenterOf(ButtonOf(Ctx->Leader, ReadyName))); });
		Hold(Ctx, 0.5);   // 게임패드면 커서가 초점 버튼으로 옮겨 간다(CommonAnalogCursor) — A 의 가상 클릭이 그 자리에 간다
		Do(Ctx, [Ctx]()
		{
			Ctx->bLeaderWasReady = IsServerReady(Ctx->Leader);
			SlateTap(EKeys::Gamepad_FaceButton_Bottom);
		});
		Wait(Ctx, TEXT("⑧: A toggles the leader's ready on the server"), 5.0, [Ctx]() { return IsServerReady(Ctx->Leader) != Ctx->bLeaderWasReady; });
		WaitScreensMatch(Ctx, TEXT("⑧: the screens follow the gamepad ready"));
	}

	void EnqueueClose(const TSharedRef<FContext>& Ctx)
	{
		// ⑩ J — 위에 다른 화면을 올린다
		Do(Ctx, [Ctx]()
		{
			FocusSeat(Ctx->J);
			Ctx->CoveredScreen = ScreenOf(Ctx->J);
			UAstralUISubsystem* UI = UIOf(Ctx->J);
			Ctx->Test->TestTrue(TEXT("⑩: a test menu opens above HubReady"), UI && UI->OpenScreen(UAstralScreenTestMenu::StaticClass()) != nullptr);
		});
		Wait(Ctx, TEXT("⑩: the test menu is on top"), 5.0, [Ctx]()
		{
			const UAstralActivatableWidget* Top = TopOf(Ctx->J);
			return Top && Top->IsA<UAstralScreenTestMenu>() && Top->IsActivated() && Ctx->CoveredScreen.IsValid() && !Ctx->CoveredScreen->IsActivated();
		});
		Do(Ctx, [Ctx]() { Tap(Ctx->J, EKeys::Tab); });
		Hold(Ctx, 0.5);
		Do(Ctx, [Ctx]()
		{
			const UAstralActivatableWidget* Top = TopOf(Ctx->J);
			Ctx->Test->TestTrue(TEXT("⑩: Tab under another screen closes nothing"), Top && Top->IsA<UAstralScreenTestMenu>() && Top->IsActivated());
			Tap(Ctx->J, EKeys::Gamepad_FaceButton_Right);
		});
		Wait(Ctx, TEXT("⑩: back closes only the test menu, HubReady is on top again"), 5.0, [Ctx]()
		{
			return ScreenOf(Ctx->J) == Ctx->CoveredScreen.Get() && IsScreenOpen(Ctx->J) && ModeOf(Ctx->J) == EMode::Menu;
		});
		Do(Ctx, [Ctx]() { Tap(Ctx->J, EKeys::Tab); });
		Wait(Ctx, TEXT("⑩: Tab now closes HubReady and game input returns"), 5.0, [Ctx]() { return IsGameRestored(Ctx->J); });
		Hold(Ctx, 0.5);
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestTrue(TEXT("⑩: it stays closed (the same press does not reopen it)"), IsGameRestored(Ctx->J));
			Ctx->Open.Remove(Ctx->J);
		});
		OpenWithTab(Ctx, &FContext::J, TEXT("⑩: Tab reopens HubReady for J"));
		WaitScreensMatch(Ctx, TEXT("⑩: the reopened screen shows the server state"));
	}

	void EnqueueLaunch(const TSharedRef<FContext>& Ctx)
	{
		// ⑨ 아직 준비 안 한 사람은 준비를 누른다
		Do(Ctx, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Open)
			{
				if (!IsServerReady(PlayerId))
				{
					ClickButton(Ctx, PlayerId, ReadyName);
				}
			}
		});
		Wait(Ctx, TEXT("⑨: everyone ready"), 10.0, []()
		{
			const AAstralHubGameState* Hub = ServerHub();
			return Hub && Hub->AreAllPlayersReady();
		});
		WaitScreensMatch(Ctx, TEXT("⑨: the leader's Launch is enabled"));
		Do(Ctx, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Open)
			{
				Ctx->OldLayouts.Add(PlayerId, LayoutOf(PlayerId));
			}
			ClickButton(Ctx, Ctx->Leader, LaunchName);
		});
		Wait(Ctx, TEXT("⑨: every seat is in RaidMap with a new layout, no screen and game input"), 180.0, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Open)
			{
				const AAstralPlayerController* PC = SeatPC(PlayerId);
				if (!PC || MapOf(PC->GetWorld()) != RaidMap || !PC->GetPawn() || !LayoutOf(PlayerId) || LayoutOf(PlayerId) == Ctx->OldLayouts.FindRef(PlayerId).Get())
				{
					return false;
				}
			}
			return true;
		});
		Hold(Ctx, 1.0);
		Do(Ctx, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Open)
			{
				FocusSeat(PlayerId);   // 편집기에서는 초점이 있는 창의 라우터만 설정을 건다(3-1 함정 8)
				Ctx->Test->TestNull(*FString::Printf(TEXT("⑨: seat %d has no screen in the raid"), PlayerId), TopOf(PlayerId));
			}
		});
		Hold(Ctx, 0.5);
		Do(Ctx, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Open)
			{
				Ctx->Test->TestTrue(*FString::Printf(TEXT("⑨: seat %d is back to game input"), PlayerId), ModeOf(PlayerId) != EMode::Menu && !SeatPC(PlayerId)->ShouldShowMouseCursor());
			}
			Note(*Ctx->Test, FString::Printf(TEXT("⑨: %s"), *Describe(*Ctx)));
		});
	}

	void EnqueueAll(FAutomationTestBase& Test, bool bDedicated)
	{
		// 거절 로그는 정해진 횟수만큼 — ⑤ 의 하나뿐. ③ 에서 요청이 새면 '방장이 아님' 이 나와 실패한다
		Test.AddExpectedError(TEXT("ServerStartRaid: 전원 준비 아님"), EAutomationExpectedErrorFlags::Contains, 1, /*IsRegex*/ false);

		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;
		Ctx->bDedicated = bDedicated;
		EnqueueSetup(Ctx);
		EnqueueOpen(Ctx);
		EnqueueHarnessCheck(Ctx);
		EnqueueReadyAndSelect(Ctx);
		EnqueueDenied(Ctx);
		EnqueueLateJoin(Ctx);
		if (bDedicated)
		{
			EnqueueLeaderLeaves(Ctx);
		}
		else
		{
			Do(Ctx, [Ctx]() { Note(*Ctx->Test, TEXT("⑦: skipped in listen — the leader is the host")); });
		}
		EnqueueGamepad(Ctx);
		EnqueueClose(Ctx);
		EnqueueLaunch(Ctx);
		EndPie(Ctx);
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralHubReadyListenPieTest, "AstralBreak.Net.HubReady.ListenPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralHubReadyListenPieTest::RunTest(const FString& Parameters)
{
	AstralHubReadyPie::EnqueueAll(*this, /*bDedicated*/ false);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralHubReadyDedicatedPieTest, "AstralBreak.Net.HubReady.DedicatedPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralHubReadyDedicatedPieTest::RunTest(const FString& Parameters)
{
	AstralHubReadyPie::EnqueueAll(*this, /*bDedicated*/ true);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
