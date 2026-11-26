#include "AstralUIGameplayTags.h"

namespace AstralGameplayTags
{
	UE_DEFINE_GAMEPLAY_TAG_COMMENT(UI_Action_Back, "UI.Action.Back", "맨 위 화면을 닫는다 (Esc · 게임패드 B)");
	UE_DEFINE_GAMEPLAY_TAG_COMMENT(UI_Action_HubReady, "UI.Action.HubReady", "허브 준비 화면을 열고 닫는다 (Tab · 게임패드 Special_Left)");

	FUIActionTag MakeUIActionTag(const FGameplayTag& Tag)
	{
		check(Tag.ToString().StartsWith(TEXT("UI.Action.")));
		FUIActionTag Out;
		static_cast<FGameplayTag&>(Out) = Tag;   // 뿌리 확인(ConvertChecked) 없이 이름만 옮긴다 — 위 check 가 같은 조건을 이름으로 본다
		return Out;
	}
}
