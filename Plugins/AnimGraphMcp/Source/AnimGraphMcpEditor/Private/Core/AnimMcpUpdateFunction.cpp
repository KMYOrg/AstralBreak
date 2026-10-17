#include "AnimMcpUpdateFunction.h"

#include "AnimMcpGraphMutator.h"
#include "AnimMcpLog.h"
#include "AnimMcpTransitionRule.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimInstance.h"
#include "Bridge/AnimMcpTypes.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphNode_Comment.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_FunctionEntry.h"
#include "K2Node_VariableSet.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "ScopedTransaction.h"
#include "UObject/UnrealType.h"

namespace AnimMcpUpdateFunction
{
	const TCHAR* const SourceMarker = TEXT("AnimGraphMcp update_source v1");

	namespace
	{
		FAnimMcpError Reason(const FString& Message, const TCHAR* ReasonCode, const TCHAR* Field = nullptr)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("reason"), ReasonCode);
			if (Field) { Details->SetStringField(TEXT("field"), Field); }
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
		}

		UK2Node_FunctionEntry* FindEntry(UEdGraph* Graph)
		{
			if (!Graph) { return nullptr; }
			for (UEdGraphNode* Node : Graph->Nodes)
			{
				if (UK2Node_FunctionEntry* Entry = Cast<UK2Node_FunctionEntry>(Node))
				{
					return Entry;
				}
			}
			return nullptr;
		}

		/** 함수 시그니처의 입력 파라미터 → {"param": name} 허용 목록 */
		void CollectParamTypes(AnimMcpTransitionRule::FExpressionParams& Out)
		{
			const UFunction* Function = UAnimInstance::StaticClass()->FindFunctionByName(FunctionName());
			if (!Function) { return; }
			for (TFieldIterator<FProperty> It(Function); It; ++It)
			{
				const bool bInput = It->HasAnyPropertyFlags(CPF_Parm) && !It->HasAnyPropertyFlags(CPF_ReturnParm) && !(It->HasAnyPropertyFlags(CPF_OutParm) && !It->HasAnyPropertyFlags(CPF_ReferenceParm));
				if (!bInput) { continue; }
				FEdGraphPinType Type;
				if (GetDefault<UEdGraphSchema_K2>()->ConvertPropertyToPinType(*It, Type))
				{
					Out.Types.Add(It->GetName(), Type);
				}
			}
		}

		struct FLinkSnapshot
		{
			UEdGraphPin* Pin = nullptr;
			TArray<UEdGraphPin*> Links;
		};

		void Snapshot(UEdGraphNode* Node, TArray<FLinkSnapshot>& Out)
		{
			for (UEdGraphPin* Pin : Node->Pins)
			{
				if (Pin && Pin->LinkedTo.Num() > 0)
				{
					FLinkSnapshot S;
					S.Pin = Pin;
					S.Links = Pin->LinkedTo;
					Out.Add(S);
				}
			}
		}

		void Restore(const TArray<FLinkSnapshot>& Snapshots)
		{
			for (const FLinkSnapshot& S : Snapshots)
			{
				if (!S.Pin) { continue; }
				for (UEdGraphPin* Other : S.Links)
				{
					if (Other && !S.Pin->LinkedTo.Contains(Other))
					{
						S.Pin->MakeLinkTo(Other);
					}
				}
			}
		}

		int32 CountNodes(UEdGraph* Graph)
		{
			int32 Count = 0;
			for (UEdGraphNode* Node : Graph->Nodes)
			{
				if (Node && !Node->IsA<UEdGraphNode_Comment>()) { ++Count; }
			}
			return Count;
		}

		bool ConnectExec(UEdGraph* Graph, UEdGraphPin* From, UEdGraphPin* To, FAnimMcpError& OutError)
		{
			if (!From || !To)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("update function: exec pin missing"));
				return false;
			}
			const UEdGraphSchema* Schema = Graph->GetSchema();
			const FPinConnectionResponse Response = Schema->CanCreateConnection(From, To);
			if (Response.Response == CONNECT_RESPONSE_DISALLOW || !Schema->TryCreateConnection(From, To))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::ConnectionRejected, FString::Printf(TEXT("update function: cannot chain exec %s -> %s: %s"), *From->GetOwningNode()->GetClass()->GetName(), *To->GetOwningNode()->GetClass()->GetName(), *Response.Message.ToString()));
				return false;
			}
			return true;
		}
	}

	FName FunctionName()
	{
		return GET_FUNCTION_NAME_CHECKED(UAnimInstance, BlueprintThreadSafeUpdateAnimation);
	}

	UEdGraph* FindGraph(UAnimBlueprint* Blueprint)
	{
		if (!Blueprint) { return nullptr; }
		for (UEdGraph* Graph : Blueprint->FunctionGraphs)
		{
			if (Graph && Graph->GetFName() == FunctionName())
			{
				return Graph;
			}
		}
		return nullptr;
	}

	bool ParseAndValidate(UAnimBlueprint* Blueprint, const TSharedRef<FJsonObject>& Params, TArray<FAssignment>& OutAssignments, FString& OutCanonical, FAnimMcpError& OutError)
	{
		OutAssignments.Reset();
		OutCanonical.Reset();
		const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
		if (!Params->TryGetArrayField(TEXT("assignments"), Array) || !Array)
		{
			OutError = Reason(TEXT("set_update_function requires 'assignments' (array of {variable, value}); use [] to empty the function or remove=true to delete it"), TEXT("NO_ASSIGNMENTS"), TEXT("assignments"));
			return false;
		}
		AnimMcpTransitionRule::FExpressionParams ExprParams;
		CollectParamTypes(ExprParams);
		UClass* VarClass = AnimMcpGraphMutator::VariableClassOf(Blueprint);

		TSet<FString> Seen;
		OutCanonical = TEXT("{\"assignments\":[");
		for (int32 i = 0; i < Array->Num(); ++i)
		{
			const TSharedPtr<FJsonValue>& Item = (*Array)[i];
			const TSharedPtr<FJsonObject> Obj = (Item.IsValid() && Item->Type == EJson::Object) ? Item->AsObject() : nullptr;
			FString Variable;
			if (!Obj.IsValid() || !Obj->TryGetStringField(TEXT("variable"), Variable) || !Obj->HasTypedField<EJson::Object>(TEXT("value")))
			{
				OutError = Reason(FString::Printf(TEXT("assignments[%d] must be {variable: <name>, value: <expression object>}"), i), TEXT("BAD_ASSIGNMENT"), TEXT("assignments"));
				return false;
			}
			Variable.TrimStartAndEndInline();
			if (Seen.Contains(Variable))
			{
				OutError = Reason(FString::Printf(TEXT("assignments[%d]: variable '%s' is assigned more than once"), i, *Variable), TEXT("DUPLICATE_VARIABLE"), TEXT("assignments"));
				return false;
			}
			Seen.Add(Variable);

			FProperty* Property = AnimMcpGraphMutator::ResolveVariable(Blueprint, Variable, OutError);
			if (!Property)
			{
				return false;
			}
			if (Property->HasAnyPropertyFlags(CPF_BlueprintReadOnly))
			{
				OutError = Reason(FString::Printf(TEXT("assignments[%d]: '%s' is BlueprintReadOnly (declared in C++ as read-only); assign a Blueprint variable or a BlueprintReadWrite property"), i, *Variable), TEXT("READ_ONLY"), TEXT("assignments"));
				return false;
			}
			FEdGraphPinType VarType;
			if (!GetDefault<UEdGraphSchema_K2>()->ConvertPropertyToPinType(Property, VarType))
			{
				OutError = Reason(FString::Printf(TEXT("assignments[%d]: '%s' has a type that cannot be a pin"), i, *Variable), TEXT("TYPE_INCOMPATIBLE"), TEXT("assignments"));
				return false;
			}

			FAssignment A;
			A.Variable = Variable;
			A.Value = Obj->TryGetField(TEXT("value"));
			FEdGraphPinType ValueType;
			bool bLiteral = false;
			TSharedPtr<FJsonValue> Literal;
			if (!AnimMcpTransitionRule::ValidateExpression(Blueprint, A.Value, &ExprParams, A.ValueCanonical, ValueType, bLiteral, Literal, OutError))
			{
				if (OutError.Details.IsValid()) { OutError.Details->SetNumberField(TEXT("assignment_index"), i); }
				return false;
			}
			if (bLiteral)
			{
				FString Unused;
				if (!AnimMcpTransitionRule::LiteralForPin(Literal, VarType, Unused, OutError))
				{
					return false;
				}
			}
			else if (!GetDefault<UEdGraphSchema_K2>()->ArePinTypesCompatible(ValueType, VarType))
			{
				FString ValueTypeText = ValueType.PinCategory.ToString();
				if (ValueType.PinSubCategoryObject.IsValid()) { ValueTypeText += TEXT(":") + ValueType.PinSubCategoryObject->GetName(); }
				OutError = Reason(FString::Printf(TEXT("assignments[%d]: value type %s cannot be assigned to '%s' (%s)"), i, *ValueTypeText, *Variable, *Property->GetCPPType()), TEXT("TYPE_INCOMPATIBLE"), TEXT("assignments"));
				return false;
			}
			if (i > 0) { OutCanonical += TEXT(","); }
			OutCanonical += TEXT("{\"variable\":\"") + Variable + TEXT("\",\"value\":") + A.ValueCanonical + TEXT("}");
			OutAssignments.Add(A);
		}
		OutCanonical += TEXT("]}");
		return true;
	}

	bool Apply(UAnimBlueprint* Blueprint, const TArray<FAssignment>& Assignments, const FString& Canonical, FAnimMcpContext& Context, TSharedRef<FJsonObject>& OutResult, FAnimMcpError& OutError)
	{
		if (!Blueprint)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("Apply without blueprint"));
			return false;
		}
		if (Blueprint->BlueprintType == BPTYPE_Interface)
		{
			OutError = Reason(TEXT("an Animation Layer Interface has no update function"), TEXT("NOT_ANIM_BLUEPRINT"), TEXT("asset_path"));
			return false;
		}

		FScopedTransaction Transaction(NSLOCTEXT("AnimGraphMcp", "SetUpdateFunction", "AnimGraphMcp set_update_function"));
		Blueprint->Modify();

		// 1) 그래프 — 없으면 Persona 의 Override 와 같은 경로로 만든다
		bool bCreatedGraph = false;
		UEdGraph* Graph = FindGraph(Blueprint);
		if (!Graph)
		{
			UFunction* Function = nullptr;
			UClass* OverrideClass = FBlueprintEditorUtils::GetOverrideFunctionClass(Blueprint, FunctionName(), &Function);
			if (!OverrideClass || !Function)
			{
				OverrideClass = UAnimInstance::StaticClass();
			}
			Graph = FBlueprintEditorUtils::CreateNewGraph(Blueprint, FunctionName(), UEdGraph::StaticClass(), UEdGraphSchema_K2::StaticClass());
			FBlueprintEditorUtils::AddFunctionGraph<UClass>(Blueprint, Graph, /*bIsUserCreated*/ false, OverrideClass);
			bCreatedGraph = true;
		}
		UK2Node_FunctionEntry* Entry = FindEntry(Graph);
		if (!Entry)
		{
			if (bCreatedGraph) { FBlueprintEditorUtils::RemoveGraph(Blueprint, Graph); }
			Transaction.Cancel();
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("update function graph has no FunctionEntry node"));
			return false;
		}

		// 2) 멱등
		const AnimMcpTransitionRule::FSource Existing = AnimMcpTransitionRule::ReadSource(Graph, SourceMarker);
		if (!bCreatedGraph && Existing.bHasSource && Existing.Canonical == Canonical && !Existing.bModified)
		{
			Transaction.Cancel();
			OutResult->SetStringField(TEXT("graph_guid"), Graph->GraphGuid.ToString());
			OutResult->SetBoolField(TEXT("created_graph"), false);
			OutResult->SetBoolField(TEXT("unchanged"), true);
			OutResult->SetNumberField(TEXT("node_count"), CountNodes(Graph));
			OutResult->SetNumberField(TEXT("assignment_count"), Assignments.Num());
			return true;
		}

		// 3) 기존 노드(Entry 제외) 분리 보관 + 링크 스냅샷 (Entry 핀 포함)
		Graph->Modify();
		Entry->Modify();
		TArray<UEdGraphNode*> Old;
		for (UEdGraphNode* Node : Graph->Nodes)
		{
			if (Node && Node != Entry) { Old.Add(Node); }
		}
		TArray<FLinkSnapshot> Snapshots;
		Snapshot(Entry, Snapshots);
		for (UEdGraphNode* Node : Old)
		{
			Snapshot(Node, Snapshots);
			AnimMcpGraphMutator::DetachNode(Node);
		}

		// 4) 재생성
		TArray<UEdGraphNode*> Created;
		auto Rollback = [&]()
		{
			for (int32 i = Created.Num() - 1; i >= 0; --i)
			{
				AnimMcpGraphMutator::DestroyNodeQuietly(Created[i]);
			}
			for (UEdGraphNode* Node : Old)
			{
				AnimMcpGraphMutator::ReattachNode(Graph, Node);
			}
			Restore(Snapshots);
			if (bCreatedGraph)
			{
				FBlueprintEditorUtils::RemoveGraph(Blueprint, Graph);
			}
			Transaction.Cancel();
		};

		UClass* VarClass = AnimMcpGraphMutator::VariableClassOf(Blueprint);
		TMap<FString, UEdGraphPin*> ParamPins;
		for (UEdGraphPin* Pin : Entry->Pins)
		{
			if (Pin && Pin->Direction == EGPD_Output && Pin->PinType.PinCategory != UEdGraphSchema_K2::PC_Exec)
			{
				ParamPins.Add(Pin->PinName.ToString(), Pin);
			}
		}
		UEdGraphPin* PrevThen = Entry->FindPin(UEdGraphSchema_K2::PN_Then, EGPD_Output);
		int32 CursorY = Entry->NodePosY;
		int32 MaxDepth = 0;
		for (const FAssignment& A : Assignments)
		{
			FProperty* Property = AnimMcpGraphMutator::ResolveVariable(Blueprint, A.Variable, OutError);
			if (!Property) { Rollback(); return false; }

			FGraphNodeCreator<UK2Node_VariableSet> Creator(*Graph);
			UK2Node_VariableSet* Set = Creator.CreateNode(/*bSelectNewNode*/ false);
			Set->SetFromProperty(Property, /*bSelfContext*/ true, VarClass);
			Set->NodePosX = 0;
			Set->NodePosY = CursorY;
			Creator.Finalize();
			Created.Add(Set);

			if (!ConnectExec(Graph, PrevThen, Set->FindPin(UEdGraphSchema_K2::PN_Execute, EGPD_Input), OutError)) { Rollback(); return false; }
			UEdGraphPin* ValuePin = Set->FindPin(Property->GetFName(), EGPD_Input);
			if (!ValuePin)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("VariableSet for '%s' has no input value pin"), *A.Variable));
				Rollback();
				return false;
			}
			AnimMcpTransitionRule::FExpressionBuild Target;
			Target.Graph = Graph;
			Target.OriginX = 0;
			Target.OriginY = CursorY;
			Target.ParamPins = &ParamPins;
			Target.Created = &Created;
			if (!AnimMcpTransitionRule::BuildExpressionInto(Blueprint, Target, A.Value, ValuePin, OutError)) { Rollback(); return false; }
			MaxDepth = FMath::Max(MaxDepth, Target.MaxDepth);
			CursorY += FMath::Max(Target.RowsUsed, 1) * 140 + 80;
			PrevThen = Set->FindPin(UEdGraphSchema_K2::PN_Then, EGPD_Output);
		}

		// 5) 배치 — 식 트리가 Entry 오른쪽에 오도록 전부 밀어 놓는다 (식은 Set 의 왼쪽 360*(depth+1) 에 있다)
		const int32 ShiftX = Entry->NodePosX + 360 * (MaxDepth + 1) + 420;
		for (UEdGraphNode* Node : Created)
		{
			Node->NodePosX += ShiftX;
		}

		// 6) 원문 + 해시 주석
		{
			const FString Hash = AnimMcpTransitionRule::HashRuleGraph(Graph);
			FGraphNodeCreator<UEdGraphNode_Comment> CommentCreator(*Graph);
			UEdGraphNode_Comment* Comment = CommentCreator.CreateNode(/*bSelectNewNode*/ false);
			Comment->NodePosX = Entry->NodePosX - 40;
			Comment->NodePosY = Entry->NodePosY - 260;
			Comment->NodeWidth = ShiftX + 520;
			Comment->NodeHeight = 120;
			CommentCreator.Finalize();
			Comment->Modify();
			Comment->NodeComment = FString::Printf(TEXT("%s\n%s\n%s"), SourceMarker, *Hash, *Canonical);
			Comment->CommentColor = FLinearColor(0.2f, 0.65f, 0.45f, 1.f);
			Created.Add(Comment);
		}

		// 7) 분리 보관한 옛 노드 확정 삭제
		for (UEdGraphNode* Node : Old)
		{
			AnimMcpGraphMutator::FinalizeRemoval(Node);
		}
		FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

		OutResult->SetStringField(TEXT("graph_guid"), Graph->GraphGuid.ToString());
		OutResult->SetBoolField(TEXT("created_graph"), bCreatedGraph);
		OutResult->SetBoolField(TEXT("unchanged"), false);
		OutResult->SetNumberField(TEXT("node_count"), CountNodes(Graph));
		OutResult->SetNumberField(TEXT("assignment_count"), Assignments.Num());
		UE_LOG(LogAnimGraphMcp, Log, TEXT("set_update_function on %s: %d assignments, %d nodes (graph %s)"), *Blueprint->GetPathName(), Assignments.Num(), CountNodes(Graph), bCreatedGraph ? TEXT("created") : TEXT("regenerated"));
		return true;
	}

	bool Remove(UAnimBlueprint* Blueprint, FAnimMcpError& OutError)
	{
		UEdGraph* Graph = FindGraph(Blueprint);
		if (!Graph)
		{
			OutError = Reason(TEXT("this Animation Blueprint has no BlueprintThreadSafeUpdateAnimation override to remove"), TEXT("NO_UPDATE_FUNCTION"));
			return false;
		}
		FScopedTransaction Transaction(NSLOCTEXT("AnimGraphMcp", "RemoveUpdateFunction", "AnimGraphMcp set_update_function remove"));
		Blueprint->Modify();
		FBlueprintEditorUtils::RemoveGraph(Blueprint, Graph);
		UE_LOG(LogAnimGraphMcp, Log, TEXT("Removed update function graph from %s"), *Blueprint->GetPathName());
		return true;
	}

	TSharedPtr<FJsonValue> Describe(UAnimBlueprint* Blueprint)
	{
		UEdGraph* Graph = FindGraph(Blueprint);
		if (!Graph)
		{
			return MakeShared<FJsonValueNull>();
		}
		const AnimMcpTransitionRule::FSource Source = AnimMcpTransitionRule::ReadSource(Graph, SourceMarker);
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetStringField(TEXT("graph_guid"), Graph->GraphGuid.ToString());
		Obj->SetStringField(TEXT("function"), FunctionName().ToString());
		Obj->SetBoolField(TEXT("generated"), Source.bHasSource);
		TSharedPtr<FJsonValue> SourceValue = Source.Source.IsValid() ? TSharedPtr<FJsonValue>(MakeShared<FJsonValueObject>(Source.Source)) : TSharedPtr<FJsonValue>(MakeShared<FJsonValueNull>());
		Obj->SetField(TEXT("source"), SourceValue);
		Obj->SetBoolField(TEXT("modified"), Source.bHasSource && Source.bModified);
		Obj->SetNumberField(TEXT("node_count"), CountNodes(Graph));
		TArray<TSharedPtr<FJsonValue>> Assignments;
		if (Source.Source.IsValid())
		{
			const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
			if (Source.Source->TryGetArrayField(TEXT("assignments"), Array) && Array)
			{
				Assignments = *Array;
			}
		}
		Obj->SetArrayField(TEXT("assignments"), Assignments);
		return MakeShared<FJsonValueObject>(Obj);
	}
}
