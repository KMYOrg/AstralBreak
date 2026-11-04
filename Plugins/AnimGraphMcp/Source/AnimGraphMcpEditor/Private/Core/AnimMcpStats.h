#pragma once

#include "CoreMinimal.h"

/** 측정 Tool(inspect_skeleton · validate_animation) 공통 수치 헬퍼 */
namespace AnimMcpStats
{
	/** 선형 보간 백분위 (numpy.percentile 기본과 같다). P 는 0~100. 빈 배열은 0 */
	inline double Percentile(TArray<double> Values, double P)
	{
		if (Values.Num() == 0)
		{
			return 0.0;
		}
		Values.Sort();
		const double Rank = FMath::Clamp(P, 0.0, 100.0) / 100.0 * (Values.Num() - 1);
		const int32 Lo = FMath::FloorToInt32(Rank);
		const int32 Hi = FMath::Min(Lo + 1, Values.Num() - 1);
		return FMath::Lerp(Values[Lo], Values[Hi], Rank - Lo);
	}

	/** JSON 출력용 반올림 — 소수 Digits 자리 */
	inline double Round(double Value, int32 Digits = 3)
	{
		const double Scale = FMath::Pow(10.0, Digits);
		return FMath::RoundToDouble(Value * Scale) / Scale;
	}
}
