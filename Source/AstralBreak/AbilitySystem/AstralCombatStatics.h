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
	/**
	 * 두 액터가 Hostile 관계인가 — 팀만 본다 (생존 상태 무관).
	 * 이동 시뮬레이션(폰 충돌 정책)처럼 예측 경로에서 쓰는 판정 — 사망 태그는 서버 먼저·클라 나중이라
	 * CanDamage를 재사용하면 RTT/2 동안 서버·클라 정책이 갈린다. NoTeam은 Hostile이 아니다
	 */
	UFUNCTION(BlueprintPure, Category = "Astral|Combat")
	static bool AreHostile(const AActor* SourceActor, const AActor* TargetActor);

	/** Source가 Target에게 데미지를 넣을 수 있는가 — AreHostile ∧ Target이 사망 상태가 아님 (게임플레이 판정) */
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
	 * DamageTags(선택) — ApplyAttackHit 으로 그대로 넘긴다. 비어 있으면 기존 동작 그대로다
	 */
	static int32 ApplyDamageSweep(class UAbilitySystemComponent* SourceASC, AActor* Avatar, float BaseDamage, float TraceStartOffset, float TraceDistance, float TraceRadius, float EffectLevel = 1.0f, const FGameplayTagContainer& DamageTags = FGameplayTagContainer::EmptyContainer);

	/**
	 * 공격 적중 1건에 데미지 적용 (서버 전용) — CanDamage 필터 + SetByCaller.Damage(GameData) 주입.
	 * 소켓 연속 트레이스·전방 단발 스윕·투사체 충돌이 공유하는 공통 적중 파이프라인.
	 * EffectCauser = 실제 가해 액터(무기/투사체 등, 없으면 Avatar). Instigator는 Avatar 유지 —
	 * DamageTags(선택) — 이 적중의 데미지 스펙에 동적 asset tag 로 붙는다 (Damage.Type.Unguardable 등 — ResolveIncomingDamage 가 읽는다).
	 * 비어 있으면 스펙은 기존과 같다 — 히어로 · 더미 · 마네킹 경로는 넘기지 않는다
	 */
	static bool ApplyAttackHit(class UAbilitySystemComponent* SourceASC, AActor* InstigatorAvatar, AActor* EffectCauser, const FHitResult& HitResult, float Damage, float EffectLevel = 1.0f, const FGameplayTagContainer& DamageTags = FGameplayTagContainer::EmptyContainer);

	/** ApplyAttackHit의 마이그레이션 기간 wrapper. 신규 호출처는 ApplyAttackHit를 쓸 것 */
	static bool ApplyWeaponDamage(class UAbilitySystemComponent* SourceASC, AActor* Avatar, AActor* WeaponActor, const FHitResult& HitResult, float BaseDamage, float EffectLevel = 1.0f);

	/**
	 * SetByCaller GE를 대상 ASC 자신에게 적용 (서버 전용, Amount≈0이면 무시) — GA 컨텍스트가 없는 호출자용
	 * (투사체 명중 수급 등 — GA는 발사 후 종료됐을 수 있다). 스펙 컨텍스트는 빈 값.
	 * GA 내부에서는 GA 컨텍스트(어빌리티·SourceObject·레벨)이 스펙에 실리는
	 * UAstralGameplayAbility::ApplySetByCallerEffect를 쓸 것 — 예측은 양쪽 다 x(수급 GE는 서버 권위).
	 */
	static void ApplySetByCallerEffectToSelf(class UAbilitySystemComponent* ASC, const struct FAstralSetByCallerEffect& Effect, float Amount, float EffectLevel = 1.0f);

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
	 * State.Invulnerable(오의 중) → 맨 먼저 false 반환(완전 무효, 통지 없음). Unblockable 도 뚫지 못한다.
	 * 정면(120° 콘) 패링 → false 반환(완전 무효) + Parried(방어자)/Staggered(공격자) 이벤트.
	 * 정면 가드 → Magnitude × GuardDamageMultiplier 감쇄 + Guarded(방어자, magnitude=막은 양) 이벤트.
	 * Damage.Type.Unblockable asset tag GE는 그대로 통과 (패링 · 가드 둘 다 뚫는다).
	 * Damage.Type.Unguardable 은 가드만 뚫는다 — 패링 판정은 그대로 하고, 가드는 감쇄 · Guarded 이벤트 없이 전액 통과 (ex: 수호병 강공격).
	 */
	static bool ResolveIncomingDamage(struct FGameplayEffectModCallbackData& Data);
};
