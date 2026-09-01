#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "GameplayTagContainer.h"
#include "AstralGameData.generated.h"

class UGameplayEffect;

USTRUCT(BlueprintType)
struct FAstralSetByCallerEffect
{
	GENERATED_BODY()

	UPROPERTY(EditDefaultsOnly)
	TSoftClassPtr<UGameplayEffect> Effect;

	UPROPERTY(EditDefaultsOnly, Meta = (Categories = "SetByCaller"))
	FGameplayTag SetByCallerTag;
};

/**
 * 전역 게임 데이터 — 프로젝트에 정확히 하나만 존재해야 하는 공유 게임플레이 애셋 참조 모음 (Lyra GameData 미러).
 * DefaultGame.ini의 AstralGameDataPath가 가리키는 애셋을 AssetManager가 시작 시 로드한다.
 *
 * 수납 기준: 여러 시스템이 공유하는 "전역 단일 인스턴스" 참조만.
 * 어빌리티 고유 데이터(Cost GE, 몽타주, 튜닝 수치)는 각 GA/PawnData 소유 — 여기 두지 않는다.
 */
UCLASS(BlueprintType, Const, Meta = (DisplayName = "Astral Game Data", ShortTooltip = "Data asset containing global game data."))
class ASTRALBREAK_API UAstralGameData : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UAstralGameData();

	/** AssetManager가 로드해 둔 전역 인스턴스 */
	static const UAstralGameData& Get();

public:
	/** 데미지 파이프라인 GE (SetByCaller.Damage → AstralDamageExecution) — ApplyDamageSweep가 사용 */
	UPROPERTY(EditDefaultsOnly, Category = "Default Gameplay Effects", meta = (DisplayName = "Damage Gameplay Effect (SetByCaller)"))
	TSoftClassPtr<UGameplayEffect> DamageGameplayEffect_SetByCaller;

	/** 오의 수급 (SetByCaller.UltGain → UltGain meta) — 어빌리티 적중/패링 보상 + 피격 수급(PlayerState) 공유 */
	UPROPERTY(EditDefaultsOnly, Category = "SetByCaller Effects")
	FAstralSetByCallerEffect UltGain;

	/** 표식 수급 (SetByCaller.MarkGain → MarkGain meta) */
	UPROPERTY(EditDefaultsOnly, Category = "SetByCaller Effects")
	FAstralSetByCallerEffect MarkGain;

	/** 스태미나 가변 소모 (SetByCaller.StaminaDrain — 음수 주입은 ApplyStaminaDrain 헬퍼가) — 가드 피격 등 */
	UPROPERTY(EditDefaultsOnly, Category = "SetByCaller Effects")
	FAstralSetByCallerEffect StaminaDrain;


	/** 스태미나 회복 지연 GE (Has Duration — State.Stamina.RegenBlocked 부여, 딜레이 값은 GE의 Duration) */
	UPROPERTY(EditDefaultsOnly, Category = "Default Gameplay Effects|Regen")
	TSoftClassPtr<UGameplayEffect> StaminaRegenBlockEffect;
};
