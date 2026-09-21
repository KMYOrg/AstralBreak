#pragma once

#include "CoreMinimal.h"
#include "Abilities/GameplayAbilityTargetTypes.h"
#include "AstralFacingTypes.generated.h"

/**
 * 락온 — 공격 방향(Facing) 전달·수신·검증 타입.
 * 월드 의존이 없는 것(양자화 · 수신 분류 · 검증 경계)은 전부 여기 순수 함수/값 타입으로 두어 Automation 테스트로 덮는다.
 */

/** 방향 소스 — None은 "명시적 무보정"(매 단계 보낸다). MoveInput은 7단계 */
UENUM()
enum class EAstralFacingSource : uint8
{
	None,
	LockOn,
};

/** 단계 시작 확정 결과 — 그 단계에서 다시 바뀌지 않는다 */
UENUM()
enum class EAstralFacingDecision : uint8
{
	Warp,
	NoWarp_ExplicitNone,
	NoWarp_Missing,
	NoWarp_Rejected,
};

/** 서버 월드 검증 거부 사유 */
UENUM()
enum class EAstralFacingRejectReason : uint8
{
	None,
	InvalidTarget,
	SelfTarget,
	CannotDamage,
	OutOfRange,
	BearingMismatch,
};

/** 수신 분류 — 보관함(FAstralFacingStageInbox)이 돌려준다. 로그가 원인을 가리키게 하기 위한 값 */
UENUM()
enum class EAstralFacingReceiveResult : uint8
{
	StoredCurrent,
	StoredNext,
	DuplicateIgnored,
	ConflictIgnored,
	DiscardedPast,
	DiscardedResolved,
	DiscardedTooFar,
	DiscardedOutOfRange,
};

namespace AstralFacing
{
	/** 락온 유지 반경(2000) + 네트워크 여유 */
	constexpr float ValidateRange = 2200.f;
	/** 제출 Yaw ↔ 서버 방위 최단각 허용 오차 (도) */
	constexpr float MaxTargetBearingError = 60.f;
	/** 이 거리 미만이면 각도 검사를 건너뛴다 — 캡슐 접촉 거리에서 방위가 불안정하다 */
	constexpr float BearingCheckMinDistance = 100.f;

	/** Yaw(도) → uint16. 정규화 후 [-180, 180) 를 65536 단계로. 해상도 ≈ 0.0055° */
	ASTRALBREAK_API uint16 QuantizeYaw(float YawDegrees);
	/** uint16 → Yaw(도, (-180, 180]) — 로컬 예측도 이 값을 쓴다 (양쪽이 같은 값을 쓰게 하는 유일한 방법) */
	ASTRALBREAK_API float DequantizeYaw(uint16 Quantized);

	/**
	 * 거리·방위 검증 (순수). TargetActor 유효성·CanDamage는 호출자가 먼저 본다.
	 * @param ServerBearingYaw 서버 시점 아바타 → 타겟 방위 — 검증에만 쓰고 재계산에는 쓰지 않는다 (§8)
	 */
	ASTRALBREAK_API EAstralFacingRejectReason ValidateBearing(float Distance2D, float ServerBearingYaw, float SubmittedYaw);

	ASTRALBREAK_API const TCHAR* ToString(EAstralFacingSource Value);
	ASTRALBREAK_API const TCHAR* ToString(EAstralFacingDecision Value);
	ASTRALBREAK_API const TCHAR* ToString(EAstralFacingRejectReason Value);
	ASTRALBREAK_API const TCHAR* ToString(EAstralFacingReceiveResult Value);
}

/** 한 단계의 방향서 — 클라가 캡처해 보내고 서버가 검증한다. None은 빈 Actor · NAME_None · Yaw 0으로 정규화 */
USTRUCT()
struct ASTRALBREAK_API FAstralFacingProposal
{
	GENERATED_BODY()

	UPROPERTY()
	EAstralFacingSource Source = EAstralFacingSource::None;

	UPROPERTY()
	TWeakObjectPtr<AActor> TargetActor;

	UPROPERTY()
	FName TargetPointId = NAME_None;

	UPROPERTY()
	uint16 QuantizedDesiredYaw = 0;

	/** 활성화 내 ComboIndex */
	UPROPERTY()
	uint8 StageIndex = 0;

	bool IsNone() const { return Source == EAstralFacingSource::None; }

	/** None 정규화 — Source가 None이면 나머지 필드를 비운다 */
	void NormalizeNone();

	static FAstralFacingProposal MakeNone(uint8 InStageIndex);

	bool operator==(const FAstralFacingProposal& Other) const;
	bool operator!=(const FAstralFacingProposal& Other) const { return !(*this == Other); }
	
	void NetSerializeFields(FArchive& Ar, class UPackageMap* Map);
};

/**
 * GAS TargetData 페이로드 — Stage 0은 활성화 이벤트(TriggerEventData.TargetData)에, Stage 1~N은 ServerSetReplicatedTargetData에 실린다.
 * Actor는 UPackageMap 경로로 직렬화 (메모리 주소를 보내지 않는다)
 */
USTRUCT()
struct ASTRALBREAK_API FGameplayAbilityTargetData_AstralFacing : public FGameplayAbilityTargetData
{
	GENERATED_BODY()

	UPROPERTY()
	FAstralFacingProposal Proposal;

	FGameplayAbilityTargetData_AstralFacing() = default;
	explicit FGameplayAbilityTargetData_AstralFacing(const FAstralFacingProposal& InProposal) : Proposal(InProposal) {}

	virtual UScriptStruct* GetScriptStruct() const override { return FGameplayAbilityTargetData_AstralFacing::StaticStruct(); }
	virtual TArray<TWeakObjectPtr<AActor>> GetActors() const override;
	virtual FString ToString() const override;

	bool NetSerialize(FArchive& Ar, class UPackageMap* Map, bool& bOutSuccess);

	/**
	 * 구조 검증 + 추출 — 페이로드 정확히 1개 · 예상 ScriptStruct · Source 범위 · StageIndex < NumStages · TargetPointId == NAME_None · None 정규화.
	 * 실패 시 false (호출자는 Rejected/Missing으로 기록)
	 */
	static bool ExtractProposal(const FGameplayAbilityTargetDataHandle& Handle, int32 NumStages, FAstralFacingProposal& OutProposal);

	static FGameplayAbilityTargetDataHandle MakeHandle(const FAstralFacingProposal& Proposal);
};

template<>
struct TStructOpsTypeTraits<FGameplayAbilityTargetData_AstralFacing> : public TStructOpsTypeTraitsBase2<FGameplayAbilityTargetData_AstralFacing>
{
	enum
	{
		WithNetSerializer = true,
		WithCopy = true,
	};
};

/**
 * 서버 보관함 — ServerSetReplicatedTargetData는 활성화 키별 캐시를 교체하므로 프로젝트가 순서를 관리한다.
 * "현재 단계 확정 결과 + 다음 한 단계 pending"으로 제한 — 2단계 이상 벌어지면 버퍼 확장으로 감추지 않고 불일치로 기록한다
 * 월드 의존 없음 — Automation 테스트 대상
 */
struct ASTRALBREAK_API FAstralFacingStageInbox
{
	/** 활성화 시작 — 단계 수를 고정하고 0단계 미확정 상태로 */
	void Reset(int32 InNumStages);

	/** 수신 분류 (stage-5 표). 동일 단계 상충 데이터는 첫 수용값 유지 */
	EAstralFacingReceiveResult Receive(const FAstralFacingProposal& Proposal);

	/**
	 * 단계 시작 — 이전 단계의 pending을 현재로 승격. 순차(N == Current+1)가 아니면 슬롯을 비우고 false (불일치 기록용).
	 * 첫 단계(0)는 Reset 직후 그대로 통과
	 */
	bool BeginStage(int32 StageIndex);

	/** 현재 단계 제안을 꺼내고 확정 표시 — 이후 같은 단계 수신은 DiscardedResolved */
	TOptional<FAstralFacingProposal> TakeCurrent();

	int32 GetCurrentStage() const { return CurrentStage; }
	int32 GetNumStages() const { return NumStages; }
	bool IsCurrentResolved() const { return bCurrentResolved; }
	bool HasPendingNext() const { return Next.IsSet(); }

private:
	int32 NumStages = 0;
	int32 CurrentStage = 0;
	bool bCurrentResolved = false;
	TOptional<FAstralFacingProposal> Current;
	TOptional<FAstralFacingProposal> Next;
};
