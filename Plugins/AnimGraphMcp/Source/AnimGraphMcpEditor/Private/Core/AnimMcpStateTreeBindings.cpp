#include "AnimMcpStateTreeBindings.h"

#include "Bridge/AnimMcpTypes.h"
#include "PropertyBindingDataView.h"
#include "PropertyBindingExtension.h"
#include "PropertyBindingTypes.h"
#include "StateTreeEditorData.h"
#include "StateTreePropertyBindings.h"
#include "StateTreeTypes.h"
#include "StructUtils/InstancedStruct.h"
#include "UObject/UnrealType.h"

namespace AnimMcpStateTreeBindings
{
	namespace
	{
		FCheck Fail(const TCHAR* Code, const FString& Detail)
		{
			FCheck Check;
			Check.Code = Code;
			Check.Detail = Detail;
			return Check;
		}

		/** 계획된 노드는 구조체로, 기존 구조체는 값 뷰로 푼다. 컨텍스트는 값 뷰의 메모리가 없어 타입으로만 푼다(E4) */
		bool Resolve(const UStateTreeEditorData& Data, const FEndpoint& End, TArray<FPropertyBindingPathIndirection>& OutSteps, const UStruct*& OutStruct, FString& OutError)
		{
			if (End.PlannedStruct)
			{
				OutStruct = End.PlannedStruct;
				return End.Path.ResolveIndirections(End.PlannedStruct, OutSteps, &OutError);
			}

			TInstancedStruct<FPropertyBindingBindableStructDescriptor> Desc;
			if (!Data.GetBindableStructByID(End.Path.GetStructID(), Desc))
			{
				OutError = FString::Printf(TEXT("struct %s does not exist in this tree"), *End.Path.GetStructID().ToString());
				return false;
			}
			OutStruct = Desc.Get().Struct;
			FPropertyBindingDataView View;
			Data.GetBindingDataViewByID(End.Path.GetStructID(), View);
			return View.IsValid()
				? End.Path.ResolveIndirectionsWithValue(View, OutSteps, &OutError)
				: End.Path.ResolveIndirections(OutStruct, OutSteps, &OutError);
		}

		FString UsageName(const EStateTreePropertyUsage Usage)
		{
			switch (Usage)
			{
			case EStateTreePropertyUsage::Context: return TEXT("Context");
			case EStateTreePropertyUsage::Input: return TEXT("Input");
			case EStateTreePropertyUsage::Parameter: return TEXT("Parameter");
			case EStateTreePropertyUsage::Output: return TEXT("Output");
			default: return TEXT("Invalid");
			}
		}

		FString SourceKindName(const EStateTreeBindableStructSource Source)
		{
			switch (Source)
			{
			case EStateTreeBindableStructSource::Context: return TEXT("context");
			case EStateTreeBindableStructSource::Parameter: return TEXT("parameter");
			case EStateTreeBindableStructSource::Evaluator: return TEXT("evaluator");
			case EStateTreeBindableStructSource::GlobalTask: return TEXT("global_task");
			case EStateTreeBindableStructSource::StateParameter: return TEXT("state_parameter");
			case EStateTreeBindableStructSource::Task: return TEXT("task");
			case EStateTreeBindableStructSource::Condition: return TEXT("condition");
			case EStateTreeBindableStructSource::Consideration: return TEXT("consideration");
			case EStateTreeBindableStructSource::TransitionEvent: return TEXT("transition_event");
			case EStateTreeBindableStructSource::StateEvent: return TEXT("state_event");
			case EStateTreeBindableStructSource::PropertyFunction: return TEXT("property_function");
			case EStateTreeBindableStructSource::Transition: return TEXT("transition");
			default: return TEXT("unknown");
			}
		}
	}

	FCheck CheckPathsAndTypes(const UStateTreeEditorData& Data, const FEndpoint& Source, const FEndpoint& Target)
	{
		TArray<FPropertyBindingPathIndirection> SourceSteps;
		const UStruct* SourceStruct = nullptr;
		FString SourceError;
		if (!Resolve(Data, Source, SourceSteps, SourceStruct, SourceError))
		{
			return Fail(AnimMcpErrorCodes::BadSourcePath, SourceError);
		}

		TArray<FPropertyBindingPathIndirection> TargetSteps;
		const UStruct* TargetStruct = nullptr;
		FString TargetError;
		if (Target.Path.IsPathEmpty())
		{
			return Fail(AnimMcpErrorCodes::BadTargetPath, TEXT("target path is empty"));
		}
		if (!Resolve(Data, Target, TargetSteps, TargetStruct, TargetError) || TargetSteps.IsEmpty())
		{
			return Fail(AnimMcpErrorCodes::BadTargetPath, TargetError);
		}

		// Context 는 컴파일러가 타입으로 자동 바인딩하고(§2-7) Output 은 소스 쪽 프로퍼티다
		const EStateTreePropertyUsage TargetUsage = UE::StateTree::GetUsageFromMetaData(TargetSteps[0].GetProperty());
		if (TargetUsage == EStateTreePropertyUsage::Context || TargetUsage == EStateTreePropertyUsage::Output)
		{
			return Fail(AnimMcpErrorCodes::BadTargetPath, FString::Printf(TEXT("target '%s' is a %s property and cannot be bound"), *TargetSteps[0].GetProperty()->GetName(), *UsageName(TargetUsage)));
		}

		// D-6 — 컴파일은 되지만 사용자가 에디터에서 같은 바인딩을 다시 만들 수 없다
		for (const FPropertyBindingPathIndirection& Step : SourceSteps)
		{
			if (Step.GetProperty() && !UE::PropertyBinding::IsPropertyBindable(*Step.GetProperty()))
			{
				return Fail(AnimMcpErrorCodes::NotBindable, FString::Printf(TEXT("'%s' is not in the engine binding menu — expose it in C++ (AllowPrivateAccess) or through an Evaluator output"), *Step.GetProperty()->GetName()));
			}
		}

		const FProperty* TargetLeaf = TargetSteps.Last().GetProperty();
		if (SourceSteps.IsEmpty())
		{
			// 경로 없음 = 구조체 자체(컨텍스트 Actor 를 객체 입력에 묶는 경우)
			const FObjectPropertyBase* ObjectTarget = CastField<FObjectPropertyBase>(TargetLeaf);
			if (!SourceStruct || !ObjectTarget || !SourceStruct->IsChildOf(ObjectTarget->PropertyClass))
			{
				return Fail(AnimMcpErrorCodes::IncompatibleTypes, FString::Printf(TEXT("%s -> %s"), *GetNameSafe(SourceStruct), *TargetLeaf->GetCPPType()));
			}
			return FCheck();
		}
		if (UE::PropertyBinding::GetPropertyCompatibility(SourceSteps.Last().GetProperty(), TargetLeaf) == UE::PropertyBinding::EPropertyCompatibility::Incompatible)
		{
			return Fail(AnimMcpErrorCodes::IncompatibleTypes, FString::Printf(TEXT("%s -> %s"), *SourceSteps.Last().GetProperty()->GetCPPType(), *TargetLeaf->GetCPPType()));
		}
		return FCheck();
	}

	FCheck CheckScope(const UStateTreeEditorData& Data, const FPropertyBindingPath& Source, const FPropertyBindingPath& Target)
	{
		TArray<TInstancedStruct<FPropertyBindingBindableStructDescriptor>> Accessible;
		Data.GetBindableStructs(Target.GetStructID(), Accessible);
		for (const TInstancedStruct<FPropertyBindingBindableStructDescriptor>& Desc : Accessible)
		{
			if (Desc.Get().ID == Source.GetStructID())
			{
				return FCheck();
			}
		}
		return Fail(AnimMcpErrorCodes::BindingOutOfScope, FString::Printf(TEXT("%s is not reachable from the target (%d candidates; see list_state_tree_bindable_sources)"), *Source.GetStructID().ToString(), Accessible.Num()));
	}

	FCheck Preflight(const UStateTreeEditorData& Data, const FPropertyBindingPath& Source, const FPropertyBindingPath& Target)
	{
		FCheck Scope = CheckScope(Data, Source, Target);
		if (!Scope.IsOk())
		{
			return Scope;
		}
		FEndpoint SourceEnd;
		SourceEnd.Path = Source;
		FEndpoint TargetEnd;
		TargetEnd.Path = Target;
		return CheckPathsAndTypes(Data, SourceEnd, TargetEnd);
	}

	TArray<TSharedPtr<FJsonValue>> DescribeProperties(const UStruct* Struct)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		if (!Struct)
		{
			return Out;
		}
		for (TFieldIterator<FProperty> It(Struct); It; ++It)
		{
			const FProperty* Property = *It;
			if (!Property->HasAnyPropertyFlags(CPF_Edit))
			{
				continue;
			}
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("name"), Property->GetName());
			Obj->SetStringField(TEXT("type"), Property->GetCPPType());
			Obj->SetStringField(TEXT("usage"), UsageName(UE::StateTree::GetUsageFromMetaData(Property)));
			Obj->SetBoolField(TEXT("bindable"), UE::PropertyBinding::IsPropertyBindable(*Property));
			Out.Add(MakeShared<FJsonValueObject>(Obj));
		}
		return Out;
	}

	TSharedRef<FJsonObject> ListSources(const UStateTreeEditorData& Data, const FGuid& TargetId)
	{
		TArray<TInstancedStruct<FPropertyBindingBindableStructDescriptor>> Accessible;
		Data.GetBindableStructs(TargetId, Accessible);

		TArray<TSharedPtr<FJsonValue>> Sources;
		for (const TInstancedStruct<FPropertyBindingBindableStructDescriptor>& Item : Accessible)
		{
			const FStateTreeBindableStructDesc& Desc = Item.Get<FStateTreeBindableStructDesc>();
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("id"), Desc.ID.ToString());
			Obj->SetStringField(TEXT("name"), Desc.Name.ToString());
			Obj->SetStringField(TEXT("kind"), SourceKindName(Desc.DataSource));
			Obj->SetStringField(TEXT("state_path"), Desc.StatePath);
			Obj->SetStringField(TEXT("struct"), GetPathNameSafe(Desc.Struct));

			int32 Hidden = 0;
			TArray<TSharedPtr<FJsonValue>> Visible;
			for (const TSharedPtr<FJsonValue>& Property : DescribeProperties(Desc.Struct))
			{
				if (Property->AsObject()->GetBoolField(TEXT("bindable")))
				{
					Visible.Add(Property);
				}
				else
				{
					++Hidden;
				}
			}
			Obj->SetArrayField(TEXT("properties"), Visible);
			Obj->SetNumberField(TEXT("hidden_properties"), Hidden);
			Sources.Add(MakeShared<FJsonValueObject>(Obj));
		}

		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetStringField(TEXT("target"), TargetId.ToString());
		Result->SetArrayField(TEXT("sources"), Sources);
		return Result;
	}
}
