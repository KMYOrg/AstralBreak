#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "AstralEnemyAnimInstance.generated.h"

class UAstralHealthComponent;

/**
 * 적 전용 AnimInstance — 그래프가 읽는 값 두 개만 낸다 (Docs/Design/m3-enemy-ai.md §10 C1 ③).
 *   GroundSpeed  지면 속도(XY) — 대기 · 걷기 · 달리기 블렌드 스페이스의 축
 *   bDead        사망 여부 — UAstralHealthComponent 의 복제되는 DeathState. 모든 머신이 같은 값을 본다
 *
 * 히어로의 UAstralAnimInstance(조준 · 제자리 회전 · 무기 파지)를 상속하지 않는다.
 * 사망은 이벤트(OnDeathStarted / OnDeathReset) 구독 대신 매 갱신 때 원천을 읽는다 — 속도 때문에 어차피 매 프레임 도는 함수이고,
 * 원천 하나를 그대로 읽으면 구독 시점(클라이언트의 초기 복제 · 부활)에 따라 값이 어긋날 자리가 없다.
 */
UCLASS()
class ASTRALBREAK_API UAstralEnemyAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	float GetGroundSpeed() const { return GroundSpeed; }
	bool IsDead() const { return bDead; }

protected:
	//~ UAnimInstance
	virtual void NativeInitializeAnimation() override;
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;
	//~ End UAnimInstance

protected:
	/** 지면 속도 (cm/s, XY) */
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Enemy")
	float GroundSpeed = 0.f;

	/** 죽었거나 죽는 중 */
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Enemy")
	bool bDead = false;

private:
	TWeakObjectPtr<const UAstralHealthComponent> HealthComponent;
};
