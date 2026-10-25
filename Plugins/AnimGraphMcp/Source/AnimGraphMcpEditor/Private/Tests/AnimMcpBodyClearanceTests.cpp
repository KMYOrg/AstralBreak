// 팔-몸통 관통 보정(Core/AnimMcpBodyClearance)의 계산부 단위 테스트 — 최소제곱 어깨 회전과 시간 평활. 애셋 없이 메모리에서만.
// run_automation_tests {filter:"AnimGraphMcp.Generation.BodyClearance"} 로 돈다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Core/AnimMcpBodyClearance.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAnimMcpBodyClearanceTest, "AnimGraphMcp.Generation.BodyClearance", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FAnimMcpBodyClearanceTest::RunTest(const FString& Parameters)
{
	// ---- 회전: 어깨(원점)에서 아래로 매달린 팔 끝 점들을 +X(바깥)로 2 cm — 앞축(Y) 둘레 벌림이 나와야 한다 ----
	{
		TArray<FVector> Offsets, Displacements;
		for (int32 i = 0; i < 6; ++i)
		{
			Offsets.Add(FVector(0.0, 0.0, -45.0 - i));
			Displacements.Add(FVector(2.0, 0.0, 0.0));
		}
		const FVector Omega = AnimMcpBodyClearance::SolveRotation(Offsets, Displacements, 0.05);
		const FQuat R(Omega.GetSafeNormal(), Omega.Size());
		const FVector Moved = R.RotateVector(Offsets[0]) - Offsets[0];
		TestTrue(TEXT("hanging arm pushed outward moves +X"), Moved.X > 1.5 && Moved.X < 2.5);
		TestTrue(TEXT("rotation axis is the forward (Y) axis"), FMath::Abs(Omega.GetSafeNormal().Y) > 0.99);
		// 팔 축 둘레(비틀림)는 점을 옮기지 못하니 정규화로 0 근처
		const FVector Twist = AnimMcpBodyClearance::SolveRotation({ FVector(0, 0, -40), FVector(0, 0, -50) }, { FVector::ZeroVector, FVector::ZeroVector }, 0.05);
		TestTrue(TEXT("no displacement → no rotation"), Twist.Size() < 1e-9);
	}

	// ---- 평활: 크기 팽창 → 가우시안. 한 프레임 충격은 그 프레임에서 줄지 않고(팽창 반경 = 블러 반경) 반경 밖은 0 ----
	{
		TArray<FVector> Vectors;
		Vectors.Init(FVector::ZeroVector, 21);
		Vectors[10] = FVector(0.0, 5.0, 0.0);
		const TArray<FVector> Smoothed = AnimMcpBodyClearance::SmoothRotationVectors(Vectors, 3);
		TestEqual(TEXT("length kept"), Smoothed.Num(), 21);
		TestTrue(TEXT("impulse frame keeps its magnitude"), Smoothed[10].Size() >= 5.0 - 1e-9);
		TestTrue(TEXT("neighbours ramp"), Smoothed[13].Size() > 0.0 && Smoothed[13].Size() < 5.0);
		TestTrue(TEXT("beyond dilation + blur radius stays zero"), Smoothed[3].Size() < 1e-12 && Smoothed[17].Size() < 1e-12);
		TestTrue(TEXT("radius 0 is identity"), AnimMcpBodyClearance::SmoothRotationVectors(Vectors, 0)[10].Equals(Vectors[10]));
	}
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
