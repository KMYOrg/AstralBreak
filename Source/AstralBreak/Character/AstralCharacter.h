#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "GameFramework/Character.h"
#include "UObject/PrimaryAssetId.h"
#include "AstralCharacter.generated.h"

class UAstralAbilitySystemComponent;
class UAstralEquipmentManagerComponent;
class UAstralHealthComponent;
class UAstralLoadoutComponent;
class UAstralPawnExtensionComponent;
class AAstralPlayerState;

UCLASS()
class ASTRALBREAK_API AAstralCharacter : public ACharacter, public IAbilitySystemInterface
{
	GENERATED_BODY()

public:
	AAstralCharacter(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	//~ IAbilitySystemInterface
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;
	//~ End IAbilitySystemInterface

	UFUNCTION(BlueprintCallable, Category = "Astral|Character")
	AAstralPlayerState* GetAstralPlayerState() const;

	UFUNCTION(BlueprintCallable, Category = "Astral|Character")
	UAstralAbilitySystemComponent* GetAstralAbilitySystemComponent() const;

	UFUNCTION(BlueprintPure, Category = "Astral|Character")
	UAstralHealthComponent* GetHealthComponent() const { return HealthComponent; }

	UFUNCTION(BlueprintPure, Category = "Astral|Character")
	UAstralEquipmentManagerComponent* GetEquipmentManagerComponent() const { return EquipmentManagerComponent; }

	UFUNCTION(BlueprintPure, Category = "Astral|Character")
	UAstralLoadoutComponent* GetLoadoutComponent() const { return LoadoutComponent; }

	/** 디버그 — 콘솔에서 `DamageSelf 50`. 데미지 파이프라인(GE_Damage_Base)을 그대로 태워 사망/수급 경로 검증용 */
	UFUNCTION(Exec)
	void DamageSelf(float Amount = 25.0f);

	/** 디버그 — 콘솔에서 `ReviveSelf`. HP 전체 회복 + 사망 상태 리셋 (사망 재테스트용) */
	UFUNCTION(Exec)
	void ReviveSelf();

	/**
	 * 디버그 — 콘솔에서 `EquipWeapon WD_HSword_A` (타입 생략 시 AstralWeaponDefinition 가정).
	 * 기존 장비 전체 해제 후 교체 — 로비 없이 무기 변형(메쉬·사거리·스탯) 검증용
	 */
	UFUNCTION(Exec)
	void EquipWeapon(const FString& WeaponIdString);

protected:
	UFUNCTION(Server, Reliable)
	void ServerDamageSelf(float Amount);

	UFUNCTION(Server, Reliable)
	void ServerReviveSelf();

	UFUNCTION(Server, Reliable)
	void ServerEquipWeapon(FPrimaryAssetId WeaponId);

	virtual void OnAbilitySystemInitialized();
	virtual void OnAbilitySystemUninitialized();

	/** 사망 물리 반응 — 게임플레이 필수(콜리전/이동 정지)만 C++. 몽타주·래그돌 등 연출은 BP가 OnDeathStarted 구독 */
	UFUNCTION()
	virtual void HandleDeathStarted(AActor* OwningActor);

	/** 부활(디버그 ReviveSelf / 추후 M6 리스폰) — 콜리전/이동 복구 */
	UFUNCTION()
	virtual void HandleDeathReset(AActor* OwningActor);

protected:
	//~ AActor
	virtual void PreInitializeComponents() override;
	virtual void PostInitializeComponents() override;
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	//~ End AActor

	//~ APawn
	virtual void PossessedBy(AController* NewController) override;
	virtual void UnPossessed() override;
	virtual void OnRep_Controller() override;
	virtual void OnRep_PlayerState() override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	//~ End APawn


protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Components", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralPawnExtensionComponent> PawnExtComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Components", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralHealthComponent> HealthComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Components", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralEquipmentManagerComponent> EquipmentManagerComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Components", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralLoadoutComponent> LoadoutComponent;
};
