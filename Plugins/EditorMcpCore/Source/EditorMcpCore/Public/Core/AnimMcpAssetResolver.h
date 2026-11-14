#pragma once

#include "CoreMinimal.h"

class UAnimBlueprint;
class UAnimationAsset;
class USkeleton;
struct FAnimMcpError;

/**
 * 경로 → 애셋 해석. 존재 여부는 AssetRegistry 로 먼저 확인해 ASSET_NOT_FOUND 를 명확히 돌려주고, 그 뒤에 로드한다.
 * 받는 경로 형식: "/Game/A/B" 또는 "/Game/A/B.B" — 둘 다 오브젝트 경로로 정규화한다.
 */
namespace AnimMcpAssetResolver
{
	/** "/Game/A/B" → "/Game/A/B.B". 이미 오브젝트 경로면 그대로 */
	EDITORMCPCORE_API FString NormalizeObjectPath(const FString& InPath);

	/** 오브젝트 경로 → 패키지 경로 ("/Game/A/B.B" → "/Game/A/B") */
	EDITORMCPCORE_API FString ToPackagePath(const FString& InPath);

	EDITORMCPCORE_API bool AssetExists(const FString& ObjectPath);

	/** 애니 애셋 단축 로더 — 엔진(Engine 모듈) 타입만 써서 코어에 둔다(AnimGraphMcp 가 주로 쓴다) */
	EDITORMCPCORE_API UAnimBlueprint* LoadAnimBlueprint(const FString& AssetPath, FAnimMcpError& OutError);
	EDITORMCPCORE_API USkeleton* LoadSkeleton(const FString& AssetPath, FAnimMcpError& OutError);
	EDITORMCPCORE_API UAnimationAsset* LoadAnimationAsset(const FString& AssetPath, FAnimMcpError& OutError);

	/** 공통 로드 — 클래스 불일치는 BAD_REQUEST */
	EDITORMCPCORE_API UObject* LoadAssetOfClass(const FString& AssetPath, UClass* ExpectedClass, FAnimMcpError& OutError);
}
