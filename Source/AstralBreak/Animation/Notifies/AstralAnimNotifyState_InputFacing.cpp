#include "AstralAnimNotifyState_InputFacing.h"

#include "Animation/AstralRootMotionModifier_InputFacing.h"

UAstralAnimNotifyState_InputFacing::UAstralAnimNotifyState_InputFacing(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// 베이스는 RootMotionModifier_SkewWarp를 필수 CreateDefaultSubobject로 만든다 — DoNotCreateDefaultSubobject는 필수 객체에 무시되고
	// SetDefaultSubobjectClass는 SkewWarp 자식만 허용한다. 기본 객체는 그대로 두고 실행 템플릿 참조만 전용 타입으로 바꾼다
	RootMotionModifier = ObjectInitializer.CreateDefaultSubobject<UAstralRootMotionModifier_InputFacing>(this, TEXT("RootMotionModifier_InputFacing"));
}

const UAstralRootMotionModifier_InputFacing* UAstralAnimNotifyState_InputFacing::GetInputFacingModifier() const
{
	return Cast<UAstralRootMotionModifier_InputFacing>(RootMotionModifier);
}

FString UAstralAnimNotifyState_InputFacing::GetNotifyName_Implementation() const
{
	return TEXT("Astral Input Facing");
}
