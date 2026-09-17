// 락온 5단계 순수 계산 테스트 — Yaw 양자화 왕복 · 페이로드 직렬화 왕복 · 수신 분류/보관함 · 서버 검증 경계.
// 월드 의존이 없어 Session Frontend / -ExecCmds="Automation RunTests AstralBreak.Facing"로 돈다.
// 네트워크·몽타주·접촉은 PIE 수동 검증 (stage-5-network.md)

#include "Misc/AutomationTest.h"
#include "Combat/AstralFacingTypes.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace
{
	FAstralFacingProposal MakeLockOn(uint8 Stage, uint16 Yaw)
	{
		FAstralFacingProposal P;
		P.Source = EAstralFacingSource::LockOn;
		P.StageIndex = Stage;
		P.QuantizedDesiredYaw = Yaw;
		return P;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralFacingQuantizeTest, "AstralBreak.Facing.QuantizeYaw", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralFacingQuantizeTest::RunTest(const FString& Parameters)
{
	using namespace AstralFacing;
	constexpr float Resolution = 360.f / 65536.f;

	// 왕복 오차 ≤ 해상도/2
	for (const float Yaw : { 0.f, 45.f, -45.f, 179.99f, -179.99f, 90.f, -90.f, 123.456f, -0.001f })
	{
		const float Back = DequantizeYaw(QuantizeYaw(Yaw));
		TestTrue(*FString::Printf(TEXT("roundtrip %.3f -> %.3f"), Yaw, Back), FMath::Abs(FMath::FindDeltaAngleDegrees(Yaw, Back)) <= Resolution * 0.5f + KINDA_SMALL_NUMBER);
	}

	// 정규화 — 360 밖의 입력도 같은 값
	TestEqual(TEXT("370 == 10"), QuantizeYaw(370.f), QuantizeYaw(10.f));
	TestEqual(TEXT("-350 == 10"), QuantizeYaw(-350.f), QuantizeYaw(10.f));

	// 180 경계 — 180과 -180은 같은 방향
	TestEqual(TEXT("180 == -180"), QuantizeYaw(180.f), QuantizeYaw(-180.f));

	// 결과는 (-180, 180] 안
	for (uint32 Q = 0; Q < 65536; Q += 4097)
	{
		const float Y = DequantizeYaw(static_cast<uint16>(Q));
		TestTrue(*FString::Printf(TEXT("dequantize %u in range"), Q), Y > -180.f - KINDA_SMALL_NUMBER && Y <= 180.f + KINDA_SMALL_NUMBER);
	}

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralFacingSerializeTest, "AstralBreak.Facing.Serialize", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralFacingSerializeTest::RunTest(const FString& Parameters)
{
	// 액터 없는 페이로드의 직렬화 왕복 (액터는 UPackageMap 경로라 PIE 몫)
	{
		FGameplayAbilityTargetData_AstralFacing Source(MakeLockOn(2, 40000));

		TArray<uint8> Bytes;
		FMemoryWriter Writer(Bytes);
		bool bSuccess = false;
		Source.NetSerialize(Writer, nullptr, bSuccess);
		TestTrue(TEXT("write success"), bSuccess);

		FGameplayAbilityTargetData_AstralFacing Loaded;
		FMemoryReader Reader(Bytes);
		Loaded.NetSerialize(Reader, nullptr, bSuccess);
		TestTrue(TEXT("read success"), bSuccess);

		TestTrue(TEXT("roundtrip equal"), Loaded.Proposal == Source.Proposal);
		TestEqual(TEXT("stage"), static_cast<int32>(Loaded.Proposal.StageIndex), 2);
		TestEqual(TEXT("yaw"), static_cast<int32>(Loaded.Proposal.QuantizedDesiredYaw), 40000);
	}

	// None은 정규화된다 — Yaw·PointId를 실어 보내도 비워진다
	{
		FAstralFacingProposal Dirty;
		Dirty.Source = EAstralFacingSource::None;
		Dirty.StageIndex = 1;
		Dirty.QuantizedDesiredYaw = 777;
		FGameplayAbilityTargetData_AstralFacing Source(Dirty);

		TArray<uint8> Bytes;
		FMemoryWriter Writer(Bytes);
		bool bSuccess = false;
		Source.NetSerialize(Writer, nullptr, bSuccess);

		FGameplayAbilityTargetData_AstralFacing Loaded;
		FMemoryReader Reader(Bytes);
		Loaded.NetSerialize(Reader, nullptr, bSuccess);

		TestTrue(TEXT("none normalized"), Loaded.Proposal.IsNone() && Loaded.Proposal.QuantizedDesiredYaw == 0 && Loaded.Proposal.TargetPointId.IsNone());
		TestEqual(TEXT("none keeps stage"), static_cast<int32>(Loaded.Proposal.StageIndex), 1);
	}

	// ExtractProposal — 구조 검증
	{
		FAstralFacingProposal Out;
		const int32 NumStages = 3;

		TestTrue(TEXT("valid handle"), FGameplayAbilityTargetData_AstralFacing::ExtractProposal(FGameplayAbilityTargetData_AstralFacing::MakeHandle(MakeLockOn(1, 100)), NumStages, Out));
		TestEqual(TEXT("extracted stage"), static_cast<int32>(Out.StageIndex), 1);

		TestFalse(TEXT("empty handle"), FGameplayAbilityTargetData_AstralFacing::ExtractProposal(FGameplayAbilityTargetDataHandle(), NumStages, Out));

		FGameplayAbilityTargetDataHandle Two = FGameplayAbilityTargetData_AstralFacing::MakeHandle(MakeLockOn(0, 1));
		Two.Append(FGameplayAbilityTargetData_AstralFacing::MakeHandle(MakeLockOn(0, 2)));
		TestFalse(TEXT("two payloads"), FGameplayAbilityTargetData_AstralFacing::ExtractProposal(Two, NumStages, Out));

		TestFalse(TEXT("stage out of range"), FGameplayAbilityTargetData_AstralFacing::ExtractProposal(FGameplayAbilityTargetData_AstralFacing::MakeHandle(MakeLockOn(3, 1)), NumStages, Out));

		FAstralFacingProposal WithPoint = MakeLockOn(0, 1);
		WithPoint.TargetPointId = FName(TEXT("Head"));
		TestFalse(TEXT("point id not allowed until M5"), FGameplayAbilityTargetData_AstralFacing::ExtractProposal(FGameplayAbilityTargetData_AstralFacing::MakeHandle(WithPoint), NumStages, Out));

		// 다른 ScriptStruct — 엔진 기본 타입은 거부
		FGameplayAbilityTargetDataHandle Foreign;
		Foreign.Add(new FGameplayAbilityTargetData_LocationInfo());
		TestFalse(TEXT("foreign struct"), FGameplayAbilityTargetData_AstralFacing::ExtractProposal(Foreign, NumStages, Out));
	}

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralFacingInboxTest, "AstralBreak.Facing.Inbox", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralFacingInboxTest::RunTest(const FString& Parameters)
{
	using R = EAstralFacingReceiveResult;

	// 정상 순서 — 0 도착 → 0 시작·소비 → 1 도착 → 1 시작·소비
	{
		FAstralFacingStageInbox Inbox;
		Inbox.Reset(3);
		TestEqual(TEXT("stage0 stored current"), Inbox.Receive(MakeLockOn(0, 10)), R::StoredCurrent);
		TestTrue(TEXT("begin 0"), Inbox.BeginStage(0));
		TOptional<FAstralFacingProposal> P = Inbox.TakeCurrent();
		TestTrue(TEXT("take 0"), P.IsSet() && P->QuantizedDesiredYaw == 10);

		TestEqual(TEXT("stage1 stored next"), Inbox.Receive(MakeLockOn(1, 20)), R::StoredNext);
		TestTrue(TEXT("begin 1 promotes"), Inbox.BeginStage(1));
		P = Inbox.TakeCurrent();
		TestTrue(TEXT("take 1"), P.IsSet() && P->QuantizedDesiredYaw == 20);
	}

	// 조기 도착 — 현재(0) 미확정인데 1이 먼저 와도 pending에 보관되고, 0 시작을 앞당기지 않는다
	{
		FAstralFacingStageInbox Inbox;
		Inbox.Reset(3);
		TestEqual(TEXT("early stage1"), Inbox.Receive(MakeLockOn(1, 20)), R::StoredNext);
		TestEqual(TEXT("current stage still 0"), Inbox.GetCurrentStage(), 0);
		TestTrue(TEXT("begin 0"), Inbox.BeginStage(0));
		TestFalse(TEXT("stage0 missing"), Inbox.TakeCurrent().IsSet());
		TestTrue(TEXT("begin 1"), Inbox.BeginStage(1));
		TestTrue(TEXT("stage1 consumed from pending"), Inbox.TakeCurrent().IsSet());
	}

	// 지각 — 확정 후 도착은 폐기, 과거 단계는 폐기
	{
		FAstralFacingStageInbox Inbox;
		Inbox.Reset(3);
		Inbox.BeginStage(0);
		Inbox.TakeCurrent();
		TestEqual(TEXT("late stage0 after resolve"), Inbox.Receive(MakeLockOn(0, 10)), R::DiscardedResolved);
		Inbox.BeginStage(1);
		TestEqual(TEXT("past stage0"), Inbox.Receive(MakeLockOn(0, 10)), R::DiscardedPast);
	}

	// 중복·상충 — 첫 수용값 유지
	{
		FAstralFacingStageInbox Inbox;
		Inbox.Reset(3);
		TestEqual(TEXT("first"), Inbox.Receive(MakeLockOn(0, 10)), R::StoredCurrent);
		TestEqual(TEXT("same again"), Inbox.Receive(MakeLockOn(0, 10)), R::DuplicateIgnored);
		TestEqual(TEXT("conflict"), Inbox.Receive(MakeLockOn(0, 99)), R::ConflictIgnored);
		Inbox.BeginStage(0);
		TOptional<FAstralFacingProposal> P = Inbox.TakeCurrent();
		TestTrue(TEXT("first value kept"), P.IsSet() && P->QuantizedDesiredYaw == 10);
	}

	// 너무 먼 미래 · 범위 밖
	{
		FAstralFacingStageInbox Inbox;
		Inbox.Reset(3);
		TestEqual(TEXT("stage2 too far from 0"), Inbox.Receive(MakeLockOn(2, 1)), R::DiscardedTooFar);
		TestEqual(TEXT("stage3 out of range"), Inbox.Receive(MakeLockOn(3, 1)), R::DiscardedOutOfRange);
	}

	// 단계 불일치 — 건너뛰면 false + 슬롯 초기화 (감추지 않는다)
	{
		FAstralFacingStageInbox Inbox;
		Inbox.Reset(4);
		Inbox.Receive(MakeLockOn(0, 10));
		Inbox.Receive(MakeLockOn(1, 20));
		TestFalse(TEXT("jump 0 -> 2 mismatch"), Inbox.BeginStage(2));
		TestEqual(TEXT("current is 2"), Inbox.GetCurrentStage(), 2);
		TestFalse(TEXT("slots cleared"), Inbox.TakeCurrent().IsSet());
	}

	// None도 값이다 — 명시적 무보정은 Missing과 구별된다
	{
		FAstralFacingStageInbox Inbox;
		Inbox.Reset(1);
		TestEqual(TEXT("explicit none stored"), Inbox.Receive(FAstralFacingProposal::MakeNone(0)), R::StoredCurrent);
		Inbox.BeginStage(0);
		TOptional<FAstralFacingProposal> P = Inbox.TakeCurrent();
		TestTrue(TEXT("none present"), P.IsSet() && P->IsNone());
	}

	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralFacingValidateTest, "AstralBreak.Facing.ValidateBearing", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FAstralFacingValidateTest::RunTest(const FString& Parameters)
{
	using namespace AstralFacing;
	using E = EAstralFacingRejectReason;

	// 정상
	TestEqual(TEXT("in range, small error"), ValidateBearing(500.f, 30.f, 40.f), E::None);

	// 거리 경계
	TestEqual(TEXT("at range"), ValidateBearing(ValidateRange, 0.f, 0.f), E::None);
	TestEqual(TEXT("beyond range"), ValidateBearing(ValidateRange + 1.f, 0.f, 0.f), E::OutOfRange);

	// 방위 경계 — 최단각. ±180 래핑
	TestEqual(TEXT("error at limit"), ValidateBearing(500.f, 0.f, MaxTargetBearingError), E::None);
	TestEqual(TEXT("error beyond limit"), ValidateBearing(500.f, 0.f, MaxTargetBearingError + 1.f), E::BearingMismatch);
	TestEqual(TEXT("wrap: 170 vs -170 = 20"), ValidateBearing(500.f, 170.f, -170.f), E::None);
	TestEqual(TEXT("wrap: 100 vs -100 = 160"), ValidateBearing(500.f, 100.f, -100.f), E::BearingMismatch);

	// 근거리 완화 — 접촉 거리에서는 각도 검사 생략
	TestEqual(TEXT("close: any bearing ok"), ValidateBearing(BearingCheckMinDistance - 1.f, 0.f, 180.f), E::None);
	TestEqual(TEXT("at min distance: bearing checked"), ValidateBearing(BearingCheckMinDistance, 0.f, 180.f), E::BearingMismatch);

	// 거리 거부가 방위보다 먼저
	TestEqual(TEXT("far and wrong -> OutOfRange"), ValidateBearing(ValidateRange + 100.f, 0.f, 180.f), E::OutOfRange);

	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
