#pragma once

#include "CoreMinimal.h"
#include "AstralEquipmentTypes.generated.h"

/**
 * GameState 클래스는 맵(GameMode)마다 다르고 클라에도 같은 클래스로 스폰되므로 복제가 필요 없다.
 * ⚠️ 이 전제는 CDO 값일 때만 성립 — 런타임에 인스턴스 값을 바꾸면 클라와 어긋난다.
 */
UENUM(BlueprintType)
enum class EAstralEquipmentPolicy : uint8
{
	/** 장착 안 함 — 관전 등 */
	None,
	/** 액터 스폰만(홀스터 표시), 어빌리티·스탯 부여 없음 — 로비 */
	VisualOnly,
	/** 전부 — 전투 */
	Full
};

/** 장비 액터 부착 상태 — 서버가 전환, AttachmentReplication/bHidden으로 클라 전파 */
UENUM()
enum class EAstralEquipmentAttachState : uint8
{
	/** HolsterSocket 부착 (등/허리) — 소켓 미지정 계열은 숨김 (기존 동작 보존) */
	Holstered,
	/** AttachSocket 부착 (손) */
	Held
};
