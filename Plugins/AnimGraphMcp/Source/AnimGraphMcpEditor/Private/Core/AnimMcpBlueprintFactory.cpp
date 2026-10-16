#include "AnimMcpBlueprintFactory.h"

#include "AnimMcpAssetOps.h"
#include "AnimMcpAssetProtection.h"
#include "AnimMcpAssetResolver.h"
#include "AnimMcpLog.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimBlueprintGeneratedClass.h"
#include "Animation/AnimInstance.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Bridge/AnimMcpTypes.h"
#include "Editor.h"
#include "Engine/BlueprintGeneratedClass.h"
#include "Engine/SkeletalMesh.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/PackageName.h"
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"

namespace AnimMcpBlueprintFactory
{
	UClass* ResolveClass(const FString& InClassPath, FAnimMcpError& OutError)
	{
		const FString ClassPath = InClassPath.TrimStartAndEnd();
		if (ClassPath.IsEmpty())
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("class path is empty"));
			return nullptr;
		}

		UClass* Found = nullptr;
		if (ClassPath.StartsWith(TEXT("/Script/")))
		{
			Found = FindObject<UClass>(nullptr, *ClassPath);
		}
		else if (ClassPath.Contains(TEXT("/")))
		{
			// BP 클래스 — "/Game/X/BP.BP" 또는 "/Game/X/BP.BP_C"
			FString Path = AnimMcpAssetResolver::NormalizeObjectPath(ClassPath);
			Found = LoadObject<UClass>(nullptr, *Path);
			if (!Found && !Path.EndsWith(TEXT("_C")))
			{
				Found = LoadObject<UClass>(nullptr, *(Path + TEXT("_C")));
			}
		}
		else
		{
			Found = FindFirstObject<UClass>(*ClassPath, EFindFirstObjectOptions::None, ELogVerbosity::Warning, TEXT("AnimGraphMcp ResolveClass"));
		}

		if (!Found)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Class '%s' not found (use /Script/Module.Class, a BP class path, or an exact class name)"), *ClassPath));
		}
		return Found;
	}

	UAnimBlueprint* CreateAnimBlueprint(const FCreateParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		check(IsInGameThread());

		// 경로 분해·검증
		const FString PackagePath = AnimMcpAssetResolver::ToPackagePath(Params.AssetPath);
		FText PathReason;
		if (!FPackageName::IsValidLongPackageName(PackagePath, /*bIncludeReadOnlyRoots*/ false, &PathReason))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Invalid package path '%s': %s"), *PackagePath, *PathReason.ToString()));
			return nullptr;
		}
		const FString AssetName = FPackageName::GetLongPackageAssetName(PackagePath);
		const FString ObjectPath = PackagePath + TEXT(".") + AssetName;

		// 부모 클래스 — 팩토리와 같은 조건 (AnimBlueprintFactory.cpp:456)
		UClass* ParentClass = ResolveClass(Params.ParentClassPath, OutError);
		if (!ParentClass)
		{
			return nullptr;
		}
		if (!ParentClass->IsChildOf(UAnimInstance::StaticClass()) || !FKismetEditorUtilities::CanCreateBlueprintOfClass(ParentClass))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' is not a valid AnimInstance parent class for an Animation Blueprint"), *ParentClass->GetPathName()));
			return nullptr;
		}

		USkeleton* Skeleton = AnimMcpAssetResolver::LoadSkeleton(Params.SkeletonPath, OutError);
		if (!Skeleton)
		{
			return nullptr;
		}

		USkeletalMesh* PreviewMesh = nullptr;
		if (!Params.PreviewMeshPath.IsEmpty())
		{
			PreviewMesh = Cast<USkeletalMesh>(AnimMcpAssetResolver::LoadAssetOfClass(Params.PreviewMeshPath, USkeletalMesh::StaticClass(), OutError));
			if (!PreviewMesh)
			{
				return nullptr;
			}
		}

		// 기존 애셋 처리 — 보호 목록(Phase 6-2) → 삭제 + 메모리 잔존 객체 정리 (AnimMcpAssetOps 공용)
		if (AnimMcpAssetResolver::AssetExists(ObjectPath))
		{
			if (!Params.bOverwrite)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetExists, FString::Printf(TEXT("'%s' already exists (pass overwrite=true to replace)"), *ObjectPath));
				return nullptr;
			}
			if (!AnimMcpAssetProtection::EnsureNotProtected(ObjectPath, TEXT("overwrite"), OutError))
			{
				return nullptr;
			}
			if (!AnimMcpAssetOps::DeleteAssetAtPath(ObjectPath, Context, OutError))
			{
				return nullptr;
			}
			Context.AddDiagnostic(TEXT("info"), TEXT("ASSET_REPLACED"), FString::Printf(TEXT("Deleted existing '%s' before creating"), *ObjectPath));
		}

		UPackage* Package = CreatePackage(*PackagePath);
		if (!Package)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("CreatePackage failed for '%s'"), *PackagePath));
			return nullptr;
		}
		Package->FullyLoad();

		// CreateBlueprint 는 같은 이름의 BP 가 Outer 에 있으면 check 로 죽는다. DeleteAssetAtPath 가 잔존 객체·파일을 치우지만,
		// 그래도 남아 있으면(실측: 참조 중인 패키지는 ForceDelete 가 건너뛴다) 임시 패키지로 옮기고 가비지로 표시한다
		if (UObject* Stale = FindObject<UObject>(Package, *AssetName))
		{
			const FName StaleName = MakeUniqueObjectName(GetTransientPackage(), Stale->GetClass(), FName(*(AssetName + TEXT("_MCP_STALE"))));
			Stale->ClearFlags(RF_Public | RF_Standalone);
			if (!Stale->Rename(*StaleName.ToString(), GetTransientPackage(), REN_DontCreateRedirectors | REN_NonTransactional | REN_DoNotDirty))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetExists, FString::Printf(TEXT("A Blueprint object named '%s' still exists in package '%s' and could not be moved aside"), *AssetName, *PackagePath));
				return nullptr;
			}
			Stale->MarkAsGarbage();
			Context.AddDiagnostic(TEXT("info"), TEXT("STALE_OBJECT_MOVED"), FString::Printf(TEXT("In-memory object '%s' survived deletion; moved to transient package before creating"), *AssetName));
		}

		// 팩토리 경로 재현 (AnimBlueprintFactory.cpp:466) — 내부에서 GN_AnimGraph 그래프와 Root 노드가 생긴다 (Kismet2.cpp:500)
		UAnimBlueprint* NewBP = Cast<UAnimBlueprint>(FKismetEditorUtilities::CreateBlueprint(
			ParentClass, Package, FName(*AssetName), BPTYPE_Normal,
			UAnimBlueprint::StaticClass(), UBlueprintGeneratedClass::StaticClass(), FName(TEXT("AnimGraphMcp"))));
		if (!NewBP)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("FKismetEditorUtilities::CreateBlueprint returned null"));
			return nullptr;
		}

		// 스켈레톤 3곳 (AnimBlueprintFactory.cpp:475-494)
		NewBP->bIsTemplate = false;
		NewBP->TargetSkeleton = Skeleton;
		if (UAnimBlueprintGeneratedClass* GenClass = Cast<UAnimBlueprintGeneratedClass>(NewBP->GeneratedClass))
		{
			GenClass->TargetSkeleton = Skeleton;
		}
		if (UAnimBlueprintGeneratedClass* SkelClass = Cast<UAnimBlueprintGeneratedClass>(NewBP->SkeletonGeneratedClass))
		{
			SkelClass->TargetSkeleton = Skeleton;
		}
		if (PreviewMesh)
		{
			NewBP->SetPreviewMesh(PreviewMesh);
		}

		FAssetRegistryModule::AssetCreated(NewBP);
		NewBP->MarkPackageDirty();
		FBlueprintEditorUtils::MarkBlueprintAsModified(NewBP);

		UE_LOG(LogAnimGraphMcp, Log, TEXT("Created Animation Blueprint %s (parent %s, skeleton %s)"), *ObjectPath, *ParentClass->GetName(), *Skeleton->GetName());
		return NewBP;
	}
}
