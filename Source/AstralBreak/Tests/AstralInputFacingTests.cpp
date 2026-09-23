// 락온 7단계 순수 계산 테스트 — 샘플 양자화·직렬화 · 회전 부호와 수용 폭 · 창 교차 시간 · 기준축 합성.
// 월드 의존이 없어 -ExecCmds="Automation RunTests AstralBreak.InputFacing"로 돈다.
// Modifier 수명·CMC 보정·관찰자 표현은 PIE 검증 (stage-7-moveinput-facing.md §9)

#include "Misc/AutomationTest.h"
#include "Combat/AstralInputFacingTypes.h"
#include "Serialization/BitReader.h"
#include "Serialization/BitWriter.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralInputFacingSampleTest, "AstralBreak.InputFacing.Sample", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralInputFacingSampleTest::RunTest(const FString& Parameters)
{
	using namespace AstralInputFacing;
	constexpr float Tolerance = 0.01f;

	// 크기 양자화 — 경계·클램프
	TestEqual(TEXT("mag 0"), QuantizeMagnitude(0.f), static_cast<uint8>(0));
	TestEqual(TEXT("mag 1"), QuantizeMagnitude(1.f), static_cast<uint8>(255));
	TestEqual(TEXT("mag >1 clamps"), QuantizeMagnitude(1.41f), static_cast<uint8>(255));
	TestEqual(TEXT("mag <0 clamps"), QuantizeMagnitude(-0.5f), static_cast<uint8>(0));
	TestNearlyEqual(TEXT("mag roundtrip 0.5"), DequantizeMagnitude(QuantizeMagnitude(0.5f)), 0.5f, Tolerance);

	// 부호 선택 — 최단각 부호, 정확한 180은 기본 부호
	TestTrue(TEXT("sign: 0 -> 90 positive"), ChooseTurnSign(0.f, 90.f));
	TestFalse(TEXT("sign: 0 -> -90 negative"), ChooseTurnSign(0.f, -90.f));
	TestTrue(TEXT("sign: wrap 170 -> -170 positive (shortest +20)"), ChooseTurnSign(170.f, -170.f));
	TestFalse(TEXT("sign: wrap -170 -> 170 negative (shortest -20)"), ChooseTurnSign(-170.f, 170.f));
	TestEqual(TEXT("sign: exact 180 = default"), ChooseTurnSign(0.f, 180.f), DefaultPositiveTurn);
	TestEqual(TEXT("sign: exact -180 = default"), ChooseTurnSign(0.f, -180.f), DefaultPositiveTurn);

	// MakeSample — 방향·크기·부호·억제
	{
		const FAstralInputFacingSample S = MakeSample(FVector(0.f, 1.f, 0.f), 0.f, false);
		TestTrue(TEXT("make: has input"), S.HasInput());
		TestNearlyEqual(TEXT("make: yaw +90"), S.GetInputYaw(), 90.f, Tolerance);
		TestNearlyEqual(TEXT("make: mag 1"), S.GetInputMagnitude(), 1.f, Tolerance);
		TestTrue(TEXT("make: sign +"), S.bPositiveTurn);
		TestFalse(TEXT("make: no suppress"), S.bSuppressInputFacing);
	}
	{
		// 대각(크기 √2) → 1로 클램프, 방향 유지. Z는 무시
		const FAstralInputFacingSample S = MakeSample(FVector(1.f, -1.f, 5.f), 0.f, true);
		TestNearlyEqual(TEXT("make: diagonal yaw -45"), S.GetInputYaw(), -45.f, Tolerance);
		TestNearlyEqual(TEXT("make: diagonal mag clamped"), S.GetInputMagnitude(), 1.f, Tolerance);
		TestFalse(TEXT("make: diagonal sign -"), S.bPositiveTurn);
		TestTrue(TEXT("make: suppress kept"), S.bSuppressInputFacing);
	}
	{
		// 무입력 정규화 — Yaw 0 · 기본 부호, 억제는 독립 유지
		const FAstralInputFacingSample S = MakeSample(FVector::ZeroVector, 123.f, true);
		TestFalse(TEXT("none: no input"), S.HasInput());
		TestEqual(TEXT("none: yaw 0"), S.WorldInputYaw, static_cast<uint16>(0));
		TestEqual(TEXT("none: default sign"), S.bPositiveTurn, DefaultPositiveTurn);
		TestTrue(TEXT("none: suppress kept"), S.bSuppressInputFacing);
	}
	{
		// 부호는 현재 Yaw 기준 — 같은 입력도 자세에 따라 갈린다
		const FAstralInputFacingSample A = MakeSample(FVector(1.f, 0.f, 0.f), 100.f, false);
		const FAstralInputFacingSample B = MakeSample(FVector(1.f, 0.f, 0.f), -100.f, false);
		TestFalse(TEXT("make: from +100 to 0 is negative"), A.bPositiveTurn);
		TestTrue(TEXT("make: from -100 to 0 is positive"), B.bPositiveTurn);
	}

	// 비트 직렬화 왕복 — 26비트, 로드 후 정규화
	{
		FAstralInputFacingSample Source = MakeSample(FVector(-1.f, 0.3f, 0.f), 30.f, true);

		FBitWriter Writer(64);
		Source.SerializeBits(Writer);
		TestEqual(TEXT("serialize: bit count"), Writer.GetNumBits(), SampleNumBits);

		FBitReader Reader(Writer.GetData(), Writer.GetNumBits());
		FAstralInputFacingSample Loaded;
		Loaded.SerializeBits(Reader);
		TestTrue(TEXT("serialize: roundtrip equal"), Loaded == Source);
		TestFalse(TEXT("serialize: no error"), Reader.IsError());
	}
	{
		// 크기 0인데 Yaw·부호가 더러운 샘플은 로드 시 정규화된다
		FAstralInputFacingSample Dirty;
		Dirty.InputMagnitude = 0;
		Dirty.WorldInputYaw = 4321;
		Dirty.bPositiveTurn = !DefaultPositiveTurn;
		Dirty.bSuppressInputFacing = true;

		FBitWriter Writer(64);
		Dirty.SerializeBits(Writer);
		FBitReader Reader(Writer.GetData(), Writer.GetNumBits());
		FAstralInputFacingSample Loaded;
		Loaded.SerializeBits(Reader);
		TestEqual(TEXT("serialize: none normalized yaw"), Loaded.WorldInputYaw, static_cast<uint16>(0));
		TestEqual(TEXT("serialize: none normalized sign"), Loaded.bPositiveTurn, DefaultPositiveTurn);
		TestTrue(TEXT("serialize: suppress survives normalization"), Loaded.bSuppressInputFacing);
	}

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralInputFacingTurnDeltaTest, "AstralBreak.InputFacing.TurnDelta", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralInputFacingTurnDeltaTest::RunTest(const FString& Parameters)
{
	using namespace AstralInputFacing;
	constexpr float Tolerance = 0.001f;
	constexpr float Accept = 2.f;

	// 부호 일치 — 속도 제한, 목표 근처 정지(오버슈트 방지)
	TestNearlyEqual(TEXT("match: +100 step 30 -> +30"), ComputeTurnDelta(100.f, true, 30.f, Accept), 30.f, Tolerance);
	TestNearlyEqual(TEXT("match: -100 step 30 -> -30"), ComputeTurnDelta(-100.f, false, 30.f, Accept), -30.f, Tolerance);
	TestNearlyEqual(TEXT("match: +10 step 30 -> +10 (no overshoot)"), ComputeTurnDelta(10.f, true, 30.f, Accept), 10.f, Tolerance);
	TestNearlyEqual(TEXT("match: -10 step 30 -> -10"), ComputeTurnDelta(-10.f, false, 30.f, Accept), -10.f, Tolerance);
	TestNearlyEqual(TEXT("huge step: +100 step 1000 -> +100"), ComputeTurnDelta(100.f, true, 1000.f, Accept), 100.f, Tolerance);

	// 부호 불일치 (폭 밖) → 0
	TestNearlyEqual(TEXT("mismatch: +100 with - -> 0"), ComputeTurnDelta(100.f, false, 30.f, Accept), 0.f, Tolerance);
	TestNearlyEqual(TEXT("mismatch: -100 with + -> 0"), ComputeTurnDelta(-100.f, true, 30.f, Accept), 0.f, Tolerance);
	TestNearlyEqual(TEXT("mismatch: -177 with + (outside 178) -> 0"), ComputeTurnDelta(-177.f, true, 30.f, Accept), 0.f, Tolerance);
	TestNearlyEqual(TEXT("mismatch: +177 with - (outside 178) -> 0"), ComputeTurnDelta(177.f, false, 30.f, Accept), 0.f, Tolerance);

	// 수용 폭 안 — 제출 부호 방향 거리 (360 - |Error|)
	TestNearlyEqual(TEXT("accept: -179 with + -> +30 (remaining 181)"), ComputeTurnDelta(-179.f, true, 30.f, Accept), 30.f, Tolerance);
	TestNearlyEqual(TEXT("accept: -179 with + huge step -> +181"), ComputeTurnDelta(-179.f, true, 1000.f, Accept), 181.f, Tolerance);
	TestNearlyEqual(TEXT("accept: +179 with - huge step -> -181"), ComputeTurnDelta(179.f, false, 1000.f, Accept), -181.f, Tolerance);
	TestNearlyEqual(TEXT("accept: -178 boundary with + -> +30"), ComputeTurnDelta(-178.f, true, 30.f, Accept), 30.f, Tolerance);
	TestNearlyEqual(TEXT("accept: exact +180 with + huge -> +180"), ComputeTurnDelta(180.f, true, 1000.f, Accept), 180.f, Tolerance);
	TestNearlyEqual(TEXT("accept: exact -180 with + huge -> +180"), ComputeTurnDelta(-180.f, true, 1000.f, Accept), 180.f, Tolerance);
	TestNearlyEqual(TEXT("accept: exact 180 with - huge -> -180"), ComputeTurnDelta(180.f, false, 1000.f, Accept), -180.f, Tolerance);
	// 폭 0이면 정확한 180만 수용
	TestNearlyEqual(TEXT("accept width 0: -179 with + -> 0"), ComputeTurnDelta(-179.f, true, 30.f, 0.f), 0.f, Tolerance);
	TestNearlyEqual(TEXT("accept width 0: exact 180 with + -> +30"), ComputeTurnDelta(180.f, true, 30.f, 0.f), 30.f, Tolerance);

	// 무효 입력
	TestNearlyEqual(TEXT("zero error -> 0"), ComputeTurnDelta(0.f, true, 30.f, Accept), 0.f, Tolerance);
	TestNearlyEqual(TEXT("zero step -> 0"), ComputeTurnDelta(100.f, true, 0.f, Accept), 0.f, Tolerance);
	TestNearlyEqual(TEXT("unnormalized error 460 = 100"), ComputeTurnDelta(460.f, true, 30.f, Accept), 30.f, Tolerance);

	// 수렴 — -179 오차에 + 부호를 고정한 채 반복 평가하면 180을 통과해 목표에 닿고, 한 번도 음의 회전이 나오지 않는다
	{
		const float TargetYaw = -179.f;
		float Yaw = 0.f;
		bool bAllNonNegative = true;
		int32 Steps = 0;
		for (; Steps < 20; ++Steps)
		{
			const float Error = FMath::FindDeltaAngleDegrees(Yaw, TargetYaw);
			if (FMath::Abs(Error) <= Tolerance)
			{
				break;
			}
			const float Delta = ComputeTurnDelta(Error, true, 30.f, Accept);
			if (Delta < 0.f)
			{
				bAllNonNegative = false;
			}
			if (FMath::IsNearlyZero(Delta))
			{
				break;
			}
			Yaw = FRotator::NormalizeAxis(Yaw + Delta);
		}
		TestTrue(TEXT("converge: never negative"), bAllNonNegative);
		TestNearlyEqual(TEXT("converge: reached target"), FMath::FindDeltaAngleDegrees(Yaw, TargetYaw), 0.f, Tolerance);
		TestEqual(TEXT("converge: 181/30 -> 7 steps"), Steps, 7);
	}
	{
		// 대칭 — +179 오차에 - 부호
		const float TargetYaw = 179.f;
		float Yaw = 0.f;
		bool bAllNonPositive = true;
		for (int32 Step = 0; Step < 20; ++Step)
		{
			const float Error = FMath::FindDeltaAngleDegrees(Yaw, TargetYaw);
			if (FMath::Abs(Error) <= Tolerance)
			{
				break;
			}
			const float Delta = ComputeTurnDelta(Error, false, 30.f, Accept);
			if (Delta > 0.f)
			{
				bAllNonPositive = false;
			}
			if (FMath::IsNearlyZero(Delta))
			{
				break;
			}
			Yaw = FRotator::NormalizeAxis(Yaw + Delta);
		}
		TestTrue(TEXT("converge mirror: never positive"), bAllNonPositive);
		TestNearlyEqual(TEXT("converge mirror: reached target"), FMath::FindDeltaAngleDegrees(Yaw, TargetYaw), 0.f, Tolerance);
	}

	// 보정으로 현재 Yaw만 어긋난 경우 — 클라 +179.9 / 서버 -179.9, 클라가 고른 + 부호를 서버도 수용한다 (교착 없음)
	{
		const float ClientDelta = ComputeTurnDelta(179.9f, true, 30.f, Accept);
		const float ServerDelta = ComputeTurnDelta(-179.9f, true, 30.f, Accept);
		TestNearlyEqual(TEXT("knife edge: client +30"), ClientDelta, 30.f, Tolerance);
		TestNearlyEqual(TEXT("knife edge: server +30 (accepted)"), ServerDelta, 30.f, Tolerance);
	}

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralInputFacingActiveSecondsTest, "AstralBreak.InputFacing.ActiveSeconds", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralInputFacingActiveSecondsTest::RunTest(const FString& Parameters)
{
	using namespace AstralInputFacing;
	constexpr float Tolerance = 0.0001f;
	// 창 [0.2, 0.5], PlayRate 1, 프레임 1/60
	const float Start = 0.2f, End = 0.5f, Dt = 1.f / 60.f;

	TestNearlyEqual(TEXT("fully inside"), ComputeActiveSeconds(0.30f, 0.30f + Dt, Start, End, 1.f, Dt), Dt, Tolerance);
	TestNearlyEqual(TEXT("entry partial: prev before start"), ComputeActiveSeconds(0.19f, 0.21f, Start, End, 1.f, 0.02f), 0.01f, Tolerance);
	TestNearlyEqual(TEXT("exit partial: cur after end"), ComputeActiveSeconds(0.49f, 0.52f, Start, End, 1.f, 0.03f), 0.01f, Tolerance);
	TestNearlyEqual(TEXT("before window"), ComputeActiveSeconds(0.10f, 0.15f, Start, End, 1.f, 0.05f), 0.f, Tolerance);
	TestNearlyEqual(TEXT("after window"), ComputeActiveSeconds(0.50f, 0.55f, Start, End, 1.f, 0.05f), 0.f, Tolerance);
	TestNearlyEqual(TEXT("whole window in one step"), ComputeActiveSeconds(0.10f, 0.60f, Start, End, 1.f, 0.5f), 0.3f, Tolerance);

	// PlayRate — 애니 시간 교차를 실제 시간으로 환산, 이번 평가 DeltaSeconds로 제한
	TestNearlyEqual(TEXT("playrate 2 halves"), ComputeActiveSeconds(0.30f, 0.34f, Start, End, 2.f, 0.02f), 0.02f, Tolerance);
	TestNearlyEqual(TEXT("playrate 0.5 doubles but clamped to dt"), ComputeActiveSeconds(0.30f, 0.31f, Start, End, 0.5f, 0.015f), 0.015f, Tolerance);

	// 지원하지 않는 진행 — 역행·PlayRate ≤ 0·창 길이 0
	TestNearlyEqual(TEXT("reverse -> 0"), ComputeActiveSeconds(0.35f, 0.30f, Start, End, 1.f, Dt), 0.f, Tolerance);
	TestNearlyEqual(TEXT("playrate 0 -> 0"), ComputeActiveSeconds(0.30f, 0.32f, Start, End, 0.f, Dt), 0.f, Tolerance);
	TestNearlyEqual(TEXT("negative playrate -> 0"), ComputeActiveSeconds(0.30f, 0.32f, Start, End, -1.f, Dt), 0.f, Tolerance);
	TestNearlyEqual(TEXT("zero-length window -> 0"), ComputeActiveSeconds(0.30f, 0.32f, 0.3f, 0.3f, 1.f, Dt), 0.f, Tolerance);

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralInputFacingComposeTest, "AstralBreak.InputFacing.Compose", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralInputFacingComposeTest::RunTest(const FString& Parameters)
{
	using namespace AstralInputFacing;
	constexpr float Tolerance = 0.01f;

	// 표준 마네킹 — 메시가 액터 기준 Yaw -90
	const FQuat MeshRelative = FRotator(0.f, -90.f, 0.f).Quaternion();
	const FQuat Actor = FRotator(0.f, 40.f, 0.f).Quaternion();

	// 원본 회전 없음 + 추가 +30 → 액터 Yaw 70
	{
		const FQuat Local = ComposeLocalRotation(Actor, MeshRelative, FQuat::Identity, 30.f);
		const FQuat Predicted = PredictActorRotation(Actor, MeshRelative, Local);
		TestNearlyEqual(TEXT("compose: identity + 30 -> 70"), static_cast<float>(Predicted.Rotator().Yaw), 70.f, Tolerance);
	}
	// 원본 로컬 Yaw +10 (메시 공간) — 예측만: 액터 Yaw 50
	{
		const FQuat OriginalLocal = FRotator(0.f, 10.f, 0.f).Quaternion();
		const FQuat Predicted = PredictActorRotation(Actor, MeshRelative, OriginalLocal);
		TestNearlyEqual(TEXT("predict: original +10 -> 50"), static_cast<float>(Predicted.Rotator().Yaw), 50.f, Tolerance);
	}
	// 원본 +10 + 추가 +20 → 액터 Yaw 70 (원본과 추가가 중복되지 않는다)
	{
		const FQuat OriginalLocal = FRotator(0.f, 10.f, 0.f).Quaternion();
		const FQuat Local = ComposeLocalRotation(Actor, MeshRelative, OriginalLocal, 20.f);
		const FQuat Predicted = PredictActorRotation(Actor, MeshRelative, Local);
		TestNearlyEqual(TEXT("compose: original +10 add +20 -> 70"), static_cast<float>(Predicted.Rotator().Yaw), 70.f, Tolerance);
	}
	// 추가 음수 · 랩어라운드
	{
		const FQuat Local = ComposeLocalRotation(FRotator(0.f, 170.f, 0.f).Quaternion(), MeshRelative, FQuat::Identity, 30.f);
		const FQuat Predicted = PredictActorRotation(FRotator(0.f, 170.f, 0.f).Quaternion(), MeshRelative, Local);
		TestNearlyEqual(TEXT("compose: 170 + 30 wraps to -160"), static_cast<float>(Predicted.Rotator().Yaw), -160.f, Tolerance);
	}
	{
		const FQuat Local = ComposeLocalRotation(Actor, MeshRelative, FQuat::Identity, -50.f);
		const FQuat Predicted = PredictActorRotation(Actor, MeshRelative, Local);
		TestNearlyEqual(TEXT("compose: 40 - 50 -> -10"), static_cast<float>(Predicted.Rotator().Yaw), -10.f, Tolerance);
	}
	// 추가 0이면 원본 그대로
	{
		const FQuat OriginalLocal = FRotator(0.f, 10.f, 0.f).Quaternion();
		const FQuat Local = ComposeLocalRotation(Actor, MeshRelative, OriginalLocal, 0.f);
		TestTrue(TEXT("compose: zero add keeps original"), Local.Equals(OriginalLocal, 1e-6f));
	}

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
