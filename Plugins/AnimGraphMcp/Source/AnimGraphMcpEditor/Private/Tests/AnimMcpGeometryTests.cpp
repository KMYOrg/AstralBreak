// AI 애니 생성 Phase 8-4a — 메시 기하(inspect_skeleton geometry)의 계산부 단위 테스트: 점 구름 주축(대칭 3×3 야코비).
// 기울인 긴 상자 정점 → 첫 주축 = 긴 변 방향 · 분산 큰 순 · 평균 · 부호 규칙. 애셋 없이 메모리에서만.
// run_automation_tests {filter:"AnimGraphMcp.Generation.Geometry"} 로 돈다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Core/AnimMcpSkeletonGeometry.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAnimMcpGeometryTest, "AnimGraphMcp.Generation.Geometry", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FAnimMcpGeometryTest::RunTest(const FString& Parameters)
{
	// 200 × 12 × 4 cm 상자 격자 — 회전 R(Yaw 30 · Pitch 20) · 원점 (5, −3, 50) 으로 옮긴다
	const FQuat R = FRotator(20.0, 30.0, 0.0).Quaternion();
	const FVector Origin(5.0, -3.0, 50.0);
	TArray<FVector> Points;
	for (int32 i = 0; i <= 40; ++i)
	{
		for (int32 j = 0; j <= 6; ++j)
		{
			for (int32 k = 0; k <= 2; ++k)
			{
				Points.Add(Origin + R.RotateVector(FVector(-100.0 + 5.0 * i, -6.0 + 2.0 * j, -2.0 + 2.0 * k)));
			}
		}
	}
	FVector Centroid;
	FVector Axes[3];
	double Variance[3];
	TestTrue(TEXT("axes computed"), AnimMcpSkeletonGeometry::PrincipalAxes(Points, Centroid, Axes, Variance));
	TestTrue(TEXT("centroid = box centre"), Centroid.Equals(Origin, 1e-6));
	TestTrue(TEXT("first axis = the long side"), FMath::Abs(FVector::DotProduct(Axes[0], R.GetAxisX())) > 0.9999);
	TestTrue(TEXT("second axis = the middle side"), FMath::Abs(FVector::DotProduct(Axes[1], R.GetAxisY())) > 0.9999);
	TestTrue(TEXT("third axis = the short side"), FMath::Abs(FVector::DotProduct(Axes[2], R.GetAxisZ())) > 0.9999);
	TestTrue(TEXT("variance largest first"), Variance[0] > Variance[1] && Variance[1] > Variance[2]);
	TestTrue(TEXT("orthonormal"), FMath::Abs(FVector::DotProduct(Axes[0], Axes[1])) < 1e-9 && FMath::Abs(Axes[2].Size() - 1.0) < 1e-9);
	for (int32 a = 0; a < 3; ++a)
	{
		const int32 Big = FMath::Abs(Axes[a].X) >= FMath::Abs(Axes[a].Y) && FMath::Abs(Axes[a].X) >= FMath::Abs(Axes[a].Z) ? 0 : FMath::Abs(Axes[a].Y) >= FMath::Abs(Axes[a].Z) ? 1 : 2;
		TestTrue(FString::Printf(TEXT("sign: largest component of axis %d is positive"), a), Axes[a][Big] > 0.0);
	}
	TArray<FVector> None;
	TestFalse(TEXT("no points → false"), AnimMcpSkeletonGeometry::PrincipalAxes(None, Centroid, Axes, Variance));
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
