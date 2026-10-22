#pragma once

#include "CoreMinimal.h"
#include "AstralEquipmentActor.h"
#include "AstralWeaponDefinition.h"
#include "AstralWeaponActor.generated.h"

class USkeletalMeshComponent;

/**
 * 무기 액터 — 계열당 1클래스, 변형 차이는 런타임 MeshInfo(메시+상태별 자세값) 적용.
 * SkeletalMeshComponent의 메시는 기본 비복제이므로 MeshInfo를 ReplicatedUsing으로 복제해
 * 클라이언트에서도 변형이 보이게 한다. 메시는 루트(씬)의 자식이라 상태 자세값(Attach/HolsterOffset)이
 * 액터 부착 자세와 독립적인 로컬 트랜스폼으로 들어간다 — 부착 상태에 따라 둘 중 하나를 적용.
 * 데미지 판정은 TraceStart/TraceEnd 소켓 구간의 연속 스윕(AbilityTask_AttackTraceWindows) — 콜리전 없음.
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

	/**
	 * 왼손 파지점 — LeftHandGripSocket 을 부착된 캐릭터 메시의 ReferenceBone 공간으로 환산한다. 손(Held)에 붙어 있고 소켓이 있을 때만 true.
	 * 무기는 손 본에 붙은 강체라 결과는 자세와 무관한 상수 — 부착·외형이 바뀔 때만 다시 구한다(장비 매니저)
	 */
	bool GetLeftHandGrip(FName ReferenceBone, FTransform& OutGrip) const;

protected:
	/** 무기 메시 소켓을 부착된 캐릭터 메시의 ReferenceBone 공간으로 — 손(Held)에 붙어 있고 소켓이 있을 때만 true. 왼손 파지점·총구가 같은 규칙을 쓴다 */
	bool GetSocketInReferenceBone(FName Socket, FName ReferenceBone, FTransform& OutTransform) const;

	//~AActor
	virtual void BeginPlay() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	//~End AActor

	//~AAstralEquipmentActor
	virtual void HandleAttachStateChanged() override;
	//~End AAstralEquipmentActor

	UFUNCTION()
	void OnRep_MeshInfo();

	void ApplyMeshInfo();

protected:
	/** 루트(씬)의 자식 — 상태 자세값(Attach/HolsterOffset)을 로컬 트랜스폼으로 받는다 */
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

	/**
	 * 왼손 IK 파지 소켓 (무기 메시) — 비우면 한손 무기(왼손 IK 없음). 이름은 계열 액터 클래스의 관례, 위치·회전은 변형 메시마다 그 소켓이 정한다.
	 * 소켓은 왼손 본(hand_l) 트랜스폼 그대로 — 손 모양 조정은 무기 메시 소켓을 옮긴다
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Weapon|Animation")
	FName LeftHandGripSocket;
};
