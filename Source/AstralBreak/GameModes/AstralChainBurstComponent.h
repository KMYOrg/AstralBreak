#pragma once

#include "CoreMinimal.h"
#include "ActiveGameplayEffectHandle.h"
#include "Components/GameStateComponent.h"
#include "Templates/SubclassOf.h"
#include "AstralChainTracker.h"
#include "AstralChainBurstComponent.generated.h"

class APlayerState;
class UAbilitySystemComponent;
class UGameplayEffect;

/**
 * 복제되는 체인 상태 — 이것 하나가 전부다. 버스트 통지도 멀티캐스트가 아니라 LastBurst* 의 변화로 간다
 * (늦게 받거나 한 번 놓쳐도 최신 값이 온다 — 설계 Docs/Design/m4-ult-chain.md §3).
 */
USTRUCT(BlueprintType)
struct FAstralChainState
{
	GENERATED_BODY()

	/** 체인 번호 — 열릴 때마다 1 씩 커진다. 0 = 이 맵에서 아직 열린 적 없음 */
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Chain")
	int32 ChainId = 0;

	UPROPERTY(BlueprintReadOnly, Category = "Astral|Chain")
	EAstralChainPhase Phase = EAstralChainPhase::None;

	/** 참가자의 APlayerState::PlayerId — 등록 순서대로(= 맞힌 오의가 끝난 순서) */
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Chain")
	TArray<int32> ParticipantIds;

	/** 마감 — 서버 월드 시간(AGameStateBase::GetServerWorldTimeSeconds). 유예는 들어 있지 않다. Open 이고 멈춰 있지 않을 때만 뜻이 있다 */
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Chain")
	double DeadlineServerTime = 0.0;

	/** 지금 오의를 쓰는 사람의 PlayerId — 0 = 없음. 체인이 없을 때도 선다(그동안 나머지는 오의를 못 쓴다) */
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Chain")
	int32 CastingPlayerId = 0;

	/** 열린 체인의 타이머가 멈춰 있는가 — 누가 오의를 쓰는 동안. 그 오의가 못 맞히면 PausedRemainingSeconds 로 다시 돈다 */
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Chain")
	bool bTimerPaused = false;

	/** 멈출 때 남아 있던 시간(초) — bTimerPaused 일 때만 뜻이 있다 */
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Chain")
	float PausedRemainingSeconds = 0.f;

	/** 마지막으로 버스트가 나간 체인의 번호 — 이 값이 바뀌면 버스트가 한 번 나간 것이다 */
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Chain")
	int32 LastBurstChainId = 0;

	/** 그 버스트의 인원 */
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Chain")
	int32 LastBurstCount = 0;

	bool operator==(const FAstralChainState& Other) const
	{
		return ChainId == Other.ChainId && Phase == Other.Phase && ParticipantIds == Other.ParticipantIds
			&& DeadlineServerTime == Other.DeadlineServerTime && CastingPlayerId == Other.CastingPlayerId
			&& bTimerPaused == Other.bTimerPaused && PausedRemainingSeconds == Other.PausedRemainingSeconds
			&& LastBurstChainId == Other.LastBurstChainId && LastBurstCount == Other.LastBurstCount;
	}
	bool operator!=(const FAstralChainState& Other) const { return !(*this == Other); }
};

/** 마지막 버스트의 피해 내역 — 서버 전용(복제하지 않는다). 로그 · 자동 시험이 읽는다 */
struct FAstralChainBurstReport
{
	int32 ChainId = 0;

	/** 체인 인원 — 배수를 정한 값 */
	int32 Count = 0;

	/** 실제로 피해를 넣은 사람 수 (죽었거나 나간 참가자는 빠진다) */
	int32 NumContributors = 0;

	/** 피해가 들어간 적의 수 */
	int32 NumTargets = 0;

	/** 총 피해(배수 적용, 개인 배수 적용 전) — 적 하나가 받는 양의 기준 */
	float TotalDamage = 0.f;
};

/** (새 상태, 앞 상태) — 서버는 바꾼 직후, 클라이언트는 복제를 받은 직후 */
DECLARE_MULTICAST_DELEGATE_TwoParams(FAstralChainStateChanged, const FAstralChainState& /*NewState*/, const FAstralChainState& /*OldState*/);

/**
 * 체인 버스트 — 레이드 GameState 에 붙는 복제 컴포넌트 (설계 §3 · §3 끝 'B 다듬기').
 * 오의 어빌리티가 서버에서 두 번 알린다:
 *   NotifyUltStarted — 비용 확정 직후. 나머지 히어로에게 오의 차단을 걸고(한 번에 한 명), 열린 체인의 타이머를 멈춘다
 *   NotifyUltEnded   — 오의가 끝났을 때. 차단을 풀고, 맞혔으면 그 시각으로 체인에 등록 + 팀 게이지, 못 맞혔으면 타이머만 다시 돌린다
 * 판정은 FAstralChainTracker 가 하고, 여기는 타이머 · 복제 · 차단 · 팀 게이지 · 버스트 피해만 맡는다.
 * 이 컴포넌트가 없는 맵(허브 등)에서는 FindChainBurstComponent 가 null 이라 오의는 혼자 쓰는 것으로 끝난다(차단도 없다).
 * 값은 전부 잠정이고 레이드 GameState BP 에서 고친다.
 */
UCLASS()
class ASTRALBREAK_API UAstralChainBurstComponent : public UGameStateComponent
{
	GENERATED_BODY()

public:
	UAstralChainBurstComponent(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	/** 이 월드의 GameState 에 붙은 체인 컴포넌트. 없으면 null */
	static UAstralChainBurstComponent* FindChainBurstComponent(const UObject* WorldContextObject);

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	/**
	 * 서버 — 오의 시전이 시작됐다. 비용 확정이 성공한 직후에만 부를 것(예측 클라이언트는 부르지 않는다).
	 * UserASC 의 오너가 APlayerState 가 아니면 무시한다
	 */
	void NotifyUltStarted(UAbilitySystemComponent* UserASC);

	/**
	 * 서버 — 그 오의가 끝났다(끊긴 것 포함). bHit = 오의 판정에 적이 한 명이라도 걸렸는가.
	 * 맞혔으면 지금 시각으로 체인에 등록하고 본인을 뺀 살아 있는 히어로 전원에게 TeamUltGain 을 준다. 못 맞혔으면 아무 일도 없다(멈춘 타이머만 다시 돈다)
	 */
	void NotifyUltEnded(UAbilitySystemComponent* UserASC, bool bHit);

	const FAstralChainState& GetChainState() const { return ChainState; }

	/** 열린 체인의 남은 시간(초) — 도는 중이면 서버 시간에서 계산하고, 멈춰 있으면 멈출 때의 값. 열려 있지 않으면 0 */
	UFUNCTION(BlueprintPure, Category = "Astral|Chain")
	float GetRemainingSeconds() const;

	int32 GetMaxParticipants() const { return MaxParticipants; }

	/** PlayerId → PlayerState (복제된 PlayerArray 에서 찾는다 — 어디서든 부를 수 있다) */
	APlayerState* FindPlayerState(int32 PlayerId) const;

	/** 서버 전용 — 마지막 버스트의 피해 내역 */
	const FAstralChainBurstReport& GetLastBurstReport() const { return LastBurstReport; }

	/** 디버그 위젯용 한 줄 */
	FString GetDebugString() const;

	FAstralChainStateChanged OnChainStateChanged;

protected:
	UFUNCTION()
	void OnRep_ChainState(const FAstralChainState& OldState);

	// ─── 판정 값 (잠정) ───

	/** 마감 = 마지막으로 맞힌 오의가 끝난 시각 + 이 값(초). 연출 시간은 들어 있지 않다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Chain", meta = (ClampMin = "0.1"))
	float WindowSeconds = 6.0f;

	/** 서버가 마감 뒤에 더 받는 시간(초) — 지연으로 늦게 도착한 입력의 몫 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Chain", meta = (ClampMin = "0.0"))
	float GraceSeconds = 0.25f;

	/** 이 인원(또는 살아 있는 파티 전원)이 차면 바로 닫는다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Chain", meta = (ClampMin = "2"))
	int32 MaxParticipants = 4;

	/** 아군이 오의를 맞혔을 때 나머지 살아 있는 히어로가 받는 게이지 (UltGainMultiplier 가 곱해진다) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Chain", meta = (ClampMin = "0.0"))
	float TeamUltGain = 10.f;

	// ─── 시전 (잠정) ───

	/** 누가 오의를 쓰는 동안 나머지 히어로에게 거는 효과 — State.Ult.Blocked 를 준다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Chain|Cast")
	TSubclassOf<UGameplayEffect> UltBlockEffectClass;

	/**
	 * 시전 종료 통지를 기다리는 상한(초) — 쓰는 사람이 나가 통지가 오지 않을 때 차단을 풀고 타이머를 다시 돌린다.
	 * 가장 긴 오의 연출보다 길어야 한다
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Chain|Cast", meta = (ClampMin = "0.1"))
	float CastTimeout = 10.f;

	// ─── 버스트 피해 (잠정) ───

	/** 총 피해의 기준 — 여기에 인원 배수를 곱한 뒤 참가자 수로 나눠 각자의 이름으로 넣는다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Chain|Burst", meta = (ClampMin = "0.0"))
	float BurstBaseDamage = 300.f;

	/** 인원 배수 — [0] = 2명, [1] = 3명, [2] = 4명. 그보다 많으면 마지막 값 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Chain|Burst")
	TArray<float> BurstDamageMultipliers = { 1.0f, 1.6f, 2.5f };

	/** 마지막 참가자를 중심으로 이 반경 안의 적 전부 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Chain|Burst", meta = (ClampMin = "1.0"))
	float BurstRadius = 1000.f;

private:
	FAstralChainRules MakeRules() const;
	double GetServerTime() const;

	/** 살아 있는 파티 인원 — 봇 · 관전자 · 폰이 없거나 죽은 사람을 뺀 PlayerArray */
	int32 CountAliveParty() const;

	void GrantTeamUltGain(const APlayerState* User) const;

	/** 판정 구조체 · 시전 상태가 바뀐 뒤 — 복제 상태 갱신 · 버스트 예약 · 마감 타이머 */
	void HandleTrackerChanged();
	void OnCloseTimer();

	// ─── 시전 ───

	void ApplyUltBlock(const APlayerState* Caster);
	void RemoveUltBlock();

	/** 시전 상태를 걷는다 — 차단 · 상한 타이머 · 시전자 */
	void EndCast();
	void OnCastTimeout();

	// ─── 버스트 ───

	void FireBurst();
	void ApplyBurstDamage(const TArray<int32>& ParticipantIds);

	UPROPERTY(ReplicatedUsing = OnRep_ChainState)
	FAstralChainState ChainState;

	/** 서버 전용 */
	FAstralChainTracker Tracker;
	FAstralChainBurstReport LastBurstReport;

	/** 서버 전용 — 지금 오의를 쓰는 사람. 0 = 없음 */
	int32 CastingPlayerId = 0;

	FTimerHandle CloseTimerHandle;
	FTimerHandle CastTimeoutHandle;

	/** Burst 단계에 들어 다음 틱의 피해를 예약해 둔 상태 */
	bool bBurstScheduled = false;

	struct FUltBlockEntry
	{
		TWeakObjectPtr<UAbilitySystemComponent> ASC;
		FActiveGameplayEffectHandle Handle;
	};
	TArray<FUltBlockEntry> UltBlocks;
};
