// PIE 자동 시험 공용 틀 — 단계 큐 · PIE 시작/종료 · 월드 조회 (설계 Docs/Design/m3-enemy-ai.md §7-2 ① 의 틀을 시험 파일들이 나눠 쓴다)
//
// 지연 명령 하나가 한 단계다. 한 단계라도 제한 시간을 넘기면 bAborted 가 서고, 이후 단계는 건너뛴 채 EndPie 만 돈다.

#pragma once

#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Editor.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "PlayInEditorDataTypes.h"
#include "Settings/LevelEditorPlaySettings.h"

namespace AstralPieTest
{
	struct FContextBase
	{
		FAutomationTestBase* Test = nullptr;

		/** 한 단계라도 실패하면 이후 단계를 건너뛰고 PIE 만 정리한다 */
		bool bAborted = false;
		bool bPieRequested = false;
	};

	/**
	 * 실측값 기록 — 시험 결과의 정보 줄 + 로그(`ASTRAL_PIETEST` 표지).
	 * 자동 시험 러너의 결과에는 오류 · 경고만 실리므로, 값은 에디터를 `-stdout -FullStdOutLogOutput` 로 띄워 표준 출력에서 읽는다
	 */
	inline void Note(FAutomationTestBase& Test, const FString& Message)
	{
		Test.AddInfo(Message);
		UE_LOG(LogTemp, Display, TEXT("ASTRAL_PIETEST %s"), *Message);
	}

	// ─── 월드 조회 — 이동 때마다 월드가 바뀌므로 저장하지 않고 매번 다시 찾는다 ───

	inline TArray<UWorld*> GetPieWorlds()
	{
		TArray<UWorld*> Out;
		for (const FWorldContext& WorldContext : GEngine->GetWorldContexts())
		{
			if (WorldContext.WorldType == EWorldType::PIE && WorldContext.World())
			{
				Out.Add(WorldContext.World());
			}
		}
		return Out;
	}

	/** 리슨 · Dedicated 서버 월드. Standalone 은 서버로 치지 않는다 */
	inline UWorld* FindServerWorld()
	{
		for (UWorld* World : GetPieWorlds())
		{
			const ENetMode NetMode = World->GetNetMode();
			if (NetMode == NM_ListenServer || NetMode == NM_DedicatedServer)
			{
				return World;
			}
		}
		return nullptr;
	}

	/** 권위 월드 — 서버 또는 Standalone */
	inline UWorld* FindAuthorityWorld()
	{
		for (UWorld* World : GetPieWorlds())
		{
			if (World->GetNetMode() != NM_Client)
			{
				return World;
			}
		}
		return nullptr;
	}

	inline FString MapOf(const UWorld* World)
	{
		return World ? UWorld::RemovePIEPrefix(World->GetMapName()) : FString();
	}

	// ─── 단계 큐 ───

	inline void Step(TFunction<bool()> Fn)
	{
		FAutomationTestFramework::Get().EnqueueLatentCommand(MakeShared<FFunctionLatentCommand>(MoveTemp(Fn)));
	}

	/** 한 번 실행. 앞 단계가 실패했으면 건너뛴다 */
	inline void Do(const TSharedRef<FContextBase>& Ctx, TFunction<void()> Fn)
	{
		Step([Ctx, Fn = MoveTemp(Fn)]() -> bool
		{
			if (!Ctx->bAborted)
			{
				Fn();
			}
			return true;
		});
	}

	/**
	 * 조건이 참이 될 때까지. 조건을 먼저 보고 시간을 본다 — 맵 로드 프레임이 길어도 도착했으면 통과.
	 * Describe 는 실패 문장에 붙일 현재 상태(선택)
	 */
	inline void WaitUntil(const TSharedRef<FContextBase>& Ctx, const TCHAR* What, double TimeoutSeconds, TFunction<bool()> Condition, TFunction<FString()> Describe = nullptr)
	{
		TSharedRef<double> StartTime = MakeShared<double>(-1.0);
		Step([Ctx, What = FString(What), TimeoutSeconds, StartTime, Condition = MoveTemp(Condition), Describe = MoveTemp(Describe)]() -> bool
		{
			if (Ctx->bAborted)
			{
				return true;
			}
			if (*StartTime < 0.0)
			{
				*StartTime = FPlatformTime::Seconds();
			}
			if (Condition())
			{
				return true;
			}
			const bool bPieGone = Ctx->bPieRequested && !GEditor->PlayWorld && !GEditor->IsPlaySessionInProgress() && (FPlatformTime::Seconds() - *StartTime > 5.0);
			if (bPieGone || FPlatformTime::Seconds() - *StartTime > TimeoutSeconds)
			{
				Ctx->Test->AddError(FString::Printf(TEXT("%s: %s%s"),
					bPieGone ? TEXT("PIE ended while waiting") : TEXT("timed out waiting"), *What,
					Describe ? *FString::Printf(TEXT(" (%s)"), *Describe()) : TEXT("")));
				Ctx->bAborted = true;
				return true;
			}
			return false;
		});
	}

	/** 실제 시간으로 기다린다 — RPC 가 닿을 시간, '안 바뀜' 확인 전 여유 */
	inline void Hold(const TSharedRef<FContextBase>& Ctx, double Seconds)
	{
		TSharedRef<double> StartTime = MakeShared<double>(-1.0);
		Step([Ctx, Seconds, StartTime]() -> bool
		{
			if (Ctx->bAborted)
			{
				return true;
			}
			if (*StartTime < 0.0)
			{
				*StartTime = FPlatformTime::Seconds();
			}
			return FPlatformTime::Seconds() - *StartTime >= Seconds;
		});
	}

	/** 사용자 플레이 설정에 끌려가지 않게 맵 · 넷 모드 · 인원 · 프로세스 구성을 명시해 PIE 를 요청한다. 도착 판정은 호출자가 WaitUntil 로 한다 */
	inline void RequestPie(const TSharedRef<FContextBase>& Ctx, const TCHAR* MapPath, EPlayNetMode NetMode, int32 NumPlayers)
	{
		Step([Ctx, MapPath = FString(MapPath), NetMode, NumPlayers]() -> bool
		{
			if (!GEditor || GEditor->PlayWorld || GEditor->IsPlaySessionInProgress())
			{
				Ctx->Test->AddError(TEXT("PIE is already active — end it before running this test"));
				Ctx->bAborted = true;
				return true;
			}

			FRequestPlaySessionParams Params;
			Params.GlobalMapOverride = MapPath;
			ULevelEditorPlaySettings* Settings = NewObject<ULevelEditorPlaySettings>(GetTransientPackage()); // RequestPlaySession 이 복제해 쥔다
			Settings->SetPlayNetMode(NetMode);
			Settings->SetPlayNumberOfClients(NumPlayers);
			Settings->SetRunUnderOneProcess(true);
			Params.EditorPlaySettings = Settings;
			GEditor->RequestPlaySession(Params);
			Ctx->bPieRequested = true;
			return true;
		});
	}

	/** 실패했어도 반드시 PIE 를 내린다 */
	inline void EndPie(const TSharedRef<FContextBase>& Ctx)
	{
		Step([Ctx]() -> bool
		{
			if (Ctx->bPieRequested && (GEditor->PlayWorld || GEditor->IsPlaySessionInProgress()))
			{
				GEditor->RequestEndPlayMap();
			}
			return true;
		});
		Step([]() -> bool { return GEditor->PlayWorld == nullptr && !GEditor->IsPlaySessionInProgress(); });
	}
}

#endif // WITH_DEV_AUTOMATION_TESTS
