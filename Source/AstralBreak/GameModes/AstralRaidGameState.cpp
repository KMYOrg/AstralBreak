#include "AstralRaidGameState.h"

#include "AstralChainBurstComponent.h"
#include "Blueprint/UserWidget.h"

AAstralRaidGameState::AAstralRaidGameState(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	ChainBurstComponent = CreateDefaultSubobject<UAstralChainBurstComponent>(TEXT("ChainBurstComponent"));

	// 전투 맵의 HUD — 승격본(uigen promote_widget). 허브 폰에는 스태미나 · 오의 같은 전투 자원이 없어 허브 목록에는 없다.
	// 소프트 참조라 애셋이 없어도 클래스 로드는 깨지지 않는다(UAstralRootLayout 이 경고만). BP 에서 덮어쓸 수 있다
	ContextHUDWidgets = {
		TSoftClassPtr<UUserWidget>(FSoftObjectPath(TEXT("/Game/UI/HUD/StatusHUD/WBP_StatusHUD.WBP_StatusHUD_C"))),
		TSoftClassPtr<UUserWidget>(FSoftObjectPath(TEXT("/Game/UI/HUD/CombatHUD/WBP_CombatHUD.WBP_CombatHUD_C"))),
	};
}
