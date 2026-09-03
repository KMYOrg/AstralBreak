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

	/**
	 * 3열 배치 — 좌상단 DebugText(상태), 우상단 LockOnText(락온·조준), 우하단 PartyText(로비).
	 * WBP에 동일 이름 TextBlock을 둘 것. 전부 Optional — LockOnText/PartyText가 없으면 해당 섹션은 DebugText에 이어 붙는다
	 */
	UPROPERTY(meta = (BindWidgetOptional))
	TObjectPtr<UTextBlock> DebugText;

	UPROPERTY(meta = (BindWidgetOptional))
	TObjectPtr<UTextBlock> LockOnText;

	UPROPERTY(meta = (BindWidgetOptional))
	TObjectPtr<UTextBlock> PartyText;

	/** 좌측 열 — 네트·역할 · Attributes · Movement · Abilities (압축 표기) */
	FString BuildStatusString() const;

	/** 우상단 — [LockOn] + [Target] */
	FString BuildLockOnString() const;

	/** 우하단 — [Party] */
	FString BuildPartyString() const;

	FString GetNetModeString() const;
	FString GetRoleString() const;
	FString GetRemoteRoleString() const;
	FString GetAttributesString() const;

	/** 스프린트 의도/승인 분리 관측 — 서버 권위 검증(의도 true + 승인 false = 속도 미상승)의 확인 지점 */
	FString GetMovementString() const;
	FString GetAbilitiesString() const;
	FString GetDeathStateString() const;
	FString GetTargetString() const;

	/** 락온 1단계 — 모드 · 선택 타겟 · 후보별 (거리, 각도, 점수). 가중치 튜닝의 관측 지점 */
	FString GetLockOnString() const;

	/** M1 — 맵/로드아웃 소스/파티 준비 상태 */
	FString GetPartyString() const;
};
