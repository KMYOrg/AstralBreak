#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstralEquipmentActor.generated.h"

class UAstralItemDefinition;
class USceneComponent;

/**
 * 장비 표현 액터 베이스
 * 루트는 빈 씬 컴포넌트 — 액터 트랜스폼(계열의 AttachTransform, 파지 자세)과
 * 표현 컴포넌트의 로컬 보정(변형별 피벗 오프셋)을 분리하기 위함.
 */
UCLASS(Abstract)
class ASTRALBREAK_API AAstralEquipmentActor : public AActor
{
	GENERATED_BODY()

public:
	AAstralEquipmentActor();

	/** 장착 데이터 적용 — FinishSpawning 전에 호출되어 복제 프로퍼티가 초기 번치에 동봉된다 */
	UFUNCTION(BlueprintCallable, BlueprintNativeEvent, Category = "Astral|Equipment")
	void OnEquipmentDataApplied(const UAstralItemDefinition* Definition);

	/**
	 * (서버 전용 — 클라 액터는 null). 파생이 자기 Def 타입으로 캐스팅해 읽는다 —
	 */
	const UAstralItemDefinition* GetAppliedDefinition() const { return AppliedDefinition; }

protected:
	UPROPERTY(VisibleAnywhere, Category = "Astral|Equipment")
	TObjectPtr<USceneComponent> RootSceneComponent;

	UPROPERTY(Transient)
	TObjectPtr<const UAstralItemDefinition> AppliedDefinition;
};
