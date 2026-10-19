#include "AnimMcpRuntimeScenario.h"

namespace AnimMcpRuntimeScenario
{
	namespace
	{
		FString LastObservation;
	}

	FString MakeTestCommand(const FString& ScenarioJson)
	{
		return FString::Printf(TEXT("%s %s"), TestClassName, *ScenarioJson);
	}

	void SetObservation(const FString& Json)
	{
		LastObservation = Json;
	}

	FString TakeObservation()
	{
		FString Out = MoveTemp(LastObservation);
		LastObservation.Empty();
		return Out;
	}
}
