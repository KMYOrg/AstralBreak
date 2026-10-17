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
#include "AnimGraphNode_StateResult.h"
#include "AnimGraphNode_UseCachedPose.h"
#include "AnimStateNode.h"
#include "AnimationStateMachineGraph.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimLayerInterface.h"
#include "AssetRegistry/ARFilter.h"
#include "AssetRegistry/AssetData.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Core/AnimMcpAnimLayer.h"
#include "Core/AnimMcpGraphInspector.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphPin.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/ConfigCacheIni.h"

IMPLEMENT_COMPLEX_AUTOMATION_TEST(FAnimMcpSmokeAnimBlueprintTest, "AnimGraphMcp.Smoke.AnimBlueprint", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

void FAnimMcpSmokeAnimBlueprintTest::GetTests(TArray<FString>& OutBeautifiedNames, TArray<FString>& OutTestCommands) const
{
	TArray<FString> Paths;
	GConfig->GetArray(TEXT("AnimGraphMcp"), TEXT("SmokeTestPaths"), Paths, GEngineIni);
	if (Paths.Num() == 0)
	{
		Paths.Add(TEXT("/Game/Animation"));
	}

	FARFilter Filter;
	Filter.ClassPaths.Add(UAnimBlueprint::StaticClass()->GetClassPathName());
	Filter.bRecursiveClasses = true;
	Filter.bRecursivePaths = true;
	for (const FString& P : Paths)
	{
		Filter.PackagePaths.Add(FName(*P.TrimStartAndEnd()));
	}
	TArray<FAssetData> Assets;
	FAssetRegistryModule::GetRegistry().GetAssets(Filter, Assets);
	Assets.Sort([](const FAssetData& A, const FAssetData& B) { return A.GetObjectPathString() < B.GetObjectPathString(); });
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

#endif // WITH_DEV_AUTOMATION_TESTS
