#include "AnimMcpPropertyBinding.h"

#include "AnimMcpGraphMutator.h"
#include "AnimMcpLog.h"
#include "Animation/AnimBlueprint.h"
#include "Bridge/AnimMcpTypes.h"
#include "EdGraph/EdGraphPin.h"
#include "Features/IModularFeatures.h"
#include "IPropertyAccessEditor.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "UObject/UnrealType.h"

namespace AnimMcpPropertyBinding
{
	namespace
	{
		const FName PropertyAccessEditorFeature(TEXT("PropertyAccessEditor"));
		const FName BindingPropertyName(TEXT("Binding"));
		const FName MapPropertyName(TEXT("PropertyBindings"));

		/** 노드의 private `Binding` 객체 — FObjectProperty 로 */
		UObject* BindingObject(const UAnimGraphNode_Base* Node)
		{
			FObjectPropertyBase* Prop = CastField<FObjectPropertyBase>(UAnimGraphNode_Base::StaticClass()->FindPropertyByName(BindingPropertyName));
			return Prop ? Prop->GetObjectPropertyValue_InContainer(Node) : nullptr;
		}

		/** 바인딩 객체의 `PropertyBindings` — 키 FName · 값 FAnimGraphNodePropertyBinding 인지 확인 */
		FMapProperty* BindingsMap(const UObject* BindingObj)
		{
			if (!BindingObj)
			{
				return nullptr;
			}
			FMapProperty* Map = CastField<FMapProperty>(BindingObj->GetClass()->FindPropertyByName(MapPropertyName));
			if (!Map || !CastField<FNameProperty>(Map->KeyProp))
			{
				return nullptr;
			}
			const FStructProperty* ValueProp = CastField<FStructProperty>(Map->ValueProp);
			if (!ValueProp || ValueProp->Struct != FAnimGraphNodePropertyBinding::StaticStruct())
			{
				return nullptr;
			}
			return Map;
		}

		struct FMapAccess
		{
			UObject* Obj = nullptr;
			FMapProperty* Map = nullptr;
			bool IsValid() const { return Obj && Map; }
			FScriptMapHelper Helper() const { return FScriptMapHelper(Map, Map->ContainerPtrToValuePtr<void>(Obj)); }
		};

		FMapAccess Access(const UAnimGraphNode_Base* Node)
		{
			FMapAccess A;
			A.Obj = BindingObject(Node);
			A.Map = BindingsMap(A.Obj);
			return A;
		}

		UAnimBlueprint* BlueprintOf(const UAnimGraphNode_Base* Node)
		{
			return Cast<UAnimBlueprint>(FBlueprintEditorUtils::FindBlueprintForNode(Node));
		}

		FAnimMcpError Reason(const FString& Message, const TCHAR* ReasonCode)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("reason"), ReasonCode);
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
		}

		const TCHAR* TypeName(EAnimGraphNodePropertyBindingType Type)
		{
			switch (Type)
			{
			case EAnimGraphNodePropertyBindingType::Function: return TEXT("Function");
			case EAnimGraphNodePropertyBindingType::Property: return TEXT("Property");
			default: return TEXT("None");
			}
		}
	}

	bool IsAvailable()
	{
		return IModularFeatures::Get().IsModularFeatureAvailable(PropertyAccessEditorFeature);
	}

	bool ReadBindings(const UAnimGraphNode_Base* Node, TArray<FBindingInfo>& Out)
	{
		Out.Reset();
		const FMapAccess A = Access(Node);
		if (!A.IsValid())
		{
			return false;
		}
		FScriptMapHelper Helper = A.Helper();
		for (int32 i = 0; i < Helper.GetMaxIndex(); ++i)
		{
			if (!Helper.IsValidIndex(i))
			{
				continue;
			}
			const FName* Key = reinterpret_cast<const FName*>(Helper.GetKeyPtr(i));
			const FAnimGraphNodePropertyBinding* Value = reinterpret_cast<const FAnimGraphNodePropertyBinding*>(Helper.GetValuePtr(i));
			FBindingInfo Info;
			Info.Name = *Key;
			Info.Path = Value->PropertyPath;
			Info.PathText = Value->PathAsText.ToString();
			Info.Type = TypeName(Value->Type);
			Info.Context = Value->ContextId;
			Info.bPromotion = Value->bIsPromotion;
			Info.bBound = Value->bIsBound;
			Out.Add(Info);
		}
		Out.Sort([](const FBindingInfo& L, const FBindingInfo& R) { return L.Name.LexicalLess(R.Name); });
		return true;
	}

	bool FindRaw(const UAnimGraphNode_Base* Node, FName Name, FAnimGraphNodePropertyBinding& Out)
	{
		const FMapAccess A = Access(Node);
		if (!A.IsValid())
		{
			return false;
		}
		FScriptMapHelper Helper = A.Helper();
		if (const uint8* ValuePtr = Helper.FindValueFromHash(&Name))
		{
			Out = *reinterpret_cast<const FAnimGraphNodePropertyBinding*>(ValuePtr);
			return true;
		}
		return false;
	}

	bool ValidateBind(UAnimGraphNode_Base* Node, FName Property, const TArray<FString>& Path, FString& OutType, FAnimMcpError& OutError)
	{
		if (!IsAvailable())
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("PropertyAccessEditor modular feature is not available"));
			return false;
		}
		if (Path.Num() == 0)
		{
			OutError = Reason(TEXT("bind_pin requires a non-empty 'path' (array of property/function names, or \"A.B\")"), TEXT("EMPTY_PATH"));
			return false;
		}
		UAnimBlueprint* Blueprint = BlueprintOf(Node);
		if (!Blueprint || !Blueprint->SkeletonGeneratedClass)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("Node has no Animation Blueprint / skeleton class to resolve the binding against"));
			return false;
		}
		// 노출 가능 핀이어야 한다 (에디터의 바인딩 메뉴도 optional pin 에만 뜬다)
		if (AnimMcpGraphMutator::FindOptionalPinIndex(Node, Property, OutError) == INDEX_NONE)
		{
			return false;
		}
		FProperty* PinProperty = Node->GetPinProperty(Property);
		if (!PinProperty)
		{
			OutError = Reason(FString::Printf(TEXT("'%s' is not a property of %s"), *Property.ToString(), *Node->GetClass()->GetName()), TEXT("NO_PIN_PROPERTY"));
			return false;
		}
		if (const UEdGraphPin* Pin = Node->FindPin(Property))
		{
			if (Pin->LinkedTo.Num() > 0)
			{
				OutError = Reason(FString::Printf(TEXT("Pin '%s' is linked; disconnect it before binding (the editor would break the link silently)"), *Property.ToString()), TEXT("PIN_LINKED"));
				return false;
			}
		}

		IPropertyAccessEditor& PAE = IModularFeatures::Get().GetModularFeature<IPropertyAccessEditor>(PropertyAccessEditorFeature);
		FProperty* Leaf = nullptr;
		int32 ArrayIndex = INDEX_NONE;
		const FPropertyAccessResolveResult Resolved = PAE.ResolvePropertyAccess(Blueprint->SkeletonGeneratedClass, Path, Leaf, ArrayIndex);
		if (Resolved.Result != EPropertyAccessResolveResult::Succeeded || !Leaf)
		{
			OutError = Reason(FString::Printf(TEXT("Binding path '%s' does not resolve on %s (BlueprintVisible property or BlueprintPure function of the AnimInstance class chain)"),
				*FString::Join(Path, TEXT(".")), *Blueprint->SkeletonGeneratedClass->GetName()), TEXT("PATH_UNRESOLVED"));
			return false;
		}
		// 마지막 세그먼트가 함수인지 — 콜백 오버로드로 본다
		bool bLeafIsFunction = false;
		{
			IPropertyAccessEditor::FResolvePropertyAccessArgs Args;
			Args.PropertyFunction = [&bLeafIsFunction](int32, FProperty*, int32) { bLeafIsFunction = false; };
			Args.ArrayFunction = [&bLeafIsFunction](int32, FArrayProperty*, int32) { bLeafIsFunction = false; };
			Args.FunctionFunction = [&bLeafIsFunction](int32, UFunction*, FProperty*) { bLeafIsFunction = true; };
			PAE.ResolvePropertyAccess(Blueprint->SkeletonGeneratedClass, Path, Args);
		}
		const EPropertyAccessCompatibility Compat = PAE.GetPropertyCompatibility(Leaf, PinProperty);
		if (Compat == EPropertyAccessCompatibility::Incompatible)
		{
			OutError = Reason(FString::Printf(TEXT("'%s' (%s) is not compatible with pin '%s' (%s)"), *FString::Join(Path, TEXT(".")), *Leaf->GetCPPType(), *Property.ToString(), *PinProperty->GetCPPType()), TEXT("TYPE_INCOMPATIBLE"));
			return false;
		}
		OutType = bLeafIsFunction ? TEXT("Function") : TEXT("Property");
		return true;
	}

	bool Bind(UAnimGraphNode_Base* Node, FName Property, const TArray<FString>& Path, bool& bOutHadOld, FAnimGraphNodePropertyBinding& OutOld, bool& bOutPinWasHidden, FAnimMcpError& OutError)
	{
		FString Type;
		if (!ValidateBind(Node, Property, Path, Type, OutError))
		{
			return false;
		}
		const FMapAccess A = Access(Node);
		if (!A.IsValid())
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("Node %s has no binding object (PropertyBindings map not found by reflection)"), *Node->GetName()));
			return false;
		}
		UAnimBlueprint* Blueprint = BlueprintOf(Node);
		IPropertyAccessEditor& PAE = IModularFeatures::Get().GetModularFeature<IPropertyAccessEditor>(PropertyAccessEditorFeature);

		Node->Modify();
		A.Obj->Modify();

		// 핀 노출 — 바인딩이 있으면 핀은 보여야 한다 (OnAddBinding 의 OnSetPinVisibility)
		const int32 OptionalIndex = AnimMcpGraphMutator::FindOptionalPinIndex(Node, Property, OutError);
		bOutPinWasHidden = OptionalIndex != INDEX_NONE && !Node->ShowPinForProperties[OptionalIndex].bShowPin;
		if (bOutPinWasHidden)
		{
			Node->SetPinVisibility(true, OptionalIndex);
		}

		bOutHadOld = FindRaw(Node, Property, OutOld);

		FAnimGraphNodePropertyBinding NewBinding;
		NewBinding.PropertyName = Property;
		NewBinding.PropertyPath = Path;
		NewBinding.PathAsText = PAE.MakeTextPath(Path, Blueprint->SkeletonGeneratedClass);
		NewBinding.Type = Type == TEXT("Function") ? EAnimGraphNodePropertyBindingType::Function : EAnimGraphNodePropertyBindingType::Property;
		NewBinding.bIsBound = true;
		{
			FScriptMapHelper Helper = A.Helper();
			Helper.AddPair(&Property, &NewBinding);   // 키가 있으면 값 덮어쓰기
		}

		// PinType/PromotedPinType/bIsPromotion 은 ReconstructNode → OnReconstructNode → RecalculateBindingType 이 채운다
		Node->ReconstructNode();
		FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
		UE_LOG(LogAnimGraphMcp, Log, TEXT("Bound %s.%s -> %s (%s)"), *Node->GetName(), *Property.ToString(), *FString::Join(Path, TEXT(".")), *Type);
		return true;
	}

	bool Unbind(UAnimGraphNode_Base* Node, FName Property, FAnimGraphNodePropertyBinding& OutOld, FAnimMcpError& OutError)
	{
		if (!FindRaw(Node, Property, OutOld))
		{
			OutError = Reason(FString::Printf(TEXT("Pin '%s' of %s has no property binding"), *Property.ToString(), *Node->GetClass()->GetName()), TEXT("NOT_BOUND"));
			return false;
		}
		const FMapAccess A = Access(Node);
		Node->Modify();
		A.Obj->Modify();
		Node->RemoveBindings(Property);
		Node->ReconstructNode();
		if (UAnimBlueprint* Blueprint = BlueprintOf(Node))
		{
			FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
		}
		return true;
	}

	void WriteRaw(UAnimGraphNode_Base* Node, const FAnimGraphNodePropertyBinding& Binding)
	{
		const FMapAccess A = Access(Node);
		if (!A.IsValid())
		{
			return;
		}
		A.Obj->Modify();
		FScriptMapHelper Helper = A.Helper();
		Helper.AddPair(&Binding.PropertyName, &Binding);
		Node->ReconstructNode();
	}

	void RemoveRaw(UAnimGraphNode_Base* Node, FName Name)
	{
		const FMapAccess A = Access(Node);
		if (!A.IsValid())
		{
			return;
		}
		A.Obj->Modify();
		Node->RemoveBindings(Name);
		Node->ReconstructNode();
	}

	void AppendRevision(const UAnimGraphNode_Base* Node, FString& Out)
	{
		TArray<FBindingInfo> Bindings;
		if (!ReadBindings(Node, Bindings))
		{
			return;
		}
		for (const FBindingInfo& B : Bindings)
		{
			Out += FString::Printf(TEXT("B|%s|%s|%s|%s\n"), *B.Name.ToString(), *FString::Join(B.Path, TEXT(".")), *B.Type, *B.Context.ToString());
		}
	}
}
