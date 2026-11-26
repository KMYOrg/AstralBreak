// 화면 시험 공용 — PIE 자동 시험과 별도 프로세스 시험(Gauntlet)이 같이 쓴다

#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Components/PanelWidget.h"

namespace AstralUITest
{
	/**
	 * 화면에 붙어 있는가 — 스스로 화면에 올랐거나 화면에 오른 위젯 안에 있다.
	 * HUD 는 UAstralRootLayout 의 HUD 층에 있으므로 HUD 자신의 IsInViewport 는 거짓이다
	 */
	inline bool IsOnScreen(const UWidget* Widget)
	{
		while (Widget)
		{
			if (Widget->IsInViewport())
			{
				return true;
			}
			// 같은 위젯 트리 안에서는 부모 칸으로, 트리의 뿌리에서는 그 트리를 가진 UserWidget 으로 올라간다
			const UWidget* Parent = Widget->GetParent();
			Widget = Parent ? Parent : Widget->GetTypedOuter<UUserWidget>();
		}
		return false;
	}
}
