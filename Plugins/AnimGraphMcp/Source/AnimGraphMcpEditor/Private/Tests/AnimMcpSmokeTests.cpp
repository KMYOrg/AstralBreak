// Phase 6-5 — AnimBP 구조 스모크 테스트. 설정 경로([AnimGraphMcp] SmokeTestPaths, 기본 /Game/Animation) 아래의 모든
// Animation Blueprint 를 애셋마다 하나의 테스트로 연다: 컴파일 0 에러 · 루트 Output Pose 연결(레이어 제공자는 경고) · 빈 상태 없음 ·
// UseCachedPose 의 소스 존재 · LinkedAnimLayer 의 레이어 유효 · 구현 레이어 그래프의 빈 Output Pose(경고).
// run_automation_tests {filter:"AnimGraphMcp.Smoke"} 로 돈다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Algo/AnyOf.h"
#include "AnimGraphNode_LinkedAnimLayer.h"
#include "AnimGraphNode_Root.h"
#include "AnimGraphNode_SaveCachedPose.h"
#include "AnimGraphNode_Slot.h"
#include "AnimGraphNode_StateResult.h"
#include "AnimGraphNode_UseCachedPose.h"
#include "AnimStateNode.h"
#include "AnimationStateMachineGraph.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimLayerInterface.h"
#include "Animation/AnimMontage.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/ARFilter.h"
#include "AssetRegistry/AssetData.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Core/AnimMcpAnimLayer.h"
#include "Core/AnimMcpGraphInspector.h"
#include "Core/AnimMcpMontage.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphPin.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/ConfigCacheIni.h"

namespace
{
	/** ini [AnimGraphMcp] SmokeTestPaths 아래의 Class 애셋 — 경로 순 */
	void ListSmokeAssets(UClass* Class, TArray<FAssetData>& OutAssets)
	{
		TArray<FString> Paths;
		GConfig->GetArray(TEXT("AnimGraphMcp"), TEXT("SmokeTestPaths"), Paths, GEngineIni);
		if (Paths.Num() == 0)
		{
			Paths.Add(TEXT("/Game/Animation"));
		}

		FARFilter Filter;
		Filter.ClassPaths.Add(Class->GetClassPathName());
		Filter.bRecursiveClasses = true;
		Filter.bRecursivePaths = true;
		for (const FString& P : Paths)
		{
			Filter.PackagePaths.Add(FName(*P.TrimStartAndEnd()));
		}
		FAssetRegistryModule::GetRegistry().GetAssets(Filter, OutAssets);
		OutAssets.Sort([](const FAssetData& A, const FAssetData& B) { return A.GetObjectPathString() < B.GetObjectPathString(); });
	}
}

IMPLEMENT_COMPLEX_AUTOMATION_TEST(FAnimMcpSmokeAnimBlueprintTest, "AnimGraphMcp.Smoke.AnimBlueprint", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

void FAnimMcpSmokeAnimBlueprintTest::GetTests(TArray<FString>& OutBeautifiedNames, TArray<FString>& OutTestCommands) const
{
	TArray<FAssetData> Assets;
	ListSmokeAssets(UAnimBlueprint::StaticClass(), Assets);
	for (const FAssetData& Data : Assets)
	{
		OutBeautifiedNames.Add(Data.AssetName.ToString());
		OutTestCommands.Add(Data.GetObjectPathString());
	}
}

bool FAnimMcpSmokeAnimBlueprintTest::RunTest(const FString& Parameters)
{
	UAnimBlueprint* Blueprint = LoadObject<UAnimBlueprint>(nullptr, *Parameters);
	if (!Blueprint)
	{
		AddError(FString::Printf(TEXT("Could not load Animation Blueprint '%s'"), *Parameters));
		return false;
	}

	// 1) 컴파일
	{
		FCompilerResultsLog Log;
		Log.bSilentMode = true;
		FKismetEditorUtilities::CompileBlueprint(Blueprint, EBlueprintCompileOptions::SkipGarbageCollection, &Log);
		if (Log.NumErrors > 0)
		{
			for (const TSharedRef<FTokenizedMessage>& Message : Log.Messages)
			{
				if (Message->GetSeverity() == EMessageSeverity::Error)
				{
					AddError(FString::Printf(TEXT("Compile: %s"), *Message->ToText().ToString()));
				}
			}
		}
	}
	if (Blueprint->BlueprintType == BPTYPE_Interface)
	{
		// 레이어 인터페이스 — 그래프는 서명만, 구조 검사 없음
		return !HasAnyErrors();
	}

	// 2) 루트 Output Pose 연결 — 레이어 제공자 ABP(인터페이스 구현만 하고 루트 그래프는 쓰지 않는 Lyra ABP_ItemAnimLayersBase 식)는 경고로 낮춘다
	const bool bLayerProvider = Algo::AnyOf(Blueprint->ImplementedInterfaces, [](const FBPInterfaceDescription& Desc)
	{
		return Desc.Interface && Desc.Interface->IsChildOf(UAnimLayerInterface::StaticClass()) && Desc.Graphs.Num() > 0;
	});
	if (UEdGraph* Root = AnimMcpGraphInspector::FindRootAnimGraph(Blueprint))
	{
		TArray<UAnimGraphNode_Root*> Roots;
		Root->GetNodesOfClass<UAnimGraphNode_Root>(Roots);
		for (const UAnimGraphNode_Root* RootNode : Roots)
		{
			const UEdGraphPin* Result = RootNode->FindPin(TEXT("Result"));
			if (!Result || Result->LinkedTo.Num() == 0)
			{
				if (bLayerProvider)
				{
					AddWarning(TEXT("Root AnimGraph: Output Pose 'Result' pin is not connected (layer provider — root graph unused)"));
				}
				else
				{
					AddError(TEXT("Root AnimGraph: Output Pose 'Result' pin is not connected"));
				}
			}
		}
	}
	else
	{
		AddError(TEXT("No root AnimGraph"));
	}

	// 2b) 구현한 레이어 그래프의 Output Pose — 비어 있으면 경고 (기본 구현을 비워 두는 Lyra 베이스 ABP 가 정상이므로 오류는 아님)
	for (const FBPInterfaceDescription& Desc : Blueprint->ImplementedInterfaces)
	{
		if (!Desc.Interface || !Desc.Interface->IsChildOf(UAnimLayerInterface::StaticClass())) { continue; }
		for (const UEdGraph* LayerGraph : Desc.Graphs)
		{
			if (!LayerGraph) { continue; }
			TArray<UAnimGraphNode_Root*> Roots;
			LayerGraph->GetNodesOfClass<UAnimGraphNode_Root>(Roots);
			for (const UAnimGraphNode_Root* RootNode : Roots)
			{
				const UEdGraphPin* Result = RootNode->FindPin(TEXT("Result"));
				if (!Result || Result->LinkedTo.Num() == 0)
				{
					AddWarning(FString::Printf(TEXT("Layer '%s' (%s): Output Pose is not connected (empty layer implementation)"), *LayerGraph->GetName(), *Desc.Interface->GetName()));
				}
			}
		}
	}

	// 3) 그래프 전체 — 빈 상태 · 끊긴 캐시 · 빈 레이어
	TArray<AnimMcpGraphInspector::FGraphRecord> Graphs;
	AnimMcpGraphInspector::CollectGraphs(Blueprint, Graphs);
	for (const AnimMcpGraphInspector::FGraphRecord& Record : Graphs)
	{
		if (!Record.Graph) { continue; }
		for (UEdGraphNode* Node : Record.Graph->Nodes)
		{
			if (const UAnimStateNode* State = Cast<UAnimStateNode>(Node))
			{
				const UEdGraph* Bound = State->GetBoundGraph();
				bool bLinked = false;
				if (Bound)
				{
					TArray<UAnimGraphNode_StateResult*> Results;
					Bound->GetNodesOfClass<UAnimGraphNode_StateResult>(Results);
					for (const UAnimGraphNode_StateResult* R : Results)
					{
						const UEdGraphPin* Pin = R->FindPin(TEXT("Result"));
						bLinked |= Pin && Pin->LinkedTo.Num() > 0;
					}
				}
				if (!bLinked)
				{
					AddError(FString::Printf(TEXT("State '%s' in '%s' is empty (its Output Animation Pose is not connected)"), *State->GetStateName(), *Record.Graph->GetName()));
				}
			}
			else if (const UAnimGraphNode_UseCachedPose* Use = Cast<UAnimGraphNode_UseCachedPose>(Node))
			{
				if (!Use->SaveCachedPoseNode.IsValid())
				{
					AddError(FString::Printf(TEXT("UseCachedPose %s in '%s' has no SaveCachedPose source (broken cache link)"), *Use->NodeGuid.ToString(), *Record.Graph->GetName()));
				}
			}
			else if (const UAnimGraphNode_LinkedAnimLayer* Layer = Cast<UAnimGraphNode_LinkedAnimLayer>(Node))
			{
				UClass* Interface = nullptr;
				if (Layer->Node.Layer.IsNone() || !AnimMcpAnimLayer::FindLayerGraph(Blueprint, Layer->Node.Layer, Interface))
				{
					AddError(FString::Printf(TEXT("LinkedAnimLayer %s in '%s' has no valid layer ('%s')"), *Layer->NodeGuid.ToString(), *Record.Graph->GetName(), *Layer->Node.Layer.ToString()));
				}
			}
		}
	}
	return !HasAnyErrors();
}

// Phase 7-3 — 몽타주 스모크: SmokeTestPaths 아래 AnimMontage 마다 하나. 슬롯이 스켈레톤에 등록돼 있는지(오류) · 같은 스켈레톤의 AnimBP 에 그 이름의
// Slot 노드가 있는지(경고 — 몽타주가 어느 그래프에서도 재생되지 않을 수 있다) · 섹션이 있고 Next 가 존재하는 이름인지(오류) · 첫 섹션이 0 에서 시작하는지(경고).
IMPLEMENT_COMPLEX_AUTOMATION_TEST(FAnimMcpSmokeAnimMontageTest, "AnimGraphMcp.Smoke.AnimMontage", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

void FAnimMcpSmokeAnimMontageTest::GetTests(TArray<FString>& OutBeautifiedNames, TArray<FString>& OutTestCommands) const
{
	TArray<FAssetData> Assets;
	ListSmokeAssets(UAnimMontage::StaticClass(), Assets);
	for (const FAssetData& Data : Assets)
	{
		OutBeautifiedNames.Add(Data.AssetName.ToString());
		OutTestCommands.Add(Data.GetObjectPathString());
	}
}

bool FAnimMcpSmokeAnimMontageTest::RunTest(const FString& Parameters)
{
	UAnimMontage* Montage = LoadObject<UAnimMontage>(nullptr, *Parameters);
	if (!Montage)
	{
		AddError(FString::Printf(TEXT("Could not load AnimMontage '%s'"), *Parameters));
		return false;
	}
	const USkeleton* Skeleton = Montage->GetSkeleton();
	if (!Skeleton)
	{
		AddError(TEXT("Montage has no skeleton"));
		return false;
	}

	// 1) 슬롯 — 스켈레톤 등록 여부
	if (Montage->SlotAnimTracks.Num() == 0)
	{
		AddError(TEXT("Montage has no slot track"));
	}
	for (int32 i = 0; i < Montage->SlotAnimTracks.Num(); ++i)
	{
		const FSlotAnimationTrack& Track = Montage->SlotAnimTracks[i];
		if (!AnimMcpMontage::SkeletonHasSlot(Skeleton, Track.SlotName))
		{
			AddError(FString::Printf(TEXT("Slot track %d '%s' is not registered in skeleton '%s'"), i, *Track.SlotName.ToString(), *Skeleton->GetPathName()));
		}
		if (Track.AnimTrack.AnimSegments.Num() == 0)
		{
			AddWarning(FString::Printf(TEXT("Slot track %d '%s' has no animation segment"), i, *Track.SlotName.ToString()));
		}
	}

	// 2) 섹션 — 존재 · Next 유효 · 범위 · 0 시작
	if (Montage->CompositeSections.Num() == 0)
	{
		AddError(TEXT("Montage has no section (it cannot play)"));
	}
	const float Length = Montage->GetPlayLength();
	float FirstStart = TNumericLimits<float>::Max();
	for (const FCompositeSection& Section : Montage->CompositeSections)
	{
		const float Start = Section.GetTime();
		FirstStart = FMath::Min(FirstStart, Start);
		if (Start < 0.f || Start > Length)
		{
			AddError(FString::Printf(TEXT("Section '%s' starts at %.4f, outside [0, %.4f]"), *Section.SectionName.ToString(), Start, Length));
		}
		if (!Section.NextSectionName.IsNone() && Montage->GetSectionIndex(Section.NextSectionName) == INDEX_NONE)
		{
			AddError(FString::Printf(TEXT("Section '%s' next section '%s' does not exist"), *Section.SectionName.ToString(), *Section.NextSectionName.ToString()));
		}
	}
	if (Montage->CompositeSections.Num() > 0 && FirstStart > KINDA_SMALL_NUMBER)
	{
		AddWarning(FString::Printf(TEXT("First section starts at %.4f — time before it belongs to no section"), FirstStart));
	}

	// 3) 같은 스켈레톤의 AnimBP(SmokeTestPaths 아래)에 그 이름의 Slot 노드가 있는가 — 없으면 경고
	TSet<FName> SlotNodeNames;
	{
		TArray<FAssetData> Blueprints;
		ListSmokeAssets(UAnimBlueprint::StaticClass(), Blueprints);
		for (const FAssetData& Data : Blueprints)
		{
			UAnimBlueprint* Blueprint = Cast<UAnimBlueprint>(Data.GetAsset());
			// 같은 애셋이거나 호환 스켈레톤(IsCompatibleForEditor — 몽타주 재생 가능 범위)인 ABP 만
			if (!Blueprint || !Blueprint->TargetSkeleton || !(Blueprint->TargetSkeleton == Skeleton || Blueprint->TargetSkeleton->IsCompatibleForEditor(Skeleton))) { continue; }
			TArray<AnimMcpGraphInspector::FGraphRecord> Graphs;
			AnimMcpGraphInspector::CollectGraphs(Blueprint, Graphs);
			for (const AnimMcpGraphInspector::FGraphRecord& Record : Graphs)
			{
				if (!Record.Graph) { continue; }
				TArray<UAnimGraphNode_Slot*> SlotNodes;
				Record.Graph->GetNodesOfClass<UAnimGraphNode_Slot>(SlotNodes);
				for (const UAnimGraphNode_Slot* SlotNode : SlotNodes)
				{
					SlotNodeNames.Add(SlotNode->Node.SlotName);
				}
			}
		}
	}
	for (const FSlotAnimationTrack& Track : Montage->SlotAnimTracks)
	{
		if (!SlotNodeNames.Contains(Track.SlotName))
		{
			AddWarning(FString::Printf(TEXT("No Slot node named '%s' in any Animation Blueprint for skeleton '%s' under SmokeTestPaths — the montage may never play"), *Track.SlotName.ToString(), *Skeleton->GetName()));
		}
	}
	return !HasAnyErrors();
}

#endif // WITH_DEV_AUTOMATION_TESTS
