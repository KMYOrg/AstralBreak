#pragma once

#include "CoreMinimal.h"

class UAnimBlueprint;
class UClass;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * AnimBP 생성 — UAnimBlueprintFactory 를 쓰지 않는다 (ConfigureProperties 가 Slate 다이얼로그, 실패 시 FMessageDialog 모달).
 * 팩토리의 FactoryCreateNew 가 하는 일을 재현한다 (Private/Factories/AnimBlueprintFactory.cpp:451-503):
 *   사전 검증 → FKismetEditorUtilities::CreateBlueprint → TargetSkeleton 3곳 세팅 → (선택) 프리뷰 메시.
 */
namespace AnimMcpBlueprintFactory
{
	struct FCreateParams
	{
		/** "/Game/A/ABP_X" 또는 "/Game/A/ABP_X.ABP_X" */
		FString AssetPath;
		/** "/Script/Engine.AnimInstance", "/Script/MyGame.MyAnimInstance"(짧은 이름 "MyAnimInstance" 도 가능), 또는 BP 클래스 경로 */
		FString ParentClassPath = TEXT("/Script/Engine.AnimInstance");
		FString SkeletonPath;
		FString PreviewMeshPath;
		/** 같은 경로에 애셋이 있으면 삭제 후 생성. 기본 false → ASSET_EXISTS */
		bool bOverwrite = false;
	};

	/** 이름/경로 문자열 → UClass. "/Script/..." 네이티브, "/Game/...(_C)" BP 클래스, 짧은 이름은 FindFirstObject */
	UClass* ResolveClass(const FString& ClassPath, FAnimMcpError& OutError);

	UAnimBlueprint* CreateAnimBlueprint(const FCreateParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError);
}
