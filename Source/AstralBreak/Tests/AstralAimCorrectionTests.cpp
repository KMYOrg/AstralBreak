// 최종 조준 보정 순수 계산 테스트 — 정렬 상태 무변경 · 원거리 오차 수렴 · 근거리 시차 수렴 · 최대각 제한 · 가중치 분배.
// 월드 의존이 없어 run_automation_tests {"filter": "AstralBreak.AimCorrection"} 로 돈다. 그래프 배선·실제 총열 각은 PIE 총구 프로브 (hero-combat-abp.md §7)

#include "Misc/AutomationTest.h"
#include "Animation/AstralAimCorrection.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace
{
	/** 세로 척추 3본(z 110 · 120 · 135) + 오른손이 앞 오른쪽(x 25, y 20, z 128). 총구는 손에서 +X 로 60cm — 총열이 +X(정면)를 본다 */
	struct FAimRig
	{
		TArray<FTransform> Chain = { FTransform(FVector(0, 0, 110)), FTransform(FVector(0, 0, 120)), FTransform(FVector(0, 0, 135)) };
		TArray<float> Weights = { 0.25f, 0.35f, 0.4f };
		FTransform Hand = FTransform(FVector(25, 20, 128));
		FTransform Muzzle = FTransform(FVector(60, 0, 0));

		FAstralAimCorrectionInput Input(const FVector& Target, float MaxAngle = 30.f, int32 Iterations = 3) const
		{
			FAstralAimCorrectionInput In;
			In.Chain = Chain;
			In.Weights = Weights;
			In.WeaponBone = Hand;
			In.MuzzleInWeaponBone = Muzzle;
			In.Target = Target;
			In.MaxAngleDegrees = MaxAngle;
			In.Iterations = Iterations;
			return In;
		}

		FVector MuzzleLocation() const { return (Muzzle * Hand).GetLocation(); }
	};

	/** 결과 체인 끝 본이 옮긴 만큼 손도 옮겨 보정 뒤 총열 방향을 다시 잰다 (솔버 밖에서 독립 검증) */
	FVector BarrelAfter(const FAimRig& Rig, const FAstralAimCorrectionResult& R)
	{
		const FTransform TipBefore = Rig.Chain.Last();
		const FTransform TipAfter = R.Chain.Last();
		const FTransform HandAfter = Rig.Hand * TipBefore.Inverse() * TipAfter;
		return (Rig.Muzzle * HandAfter).GetUnitAxis(EAxis::X);
	}

	FVector MuzzleAfter(const FAimRig& Rig, const FAstralAimCorrectionResult& R)
	{
		const FTransform HandAfter = Rig.Hand * Rig.Chain.Last().Inverse() * R.Chain.Last();
		return (Rig.Muzzle * HandAfter).GetLocation();
	}

	float AngleDeg(const FVector& A, const FVector& B)
	{
		return FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(A.GetSafeNormal(), B.GetSafeNormal()), -1.f, 1.f)));
	}

	/** 총구에서 Yaw/Pitch(도) 방향으로 Distance 떨어진 조준점 */
	FVector TargetFrom(const FVector& Origin, float Yaw, float Pitch, float Distance)
	{
		return Origin + FRotator(Pitch, Yaw, 0.f).Vector() * Distance;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralAimCorrectionAlignedTest, "AstralBreak.AimCorrection.Aligned", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralAimCorrectionAlignedTest::RunTest(const FString& Parameters)
{
	const FAimRig Rig;
	const FAstralAimCorrectionResult R = AstralAimCorrection::Solve(Rig.Input(TargetFrom(Rig.MuzzleLocation(), 0.f, 0.f, 5000.f)));
	TestTrue(TEXT("valid"), R.bValid);
	TestTrue(TEXT("no initial error"), R.InitialErrorDegrees < 0.01f);
	TestTrue(TEXT("no correction"), R.Correction.GetAngle() < 1e-4f);
	for (int32 Index = 0; Index < Rig.Chain.Num(); ++Index)
	{
		TestTrue(FString::Printf(TEXT("chain %d unchanged"), Index), R.Chain[Index].Equals(Rig.Chain[Index], 1e-3f));
	}
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralAimCorrectionFarTest, "AstralBreak.AimCorrection.Far", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralAimCorrectionFarTest::RunTest(const FString& Parameters)
{
	// AO 대각 수준 오차(Yaw 10 · Pitch −6) — 원거리라 한 번에 거의 맞고 반복으로 마무리
	const FAimRig Rig;
	const FVector Target = TargetFrom(Rig.MuzzleLocation(), 10.f, -6.f, 5000.f);
	const FAstralAimCorrectionResult R = AstralAimCorrection::Solve(Rig.Input(Target));
	TestTrue(TEXT("valid"), R.bValid);
	TestTrue(FString::Printf(TEXT("initial ≈ 11.6 (%.2f)"), R.InitialErrorDegrees), FMath::IsNearlyEqual(R.InitialErrorDegrees, 11.65f, 0.3f));
	TestTrue(FString::Printf(TEXT("residual < 0.05 (%.4f)"), R.ResidualErrorDegrees), R.ResidualErrorDegrees < 0.05f);
	// 솔버 밖에서 독립 검증 — 보정된 체인으로 손을 옮겨 총열이 조준점을 보는가
	const float Check = AngleDeg(BarrelAfter(Rig, R), Target - MuzzleAfter(Rig, R));
	TestTrue(FString::Printf(TEXT("independent barrel check < 0.05 (%.4f)"), Check), Check < 0.05f);
	// 척추 본 위치는 체인 뿌리가 그대로 — 회전만
	TestTrue(TEXT("root bone stays"), R.Chain[0].GetLocation().Equals(Rig.Chain[0].GetLocation(), 1e-3f));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralAimCorrectionNearTest, "AstralBreak.AimCorrection.NearParallax", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralAimCorrectionNearTest::RunTest(const FString& Parameters)
{
	// 2m 앞 조준점 — 척추 피벗 기준 회전이 총구를 옮겨 방향이 바뀐다(시차). 총열을 "지금 총구 → 조준점" 방향으로만 돌리면 87cm 반경으로 움직인 총구 때문에
	// 오차가 진동하며 천천히 준다(손 계산: 15° → −6.4 → +2.7 → −1.2). 솔버는 회전 중심 기준으로 총열 직선이 조준점을 지나게 풀어 바로 수렴해야 한다
	const FAimRig Rig;
	for (const FVector2f& YawPitch : { FVector2f(15.f, 0.f), FVector2f(15.f, -20.f), FVector2f(-10.f, 25.f) })
	{
		const FVector Target = TargetFrom(Rig.MuzzleLocation(), YawPitch.X, YawPitch.Y, 200.f);
		const FAstralAimCorrectionResult R = AstralAimCorrection::Solve(Rig.Input(Target));
		const FString Case = FString::Printf(TEXT("yaw %.0f pitch %.0f @2m"), YawPitch.X, YawPitch.Y);
		TestTrue(FString::Printf(TEXT("%s converges (%.2f → %.4f)"), *Case, R.InitialErrorDegrees, R.ResidualErrorDegrees), R.ResidualErrorDegrees < 0.05f);
		const float Check = AngleDeg(BarrelAfter(Rig, R), Target - MuzzleAfter(Rig, R));
		TestTrue(FString::Printf(TEXT("%s independent barrel check < 0.05 (%.4f)"), *Case, Check), Check < 0.05f);
	}
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralAimCorrectionClampTest, "AstralBreak.AimCorrection.Clamp", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralAimCorrectionClampTest::RunTest(const FString& Parameters)
{
	// AO 범위 밖(60°) 오차 — 최대각 30 만큼만 돌리고 나머지는 남긴다
	const FAimRig Rig;
	const FAstralAimCorrectionResult R = AstralAimCorrection::Solve(Rig.Input(TargetFrom(Rig.MuzzleLocation(), 60.f, 0.f, 5000.f), 30.f));
	TestTrue(TEXT("valid"), R.bValid);
	TestTrue(FString::Printf(TEXT("correction clamped to 30 (%.3f)"), FMath::RadiansToDegrees(R.Correction.GetAngle())),
		FMath::IsNearlyEqual(FMath::RadiansToDegrees(R.Correction.GetAngle()), 30.f, 0.01f));
	TestTrue(FString::Printf(TEXT("residual ≈ 30 (%.2f)"), R.ResidualErrorDegrees), FMath::IsNearlyEqual(R.ResidualErrorDegrees, 30.f, 1.f));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralAimCorrectionWeightsTest, "AstralBreak.AimCorrection.Weights", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralAimCorrectionWeightsTest::RunTest(const FString& Parameters)
{
	// 본마다 받은 회전 = 전체 × 가중치 비율 (합 정규화 — 2:3:5 와 0.2:0.3:0.5 가 같다). 음수 가중치는 0
	FAimRig Rig;
	Rig.Weights = { 2.f, 3.f, 5.f };
	const FVector Target = TargetFrom(Rig.MuzzleLocation(), 12.f, 0.f, 5000.f);
	const FAstralAimCorrectionResult R = AstralAimCorrection::Solve(Rig.Input(Target));
	const float Total = FMath::RadiansToDegrees(R.Correction.GetAngle());
	const float Shares[] = { 0.2f, 0.3f, 0.5f };
	for (int32 Index = 0; Index < 3; ++Index)
	{
		// 본 i 의 누적 회전 = 앞 본들 몫 + 자기 몫 → 자기 몫 = 누적 차
		const FQuat Own = R.Chain[Index].GetRotation() * Rig.Chain[Index].GetRotation().Inverse();
		const FQuat Prev = Index > 0 ? R.Chain[Index - 1].GetRotation() * Rig.Chain[Index - 1].GetRotation().Inverse() : FQuat::Identity;
		const float Step = FMath::RadiansToDegrees((Own * Prev.Inverse()).GetAngle());
		TestTrue(FString::Printf(TEXT("bone %d share %.2f of %.2f (got %.3f)"), Index, Shares[Index], Total, Step), FMath::IsNearlyEqual(Step, Total * Shares[Index], 0.02f));
	}

	Rig.Weights = { -1.f, 0.f, 1.f };
	const FAstralAimCorrectionResult TipOnly = AstralAimCorrection::Solve(Rig.Input(Target));
	TestTrue(TEXT("negative/zero weights leave bone 0 alone"), TipOnly.Chain[0].Equals(Rig.Chain[0], 1e-3f));
	TestTrue(TEXT("tip-only still converges"), TipOnly.ResidualErrorDegrees < 0.05f);

	Rig.Weights = { 0.f, 0.f, 0.f };
	TestFalse(TEXT("all-zero weights → invalid (pose untouched)"), AstralAimCorrection::Solve(Rig.Input(Target)).bValid);
	return true;
}

#endif
