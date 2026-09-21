// 락온 6단계 순수 계산 테스트 — 발사 허용각 경계 · 원거리/회피 페이로드 직렬화 · 회피 방향 우선순위.
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
