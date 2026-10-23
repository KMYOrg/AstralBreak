#include "AnimMcpTypes.h"

#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

int32 FAnimMcpError::ToHttpStatus() const
{
	if (!IsSet())
	{
		return 200;
	}
	if (Code == AnimMcpErrorCodes::Unauthorized)
	{
		return 401;
	}
	if (Code == AnimMcpErrorCodes::ToolNotFound || Code == AnimMcpErrorCodes::AssetNotFound
		|| Code == AnimMcpErrorCodes::GraphNotFound || Code == AnimMcpErrorCodes::NodeNotFound
		|| Code == AnimMcpErrorCodes::PinNotFound)
	{
		return 404;
	}
	if (Code == AnimMcpErrorCodes::AssetProtected || Code == AnimMcpErrorCodes::OutputPathNotAllowed
		|| Code == AnimMcpErrorCodes::ImportSourceNotAllowed)
	{
		return 403;
	}
	if (Code == AnimMcpErrorCodes::RevisionMismatch || Code == AnimMcpErrorCodes::AssetExists
		|| Code == AnimMcpErrorCodes::AssetReferenced || Code == AnimMcpErrorCodes::DirtyPackages
		|| Code == AnimMcpErrorCodes::UnexpectedDirty)
	{
		return 409;
	}
	if (Code == AnimMcpErrorCodes::Internal)
	{
		return 500;
	}
	// BAD_REQUEST · CONNECTION_REJECTED · PROPERTY_NOT_ALLOWED · COMPILE_FAILED · SAVE_FAILED
	// · IMPORT_FAILED · IKRIG_AUTO_FAILED · RETARGET_FAILED · VALIDATION_FAILED — 요청 내용으로 인한 실패
	return 400;
}

TSharedRef<FJsonObject> FAnimMcpError::ToJson() const
{
	TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
	Obj->SetStringField(TEXT("code"), Code);
	Obj->SetStringField(TEXT("message"), Message);
	if (Details.IsValid())
	{
		Obj->SetObjectField(TEXT("details"), Details);
	}
	return Obj;
}

bool FAnimMcpRequest::GetRequiredString(const TCHAR* Key, FString& Out, FAnimMcpError& OutError) const
{
	if (!Params->TryGetStringField(Key, Out) || Out.IsEmpty())
	{
		OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Missing or empty required string parameter '%s'"), Key));
		return false;
	}
	return true;
}

FString FAnimMcpRequest::GetOptionalString(const TCHAR* Key, const FString& Default) const
{
	FString Out;
	return Params->TryGetStringField(Key, Out) ? Out : Default;
}

bool FAnimMcpRequest::GetOptionalBool(const TCHAR* Key, bool Default) const
{
	bool Out = Default;
	return Params->TryGetBoolField(Key, Out) ? Out : Default;
}

double FAnimMcpRequest::GetOptionalNumber(const TCHAR* Key, double Default) const
{
	double Out = Default;
	return Params->TryGetNumberField(Key, Out) ? Out : Default;
}

void FAnimMcpContext::AddDiagnostic(const TCHAR* Level, const TCHAR* Code, const FString& Message, TSharedPtr<FJsonObject> Extra)
{
	TSharedRef<FJsonObject> D = Extra.IsValid() ? Extra.ToSharedRef() : MakeShared<FJsonObject>();
	D->SetStringField(TEXT("level"), Level);
	D->SetStringField(TEXT("code"), Code);
	D->SetStringField(TEXT("message"), Message);
	Diagnostics.Add(MakeShared<FJsonValueObject>(D));
}

namespace AnimMcpJson
{
	FString ToString(const TSharedRef<FJsonObject>& Object, bool bPretty)
	{
		FString Out;
		if (bPretty)
		{
			TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Out);
			FJsonSerializer::Serialize(Object, Writer);
		}
		else
		{
			TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
			FJsonSerializer::Serialize(Object, Writer);
		}
		return Out;
	}

	bool Parse(const FString& Text, TSharedPtr<FJsonObject>& OutObject, FString& OutParseError)
	{
		TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
		if (!FJsonSerializer::Deserialize(Reader, OutObject) || !OutObject.IsValid())
		{
			OutParseError = Reader->GetErrorMessage();
			if (OutParseError.IsEmpty())
			{
				OutParseError = TEXT("Body is not a JSON object");
			}
			return false;
		}
		return true;
	}

	TSharedRef<FJsonObject> MakeObject()
	{
		return MakeShared<FJsonObject>();
	}

	TSharedPtr<FJsonValue> StringOrNull(const FString& Value)
	{
		if (Value.IsEmpty())
		{
			return MakeShared<FJsonValueNull>();
		}
		return MakeShared<FJsonValueString>(Value);
	}

	TSharedPtr<FJsonValue> ObjectPathOrNull(const UObject* Object)
	{
		return Object ? StringOrNull(Object->GetPathName()) : MakeShared<FJsonValueNull>();
	}
}
