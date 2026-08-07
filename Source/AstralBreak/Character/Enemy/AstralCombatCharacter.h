#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "GameFramework/Character.h"
#include "GenericTeamAgentInterface.h"
#include "UObject/PrimaryAssetId.h"
#include "AstralCombatCharacter.generated.h"

class UAstralAbilitySystemComponent;
class UAstralAbilitySet;
class UAstralCombatSet;
class UAstralEquipmentManagerComponent;
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

	UFUNCTION(BlueprintPure, Category = "Astral|Combat")
	bool IsTelegraphAttackEnabled() const { return bTelegraphAttackEnabled; }

	/**
	 * 텔레그래프 예고 표시 — 전 머신 DrawDebug (디버그 전용, GameplayCue 도입 시 제거 예정).
	 * DrawDebug는 월드 로컬이라 서버(ServerOnly GA)에서만 그리면 클라 뷰포트에 안 보임 → 멀티캐스트로 각 머신이 그린다
	 */
	UFUNCTION(NetMulticast, Unreliable)
	void MulticastDrawTelegraphDebug(float Duration, float TraceStartOffset, float TraceDistance, float TraceRadius);

protected:
	//~ AActor
	virtual void PostInitializeComponents() override;
	virtual void BeginPlay() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	//~ End AActor

	/** 사망 시작 — 물리 반응(콜리전/이동 정지)은 액터 책임. FinishDeath 타이밍은 GA_Death의 DeathDuration이 결정 */
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

	/** 스폰 시(서버) 장착할 기본 장비 — 더미는 비워도 됨, M3 무기 든 몬스터용 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Equipment", Meta = (AllowedTypes = "AstralWeaponDefinition,AstralRangedWeaponDefinition"))
	TArray<FPrimaryAssetId> DefaultEquipment;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Components")
	TObjectPtr<UAstralEquipmentManagerComponent> EquipmentManagerComponent;

	/** 팀 ID (플레이어 = 0, 적 = 1). 런타임 변경(SetGenericTeamId)이 클라에도 반영되도록 복제 */
	UPROPERTY(EditAnywhere, Replicated, Category = "Astral|Team")
	uint8 TeamId = 1;

	/** 예고 공격 루프 활성 여부 — GA_Enemy_TelegraphAttack이 매 사이클 확인. 패시브/예고 더미를 레벨에서 구분 배치 (서버 판정 전용) */
	UPROPERTY(EditAnywhere, Category = "Astral|Combat")
	bool bTelegraphAttackEnabled = false;

	/** FinishDeath 후 액터 제거까지의 시간 (초) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Death", Meta = (ClampMin = "0.0"))
	float DestroyAfterDeathDelay = 2.0f;
};
