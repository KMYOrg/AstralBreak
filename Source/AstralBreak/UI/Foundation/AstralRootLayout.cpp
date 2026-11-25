#include "AstralRootLayout.h"

#include "AstralLogChannels.h"
#include "Blueprint/WidgetTree.h"
#include "CommonInputModeTypes.h"
#include "Components/Overlay.h"
#include "Components/OverlaySlot.h"
#include "GameModes/AstralGameState.h"
#include "Input/CommonUIInputTypes.h"
#include "Widgets/CommonActivatableWidgetContainer.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(AstralRootLayout)

namespace AstralRootLayout
{
	/** 화면 전체를 채우는 칸으로 넣는다 */
	void AddFilled(UOverlay* Overlay, UWidget* Child)
	{
		UOverlaySlot* OverlaySlot = Overlay->AddChildToOverlay(Child);
		OverlaySlot->SetHorizontalAlignment(HAlign_Fill);
		OverlaySlot->SetVerticalAlignment(VAlign_Fill);
	}
}

UAstralRootLayout::UAstralRootLayout(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	InputConfig = EAstralWidgetInputMode::Game;
	bClosesOnBackAction = false;   // 뿌리는 닫히지 않는다
	bAutoActivate = true;
}

void UAstralRootLayout::NativeOnInitialized()
{
	using namespace AstralRootLayout;

	// 층은 코드가 정한다 — 애셋(WBP)이 할 일이 없다
	UOverlay* Root = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("Layers"));
	Root->SetVisibility(ESlateVisibility::SelfHitTestInvisible);
	WidgetTree->RootWidget = Root;

	HUDLayer = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("HUDLayer"));
	HUDLayer->SetVisibility(ESlateVisibility::HitTestInvisible);
	AddFilled(Root, HUDLayer);

	DebugLayer = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("DebugLayer"));
	DebugLayer->SetVisibility(ESlateVisibility::HitTestInvisible);
	AddFilled(Root, DebugLayer);

	MenuStack = WidgetTree->ConstructWidget<UCommonActivatableWidgetStack>(UCommonActivatableWidgetStack::StaticClass(), TEXT("MenuStack"));
	ModalStack = WidgetTree->ConstructWidget<UCommonActivatableWidgetStack>(UCommonActivatableWidgetStack::StaticClass(), TEXT("ModalStack"));
	for (UCommonActivatableWidgetStack* Stack : { MenuStack.Get(), ModalStack.Get() })
	{
		// 전환이 길면 그동안 초점이 새 화면에 제대로 옮겨 가지 않는다(Lyra PrimaryGameLayout::RegisterLayer 와 같은 까닭)
		Stack->SetTransitionDuration(0.f);
		AddFilled(Root, Stack);
	}

	Super::NativeOnInitialized();
}

TOptional<FUIInputConfig> UAstralRootLayout::GetDesiredInputConfig() const
{
	// Modal 은 라우터에서 따로 선 뿌리다 — 켜졌지만 아직 그려지지 않아 라우터가 이 레이아웃을 고른 틱에도 확인 창의 설정을 따른다
	const UCommonActivatableWidget* Modal = ModalStack ? ModalStack->GetActiveWidget() : nullptr;
	if (Modal && Modal->IsActivated())
	{
		if (const TOptional<FUIInputConfig> ModalConfig = Modal->GetDesiredInputConfig(); ModalConfig.IsSet())
		{
			return ModalConfig;
		}
	}

	// 맨 위 화면이 막 꺼졌다 — 뒤이어 설 화면(겹쳐 여는 중이면 새 화면, 닫는 중이면 그 아래)이 있으면 그 설정
	const UCommonActivatableWidget* Displayed = MenuStack ? MenuStack->GetActiveWidget() : nullptr;
	if (Displayed && !Displayed->IsActivated())
	{
		const TArray<UCommonActivatableWidget*>& Screens = MenuStack->GetWidgetList();
		for (int32 Index = Screens.Num() - 1; Index >= 0; --Index)
		{
			if (Screens[Index] && Screens[Index] != Displayed)
			{
				if (const TOptional<FUIInputConfig> NextConfig = Screens[Index]->GetDesiredInputConfig(); NextConfig.IsSet())
				{
					return NextConfig;
				}
				break;
			}
		}
	}

	return Super::GetDesiredInputConfig();
}

void UAstralRootLayout::ApplyContext(const AAstralGameState* GameState)
{
	for (FUIActionBindingHandle& Handle : ContextBindings)
	{
		RemoveActionBinding(Handle);
		Handle.Unregister();
	}
	ContextBindings.Reset();
	HUDLayer->ClearChildren();

	if (!GameState)
	{
		return;
	}

	for (const TSoftClassPtr<UUserWidget>& SoftClass : GameState->GetContextHUDWidgets())
	{
		UClass* HUDClass = SoftClass.LoadSynchronous();
		if (!HUDClass)
		{
			UE_LOG(LogAstral, Warning, TEXT("UAstralRootLayout: HUD 클래스 '%s' 를 불러오지 못함 — 이 HUD 없이 진행 (%s)"), *SoftClass.ToString(), *GetNameSafe(GameState));
			continue;
		}
		AddToOverlay(HUDLayer, HUDClass);
	}

	for (const FAstralContextScreen& Screen : GameState->GetContextScreens())
	{
		if (!Screen.ActionTag.IsValid() || Screen.ScreenClass.IsNull())
		{
			continue;
		}
		FBindUIActionArgs Args(Screen.ActionTag, /*bShouldDisplayInActionBar*/ false, FSimpleDelegate::CreateUObject(this, &ThisClass::HandleContextScreenAction, Screen.ScreenClass));
		Args.InputMode = ECommonInputMode::Game;   // 메뉴가 떠 있는 동안에는 열지 않는다 — 그때 같은 키는 화면의 것이다
		const FUIActionBindingHandle Handle = RegisterUIActionBinding(Args);
		if (Handle.IsValid())
		{
			ContextBindings.Add(Handle);
		}
	}
}

UAstralActivatableWidget* UAstralRootLayout::PushScreen(TSubclassOf<UAstralActivatableWidget> ScreenClass, EAstralUILayer Layer)
{
	UCommonActivatableWidgetStack* Stack = GetStack(Layer);
	if (!Stack || !ScreenClass)
	{
		return nullptr;
	}
	if (UAstralActivatableWidget* Top = GetTopScreen(Layer); Top && Top->GetClass() == ScreenClass && Top->IsActivated())
	{
		return Top;
	}
	const bool bModal = Layer == EAstralUILayer::Modal;
	return Stack->AddWidget<UAstralActivatableWidget>(ScreenClass, [bModal](UAstralActivatableWidget& Screen) { Screen.SetTreatedAsModal(bModal); });
}

UAstralActivatableWidget* UAstralRootLayout::GetTopScreen(EAstralUILayer Layer) const
{
	const UCommonActivatableWidgetStack* Stack = GetStack(Layer);
	return Stack ? Cast<UAstralActivatableWidget>(Stack->GetActiveWidget()) : nullptr;
}

UUserWidget* UAstralRootLayout::FindHUDWidget(const UClass* WidgetClass) const
{
	if (HUDLayer && WidgetClass)
	{
		for (UWidget* Child : HUDLayer->GetAllChildren())
		{
			if (Child && Child->IsA(WidgetClass))
			{
				return Cast<UUserWidget>(Child);
			}
		}
	}
	return nullptr;
}

UUserWidget* UAstralRootLayout::ShowDebugWidget(TSubclassOf<UUserWidget> WidgetClass)
{
	if (!DebugLayer || !WidgetClass)
	{
		return nullptr;
	}
	for (UWidget* Child : DebugLayer->GetAllChildren())
	{
		if (Child && Child->GetClass() == WidgetClass)
		{
			return Cast<UUserWidget>(Child);
		}
	}
	return AddToOverlay(DebugLayer, WidgetClass);
}

UUserWidget* UAstralRootLayout::AddToOverlay(UOverlay* Overlay, TSubclassOf<UUserWidget> WidgetClass)
{
	UUserWidget* Widget = CreateWidget<UUserWidget>(GetOwningPlayer(), WidgetClass);
	if (Widget)
	{
		AstralRootLayout::AddFilled(Overlay, Widget);
	}
	return Widget;
}

UCommonActivatableWidgetStack* UAstralRootLayout::GetStack(EAstralUILayer Layer) const
{
	return Layer == EAstralUILayer::Modal ? ModalStack : MenuStack;
}

void UAstralRootLayout::HandleContextScreenAction(TSoftClassPtr<UAstralActivatableWidget> ScreenClass)
{
	if (UClass* LoadedClass = ScreenClass.LoadSynchronous())
	{
		PushScreen(LoadedClass, EAstralUILayer::Menu);
	}
	else
	{
		UE_LOG(LogAstral, Warning, TEXT("UAstralRootLayout: 화면 클래스 '%s' 를 불러오지 못함"), *ScreenClass.ToString());
	}
}
