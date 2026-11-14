// uigen 이 처음 한 번 만든 스텁 — 이제 사람 소유다. uigen 은 이 파일을 다시 쓰지 않는다(설계 Docs/Design/ui-autogen-pipeline.md §3-3).
// 게임 연결(GAS 속성 변화 · 컴포넌트 통지 → 생성 베이스의 setter 호출)은 여기에 쓴다.

#pragma once

#include "CoreMinimal.h"
#include "UI/HUD/AutoGen/AstralCombatHUDViewBase.h"
#include "AstralCombatHUDWidget.generated.h"

/**
 * CombatHUD 화면 위젯 — WBP 의 부모 클래스. 바인딩 위젯과 setter 는 생성 베이스 UAstralCombatHUDViewBase 에 있다.
 */
UCLASS()
class ASTRALBREAK_API UAstralCombatHUDWidget : public UAstralCombatHUDViewBase
{
	GENERATED_BODY()
};
