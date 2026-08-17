#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
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
	 * 무기 트레이스 적중 1건에 데미지 적용 (서버 전용) — CanDamage 필터 + SetByCaller.Damage(GameData) 주입.
	 * EffectCauser = WeaponActor (Instigator는 Avatar 유지 — 방어 정면 판정은 OriginalInstigator라 영향 없음).
	 * 적용 성공 여부 반환.
	 */
	static bool ApplyWeaponDamage(class UAbilitySystemComponent* SourceASC, AActor* Avatar, AActor* WeaponActor, const FHitResult& HitResult, float BaseDamage, float EffectLevel = 1.0f);

	/**
	 * SetByCaller GE를 대상 ASC 자신에게 적용 (서버 전용, Amount≈0이면 무시) — GA 문맥이 없는 호출자용
	 * (투사체 명중 수급 등 — GA는 발사 후 종료됐을 수 있다). GA 내부에서는 예측 문맥이 실리는
	 * GA_Hero_Base::ApplySetByCallerEffect를 쓸 것
	 */
	static void ApplySetByCallerEffectToSelf(class UAbilitySystemComponent* ASC, TSubclassOf<class UGameplayEffect> EffectClass, const struct FGameplayTag& SetByCallerTag, float Amount, float EffectLevel = 1.0f);

	/** 표식 수급 (GameData MarkGain GE) — 투사체 명중 등 GA 밖의 수급 지점용 (서버 전용) */
	static void ApplyMarkGainToSelf(class UAbilitySystemComponent* ASC, float Amount);

	/** 오의 수급 (GameData UltGain GE) — 투사체 명중 등 GA 밖의 수급 지점용 (서버 전용) */
	static void ApplyUltGainToSelf(class UAbilitySystemComponent* ASC, float Amount);

	/**
	 * 서버 — 원하는 전투 스타일을 장비 조건으로 해석해 적용
	 * 빈 태그면 no-op — 스타일 시스템 미사용 폰에서 경고 x
	 */
	static void ApplyCombatStyle(AActor* Avatar, FGameplayTag DesiredStyle);

	/**
	 * 받는 데미지의 방어 판정 (서버 전용 — HealthSet::PreGameplayEffectExecute의 Damage 분기에서 1줄 호출).
	 * 정면(120° 콘) 패링 → false 반환(완전 무효) + Parried(방어자)/Staggered(공격자) 이벤트.
	 * 정면 가드 → Magnitude × GuardDamageMultiplier 감쇄 + Guarded(방어자, magnitude=막은 양) 이벤트.
	 * Damage.Type.Unblockable asset tag GE는 그대로 통과 (ex: 강공격).
	 */
	static bool ResolveIncomingDamage(struct FGameplayEffectModCallbackData& Data);
};
