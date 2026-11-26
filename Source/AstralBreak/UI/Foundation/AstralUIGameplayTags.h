#pragma once

#include "NativeGameplayTags.h"
#include "UITag.h"

/**
 * UI 액션 태그 — 화면을 여닫는 입력. 게임 입력(InputTag.*, Enhanced Input)과 다른 길이다:
 * 키는 Config/DefaultInput.ini 의 [/Script/CommonUI.CommonUIInputSettings] 에 있고, CommonUI 라우터가 가장 안쪽의 켜진 화면부터 준다.
 * 새 태그를 더하면 그 ini 에 키를 같이 적는다 — 키가 없는 태그는 묶을 수 없다
 */
namespace AstralGameplayTags
{
	/** 뒤로 — 맨 위 화면 하나를 닫는다 */
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(UI_Action_Back);

	/** 허브 준비 화면 — 게임 입력에서는 연다(허브 GameState 의 ContextScreens), 화면이 떠 있으면 같은 키로 닫는다(화면의 Menu 묶음) */
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(UI_Action_HubReady);

	/**
	 * 네이티브 태그 → UI 액션 태그. 클래스 기본 객체(생성자)에서도 쓸 수 있다 — FUIActionTag::ConvertChecked 는 태그 관리자가 'UI.Action' 뿌리를
	 * 등록하기 전(모듈을 올리며 기본 객체를 만들 때)에는 맞는 태그도 check 에 건다. 'UI.Action.' 아래 태그만 넘긴다
	 */
	ASTRALBREAK_API FUIActionTag MakeUIActionTag(const FGameplayTag& Tag);
}
