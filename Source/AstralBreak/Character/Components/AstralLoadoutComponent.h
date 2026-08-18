#pragma once

#include "CoreMinimal.h"
#include "Components/PawnComponent.h"
#include "AstralLoadoutComponent.generated.h"

class AAstralPlayerState;

/** 장비 복원에 실제 쓰인 소스 — 디버그 가시성용 (값 = "무엇을 썼는가", 우선순위 아님) */
UENUM()
enum class EAstralLoadoutSource : uint8
{
	None,
	PartyCache,
	PlayerState,
	PawnDataFallback,
};

/**
 * 히어로 전용 기능
 * 초기화는 소유 폰의 OnAbilitySystemInitialized가 명시 호출
 * "장비 정책 주입 → 스타일 시드 → 로드아웃 적용" 순서 불변식이 델리게이트 등록 순서로 약화되지 않게.
 */
UCLASS(ClassGroup=(Custom), Meta = (BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralLoadoutComponent : public UPawnComponent
{
	GENERATED_BODY()

public:
	UAstralLoadoutComponent(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
	
	void HandleAbilitySystemInitialized();
	void HandleAbilitySystemUninitialized();
	
	void ApplyLoadout(bool bReapplyEquipment);

	EAstralLoadoutSource GetLastLoadoutSource() const { return LastLoadoutSource; }

protected:
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:

	void RefreshAppearanceFromLoadout();
	void RestoreEquipmentFromLoadout(bool bReapply);

	void HandleLoadoutChanged();
	void UnbindLoadoutChanged();

	AAstralPlayerState* GetAstralPlayerState() const;

	EAstralLoadoutSource LastLoadoutSource = EAstralLoadoutSource::None;

	TWeakObjectPtr<AAstralPlayerState> BoundPlayerState;

	FDelegateHandle LoadoutChangedHandle;
};
