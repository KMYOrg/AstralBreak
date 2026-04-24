#pragma once

#include "CoreMinimal.h"
#include "Engine/LocalPlayer.h"
#include "AstralLocalPlayer.generated.h"

/**
 * UAstralLocalPlayer
 * 클라이언트 측 상태의 보관소 역할
 * 현재 책임:
 *   - PlayerController 교체 시점 훅 (세 진입점 통합)
 * 확장 예정:
 *   - 설정 시스템 브릿지 (Local / Shared)
 *   - 백엔드 인증 토큰 / 던전 예약 정보 캐시 (데디 + DB 구조 도입 시)
 */
UCLASS()
class ASTRALBREAK_API UAstralLocalPlayer : public ULocalPlayer
{
	GENERATED_BODY()

public:
	UAstralLocalPlayer();

	//~ UObject interface
	virtual void PostInitProperties() override;
	//~ End UObject interface

	//~ UPlayer interface
	virtual void SwitchController(APlayerController* PC) override;
	//~ End UPlayer interface

	//~ ULocalPlayer interface
	virtual bool SpawnPlayActor(const FString& URL, FString& OutError, UWorld* InWorld) override;
	virtual void InitOnlineSession() override;
	//~ End ULocalPlayer interface
	
	// =========================================================
	// TODO(Settings): 설정 시스템 도입 시 활성화
	// =========================================================
	//
	// /** 머신 단위 설정 (그래픽, 오디오 장치 등) - config 기반, 항상 유효 */
	// UFUNCTION()
	// UAstralSettingsLocal* GetLocalSettings() const;
	//
	// /** 계정 단위 설정 (감도, 자막 등) - SaveGame 기반, 로그인 후 유효 */
	// UFUNCTION()
	// UAstralSettingsShared* GetSharedSettings() const;
	//
	// /** Shared 설정 비동기 로드 시작 */
	// void LoadSharedSettingsFromDisk(bool bForceLoad = false);
	
protected:

	void OnPlayerControllerChanged(APlayerController* NewController);
	
	// =========================================================
	// TODO(Settings): 설정 로드 콜백 및 오디오 장치 스왑 핸들러
	// =========================================================
	//
	// void OnSharedSettingsLoaded(UAstralSettingsShared* LoadedOrCreatedSettings);
	// void OnAudioOutputDeviceChanged(const FString& InAudioOutputDeviceId);
	//
	// UFUNCTION()
	// void OnCompletedAudioDeviceSwap(const FSwapAudioOutputResult& SwapResult);
	
private:
	/**
	 * 이전에 훅을 바인딩했던 PC의 약참조.
	 * PC가 이미 파괴된 뒤에도 델리게이트 해제 대상 식별에 필요하므로 Weak으로 보관
	 * 현재는 사용처가 없지만 Settings 훅 추가 시 즉시 활용
	 */
	UPROPERTY(Transient)
	TWeakObjectPtr<APlayerController> LastBoundPC;
};
