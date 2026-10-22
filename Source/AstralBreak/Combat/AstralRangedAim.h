#pragma once

#include "CoreMinimal.h"

class AActor;
class AController;

/**
 * 원거리 조준점 — 화면 중앙(카메라) 레이가 맞는 지점. 발사(UAstralGA_Hero_BasicAttack_Ranged — 원격 플레이어는 소유 클라가 발사 순간 계산해 보낸 값)와
 * 최종 조준 보정 애니(UAstralAnimInstance), 관찰자용 복제(AAstralCharacter_Hero::PreReplication)가 같은 함수를 쓴다: 투사체가 날아가는 점 = 총열이 향하는 점 (한쪽만 바뀌어 다시 어긋나는 일이 없게)
 */
namespace AstralRangedAim
{
	/** 기본 트레이스 사거리 — GA AimTraceRange 의 기본값 */
	inline constexpr float DefaultTraceRange = 10000.f;

	struct FCameraAimPoint
	{
		/** 트레이스 시작 = 카메라 레이 위 총구 투영점 */
		FVector TraceStart = FVector::ZeroVector;

		/** 카메라 방향 (단위) */
		FVector Direction = FVector::ForwardVector;

		/** 조준점 — 맞은 곳, 없으면 사거리 끝. 총구 뒤·옆이면(극근접 지형 등) 총구에서 카메라 방향 사거리 끝 */
		FVector TargetPoint = FVector::ZeroVector;
	};

	/**
	 * 컨트롤러의 카메라 POV 로 조준점을 구한다 — 원격 플레이어의 서버 쪽 POV 는 클라가 ServerUpdateCamera 로 보고하는 엔진 표준 경로.
	 * 트레이스는 Visibility, Avatar·IgnoreActor 제외. 시작을 카메라 레이 위 총구 투영점으로 당겨 카메라~캐릭터 사이(등 뒤) 오브젝트 오폭을 막는다.
	 * Controller·Avatar·월드가 없으면 false
	 */
	ASTRALBREAK_API bool ComputeCameraAimPoint(const AController* Controller, const AActor* Avatar, const AActor* IgnoreActor, const FVector& MuzzleLocation, float TraceRange, FCameraAimPoint& Out);

	/**
	 * 위와 같은 규칙(총구 투영 시작 · Visibility · 전방 보장)을 지정한 뷰 위치·방향으로 — 서버가 원격 플레이어의 보고 방향을 허용각으로 다듬었을 때 그 방향으로 다시 잰다.
	 * Avatar·월드가 없거나 방향이 0 이면 false
	 */
	ASTRALBREAK_API bool ComputeAimPointAlongView(const FVector& ViewLocation, const FVector& ViewDirection, const AActor* Avatar, const AActor* IgnoreActor, const FVector& MuzzleLocation, float TraceRange, FCameraAimPoint& Out);
}
