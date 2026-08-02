#pragma once

#include "CoreMinimal.h"
#include "AstralEquipmentActor.h"
#include "AstralWeaponDefinition.h"
#include "AstralWeaponActor.generated.h"

class USkeletalMeshComponent;

/**
 * 무기 액터 — 계열당 1클래스, 변형 차이는 런타임 MeshInfo(메시+피벗 보정) 적용.
 * SkeletalMeshComponent의 메시는 기본 비복제이므로 MeshInfo를 ReplicatedUsing으로 복제해
 * 클라이언트에서도 변형이 보이게 한다. 메시는 루트(씬)의 자식이라 MeshOffset이
 * 액터 부착 자세와 독립적인 로컬 트랜스폼으로 들어간다.
 * 데미지 판정은 TraceStart/TraceEnd 소켓 구간의 연속 스윕(AbilityTask_WeaponTrace) — 콜리전 없음.
 */
UCLASS()
class ASTRALBREAK_API AAstralWeaponActor : public AAstralEquipmentActor
{
	GENERATED_BODY()

public:
	AAstralWeaponActor();

	//~AAstralEquipmentActor
	virtual void OnEquipmentDataApplied_Implementation(const UAstralItemDefinition* Definition) override;
	//~End AAstralEquipmentActor

	/** 서버 — 변형 메시+보정 적용 (클라는 OnRep_MeshInfo) */
	void SetMeshInfo(const FAstralWeaponMeshInfo& InMeshInfo);

	FVector GetTraceStartLocation() const;
	FVector GetTraceEndLocation() const;

	USkeletalMeshComponent* GetMeshComponent() const { return MeshComponent; }

protected:
	//~AActor
	virtual void BeginPlay() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	//~End AActor

	UFUNCTION()
	void OnRep_MeshInfo();

	void ApplyMeshInfo();

protected:
	/** 루트(씬)의 자식 — MeshOffset(피벗 보정)을 로컬 트랜스폼으로 받는다 */
	UPROPERTY(VisibleAnywhere, Category = "Astral|Weapon")
	TObjectPtr<USkeletalMeshComponent> MeshComponent;

	/** 변형 메시+보정 — 한 단위로 복제 (메시/오프셋이 서로 다른 프레임에 도착하는 어긋남 방지) */
	UPROPERTY(ReplicatedUsing = OnRep_MeshInfo)
	FAstralWeaponMeshInfo MeshInfo;

	/** 트레이스 구간 소켓 (무기 메쉬에 있어야 함 — 밑동/끝) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Weapon|Trace")
	FName TraceStartSocket = TEXT("TraceStart");

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Weapon|Trace")
	FName TraceEndSocket = TEXT("TraceEnd");
};
