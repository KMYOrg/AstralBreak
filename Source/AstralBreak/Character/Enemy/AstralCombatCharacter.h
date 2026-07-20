#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "GameFramework/Character.h"
#include "GenericTeamAgentInterface.h"
#include "AstralCombatCharacter.generated.h"

class UAstralAbilitySystemComponent;
class UAstralAbilitySet;
class UAstralCombatSet;
class UAstralHealthComponent;
class UAstralHealthSet;

/**
 * 자기 자신이 ASC를 소유하는 전투 캐릭터 베이스 — 타겟 더미(M2)와 M3 몬스터의 공통 조상.
 * Hero(ASC를 PlayerState에서 빌려옴)와 달리 InitState 체인/PawnExtension 없이 스폰 즉시 완결 초기화.
 * HealthSet/CombatSet은 PlayerState와 동일하게 CDO 서브오브젝트 패턴 (스폰 시점부터 존재, 복제 타이밍 안전).
 */
UCLASS()
class ASTRALBREAK_API AAstralCombatCharacter : public ACharacter, public IAbilitySystemInterface, public IGenericTeamAgentInterface
{
	GENERATED_BODY()

public:
	AAstralCombatCharacter(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	//~ IAbilitySystemInterface
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;
	//~ End IAbilitySystemInterface

	//~ IGenericTeamAgentInterface
	virtual void SetGenericTeamId(const FGenericTeamId& NewTeamID) override { TeamId = NewTeamID.GetId(); }
	virtual FGenericTeamId GetGenericTeamId() const override { return FGenericTeamId(TeamId); }
	//~ End IGenericTeamAgentInterface

	UFUNCTION(BlueprintPure, Category = "Astral|Combat")
	UAstralHealthComponent* GetHealthComponent() const { return HealthComponent; }

protected:
	//~ AActor
	virtual void PostInitializeComponents() override;
	virtual void BeginPlay() override;
	//~ End AActor

	/** 사망 시작 — 물리 반응(콜리전/이동 정지)은 액터 책임. 연출 완료 타이머로 FinishDeath 진입 */
	UFUNCTION()
	virtual void HandleDeathStarted(AActor* OwningActor);

	/** 사망 완료 — MVP는 LifeSpan으로 정리. M3에서 스폰/디스폰 인터페이스로 교체 예정 (풀링 대비) */
	UFUNCTION()
	virtual void HandleDeathFinished(AActor* OwningActor);

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Components")
	TObjectPtr<UAstralAbilitySystemComponent> AbilitySystemComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Components")
	TObjectPtr<UAstralHealthComponent> HealthComponent;

	UPROPERTY()
	TObjectPtr<const UAstralHealthSet> HealthSet;

	UPROPERTY()
	TObjectPtr<const UAstralCombatSet> CombatSet;

	/** 스폰 시(서버) 부여할 어빌리티/이펙트 세트 — 더미는 비워도 됨, M3 몬스터 GA용 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Abilities")
	TArray<TObjectPtr<const UAstralAbilitySet>> AbilitySets;

	/** 팀 ID (플레이어 = 0, 적 = 1) */
	UPROPERTY(EditAnywhere, Category = "Astral|Team")
	uint8 TeamId = 1;

	/** DeathStarted → FinishDeath까지의 연출 시간 (초) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Death", Meta = (ClampMin = "0.0"))
	float DeathFinishDelay = 3.0f;

	/** FinishDeath 후 액터 제거까지의 시간 (초) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Death", Meta = (ClampMin = "0.0"))
	float DestroyAfterDeathDelay = 2.0f;

private:
	FTimerHandle DeathFinishTimerHandle;
};
