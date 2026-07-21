#pragma once

#include "CoreMinimal.h"
#include "GenericTeamAgentInterface.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "AstralCombatStatics.generated.h"

/**
 * 전투 판정 공용 헬퍼.
 * 팀 해석은 IGenericTeamAgentInterface 기반 — 액터 본인 → 컨트롤러 → PlayerState 순으로 거슬러 올라간다.
 * 팀 정보를 못 찾으면 NoTeam → 기본값은 "때릴 수 없음" (CanDamage에서 직접 차단 — 엔진 기본 solver는 NoTeam도 Hostile로 보므로).
 */
UCLASS()
class ASTRALBREAK_API UAstralCombatStatics : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** Source가 Target에게 데미지를 넣을 수 있는가 — Hostile 관계이고 Target이 사망 상태가 아닐 때만 true */
	UFUNCTION(BlueprintPure, Category = "Astral|Combat")
	static bool CanDamage(const AActor* SourceActor, const AActor* TargetActor);

	/** 액터의 팀 해석 (본인 → 컨트롤러 → PlayerState). 실패 시 FGenericTeamId::NoTeam */
	static FGenericTeamId GetTeamId(const AActor* Actor);

	/** 디버그 표시용 — NoTeam은 255 */
	UFUNCTION(BlueprintPure, Category = "Astral|Combat")
	static int32 GetTeamIdAsInt(const AActor* Actor);

	/** State.Death(Dying/Dead 포함) 태그 보유 여부 */
	UFUNCTION(BlueprintPure, Category = "Astral|Combat")
	static bool IsDeadOrDying(const AActor* Actor);
};
