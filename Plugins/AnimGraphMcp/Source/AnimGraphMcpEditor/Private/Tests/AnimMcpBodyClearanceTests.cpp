// 팔-몸통 관통 보정(Core/AnimMcpBodyClearance)의 계산부 단위 테스트 — 최소제곱 어깨 회전과 시간 평활, 반경 지도 · 몸통 칸 · 모델 인코딩(Phase 8-4a) · 손끼리 지도(8-4b).
// 애셋 없이 메모리에서만. run_automation_tests {filter:"AnimGraphMcp.Generation.BodyClearance"} 로 돈다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Core/AnimMcpBodyClearance.h"
#include "Misc/Base64.h"

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

	// ---- 반경 지도 (8-4a 공개 — anim_gen/body_model.py 와 같은 규칙): Z 축 원통(반경 10) 정점 → 안(반경 6) 깊이 +4 · 밖(15) −5 · 빈 칸 = 이웃 · t 범위 밖 ----
	{
		using AnimMcpBodyClearance::AngleBins;
		AnimMcpBodyClearance::FRadialAxis Axis;
		Axis.Init(FVector::ZeroVector, FVector(0.0, 0.0, 100.0), FVector(1.0, 0.0, 0.0), 0.0, 1.0, 10);
		TestTrue(TEXT("axis valid"), Axis.bValid);
		TestTrue(TEXT("angle basis: X = lateral, Y = Dir × X"), Axis.X.Equals(FVector(1, 0, 0)) && Axis.Y.Equals(FVector(0, 1, 0)));
		const auto AngleOf = [](int32 Bin) { return -UE_DOUBLE_PI + (Bin + 0.5) * 2.0 * UE_DOUBLE_PI / AngleBins; };
		int32 Index = 0;
		for (int32 Z = 5; Z < 100; Z += 10)
		{
			for (int32 Bin = 0; Bin < AngleBins; ++Bin)
			{
				if (Z == 55 && Bin == 9) { continue; }   // 구멍 하나
				Axis.Add(FVector(10.0 * FMath::Cos(AngleOf(Bin)), 10.0 * FMath::Sin(AngleOf(Bin)), Z), Index++);
			}
		}
		auto DepthAt = [&Axis](const FVector& P, double& OutDepth)
		{
			int32 T, Angle, Who;
			FVector Radial;
			if (!Axis.Locate(P, T, Angle, Radial)) { return false; }
			const double Rho = Axis.Radius(T, Angle, Who);
			OutDepth = Rho - Radial.Size();
			return Rho >= 0.0;
		};
		double Depth = 0.0;
		TestTrue(TEXT("inside point located"), DepthAt(FVector(6.0 * FMath::Cos(AngleOf(0)), 6.0 * FMath::Sin(AngleOf(0)), 55.0), Depth));
		TestEqual(TEXT("inside depth = 10 − 6"), Depth, 4.0, 1e-6);
		TestTrue(TEXT("outside point located"), DepthAt(FVector(15.0 * FMath::Cos(AngleOf(18)), 15.0 * FMath::Sin(AngleOf(18)), 35.0), Depth));
		TestEqual(TEXT("outside depth = 10 − 15 (signed gap)"), Depth, -5.0, 1e-6);
		TestTrue(TEXT("empty cell takes the 3x3 neighbour max"), DepthAt(FVector(8.0 * FMath::Cos(AngleOf(9)), 8.0 * FMath::Sin(AngleOf(9)), 55.0), Depth) && FMath::IsNearlyEqual(Depth, 2.0, 1e-6));
		TestFalse(TEXT("beyond t_max is not located"), DepthAt(FVector(0.0, 5.0, 120.0), Depth));
		TestEqual(TEXT("bin centre"), Axis.BinCenter(3), 0.35, 1e-9);
		AnimMcpBodyClearance::FRadialAxis Lone;
		Lone.Init(FVector::ZeroVector, FVector(0.0, 0.0, 100.0), FVector(1.0, 0.0, 0.0), 0.0, 1.0, 10);
		Lone.Add(FVector(10.0, 0.0, 5.0), 0);
		int32 Who = 0;
		TestTrue(TEXT("cell with no filled neighbour is −1"), Lone.Radius(9, 0, Who) < 0.0);
	}

	// ---- 손끼리 (8-4b): 손 끝 = 무게중심 방향 최대 투영 · 손 지도 원통(반경 2.5)에 다른 손 원통 — 겹치면 겹침 깊이, 떨어지면 음수 틈 ----
	{
		using AnimMcpBodyClearance::AngleBins;
		const FVector Elbow(-25.0, 0.0, 0.0), Wrist = FVector::ZeroVector;
		TArray<FVector> Line;
		for (int32 X = 2; X <= 10; ++X) { Line.Append({ FVector(X, 1.0, 0.0), FVector(X, -1.0, 0.0) }); }
		TestTrue(TEXT("hand tip = farthest projection toward the hand centroid"), AnimMcpBodyClearance::HandTip(Line, Elbow, Wrist).Equals(FVector(10.0, 0.0, 0.0), 1e-9));
		TestTrue(TEXT("centroid on the wrist → forearm direction"), AnimMcpBodyClearance::HandTip({ FVector(3, 0, 0), FVector(-3, 0, 0) }, Elbow, Wrist).Equals(FVector(3.0, 0.0, 0.0), 1e-9));
		TestTrue(TEXT("no hand points → the wrist (no axis)"), AnimMcpBodyClearance::HandTip({}, Elbow, Wrist).Equals(Wrist));

		const FVector Lateral(0.0, 1.0, 0.0);
		const auto AngleOf = [](int32 Bin) { return -UE_DOUBLE_PI + (Bin + 0.5) * 2.0 * UE_DOUBLE_PI / AngleBins; };
		// 축 (A → A + 10 X) 둘레 반경 R 원통 점 — 손 지도의 각도 기준(X = Lateral ⊥ = +Y · Y = Dir × X = +Z)과 같은 각도로
		const auto Cylinder = [&AngleOf](const FVector& A, double Length, double R, double T0, double T1, int32 Bins)
		{
			TArray<FVector> Out;
			for (int32 T = 0; T < Bins; ++T)
			{
				const double X = (T0 + (T + 0.5) / Bins * (T1 - T0)) * Length;
				for (int32 Bin = 0; Bin < AngleBins; ++Bin) { Out.Add(A + FVector(X, R * FMath::Cos(AngleOf(Bin)), R * FMath::Sin(AngleOf(Bin)))); }
			}
			return Out;
		};
		AnimMcpBodyClearance::FArmAxes Arm;
		Arm.Init(Elbow, Wrist, FVector(10.0, 0.0, 0.0), Lateral);
		TestTrue(TEXT("hand map: wrist → tip, t −0.15 ~ 1.05 · 12 bins"), Arm.Hand.bValid && Arm.Hand.TBins == 12 && FMath::IsNearlyEqual(Arm.Hand.TMin, -0.15) && FMath::IsNearlyEqual(Arm.Hand.TMax, 1.05)
			&& FMath::IsNearlyEqual(Arm.Hand.Length, 10.0));
		TestTrue(TEXT("forearm map: elbow → wrist, t −0.1 ~ 1.05 · 14 bins"), Arm.Forearm.bValid && Arm.Forearm.TBins == 14 && FMath::IsNearlyEqual(Arm.Forearm.Length, 25.0));
		int32 Index = 0;
		for (const FVector& P : Cylinder(Wrist, 10.0, 2.5, -0.15, 1.05, 12)) { Arm.Hand.Add(P, Index++); }
		for (const FVector& P : Cylinder(Elbow, 25.0, 3.5, -0.1, 1.05, 14)) { Arm.Forearm.Add(P, Index++); }
		// 다른 손 점들이 이 지도에 묻는 가장 깊은 값(부호 있음)
		const auto Deepest = [](const AnimMcpBodyClearance::FRadialAxis& Axis, const TArray<FVector>& Points, double& OutDepth)
		{
			bool bFound = false;
			for (const FVector& P : Points)
			{
				int32 T, Angle, Who;
				FVector Radial;
				if (!Axis.Locate(P, T, Angle, Radial)) { continue; }
				const double Rho = Axis.Radius(T, Angle, Who);
				if (Rho < 0.0) { continue; }
				OutDepth = bFound ? FMath::Max(OutDepth, Rho - Radial.Size()) : Rho - Radial.Size();
				bFound = true;
			}
			return bFound;
		};
		double Depth = 0.0;
		// 다른 손 = 같은 방향 원통(반경 2.5) — 축 사이 4 cm 면 반경 합 5 와 1 cm 겹친다(각도 칸 가운데 점이라 ±0.05)
		TestTrue(TEXT("overlapping hands located"), Deepest(Arm.Hand, Cylinder(FVector(0.0, 0.0, 4.0), 10.0, 2.5, 0.0, 1.0, 10), Depth));
		TestEqual(TEXT("overlap depth ≈ 2.5 + 2.5 − 4"), Depth, 1.0, 0.05);
		TestTrue(TEXT("separated hands located"), Deepest(Arm.Hand, Cylinder(FVector(0.0, 0.0, 7.0), 10.0, 2.5, 0.0, 1.0, 10), Depth));
		TestEqual(TEXT("separated → negative gap ≈ 5 − 7"), Depth, -2.0, 0.05);
		TestTrue(TEXT("a point beside the forearm"), Deepest(Arm.Forearm, { FVector(-12.0, 0.0, 2.0) }, Depth) && FMath::IsNearlyEqual(Depth, 1.5, 1e-6));
		TestFalse(TEXT("beyond the hand tip is not on the hand map"), Deepest(Arm.Hand, { FVector(12.0, 0.0, 0.5) }, Depth));
	}

	// ---- 몸통 칸 · 내보내기 인코딩 ----
	{
		TestEqual(TEXT("torso part pelvis"), FString(AnimMcpBodyClearance::TorsoPart(0.10, 0.2, 0.5)), FString(TEXT("pelvis")));
		TestEqual(TEXT("torso part belly"), FString(AnimMcpBodyClearance::TorsoPart(0.30, 0.2, 0.5)), FString(TEXT("belly")));
		TestEqual(TEXT("torso part chest"), FString(AnimMcpBodyClearance::TorsoPart(0.75, 0.2, 0.5)), FString(TEXT("chest")));
		TArray<uint8> Bytes;
		TestTrue(TEXT("i16 base64 decodes"), FBase64::Decode(AnimMcpBodyClearance::EncodeI16({ 1.234, -1.0, 400.0, 0.0 }, 0.01), Bytes) && Bytes.Num() == 8);
		auto I16 = [&Bytes](int32 i) { return static_cast<int16>(static_cast<uint16>(Bytes[2 * i]) | (static_cast<uint16>(Bytes[2 * i + 1]) << 8)); };
		TestTrue(TEXT("i16 values (0.01 cm, empty, clamped, zero)"), I16(0) == 123 && I16(1) == AnimMcpBodyClearance::EmptyRadiusI16 && I16(2) == 32767 && I16(3) == 0);
		TestTrue(TEXT("f32 base64 decodes"), FBase64::Decode(AnimMcpBodyClearance::EncodeF32({ 1.5, -2.25 }), Bytes) && Bytes.Num() == 8);
		float F[2];
		FMemory::Memcpy(F, Bytes.GetData(), 8);
		TestTrue(TEXT("f32 little-endian values"), F[0] == 1.5f && F[1] == -2.25f);
	}
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
