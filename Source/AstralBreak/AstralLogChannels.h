#pragma once

#include "Logging/LogMacros.h"

class UObject;

ASTRALBREAK_API DECLARE_LOG_CATEGORY_EXTERN(LogAstral, Log, All);

ASTRALBREAK_API DECLARE_LOG_CATEGORY_EXTERN(LogAstralAbilitySystem, Log, All);

ASTRALBREAK_API FString GetClientServerContextString(UObject* ContextObject = nullptr);