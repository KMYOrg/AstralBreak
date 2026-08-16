#pragma once

#include "CoreMinimal.h"
#include "Equipment/AstralEquipmentTypes.h"
#include "GameFramework/Actor.h"
#include "AstralEquipmentActor.generated.h"

class UAstralItemDefinition;
class USceneComponent;

/**
 * 장비 표현 액터 베이스
 * 루트는 빈 씬 컴포넌트 — 액터 트랜스폼(계열의 AttachTransform, 파지 자세)과
 * 표현 컴포넌트의 로컬 보정(변형별 상태 자세값)을 분리하기 위함.
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

	/**
	 * 서버 — 부착 상태 세팅 (EquipmentInstance::ApplyAttachState가 호출).
	 * 스폰 시엔 FinishSpawning 전에 확정되어 초기 번치에 동봉. 클라는 OnRep으로 표현 갱신
	 */
	void SetAttachState(EAstralEquipmentAttachState InState);

	EAstralEquipmentAttachState GetAttachState() const { return AttachState; }

protected:
	//~AActor
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	//~End AActor

	UFUNCTION()
	void OnRep_AttachState();

	/** 상태별 표현 갱신 훅 (서버·클라 양쪽) — 파생이 상태별 자세값 교체·전환 연출에 사용 */
	virtual void HandleAttachStateChanged() {}

protected:
	UPROPERTY(VisibleAnywhere, Category = "Astral|Equipment")
	TObjectPtr<USceneComponent> RootSceneComponent;

	UPROPERTY(Transient)
	TObjectPtr<const UAstralItemDefinition> AppliedDefinition;

	/** 부착 상태 — 변형별 상태 자세값(HolsterOffset) 적용은 클라에서도 일어나므로 복제 */
	UPROPERTY(ReplicatedUsing = OnRep_AttachState)
	EAstralEquipmentAttachState AttachState = EAstralEquipmentAttachState::Held;
};
