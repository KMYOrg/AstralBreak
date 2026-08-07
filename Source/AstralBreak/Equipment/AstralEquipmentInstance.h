#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "AstralEquipmentInstance.generated.h"

class AActor;
class APawn;
class UAstralItemDefinition;
struct FAstralEquipmentActorToSpawn;

/**
 * 장착된 장비 1개의 런타임 인스턴스 — 복제 서브오브젝트 (EquipmentManagerComponent가 등록).
 * Outer = 소유 폰. 어빌리티 부여 시 SourceObject로 넘겨져 GA가 GetCurrentSourceObject()로 자기 무기를 얻는다.
 * 폰 컴포넌트 소속이므로 폰과 수명을 같이한다 — 로드아웃(선택)은 M1의 별도 레이어.
 */
UCLASS(BlueprintType, Blueprintable)
class ASTRALBREAK_API UAstralEquipmentInstance : public UObject
{
	GENERATED_BODY()

public:
	//~UObject — 복제 서브오브젝트 요건
	virtual bool IsSupportedForNetworking() const override { return true; }
	virtual UWorld* GetWorld() const override final;
	//~End UObject

	UFUNCTION(BlueprintPure, Category = "Astral|Equipment")
	APawn* GetPawn() const;

	UFUNCTION(BlueprintPure, Category = "Astral|Equipment")
	TArray<AActor*> GetSpawnedActors() const { return SpawnedActors; }

	/** 첫 번째 T형 스폰 액터 — WeaponTrace가 무기 액터를 얻는 경로 */
	template<typename T>
	T* GetFirstSpawnedActorOfType() const
	{
		for (AActor* Actor : SpawnedActors)
		{
			if (T* Typed = Cast<T>(Actor))
			{
				return Typed;
			}
		}
		return nullptr;
	}

	/**
	 * 서버 — 정의의 액터들을 스폰·부착.
	 * bActive: 초기 표시 상태 — 비활성이면 숨김 스폰 (FinishSpawning 전에 세팅해 초기 번치에 bHidden 동봉)
	 */
	virtual void SpawnEquipmentActors(const TArray<FAstralEquipmentActorToSpawn>& ActorsToSpawn, const UAstralItemDefinition* Definition, bool bActive);
	virtual void DestroyEquipmentActors();

	/**
	 * 서버 — 활성 전환에 따른 스폰 액터 표시/숨김 (bHidden은 액터 복제 프로퍼티 — 클라 자동 전파).
	 * 전환 연출(머테리얼 등)이 붙으면 이 지점이 훅
	 */
	virtual void SetActorsActive(bool bActive);

	virtual void OnEquipped();
	virtual void OnUnequipped();

protected:
	/** 장착 훅 (BP) — ⚠️ 현재 서버에서만 호출됨. 클라 연출이 필요해지면 FastArray 콜백(PostReplicatedAdd/PreReplicatedRemove) 도입 시점 */
	UFUNCTION(BlueprintImplementableEvent, Category = "Astral|Equipment", Meta = (DisplayName = "OnEquipped"))
	void K2_OnEquipped();

	UFUNCTION(BlueprintImplementableEvent, Category = "Astral|Equipment", Meta = (DisplayName = "OnUnequipped"))
	void K2_OnUnequipped();

private:
	/** 서버 로컬 캐시 — 비복제. 소비자(WeaponTrace)가 전부 서버 전용이고,
	 * 클라에는 액터 자체 복제(bReplicates)가 이미 도달하므로 참조 복제는 추가 정보가 0이다 */
	UPROPERTY()
	TArray<TObjectPtr<AActor>> SpawnedActors;
};
