#include "AstralEnemyAnimInstance.h"

#include "Character/Components/AstralHealthComponent.h"
#include "GameFramework/Pawn.h"

void UAstralEnemyAnimInstance::NativeInitializeAnimation()
{
	Super::NativeInitializeAnimation();

	// 에디터 미리보기에는 폰 · 체력 컴포넌트가 없다 — 그때는 기본값(속도 0 · 살아 있음)으로 돈다
	HealthComponent = UAstralHealthComponent::FindHealthComponent(TryGetPawnOwner());
}

void UAstralEnemyAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);

	const APawn* Pawn = TryGetPawnOwner();
	if (!Pawn)
	{
		return;
	}

	// 시뮬레이션 프록시도 복제된 이동 속도를 돌려준다
	GroundSpeed = Pawn->GetVelocity().Size2D();

	if (const UAstralHealthComponent* Health = HealthComponent.Get())
	{
		bDead = Health->IsDeadOrDying();
	}
}
