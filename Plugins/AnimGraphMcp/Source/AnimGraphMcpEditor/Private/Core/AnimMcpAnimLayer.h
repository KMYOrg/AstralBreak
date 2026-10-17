#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Misc/Guid.h"
#include "Templates/SubclassOf.h"

class UAnimBlueprint;
class UAnimGraphNode_LinkedAnimLayer;
class UAnimLayerInterface;
class UEdGraph;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * Linked Anim Layer 저작 (Phase 6-4b, Lyra 식 레이어 분리).
 *
 * 세 단계 — 엔진 경로:
 *  ① 인터페이스 애셋: UAnimLayerInterfaceFactory = UAnimBlueprintFactory(BPTYPE_Interface) →
 *     FKismetEditorUtilities::CreateBlueprint(UAnimLayerInterface, Package, Name, BPTYPE_Interface, UAnimBlueprint, UBlueprintGeneratedClass)
 *     (AnimBlueprintFactory.cpp:451-503, :514-517). 레이어 = UAnimationGraph 함수 그래프: CreateNewGraph(UAnimationGraph, UAnimationGraphSchema)
 *     + AddDomainSpecificGraph (BlueprintEditor.cpp:9714-9719, BlueprintEditorUtils.cpp:2418-2430 — Root 노드 자동).
 *     입력 포즈 = 레이어 그래프 안의 UAnimGraphNode_LinkedInputPose (AnimGraphDetails.cpp:285-304 "Add Input Pose"), 그룹 = Root.Node.SetGroup.
 *     컴파일하면 생성 클래스의 함수에 MD_AnimBlueprintFunction 메타가 붙는다 (AnimBlueprintCompiler.cpp:1761,:1791) — 구현 단계의 전제.
 *  ② 구현: FBlueprintEditorUtils::ImplementNewInterface(ABP, 인터페이스 클래스 경로) (BlueprintEditorUtils.cpp:6414-6510) —
 *     anim 함수마다 UAnimationGraph 를 만들고 AddInterfaceGraph → UAnimationGraphSchema::CreateFunctionGraphTerminators 가
 *     Root + 입력 포즈 노드를 함수 시그니처에서 자동 생성 (AnimationGraphSchema.cpp:423-482). ImplementedInterfaces[].Graphs 에 들어간다.
 *  ③ 노드: UAnimGraphNode_LinkedAnimLayer::SetupFromLayerId (AnimGraphNode_LinkedAnimLayer.cpp:974-1006) 재현 —
 *     Node.Layer · FunctionReference.SetSelfMember · Node.Interface(= 그 이름의 인터페이스 그래프 소유 인터페이스, 없으면 self) ·
 *     InterfaceGuid(= 그래프 InterfaceGuid) · Node.InstanceClass=null → ReconstructNode(CreateCustomPins 가 입력 포즈 핀을 만든다).
 *     SetupFromLayerId/SetLayerName 은 MinimalAPI 비내보내기·protected 라 호출 불가, FunctionReference 는 protected → 리플렉션.
 */
namespace AnimMcpAnimLayer
{
	struct FLayerParams
	{
		FString Name;
		FString Group;
		TArray<FString> InputPoses;
	};

	struct FCreateInterfaceParams
	{
		FString AssetPath;
		TArray<FLayerParams> Layers;
		bool bOverwrite = false;
	};

	bool ParseCreateInterfaceParams(const TSharedRef<FJsonObject>& Params, FCreateInterfaceParams& Out, FAnimMcpError& OutError);

	/** 인터페이스 BP 생성 + 레이어 그래프 + 입력 포즈. 컴파일은 호출자(Tool)가 한다 */
	UAnimBlueprint* CreateLayerInterface(const FCreateInterfaceParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError);

	/** 인터페이스 BP 검증 — BPTYPE_Interface · 부모 UAnimLayerInterface · 컴파일된 클래스에 anim 함수 ≥ 1 */
	bool ValidateLayerInterface(UAnimBlueprint* InterfaceBP, FAnimMcpError& OutError);

	/** 구현 — 이미 구현·그래프 이름 충돌·대상이 인터페이스면 BAD_REQUEST */
	bool ImplementInterface(UAnimBlueprint* Target, UAnimBlueprint* InterfaceBP, FAnimMcpContext& Context, FAnimMcpError& OutError);

	/** 레이어 이름 → 그래프. 인터페이스 그래프(ImplementedInterfaces[].Graphs) 우선, 그다음 자체 UAnimationGraph 함수 그래프(AnimGraph 제외). OutInterface 는 self 면 null */
	UEdGraph* FindLayerGraph(UAnimBlueprint* Blueprint, FName Layer, UClass*& OutInterface);

	bool ValidateLayerName(UAnimBlueprint* Blueprint, const FString& Layer, FAnimMcpError& OutError);

	/**
	 * 노드에 줄 수 있는 레이어인가 — 이름 존재 + **같은 ABP 의 다른 LinkedAnimLayer 노드가 쓰지 않음**
	 * (컴파일 규칙 "layers can be used only once in an animation blueprint", 실측). ExcludeNode 는 자기 자신(재지정 시)
	 */
	bool ValidateLayerAssignable(UAnimBlueprint* Blueprint, const FString& Layer, const UAnimGraphNode_LinkedAnimLayer* ExcludeNode, FAnimMcpError& OutError);

	struct FLayerRef
	{
		FName Layer;
		TSubclassOf<UAnimLayerInterface> Interface;
		FGuid Guid;
	};

	/**
	 * 노드에 레이어 설정 (SetupFromLayerId 재현). OutOld 는 롤백용.
	 * 입력 포즈 핀에 링크가 있으면 거부(PINS_LINKED) — 재구성 뒤 사라지는 핀은 고아로 남아 컴파일 오류("In use pin no longer exists", 실측)
	 */
	bool SetLinkedLayer(UAnimGraphNode_LinkedAnimLayer* Node, FName Layer, FLayerRef& OutOld, FAnimMcpError& OutError);
	void RestoreLinkedLayer(UAnimGraphNode_LinkedAnimLayer* Node, const FLayerRef& Old);

	/** 조회 — implemented_interfaces[{interface, blueprint, graphs[{name, graph_guid, interface_guid}]}] */
	TArray<TSharedPtr<FJsonValue>> DescribeImplementedInterfaces(UAnimBlueprint* Blueprint);

	/** 조회 — layers[{name, graph_guid, interface|null, interface_guid|null, group, input_poses[]}] (인터페이스 그래프 + 자체 레이어 그래프) */
	TArray<TSharedPtr<FJsonValue>> DescribeLayers(UAnimBlueprint* Blueprint);

	/** 노드 조회 — {layer, interface|null, instance_class|null} */
	TSharedRef<FJsonObject> DescribeLinkedLayerNode(const UAnimGraphNode_LinkedAnimLayer* Node);
}
