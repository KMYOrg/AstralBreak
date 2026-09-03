#pragma once

#include "CoreMinimal.h"
#include "AstralTargetHandle.generated.h"

class AActor;

/**
 * 타겟 핸들 — 타게팅 상태가 가리키는 대상.
 * 네트워크로 보낼 때는 컴포넌트 포인터가 아니라
 * TargetActor + TargetPointId를 보내고 수신 측이 다시 해석한다.
 */
USTRUCT(BlueprintType)
struct FAstralTargetHandle
{
	GENERATED_BODY()

	/** 약한 참조 — 타게팅은 액터 소유권을 갖지 않는다 */
	UPROPERTY()
	TWeakObjectPtr<AActor> TargetActor;

	/** 부위 ID — MVP는 항상 NAME_None(캡슐 중심). M5 보스 약점 부위의 진입점 (필드만 두고 쓰지 않는다) */
	UPROPERTY()
	FName TargetPointId = NAME_None;

	bool IsSet() const { return TargetActor.IsValid(); }

	/** 조준점 — MVP: 액터 위치(캐릭터는 캡슐 중심). 부위 시스템 도입 시 TargetPointId 해석이 여기 붙는다 */
	FVector GetAimLocation() const;

	void Reset()
	{
		TargetActor = nullptr;
		TargetPointId = NAME_None;
	}
};
