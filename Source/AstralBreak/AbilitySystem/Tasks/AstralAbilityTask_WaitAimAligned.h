#pragma once

#include "CoreMinimal.h"
#include "Abilities/Tasks/AbilityTask.h"
#include "AstralAbilityTask_WaitAimAligned.generated.h"

class APawn;
class UGameplayAbility;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FAstralAimAlignedDelegate, bool, bTimedOut);

/**
 * 몸(액터) Yaw 가 컨트롤러 Yaw 의 허용각 안에 들 때까지 기다린다 — 원거리 즉발 사격이 몸이 조준 방향으로 돈 뒤에 나가도록.
 * 회전 자체는 이동 컴포넌트의 조준 회전 모드(컨트롤러 Desired 회전 + AimingRotationRate)가 하고 여기는 보기만 한다.
 * 서버·소유 클라가 각자 자기 액터·컨트롤러로 판정한다(원격 폰의 서버 컨트롤 회전은 이동 패킷이 갱신). MaxWait 이 지나면 정렬 전이라도 끝낸다
 */
UCLASS()
class ASTRALBREAK_API UAstralAbilityTask_WaitAimAligned : public UAbilityTask
{
	GENERATED_BODY()

public:
	UAstralAbilityTask_WaitAimAligned(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	static UAstralAbilityTask_WaitAimAligned* WaitAimAligned(UGameplayAbility* OwningAbility, float InToleranceYaw, float InMaxWaitSeconds);

	/** |컨트롤러 Yaw − 액터 Yaw| ≤ 허용각. 컨트롤러가 없으면 기다릴 기준이 없으므로 정렬로 본다 */
	static bool IsAimAligned(const APawn* Pawn, float ToleranceYaw);

	/** 정렬(bTimedOut=false) 또는 시간 초과(true) — 1회 */
	UPROPERTY(BlueprintAssignable)
	FAstralAimAlignedDelegate OnFinished;

	//~UAbilityTask
	virtual void TickTask(float DeltaTime) override;
	//~End UAbilityTask

private:
	void Finish(bool bTimedOut);

	float ToleranceYaw = 10.f;
	float MaxWaitSeconds = 0.3f;
	float Elapsed = 0.f;
};
