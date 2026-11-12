#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/AstralGameplayAbility.h"
#include "AstralGA_Enemy_MeleeAttack.generated.h"

class AAIController;
class UAbilityTask_WaitDelay;
class UAnimMontage;

/**
 * 적의 단발 근접 공격 — 한 번 발동하면 예고 → 전방 스윕 → 종료 (Docs/Design/m3-enemy-ai.md §8 ④ · ⑤).
 * 스스로 반복하지 않는다. 언제 다시 쓸지는 StateTree 가 정한다(FAstralStateTreeTask_ActivateAbility 가 발동하고 종료를 기다린다).
 * 상주 루프인 UAstralGA_Enemy_TelegraphAttack(더미용)과 같은 AbilitySet 에 넣지 않는다 — 공격이 둘이 된다.
 *
 * 회전: 예고 앞 FacingTrackDuration 동안만 타깃을 포커스해 따라 돌고, 그 뒤 판정까지는 방향을 고정한다.
 *       고정 뒤 옆으로 빠지면 스윕이 빗나간다 — 위치 이탈로 피하는 창이다. 폰의 이동 컴포넌트가 컨트롤러 회전을 따라야 한다
 *       (bUseControllerDesiredRotation — 적 BP 의 값). 타깃은 발동 이벤트 데이터의 Target 으로 받는다.
 * 패링: 스윕이 패링당하면 GameplayEvent.Staggered 가 스윕 호출 안에서 온다. 그러면 StaggerRecovery 만큼 더 머문 뒤 끝난다 —
 *       트리는 종료를 기다리는 중이라 그동안 아무것도 하지 않는다. 경직을 별도 GA 로 떼는 것은 단위 C.
 *
 * ServerOnly — 판정 · 타이밍 전부 서버 권위. 예고 표시는 더미와 같은 DrawDebug 멀티캐스트(MVP).
 * 값은 전부 잠정이고 BP 자식(GA_Enemy_MeleeAttack)에서 바꾼다.
 *
 * 두 방식 (§10 C1 ④) — AttackMontage 가 비어 있으면 위의 타이머 방식 그대로다(마네킹 BP_Enemy_Melee · 기존 시험의 고정물).
 * 몽타주가 있으면: 몽타주 재생 → 몽타주의 타격 노티파이(HitEventTag)마다 스윕 1회 → 몽타주가 끝나면 종료. 노티파이가 여럿이면 연타다.
 *       예고 길이는 TelegraphDuration 이 아니라 첫 타격 노티파이까지의 시간이고, 예고 태그는 첫 타격에서 내린다.
 *       클라이언트는 ASC 가 복제하는 몽타주로 준비 동작을 본다. 타깃 추적 · 경직 처리는 타이머 방식과 같은 코드다.
 *       패링당하면 몽타주를 멈추고(블렌드 아웃) 경직만큼 머문다 — 휘두르던 동작이 끊기는 것이 패링 성공의 표시다. 경직 애니는 단위 C2.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Enemy_MeleeAttack : public UAstralGameplayAbility
{
	GENERATED_BODY()

public:
	UAstralGA_Enemy_MeleeAttack(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	// 데이터 읽기 — 시험 · 애셋 검증용
	UAnimMontage* GetAttackMontage() const { return AttackMontage; }
	const FGameplayTag& GetHitEventTag() const { return HitEventTag; }
	float GetMontagePlayRate() const { return MontagePlayRate; }
	float GetBaseDamage() const { return BaseDamage; }
	float GetStaggerRecovery() const { return StaggerRecovery; }

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	/** 타깃 추적 끝 — 포커스를 풀어 방향을 고정하고 남은 예고 시간을 기다린다 */
	UFUNCTION()
	void OnFacingTrackElapsed();

	/** 예고 끝 — 판정 */
	UFUNCTION()
	void OnTelegraphElapsed();

	/** 패링당함 — 판정 안에서 오면 판정 뒤에, 그 전에 오면 예고를 끊고 바로 경직으로 간다 */
	UFUNCTION()
	void OnStaggered(FGameplayEventData EventData);

	UFUNCTION()
	void OnStaggerRecovered();

	/** 몽타주 방식 — 타격 노티파이. 올 때마다 스윕 1회, 첫 번째에서 예고가 끝난다 */
	UFUNCTION()
	void OnMontageHit(FGameplayEventData EventData);

	/** 몽타주 방식 — 몽타주가 끝났다(블렌드 아웃 시작 포함). 경직 중이면 경직 타이머가 끝낸다 */
	UFUNCTION()
	void OnMontageFinished();

	/** 몽타주 방식 — 다른 몽타주에 밀렸거나 재생에 실패했다. 스스로 멈춘 것(경직)은 무시한다 */
	UFUNCTION()
	void OnMontageInterrupted();

	/** DelaySeconds 뒤 Callback (UFUNCTION 이름). 0 이하면 다음 틱 */
	void WaitThen(float DelaySeconds, FName CallbackName);

	/** 전방 스윕 1회 — 두 방식 공용. 패링당하면 이 호출 안에서 OnStaggered 가 불린다 */
	void SweepOnce();

	/** 몽타주의 첫 타격 노티파이까지의 시간(초, 재생 속도 반영). 노티파이가 없으면 음수 */
	float FindFirstHitTime() const;

	void BeginStaggerRecovery();

	/** 예고 표시 — 지금 방향 기준. 방향을 고정할 때 한 번 더 그려 마지막 표시가 실제 판정 볼륨과 같게 한다 */
	void DrawTelegraph(float Duration) const;

	/** 예고 구간 정리 (루즈 태그 해제) — 멱등 */
	void ClearTelegraph();

	/** 이 어빌리티가 건 포커스만 푼다 — 멱등 */
	void ClearFacingFocus();

	void FinishAttack();

protected:
	/** 공격 데미지 (Damage GE는 GameData 전역) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Attack")
	float BaseDamage = 15.f;

	/** 예고 시간 — 발동부터 판정까지. 이 구간이 가드 · 패링 · 회피 반응 창. 몽타주 방식에서는 쓰지 않는다(첫 타격 노티파이 시각이 예고 길이) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Attack", Meta = (ClampMin = "0.1"))
	float TelegraphDuration = 1.0f;

	/** 예고 앞부분 중 타깃을 따라 도는 시간 — 나머지(TelegraphDuration - 이 값)는 방향이 고정된다. TelegraphDuration 보다 크면 끝까지 따라 돈다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Attack", Meta = (ClampMin = "0.0"))
	float FacingTrackDuration = 0.7f;

	/** 패링당한 뒤 경직 시간 — 이만큼 더 머문 뒤 끝난다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Attack", Meta = (ClampMin = "0.0"))
	float StaggerRecovery = 2.0f;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Attack|Trace")
	float TraceRadius = 80.f;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Attack|Trace")
	float TraceDistance = 200.f;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Attack|Trace")
	float TraceStartOffset = 50.f;

	/** 공격 몽타주(선택) — 비어 있으면 타이머 방식. 있으면 판정 시점은 이 몽타주의 타격 노티파이가 낸다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Attack|Montage")
	TObjectPtr<UAnimMontage> AttackMontage;

	/** 몽타주의 타격 노티파이(UAstralAnimNotify_GameplayEvent)가 보내는 태그 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Attack|Montage", Meta = (Categories = "GameplayEvent"))
	FGameplayTag HitEventTag;

	/** 몽타주 재생 속도 — 준비 동작 길이(= 예고)를 이 값으로 맞춘다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Attack|Montage", Meta = (ClampMin = "0.1"))
	float MontagePlayRate = 1.0f;

	/** 빨간 예고 캡슐(DrawDebug 멀티캐스트)을 그릴지 — 몽타주의 준비 동작이 예고로 충분하면 끈다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Attack|Debug")
	bool bDrawTelegraphDebug = true;

private:
	/** 진행 중인 대기 (추적 / 남은 예고 / 경직 중 하나) */
	UPROPERTY(Transient)
	TObjectPtr<UAbilityTask_WaitDelay> ActiveDelayTask;

	/** 포커스를 건 컨트롤러 — 푼 뒤에는 비운다 */
	TWeakObjectPtr<AAIController> FocusedController;

	/** 이번 발동의 예고 길이 — 타이머 방식 = TelegraphDuration, 몽타주 방식 = 첫 타격 노티파이까지 */
	float ActiveTelegraphDuration = 0.f;

	/** 이번 발동이 몽타주 방식인가 (발동 때 AttackMontage 유무로 정한다) */
	bool bMontageAttack = false;

	bool bTelegraphing = false;
	bool bSweeping = false;
	bool bStaggered = false;
};
