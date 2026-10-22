#pragma once

#include "CoreMinimal.h"
#include "AnimGraphNode_SkeletalControlBase.h"
#include "Animation/AnimNode_AstralAimCorrection.h"
#include "AnimGraphNode_AstralAimCorrection.generated.h"

class FCompilerResultsLog;

/** 그래프 노드 — FAnimNode_AstralAimCorrection(최종 조준 보정)을 AnimBP 에 놓는다. 동작·배치 규칙은 런타임 노드 주석 */
UCLASS(Meta = (Keywords = "Aim Muzzle Barrel Correction"))
class ASTRALBREAKEDITOR_API UAnimGraphNode_AstralAimCorrection : public UAnimGraphNode_SkeletalControlBase
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, Category = "Settings")
	FAnimNode_AstralAimCorrection Node;

	//~UEdGraphNode
	virtual FText GetNodeTitle(ENodeTitleType::Type TitleType) const override;
	virtual FText GetTooltipText() const override;
	//~End UEdGraphNode

protected:
	//~UAnimGraphNode_Base
	virtual void ValidateAnimNodeDuringCompilation(USkeleton* ForSkeleton, FCompilerResultsLog& MessageLog) override;
	//~End UAnimGraphNode_Base

	//~UAnimGraphNode_SkeletalControlBase
	virtual FText GetControllerDescription() const override;
	virtual const FAnimNode_SkeletalControlBase* GetNode() const override { return &Node; }
	//~End UAnimGraphNode_SkeletalControlBase
};
