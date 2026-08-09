#pragma once

#include "CoreMinimal.h"
#include "UObject/PrimaryAssetId.h"
#include "AstralPlayerLoadout.generated.h"

/**
 * 로비 선택 페이로드 — 원본은 클라이언트(LocalPlayer 캐시), 서버는 세션 캐시(PartySubsystem).
 * 토폴로지 무관: 같은 프로세스 travel이든 별도 인스턴스 서버든 "클라 보관 + 명시적 전송"으로 도착한다.
 * 필드 추가가 쉬운 형태 유지 — M7의 룬 액티브 4칸·성장 트리가 여기 얹힌다.
 */
USTRUCT(BlueprintType)
struct FAstralPlayerLoadout
{
	GENERATED_BODY()

	/** 선택 캐릭터 — 외형(즉시) + 도착지 전투 구성(멀티 히어로 시) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Meta = (AllowedTypes = "AstralCharacterDefinition"))
	FPrimaryAssetId CharacterId;

	/** 무기 등 장비 ID — EquipItemById가 그대로 소비 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Meta = (AllowedTypes = "AstralWeaponDefinition,AstralRangedWeaponDefinition"))
	TArray<FPrimaryAssetId> Equipment;

	/** 진/룬 — M7 자리만 확보 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	TArray<FPrimaryAssetId> Runes;

	bool IsSet() const { return CharacterId.IsValid() || Equipment.Num() > 0; }
};

/** 방장이 고른 목적지 (퀘스트/레이드) — 세션 단위, GameState 복제 */
USTRUCT(BlueprintType)
struct FAstralRaidRequest
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite)
	FString MapName;

	bool IsSet() const { return !MapName.IsEmpty(); }
};
