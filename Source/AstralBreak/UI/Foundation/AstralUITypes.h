#pragma once

#include "CoreMinimal.h"
#include "UITag.h"
#include "UObject/SoftObjectPtr.h"
#include "AstralUITypes.generated.h"

class UAstralActivatableWidget;

/** 화면이 오르는 층 — 아래에서 위로. HUD 층은 켜고 끄는 화면이 아니므로 여기 없다(맵의 목록으로만 채운다) */
UENUM(BlueprintType)
enum class EAstralUILayer : uint8
{
	/** 메뉴 화면 — 겹쳐 쌓이고 맨 위만 켜진다 */
	Menu,
	/** 확인 창처럼 아래를 모두 막는 화면 — Menu 화면이 켜져 있어도 이것만 입력을 받는다 */
	Modal
};

/** 이 맵에서 UI 액션으로 여는 화면 하나 */
USTRUCT()
struct FAstralContextScreen
{
	GENERATED_BODY()

	/** 여는 액션 — 키는 DefaultInput.ini [/Script/CommonUI.CommonUIInputSettings] */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|UI")
	FUIActionTag ActionTag;

	/** Menu 층에 여는 화면 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|UI")
	TSoftClassPtr<UAstralActivatableWidget> ScreenClass;
};
