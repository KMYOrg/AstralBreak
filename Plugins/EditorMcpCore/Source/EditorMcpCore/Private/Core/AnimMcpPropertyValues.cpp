#include "Core/AnimMcpPropertyValues.h"

#include "Bridge/AnimMcpTypes.h"
#include "Dom/JsonValue.h"
#include "Misc/PackageName.h"
#include "UObject/Package.h"
#include "UObject/UnrealType.h"

namespace AnimMcpPropertyRules
{
	namespace
	{
		FString Quote(const FString& In)
		{
			return TEXT("\"") + In.ReplaceQuotesWithEscapedQuotes() + TEXT("\"");
		}

		FAnimMcpError ReasonError(const FString& Message, const TCHAR* ReasonCode)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("reason"), ReasonCode);
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
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
			// (7-2) 오브젝트 참조 — 애셋 경로 문자열. 로드해 클래스를 확인한 뒤 ImportText 가 확실히 받는 Class'Path' 형식으로
			if (const FObjectPropertyBase* ObjProp = CastField<FObjectPropertyBase>(Property))
			{
				if (Value->Type != EJson::String || Value->AsString().TrimStartAndEnd().IsEmpty())
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' expects an asset path string (a %s) or null"), *PropName, ObjProp->PropertyClass ? *ObjProp->PropertyClass->GetName() : TEXT("object")));
					return false;
				}
				UObject* Object = ResolveObjectValue(ObjProp, Value->AsString(), OutError);
				if (!Object)
				{
					return false;
				}
				OutText = FString::Printf(TEXT("%s'%s'"), *Object->GetClass()->GetName(), *Object->GetPathName());
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
				// (7-2) 오브젝트 참조는 null 로 비울 수 있다
				if (CastField<FObjectPropertyBase>(Property))
				{
					OutText = TEXT("None");
					return true;
				}
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

	bool JsonToImportText(const FProperty* Property, const TSharedPtr<FJsonValue>& Value, FString& OutText, FAnimMcpError& OutError)
	{
		if (!Property || ((!Value.IsValid() || Value->Type == EJson::Null) && !CastField<FObjectPropertyBase>(Property)))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("set_property requires a non-null 'value' (null is allowed only for object references)"));
			return false;
		}
		return ValueToImportText(Property, Value, /*bInsideContainer*/ false, OutText, OutError);
	}

	UObject* ResolveObjectValue(const FObjectPropertyBase* Property, const FString& InPath, FAnimMcpError& OutError)
	{
		const FString Path = InPath.TrimStartAndEnd();
		const FString PropName = Property ? Property->GetName() : TEXT("?");
		// "/Game/Folder/Asset" 은 패키지로 해석되므로 ".Asset" 을 붙인 오브젝트 경로를 먼저 본다 (서브오브젝트 "A.B:C" 는 그대로)
		FString ObjectPath = Path;
		if (!Path.Contains(TEXT(".")) && !Path.Contains(TEXT(":")))
		{
			ObjectPath = Path + TEXT(".") + FPackageName::GetShortName(Path);
		}
		UObject* Object = FindObject<UObject>(nullptr, *ObjectPath);
		if (!Object)
		{
			Object = LoadObject<UObject>(nullptr, *ObjectPath);
		}
		if (!Object && ObjectPath != Path)
		{
			Object = FindObject<UObject>(nullptr, *Path);
			if (!Object) { Object = LoadObject<UObject>(nullptr, *Path); }
		}
		if (Object && Object->IsA<UPackage>())
		{
			Object = nullptr;
		}
		if (!Object)
		{
			OutError = ReasonError(FString::Printf(TEXT("'%s': asset '%s' not found (use an object path like /Game/Folder/Asset or Skeleton.Skeleton:Profile)"), *PropName, *Path), TEXT("OBJECT_NOT_FOUND"));
			return nullptr;
		}
		if (Property && Property->PropertyClass && !Object->IsA(Property->PropertyClass))
		{
			OutError = ReasonError(FString::Printf(TEXT("'%s' expects a %s, but '%s' is a %s"), *PropName, *Property->PropertyClass->GetName(), *Path, *Object->GetClass()->GetName()), TEXT("OBJECT_CLASS_MISMATCH"));
			return nullptr;
		}
		return Object;
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
		// (7-2) 오브젝트 참조 → 경로 문자열 또는 null
		if (const FObjectPropertyBase* ObjProp = CastField<FObjectPropertyBase>(Property))
		{
			const UObject* Object = ObjProp->GetObjectPropertyValue(ValuePtr);
			return Object ? TSharedPtr<FJsonValue>(MakeShared<FJsonValueString>(Object->GetPathName())) : TSharedPtr<FJsonValue>(MakeShared<FJsonValueNull>());
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
