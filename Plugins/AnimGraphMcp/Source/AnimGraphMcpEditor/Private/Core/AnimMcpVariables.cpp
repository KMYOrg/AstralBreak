#include "AnimMcpVariables.h"

#include "AnimMcpLog.h"
#include "Animation/AnimBlueprint.h"
#include "Bridge/AnimMcpTypes.h"
#include "EdGraphSchema_K2.h"
#include "Engine/Blueprint.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/Kismet2NameValidators.h"
#include "UObject/UnrealType.h"

namespace AnimMcpVariables
{
	namespace
	{
		FAnimMcpError Reason(const FString& Message, const TCHAR* ReasonCode, const TCHAR* Field = nullptr)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("reason"), ReasonCode);
			if (Field) { Details->SetStringField(TEXT("field"), Field); }
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
		}

		template <typename T>
		FEdGraphPinType StructType()
		{
			FEdGraphPinType Type;
			Type.PinCategory = UEdGraphSchema_K2::PC_Struct;
			Type.PinSubCategoryObject = TBaseStructure<T>::Get();
			return Type;
		}

		const TCHAR* ValidatorResultText(EValidatorResult Result)
		{
			switch (Result)
			{
			case EValidatorResult::AlreadyInUse: return TEXT("ALREADY_IN_USE");
			case EValidatorResult::EmptyName: return TEXT("EMPTY_NAME");
			case EValidatorResult::TooLong: return TEXT("TOO_LONG");
			case EValidatorResult::ContainsInvalidCharacters: return TEXT("INVALID_CHARACTERS");
			case EValidatorResult::LocallyInUse: return TEXT("LOCALLY_IN_USE");
			case EValidatorResult::ExistingName: return TEXT("EXISTING_NAME");
			default: return TEXT("BAD_NAME");
			}
		}
	}

	bool ParsePinType(const FString& InText, FEdGraphPinType& OutType, FAnimMcpError& OutError)
	{
		OutType = FEdGraphPinType();
		const FString Text = InText.TrimStartAndEnd();
		const FString Lower = Text.ToLower();
		if (Lower == TEXT("bool") || Lower == TEXT("boolean")) { OutType.PinCategory = UEdGraphSchema_K2::PC_Boolean; return true; }
		if (Lower == TEXT("float") || Lower == TEXT("double") || Lower == TEXT("real"))
		{
			// UE5 BP 의 실수 변수는 double (PC_Real / PC_Double)
			OutType.PinCategory = UEdGraphSchema_K2::PC_Real;
			OutType.PinSubCategory = UEdGraphSchema_K2::PC_Double;
			return true;
		}
		if (Lower == TEXT("int") || Lower == TEXT("int32") || Lower == TEXT("integer")) { OutType.PinCategory = UEdGraphSchema_K2::PC_Int; return true; }
		if (Lower == TEXT("int64")) { OutType.PinCategory = UEdGraphSchema_K2::PC_Int64; return true; }
		if (Lower == TEXT("name")) { OutType.PinCategory = UEdGraphSchema_K2::PC_Name; return true; }
		if (Lower == TEXT("string")) { OutType.PinCategory = UEdGraphSchema_K2::PC_String; return true; }
		if (Lower == TEXT("text")) { OutType.PinCategory = UEdGraphSchema_K2::PC_Text; return true; }
		if (Lower == TEXT("byte")) { OutType.PinCategory = UEdGraphSchema_K2::PC_Byte; return true; }
		if (Lower == TEXT("vector")) { OutType = StructType<FVector>(); return true; }
		if (Lower == TEXT("vector2d")) { OutType = StructType<FVector2D>(); return true; }
		if (Lower == TEXT("rotator")) { OutType = StructType<FRotator>(); return true; }
		if (Lower == TEXT("transform")) { OutType = StructType<FTransform>(); return true; }
		if (Lower == TEXT("linearcolor")) { OutType = StructType<FLinearColor>(); return true; }

		FString Kind, Path;
		if (Text.Split(TEXT(":"), &Kind, &Path))
		{
			Kind = Kind.TrimStartAndEnd().ToLower();
			Path = Path.TrimStartAndEnd();
			if (Kind == TEXT("object") || Kind == TEXT("class"))
			{
				UClass* Class = FindObject<UClass>(nullptr, *Path);
				if (!Class) { Class = LoadObject<UClass>(nullptr, *Path); }
				if (!Class)
				{
					OutError = Reason(FString::Printf(TEXT("type '%s': class '%s' not found (use a path like /Script/Engine.Actor)"), *Text, *Path), TEXT("BAD_TYPE"), TEXT("type"));
					return false;
				}
				OutType.PinCategory = Kind == TEXT("object") ? UEdGraphSchema_K2::PC_Object : UEdGraphSchema_K2::PC_Class;
				OutType.PinSubCategoryObject = Class;
				return true;
			}
			if (Kind == TEXT("struct"))
			{
				UScriptStruct* Struct = FindObject<UScriptStruct>(nullptr, *Path);
				if (!Struct) { Struct = LoadObject<UScriptStruct>(nullptr, *Path); }
				if (!Struct)
				{
					OutError = Reason(FString::Printf(TEXT("type '%s': struct '%s' not found (use a path like /Script/CoreUObject.Vector)"), *Text, *Path), TEXT("BAD_TYPE"), TEXT("type"));
					return false;
				}
				OutType.PinCategory = UEdGraphSchema_K2::PC_Struct;
				OutType.PinSubCategoryObject = Struct;
				return true;
			}
			if (Kind == TEXT("enum"))
			{
				UEnum* Enum = FindObject<UEnum>(nullptr, *Path);
				if (!Enum) { Enum = LoadObject<UEnum>(nullptr, *Path); }
				if (!Enum)
				{
					OutError = Reason(FString::Printf(TEXT("type '%s': enum '%s' not found (use a path like /Script/Engine.EAlphaBlendOption)"), *Text, *Path), TEXT("BAD_TYPE"), TEXT("type"));
					return false;
				}
				OutType.PinCategory = UEdGraphSchema_K2::PC_Byte;
				OutType.PinSubCategoryObject = Enum;
				return true;
			}
		}
		OutError = Reason(FString::Printf(TEXT("unknown variable type '%s' (bool|float|int|int64|name|string|text|byte|vector|vector2d|rotator|transform|linearcolor|object:<class>|class:<class>|struct:<struct>|enum:<enum>)"), *Text), TEXT("BAD_TYPE"), TEXT("type"));
		return false;
	}

	FString PinTypeToText(const FEdGraphPinType& Type)
	{
		const FName Cat = Type.PinCategory;
		FString Text;
		if (Cat == UEdGraphSchema_K2::PC_Boolean) { Text = TEXT("bool"); }
		else if (Cat == UEdGraphSchema_K2::PC_Real) { Text = TEXT("float"); }
		else if (Cat == UEdGraphSchema_K2::PC_Int) { Text = TEXT("int"); }
		else if (Cat == UEdGraphSchema_K2::PC_Int64) { Text = TEXT("int64"); }
		else if (Cat == UEdGraphSchema_K2::PC_Name) { Text = TEXT("name"); }
		else if (Cat == UEdGraphSchema_K2::PC_String) { Text = TEXT("string"); }
		else if (Cat == UEdGraphSchema_K2::PC_Text) { Text = TEXT("text"); }
		else if (Cat == UEdGraphSchema_K2::PC_Byte) { Text = Type.PinSubCategoryObject.IsValid() ? TEXT("enum:") + Type.PinSubCategoryObject->GetPathName() : TEXT("byte"); }
		else if (Cat == UEdGraphSchema_K2::PC_Struct)
		{
			const UObject* Struct = Type.PinSubCategoryObject.Get();
			if (Struct == TBaseStructure<FVector>::Get()) { Text = TEXT("vector"); }
			else if (Struct == TBaseStructure<FVector2D>::Get()) { Text = TEXT("vector2d"); }
			else if (Struct == TBaseStructure<FRotator>::Get()) { Text = TEXT("rotator"); }
			else if (Struct == TBaseStructure<FTransform>::Get()) { Text = TEXT("transform"); }
			else if (Struct == TBaseStructure<FLinearColor>::Get()) { Text = TEXT("linearcolor"); }
			else { Text = TEXT("struct:") + (Struct ? Struct->GetPathName() : FString(TEXT("?"))); }
		}
		else if (Cat == UEdGraphSchema_K2::PC_Object) { Text = TEXT("object:") + (Type.PinSubCategoryObject.IsValid() ? Type.PinSubCategoryObject->GetPathName() : FString(TEXT("?"))); }
		else if (Cat == UEdGraphSchema_K2::PC_Class) { Text = TEXT("class:") + (Type.PinSubCategoryObject.IsValid() ? Type.PinSubCategoryObject->GetPathName() : FString(TEXT("?"))); }
		else { Text = Cat.ToString(); }
		if (Type.IsArray()) { Text += TEXT("[]"); }
		else if (Type.IsSet()) { Text += TEXT("{}"); }
		else if (Type.IsMap()) { Text += TEXT("{:}"); }
		return Text;
	}

	bool AddVariable(UAnimBlueprint* Blueprint, const FAddParams& Params, FAnimMcpError& OutError)
	{
		if (!Blueprint)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("AddVariable without blueprint"));
			return false;
		}
		const FString Name = Params.Name.TrimStartAndEnd();
		if (Name.IsEmpty())
		{
			OutError = Reason(TEXT("add_blueprint_variable requires 'name'"), TEXT("EMPTY_NAME"), TEXT("name"));
			return false;
		}
		// 에디터의 변수 이름 검증기 — 중복(변수·함수·그래프)·금지 문자·길이
		{
			FKismetNameValidator Validator(Blueprint);
			const EValidatorResult Result = Validator.IsValid(Name);
			if (Result != EValidatorResult::Ok)
			{
				const TCHAR* Code = (Result == EValidatorResult::AlreadyInUse || Result == EValidatorResult::ExistingName || Result == EValidatorResult::LocallyInUse) ? TEXT("VARIABLE_EXISTS") : TEXT("BAD_NAME");
				OutError = Reason(FString::Printf(TEXT("variable name '%s' is not valid for this Blueprint (%s)"), *Name, ValidatorResultText(Result)), Code, TEXT("name"));
				return false;
			}
		}
		FEdGraphPinType Type;
		if (!ParsePinType(Params.Type, Type, OutError))
		{
			return false;
		}
		// 기본값 — 단순 타입만 미리 검사 (구조체·오브젝트는 컴파일러가 ImportText 로 본다)
		FString DefaultValue = Params.DefaultValue.TrimStartAndEnd();
		if (!DefaultValue.IsEmpty())
		{
			if (Type.PinCategory == UEdGraphSchema_K2::PC_Boolean)
			{
				const FString L = DefaultValue.ToLower();
				if (L != TEXT("true") && L != TEXT("false"))
				{
					OutError = Reason(FString::Printf(TEXT("default for bool must be true or false, got '%s'"), *DefaultValue), TEXT("BAD_DEFAULT"), TEXT("default"));
					return false;
				}
				DefaultValue = L;
			}
			else if ((Type.PinCategory == UEdGraphSchema_K2::PC_Real || Type.PinCategory == UEdGraphSchema_K2::PC_Int || Type.PinCategory == UEdGraphSchema_K2::PC_Int64) && !DefaultValue.IsNumeric())
			{
				OutError = Reason(FString::Printf(TEXT("default for a numeric variable must be a number, got '%s'"), *DefaultValue), TEXT("BAD_DEFAULT"), TEXT("default"));
				return false;
			}
		}

		Blueprint->Modify();
		if (!FBlueprintEditorUtils::AddMemberVariable(Blueprint, FName(*Name), Type, DefaultValue))
		{
			OutError = Reason(FString::Printf(TEXT("the engine refused to add variable '%s' (name already used in this class chain?)"), *Name), TEXT("VARIABLE_EXISTS"), TEXT("name"));
			return false;
		}
		const int32 Index = FBlueprintEditorUtils::FindNewVariableIndex(Blueprint, FName(*Name));
		if (Index == INDEX_NONE)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("variable '%s' was added but cannot be found in NewVariables"), *Name));
			return false;
		}
		if (Params.bInstanceEditable)
		{
			Blueprint->NewVariables[Index].PropertyFlags &= ~CPF_DisableEditOnInstance;
		}
		if (!Params.Category.TrimStartAndEnd().IsEmpty())
		{
			FBlueprintEditorUtils::SetBlueprintVariableCategory(Blueprint, FName(*Name), nullptr, FText::FromString(Params.Category.TrimStartAndEnd()), /*bDontRecompile*/ true);
		}
		UE_LOG(LogAnimGraphMcp, Log, TEXT("Added Blueprint variable %s (%s) to %s"), *Name, *PinTypeToText(Type), *Blueprint->GetPathName());
		return true;
	}

	bool RemoveVariable(UAnimBlueprint* Blueprint, const FString& InName, bool bForce, bool& bOutWasUsed, FAnimMcpError& OutError)
	{
		bOutWasUsed = false;
		if (!Blueprint)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("RemoveVariable without blueprint"));
			return false;
		}
		const FName Name(*InName.TrimStartAndEnd());
		if (Name.IsNone())
		{
			OutError = Reason(TEXT("remove_blueprint_variable requires 'name'"), TEXT("EMPTY_NAME"), TEXT("name"));
			return false;
		}
		if (FBlueprintEditorUtils::FindNewVariableIndex(Blueprint, Name) == INDEX_NONE)
		{
			const bool bNative = Blueprint->ParentClass && Blueprint->ParentClass->FindPropertyByName(Name) != nullptr;
			OutError = Reason(bNative
				? FString::Printf(TEXT("'%s' is a native (C++) property of %s and cannot be removed here"), *Name.ToString(), *Blueprint->ParentClass->GetName())
				: FString::Printf(TEXT("'%s' is not a variable declared by this Blueprint"), *Name.ToString()), TEXT("NOT_BLUEPRINT_VARIABLE"), TEXT("name"));
			return false;
		}
		bOutWasUsed = FBlueprintEditorUtils::IsVariableUsed(Blueprint, Name);
		if (bOutWasUsed && !bForce)
		{
			OutError = Reason(FString::Printf(TEXT("variable '%s' is referenced by graph nodes; pass force=true to remove it and its nodes"), *Name.ToString()), TEXT("VARIABLE_IN_USE"), TEXT("name"));
			return false;
		}
		Blueprint->Modify();
		FBlueprintEditorUtils::RemoveMemberVariable(Blueprint, Name);
		UE_LOG(LogAnimGraphMcp, Log, TEXT("Removed Blueprint variable %s from %s (was used: %d)"), *Name.ToString(), *Blueprint->GetPathName(), bOutWasUsed ? 1 : 0);
		return true;
	}

	TSharedPtr<FJsonObject> DescribeDeclaration(UAnimBlueprint* Blueprint, FName Name)
	{
		const int32 Index = Blueprint ? FBlueprintEditorUtils::FindNewVariableIndex(Blueprint, Name) : INDEX_NONE;
		if (Index == INDEX_NONE)
		{
			return nullptr;
		}
		const FBPVariableDescription& Var = Blueprint->NewVariables[Index];
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetStringField(TEXT("type"), PinTypeToText(Var.VarType));
		Obj->SetStringField(TEXT("default_value"), Var.DefaultValue);
		Obj->SetStringField(TEXT("category"), Var.Category.ToString());
		Obj->SetBoolField(TEXT("instance_editable"), !(Var.PropertyFlags & CPF_DisableEditOnInstance));
		return Obj;
	}

	void AppendRevisionLines(UAnimBlueprint* Blueprint, FString& Out)
	{
		if (!Blueprint)
		{
			return;
		}
		for (const FBPVariableDescription& Var : Blueprint->NewVariables)
		{
			Out += FString::Printf(TEXT("BV|%s|%s|%s\n"), *Var.VarName.ToString(), *PinTypeToText(Var.VarType), *Var.DefaultValue);
		}
	}
}
