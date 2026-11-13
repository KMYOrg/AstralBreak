#pragma once

#include "CoreMinimal.h"
#include "StateTreeTaskBase.h"
#include "AstralStateTreeTask_EngageSlot.generated.h"

class AAstralEnemyController;

USTRUCT()
struct FAstralStateTreeTask_EngageSlotInstanceData
{
	GENERATED_BODY()

	/** 타깃과 자리를 쥔 컨트롤러 — 스키마의 AIControllerClass 가 AAstralEnemyController 여야 자동으로 묶인다 */
	UPROPERTY(EditAnywhere, Category = Context)
	TObjectPtr<AAstralEnemyController> AIController = nullptr;

	/** 고리 반경 (cm) — 타깃 중심에서 자리까지 */
	UPROPERTY(EditAnywhere, Category = Parameter, meta = (ClampMin = "0.0", ForceUnits = "cm"))
	float RingRadius = 122.f;

	/** 자리 사이 최소 각 (도) — 같은 타깃을 쥔 적끼리 이만큼은 떨어져 선다. 이웃과의 거리 = 2 × 반경 × sin(각 ÷ 2) */
	UPROPERTY(EditAnywhere, Category = Parameter, meta = (ClampMin = "0.0", ClampMax = "180.0", ForceUnits = "deg"))
	float MinSeparationDegrees = 60.f;

	/**
	 * 내 방위가 자리에서 이만큼 넘게 벌어져 있으면(타깃이 나를 지나쳐 자리가 반대편이 됐다) 지금 내 쪽에서 자리를 다시 고른다.
	 * 이 안이면 쥐고 있던 자리를 그대로 쓴다 — 공격 사이클마다 자리가 조금씩 밀려 대형이 도는 일이 없다. 0 이하면 한 번 잡은 자리를 타깃이 바뀔 때까지 쓴다
	 */
	UPROPERTY(EditAnywhere, Category = Parameter, meta = (ClampMax = "180.0", ForceUnits = "deg"))
	float RepickAngleDegrees = 90.f;

	/**
	 * 돌아가기 — 자리가 내 방위에서 이 각보다 멀면 곧장 가지 않고(앞줄에 선 적들에게 막힌다), 고리 바깥(DetourRadius)을 따라 이 각만큼씩 앞선 경유점으로 간다.
	 * 이 각 안에 들면 자리로 곧장 들어간다. 0 이하면 돌아가지 않는다
	 */
	UPROPERTY(EditAnywhere, Category = Parameter, meta = (ClampMax = "90.0", ForceUnits = "deg"))
	float DetourAngleDegrees = 30.f;

	/** 돌아갈 때의 반경 (cm) — 서 있는 적의 바깥 가장자리(고리 반경 + 캡슐 반경)에 내 캡슐 반경과 여유를 더한 것보다 커야 한다 */
	UPROPERTY(EditAnywhere, Category = Parameter, meta = (ClampMin = "0.0", ForceUnits = "cm"))
	float DetourRadius = 265.f;

	/** 지금 갈 곳의 월드 좌표(자리 또는 경유점) — 같은 상태의 MoveTo.Destination 이 여기에 묶인다. 타깃을 따라 매 틱 갱신된다 */
	UPROPERTY(EditAnywhere, Category = Output)
	FVector Location = FVector::ZeroVector;
};

/**
 * 공격 자리를 잡고 그 좌표를 낸다 (Docs/Design/m3-enemy-ai.md §13 T1 · T2).
 * 같은 타깃에 붙는 적들이 한 점(타깃 중심)으로 몰리지 않게, 타깃 둘레 고리 위에 저마다 자리를 하나씩 잡는다.
 *
 * 들어올 때: 자리가 없거나 반대편이 됐으면 AAstralEnemyController::SelectEngageSlot 으로 고르고 좌표를 낸다. 타깃이 없으면 실패.
 * 틱:       좌표 = 타깃 위치 + 자리 방위 × 반경 — 타깃이 움직이면 좌표도 따라간다(위치는 연속 값이라 알릴 이벤트가 없다. 엔진의 액터 추적도 안에서 같은 일을 한다).
 *           타깃이 나를 지나쳐 자리가 반대편이 되면 다시 고른다. 자리가 멀면 고리 바깥을 도는 경유점을 낸다(앞줄을 뚫고 가지 않게).
 * 스스로 끝나지 않는다(Running) — 같은 상태의 MoveTo 가 상태를 끝낸다. 타깃을 잃은 뒤에는 마지막 좌표를 그대로 둔다(상태를 떠나는 것은 TargetLost 전환의 몫).
 */
USTRUCT(meta = (DisplayName = "Astral Engage Slot", Category = "Astral|AI"))
struct ASTRALBREAK_API FAstralStateTreeTask_EngageSlot : public FStateTreeTaskCommonBase
{
	GENERATED_BODY()

	using FInstanceDataType = FAstralStateTreeTask_EngageSlotInstanceData;

	FAstralStateTreeTask_EngageSlot();

	virtual const UStruct* GetInstanceDataType() const override { return FInstanceDataType::StaticStruct(); }
	virtual EStateTreeRunStatus EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const override;
	virtual EStateTreeRunStatus Tick(FStateTreeExecutionContext& Context, const float DeltaTime) const override;

private:
	/** 자리를 (필요하면) 고르고 지금 갈 곳을 InstanceData.Location 에 쓴다. 타깃이 없으면 false — Location 은 그대로 */
	static bool UpdateLocation(FInstanceDataType& InstanceData);
};
