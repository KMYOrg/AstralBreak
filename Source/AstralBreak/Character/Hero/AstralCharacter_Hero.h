// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Character/AstralCharacter.h"
#include "Combat/AstralInputFacingTypes.h"
#include "AstralCharacter_Hero.generated.h"

class AAstralPlayerState;
class UAstralHeroCameraComponent;
class UAstralHeroComponent;
class UAstralLoadoutComponent;
class UAstralTargetingComponent;
class UCameraComponent;
class UMotionWarpingComponent;
class USpringArmComponent;

/**
 * 플레이어 히어로 — ASC는 PlayerState 소유. HeroComponent가 InitState 체인으로 PlayerState·컨트롤러·입력 도착을 중재하고
 * DataInitialized 시점에 PawnExtension에 ASC를 넘긴다. 베이스의 공통 결합 뒤에 로드아웃(외형·장비 복원)을 적용한다
 */
UCLASS()
class ASTRALBREAK_API AAstralCharacter_Hero : public AAstralCharacter
{
	GENERATED_BODY()

public:
	AAstralCharacter_Hero(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	UFUNCTION(BlueprintCallable, Category = "Astral|Hero")
	AAstralPlayerState* GetAstralPlayerState() const;

	UFUNCTION(BlueprintPure, Category = "Astral|Hero")
	UAstralLoadoutComponent* GetLoadoutComponent() const { return LoadoutComponent; }

	UFUNCTION(BlueprintPure, Category = "Astral|Hero")
	UAstralTargetingComponent* GetTargetingComponent() const { return TargetingComponent; }

	UFUNCTION(BlueprintPure, Category = "Astral|Hero")
	UAstralHeroCameraComponent* GetHeroCameraComponent() const { return HeroCameraComponent; }

	// 입력 회전 관찰자 표현 (락온 7단계) — 단일 원본은 이 액터. CMC는 복제하지 않으므로 여기 둔다

	/** 서버 전용 — 입력 Modifier가 창 안에서 소비한 샘플과 적용 문맥을 기록. 값이 같으면 쓰지 않는다 */
	void SetInputFacingPresentation(const FAstralInputFacingPresentation& Presentation);

	/** 시뮬 프록시의 입력 Modifier가 읽는다 — 자기 창과 일치할 때만 유효 */
	const FAstralInputFacingPresentation& GetInputFacingPresentation() const { return InputFacingPresentation; }

protected:
	//~AActor
	virtual void PostInitializeComponents() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	//~End AActor

	//~AAstralCharacter
	/** 베이스 결합(정책 → 시드) 다음에 로드아웃 적용 — 순서 불변식 */
	virtual void OnAbilitySystemInitialized() override;
	virtual void OnAbilitySystemUninitialized() override;
	//~End AAstralCharacter

protected:
	/** 3인칭 카메라 팔. 소울라이크 회전: 마우스가 카메라 독립 제어. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<USpringArmComponent> CameraBoom;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UCameraComponent> FollowCamera;

	/** Hero 전용 초기화 허브. Input/Lockon 입력을 InitState 체인으로 중재 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralHeroComponent> HeroComponent;

	/** 로드아웃 — 외형·장비 복원. 초기화는 이 폰이 OnAbilitySystemInitialized에서 명시 호출 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralLoadoutComponent> LoadoutComponent;

	/** 락온 타게팅 — 누구를 (후보 탐색·점수·상태 기계). 히어로 전용, 로컬 전용 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralTargetingComponent> TargetingComponent;

	/** 락온 카메라 — 타깃을 화면에 어떻게 유지하는가. 붐·카메라·타게팅 참조를 이 폰이 주입한다 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralHeroCameraComponent> HeroCameraComponent;

	/** 공격 방향 보정 — anim 루트모션의 로컬 트랜스폼을 월드 변환 직전에 수정 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UMotionWarpingComponent> MotionWarpingComponent;

	/**
	 * 관찰자용 승인 입력 샘플 — COND_SimulatedOnly (소유 클라는 CMC 예측 샘플, 서버는 패킷 샘플을 쓴다).
	 * 최신 값만 도착하고 몽타주 복제와 원자적이지 않다 — 관찰자는 창·몽타주 일치를 확인하고 추정만 하며, 최종 자세는 이동 복제가 기준
	 */
	UPROPERTY(Replicated)
	FAstralInputFacingPresentation InputFacingPresentation;
};
