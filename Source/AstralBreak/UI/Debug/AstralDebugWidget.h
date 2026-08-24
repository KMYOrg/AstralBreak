#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "AstralDebugWidget.generated.h"

class UTextBlock;

/**
 * 
 */
UCLASS()
class ASTRALBREAK_API UAstralDebugWidget : public UUserWidget
{
	GENERATED_BODY()
	
protected:
	
	// Debug 용이므로 매프레임 단순히 ASC 조회
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;

	/** WBP에 동일 이름 TextBlock을 둘 것. Optional이라 없어도 컴파일은 됨 */
	UPROPERTY(meta = (BindWidgetOptional))
	TObjectPtr<UTextBlock> DebugText;

	FString BuildDebugString() const;

	FString GetNetModeString() const;
	FString GetRoleString() const;
	FString GetRemoteRoleString() const;
	FString GetAttributesString() const;

	/** 스프린트 의도/승인 분리 관측 — 서버 권위 검증(의도 true + 승인 false = 속도 미상승)의 확인 지점 */
	FString GetMovementString() const;
	FString GetAbilitiesString() const;
	FString GetDeathStateString() const;
	FString GetTargetString() const;

	/** M1 — 맵/로드아웃 소스/파티 준비 상태 */
	FString GetPartyString() const;
};
