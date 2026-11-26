#include "Core/EditorMcpSettings.h"

#include "Misc/ConfigCacheIni.h"

namespace EditorMcpSettings
{
	TArray<FString> GetArray(const TCHAR* Key)
	{
		TArray<FString> Out;
		TArray<FString> Raw;
		if (GConfig->GetArray(Section, Key, Raw, GEngineIni) > 0)
		{
			Out.Append(Raw);
		}
		Raw.Reset();
		if (GConfig->GetArray(LegacySection, Key, Raw, GEngineIni) > 0)
		{
			Out.Append(Raw);
		}
		return Out;
	}

	bool GetInt(const TCHAR* Key, int32& Out)
	{
		return GConfig->GetInt(Section, Key, Out, GEngineIni) || GConfig->GetInt(LegacySection, Key, Out, GEngineIni);
	}

	bool GetBool(const TCHAR* Key, bool& Out)
	{
		return GConfig->GetBool(Section, Key, Out, GEngineIni) || GConfig->GetBool(LegacySection, Key, Out, GEngineIni);
	}

	FString Describe(const TCHAR* Key)
	{
		return FString::Printf(TEXT("[%s] (or legacy [%s]) %s in DefaultEngine.ini"), Section, LegacySection, Key);
	}

	TArray<FString> GetArrayFromFile(const FConfigFile& File, const TCHAR* Key)
	{
		TArray<FString> Out;
		TArray<FString> Raw;
		if (File.GetArray(Section, Key, Raw) > 0)
		{
			Out.Append(Raw);
		}
		Raw.Reset();
		if (File.GetArray(LegacySection, Key, Raw) > 0)
		{
			Out.Append(Raw);
		}
		return Out;
	}

	bool GetIntFromFile(const FConfigFile& File, const TCHAR* Key, int32& Out)
	{
		return File.GetInt(Section, Key, Out) || File.GetInt(LegacySection, Key, Out);
	}
}
