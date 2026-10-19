#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonValue.h"

class UAnimBlueprint;
class UEdGraph;
class UEdGraphNode;
class UK2Node;
struct FAnimMcpError;

/**
 * Phase 7-1 — Property Access 노드(UK2Node_PropertyAccess) 리플렉션 헬퍼.
 *
 * 노드 클래스는 엔진 플러그인 PropertyAccessNode(Engine/Plugins/Developer/PropertyAccessNode, 기본 활성, 모듈 UncookedOnly)의
 * **비공개 헤더**에 있고 MinimalAPI 라 포함·호출이 불가능하다. 그래서 클래스는 경로로 찾고(/Script/PropertyAccessNode.K2Node_PropertyAccess),
 * 경로(UPROPERTY TArray<FString> Path)는 리플렉션으로 쓰며, 핀·표시 텍스트는 AllocateDefaultPins/ReconstructNode 가
 * 경로를 해석해 만든다 (K2Node_PropertyAccess.cpp:170-217 AllocatePins — ResolvePropertyAccess → ConvertPropertyToPinType → "Value" 출력 핀).
 * 어느 그래프에 놓을 수 있는지는 IPropertyAccessBlueprintBinding::CanBindToContext 가 정하고, AnimGraph 쪽 구현은 AnimBP 의 모든 그래프를
 * 허용한다 (PropertyAccessAnimBlueprintBinding.cpp:22-30). 경로 해석은 6-4a 와 같은 IPropertyAccessEditor (SkeletonGeneratedClass 기준).
 */
namespace AnimMcpPropertyAccessNode
{
	/** 플러그인이 로드돼 있으면 클래스, 아니면 null */
	UClass* NodeClass();

	bool IsPropertyAccessNode(const UEdGraphNode* Node);

	/** "A.B" 문자열 또는 ["A","B"] 배열 → 세그먼트. 비어 있으면 BAD_REQUEST(EMPTY_PATH) */
	bool ParsePath(const TSharedPtr<FJsonValue>& Value, TArray<FString>& OutPath, FAnimMcpError& OutError);

	FString JoinPath(const TArray<FString>& Path);

	/**
	 * 경로 해석 — 잎 프로퍼티(함수면 반환값 프로퍼티) · 스레드 안전 여부 · 잎이 함수인지. 실패 시 BAD_REQUEST(PATH_UNRESOLVED).
	 * SkeletonGeneratedClass 가 없으면(컴파일 안 된 새 BP) GeneratedClass → ParentClass 순으로 본다
	 */
	bool ResolvePath(UAnimBlueprint* Blueprint, const TArray<FString>& Path, FProperty*& OutLeaf, bool& bOutThreadSafe, bool& bOutLeafIsFunction, FAnimMcpError& OutError);

	/** 노드의 Path 를 읽는다 (리플렉션). 노드가 Property Access 가 아니면 false */
	bool GetPath(const UEdGraphNode* Node, TArray<FString>& OutPath);

	/** 노드의 Path 를 쓴다 (리플렉션). 핀은 호출자가 Finalize/ReconstructNode 로 만든다 */
	bool SetPath(UEdGraphNode* Node, const TArray<FString>& Path, FAnimMcpError& OutError);

	/**
	 * 그래프에 Property Access 노드를 만들고 경로를 넣는다 (FGraphNodeCreator 경로 — Finalize 가 AllocateDefaultPins 로 경로를 해석해 "Value" 핀을 만든다).
	 * 해석 실패로 핀이 와일드카드면 노드를 지우고 실패
	 */
	UK2Node* Spawn(UEdGraph* Graph, const TArray<FString>& Path, int32 PosX, int32 PosY, FAnimMcpError& OutError);
}
