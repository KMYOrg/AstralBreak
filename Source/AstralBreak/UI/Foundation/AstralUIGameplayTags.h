#pragma once

#include "NativeGameplayTags.h"

/**
 * UI 액션 태그 — 화면을 여닫는 입력. 게임 입력(InputTag.*, Enhanced Input)과 다른 길이다:
 * 키는 Config/DefaultInput.ini 의 [/Script/CommonUI.CommonUIInputSettings] 에 있고, CommonUI 라우터가 가장 안쪽의 켜진 화면부터 준다.
 * 새 태그를 더하면 그 ini 에 키를 같이 적는다 — 키가 없는 태그는 묶을 수 없다
 */
namespace AstralGameplayTags
{
	/** 뒤로 — 맨 위 화면 하나를 닫는다 */
	UE_DECLARE_GAMEPLAY_TAG_EXTERN(UI_Action_Back);
}
