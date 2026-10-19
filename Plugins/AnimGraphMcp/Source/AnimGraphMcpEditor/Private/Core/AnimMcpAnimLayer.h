#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Engine/MemberReference.h"
#include "Misc/Guid.h"
#include "Templates/SubclassOf.h"

class UAnimBlueprint;
class UAnimGraphNode_LinkedAnimLayer;
class UAnimGraphNode_LinkedInputPose;
class UAnimInstance;
class UAnimLayerInterface;
class UEdGraph;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * Linked Anim Layer 저작 (Phase 6-4b, Lyra 식 레이어 분리 · Phase 7-4 값 파라미터·InstanceClass·레이어 추가/삭제).
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
 *
 * Phase 7-4:
 *  ④ 값 파라미터 = 레이어 그래프의 **Input Pose 노드**에 붙는 `UAnimGraphNode_LinkedInputPose::Inputs[{Name, FEdGraphPinType}]`
 *     (AnimGraphNode_LinkedInputPose.h:55). 컴파일러가 Input Pose 노드의 비-포즈 출력 핀을 함수 파라미터로 만든다(AnimBlueprintCompiler.cpp:1660-1676).
 *     변경은 `PostEditChangeProperty(Inputs)` 가 재구성·구조 변경·self 레이어 노드 재구성까지 처리(AnimGraphNode_LinkedInputPose.cpp:131-149).
 *     구현 ABP 의 Input Pose 는 스텁 함수에서 값 핀을 만들고(CreatePinsFromStubFunction :308), LinkedAnimLayer 노드는 CustomPinProperties 로
 *     값 핀을 옵션 핀으로 노출(AnimGraphNode_LinkedAnimLayer.cpp:676-726) — expose_pin 이 CustomPinProperties 도 다룬다(Mutator).
 *  ⑤ InstanceClass: Node.InstanceClass + FunctionReference.SetExternalMember(레이어, 클래스, Guid) + ReconstructNode (SetupFromLayerId :994-1001).
 *     self 레이어는 불가(:905-909). 컴파일 규칙: 자기 클래스 금지·스켈레톤 호환(AnimGraphNode_LinkedAnimGraphBase.cpp:226-238)·인터페이스 미구현 오류(:199-215).
 *  ⑥ 레이어 추가/삭제: 추가 = ①과 같은 그래프 생성; 삭제 = FBlueprintEditorUtils::RemoveGraph. 구현 ABP 는 자기 컴파일 때 ConformImplementedInterfaces
 *     (BlueprintCompilationManager.cpp:3909 → ConformInterfaceByName, BlueprintEditorUtils.cpp:7364-7427)로 동기화 — 새 레이어 그래프 생성, 사라진 레이어
 *     그래프는 이름 해제·편집 불가(내용 유실) → 도구가 참조 ABP 를 로드해 재컴파일한다(ConformImplementers).
 */
namespace AnimMcpAnimLayer
{
	/** 값 파라미터 — type 은 add_blueprint_variable 과 같은 문자열(AnimMcpVariables::ParsePinType) */
	struct FInputParam
	{
		FString Name;
		FString Type;
	};

	struct FInputPoseParams
	{
		FString Name;
		TArray<FInputParam> Inputs;
	};

	struct FLayerParams
	{
		FString Name;
		FString Group;
		TArray<FInputPoseParams> InputPoses;
	};

	struct FCreateInterfaceParams
	{
		FString AssetPath;
		TArray<FLayerParams> Layers;
		bool bOverwrite = false;
	};

	/** `layers[{name, group?, input_poses?[ "Name" | {name, inputs?[{name, type}]} ]}]` — create 와 add_anim_layers 공용 */
	bool ParseLayerList(const TArray<TSharedPtr<FJsonValue>>& Layers, TArray<FLayerParams>& Out, FAnimMcpError& OutError, const FString& Field = TEXT("layers"));

	/** `inputs[{name, type}]` — 이름 유효성·중복·타입 */
	bool ParseInputParams(const TArray<TSharedPtr<FJsonValue>>& Inputs, TArray<FInputParam>& Out, FAnimMcpError& OutError, const FString& Field);

	bool ParseCreateInterfaceParams(const TSharedRef<FJsonObject>& Params, FCreateInterfaceParams& Out, FAnimMcpError& OutError);

	/** 인터페이스 BP 생성 + 레이어 그래프 + 입력 포즈. 컴파일은 호출자(Tool)가 한다 */
	UAnimBlueprint* CreateLayerInterface(const FCreateInterfaceParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError);

	/**
	 * (7-4) 레이어 그래프 추가 — 인터페이스 BP 면 인터페이스 레이어, 일반 ABP 면 자체 레이어(FunctionGraphs).
	 * 이름 충돌(기존 그래프·AnimGraph 예약)은 DUPLICATE_NAME/RESERVED_NAME 으로 전부 선검증 뒤 생성. 호출자가 MarkBlueprintAsStructurallyModified·컴파일
	 */
	bool AddLayerGraphs(UAnimBlueprint* Blueprint, const TArray<FLayerParams>& Layers, FAnimMcpError& OutError);

	/**
	 * (7-4) 레이어 그래프 삭제 — 인터페이스 BP: 참조 ABP(AssetRegistry 참조자)를 로드해 그 레이어의 구현 그래프에 Root/InputPose 외 노드가 있거나
	 * LinkedAnimLayer 노드가 그 레이어를 쓰면 bForce 없이는 LAYER_IN_USE_BY(details.usage[]). 일반 ABP: 자기 LinkedAnimLayer 노드 사용만 검사.
	 * 통과하면 FBlueprintEditorUtils::RemoveGraph. OutUsage 는 force 로 강행했을 때도 채운다
	 */
	bool RemoveLayerGraphs(UAnimBlueprint* Blueprint, const TArray<FString>& Names, bool bForce, FAnimMcpContext& Context, FAnimMcpError& OutError, TArray<TSharedPtr<FJsonValue>>& OutUsage);

	/**
	 * (7-4) 레이어의 Input Pose 노드 Inputs 전체 교체. 편집 가능한 그래프(인터페이스 BP 의 레이어 · ABP 의 자체 레이어)만 — 구현 그래프는 NOT_EDITABLE.
	 * InputPose 가 비어 있으면 그 레이어의 유일한 Input Pose(없으면 NO_INPUT_POSE, 둘 이상이면 AMBIGUOUS_INPUT_POSE). 같은 목록이면 bOutUnchanged
	 */
	bool SetLayerInputs(UAnimBlueprint* Blueprint, const FString& Layer, const FString& InputPose, const TArray<FInputParam>& Inputs, bool& bOutUnchanged, FAnimMcpError& OutError);

	/**
	 * (7-4) 인터페이스를 바꾼 뒤 구현 ABP 동기화 — AssetRegistry 참조자 중 이 인터페이스를 구현한 ABP 를 로드해 ConformImplementedInterfaces + 컴파일.
	 * 응답 implementers[{asset_path, conformed, compile{num_errors, num_warnings}}]. 저장은 하지 않는다(더티로 남는다)
	 */
	TArray<TSharedPtr<FJsonValue>> ConformImplementers(UAnimBlueprint* InterfaceBP, FAnimMcpContext& Context);

	/** 인터페이스 BP 검증 — BPTYPE_Interface · 부모 UAnimLayerInterface · 컴파일된 클래스에 anim 함수 ≥ 1 */
	bool ValidateLayerInterface(UAnimBlueprint* InterfaceBP, FAnimMcpError& OutError);

	/** 인터페이스 BP 인가(컴파일 여부 무관) */
	bool IsLayerInterface(const UAnimBlueprint* Blueprint);

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

	/** (7-4) InstanceClass 롤백용 — 클래스 + FunctionReference 통째 */
	struct FInstanceRef
	{
		TSubclassOf<UAnimInstance> InstanceClass;
		FMemberReference FunctionReference;
	};

	/**
	 * (7-4) 인스턴스 클래스 경로 → UClass. "/Game/A/ABP_X"(AnimBP 애셋) · "/Game/A/ABP_X.ABP_X_C"(클래스) 둘 다. 거부: ASSET_NOT_FOUND · BAD_CLASS(AnimInstance 아님)
	 */
	UClass* ResolveAnimInstanceClass(const FString& Path, FAnimMcpError& OutError);

	/**
	 * (7-4) 노드에 InstanceClass 가 가능한가 — SELF_LAYER(인터페이스 레이어가 아님) · NOT_IMPLEMENTING(클래스가 노드 인터페이스를 구현하지 않음) ·
	 * SELF_CLASS(자기 ABP 클래스) · INCOMPATIBLE(스켈레톤 비호환, UAnimBlueprint::IsCompatible) · PINS_LINKED(링크된 값 핀 — 재구성 뒤 고아). Class 가 null 이면 해제
	 */
	bool ValidateInstanceClass(UAnimGraphNode_LinkedAnimLayer* Node, UClass* Class, FAnimMcpError& OutError);

	/** (7-4) InstanceClass 설정/해제(null) — 검증 뒤 Node.InstanceClass + FunctionReference(외부/self 멤버) + ReconstructNode. OutOld 는 롤백용 */
	bool SetInstanceClass(UAnimGraphNode_LinkedAnimLayer* Node, UClass* Class, FInstanceRef& OutOld, FAnimMcpError& OutError);
	void RestoreInstanceClass(UAnimGraphNode_LinkedAnimLayer* Node, const FInstanceRef& Old);

	/** 조회 — implemented_interfaces[{interface, blueprint, graphs[{name, graph_guid, interface_guid}]}] */
	TArray<TSharedPtr<FJsonValue>> DescribeImplementedInterfaces(UAnimBlueprint* Blueprint);

	/**
	 * 조회 — layers[{name, graph_guid, interface|null, interface_guid|null, group, editable, input_poses[], inputs[{name, type, input_pose}]}]
	 * (인터페이스 그래프 + 자체 레이어 그래프). (7-4) inputs 는 Input Pose 노드의 비-포즈 출력 핀(= 함수 값 파라미터)
	 */
	TArray<TSharedPtr<FJsonValue>> DescribeLayers(UAnimBlueprint* Blueprint);

	/** 노드 조회 — {layer, interface|null, instance_class|null, interface_guid} */
	TSharedRef<FJsonObject> DescribeLinkedLayerNode(const UAnimGraphNode_LinkedAnimLayer* Node);
}
