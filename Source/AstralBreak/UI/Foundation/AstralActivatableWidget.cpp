#include "AstralActivatableWidget.h"

#include "AstralUIGameplayTags.h"
#include "CommonInputModeTypes.h"
#include "Input/CommonUIInputTypes.h"
#include "Input/UIActionBindingHandle.h"
#include "UITag.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(AstralActivatableWidget)

UAstralActivatableWidget::UAstralActivatableWidget(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

TOptional<FUIInputConfig> UAstralActivatableWidget::GetDesiredInputConfig() const
{
	switch (InputConfig)
	{
	case EAstralWidgetInputMode::GameAndMenu:
		return FUIInputConfig(ECommonInputMode::All, GameMouseCaptureMode);
	case EAstralWidgetInputMode::Game:
		return FUIInputConfig(ECommonInputMode::Game, GameMouseCaptureMode);
	case EAstralWidgetInputMode::Menu:
		return FUIInputConfig(ECommonInputMode::Menu, EMouseCaptureMode::NoCapture);
	case EAstralWidgetInputMode::Default:
	default:
		return TOptional<FUIInputConfig>();
	}
}

void UAstralActivatableWidget::SetTreatedAsModal(bool bInModal)
{
	bIsModal = bInModal;
}

void UAstralActivatableWidget::NativeOnInitialized()
{
	Super::NativeOnInitialized();

	if (bClosesOnBackAction)
	{
		RegisterUIActionBinding(FBindUIActionArgs(FUIActionTag::ConvertChecked(AstralGameplayTags::UI_Action_Back), /*bShouldDisplayInActionBar*/ false,
			FSimpleDelegate::CreateUObject(this, &ThisClass::HandleBackActionTriggered)));
	}
}

void UAstralActivatableWidget::HandleBackActionTriggered()
{
	DeactivateWidget();
}
