#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "GameFramework/Character.h"
#include "UObject/PrimaryAssetId.h"
#include "AstralCharacter.generated.h"

class UAstralAbilitySystemComponent;
class UAstralEquipmentManagerComponent;
class UAstralHealthComponent;
class UAstralPawnExtensionComponent;

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
	UAstralAbilitySystemComponent* GetAstralAbilitySystemComponent() const;

	UFUNCTION(BlueprintPure, Category = "Astral|Character")
	UAstralHealthComponent* GetHealthComponent() const { return HealthComponent; }

	UFUNCTION(BlueprintPure, Category = "Astral|Character")
	UAstralEquipmentManagerComponent* GetEquipmentManagerComponent() const { return EquipmentManagerComponent; }

	UFUNCTION(BlueprintPure, Category = "Astral|Character")
	UAstralPawnExtensionComponent* GetPawnExtensionComponent() const { return PawnExtComponent; }

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

	/** 디버그 — 콘솔에서 `SetMoveSpeedMultiplier 1.5`. 걷기·질주 속도가 함께 변하는지 검증용 */
	UFUNCTION(Exec)
	void SetMoveSpeedMultiplier(float Multiplier = 1.0f);

	/** 디버그 — 콘솔에서 `CancelAttack`. 활성 공격 GA(Ability.Attack)를 로컬에서 취소한다. */
	UFUNCTION(Exec)
	void CancelAttack();

	/**
	 * 디버그 — 콘솔에서 `SpawnEnemy` 또는 `SpawnEnemy BP_Enemy_Melee 600`. 내 앞 Distance(cm, 생략 시 400)에 적을 서버에서 스폰한다.
	 * 이름은 /Game/Characters/Enemy/ 아래의 BP 이름(생략 시 BP_Enemy_Melee). 맵에 배치하지 않고 어느 맵 · 넷 구성에서도 적을 불러 본다
	 * (Docs/Design/m3-enemy-ai.md §8 ⑧ — 스폰 시스템은 단위 D)
	 */
	UFUNCTION(Exec)
	void SpawnEnemy(const FString& EnemyName, float Distance = 0.0f);

	/** 디버그 — 콘솔에서 `FillUlt`. 오의 게이지를 최대치로 채운다 (오의 · 체인 시험용 — m4-ult-chain.md §6 단위 A) */
	UFUNCTION(Exec)
	void FillUlt();

	/**
	 * 디버그 — 콘솔에서 `SetUltBlocked 1` / `SetUltBlocked 0`. 오의 차단 태그(State.Ult.Blocked)를 걸고 푼다.
	 * 루즈 태그는 복제되지 않으므로 부른 쪽과 서버 양쪽에 건다 — M5 의 Burst Aura 는 GE 로 걸어 복제에 맡긴다
	 */
	UFUNCTION(Exec)
	void SetUltBlocked(bool bBlocked = true);

protected:
	UFUNCTION(Server, Reliable)
	void ServerDamageSelf(float Amount);

	UFUNCTION(Server, Reliable)
	void ServerReviveSelf();

	UFUNCTION(Server, Reliable)
	void ServerEquipWeapon(FPrimaryAssetId WeaponId);

	UFUNCTION(Server, Reliable)
	void ServerSetMoveSpeedMultiplier(float Multiplier);

	UFUNCTION(Server, Reliable)
	void ServerSpawnEnemy(const FString& EnemyName, float Distance);

	UFUNCTION(Server, Reliable)
	void ServerFillUlt();

	UFUNCTION(Server, Reliable)
	void ServerSetUltBlocked(bool bBlocked);

	virtual void OnAbilitySystemInitialized();
	virtual void OnAbilitySystemUninitialized();

	/** 사망 물리 반응 — 게임플레이 필수(콜리전/이동 정지)만 C++. 몽타주·래그돌 등 연출은 BP가 OnDeathStarted 구독 */
	UFUNCTION()
	virtual void HandleDeathStarted(AActor* OwningActor);

	/** 사망 완료 — 기본은 dead 유지 (Hero: TODO M6 리스폰/관전). CombatCharacter는 LifeSpan 정리로 오버라이드 */
	UFUNCTION()
	virtual void HandleDeathFinished(AActor* OwningActor);

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
};
