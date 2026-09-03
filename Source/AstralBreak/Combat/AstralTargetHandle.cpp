#include "AstralTargetHandle.h"

#include "GameFramework/Actor.h"

FVector FAstralTargetHandle::GetAimLocation() const
{
	const AActor* Actor = TargetActor.Get();
	return Actor ? Actor->GetActorLocation() : FVector::ZeroVector;
}
