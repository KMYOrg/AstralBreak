#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "AstralLoadoutDisplayComponent.generated.h"

/**
 * 로비 무기 코스메틱 표시 — 로비용 폰 BP에만 부착 (문맥 분리 = 컴포넌트 조립 + PawnData.PawnClass 축).
 * 복제되는 PlayerState.Loadout을 각 머신이 읽어 **비복제 표시 액터**를 로컬 스폰,
 * 계열의 DisplaySocket(등/허리 등)에 부착. 장비 시스템·ASC 무접촉 — 부여 위험 원천 차단.
 * ⚠️ 전투 폰 BP에 부착하지 말 것 — 실장비와 코스메틱이 겹쳐 보인다.
 */
UCLASS(BlueprintType, Meta = (BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralLoadoutDisplayComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	/** 멱등 재구성 — 기존 표시 액터 전량 정리 후 현재 Loadout 기준 재스폰. PS 미도착이면 no-op */
	void RefreshDisplay();

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	/**
	 * ASC 초기화 = PS 확정 시점 — PawnExt RegisterAndCall 경유라 이미 지난 시점도 즉시 호출된다.
	 * 여기서 PS.OnLoadoutChanged 구독 + 초기 1회 갱신 (구독 전에 지나간 Broadcast를 놓치는 문제 해소)
	 */
	void HandleAbilitySystemInitialized();

	void ClearDisplayActors();

	/** 표시 액터 — 머신 로컬·비복제 */
	UPROPERTY(Transient)
	TArray<TObjectPtr<AActor>> DisplayActors;

	/** 구독 중인 PS — travel/재빙의로 PS가 바뀌면 재구독 */
	TWeakObjectPtr<class AAstralPlayerState> BoundPlayerState;

	FDelegateHandle LoadoutChangedHandle;
};
