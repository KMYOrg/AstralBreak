// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Character/AstralCharacter.h"
#include "AstralCharacter_Hero.generated.h"

class USpringArmComponent;
class UCameraComponent;
class UAstralHeroCameraComponent;
class UAstralHeroComponent;
class UAstralTargetingComponent;

UCLASS()
class ASTRALBREAK_API AAstralCharacter_Hero : public AAstralCharacter
{
	GENERATED_BODY()

public:
	AAstralCharacter_Hero(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	UFUNCTION(BlueprintPure, Category = "Astral|Hero")
	UAstralTargetingComponent* GetTargetingComponent() const { return TargetingComponent; }

	UFUNCTION(BlueprintPure, Category = "Astral|Hero")
	UAstralHeroCameraComponent* GetHeroCameraComponent() const { return HeroCameraComponent; }

protected:
	//~AActor
	virtual void PostInitializeComponents() override;
	//~End AActor

protected:
	/** 3인칭 카메라 팔. 소울라이크 회전: 마우스가 카메라 독립 제어. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<USpringArmComponent> CameraBoom;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UCameraComponent> FollowCamera;

	/** Hero 전용 초기화 허브. Input/Lockon 입력을 InitState 체인으로 중재 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralHeroComponent> HeroComponent;

	/** 락온 타게팅 — 누구를 (후보 탐색·점수·상태 기계). 히어로 전용, 로컬 전용 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralTargetingComponent> TargetingComponent;

	/** 락온 카메라 — 타깃을 화면에 어떻게 유지하는가. 붐·카메라·타게팅 참조를 이 폰이 주입한다 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralHeroCameraComponent> HeroCameraComponent;
};
