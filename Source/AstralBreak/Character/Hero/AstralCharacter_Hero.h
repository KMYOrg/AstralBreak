// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Character/AstralCharacter.h"
#include "AstralCharacter_Hero.generated.h"

class USpringArmComponent;
class UCameraComponent;
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

protected:
	/** 3인칭 카메라 팔. 소울라이크 회전: 마우스가 카메라 독립 제어. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<USpringArmComponent> CameraBoom;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UCameraComponent> FollowCamera;

	/** Hero 전용 초기화 허브. Input/Camera/Lockon을 InitState 체인으로 중재 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralHeroComponent> HeroComponent;

	/** 락온 타게팅 — 후보 탐색·점수·상태 기계 (히어로 전용, 로컬 전용) */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Hero", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralTargetingComponent> TargetingComponent;
};
