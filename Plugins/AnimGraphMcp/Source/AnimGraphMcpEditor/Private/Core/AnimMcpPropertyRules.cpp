#include "AnimMcpPropertyRules.h"

#include "AnimGraphNode_Base.h"
#include "Bridge/AnimMcpTypes.h"
#include "Dom/JsonValue.h"
#include "EdGraph/EdGraphNode.h"
#include "UObject/UnrealType.h"

namespace AnimMcpPropertyRules
{
	namespace
	{
		struct FClassRules
		{
			const TCHAR* ClassName;
			TArray<FRule> Rules;
		};

		/**
		 * 허용 표. 프로퍼티 이름·타입은 전부 UE 5.7.4 헤더에서 확인 (phase1 §B-3, 핸드오프 §8):
		 *  FAnimNode_SequencePlayer     Runtime/Engine/Classes/Animation/AnimNode_SequencePlayer.h:122-142
		 *  FAnimNode_BlendSpacePlayer   Runtime/AnimGraphRuntime/Public/AnimNodes/AnimNode_BlendSpacePlayer.h:160-180
		 *  FAnimNode_Slot               Runtime/AnimGraphRuntime/Public/AnimNodes/AnimNode_Slot.h:25-29
		 *  FAnimNode_LayeredBoneBlend   Runtime/AnimGraphRuntime/Public/AnimNodes/AnimNode_LayeredBoneBlend.h:90-110
		 *  FAnimNode_BlendListBase      Runtime/AnimGraphRuntime/Public/AnimNodes/AnimNode_BlendListBase.h:48
		 *  UAnimGraphNode_SaveCachedPose Editor/AnimGraph/Public/AnimGraphNode_SaveCachedPose.h:25
		 *  UAnimGraphNode_UseCachedPose  Editor/AnimGraph/Public/AnimGraphNode_UseCachedPose.h:24
		 *  UAnimGraphNode_BlendListByEnum Editor/AnimGraph/Public/AnimGraphNode_BlendListByEnum.h:26-29
		 *  UAnimStateTransitionNode     Editor/AnimGraph/Public/AnimStateTransitionNode.h:35-104
		 *  UAnimStateNode               Editor/AnimGraph/Public/AnimStateNode.h:48
		 */
		const TArray<FClassRules>& Table()
		{
			static const TArray<FClassRules> Rules = {
				{ TEXT("AnimGraphNode_SequencePlayer"), {
					{ TEXT("bLoopAnimation"), EScope::FNode }, { TEXT("PlayRate"), EScope::FNode },
					{ TEXT("StartPosition"), EScope::FNode }, { TEXT("PlayRateBasis"), EScope::FNode } } },
				{ TEXT("AnimGraphNode_BlendSpacePlayer"), {
					{ TEXT("bLoop"), EScope::FNode }, { TEXT("PlayRate"), EScope::FNode }, { TEXT("StartPosition"), EScope::FNode },
					{ TEXT("X"), EScope::FNode }, { TEXT("Y"), EScope::FNode }, { TEXT("bResetPlayTimeWhenBlendSpaceChanges"), EScope::FNode } } },
				{ TEXT("AnimGraphNode_Slot"), {
					{ TEXT("SlotName"), EScope::FNode }, { TEXT("bAlwaysUpdateSourcePose"), EScope::FNode } } },
				{ TEXT("AnimGraphNode_SaveCachedPose"), {
					{ TEXT("CacheName"), EScope::Node } } },
				{ TEXT("AnimGraphNode_UseCachedPose"), {
					{ TEXT("SaveCachedPoseNode"), EScope::NodeRef } } },
				{ TEXT("AnimGraphNode_LayeredBoneBlend"), {
					{ TEXT("bMeshSpaceRotationBlend"), EScope::FNode }, { TEXT("bMeshSpaceScaleBlend"), EScope::FNode },
					{ TEXT("bBlendRootMotionBasedOnRootBone"), EScope::FNode }, { TEXT("LODThreshold"), EScope::FNode },
					// Phase 5 (2026-10-16 사용자 확정): 본 필터. LayerSetup = [{BranchFilters:[{BoneName, BlendDepth}]}] 포즈당 1개 (BoneMaskFilter.h:16-37)
					{ TEXT("BlendMode"), EScope::FNode }, { TEXT("LayerSetup"), EScope::FNode } } },
				{ TEXT("AnimGraphNode_BlendListBase"), {
					{ TEXT("BlendTime"), EScope::FNode } } },
				{ TEXT("AnimGraphNode_BlendListByEnum"), {
					{ TEXT("BoundEnum"), EScope::Node, /*bReadOnly*/ true }, { TEXT("VisibleEnumEntries"), EScope::Node, /*bReadOnly*/ true } } },
				{ TEXT("AnimStateTransitionNode"), {
					{ TEXT("CrossfadeDuration"), EScope::Node }, { TEXT("PriorityOrder"), EScope::Node }, { TEXT("BlendMode"), EScope::Node },
					{ TEXT("Bidirectional"), EScope::Node }, { TEXT("bDisabled"), EScope::Node },
					{ TEXT("bAutomaticRuleBasedOnSequencePlayerInState"), EScope::Node }, { TEXT("AutomaticRuleTriggerTime"), EScope::Node } } },
				{ TEXT("AnimStateNode"), {
					{ TEXT("bAlwaysResetOnEntry"), EScope::Node } } },
			};
			return Rules;
		}

		FString Quote(const FString& In)
		{
			return TEXT("\"") + In.ReplaceQuotesWithEscapedQuotes() + TEXT("\"");
		}

		bool ScalarToImportText(const FProperty* Property, const TSharedPtr<FJsonValue>& Value, bool bInsideArray, FString& OutText, FAnimMcpError& OutError)
		{
			const FString PropName = Property->GetName();
			if (const FBoolProperty* BoolProp = CastField<FBoolProperty>(Property))
			{
				if (Value->Type != EJson::Boolean)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' expects a boolean"), *PropName));
					return false;
				}
				OutText = Value->AsBool() ? TEXT("True") : TEXT("False");
				return true;
			}
			if (const FEnumProperty* EnumProp = CastField<FEnumProperty>(Property))
			{
				// GetIndexByNameString 은 "Linear" 와 "EAlphaBlendOption::Linear" 둘 다 받는다
				if (Value->Type != EJson::String || EnumProp->GetEnum()->GetIndexByNameString(Value->AsString()) == INDEX_NONE)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' expects an enum name of %s"), *PropName, *EnumProp->GetEnum()->GetName()));
					return false;
				}
				OutText = Value->AsString();
				return true;
			}
			if (const FByteProperty* ByteProp = CastField<FByteProperty>(Property))
			{
				if (ByteProp->Enum)
				{
					if (Value->Type != EJson::String || ByteProp->Enum->GetIndexByNameString(Value->AsString()) == INDEX_NONE)
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' expects an enum name of %s"), *PropName, *ByteProp->Enum->GetName()));
						return false;
					}
					OutText = Value->AsString();
					return true;
				}
			}
			if (const FNumericProperty* NumProp = CastField<FNumericProperty>(Property))
			{
				if (Value->Type != EJson::Number)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' expects a number"), *PropName));
					return false;
				}
				const double Number = Value->AsNumber();
				if (NumProp->IsInteger())
				{
					if (FMath::Frac(Number) != 0.0)
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' expects an integer"), *PropName));
						return false;
					}
					OutText = FString::Printf(TEXT("%lld"), static_cast<int64>(Number));
				}
				else
				{
					OutText = FString::SanitizeFloat(Number);
				}
				return true;
			}
			if (CastField<FNameProperty>(Property) || CastField<FStrProperty>(Property) || CastField<FTextProperty>(Property))
			{
				if (Value->Type != EJson::String)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' expects a string"), *PropName));
					return false;
				}
				OutText = bInsideArray ? Quote(Value->AsString()) : Value->AsString();
				return true;
			}
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' has type %s which set_property does not support"), *PropName, *Property->GetCPPType()));
			return false;
		}

		FString DescribeStructFields(const UScriptStruct* Struct)
		{
			TArray<FString> Names;
			for (TFieldIterator<FProperty> It(Struct); It; ++It)
			{
				Names.Add(It->GetName());
			}
			return FString::Join(Names, TEXT(", "));
		}

		/**
		 * JSON → ImportText (재귀). 배열 "(a,b)" · 구조체 "(Field=Value,...)" (주어진 필드만 — 나머지는 기본값) · 스칼라.
		 * 컨테이너 안의 문자열은 따옴표로 감싼다 (ImportText 의 구조체/배열 파서 규칙)
		 */
		bool ValueToImportText(const FProperty* Property, const TSharedPtr<FJsonValue>& Value, bool bInsideContainer, FString& OutText, FAnimMcpError& OutError)
		{
			if (!Value.IsValid() || Value->Type == EJson::Null)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' requires a non-null value"), *Property->GetName()));
				return false;
			}
			if (const FArrayProperty* ArrayProp = CastField<FArrayProperty>(Property))
			{
				if (Value->Type != EJson::Array)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' expects an array"), *Property->GetName()));
					return false;
				}
				TArray<FString> Items;
				for (const TSharedPtr<FJsonValue>& Element : Value->AsArray())
				{
					FString Item;
					if (!ValueToImportText(ArrayProp->Inner, Element, /*bInsideContainer*/ true, Item, OutError))
					{
						return false;
					}
					Items.Add(Item);
				}
				OutText = TEXT("(") + FString::Join(Items, TEXT(",")) + TEXT(")");
				return true;
			}
			if (const FStructProperty* StructProp = CastField<FStructProperty>(Property))
			{
				if (Value->Type != EJson::Object)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' expects an object with fields {%s}"), *Property->GetName(), *DescribeStructFields(StructProp->Struct)));
					return false;
				}
				TArray<FString> Fields;
				for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : Value->AsObject()->Values)
				{
					const FProperty* Member = StructProp->Struct->FindPropertyByName(FName(*Pair.Key));
					if (!Member)
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' has no field '%s' (fields: %s)"), *StructProp->Struct->GetName(), *Pair.Key, *DescribeStructFields(StructProp->Struct)));
						return false;
					}
					FString Text;
					if (!ValueToImportText(Member, Pair.Value, /*bInsideContainer*/ true, Text, OutError))
					{
						return false;
					}
					Fields.Add(Member->GetName() + TEXT("=") + Text);
				}
				OutText = TEXT("(") + FString::Join(Fields, TEXT(",")) + TEXT(")");
				return true;
			}
			return ScalarToImportText(Property, Value, bInsideContainer, OutText, OutError);
		}
	}

	TArray<FRule> RulesFor(const UClass* NodeClass)
	{
		TArray<FRule> Out;
		for (const UClass* C = NodeClass; C; C = C->GetSuperClass())
		{
			const FString Name = C->GetName();
			for (const FClassRules& Entry : Table())
			{
				if (Name == Entry.ClassName)
				{
					Out.Append(Entry.Rules);
				}
			}
		}
		return Out;
	}

	const FRule* Find(const UClass* NodeClass, FName Property)
	{
		for (const UClass* C = NodeClass; C; C = C->GetSuperClass())
		{
			const FString Name = C->GetName();
			for (const FClassRules& Entry : Table())
			{
				if (Name != Entry.ClassName)
				{
					continue;
				}
				for (const FRule& Rule : Entry.Rules)
				{
					if (Rule.Property == Property)
					{
						return &Rule;
					}
				}
			}
		}
		return nullptr;
	}

	FString DescribeAllowed(const UClass* NodeClass)
	{
		TArray<FString> Names;
		for (const FRule& Rule : RulesFor(NodeClass))
		{
			if (!Rule.bReadOnly)
			{
				Names.Add(Rule.Property.ToString());
			}
		}
		return Names.Num() > 0 ? FString::Join(Names, TEXT(", ")) : TEXT("(none)");
	}

	namespace
	{
		bool ResolveInternal(const UClass* NodeClass, UEdGraphNode* NodeOrNull, FName Property, FResolved& Out, FAnimMcpError& OutError)
		{
			Out = FResolved();
			Out.Rule = Find(NodeClass, Property);
			if (!Out.Rule)
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("node_class"), NodeClass ? NodeClass->GetName() : TEXT("?"));
				Details->SetStringField(TEXT("allowed"), DescribeAllowed(NodeClass));
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, FString::Printf(TEXT("Property '%s' is not in the allow list for %s"), *Property.ToString(), NodeClass ? *NodeClass->GetName() : TEXT("?")), Details);
				return false;
			}

			switch (Out.Rule->Scope)
			{
			case EScope::NodeRef:
				return true;

			case EScope::Node:
				Out.Property = NodeClass->FindPropertyByName(Property);
				Out.Container = NodeOrNull;
				break;

			case EScope::FNode:
			{
				const UAnimGraphNode_Base* ForStruct = NodeOrNull ? Cast<UAnimGraphNode_Base>(NodeOrNull) : NodeClass->GetDefaultObject<UAnimGraphNode_Base>();
				FStructProperty* NodeProp = ForStruct ? ForStruct->GetFNodeProperty() : nullptr;
				if (!NodeProp)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("%s has no FAnimNode struct property"), *NodeClass->GetName()));
					return false;
				}
				Out.MemberProperty = NodeProp;
				Out.Property = NodeProp->Struct->FindPropertyByName(Property);
				Out.Container = NodeOrNull ? NodeProp->ContainerPtrToValuePtr<void>(NodeOrNull) : nullptr;
				break;
			}
			}

			if (!Out.Property)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("Allow-listed property '%s' was not found on %s by reflection (engine version drift?)"), *Property.ToString(), *NodeClass->GetName()));
				return false;
			}
			return true;
		}
	}

	bool ResolveOnClass(const UClass* NodeClass, FName Property, FResolved& Out, FAnimMcpError& OutError)
	{
		return ResolveInternal(NodeClass, nullptr, Property, Out, OutError);
	}

	bool ResolveOnNode(UEdGraphNode* Node, FName Property, FResolved& Out, FAnimMcpError& OutError)
	{
		if (!Node)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::NodeNotFound, TEXT("Node is null"));
			return false;
		}
		return ResolveInternal(Node->GetClass(), Node, Property, Out, OutError);
	}

	bool JsonToImportText(const FProperty* Property, const TSharedPtr<FJsonValue>& Value, FString& OutText, FAnimMcpError& OutError)
	{
		if (!Property || !Value.IsValid() || Value->Type == EJson::Null)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("set_property requires a non-null 'value'"));
			return false;
		}
		return ValueToImportText(Property, Value, /*bInsideContainer*/ false, OutText, OutError);
	}

	TSharedPtr<FJsonValue> PropertyToJson(const FProperty* Property, const void* ValuePtr, UObject* Owner)
	{
		if (!Property || !ValuePtr)
		{
			return MakeShared<FJsonValueNull>();
		}
		if (const FBoolProperty* BoolProp = CastField<FBoolProperty>(Property))
		{
			return MakeShared<FJsonValueBoolean>(BoolProp->GetPropertyValue(ValuePtr));
		}
		// enum 을 등에 업은 FByteProperty 는 IsEnum → 아래 ExportText 폴백이 이름을 낸다. FEnumProperty 는 Numeric 이 아니라 바로 폴백
		if (const FNumericProperty* NumProp = CastField<FNumericProperty>(Property); NumProp && !NumProp->IsEnum())
		{
			if (NumProp->IsInteger())
			{
				return MakeShared<FJsonValueNumber>(static_cast<double>(NumProp->GetSignedIntPropertyValue(ValuePtr)));
			}
			else if (NumProp->IsFloatingPoint())
			{
				return MakeShared<FJsonValueNumber>(NumProp->GetFloatingPointPropertyValue(ValuePtr));
			}
		}
		if (const FArrayProperty* ArrayProp = CastField<FArrayProperty>(Property))
		{
			FScriptArrayHelper Helper(ArrayProp, ValuePtr);
			TArray<TSharedPtr<FJsonValue>> Items;
			for (int32 i = 0; i < Helper.Num(); ++i)
			{
				Items.Add(PropertyToJson(ArrayProp->Inner, Helper.GetRawPtr(i), Owner));
			}
			return MakeShared<FJsonValueArray>(Items);
		}
		// 구조체 → 객체 (필드 이름 = set_property 가 받는 이름). LayerSetup 의 FInputBlendPose/FBranchFilter 가 여기로 온다
		if (const FStructProperty* StructProp = CastField<FStructProperty>(Property))
		{
			TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
			for (TFieldIterator<FProperty> It(StructProp->Struct); It; ++It)
			{
				Obj->SetField(It->GetName(), PropertyToJson(*It, It->ContainerPtrToValuePtr<void>(ValuePtr), Owner));
			}
			return MakeShared<FJsonValueObject>(Obj);
		}
		// enum 은 이름으로. ExportText_Direct(Delta=null) 는 값이 0 이면 "기본값과 같다" 고 보고 아무것도 쓰지 않는다 (Property.cpp:1005-1007) — ExportTextItem_Direct 는 무조건 쓴다
		if (const FEnumProperty* EnumProp = CastField<FEnumProperty>(Property))
		{
			return MakeShared<FJsonValueString>(EnumProp->GetEnum()->GetNameStringByValue(EnumProp->GetUnderlyingProperty()->GetSignedIntPropertyValue(ValuePtr)));
		}
		if (const FByteProperty* ByteProp = CastField<FByteProperty>(Property); ByteProp && ByteProp->Enum)
		{
			return MakeShared<FJsonValueString>(ByteProp->Enum->GetNameStringByValue(ByteProp->GetPropertyValue(ValuePtr)));
		}
		FString Text;
		Property->ExportTextItem_Direct(Text, ValuePtr, nullptr, Owner, PPF_None);
		return MakeShared<FJsonValueString>(Text);
	}
}
