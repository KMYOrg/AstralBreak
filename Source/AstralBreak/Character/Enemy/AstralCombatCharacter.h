#pragma once

#include "CoreMinimal.h"
#include "Character/AstralCharacter.h"
#include "GenericTeamAgentInterface.h"
#include "UObject/PrimaryAssetId.h"
#include "AstralCombatCharacter.generated.h"

class UAstralAbilitySet;
class UAstralAbilitySystemComponent;
class UAstralCombatSet;
class UAstralHealthSet;

/**
 * 자기 자신이 ASC를 소유하는 전투 캐릭터 — 타겟 더미(M2)와 M3 몬스터의 공통 조상 
 * Hero와 달리 PlayerState를 기다릴 필요가 없어 PostInitializeComponents에서 PawnExtension에 자기 ASC를 바로 넘긴다.
 * HealthSet/CombatSet은 PlayerState와 동일하게 CDO 서브오브젝트 패턴 (스폰 시점부터 존재, 복제 타이밍 안전).
 * InitState 체인은 PawnData가 없어 Spawned에 머무르지만 아무도 기다리지 않는다. 전투 준비 완료는 체인이 아니라 OnCombatReady 가 알린다 —
 * 체인은 Super::BeginPlay 안에서 돌아 AbilitySets 부여보다 앞선다
 */
UCLASS()
class ASTRALBREAK_API AAstralCombatCharacter : public AAstralCharacter, public IGenericTeamAgentInterface
{
	GENERATED_BODY()

public:
	AAstralCombatCharacter(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	//~ IAbilitySystemInterface
	/** 자기 ASC를 직접 — PawnExtension 결합 전(복제 초기 번치 등)에도 유효해야 한다 */
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;
	//~ End IAbilitySystemInterface

	//~ IGenericTeamAgentInterface
	virtual void SetGenericTeamId(const FGenericTeamId& NewTeamID) override { TeamId = NewTeamID.GetId(); }
	virtual FGenericTeamId GetGenericTeamId() const override { return FGenericTeamId(TeamId); }
	//~ End IGenericTeamAgentInterface

	/** 서버에서 ASC 결합 · AbilitySets 부여 · 기본 장비 장착 시도가 끝났는가. 복제하지 않는다 — 클라에서는 항상 false */
	bool IsCombatReady() const { return bCombatReady; }

	/**
	 * 전투 준비 완료 구독 — 이미 끝났으면 그 자리에서 호출한다. 서버 전용.
	 * 빙의와 BeginPlay 의 순서가 스폰 경로마다 달라 '늦게 구독해도 받는' 형태다
	 */
	void OnCombatReady_RegisterAndCall(FSimpleMulticastDelegate::FDelegate Delegate);

	/** 준비 전에 빙의가 풀린 쪽의 구독 해제. 끝난 뒤 불러도 된다 */
	void OnCombatReady_Unregister(const UObject* Listener);

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

	//~ AAstralCharacter
	/** 사망 완료 — 제거를 UAstralEnemySpawnSubsystem::ReleaseEnemy 에 넘긴다 (DestroyAfterDeathDelay 초 뒤, 0 이하면 바로). 안쪽은 LifeSpan 그대로다 — 풀링이 들어갈 자리 */
	virtual void HandleDeathFinished(AActor* OwningActor) override;
	//~ End AAstralCharacter

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Components")
	TObjectPtr<UAstralAbilitySystemComponent> AbilitySystemComponent;

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

	/** 팀 ID (플레이어 = 0, 적 = 1). 런타임 변경(SetGenericTeamId)이 클라에도 반영되도록 복제 */
	UPROPERTY(EditAnywhere, Replicated, Category = "Astral|Team")
	uint8 TeamId = 1;

	/** 예고 공격 루프 활성 여부 — GA_Enemy_TelegraphAttack이 매 사이클 확인. 패시브/예고 더미를 레벨에서 구분 배치 (서버 판정 전용) */
	UPROPERTY(EditAnywhere, Category = "Astral|Combat")
	bool bTelegraphAttackEnabled = false;

	/** FinishDeath 후 액터 제거까지의 시간 (초) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Death", Meta = (ClampMin = "0.0"))
	float DestroyAfterDeathDelay = 2.0f;

private:
	FSimpleMulticastDelegate OnCombatReady;

	bool bCombatReady = false;
};
