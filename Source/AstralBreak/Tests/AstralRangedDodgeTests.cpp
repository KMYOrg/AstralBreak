// 락온 6단계 순수 계산 테스트 — 발사 허용각 경계 · 원거리/회피 페이로드 직렬화 · 회피 방향 우선순위
// + 원격 발사 데이터(클라 조준 보고) 직렬화·추출 · 보고 방향 허용각 검증(수락/클램프/거부) · 보고 조준점 전방·사거리 다듬기.
// 월드 의존이 없어 -ExecCmds="Automation RunTests AstralBreak.Ranged" / "AstralBreak.Dodge"로 돈다.
// 노티파이 저작 검증·실제 발사·복제·총구 차단은 PIE 수동 검증 (stage-6-existing-integration.md)

#include "Misc/AutomationTest.h"
#include "Combat/AstralDodgeTypes.h"
#include "Combat/AstralFacingTypes.h"
#include "Combat/AstralRangedAttackTypes.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralRangedFireAssistTest, "AstralBreak.Ranged.FireAssist", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralRangedFireAssistTest::RunTest(const FString& Parameters)
{
	using namespace AstralRangedAttack;
	using E = EAstralFireAssistResult;

	FAstralFireAssistParams Params;
	Params.MaxRange = 2200.f;
	Params.MaxAssistYaw = 60.f;
	Params.MinDistanceForYawCheck = 100.f;

	TestEqual(TEXT("in front"), CheckFireAssist(500.f, 0.f, 30.f, Params), E::Ok);
	TestEqual(TEXT("at yaw limit"), CheckFireAssist(500.f, 0.f, 60.f, Params), E::Ok);
	TestEqual(TEXT("beyond yaw limit"), CheckFireAssist(500.f, 0.f, 61.f, Params), E::OutOfAssistYaw);
	TestEqual(TEXT("behind"), CheckFireAssist(500.f, 0.f, 180.f, Params), E::OutOfAssistYaw);
	TestEqual(TEXT("wrap 170 vs -170"), CheckFireAssist(500.f, 170.f, -170.f, Params), E::Ok);

	// 거리 — 경계 · 초과가 각도보다 먼저
	TestEqual(TEXT("at range"), CheckFireAssist(2200.f, 0.f, 0.f, Params), E::Ok);
	TestEqual(TEXT("beyond range"), CheckFireAssist(2201.f, 0.f, 0.f, Params), E::OutOfRange);
	TestEqual(TEXT("far and behind -> range"), CheckFireAssist(3000.f, 0.f, 180.f, Params), E::OutOfRange);

	// 근거리 완화
	TestEqual(TEXT("close: any yaw"), CheckFireAssist(99.f, 0.f, 180.f, Params), E::Ok);
	TestEqual(TEXT("at min distance: yaw checked"), CheckFireAssist(100.f, 0.f, 180.f, Params), E::OutOfAssistYaw);

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralRangedPayloadTest, "AstralBreak.Ranged.Payload", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralRangedPayloadTest::RunTest(const FString& Parameters)
{
	// 직렬화 왕복 (액터 없는 LockOn 제안 + 폴백 조준점). FVector_NetQuantize는 1cm 양자화 — 그 안에서 같아야 한다
	{
		FAstralRangedActivationData Source;
		Source.BodyFacing.Source = EAstralFacingSource::LockOn;
		Source.BodyFacing.QuantizedDesiredYaw = 1234;
		Source.FallbackAimPoint = FVector(1234.f, -567.f, 89.f);
		FGameplayAbilityTargetData_AstralRangedActivation Payload(Source);

		TArray<uint8> Bytes;
		FMemoryWriter Writer(Bytes);
		bool bSuccess = false;
		Payload.NetSerialize(Writer, nullptr, bSuccess);
		TestTrue(TEXT("write"), bSuccess);

		FGameplayAbilityTargetData_AstralRangedActivation Loaded;
		FMemoryReader Reader(Bytes);
		Loaded.NetSerialize(Reader, nullptr, bSuccess);
		TestTrue(TEXT("read"), bSuccess);
		TestTrue(TEXT("facing equal"), Loaded.Data.BodyFacing == Source.BodyFacing);
		TestTrue(TEXT("aim point within 1cm"), Loaded.Data.FallbackAimPoint.Equals(Source.FallbackAimPoint, 1.f));
		TestTrue(TEXT("lock-on preserved"), Loaded.Data.IsLockOn());
	}

	// None은 정규화 — Yaw가 실려도 비워지고, 조준점은 유지
	{
		FAstralRangedActivationData Source;
		Source.BodyFacing.Source = EAstralFacingSource::None;
		Source.BodyFacing.QuantizedDesiredYaw = 777;
		Source.FallbackAimPoint = FVector(100.f, 200.f, 300.f);
		FGameplayAbilityTargetData_AstralRangedActivation Payload(Source);

		TArray<uint8> Bytes;
		FMemoryWriter Writer(Bytes);
		bool bSuccess = false;
		Payload.NetSerialize(Writer, nullptr, bSuccess);
		FGameplayAbilityTargetData_AstralRangedActivation Loaded;
		FMemoryReader Reader(Bytes);
		Loaded.NetSerialize(Reader, nullptr, bSuccess);

		TestTrue(TEXT("none normalized"), Loaded.Data.BodyFacing.IsNone() && Loaded.Data.BodyFacing.QuantizedDesiredYaw == 0);
		TestTrue(TEXT("aim point kept"), Loaded.Data.FallbackAimPoint.Equals(Source.FallbackAimPoint, 1.f));
		TestFalse(TEXT("free aim"), Loaded.Data.IsLockOn());
	}

	// Extract — 구조 검증
	{
		FAstralRangedActivationData Out;
		FAstralRangedActivationData Valid;
		TestTrue(TEXT("valid"), FGameplayAbilityTargetData_AstralRangedActivation::Extract(FGameplayAbilityTargetData_AstralRangedActivation::MakeHandle(Valid), Out));
		TestFalse(TEXT("empty"), FGameplayAbilityTargetData_AstralRangedActivation::Extract(FGameplayAbilityTargetDataHandle(), Out));

		FAstralRangedActivationData WrongStage;
		WrongStage.BodyFacing.StageIndex = 1;
		TestFalse(TEXT("stage != 0"), FGameplayAbilityTargetData_AstralRangedActivation::Extract(FGameplayAbilityTargetData_AstralRangedActivation::MakeHandle(WrongStage), Out));

		FAstralRangedActivationData WithPoint;
		WithPoint.BodyFacing.Source = EAstralFacingSource::LockOn;
		WithPoint.BodyFacing.TargetPointId = FName(TEXT("Head"));
		TestFalse(TEXT("point id not allowed until M5"), FGameplayAbilityTargetData_AstralRangedActivation::Extract(FGameplayAbilityTargetData_AstralRangedActivation::MakeHandle(WithPoint), Out));

		FAstralRangedActivationData NanPoint;
		NanPoint.FallbackAimPoint = FVector(NAN, 0.f, 0.f);
		TestFalse(TEXT("nan aim point rejected"), FGameplayAbilityTargetData_AstralRangedActivation::Extract(FGameplayAbilityTargetData_AstralRangedActivation::MakeHandle(NanPoint), Out));

		// Facing 전용 페이로드는 원거리 추출기가 거부 — 기존 추출 계약과 섞이지 않는다
		FAstralFacingProposal Facing;
		TestFalse(TEXT("facing payload rejected"), FGameplayAbilityTargetData_AstralRangedActivation::Extract(FGameplayAbilityTargetData_AstralFacing::MakeHandle(Facing), Out));
		FAstralFacingProposal FacingOut;
		TestFalse(TEXT("ranged payload rejected by facing extractor"), FGameplayAbilityTargetData_AstralFacing::ExtractProposal(FGameplayAbilityTargetData_AstralRangedActivation::MakeHandle(Valid), 1, FacingOut));
	}

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralRangedFirePayloadTest, "AstralBreak.Ranged.FirePayload", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralRangedFirePayloadTest::RunTest(const FString& Parameters)
{
	// 직렬화 왕복 — 조준점 0.1cm 양자화, 방향 16비트 성분
	{
		FAstralRangedFireData Source;
		Source.AimPoint = FVector(1234.56, -789.01, 23.45);
		Source.AimDirection = FVector(0.3, -0.8, 0.2).GetSafeNormal();
		FGameplayAbilityTargetData_AstralRangedFire Payload(Source);

		TArray<uint8> Bytes;
		FMemoryWriter Writer(Bytes);
		bool bSuccess = false;
		Payload.NetSerialize(Writer, nullptr, bSuccess);
		TestTrue(TEXT("write"), bSuccess);

		FGameplayAbilityTargetData_AstralRangedFire Loaded;
		FMemoryReader Reader(Bytes);
		Loaded.NetSerialize(Reader, nullptr, bSuccess);
		TestTrue(TEXT("read"), bSuccess);
		TestTrue(TEXT("aim point within 0.1cm"), Loaded.Data.AimPoint.Equals(Source.AimPoint, 0.1));
		TestTrue(TEXT("direction within 1e-3"), Loaded.Data.AimDirection.Equals(Source.AimDirection, 1e-3));

		// 왕복한 방향도 추출의 단위 허용치(±0.01) 안
		FAstralRangedFireData Out;
		TestTrue(TEXT("round-tripped payload extracts"), FGameplayAbilityTargetData_AstralRangedFire::Extract(FGameplayAbilityTargetData_AstralRangedFire::MakeHandle(Loaded.Data), Out));
	}

	// Extract — 구조·값 검증
	{
		FAstralRangedFireData Out;
		FAstralRangedFireData Valid;
		Valid.AimPoint = FVector(100.0, 0.0, 0.0);
		Valid.AimDirection = FVector::ForwardVector;
		TestTrue(TEXT("valid"), FGameplayAbilityTargetData_AstralRangedFire::Extract(FGameplayAbilityTargetData_AstralRangedFire::MakeHandle(Valid), Out));
		TestTrue(TEXT("valid copied"), Out.AimPoint.Equals(Valid.AimPoint) && Out.AimDirection.Equals(Valid.AimDirection));
		TestFalse(TEXT("empty"), FGameplayAbilityTargetData_AstralRangedFire::Extract(FGameplayAbilityTargetDataHandle(), Out));

		// 클라가 조준을 해석하지 못하면 방향 0 으로 보낸다 — 서버는 거부(기준 방향)로 처리
		FAstralRangedFireData ZeroDirection = Valid;
		ZeroDirection.AimDirection = FVector::ZeroVector;
		TestFalse(TEXT("zero direction rejected"), FGameplayAbilityTargetData_AstralRangedFire::Extract(FGameplayAbilityTargetData_AstralRangedFire::MakeHandle(ZeroDirection), Out));

		FAstralRangedFireData LongDirection = Valid;
		LongDirection.AimDirection = FVector(2.0, 0.0, 0.0);
		TestFalse(TEXT("non-unit direction rejected"), FGameplayAbilityTargetData_AstralRangedFire::Extract(FGameplayAbilityTargetData_AstralRangedFire::MakeHandle(LongDirection), Out));

		FAstralRangedFireData NanPoint = Valid;
		NanPoint.AimPoint = FVector(NAN, 0.0, 0.0);
		TestFalse(TEXT("nan aim point rejected"), FGameplayAbilityTargetData_AstralRangedFire::Extract(FGameplayAbilityTargetData_AstralRangedFire::MakeHandle(NanPoint), Out));

		FAstralRangedFireData InfDirection = Valid;
		InfDirection.AimDirection = FVector(INFINITY, 0.0, 0.0);
		TestFalse(TEXT("inf direction rejected"), FGameplayAbilityTargetData_AstralRangedFire::Extract(FGameplayAbilityTargetData_AstralRangedFire::MakeHandle(InfDirection), Out));

		// 활성화 페이로드와 섞이지 않는다
		TestFalse(TEXT("activation payload rejected"), FGameplayAbilityTargetData_AstralRangedFire::Extract(FGameplayAbilityTargetData_AstralRangedActivation::MakeHandle(FAstralRangedActivationData()), Out));
		FAstralRangedActivationData ActivationOut;
		TestFalse(TEXT("fire payload rejected by activation extractor"), FGameplayAbilityTargetData_AstralRangedActivation::Extract(FGameplayAbilityTargetData_AstralRangedFire::MakeHandle(Valid), ActivationOut));
	}

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralRangedReportedAimTest, "AstralBreak.Ranged.ReportedAim", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralRangedReportedAimTest::RunTest(const FString& Parameters)
{
	using namespace AstralRangedAttack;
	using E = EAstralReportedAimResult;

	const auto AngleBetween = [](const FVector& A, const FVector& B)
	{
		return FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(A.GetSafeNormal(), B.GetSafeNormal()), -1.0, 1.0)));
	};
	const FVector Reference = FVector::ForwardVector;
	const FVector Yaw30 = FRotator(0.0, 30.0, 0.0).Vector();
	const FVector Yaw45 = FRotator(0.0, 45.0, 0.0).Vector();
	const FVector Yaw70 = FRotator(0.0, 70.0, 0.0).Vector();
	const FVector Pitch90 = FVector::UpVector;

	// 허용각 안 — 보고 그대로
	{
		const FAstralReportedAimCheck Same = CheckReportedAimDirection(Reference, Reference, 45.f);
		TestEqual(TEXT("same: accepted"), Same.Result, E::Accepted);
		TestTrue(TEXT("same: divergence 0"), FMath::IsNearlyZero(Same.Divergence, 1e-3f));

		const FAstralReportedAimCheck In = CheckReportedAimDirection(Yaw30 * 3.0, Reference, 45.f);
		TestEqual(TEXT("30 deg: accepted"), In.Result, E::Accepted);
		TestTrue(TEXT("30 deg: reported (normalized)"), In.Direction.Equals(Yaw30, 1e-6));
		TestTrue(TEXT("30 deg: divergence"), FMath::IsNearlyEqual(In.Divergence, 30.f, 1e-3f));

		TestEqual(TEXT("at limit (<=): accepted"), CheckReportedAimDirection(Yaw45, Reference, 45.f).Result, E::Accepted);
	}

	// 허용각 밖 — 기준에서 보고 쪽으로 허용각까지만 (옛 방향으로 되돌리지 않는다)
	{
		const FAstralReportedAimCheck Yaw = CheckReportedAimDirection(Yaw70, Reference, 45.f);
		TestEqual(TEXT("70 deg: clamped"), Yaw.Result, E::Clamped);
		TestTrue(TEXT("70 deg: 45 from reference"), FMath::IsNearlyEqual(AngleBetween(Yaw.Direction, Reference), 45.0, 1e-3));
		TestTrue(TEXT("70 deg: 25 from reported"), FMath::IsNearlyEqual(AngleBetween(Yaw.Direction, Yaw70), 25.0, 1e-3));
		TestTrue(TEXT("70 deg: divergence"), FMath::IsNearlyEqual(Yaw.Divergence, 70.f, 1e-3f));
		TestTrue(TEXT("70 deg: unit"), FMath::IsNearlyEqual(Yaw.Direction.Size(), 1.0, 1e-6));

		const FAstralReportedAimCheck Up = CheckReportedAimDirection(Pitch90, Reference, 45.f);
		TestEqual(TEXT("pitch 90: clamped"), Up.Result, E::Clamped);
		TestTrue(TEXT("pitch 90: toward up"), Up.Direction.Equals(FRotator(45.0, 0.0, 0.0).Vector(), 1e-6));

		// 정반대 — 회전축이 없어도 기준에서 정확히 허용각
		const FAstralReportedAimCheck Back = CheckReportedAimDirection(-Reference, Reference, 45.f);
		TestEqual(TEXT("opposite: clamped"), Back.Result, E::Clamped);
		TestTrue(TEXT("opposite: 45 from reference"), FMath::IsNearlyEqual(AngleBetween(Back.Direction, Reference), 45.0, 1e-3));

		// 기준이 수직(정반대 축 후보가 위쪽과 평행)이어도 같다
		const FAstralReportedAimCheck Vertical = CheckReportedAimDirection(-FVector::UpVector, FVector::UpVector, 45.f);
		TestEqual(TEXT("vertical opposite: clamped"), Vertical.Result, E::Clamped);
		TestTrue(TEXT("vertical opposite: 45 from reference"), FMath::IsNearlyEqual(AngleBetween(Vertical.Direction, FVector::UpVector), 45.0, 1e-3));
	}

	// 경계 값 — 180 이면 검증 없음, 0 이면 기준 그대로
	{
		TestEqual(TEXT("max 180: anything accepted"), CheckReportedAimDirection(-Reference, Reference, 180.f).Result, E::Accepted);
		const FAstralReportedAimCheck Zero = CheckReportedAimDirection(Yaw30, Reference, 0.f);
		TestEqual(TEXT("max 0: clamped"), Zero.Result, E::Clamped);
		TestTrue(TEXT("max 0: reference"), Zero.Direction.Equals(Reference, 1e-6));
	}

	// 비정상 보고 — 거부, 기준 방향. 기준이 없으면(컨트롤러 없음) 보고 그대로
	{
		const FAstralReportedAimCheck ZeroReport = CheckReportedAimDirection(FVector::ZeroVector, Yaw30, 45.f);
		TestEqual(TEXT("zero report: rejected"), ZeroReport.Result, E::Rejected);
		TestTrue(TEXT("zero report: reference"), ZeroReport.Direction.Equals(Yaw30, 1e-6));
		TestEqual(TEXT("nan report: rejected"), CheckReportedAimDirection(FVector(NAN, 0.0, 0.0), Reference, 45.f).Result, E::Rejected);

		const FAstralReportedAimCheck NoReference = CheckReportedAimDirection(Yaw70, FVector::ZeroVector, 45.f);
		TestEqual(TEXT("no reference: accepted"), NoReference.Result, E::Accepted);
		TestTrue(TEXT("no reference: reported"), NoReference.Direction.Equals(Yaw70, 1e-6));
	}

	// 보고 조준점 다듬기 — 서버 총구 기준 전방 · 사거리 1.1배
	{
		const FVector Muzzle(0.0, 0.0, 100.0);
		const float Range = 10000.f;
		const FVector Ahead(500.0, 20.0, 110.0);
		TestTrue(TEXT("ahead: unchanged"), ClampReportedAimPoint(Ahead, Reference, Muzzle, Range).Equals(Ahead));
		TestTrue(TEXT("behind muzzle: range end along direction"), ClampReportedAimPoint(FVector(-50.0, 0.0, 100.0), Reference, Muzzle, Range).Equals(Muzzle + Reference * Range, 1e-3));
		TestTrue(TEXT("at muzzle: range end along direction"), ClampReportedAimPoint(Muzzle, Reference, Muzzle, Range).Equals(Muzzle + Reference * Range, 1e-3));
		TestTrue(TEXT("within 1.1x range: unchanged"), ClampReportedAimPoint(Muzzle + Reference * 10500.0, Reference, Muzzle, Range).Equals(Muzzle + Reference * 10500.0));
		TestTrue(TEXT("beyond 1.1x range: pulled to range"), ClampReportedAimPoint(Muzzle + Yaw30 * 20000.0, Reference, Muzzle, Range).Equals(Muzzle + Yaw30 * Range, 1e-3));
	}

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralDodgeDirectionTest, "AstralBreak.Dodge.ResolveDirection", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralDodgeDirectionTest::RunTest(const FString& Parameters)
{
	using namespace AstralDodge;

	FAstralDodgeDirectionInput Base;
	Base.AvatarLocation = FVector(0.f, 0.f, 100.f);
	Base.TargetLocation = FVector(500.f, 0.f, 100.f); // 타겟이 +X 쪽
	Base.AvatarForward = FVector(0.f, 1.f, 0.f);       // 캐릭터는 +Y를 본다
	Base.bBackstepWhenIdle = true;

	// 1. 입력 우선 — 락온이 있어도 입력 방향 (수직 성분 제거)
	{
		FAstralDodgeDirectionInput In = Base;
		In.bHasLockTarget = true;
		In.HorizontalInput = FVector(0.f, -300.f, 50.f);
		TestTrue(TEXT("input wins"), ResolveDirection(In).Equals(FVector(0.f, -1.f, 0.f), KINDA_SMALL_NUMBER));
	}

	// 2. 무입력 + 락온 — 타겟 반대 (캐릭터가 타겟을 안 보고 있어도)
	{
		FAstralDodgeDirectionInput In = Base;
		In.bHasLockTarget = true;
		TestTrue(TEXT("away from target"), ResolveDirection(In).Equals(FVector(-1.f, 0.f, 0.f), KINDA_SMALL_NUMBER));
	}

	// 2'. 수평 겹침 — 기존 규칙(백스텝)으로 폴백
	{
		FAstralDodgeDirectionInput In = Base;
		In.bHasLockTarget = true;
		In.TargetLocation = FVector(0.f, 0.f, 300.f);
		TestTrue(TEXT("overlap -> backstep"), ResolveDirection(In).Equals(FVector(0.f, -1.f, 0.f), KINDA_SMALL_NUMBER));
	}

	// 3. 무입력·무락온 — 백스텝 / 전방
	{
		FAstralDodgeDirectionInput In = Base;
		TestTrue(TEXT("idle backstep"), ResolveDirection(In).Equals(FVector(0.f, -1.f, 0.f), KINDA_SMALL_NUMBER));
		In.bBackstepWhenIdle = false;
		TestTrue(TEXT("idle forward"), ResolveDirection(In).Equals(FVector(0.f, 1.f, 0.f), KINDA_SMALL_NUMBER));
	}

	// 결과는 항상 수평 단위 벡터
	{
		FAstralDodgeDirectionInput In = Base;
		In.AvatarForward = FVector(0.f, 0.f, 1.f); // 수직 전방 — 폴백
		const FVector Dir = ResolveDirection(In);
		TestTrue(TEXT("horizontal unit"), FMath::IsNearlyZero(Dir.Z) && FMath::IsNearlyEqual(Dir.Size(), 1.f, KINDA_SMALL_NUMBER));
	}

	// 페이로드 왕복 — Yaw만
	{
		FAstralDodgeActivationData Source;
		Source.QuantizedYaw = AstralFacing::QuantizeYaw(-135.f);
		FGameplayAbilityTargetData_AstralDodge Payload(Source);

		TArray<uint8> Bytes;
		FMemoryWriter Writer(Bytes);
		bool bSuccess = false;
		Payload.NetSerialize(Writer, nullptr, bSuccess);
		FGameplayAbilityTargetData_AstralDodge Loaded;
		FMemoryReader Reader(Bytes);
		Loaded.NetSerialize(Reader, nullptr, bSuccess);

		TestTrue(TEXT("dodge roundtrip"), Loaded.Data == Source);
		const FVector Dir = Loaded.Data.GetDirection();
		TestTrue(TEXT("decoded horizontal unit"), FMath::IsNearlyZero(Dir.Z) && FMath::IsNearlyEqual(Dir.Size(), 1.f, KINDA_SMALL_NUMBER));
		TestTrue(TEXT("decoded yaw"), FMath::IsNearlyEqual(Dir.Rotation().Yaw, -135.f, 0.01f));

		FAstralDodgeActivationData Out;
		TestTrue(TEXT("extract"), FGameplayAbilityTargetData_AstralDodge::Extract(FGameplayAbilityTargetData_AstralDodge::MakeHandle(Source), Out));
		FAstralFacingProposal Facing;
		TestFalse(TEXT("facing payload rejected"), FGameplayAbilityTargetData_AstralDodge::Extract(FGameplayAbilityTargetData_AstralFacing::MakeHandle(Facing), Out));
	}

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
