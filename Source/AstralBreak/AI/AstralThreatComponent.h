#pragma once

#include "CoreMinimal.h"
#include "AI/AstralEnemyTargeting.h"
#include "Components/ActorComponent.h"
#include "AstralThreatComponent.generated.h"

class APawn;

/** 추첨에 넘기는 후보 1명 — 컨트롤러가 수집한다 (PlayerArray · 사망 판정 · 적대심 Attribute) */
struct FAstralThreatCandidateInfo
{
	APawn* Pawn = nullptr;
	FVector Location = FVector::ZeroVector;
	bool bDeadOrDying = false;
	float Hostility = AstralEnemyTargeting::DefaultHostility;
};

/**
 * 적 한 마리의 위협 기록과 타깃 선정 규칙 (Docs/Design/m3-enemy-ai.md §9) — AAstralEnemyController 의 기본 서브오브젝트, 서버 전용.
 *
 * 고르는 방식은 적대심 가중 추첨이다. 가중치 = 적대심 × (1 + DamageWeight × 최근 피해 점유율).
 * 아무도 안 때렸으면 가장 가까운 후보, 현재 타깃을 잡은 지 HoldTime 안이면 유지, 현재 타깃이 아닌 후보에게 맞으면 유지 시간과 무관하게 다시 뽑는다.
 * 타이머 · 틱이 없다 — 기록은 피해 통지로 쌓이고, 유지 · 제외 · 창 만료는 읽을 때 시각을 비교한다. 산술은 AstralEnemyTargeting 의 순수 함수다.
 * 값은 전부 잠정이고 이 컴포넌트의 프로퍼티다 — 컨트롤러 BP(BP_EnemyController_Melee)에서 고친다.
 */
UCLASS()
class ASTRALBREAK_API UAstralThreatComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UAstralThreatComponent(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	/**
	 * 가해 폰의 피해를 기록한다.
	 * 가해자가 현재 타깃이 아니면 '다시 뽑기' 를 표시한다(RetargetCooldown 에 한 번). 표시가 섰으면 true — 부른 쪽이 트리에 AI.Event.Retarget 을 보낸다
	 */
	bool RecordDamage(const APawn* Attacker, float Damage, const AActor* CurrentTarget);

	/** 후보 중 한 명을 고른다 — Candidates 의 인덱스, 없으면 INDEX_NONE. '다시 뽑기' 표시는 이 호출이 소비한다 */
	int32 SelectTarget(const FVector& Origin, TConstArrayView<FAstralThreatCandidateInfo> Candidates, const AActor* CurrentTarget);

	/** 이 타깃을 ExcludeTime 동안 후보에서 뺀다 (닿을 수 없는 타깃) */
	void ExcludeTarget(const AActor* Target);

	/** 기록 · 제외 · 표시를 전부 비운다 — 언포제션 · 사망 */
	void Reset();

	/** 창 안에서 이 가해자가 넣은 피해 합 */
	float GetRecentDamage(const AActor* Attacker) const;

	bool IsExcluded(const AActor* Target) const;
	bool IsRetargetPending() const { return bRetargetPending; }

#if !UE_BUILD_SHIPPING
	/** 자동 시험용 — 추첨 값을 고정한다(0 ~ 1). 음수면 해제. Shipping 에는 없다 */
	void SetRollOverrideForTest(float InRoll) { RollOverrideForTest = InRoll; }
#endif

public:
	/** 피해 가중 — 최근 피해를 혼자 넣은 후보의 가중치가 (1 + 이 값)배가 된다. 0 이면 피해와 무관한 적대심 추첨 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Astral|Threat", meta = (ClampMin = "0.0"))
	float DamageWeight = 2.f;

	/** '최근' 의 길이 — 이보다 오래된 피해는 세지 않는다 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Astral|Threat", meta = (ClampMin = "0.0", Units = "s"))
	float DamageWindow = 10.f;

	/** 타깃을 잡은 뒤 다시 뽑지 않는 시간 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Astral|Threat", meta = (ClampMin = "0.0", Units = "s"))
	float HoldTime = 6.f;

	/** 다른 사람에게 맞아 다시 뽑는 것을 이 시간에 한 번만 받는다 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Astral|Threat", meta = (ClampMin = "0.0", Units = "s"))
	float RetargetCooldown = 3.f;

	/** 닿을 수 없는 타깃을 후보에서 빼 두는 시간 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Astral|Threat", meta = (ClampMin = "0.0", Units = "s"))
	float ExcludeTime = 5.f;

private:
	double GetNow() const;

	/** 추첨 값(0 ~ 1)을 뽑는 곳은 여기 하나다 */
	float DrawRoll() const;

	/** 창 밖 기록 · 만료된 제외 · 사라진 액터를 버린다 */
	void PruneExpired(double Now);

	/** 가해 폰별 피해 기록 */
	TMap<TWeakObjectPtr<const AActor>, TArray<FAstralEnemyDamageEntry>> DamageLog;

	/** 제외한 타깃 → 제외한 시각 */
	TMap<TWeakObjectPtr<const AActor>, double> ExcludedAt;

	/** 현재 타깃을 뽑은 시각. 음수 = 없음 */
	double TargetAcquiredTime = -1.0;

	/** 마지막으로 받아들인 '다시 뽑기' 요청의 시각. 음수 = 없음 */
	double LastRetargetRequestTime = -1.0;

	bool bRetargetPending = false;

#if !UE_BUILD_SHIPPING
	float RollOverrideForTest = -1.f;
#endif
};
