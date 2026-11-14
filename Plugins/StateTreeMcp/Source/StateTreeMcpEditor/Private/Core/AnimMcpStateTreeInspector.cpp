#include "AnimMcpStateTreeInspector.h"

#include "Core/AnimMcpPropertyValues.h"
#include "AnimMcpStateTreeAsset.h"
#include "AnimMcpStateTreeBindings.h"
#include "Bridge/AnimMcpTypes.h"
#include "Modules/ModuleManager.h"
#include "PropertyBindingBinding.h"
#include "StateTree.h"
#include "StateTreeConditionBase.h"
#include "StateTreeEditorData.h"
#include "StateTreeEditorModule.h"
#include "StateTreeEditorPropertyBindings.h"
#include "StateTreeEvaluatorBase.h"
#include "StateTreeNodeClassCache.h"
#include "StateTreePropertyBindings.h"
#include "StateTreePropertyFunctionBase.h"
#include "StateTreeSchema.h"
#include "StateTreeState.h"
#include "StateTreeTaskBase.h"
#include "StateTreeTypes.h"
#include "UObject/Package.h"
#include "UObject/UnrealType.h"

namespace AnimMcpStateTreeInspector
{
	namespace
	{
		template <typename TEnum>
		FString EnumName(const TEnum Value)
		{
			return StaticEnum<TEnum>()->GetNameStringByValue(static_cast<int64>(Value));
		}

		void AddValues(FJsonObject& Values, const UStruct* Struct, const void* Memory, UObject* Owner, const bool bInstance)
		{
			if (!Struct || !Memory)
			{
				return;
			}
			for (TFieldIterator<FProperty> It(Struct); It; ++It)
			{
				const FProperty* Property = *It;
				if (!Property->HasAnyPropertyFlags(CPF_Edit))
				{
					continue;
				}
				if (bInstance)
				{
					const EStateTreePropertyUsage Usage = UE::StateTree::GetUsageFromMetaData(Property);
					if (Usage == EStateTreePropertyUsage::Context || Usage == EStateTreePropertyUsage::Output)
					{
						continue;
					}
				}
				Values.SetField(Property->GetName(), AnimMcpPropertyRules::PropertyToJson(Property, Property->ContainerPtrToValuePtr<void>(Memory), Owner));
			}
		}

		TSharedRef<FJsonObject> NodeToJson(const FStateTreeEditorNode& Node)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("id"), Node.ID.ToString());
			Obj->SetStringField(TEXT("name"), Node.GetName().ToString());
			Obj->SetStringField(TEXT("type"), GetPathNameSafe(Node.Node.GetScriptStruct()));
			const FStateTreeDataView Instance = Node.GetInstance();
			Obj->SetStringField(TEXT("instance_type"), GetPathNameSafe(Instance.GetStruct()));
			Obj->SetStringField(TEXT("operand"), EnumName(Node.ExpressionOperand));
			Obj->SetNumberField(TEXT("indent"), Node.ExpressionIndent);

			// 평평한 모양 — op 의 values 가 받는 이름 그대로. 인스턴스가 먼저(같은 이름이면 인스턴스를 쓴다)
			TSharedRef<FJsonObject> Values = AnimMcpJson::MakeObject();
			AddValues(*Values, Node.Node.GetScriptStruct(), Node.Node.GetMemory(), nullptr, /*bInstance*/ false);
			AddValues(*Values, Instance.GetStruct(), Instance.GetMemory(), Node.InstanceObject.Get(), /*bInstance*/ true);
			Obj->SetObjectField(TEXT("values"), Values);
			return Obj;
		}

		TArray<TSharedPtr<FJsonValue>> NodesToJson(const TArray<FStateTreeEditorNode>& Nodes)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			for (const FStateTreeEditorNode& Node : Nodes)
			{
				Out.Add(MakeShared<FJsonValueObject>(NodeToJson(Node)));
			}
			return Out;
		}

		TSharedRef<FJsonObject> TransitionTargetToJson(const FStateTreeStateLink& Link)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			switch (Link.LinkType)
			{
			case EStateTreeTransitionType::GotoState:
				Obj->SetStringField(TEXT("kind"), TEXT("state"));
				Obj->SetStringField(TEXT("state_id"), Link.ID.ToString());
				Obj->SetStringField(TEXT("state_name"), Link.Name.ToString());
				break;
			case EStateTreeTransitionType::Succeeded: Obj->SetStringField(TEXT("kind"), TEXT("succeeded")); break;
			case EStateTreeTransitionType::Failed: Obj->SetStringField(TEXT("kind"), TEXT("failed")); break;
			case EStateTreeTransitionType::NextState: Obj->SetStringField(TEXT("kind"), TEXT("next_state")); break;
			case EStateTreeTransitionType::NextSelectableState: Obj->SetStringField(TEXT("kind"), TEXT("next_selectable_state")); break;
			default: Obj->SetStringField(TEXT("kind"), TEXT("none")); break;
			}
			return Obj;
		}

		TSharedRef<FJsonObject> TransitionToJson(const FStateTreeTransition& Transition)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("id"), Transition.ID.ToString());
			Obj->SetStringField(TEXT("trigger"), EnumName(Transition.Trigger));
			Obj->SetObjectField(TEXT("target"), TransitionTargetToJson(Transition.State));
			Obj->SetStringField(TEXT("event_tag"), Transition.RequiredEvent.Tag.ToString());
			Obj->SetStringField(TEXT("priority"), EnumName(Transition.Priority));
			Obj->SetBoolField(TEXT("enabled"), Transition.bTransitionEnabled);
			Obj->SetNumberField(TEXT("delay"), Transition.bDelayTransition ? Transition.DelayDuration : 0.0);
			Obj->SetArrayField(TEXT("conditions"), NodesToJson(Transition.Conditions));
			return Obj;
		}

		TSharedRef<FJsonObject> StateToJson(const UStateTreeState& State)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("id"), State.ID.ToString());
			Obj->SetStringField(TEXT("name"), State.Name.ToString());
			Obj->SetStringField(TEXT("path"), State.GetPath());
			Obj->SetStringField(TEXT("type"), EnumName(State.Type));
			Obj->SetStringField(TEXT("selection"), EnumName(State.SelectionBehavior));
			Obj->SetStringField(TEXT("tasks_completion"), EnumName(State.TasksCompletion));
			Obj->SetBoolField(TEXT("enabled"), State.bEnabled);
			Obj->SetStringField(TEXT("tag"), State.Tag.ToString());
			Obj->SetNumberField(TEXT("weight"), State.Weight);
			Obj->SetNumberField(TEXT("custom_tick_rate"), State.bHasCustomTickRate ? State.CustomTickRate : 0.0);
			Obj->SetStringField(TEXT("required_event_to_enter"), State.bHasRequiredEventToEnter ? State.RequiredEventToEnter.Tag.ToString() : FString());
			Obj->SetArrayField(TEXT("enter_conditions"), NodesToJson(State.EnterConditions));
			Obj->SetArrayField(TEXT("tasks"), NodesToJson(State.Tasks));
			Obj->SetArrayField(TEXT("considerations"), NodesToJson(State.Considerations));

			TArray<TSharedPtr<FJsonValue>> Transitions;
			for (const FStateTreeTransition& Transition : State.Transitions)
			{
				Transitions.Add(MakeShared<FJsonValueObject>(TransitionToJson(Transition)));
			}
			Obj->SetArrayField(TEXT("transitions"), Transitions);

			TArray<TSharedPtr<FJsonValue>> Children;
			for (const UStateTreeState* Child : State.Children)
			{
				if (Child)
				{
					Children.Add(MakeShared<FJsonValueObject>(StateToJson(*Child)));
				}
			}
			Obj->SetArrayField(TEXT("children"), Children);
			return Obj;
		}

		TSharedRef<FJsonObject> BindingEndToJson(const FPropertyBindingPath& Path, const TCHAR* IdField)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(IdField, Path.GetStructID().ToString());
			Obj->SetStringField(TEXT("path"), Path.ToString());
			return Obj;
		}

		TArray<TSharedPtr<FJsonValue>> BindingsToJson(const UStateTreeEditorData& Data)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			Data.GetPropertyEditorBindings()->ForEachBinding([&Out](const FPropertyBindingBinding& Binding)
			{
				TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
				Obj->SetObjectField(TEXT("source"), BindingEndToJson(Binding.GetSourcePath(), TEXT("struct")));
				Obj->SetObjectField(TEXT("target"), BindingEndToJson(Binding.GetTargetPath(), TEXT("node")));
				if (const FStateTreeEditorNode* Function = Binding.GetPropertyFunctionNode().GetPtr<const FStateTreeEditorNode>())
				{
					TSharedRef<FJsonObject> FunctionObj = AnimMcpJson::MakeObject();
					FunctionObj->SetStringField(TEXT("id"), Function->ID.ToString());
					FunctionObj->SetStringField(TEXT("type"), GetPathNameSafe(Function->Node.GetScriptStruct()));
					Obj->SetObjectField(TEXT("function"), FunctionObj);
				}
				Out.Add(MakeShared<FJsonValueObject>(Obj));
			});
			return Out;
		}

		TSharedRef<FJsonObject> SchemaToJson(const UStateTreeSchema& Schema)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("class"), Schema.GetClass()->GetPathName());
			TSharedRef<FJsonObject> Properties = AnimMcpJson::MakeObject();
			for (const TCHAR* Name : { TEXT("ContextActorClass"), TEXT("AIControllerClass") })
			{
				if (const FClassProperty* Property = CastField<FClassProperty>(Schema.GetClass()->FindPropertyByName(FName(Name))))
				{
					Properties->SetStringField(Name, GetPathNameSafe(Property->GetObjectPropertyValue_InContainer(&Schema)));
				}
			}
			Obj->SetObjectField(TEXT("properties"), Properties);
			return Obj;
		}
	}

	TSharedRef<FJsonObject> Inspect(const UStateTree& Tree)
	{
		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetStringField(TEXT("asset_path"), Tree.GetPathName());
		Result->SetStringField(TEXT("revision"), AnimMcpStateTreeAsset::GetRevision(Tree));
		Result->SetStringField(TEXT("compile_state"), AnimMcpStateTreeAsset::GetCompileState(Tree));
		Result->SetBoolField(TEXT("ready_to_run"), Tree.IsReadyToRun());
		Result->SetBoolField(TEXT("package_dirty"), Tree.GetPackage()->IsDirty());

		const UStateTreeEditorData* Data = AnimMcpStateTreeAsset::GetEditorData(&Tree);
		if (!Data)
		{
			return Result;
		}

		TArray<TSharedPtr<FJsonValue>> Context;
		if (Data->Schema)
		{
			Result->SetObjectField(TEXT("schema"), SchemaToJson(*Data->Schema));
			for (const FStateTreeExternalDataDesc& Desc : Data->Schema->GetContextDataDescs())
			{
				TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
				Obj->SetStringField(TEXT("name"), Desc.Name.ToString());
				Obj->SetStringField(TEXT("id"), Desc.ID.ToString());
				Obj->SetStringField(TEXT("class"), GetPathNameSafe(Desc.Struct));
				Context.Add(MakeShared<FJsonValueObject>(Obj));
			}
		}
		Result->SetArrayField(TEXT("context"), Context);

		TSharedRef<FJsonObject> Parameters = AnimMcpJson::MakeObject();
		Parameters->SetStringField(TEXT("id"), Data->GetRootParametersGuid().ToString());
		Parameters->SetArrayField(TEXT("properties"), AnimMcpStateTreeBindings::DescribeProperties(Data->GetRootParametersPropertyBag().GetPropertyBagStruct()));
		Result->SetObjectField(TEXT("parameters"), Parameters);

		Result->SetArrayField(TEXT("evaluators"), NodesToJson(Data->Evaluators));
		Result->SetArrayField(TEXT("global_tasks"), NodesToJson(Data->GlobalTasks));

		TArray<TSharedPtr<FJsonValue>> States;
		for (const UStateTreeState* SubTree : Data->SubTrees)
		{
			if (SubTree)
			{
				States.Add(MakeShared<FJsonValueObject>(StateToJson(*SubTree)));
			}
		}
		Result->SetArrayField(TEXT("states"), States);
		Result->SetArrayField(TEXT("bindings"), BindingsToJson(*Data));
		return Result;
	}

	TSharedRef<FJsonObject> ListNodeTypes(const UStateTreeSchema& Schema, const FString& Kind)
	{
		struct FKind
		{
			const TCHAR* Name;
			const UScriptStruct* Base;
		};
		const FKind Kinds[] =
		{
			{ TEXT("task"), FStateTreeTaskBase::StaticStruct() },
			{ TEXT("condition"), FStateTreeConditionBase::StaticStruct() },
			{ TEXT("evaluator"), FStateTreeEvaluatorBase::StaticStruct() },
			{ TEXT("property_function"), FStateTreePropertyFunctionBase::StaticStruct() },
		};

		TArray<TSharedPtr<FJsonValue>> Nodes;
		TSharedPtr<FStateTreeNodeClassCache> Cache = FStateTreeEditorModule::GetModule().GetNodeClassCache();
		if (Cache.IsValid())
		{
			for (const FKind& Entry : Kinds)
			{
				if (!Kind.IsEmpty() && Kind != Entry.Name)
				{
					continue;
				}
				TArray<TSharedPtr<FStateTreeNodeClassData>> Items;
				Cache->GetScripStructs(Entry.Base, Items);
				for (const TSharedPtr<FStateTreeNodeClassData>& Item : Items)
				{
					const UScriptStruct* Struct = Item->GetScriptStruct();
					if (!Struct || Struct == Entry.Base || Struct->HasMetaData(TEXT("Hidden")) || !Schema.IsStructAllowed(Struct))
					{
						continue;
					}
					TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
					Obj->SetStringField(TEXT("kind"), Entry.Name);
					Obj->SetStringField(TEXT("type"), Struct->GetPathName());
					Obj->SetStringField(TEXT("display_name"), Struct->GetDisplayNameText().ToString());
					const UStruct* Instance = Item->GetInstanceDataStruct();
					Obj->SetStringField(TEXT("instance_type"), GetPathNameSafe(Instance));
					Obj->SetArrayField(TEXT("properties"), AnimMcpStateTreeBindings::DescribeProperties(Instance));
					Obj->SetArrayField(TEXT("node_properties"), AnimMcpStateTreeBindings::DescribeProperties(Struct));
					Nodes.Add(MakeShared<FJsonValueObject>(Obj));
				}
			}
		}

		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetStringField(TEXT("schema"), Schema.GetClass()->GetPathName());
		Result->SetArrayField(TEXT("nodes"), Nodes);
		return Result;
	}
}
