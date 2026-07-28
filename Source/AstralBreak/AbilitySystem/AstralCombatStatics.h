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

	/**
	 * 전방 스피어 스윕 → CanDamage 필터 → 데미지 GE(SetByCaller.Damage, GameData에서 해석) 적용. 적중한 타겟 수 반환.
	 * 서버 전용 (데미지 execute는 서버 권위) — Hero 근접 콤보 / 더미 텔레그래프 / M3 몬스터 공격이 공유.
	 */
	static int32 ApplyDamageSweep(class UAbilitySystemComponent* SourceASC, AActor* Avatar, float BaseDamage, float TraceStartOffset, float TraceDistance, float TraceRadius, float EffectLevel = 1.0f);

	/**
	 * 받는 데미지의 방어 판정 (서버 전용 — HealthSet::PreGameplayEffectExecute의 Damage 분기에서 1줄 호출).
	 * 정면(120° 콘) 패링 → false 반환(완전 무효) + Parried(방어자)/Staggered(공격자) 이벤트.
	 * 정면 가드 → Magnitude × GuardDamageMultiplier 감쇄 + Guarded(방어자, magnitude=막은 양) 이벤트.
	 * Damage.Type.Unblockable asset tag GE는 그대로 통과 (ex: 강공격).
	 */
	static bool ResolveIncomingDamage(struct FGameplayEffectModCallbackData& Data);
};
