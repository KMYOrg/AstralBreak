#include "AnimMcpStateTreeOperations.h"

#include "AnimMcpLog.h"
#include "AnimMcpPropertyRules.h"
#include "AnimMcpStateTreeAsset.h"
#include "AnimMcpStateTreeBindings.h"
#include "Bridge/AnimMcpTypes.h"
#include "GameplayTagContainer.h"
#include "PropertyBindingBinding.h"
#include "PropertyBindingBindingCollection.h"
#include "ScopedTransaction.h"
#include "StateTree.h"
#include "StateTreeConditionBase.h"
#include "StateTreeEditorData.h"
#include "StateTreeEditorPropertyBindings.h"
#include "StateTreeEvaluatorBase.h"
#include "StateTreeNodeBase.h"
#include "StateTreePropertyBindings.h"
#include "StateTreePropertyFunctionBase.h"
#include "StateTreeSchema.h"
#include "StateTreeState.h"
#include "StateTreeTaskBase.h"
#include "StateTreeTypes.h"
#include "StructUtils/InstancedStruct.h"
#include "UObject/Package.h"
#include "UObject/StructOnScope.h"
#include "UObject/UnrealType.h"

#define LOCTEXT_NAMESPACE "AnimGraphMcpStateTree"

namespace AnimMcpStateTreeOperations
{
	namespace
	{
		enum class ENodeKind : uint8
		{
			Task,
			EnterCondition,
			TransitionCondition,
			Consideration,
			Evaluator,
			GlobalTask,
			Function,
		};

		enum class ERefKind : uint8
		{
			State,
			Node,
			Transition,
		};

		struct FRefEntry
		{
			ERefKind Kind = ERefKind::Node;
			FGuid Id;
		};

		// ─── 기존 트리의 그림자 — op 순서대로 갱신해 뒤 op 가 앞 op 의 결과를 보게 한다. 실제 데이터는 건드리지 않는다

		struct FShadowState
		{
			FGuid Id;
			FName Name;
			FGuid Parent;
			TArray<FGuid> Children;
			/** 이 상태의 파라미터 · 이벤트 구조체 — 바인딩 소스가 될 수 있다 */
			TArray<FGuid> SourceIds;
		};

		struct FShadowNode
		{
			FGuid Id;
			FName Name;
			ENodeKind Kind = ENodeKind::Task;
			FGuid OwnerState;
			FGuid OwnerTransition;
			const UScriptStruct* NodeStruct = nullptr;
			const UStruct* InstanceStruct = nullptr;
			/** 이 배치가 만드는 노드 — 데이터가 아직 없다 */
			bool bPlanned = false;
			bool bBlueprintInstance = false;
		};

		struct FShadowTransition
		{
			FGuid Id;
			FGuid OwnerState;
			FGuid TargetState;
			FGuid EventId;
		};

		struct FShadowBinding
		{
			FGuid SourceId;
			FGuid TargetId;
			FString TargetPath;
			FGuid FunctionId;
		};

		// ─── 실행 단계

		struct FApplyContext
		{
			UStateTreeEditorData* Data = nullptr;
			TSet<const UObject*> Touched;
			/** 계획 GUID → 엔진이 만든 함수 노드 GUID. AddFunctionBinding 만 GUID 를 미리 정할 수 없다 */
			TMap<FGuid, FGuid> FunctionIds;

			/**
			 * 첫 변경 직전에만 Modify — 변경 없이 끝나면 패키지를 더티로 만들지 않는다.
			 * EditorData 는 무엇을 바꾸든 항상 함께 Modify 한다: 컴파일의 조용한 삭제(ValidateStateTree)는 이 스냅샷으로만 Undo 된다(E5e A)
			 */
			void Touch(UObject* Object)
			{
				if (!Touched.Contains(Data))
				{
					Data->Modify();
					Touched.Add(Data);
				}
				if (Object && !Touched.Contains(Object))
				{
					Object->Modify();
					Touched.Add(Object);
				}
			}

			FGuid Resolve(const FGuid& Id) const
			{
				const FGuid* Found = FunctionIds.Find(Id);
				return Found ? *Found : Id;
			}
		};

		using FStep = TFunction<bool(FApplyContext&, FAnimMcpError&)>;

		struct FPlannedStep
		{
			int32 Index = INDEX_NONE;
			FStep Run;
		};

		struct FParsedValue
		{
			FName Property;
			FString Text;
			bool bOnNodeStruct = false;
		};

		struct FPlan
		{
			const UStateTreeEditorData* Data = nullptr;
			const UStateTreeSchema* Schema = nullptr;
			FGuid RootStateId;
			TMap<FGuid, FShadowState> States;
			TMap<FGuid, FShadowNode> Nodes;
			TMap<FGuid, FShadowTransition> Transitions;
			TArray<FShadowBinding> Bindings;
			/** 앞 op 가 지운 ID — GUID 로 다시 가리키면 찾지 못한 것으로 친다 */
			TSet<FGuid> RemovedIds;
			TMap<FString, FRefEntry> Refs;
			TArray<FPlannedStep> Steps;
			/** 현재 op 에서 계획 단계가 판정하지 못한 것 — Preview 응답의 deferred */
			TArray<FString> Deferred;
		};

		// ─── JSON · 이름 해석

		FAnimMcpError BadRequest(const FString& Message)
		{
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message);
		}

		bool RequireString(const FOperation& Op, const TCHAR* Key, FString& Out, FAnimMcpError& OutError)
		{
			if (!Op.Json->TryGetStringField(Key, Out) || Out.IsEmpty())
			{
				OutError = BadRequest(FString::Printf(TEXT("%s requires '%s'"), *Op.Op, Key));
				return false;
			}
			return true;
		}

		template <typename TEnum>
		bool ParseEnum(const FString& Text, const TCHAR* Field, TEnum& Out, FAnimMcpError& OutError)
		{
			const UEnum* Enum = StaticEnum<TEnum>();
			const int64 Value = Enum->GetValueByNameString(Text);
			if (Value == INDEX_NONE)
			{
				OutError = BadRequest(FString::Printf(TEXT("'%s' is not a %s value for '%s'"), *Text, *Enum->GetName(), Field));
				return false;
			}
			Out = static_cast<TEnum>(Value);
			return true;
		}

		bool ParseTag(const FString& Text, FGameplayTag& Out, FAnimMcpError& OutError)
		{
			Out = FGameplayTag::RequestGameplayTag(FName(*Text), /*ErrorIfNotFound*/ false);
			if (!Out.IsValid())
			{
				OutError = BadRequest(FString::Printf(TEXT("Gameplay tag '%s' is not registered"), *Text));
				return false;
			}
			return true;
		}

		/** 전체 경로만 받는다 — 짧은 이름으로 전역 검색하지 않는다 */
		const UScriptStruct* FindStructByPath(const FString& Path)
		{
			if (!Path.StartsWith(TEXT("/")) || !Path.Contains(TEXT(".")))
			{
				return nullptr;
			}
			return FindObject<UScriptStruct>(nullptr, *Path);
		}

		const UStruct* GetInstanceStructOf(const UScriptStruct* NodeStruct)
		{
			FInstancedStruct Temp;
			Temp.InitializeAs(NodeStruct);
			return Temp.Get<FStateTreeNodeBase>().GetInstanceDataType();
		}

		template <typename TMapType>
		bool ResolveByNameOrGuid(const FPlan& Plan, const TMapType& Map, const ERefKind Kind, const FString& Text, const TCHAR* NotFoundCode, const TCHAR* What, FGuid& OutId, FAnimMcpError& OutError)
		{
			if (const FRefEntry* Ref = Plan.Refs.Find(Text))
			{
				if (Ref->Kind == Kind)
				{
					OutId = Ref->Id;
					return true;
				}
				OutError = BadRequest(FString::Printf(TEXT("ref '%s' is not a %s"), *Text, What));
				return false;
			}
			FGuid Parsed;
			if (FGuid::Parse(Text, Parsed))
			{
				if (Map.Contains(Parsed))
				{
					OutId = Parsed;
					return true;
				}
				OutError = FAnimMcpError::Make(NotFoundCode, FString::Printf(TEXT("%s %s not found"), What, *Text));
				return false;
			}
			TArray<FGuid> Matches;
			for (const auto& Pair : Map)
			{
				if (Pair.Value.Name.ToString() == Text)
				{
					Matches.Add(Pair.Key);
				}
			}
			if (Matches.Num() == 1)
			{
				OutId = Matches[0];
				return true;
			}
			if (Matches.IsEmpty())
			{
				OutError = FAnimMcpError::Make(NotFoundCode, FString::Printf(TEXT("%s '%s' not found"), What, *Text));
				return false;
			}
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			TArray<TSharedPtr<FJsonValue>> Candidates;
			for (const FGuid& Id : Matches)
			{
				Candidates.Add(MakeShared<FJsonValueString>(Id.ToString()));
			}
			Details->SetArrayField(TEXT("candidates"), Candidates);
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AmbiguousName, FString::Printf(TEXT("%d %ss are named '%s' — use the GUID"), Matches.Num(), What, *Text), Details);
			return false;
		}

		bool ResolveState(const FPlan& Plan, const FString& Text, FGuid& OutId, FAnimMcpError& OutError)
		{
			return ResolveByNameOrGuid(Plan, Plan.States, ERefKind::State, Text, AnimMcpErrorCodes::StateNotFound, TEXT("state"), OutId, OutError);
		}

		bool ResolveNode(const FPlan& Plan, const FString& Text, FGuid& OutId, FAnimMcpError& OutError)
		{
			return ResolveByNameOrGuid(Plan, Plan.Nodes, ERefKind::Node, Text, AnimMcpErrorCodes::NodeNotFound, TEXT("node"), OutId, OutError);
		}

		// ─── 그림자 구성

		void AddShadowNodes(FPlan& Plan, const TArray<FStateTreeEditorNode>& Nodes, const ENodeKind Kind, const FGuid& OwnerState, const FGuid& OwnerTransition)
		{
			for (const FStateTreeEditorNode& Node : Nodes)
			{
				FShadowNode Shadow;
				Shadow.Id = Node.ID;
				Shadow.Name = Node.GetName();
				Shadow.Kind = Kind;
				Shadow.OwnerState = OwnerState;
				Shadow.OwnerTransition = OwnerTransition;
				Shadow.NodeStruct = Node.Node.GetScriptStruct();
				Shadow.InstanceStruct = Node.GetInstance().GetStruct();
				Shadow.bBlueprintInstance = Node.InstanceObject != nullptr;
				Plan.Nodes.Add(Shadow.Id, Shadow);
			}
		}

		void BuildShadow(const UStateTreeEditorData& Data, FPlan& Plan)
		{
			Plan.Data = &Data;
			Plan.Schema = Data.Schema;
			AddShadowNodes(Plan, Data.Evaluators, ENodeKind::Evaluator, FGuid(), FGuid());
			AddShadowNodes(Plan, Data.GlobalTasks, ENodeKind::GlobalTask, FGuid(), FGuid());
			if (Data.SubTrees.Num() > 0 && Data.SubTrees[0])
			{
				Plan.RootStateId = Data.SubTrees[0]->ID;
			}

			Data.VisitHierarchy([&Plan](UStateTreeState& State, UStateTreeState* Parent)
			{
				FShadowState Shadow;
				Shadow.Id = State.ID;
				Shadow.Name = State.Name;
				Shadow.Parent = Parent ? Parent->ID : FGuid();
				Shadow.SourceIds = { State.Parameters.ID, State.GetEventID() };
				for (const UStateTreeState* Child : State.Children)
				{
					if (Child)
					{
						Shadow.Children.Add(Child->ID);
					}
				}
				Plan.States.Add(Shadow.Id, Shadow);

				AddShadowNodes(Plan, State.EnterConditions, ENodeKind::EnterCondition, State.ID, FGuid());
				AddShadowNodes(Plan, State.Tasks, ENodeKind::Task, State.ID, FGuid());
				AddShadowNodes(Plan, State.Considerations, ENodeKind::Consideration, State.ID, FGuid());
				for (const FStateTreeTransition& Transition : State.Transitions)
				{
					FShadowTransition ShadowTransition;
					ShadowTransition.Id = Transition.ID;
					ShadowTransition.OwnerState = State.ID;
					ShadowTransition.TargetState = Transition.State.LinkType == EStateTreeTransitionType::GotoState ? Transition.State.ID : FGuid();
					ShadowTransition.EventId = Transition.GetEventID();
					Plan.Transitions.Add(ShadowTransition.Id, ShadowTransition);
					AddShadowNodes(Plan, Transition.Conditions, ENodeKind::TransitionCondition, State.ID, Transition.ID);
				}
				return EStateTreeVisitor::Continue;
			});

			Data.GetPropertyEditorBindings()->ForEachBinding([&Plan](const FPropertyBindingBinding& Binding)
			{
				FShadowBinding Shadow;
				Shadow.SourceId = Binding.GetSourcePath().GetStructID();
				Shadow.TargetId = Binding.GetTargetPath().GetStructID();
				Shadow.TargetPath = Binding.GetTargetPath().ToString();
				if (const FStateTreeEditorNode* Function = Binding.GetPropertyFunctionNode().GetPtr<const FStateTreeEditorNode>())
				{
					Shadow.FunctionId = Function->ID;
					FShadowNode Node;
					Node.Id = Function->ID;
					Node.Name = FName(*Function->Node.GetScriptStruct()->GetDisplayNameText().ToString());
					Node.Kind = ENodeKind::Function;
					Node.NodeStruct = Function->Node.GetScriptStruct();
					Node.InstanceStruct = Function->GetInstance().GetStruct();
					Plan.Nodes.Add(Node.Id, Node);
				}
				Plan.Bindings.Add(Shadow);
			});
		}

		// ─── 값

		/** op 의 values — 인스턴스 데이터에서 먼저 찾고 없으면 노드 구조체(거리 조건의 Operator 등). 임시 메모리에 시험 입력해 값까지 검증한다 */
		bool ParseValues(const TSharedPtr<FJsonObject>& Values, const UScriptStruct* NodeStruct, const UStruct* InstanceStruct, TArray<FParsedValue>& Out, FAnimMcpError& OutError)
		{
			if (!Values.IsValid())
			{
				return true;
			}
			if (InstanceStruct && !Cast<UScriptStruct>(InstanceStruct))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, TEXT("This node keeps its data in a Blueprint object — values cannot be set by this tool"));
				return false;
			}

			FStructOnScope InstanceProbe(InstanceStruct);
			FStructOnScope NodeProbe(NodeStruct);
			for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : Values->Values)
			{
				const FName Name(*Pair.Key);
				const FProperty* Property = InstanceStruct ? InstanceStruct->FindPropertyByName(Name) : nullptr;
				const bool bOnNodeStruct = Property == nullptr;
				if (bOnNodeStruct)
				{
					Property = NodeStruct->FindPropertyByName(Name);
				}
				if (!Property || !Property->HasAnyPropertyFlags(CPF_Edit))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, FString::Printf(TEXT("'%s' is not an editable property of %s"), *Pair.Key, *GetNameSafe(NodeStruct)));
					return false;
				}
				if (!bOnNodeStruct)
				{
					const EStateTreePropertyUsage Usage = UE::StateTree::GetUsageFromMetaData(Property);
					if (Usage == EStateTreePropertyUsage::Context || Usage == EStateTreePropertyUsage::Output)
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, FString::Printf(TEXT("'%s' is a Context or Output property and cannot be set"), *Pair.Key));
						return false;
					}
				}

				FParsedValue Parsed;
				Parsed.Property = Name;
				Parsed.bOnNodeStruct = bOnNodeStruct;
				if (!AnimMcpPropertyRules::JsonToImportText(Property, Pair.Value, Parsed.Text, OutError))
				{
					return false;
				}
				uint8* Probe = bOnNodeStruct ? NodeProbe.GetStructMemory() : InstanceProbe.GetStructMemory();
				if (!Property->ImportText_Direct(*Parsed.Text, Property->ContainerPtrToValuePtr<void>(Probe), nullptr, PPF_None, GLog))
				{
					OutError = BadRequest(FString::Printf(TEXT("'%s' rejected value '%s' (type %s)"), *Pair.Key, *Parsed.Text, *Property->GetCPPType()));
					return false;
				}
				Out.Add(MoveTemp(Parsed));
			}
			return true;
		}

		void ApplyValues(FStateTreeEditorNode& Node, const TArray<FParsedValue>& Values)
		{
			for (const FParsedValue& Value : Values)
			{
				const UStruct* Struct = Value.bOnNodeStruct ? Node.Node.GetScriptStruct() : Node.Instance.GetScriptStruct();
				uint8* Memory = Value.bOnNodeStruct ? Node.Node.GetMutableMemory() : Node.Instance.GetMutableMemory();
				if (const FProperty* Property = Struct ? Struct->FindPropertyByName(Value.Property) : nullptr)
				{
					Property->ImportText_Direct(*Value.Text, Property->ContainerPtrToValuePtr<void>(Memory), nullptr, PPF_None, GLog);
				}
			}
		}

		/** §2-3 절차. Private 의 EditorNodeUtils::SetNodeTypeStruct 대신 공개 템플릿 AddTask<T> 의 내용을 옮겼다 */
		void InitNode(FStateTreeEditorNode& Node, const FGuid& Id, const UScriptStruct* Struct, UObject* Outer)
		{
			Node.ID = Id;
			Node.Node.InitializeAs(Struct);
			const FStateTreeNodeBase& Base = Node.Node.Get<FStateTreeNodeBase>();
			if (const UScriptStruct* InstanceStruct = Cast<const UScriptStruct>(Base.GetInstanceDataType()))
			{
				Node.Instance.InitializeAs(InstanceStruct);
			}
			else if (const UClass* InstanceClass = Cast<const UClass>(Base.GetInstanceDataType()))
			{
				Node.InstanceObject = NewObject<UObject>(Outer, InstanceClass);
			}
			if (const UScriptStruct* RuntimeStruct = Cast<const UScriptStruct>(Base.GetExecutionRuntimeDataType()))
			{
				Node.ExecutionRuntimeData.InitializeAs(RuntimeStruct);
			}
			else if (const UClass* RuntimeClass = Cast<const UClass>(Base.GetExecutionRuntimeDataType()))
			{
				Node.ExecutionRuntimeDataObject = NewObject<UObject>(Outer, RuntimeClass);
			}
		}

		// ─── 실행 단계에서 노드 · 바인딩 찾기

		struct FNodeSlot
		{
			TArray<FStateTreeEditorNode>* Array = nullptr;
			int32 Index = INDEX_NONE;
			UObject* Owner = nullptr;

			bool IsValid() const { return Array != nullptr; }
			FStateTreeEditorNode& Get() const { return (*Array)[Index]; }
		};

		bool FindInArray(TArray<FStateTreeEditorNode>& Array, const FGuid& Id, UObject* Owner, FNodeSlot& Out)
		{
			for (int32 Index = 0; Index < Array.Num(); ++Index)
			{
				if (Array[Index].ID == Id)
				{
					Out.Array = &Array;
					Out.Index = Index;
					Out.Owner = Owner;
					return true;
				}
			}
			return false;
		}

		FNodeSlot FindNodeSlot(UStateTreeEditorData& Data, const FGuid& Id)
		{
			FNodeSlot Slot;
			if (FindInArray(Data.Evaluators, Id, &Data, Slot) || FindInArray(Data.GlobalTasks, Id, &Data, Slot))
			{
				return Slot;
			}
			Data.VisitHierarchy([&Slot, &Id](UStateTreeState& State, UStateTreeState* /*Parent*/)
			{
				if (FindInArray(State.EnterConditions, Id, &State, Slot) || FindInArray(State.Tasks, Id, &State, Slot) || FindInArray(State.Considerations, Id, &State, Slot))
				{
					return EStateTreeVisitor::Break;
				}
				for (FStateTreeTransition& Transition : State.Transitions)
				{
					if (FindInArray(Transition.Conditions, Id, &State, Slot))
					{
						return EStateTreeVisitor::Break;
					}
				}
				return EStateTreeVisitor::Continue;
			});
			return Slot;
		}

		/** 조건에 맞는 바인딩을 지운다. 함수 바인딩이면 그 함수 노드로 들어가는 입력 바인딩까지 — 남겨 두면 컴파일이 조용히 지워 fixups 가 된다 */
		void RemoveBindingsWhere(UStateTreeEditorData& Data, TFunctionRef<bool(const FPropertyBindingBinding&)> Match)
		{
			FPropertyBindingBindingCollection& Collection = Data.EditorBindings;
			TArray<FGuid> Functions;
			Collection.ForEachBinding([&Functions, &Match](const FPropertyBindingBinding& Binding)
			{
				if (Match(Binding))
				{
					if (const FStateTreeEditorNode* Function = Binding.GetPropertyFunctionNode().GetPtr<const FStateTreeEditorNode>())
					{
						Functions.Add(Function->ID);
					}
				}
			});
			Collection.RemoveBindings([&Match](FPropertyBindingBinding& Binding) { return Match(Binding); });
			for (const FGuid& Function : Functions)
			{
				RemoveBindingsWhere(Data, [&Function](const FPropertyBindingBinding& Binding)
				{
					return Binding.GetTargetPath().GetStructID() == Function;
				});
			}
		}

		void RemoveBindingAtTarget(UStateTreeEditorData& Data, const FGuid& TargetId, const FString& TargetPath)
		{
			RemoveBindingsWhere(Data, [&TargetId, &TargetPath](const FPropertyBindingBinding& Binding)
			{
				return Binding.GetTargetPath().GetStructID() == TargetId && Binding.GetTargetPath().ToString() == TargetPath;
			});
		}

		// ─── 삭제 계획

		struct FRemoval
		{
			TSet<FGuid> States;
			TSet<FGuid> Nodes;
			TSet<FGuid> Functions;
			TSet<FGuid> Transitions;
			/** 다른 곳의 소스가 될 수 있는 ID — 노드 · 함수 · 상태 파라미터 · 이벤트 */
			TSet<FGuid> Sources;
		};

		void AddTransitionToRemoval(const FPlan& Plan, const FGuid& TransitionId, FRemoval& Removal)
		{
			Removal.Transitions.Add(TransitionId);
			if (const FShadowTransition* Transition = Plan.Transitions.Find(TransitionId))
			{
				if (Transition->EventId.IsValid())
				{
					Removal.Sources.Add(Transition->EventId);
				}
			}
			for (const TPair<FGuid, FShadowNode>& Pair : Plan.Nodes)
			{
				if (Pair.Value.OwnerTransition == TransitionId)
				{
					Removal.Nodes.Add(Pair.Key);
				}
			}
		}

		void AddStateToRemoval(const FPlan& Plan, const FGuid& StateId, FRemoval& Removal)
		{
			Removal.States.Add(StateId);
			const FShadowState* State = Plan.States.Find(StateId);
			if (!State)
			{
				return;
			}
			Removal.Sources.Append(State->SourceIds);
			for (const TPair<FGuid, FShadowNode>& Pair : Plan.Nodes)
			{
				if (Pair.Value.OwnerState == StateId && !Pair.Value.OwnerTransition.IsValid())
				{
					Removal.Nodes.Add(Pair.Key);
				}
			}
			for (const TPair<FGuid, FShadowTransition>& Pair : Plan.Transitions)
			{
				if (Pair.Value.OwnerState == StateId)
				{
					AddTransitionToRemoval(Plan, Pair.Key, Removal);
				}
			}
			for (const FGuid& Child : State->Children)
			{
				AddStateToRemoval(Plan, Child, Removal);
			}
		}

		/** 지워지는 노드에 묶인 함수 노드를 끝까지 따라간다 */
		void ExpandFunctions(const FPlan& Plan, FRemoval& Removal)
		{
			bool bGrew = true;
			while (bGrew)
			{
				bGrew = false;
				for (const FShadowBinding& Binding : Plan.Bindings)
				{
					const bool bTargetGoes = Removal.Nodes.Contains(Binding.TargetId) || Removal.Functions.Contains(Binding.TargetId);
					if (bTargetGoes && Binding.FunctionId.IsValid() && !Removal.Functions.Contains(Binding.FunctionId))
					{
						Removal.Functions.Add(Binding.FunctionId);
						bGrew = true;
					}
				}
			}
			Removal.Sources.Append(Removal.Nodes);
			Removal.Sources.Append(Removal.Functions);
		}

		TArray<const FShadowBinding*> FindExternalBindings(const FPlan& Plan, const FRemoval& Removal)
		{
			TArray<const FShadowBinding*> Out;
			for (const FShadowBinding& Binding : Plan.Bindings)
			{
				const bool bSourceGoes = Removal.Sources.Contains(Binding.SourceId);
				const bool bTargetStays = !Removal.Nodes.Contains(Binding.TargetId) && !Removal.Functions.Contains(Binding.TargetId);
				if (bSourceGoes && bTargetStays)
				{
					Out.Add(&Binding);
				}
			}
			return Out;
		}

		TArray<FGuid> FindExternalTransitions(const FPlan& Plan, const FRemoval& Removal)
		{
			TArray<FGuid> Out;
			for (const TPair<FGuid, FShadowTransition>& Pair : Plan.Transitions)
			{
				if (Removal.States.Contains(Pair.Value.TargetState) && !Removal.States.Contains(Pair.Value.OwnerState))
				{
					Out.Add(Pair.Key);
				}
			}
			return Out;
		}

		FAnimMcpError MakeReferenced(const FString& Message, const TArray<const FShadowBinding*>& Bindings, const TArray<FGuid>& Transitions)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			TArray<TSharedPtr<FJsonValue>> BindingList;
			for (const FShadowBinding* Binding : Bindings)
			{
				BindingList.Add(MakeShared<FJsonValueString>(Binding->TargetId.ToString() + TEXT(":") + Binding->TargetPath));
			}
			TArray<TSharedPtr<FJsonValue>> TransitionList;
			for (const FGuid& Id : Transitions)
			{
				TransitionList.Add(MakeShared<FJsonValueString>(Id.ToString()));
			}
			Details->SetArrayField(TEXT("bindings"), BindingList);
			Details->SetArrayField(TEXT("transitions"), TransitionList);
			return FAnimMcpError::Make(AnimMcpErrorCodes::NodeReferenced, Message, Details);
		}

		/** 그림자에서 지우고, 같은 일을 할 실행 단계를 만든다 */
		void CommitRemoval(FPlan& Plan, const int32 OpIndex, const FRemoval& Removal)
		{
			Plan.RemovedIds.Append(Removal.States);
			Plan.RemovedIds.Append(Removal.Nodes);
			Plan.RemovedIds.Append(Removal.Functions);
			Plan.RemovedIds.Append(Removal.Transitions);

			for (const FGuid& Id : Removal.States)
			{
				if (const FShadowState* State = Plan.States.Find(Id))
				{
					if (FShadowState* Parent = Plan.States.Find(State->Parent))
					{
						Parent->Children.Remove(Id);
					}
				}
				Plan.States.Remove(Id);
			}
			for (const FGuid& Id : Removal.Nodes) { Plan.Nodes.Remove(Id); }
			for (const FGuid& Id : Removal.Functions) { Plan.Nodes.Remove(Id); }
			for (const FGuid& Id : Removal.Transitions) { Plan.Transitions.Remove(Id); }
			Plan.Bindings.RemoveAll([&Removal](const FShadowBinding& Binding)
			{
				return Removal.Sources.Contains(Binding.SourceId) || Removal.Nodes.Contains(Binding.TargetId) || Removal.Functions.Contains(Binding.TargetId);
			});

			FPlannedStep Step;
			Step.Index = OpIndex;
			Step.Run = [Removal](FApplyContext& Ctx, FAnimMcpError& OutError) -> bool
			{
				UStateTreeEditorData& Data = *Ctx.Data;
				Ctx.Touch(&Data);

				// 1) 바인딩 — 대상이 지워지는 것, 소스가 지워지는 것(cascade)
				TSet<FGuid> Targets;
				TSet<FGuid> Sources;
				for (const FGuid& Id : Removal.Nodes) { Targets.Add(Ctx.Resolve(Id)); }
				for (const FGuid& Id : Removal.Functions) { Targets.Add(Ctx.Resolve(Id)); }
				for (const FGuid& Id : Removal.Sources) { Sources.Add(Ctx.Resolve(Id)); }
				RemoveBindingsWhere(Data, [&Targets, &Sources](const FPropertyBindingBinding& Binding)
				{
					return Targets.Contains(Binding.GetTargetPath().GetStructID()) || Sources.Contains(Binding.GetSourcePath().GetStructID());
				});

				// 2) 전환 — 소유 상태가 함께 지워지지 않는 것만 직접 뺀다
				Data.VisitHierarchy([&Ctx, &Removal](UStateTreeState& State, UStateTreeState* /*Parent*/)
				{
					if (!Removal.States.Contains(State.ID) && State.Transitions.ContainsByPredicate([&Removal](const FStateTreeTransition& T) { return Removal.Transitions.Contains(T.ID); }))
					{
						Ctx.Touch(&State);
						State.Transitions.RemoveAll([&Removal](const FStateTreeTransition& T) { return Removal.Transitions.Contains(T.ID); });
					}
					return EStateTreeVisitor::Continue;
				});

				// 3) 노드 — 소유 상태 · 전환이 함께 지워지지 않는 것만
				for (const FGuid& Id : Removal.Nodes)
				{
					FNodeSlot Slot = FindNodeSlot(Data, Id);
					if (Slot.IsValid())
					{
						const UStateTreeState* OwnerState = Cast<UStateTreeState>(Slot.Owner);
						if (!OwnerState || !Removal.States.Contains(OwnerState->ID))
						{
							Ctx.Touch(Slot.Owner);
							Slot.Array->RemoveAt(Slot.Index);
						}
					}
				}

				// 4) 상태 — 부모에서 뺀다(엔진 RemoveSelectedStates 와 같은 순서)
				for (const FGuid& Id : Removal.States)
				{
					UStateTreeState* State = Data.GetMutableStateByID(Id);
					if (!State)
					{
						continue;   // 위에서 부모와 함께 이미 빠졌다
					}
					UStateTreeState* Parent = State->Parent;
					if (Parent)
					{
						Ctx.Touch(State);
						Ctx.Touch(Parent);
						Parent->Children.Remove(State);
						State->Parent = nullptr;
					}
				}
				return true;
			};
			Plan.Steps.Add(MoveTemp(Step));
		}

		// ─── op 별 계획

		bool ValidateNodeType(const FPlan& Plan, const FString& TypePath, const UScriptStruct* Base, const TCHAR* What, const UScriptStruct*& OutStruct, FAnimMcpError& OutError)
		{
			OutStruct = FindStructByPath(TypePath);
			if (!OutStruct)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotFound, FString::Printf(TEXT("%s type '%s' not found — use a full path from list_state_tree_node_types"), What, *TypePath));
				return false;
			}
			if (!OutStruct->IsChildOf(Base))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotAllowed, FString::Printf(TEXT("'%s' is not a %s"), *TypePath, What));
				return false;
			}
			if (!Plan.Schema->IsStructAllowed(OutStruct))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotAllowed, FString::Printf(TEXT("Schema %s does not allow '%s'"), *Plan.Schema->GetClass()->GetName(), *TypePath));
				return false;
			}
			return true;
		}

		void AddRef(FPlan& Plan, const FString& Ref, const ERefKind Kind, const FGuid& Id)
		{
			if (!Ref.IsEmpty())
			{
				FRefEntry Entry;
				Entry.Kind = Kind;
				Entry.Id = Id;
				Plan.Refs.Add(Ref, Entry);
			}
		}

		bool GetValues(const FOperation& Op, TSharedPtr<FJsonObject>& Out, FAnimMcpError& OutError)
		{
			const TSharedPtr<FJsonValue> Field = Op.Json->TryGetField(TEXT("values"));
			if (!Field.IsValid() || Field->Type == EJson::Null)
			{
				return true;
			}
			if (Field->Type != EJson::Object)
			{
				OutError = BadRequest(FString::Printf(TEXT("%s: 'values' must be an object"), *Op.Op));
				return false;
			}
			Out = Field->AsObject();
			return true;
		}

		/** 한 노드 생성의 공통부 — 타입 · 값 · 표현식 검증 + 그림자 등록 */
		struct FNodeSpec
		{
			FGuid Id;
			const UScriptStruct* Struct = nullptr;
			TArray<FParsedValue> Values;
			EStateTreeExpressionOperand Operand = EStateTreeExpressionOperand::And;
			int32 Indent = 0;
		};

		bool PlanNode(FPlan& Plan, const FJsonObject& Json, const TSharedPtr<FJsonObject>& Values, const UScriptStruct* Base, const TCHAR* What, const ENodeKind Kind, const FGuid& OwnerState, const FGuid& OwnerTransition, const FString& Ref, FNodeSpec& Out, FAnimMcpError& OutError)
		{
			FString TypePath;
			if (!Json.TryGetStringField(TEXT("type"), TypePath) || TypePath.IsEmpty())
			{
				OutError = BadRequest(FString::Printf(TEXT("%s requires 'type'"), What));
				return false;
			}
			if (!ValidateNodeType(Plan, TypePath, Base, What, Out.Struct, OutError))
			{
				return false;
			}
			const UStruct* InstanceStruct = GetInstanceStructOf(Out.Struct);
			if (!ParseValues(Values, Out.Struct, InstanceStruct, Out.Values, OutError))
			{
				return false;
			}
			FString OperandText;
			if (Json.TryGetStringField(TEXT("operand"), OperandText) && !ParseEnum(OperandText, TEXT("operand"), Out.Operand, OutError))
			{
				return false;
			}
			double Indent = 0.0;
			if (Json.TryGetNumberField(TEXT("indent"), Indent))
			{
				Out.Indent = FMath::Clamp(FMath::RoundToInt32(Indent), 0, UE::StateTree::MaxExpressionIndent);
			}

			Out.Id = FGuid::NewGuid();
			FShadowNode Shadow;
			Shadow.Id = Out.Id;
			Shadow.Name = FName(*Out.Struct->GetDisplayNameText().ToString());
			Shadow.Kind = Kind;
			Shadow.OwnerState = OwnerState;
			Shadow.OwnerTransition = OwnerTransition;
			Shadow.NodeStruct = Out.Struct;
			Shadow.InstanceStruct = InstanceStruct;
			Shadow.bPlanned = true;
			Plan.Nodes.Add(Shadow.Id, Shadow);
			AddRef(Plan, Ref, ERefKind::Node, Out.Id);
			return true;
		}

		void BuildNode(FStateTreeEditorNode& Node, const FNodeSpec& Spec, UObject* Outer)
		{
			InitNode(Node, Spec.Id, Spec.Struct, Outer);
			Node.ExpressionOperand = Spec.Operand;
			Node.ExpressionIndent = static_cast<uint8>(Spec.Indent);
			ApplyValues(Node, Spec.Values);
		}

		bool PlanAddState(FPlan& Plan, const FOperation& Op, FAnimMcpError& OutError)
		{
			FString Name;
			if (!RequireString(Op, TEXT("name"), Name, OutError))
			{
				return false;
			}
			FGuid ParentId = Plan.RootStateId;
			FString ParentText;
			if (Op.Json->TryGetStringField(TEXT("parent"), ParentText) && !ResolveState(Plan, ParentText, ParentId, OutError))
			{
				return false;
			}
			if (!Plan.States.Contains(ParentId))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::StateNotFound, TEXT("This tree has no Root state to add to"));
				return false;
			}

			EStateTreeStateType Type = EStateTreeStateType::State;
			FString TypeText;
			if (Op.Json->TryGetStringField(TEXT("type"), TypeText))
			{
				if (TypeText == TEXT("group"))
				{
					Type = EStateTreeStateType::Group;
				}
				else if (TypeText != TEXT("state"))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, FString::Printf(TEXT("add_state type '%s' is not supported (state, group)"), *TypeText));
					return false;
				}
			}
			if (!Plan.Schema->IsStateTypeAllowed(Type))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotAllowed, FString::Printf(TEXT("Schema does not allow state type '%s'"), *TypeText));
				return false;
			}

			bool bHasSelection = false;
			EStateTreeStateSelectionBehavior Selection = EStateTreeStateSelectionBehavior::TrySelectChildrenInOrder;
			FString SelectionText;
			if (Op.Json->TryGetStringField(TEXT("selection"), SelectionText))
			{
				if (!ParseEnum(SelectionText, TEXT("selection"), Selection, OutError))
				{
					return false;
				}
				if (!Plan.Schema->IsStateSelectionAllowed(Selection))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotAllowed, FString::Printf(TEXT("Schema does not allow selection '%s'"), *SelectionText));
					return false;
				}
				bHasSelection = true;
			}

			FGameplayTag Tag;
			FString TagText;
			if (Op.Json->TryGetStringField(TEXT("tag"), TagText) && !ParseTag(TagText, Tag, OutError))
			{
				return false;
			}
			bool bEnabled = true;
			Op.Json->TryGetBoolField(TEXT("enabled"), bEnabled);

			FShadowState Shadow;
			Shadow.Id = FGuid::NewGuid();
			Shadow.Name = FName(*Name);
			Shadow.Parent = ParentId;
			Plan.States.Add(Shadow.Id, Shadow);
			Plan.States[ParentId].Children.Add(Shadow.Id);
			AddRef(Plan, Op.Ref, ERefKind::State, Shadow.Id);

			FPlannedStep Step;
			Step.Index = Op.Index;
			Step.Run = [Id = Shadow.Id, ParentId, NewName = Shadow.Name, Type, bHasSelection, Selection, Tag, bEnabled](FApplyContext& Ctx, FAnimMcpError& OutErr) -> bool
			{
				UStateTreeState* Parent = Ctx.Data->GetMutableStateByID(ParentId);
				if (!Parent)
				{
					OutErr = FAnimMcpError::Make(AnimMcpErrorCodes::StateNotFound, TEXT("Parent state disappeared during apply"));
					return false;
				}
				Ctx.Touch(Ctx.Data);
				Ctx.Touch(Parent);
				UStateTreeState& New = Parent->AddChildState(NewName, Type);
				New.ID = Id;
				if (bHasSelection)
				{
					New.SelectionBehavior = Selection;
				}
				New.Tag = Tag;
				New.bEnabled = bEnabled;
				return true;
			};
			Plan.Steps.Add(MoveTemp(Step));
			return true;
		}

		bool PlanRemoveState(FPlan& Plan, const FOperation& Op, FAnimMcpError& OutError)
		{
			FString Text;
			FGuid StateId;
			if (!RequireString(Op, TEXT("state"), Text, OutError) || !ResolveState(Plan, Text, StateId, OutError))
			{
				return false;
			}
			if (StateId == Plan.RootStateId)
			{
				OutError = BadRequest(TEXT("The Root state cannot be removed"));
				return false;
			}
			bool bCascade = false;
			Op.Json->TryGetBoolField(TEXT("cascade"), bCascade);

			FRemoval Removal;
			AddStateToRemoval(Plan, StateId, Removal);
			const TArray<FGuid> ExternalTransitions = FindExternalTransitions(Plan, Removal);
			if (bCascade)
			{
				for (const FGuid& Id : ExternalTransitions)
				{
					AddTransitionToRemoval(Plan, Id, Removal);
				}
			}
			ExpandFunctions(Plan, Removal);
			const TArray<const FShadowBinding*> ExternalBindings = FindExternalBindings(Plan, Removal);
			if (!bCascade && (ExternalTransitions.Num() > 0 || ExternalBindings.Num() > 0))
			{
				OutError = MakeReferenced(FString::Printf(TEXT("State '%s' is referenced by %d transition(s) and %d binding(s) — remove them or pass cascade:true"), *Text, ExternalTransitions.Num(), ExternalBindings.Num()), ExternalBindings, ExternalTransitions);
				return false;
			}
			CommitRemoval(Plan, Op.Index, Removal);
			return true;
		}

		bool PlanSetStateProperties(FPlan& Plan, const FOperation& Op, FAnimMcpError& OutError)
		{
			FString Text;
			FGuid StateId;
			if (!RequireString(Op, TEXT("state"), Text, OutError) || !ResolveState(Plan, Text, StateId, OutError))
			{
				return false;
			}
			const TSharedPtr<FJsonObject>* Properties = nullptr;
			if (!Op.Json->TryGetObjectField(TEXT("properties"), Properties) || !Properties || !Properties->IsValid())
			{
				OutError = BadRequest(TEXT("set_state_properties requires 'properties'"));
				return false;
			}

			using FSetter = TFunction<void(UStateTreeState&)>;
			TArray<FSetter> Setters;
			for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*Properties)->Values)
			{
				const FString& Key = Pair.Key;
				const TSharedPtr<FJsonValue>& Value = Pair.Value;
				const bool bNull = !Value.IsValid() || Value->Type == EJson::Null;
				FString Str;
				double Number = 0.0;
				bool Bool = false;
				const bool bIsString = !bNull && Value->TryGetString(Str) && Value->Type == EJson::String;
				const bool bIsNumber = !bNull && Value->Type == EJson::Number && Value->TryGetNumber(Number);
				const bool bIsBool = !bNull && Value->Type == EJson::Boolean && Value->TryGetBool(Bool);

				if (Key == TEXT("TasksCompletion") && bIsString)
				{
					EStateTreeTaskCompletionType Completion;
					if (!ParseEnum(Str, *Key, Completion, OutError))
					{
						return false;
					}
					Setters.Add([Completion](UStateTreeState& State) { State.TasksCompletion = Completion; });
				}
				else if (Key == TEXT("SelectionBehavior") && bIsString)
				{
					EStateTreeStateSelectionBehavior Selection;
					if (!ParseEnum(Str, *Key, Selection, OutError))
					{
						return false;
					}
					if (!Plan.Schema->IsStateSelectionAllowed(Selection))
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotAllowed, FString::Printf(TEXT("Schema does not allow selection '%s'"), *Str));
						return false;
					}
					Setters.Add([Selection](UStateTreeState& State) { State.SelectionBehavior = Selection; });
				}
				else if (Key == TEXT("Tag") && (bIsString || bNull))
				{
					FGameplayTag Tag;
					if (bIsString && !ParseTag(Str, Tag, OutError))
					{
						return false;
					}
					Setters.Add([Tag](UStateTreeState& State) { State.Tag = Tag; });
				}
				else if (Key == TEXT("bEnabled") && bIsBool)
				{
					Setters.Add([Bool](UStateTreeState& State) { State.bEnabled = Bool; });
				}
				else if (Key == TEXT("CustomTickRate") && (bIsNumber || bNull))
				{
					const float Rate = static_cast<float>(Number);
					Setters.Add([Rate, bNull](UStateTreeState& State) { State.bHasCustomTickRate = !bNull; State.CustomTickRate = Rate; });
				}
				else if (Key == TEXT("Weight") && bIsNumber)
				{
					const float Weight = static_cast<float>(Number);
					Setters.Add([Weight](UStateTreeState& State) { State.Weight = Weight; });
				}
				else if (Key == TEXT("RequiredEventToEnter") && (bIsString || bNull))
				{
					FGameplayTag Tag;
					if (bIsString && !ParseTag(Str, Tag, OutError))
					{
						return false;
					}
					Setters.Add([Tag, bNull](UStateTreeState& State) { State.bHasRequiredEventToEnter = !bNull; State.RequiredEventToEnter.Tag = Tag; });
				}
				else
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, FString::Printf(TEXT("set_state_properties does not accept '%s' with this value (allowed: TasksCompletion, SelectionBehavior, Tag, bEnabled, CustomTickRate, Weight, RequiredEventToEnter)"), *Key));
					return false;
				}
			}

			FPlannedStep Step;
			Step.Index = Op.Index;
			Step.Run = [StateId, Setters = MoveTemp(Setters)](FApplyContext& Ctx, FAnimMcpError& OutErr) -> bool
			{
				UStateTreeState* State = Ctx.Data->GetMutableStateByID(StateId);
				if (!State)
				{
					OutErr = FAnimMcpError::Make(AnimMcpErrorCodes::StateNotFound, TEXT("State disappeared during apply"));
					return false;
				}
				Ctx.Touch(State);
				for (const FSetter& Setter : Setters)
				{
					Setter(*State);
				}
				return true;
			};
			Plan.Steps.Add(MoveTemp(Step));
			return true;
		}

		bool PlanAddStateNode(FPlan& Plan, const FOperation& Op, const ENodeKind Kind, FAnimMcpError& OutError)
		{
			FString Text;
			FGuid StateId;
			if (!RequireString(Op, TEXT("state"), Text, OutError) || !ResolveState(Plan, Text, StateId, OutError))
			{
				return false;
			}
			const bool bTask = Kind == ENodeKind::Task;
			if (bTask ? !Plan.Schema->AllowMultipleTasks() : !Plan.Schema->AllowEnterConditions())
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotAllowed, FString::Printf(TEXT("Schema does not allow %s on states"), bTask ? TEXT("multiple tasks") : TEXT("enter conditions")));
				return false;
			}

			TSharedPtr<FJsonObject> Values;
			if (!GetValues(Op, Values, OutError))
			{
				return false;
			}
			FNodeSpec Spec;
			const UScriptStruct* Base = bTask ? FStateTreeTaskBase::StaticStruct() : FStateTreeConditionBase::StaticStruct();
			if (!PlanNode(Plan, *Op.Json, Values, Base, bTask ? TEXT("task") : TEXT("condition"), Kind, StateId, FGuid(), Op.Ref, Spec, OutError))
			{
				return false;
			}

			FPlannedStep Step;
			Step.Index = Op.Index;
			Step.Run = [StateId, bTask, Spec = MoveTemp(Spec)](FApplyContext& Ctx, FAnimMcpError& OutErr) -> bool
			{
				UStateTreeState* State = Ctx.Data->GetMutableStateByID(StateId);
				if (!State)
				{
					OutErr = FAnimMcpError::Make(AnimMcpErrorCodes::StateNotFound, TEXT("State disappeared during apply"));
					return false;
				}
				Ctx.Touch(State);
				TArray<FStateTreeEditorNode>& Array = bTask ? State->Tasks : State->EnterConditions;
				BuildNode(Array.AddDefaulted_GetRef(), Spec, State);
				return true;
			};
			Plan.Steps.Add(MoveTemp(Step));
			return true;
		}

		bool PlanAddGlobalNode(FPlan& Plan, const FOperation& Op, const ENodeKind Kind, FAnimMcpError& OutError)
		{
			const bool bEvaluator = Kind == ENodeKind::Evaluator;
			if (bEvaluator && !Plan.Schema->AllowEvaluators())
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotAllowed, TEXT("Schema does not allow evaluators"));
				return false;
			}
			TSharedPtr<FJsonObject> Values;
			if (!GetValues(Op, Values, OutError))
			{
				return false;
			}
			FNodeSpec Spec;
			const UScriptStruct* Base = bEvaluator ? FStateTreeEvaluatorBase::StaticStruct() : FStateTreeTaskBase::StaticStruct();
			if (!PlanNode(Plan, *Op.Json, Values, Base, bEvaluator ? TEXT("evaluator") : TEXT("task"), Kind, FGuid(), FGuid(), Op.Ref, Spec, OutError))
			{
				return false;
			}

			FPlannedStep Step;
			Step.Index = Op.Index;
			Step.Run = [bEvaluator, Spec = MoveTemp(Spec)](FApplyContext& Ctx, FAnimMcpError&) -> bool
			{
				Ctx.Touch(Ctx.Data);
				TArray<FStateTreeEditorNode>& Array = bEvaluator ? Ctx.Data->Evaluators : Ctx.Data->GlobalTasks;
				BuildNode(Array.AddDefaulted_GetRef(), Spec, Ctx.Data);
				return true;
			};
			Plan.Steps.Add(MoveTemp(Step));
			return true;
		}

		bool ParseTransitionTarget(const FPlan& Plan, const FString& Text, EStateTreeTransitionType& OutType, FGuid& OutState, FAnimMcpError& OutError)
		{
			if (Text == TEXT("succeeded")) { OutType = EStateTreeTransitionType::Succeeded; return true; }
			if (Text == TEXT("failed")) { OutType = EStateTreeTransitionType::Failed; return true; }
			if (Text == TEXT("next_state")) { OutType = EStateTreeTransitionType::NextState; return true; }
			if (Text == TEXT("next_selectable_state")) { OutType = EStateTreeTransitionType::NextSelectableState; return true; }
			OutType = EStateTreeTransitionType::GotoState;
			return ResolveState(Plan, Text, OutState, OutError);
		}

		bool PlanAddTransition(FPlan& Plan, const FOperation& Op, FAnimMcpError& OutError)
		{
			FString StateText, TriggerText, TargetText;
			FGuid OwnerId;
			if (!RequireString(Op, TEXT("state"), StateText, OutError) || !ResolveState(Plan, StateText, OwnerId, OutError)
				|| !RequireString(Op, TEXT("trigger"), TriggerText, OutError) || !RequireString(Op, TEXT("target"), TargetText, OutError))
			{
				return false;
			}
			EStateTreeTransitionTrigger Trigger = EStateTreeTransitionTrigger::None;
			if (!ParseEnum(TriggerText, TEXT("trigger"), Trigger, OutError))
			{
				return false;
			}
			if (Trigger == EStateTreeTransitionTrigger::None || Trigger == EStateTreeTransitionTrigger::OnDelegate)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, FString::Printf(TEXT("trigger '%s' is not supported"), *TriggerText));
				return false;
			}

			EStateTreeTransitionType Type = EStateTreeTransitionType::GotoState;
			FGuid TargetState;
			if (!ParseTransitionTarget(Plan, TargetText, Type, TargetState, OutError))
			{
				return false;
			}

			FGameplayTag EventTag;
			FString EventText;
			if (Op.Json->TryGetStringField(TEXT("event_tag"), EventText) && !ParseTag(EventText, EventTag, OutError))
			{
				return false;
			}
			if (Trigger == EStateTreeTransitionTrigger::OnEvent && !EventTag.IsValid())
			{
				OutError = BadRequest(TEXT("add_transition with trigger OnEvent requires 'event_tag'"));
				return false;
			}

			bool bHasPriority = false;
			EStateTreeTransitionPriority Priority = EStateTreeTransitionPriority::Normal;
			FString PriorityText;
			if (Op.Json->TryGetStringField(TEXT("priority"), PriorityText))
			{
				if (!ParseEnum(PriorityText, TEXT("priority"), Priority, OutError))
				{
					return false;
				}
				bHasPriority = true;
			}
			double Delay = 0.0;
			const bool bHasDelay = Op.Json->TryGetNumberField(TEXT("delay"), Delay) && Delay > 0.0;

			FShadowTransition Shadow;
			Shadow.Id = FGuid::NewGuid();
			Shadow.OwnerState = OwnerId;
			Shadow.TargetState = TargetState;
			Plan.Transitions.Add(Shadow.Id, Shadow);
			AddRef(Plan, Op.Ref, ERefKind::Transition, Shadow.Id);

			TArray<FNodeSpec> Conditions;
			const TArray<TSharedPtr<FJsonValue>>* ConditionArray = nullptr;
			if (Op.Json->TryGetArrayField(TEXT("conditions"), ConditionArray) && ConditionArray)
			{
				for (const TSharedPtr<FJsonValue>& Item : *ConditionArray)
				{
					const TSharedPtr<FJsonObject>* Condition = nullptr;
					if (!Item.IsValid() || !Item->TryGetObject(Condition) || !Condition || !Condition->IsValid())
					{
						OutError = BadRequest(TEXT("add_transition: each entry of 'conditions' must be an object"));
						return false;
					}
					FString Ref;
					(*Condition)->TryGetStringField(TEXT("ref"), Ref);
					if (!Ref.IsEmpty() && Plan.Refs.Contains(Ref))
					{
						OutError = BadRequest(FString::Printf(TEXT("ref '%s' is defined twice"), *Ref));
						return false;
					}
					const TSharedPtr<FJsonObject>* ValuesField = nullptr;
					TSharedPtr<FJsonObject> Values;
					if ((*Condition)->TryGetObjectField(TEXT("values"), ValuesField) && ValuesField)
					{
						Values = *ValuesField;
					}
					FNodeSpec Spec;
					if (!PlanNode(Plan, **Condition, Values, FStateTreeConditionBase::StaticStruct(), TEXT("condition"), ENodeKind::TransitionCondition, OwnerId, Shadow.Id, Ref, Spec, OutError))
					{
						return false;
					}
					Conditions.Add(MoveTemp(Spec));
				}
			}

			FPlannedStep Step;
			Step.Index = Op.Index;
			Step.Run = [Id = Shadow.Id, OwnerId, TargetState, Trigger, Type, EventTag, bHasPriority, Priority, bHasDelay, Delay, Conditions = MoveTemp(Conditions)](FApplyContext& Ctx, FAnimMcpError& OutErr) -> bool
			{
				UStateTreeState* Owner = Ctx.Data->GetMutableStateByID(OwnerId);
				const UStateTreeState* Target = TargetState.IsValid() ? Ctx.Data->GetStateByID(TargetState) : nullptr;
				if (!Owner || (TargetState.IsValid() && !Target))
				{
					OutErr = FAnimMcpError::Make(AnimMcpErrorCodes::StateNotFound, TEXT("Transition state disappeared during apply"));
					return false;
				}
				Ctx.Touch(Owner);
				FStateTreeTransition& Transition = EventTag.IsValid() ? Owner->AddTransition(Trigger, EventTag, Type, Target) : Owner->AddTransition(Trigger, Type, Target);
				Transition.ID = Id;
				if (bHasPriority)
				{
					Transition.Priority = Priority;
				}
				if (bHasDelay)
				{
					Transition.bDelayTransition = true;
					Transition.DelayDuration = static_cast<float>(Delay);
				}
				for (const FNodeSpec& Spec : Conditions)
				{
					BuildNode(Transition.Conditions.AddDefaulted_GetRef(), Spec, Owner);
				}
				return true;
			};
			Plan.Steps.Add(MoveTemp(Step));
			return true;
		}

		bool PlanRemoveTransition(FPlan& Plan, const FOperation& Op, FAnimMcpError& OutError)
		{
			FString StateText, TransitionText;
			FGuid OwnerId;
			if (!RequireString(Op, TEXT("state"), StateText, OutError) || !ResolveState(Plan, StateText, OwnerId, OutError)
				|| !RequireString(Op, TEXT("transition"), TransitionText, OutError))
			{
				return false;
			}
			FGuid TransitionId;
			if (const FRefEntry* Ref = Plan.Refs.Find(TransitionText); Ref && Ref->Kind == ERefKind::Transition)
			{
				TransitionId = Ref->Id;
			}
			else
			{
				FGuid::Parse(TransitionText, TransitionId);
			}
			const FShadowTransition* Transition = Plan.Transitions.Find(TransitionId);
			if (!Transition || Transition->OwnerState != OwnerId)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::NodeNotFound, FString::Printf(TEXT("Transition '%s' not found on state '%s'"), *TransitionText, *StateText));
				return false;
			}

			FRemoval Removal;
			AddTransitionToRemoval(Plan, TransitionId, Removal);
			ExpandFunctions(Plan, Removal);
			const TArray<const FShadowBinding*> ExternalBindings = FindExternalBindings(Plan, Removal);
			if (ExternalBindings.Num() > 0)
			{
				OutError = MakeReferenced(FString::Printf(TEXT("Transition '%s' is a binding source for %d binding(s) — unbind them first"), *TransitionText, ExternalBindings.Num()), ExternalBindings, {});
				return false;
			}
			CommitRemoval(Plan, Op.Index, Removal);
			return true;
		}

		bool PlanRemoveNode(FPlan& Plan, const FOperation& Op, FAnimMcpError& OutError)
		{
			FString Text;
			FGuid NodeId;
			if (!RequireString(Op, TEXT("node"), Text, OutError) || !ResolveNode(Plan, Text, NodeId, OutError))
			{
				return false;
			}
			if (Plan.Nodes[NodeId].Kind == ENodeKind::Function)
			{
				OutError = BadRequest(TEXT("Property function nodes are removed with unbind_property on their target"));
				return false;
			}

			FRemoval Removal;
			Removal.Nodes.Add(NodeId);
			ExpandFunctions(Plan, Removal);
			const TArray<const FShadowBinding*> ExternalBindings = FindExternalBindings(Plan, Removal);
			if (ExternalBindings.Num() > 0)
			{
				OutError = MakeReferenced(FString::Printf(TEXT("Node '%s' is the source of %d binding(s) — unbind them first"), *Text, ExternalBindings.Num()), ExternalBindings, {});
				return false;
			}
			CommitRemoval(Plan, Op.Index, Removal);
			return true;
		}

		bool PlanSetNodeValues(FPlan& Plan, const FOperation& Op, FAnimMcpError& OutError)
		{
			FString Text;
			FGuid NodeId;
			if (!RequireString(Op, TEXT("node"), Text, OutError) || !ResolveNode(Plan, Text, NodeId, OutError))
			{
				return false;
			}
			const FShadowNode& Node = Plan.Nodes[NodeId];
			if (Node.Kind == ENodeKind::Function || Node.bBlueprintInstance)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, TEXT("Values of property function and Blueprint nodes cannot be set by this tool"));
				return false;
			}
			TSharedPtr<FJsonObject> Values;
			if (!GetValues(Op, Values, OutError))
			{
				return false;
			}
			if (!Values.IsValid())
			{
				OutError = BadRequest(TEXT("set_node_values requires 'values'"));
				return false;
			}
			TArray<FParsedValue> Parsed;
			if (!ParseValues(Values, Node.NodeStruct, Node.InstanceStruct, Parsed, OutError))
			{
				return false;
			}

			FPlannedStep Step;
			Step.Index = Op.Index;
			Step.Run = [NodeId, Parsed = MoveTemp(Parsed)](FApplyContext& Ctx, FAnimMcpError& OutErr) -> bool
			{
				FNodeSlot Slot = FindNodeSlot(*Ctx.Data, NodeId);
				if (!Slot.IsValid())
				{
					OutErr = FAnimMcpError::Make(AnimMcpErrorCodes::NodeNotFound, TEXT("Node disappeared during apply"));
					return false;
				}
				Ctx.Touch(Slot.Owner);
				ApplyValues(Slot.Get(), Parsed);
				return true;
			};
			Plan.Steps.Add(MoveTemp(Step));
			return true;
		}

		bool ParsePath(FPropertyBindingPath& Path, const FString& Text, const TCHAR* Code, FAnimMcpError& OutError)
		{
			if (!Text.IsEmpty() && !Path.FromString(Text))
			{
				OutError = FAnimMcpError::Make(Code, FString::Printf(TEXT("Malformed property path '%s'"), *Text));
				return false;
			}
			return true;
		}

		bool GetEndpointObject(const FOperation& Op, const TCHAR* Key, TSharedPtr<FJsonObject>& Out, FAnimMcpError& OutError)
		{
			const TSharedPtr<FJsonObject>* Field = nullptr;
			if (!Op.Json->TryGetObjectField(Key, Field) || !Field || !Field->IsValid())
			{
				OutError = BadRequest(FString::Printf(TEXT("%s requires '%s' {...}"), *Op.Op, Key));
				return false;
			}
			Out = *Field;
			return true;
		}

		/** target: { node, path } */
		bool ResolveTargetEndpoint(const FPlan& Plan, const FOperation& Op, AnimMcpStateTreeBindings::FEndpoint& Out, FString& OutPathText, FAnimMcpError& OutError)
		{
			TSharedPtr<FJsonObject> Target;
			if (!GetEndpointObject(Op, TEXT("target"), Target, OutError))
			{
				return false;
			}
			FString NodeText;
			if (!Target->TryGetStringField(TEXT("node"), NodeText) || NodeText.IsEmpty())
			{
				OutError = BadRequest(FString::Printf(TEXT("%s requires target.node"), *Op.Op));
				return false;
			}
			Target->TryGetStringField(TEXT("path"), OutPathText);

			FGuid NodeId;
			if (!ResolveNode(Plan, NodeText, NodeId, OutError))
			{
				return false;
			}
			const FShadowNode& Node = Plan.Nodes[NodeId];
			Out.Path = FPropertyBindingPath(NodeId);
			Out.PlannedStruct = Node.bPlanned ? Node.InstanceStruct : nullptr;
			if (!ParsePath(Out.Path, OutPathText, AnimMcpErrorCodes::BadTargetPath, OutError))
			{
				return false;
			}
			OutPathText = Out.Path.ToString();
			return true;
		}

		/** source: { struct, path } — struct = ref · GUID · 컨텍스트 이름 · parameters · 노드 이름 */
		bool ResolveSourceEndpoint(const FPlan& Plan, const FOperation& Op, AnimMcpStateTreeBindings::FEndpoint& Out, FString& OutPathText, FAnimMcpError& OutError)
		{
			TSharedPtr<FJsonObject> Source;
			if (!GetEndpointObject(Op, TEXT("source"), Source, OutError))
			{
				return false;
			}
			FString StructText;
			if (!Source->TryGetStringField(TEXT("struct"), StructText) || StructText.IsEmpty())
			{
				OutError = BadRequest(FString::Printf(TEXT("%s requires source.struct"), *Op.Op));
				return false;
			}
			Source->TryGetStringField(TEXT("path"), OutPathText);

			FGuid StructId;
			bool bResolved = false;
			if (!Plan.Refs.Contains(StructText))
			{
				if (StructText == TEXT("parameters"))
				{
					StructId = Plan.Data->GetRootParametersGuid();
					bResolved = true;
				}
				else
				{
					for (const FStateTreeExternalDataDesc& Desc : Plan.Schema->GetContextDataDescs())
					{
						if (Desc.Name.ToString() == StructText)
						{
							StructId = Desc.ID;
							bResolved = true;
							break;
						}
					}
				}
				// 노드가 아닌 구조체(상태 파라미터 · 이벤트)는 GUID 로 온다
				FGuid Parsed;
				if (!bResolved && FGuid::Parse(StructText, Parsed) && !Plan.Nodes.Contains(Parsed))
				{
					if (Plan.RemovedIds.Contains(Parsed))
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::NodeNotFound, FString::Printf(TEXT("struct %s was removed earlier in this batch"), *StructText));
						return false;
					}
					TInstancedStruct<FPropertyBindingBindableStructDescriptor> Desc;
					if (Plan.Data->GetBindableStructByID(Parsed, Desc))
					{
						StructId = Parsed;
						bResolved = true;
					}
				}
			}
			if (!bResolved && !ResolveNode(Plan, StructText, StructId, OutError))
			{
				return false;
			}

			const FShadowNode* Node = Plan.Nodes.Find(StructId);
			Out.Path = FPropertyBindingPath(StructId);
			Out.PlannedStruct = Node && Node->bPlanned ? Node->InstanceStruct : nullptr;
			if (!ParsePath(Out.Path, OutPathText, AnimMcpErrorCodes::BadSourcePath, OutError))
			{
				return false;
			}
			OutPathText = Out.Path.ToString();
			return true;
		}

		bool CheckToError(const AnimMcpStateTreeBindings::FCheck& Check, FAnimMcpError& OutError)
		{
			if (Check.IsOk())
			{
				return true;
			}
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("detail"), Check.Detail);
			OutError = FAnimMcpError::Make(*Check.Code, FString::Printf(TEXT("Binding rejected: %s (%s)"), *Check.Code, *Check.Detail), Details);
			return false;
		}

		/** 같은 대상에 묶인 기존 바인딩을 그림자에서 뺀다 — AddBinding 이 대체한다 */
		void ShadowDropTarget(FPlan& Plan, const FGuid& TargetId, const FString& TargetPath)
		{
			TArray<FGuid> Functions;
			Plan.Bindings.RemoveAll([&](const FShadowBinding& Binding)
			{
				if (Binding.TargetId == TargetId && Binding.TargetPath == TargetPath)
				{
					if (Binding.FunctionId.IsValid())
					{
						Functions.Add(Binding.FunctionId);
					}
					return true;
				}
				return false;
			});
			for (const FGuid& Function : Functions)
			{
				Plan.Nodes.Remove(Function);
				Plan.RemovedIds.Add(Function);
				TArray<FString> Inputs;
				for (const FShadowBinding& Binding : Plan.Bindings)
				{
					if (Binding.TargetId == Function)
					{
						Inputs.Add(Binding.TargetPath);
					}
				}
				for (const FString& Input : Inputs)
				{
					ShadowDropTarget(Plan, Function, Input);
				}
			}
		}

		bool PlanBindProperty(FPlan& Plan, const FOperation& Op, FAnimMcpError& OutError)
		{
			AnimMcpStateTreeBindings::FEndpoint Source, Target;
			FString SourceText, TargetText;
			if (!ResolveSourceEndpoint(Plan, Op, Source, SourceText, OutError) || !ResolveTargetEndpoint(Plan, Op, Target, TargetText, OutError))
			{
				return false;
			}
			if (!CheckToError(AnimMcpStateTreeBindings::CheckPathsAndTypes(*Plan.Data, Source, Target), OutError))
			{
				return false;
			}
			// 양쪽이 기존 노드일 때만 범위를 여기서 본다 — 나머지는 데이터가 생긴 뒤 실행 단계가 본다
			if (Source.PlannedStruct || Target.PlannedStruct)
			{
				Plan.Deferred.Add(TEXT("scope"));
			}
			else if (!CheckToError(AnimMcpStateTreeBindings::CheckScope(*Plan.Data, Source.Path, Target.Path), OutError))
			{
				return false;
			}

			const FGuid SourceId = Source.Path.GetStructID();
			const FGuid TargetId = Target.Path.GetStructID();
			ShadowDropTarget(Plan, TargetId, TargetText);
			FShadowBinding Shadow;
			Shadow.SourceId = SourceId;
			Shadow.TargetId = TargetId;
			Shadow.TargetPath = TargetText;
			Plan.Bindings.Add(Shadow);

			FPlannedStep Step;
			Step.Index = Op.Index;
			Step.Run = [SourceId, SourceText, TargetId, TargetText](FApplyContext& Ctx, FAnimMcpError& OutErr) -> bool
			{
				FPropertyBindingPath SourcePath(Ctx.Resolve(SourceId));
				FPropertyBindingPath TargetPath(Ctx.Resolve(TargetId));
				if (!ParsePath(SourcePath, SourceText, AnimMcpErrorCodes::BadSourcePath, OutErr) || !ParsePath(TargetPath, TargetText, AnimMcpErrorCodes::BadTargetPath, OutErr))
				{
					return false;
				}
				// 2차 검증 — 이제 데이터가 있다. 계획 단계와 같은 함수이고 범위까지 본다
				if (!CheckToError(AnimMcpStateTreeBindings::Preflight(*Ctx.Data, SourcePath, TargetPath), OutErr))
				{
					return false;
				}
				Ctx.Touch(Ctx.Data);
				RemoveBindingAtTarget(*Ctx.Data, TargetPath.GetStructID(), TargetText);
				Ctx.Data->AddPropertyBinding(SourcePath, TargetPath);
				return true;
			};
			Plan.Steps.Add(MoveTemp(Step));
			return true;
		}

		bool PlanUnbindProperty(FPlan& Plan, const FOperation& Op, FAnimMcpError& OutError)
		{
			AnimMcpStateTreeBindings::FEndpoint Target;
			FString TargetText;
			if (!ResolveTargetEndpoint(Plan, Op, Target, TargetText, OutError))
			{
				return false;
			}
			const FGuid TargetId = Target.Path.GetStructID();
			if (!Plan.Bindings.ContainsByPredicate([&](const FShadowBinding& Binding) { return Binding.TargetId == TargetId && Binding.TargetPath == TargetText; }))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadTargetPath, FString::Printf(TEXT("No binding at target path '%s'"), *TargetText));
				return false;
			}
			ShadowDropTarget(Plan, TargetId, TargetText);

			FPlannedStep Step;
			Step.Index = Op.Index;
			Step.Run = [TargetId, TargetText](FApplyContext& Ctx, FAnimMcpError&) -> bool
			{
				Ctx.Touch(Ctx.Data);
				RemoveBindingAtTarget(*Ctx.Data, Ctx.Resolve(TargetId), TargetText);
				return true;
			};
			Plan.Steps.Add(MoveTemp(Step));
			return true;
		}

		bool PlanBindPropertyFunction(FPlan& Plan, const FOperation& Op, FAnimMcpError& OutError)
		{
			FString FunctionPath;
			if (!RequireString(Op, TEXT("function"), FunctionPath, OutError))
			{
				return false;
			}
			const UScriptStruct* Function = nullptr;
			if (!ValidateNodeType(Plan, FunctionPath, FStateTreePropertyFunctionBase::StaticStruct(), TEXT("property function"), Function, OutError))
			{
				return false;
			}
			const UStruct* InstanceStruct = GetInstanceStructOf(Function);
			if (!InstanceStruct)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotAllowed, FString::Printf(TEXT("'%s' has no instance data"), *FunctionPath));
				return false;
			}

			FName OutputName;
			FString OutputText;
			if (Op.Json->TryGetStringField(TEXT("output"), OutputText) && !OutputText.IsEmpty())
			{
				const FProperty* Output = InstanceStruct->FindPropertyByName(FName(*OutputText));
				if (!Output || UE::StateTree::GetUsageFromMetaData(Output) != EStateTreePropertyUsage::Output)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadSourcePath, FString::Printf(TEXT("'%s' is not an Output property of %s"), *OutputText, *GetNameSafe(Function)));
					return false;
				}
				OutputName = Output->GetFName();
			}
			else
			{
				const FProperty* Single = UE::StateTree::GetStructSingleOutputProperty(*InstanceStruct);
				if (!Single)
				{
					OutError = BadRequest(FString::Printf(TEXT("%s has several outputs — pass 'output'"), *GetNameSafe(Function)));
					return false;
				}
				OutputName = Single->GetFName();
			}

			AnimMcpStateTreeBindings::FEndpoint Target;
			FString TargetText;
			if (!ResolveTargetEndpoint(Plan, Op, Target, TargetText, OutError))
			{
				return false;
			}

			const FGuid FunctionId = FGuid::NewGuid();
			AnimMcpStateTreeBindings::FEndpoint Source;
			Source.Path = FPropertyBindingPath(FunctionId, OutputName);
			Source.PlannedStruct = InstanceStruct;
			if (!CheckToError(AnimMcpStateTreeBindings::CheckPathsAndTypes(*Plan.Data, Source, Target), OutError))
			{
				return false;
			}

			const FGuid TargetId = Target.Path.GetStructID();
			ShadowDropTarget(Plan, TargetId, TargetText);
			FShadowNode Node;
			Node.Id = FunctionId;
			Node.Name = FName(*Function->GetDisplayNameText().ToString());
			Node.Kind = ENodeKind::Function;
			Node.NodeStruct = Function;
			Node.InstanceStruct = InstanceStruct;
			Node.bPlanned = true;
			Plan.Nodes.Add(FunctionId, Node);
			AddRef(Plan, Op.Ref, ERefKind::Node, FunctionId);
			FShadowBinding Shadow;
			Shadow.SourceId = FunctionId;
			Shadow.TargetId = TargetId;
			Shadow.TargetPath = TargetText;
			Shadow.FunctionId = FunctionId;
			Plan.Bindings.Add(Shadow);

			FPlannedStep Step;
			Step.Index = Op.Index;
			Step.Run = [Function, OutputName, FunctionId, TargetId, TargetText](FApplyContext& Ctx, FAnimMcpError& OutErr) -> bool
			{
				FPropertyBindingPath TargetPath(Ctx.Resolve(TargetId));
				if (!ParsePath(TargetPath, TargetText, AnimMcpErrorCodes::BadTargetPath, OutErr))
				{
					return false;
				}
				Ctx.Touch(Ctx.Data);
				RemoveBindingAtTarget(*Ctx.Data, TargetPath.GetStructID(), TargetText);
				TArray<FPropertyBindingPathSegment> Output;
				Output.Emplace(OutputName);
				const FPropertyBindingPath Created = Ctx.Data->EditorBindings.AddFunctionBinding(Function, Output, TargetPath);
				Ctx.FunctionIds.Add(FunctionId, Created.GetStructID());
				return true;
			};
			Plan.Steps.Add(MoveTemp(Step));
			return true;
		}

		bool PlanOperation(FPlan& Plan, const FOperation& Op, FAnimMcpError& OutError)
		{
			if (!Op.Ref.IsEmpty() && Plan.Refs.Contains(Op.Ref))
			{
				OutError = BadRequest(FString::Printf(TEXT("ref '%s' is defined twice"), *Op.Ref));
				return false;
			}
			if (Op.Op == TEXT("add_state")) { return PlanAddState(Plan, Op, OutError); }
			if (Op.Op == TEXT("remove_state")) { return PlanRemoveState(Plan, Op, OutError); }
			if (Op.Op == TEXT("set_state_properties")) { return PlanSetStateProperties(Plan, Op, OutError); }
			if (Op.Op == TEXT("add_task")) { return PlanAddStateNode(Plan, Op, ENodeKind::Task, OutError); }
			if (Op.Op == TEXT("add_enter_condition")) { return PlanAddStateNode(Plan, Op, ENodeKind::EnterCondition, OutError); }
			if (Op.Op == TEXT("add_evaluator")) { return PlanAddGlobalNode(Plan, Op, ENodeKind::Evaluator, OutError); }
			if (Op.Op == TEXT("add_global_task")) { return PlanAddGlobalNode(Plan, Op, ENodeKind::GlobalTask, OutError); }
			if (Op.Op == TEXT("add_transition")) { return PlanAddTransition(Plan, Op, OutError); }
			if (Op.Op == TEXT("remove_transition")) { return PlanRemoveTransition(Plan, Op, OutError); }
			if (Op.Op == TEXT("remove_node")) { return PlanRemoveNode(Plan, Op, OutError); }
			if (Op.Op == TEXT("set_node_values")) { return PlanSetNodeValues(Plan, Op, OutError); }
			if (Op.Op == TEXT("bind_property")) { return PlanBindProperty(Plan, Op, OutError); }
			if (Op.Op == TEXT("unbind_property")) { return PlanUnbindProperty(Plan, Op, OutError); }
			if (Op.Op == TEXT("bind_property_function")) { return PlanBindPropertyFunction(Plan, Op, OutError); }
			OutError = BadRequest(FString::Printf(TEXT("Unknown op '%s'"), *Op.Op));
			return false;
		}

		TSharedRef<FJsonObject> MakePlanned(const FOperation& Op)
		{
			TSharedRef<FJsonObject> Entry = AnimMcpJson::MakeObject();
			Entry->SetNumberField(TEXT("index"), Op.Index);
			Entry->SetStringField(TEXT("op"), Op.Op);
			if (!Op.Ref.IsEmpty())
			{
				Entry->SetStringField(TEXT("ref"), Op.Ref);
			}
			return Entry;
		}

		/** 첫 실패에서 멈춘다 — 뒤 op 는 앞 op 의 결과에 기대므로 이어서 검사하면 연쇄 오류만 나온다. 멈춘 뒤의 op 는 skipped */
		bool BuildPlan(const UStateTreeEditorData& Data, const TArray<FOperation>& Ops, FPlan& Plan, TArray<TSharedPtr<FJsonValue>>& OutPlanned, FAnimMcpError& OutFirstError)
		{
			BuildShadow(Data, Plan);
			bool bValid = true;
			for (const FOperation& Op : Ops)
			{
				TSharedRef<FJsonObject> Entry = MakePlanned(Op);
				if (!bValid)
				{
					Entry->SetBoolField(TEXT("skipped"), true);
					OutPlanned.Add(MakeShared<FJsonValueObject>(Entry));
					continue;
				}
				Plan.Deferred.Reset();
				FAnimMcpError Error;
				const bool bOk = PlanOperation(Plan, Op, Error);
				Entry->SetBoolField(TEXT("ok"), bOk);
				if (!bOk)
				{
					Entry->SetObjectField(TEXT("error"), Error.ToJson());
					OutFirstError = Error;
					OutFirstError.Details = nullptr;
					OutFirstError.Message = FString::Printf(TEXT("operations[%d] %s: %s"), Op.Index, *Op.Op, *Error.Message);
					bValid = false;
				}
				else if (Plan.Deferred.Num() > 0)
				{
					TArray<TSharedPtr<FJsonValue>> Deferred;
					for (const FString& Item : Plan.Deferred)
					{
						Deferred.Add(MakeShared<FJsonValueString>(Item));
					}
					Entry->SetArrayField(TEXT("deferred"), Deferred);
				}
				OutPlanned.Add(MakeShared<FJsonValueObject>(Entry));
			}
			return bValid;
		}
	}

	bool ParseOperations(const FJsonObject& Params, TArray<FOperation>& OutOps, FAnimMcpError& OutError)
	{
		const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
		if (!Params.TryGetArrayField(TEXT("operations"), Array) || !Array)
		{
			OutError = BadRequest(TEXT("'operations' array is required"));
			return false;
		}
		if (Array->IsEmpty())
		{
			OutError = BadRequest(TEXT("'operations' is empty"));
			return false;
		}
		OutOps.Reset();
		for (int32 Index = 0; Index < Array->Num(); ++Index)
		{
			const TSharedPtr<FJsonValue>& Value = (*Array)[Index];
			if (!Value.IsValid() || Value->Type != EJson::Object)
			{
				OutError = BadRequest(FString::Printf(TEXT("operations[%d] is not an object"), Index));
				return false;
			}
			FOperation Op;
			Op.Index = Index;
			Op.Json = Value->AsObject();
			if (!Op.Json->TryGetStringField(TEXT("op"), Op.Op) || Op.Op.IsEmpty())
			{
				OutError = BadRequest(FString::Printf(TEXT("operations[%d] has no 'op'"), Index));
				return false;
			}
			if (Op.Op.StartsWith(TEXT("add_")) || Op.Op == TEXT("bind_property_function"))
			{
				Op.Json->TryGetStringField(TEXT("ref"), Op.Ref);
			}
			OutOps.Add(MoveTemp(Op));
		}
		return true;
	}

	TSharedRef<FJsonObject> Preview(const UStateTree& Tree, const TArray<FOperation>& Ops)
	{
		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetStringField(TEXT("revision"), AnimMcpStateTreeAsset::GetRevision(Tree));
		Result->SetStringField(TEXT("compile_state"), AnimMcpStateTreeAsset::GetCompileState(Tree));

		const UStateTreeEditorData* Data = AnimMcpStateTreeAsset::GetEditorData(&Tree);
		if (!Data || !Data->Schema)
		{
			Result->SetBoolField(TEXT("valid"), false);
			return Result;
		}
		FPlan Plan;
		TArray<TSharedPtr<FJsonValue>> Planned;
		FAnimMcpError FirstError;
		const bool bValid = BuildPlan(*Data, Ops, Plan, Planned, FirstError);
		Result->SetBoolField(TEXT("valid"), bValid);
		Result->SetArrayField(TEXT("planned"), Planned);
		return Result;
	}

	TSharedPtr<FJsonObject> Apply(UStateTree& Tree, const TArray<FOperation>& Ops, const FString& ExpectedRevision, const bool bCompile, const bool bSave, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		check(IsInGameThread());

		UStateTreeEditorData* Data = AnimMcpStateTreeAsset::GetEditorData(&Tree);
		if (!Data || !Data->Schema)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("'%s' has no editor data or schema"), *Tree.GetPathName()));
			return nullptr;
		}

		// §5 1 ~ 2 — 리비전 · 더티
		const FString RevisionBefore = AnimMcpStateTreeAsset::GetRevision(Tree);
		if (!ExpectedRevision.IsEmpty() && ExpectedRevision != RevisionBefore)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("expected"), ExpectedRevision);
			Details->SetStringField(TEXT("actual"), RevisionBefore);
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::RevisionMismatch, TEXT("StateTree changed since the plan was made; re-inspect and retry"), Details);
			return nullptr;
		}
		if (Tree.GetPackage()->IsDirty())
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetDirty, FString::Printf(TEXT("'%s' has unsaved changes — save it in the editor or revert_state_tree first (a never-saved asset counts as unsaved)"), *Tree.GetPathName()));
			return nullptr;
		}

		// §5 3 — 변경 없이 해석
		FPlan Plan;
		TArray<TSharedPtr<FJsonValue>> Planned;
		FAnimMcpError PlanError;
		if (!BuildPlan(*Data, Ops, Plan, Planned, PlanError))
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("stage"), TEXT("preflight"));
			Details->SetArrayField(TEXT("planned"), Planned);
			OutError = PlanError;
			OutError.Details = Details;
			return nullptr;
		}

		const AnimMcpStateTreeAsset::FBaseline Baseline = AnimMcpStateTreeAsset::CaptureBaseline(Tree);

		// 실패 공통 — 복구하고 보고. 이 뒤로 Tree 를 쓰지 않는다(재로드면 무효)
		const auto Fail = [&Baseline, &RevisionBefore, &OutError, &Context](const TCHAR* Code, const FString& Message, const TCHAR* Stage, const TSharedRef<FJsonObject>& Details)
		{
			const AnimMcpStateTreeAsset::FRollback Rollback = AnimMcpStateTreeAsset::Recover(Baseline);
			Details->SetStringField(TEXT("stage"), Stage);
			Details->SetStringField(TEXT("revision_before"), RevisionBefore);
			Details->SetObjectField(TEXT("rollback"), Rollback.ToJson());
			if (!Rollback.bVerified)
			{
				UE_LOG(LogAnimGraphMcp, Error, TEXT("Rollback of %s not verified (%s -> %s, method %s)"), *Baseline.ObjectPath, *RevisionBefore, *Rollback.Revision, *Rollback.Method);
				Context.AddDiagnostic(TEXT("error"), TEXT("ROLLBACK_UNVERIFIED"), TEXT("Asset revision differs after rollback; inspect it before continuing"));
			}
			OutError = FAnimMcpError::Make(Code, Message, Details);
		};

		// §5 4 — 트랜잭션은 컴파일 전에 닫는다. 실패해도 Cancel 하지 않는다: 닫아야 Undo 대상이 된다
		FApplyContext Ctx;
		Ctx.Data = Data;
		int32 FailedIndex = INDEX_NONE;
		FAnimMcpError StepError;
		{
			FScopedTransaction Transaction(LOCTEXT("ApplyOperations", "AnimGraphMcp: apply StateTree operations"));
			for (const FPlannedStep& Step : Plan.Steps)
			{
				if (!Step.Run(Ctx, StepError))
				{
					FailedIndex = Step.Index;
					break;
				}
			}
		}
		if (FailedIndex != INDEX_NONE)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetNumberField(TEXT("failed_index"), FailedIndex);
			if (StepError.Details.IsValid())
			{
				Details->SetObjectField(TEXT("cause"), StepError.Details);
			}
			Fail(*StepError.Code, FString::Printf(TEXT("operations[%d] failed: %s"), FailedIndex, *StepError.Message), TEXT("apply"), Details);
			return nullptr;
		}

		// §5 5 ~ 6 — 컴파일 실패와 조용한 제거는 적용 실패다. 컴파일 성공은 바인딩이 남았다는 증거가 아니다(§9)
		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		if (bCompile)
		{
			AnimMcpStateTreeAsset::FCompileResult Compiled = AnimMcpStateTreeAsset::Compile(Tree);
			if (!Compiled.bOk || Compiled.Fixups.Num() > 0)
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetArrayField(TEXT("messages"), Compiled.Messages);
				Details->SetArrayField(TEXT("fixups"), Compiled.Fixups);
				if (!Compiled.bOk)
				{
					Fail(AnimMcpErrorCodes::CompileFailed, TEXT("StateTree compile failed; the batch was rolled back"), TEXT("compile"), Details);
				}
				else
				{
					Fail(AnimMcpErrorCodes::CompileFixups, TEXT("The compiler silently removed bindings or nodes; the batch was rolled back"), TEXT("fixups"), Details);
				}
				return nullptr;
			}
			Result->SetObjectField(TEXT("compile"), Compiled.ToJson());
		}
		else
		{
			TSharedRef<FJsonObject> Skipped = AnimMcpJson::MakeObject();
			Skipped->SetBoolField(TEXT("ran"), false);
			Result->SetObjectField(TEXT("compile"), Skipped);
		}

		// §5 7
		if (bSave)
		{
			FAnimMcpError SaveError;
			if (!AnimMcpStateTreeAsset::Save(Tree, SaveError))
			{
				Fail(*SaveError.Code, SaveError.Message, TEXT("save"), AnimMcpJson::MakeObject());
				return nullptr;
			}
		}
		AnimMcpStateTreeAsset::NotifyEditors(Tree);

		Result->SetStringField(TEXT("revision_before"), RevisionBefore);
		Result->SetStringField(TEXT("revision_after"), AnimMcpStateTreeAsset::GetRevision(Tree));
		Result->SetStringField(TEXT("compile_state"), AnimMcpStateTreeAsset::GetCompileState(Tree));
		Result->SetBoolField(TEXT("saved"), bSave);
		Result->SetNumberField(TEXT("applied"), Plan.Steps.Num());
		TSharedRef<FJsonObject> Refs = AnimMcpJson::MakeObject();
		for (const TPair<FString, FRefEntry>& Pair : Plan.Refs)
		{
			Refs->SetStringField(Pair.Key, Ctx.Resolve(Pair.Value.Id).ToString());
		}
		Result->SetObjectField(TEXT("refs"), Refs);
		return Result;
	}
}

#undef LOCTEXT_NAMESPACE
