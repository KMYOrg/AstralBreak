#include "AstralLocalPlayer.h"

#include "GameFramework/PlayerController.h"
#include "Engine/World.h"

// TODO(Settings): 설정 시스템 도입 시 활성화
// #include "AudioMixerBlueprintLibrary.h"
// #include "Settings/AstralSettingsLocal.h"
// #include "Settings/AstralSettingsShared.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(AstralLocalPlayer)

UAstralLocalPlayer::UAstralLocalPlayer()
{
}

void UAstralLocalPlayer::PostInitProperties()
{
    Super::PostInitProperties();

    // TODO(Settings): LocalSettings의 오디오 출력 장치 변경 델리게이트 바인딩
    //
    // if (UAstralSettingsLocal* LocalSettings = GetLocalSettings())
    // {
    //     LocalSettings->OnAudioOutputDeviceChanged.AddUObject(
    //         this, &UAstralLocalPlayer::OnAudioOutputDeviceChanged);
    // }
}

void UAstralLocalPlayer::SwitchController(APlayerController* PC)
{
    Super::SwitchController(PC);

    OnPlayerControllerChanged(PlayerController);
}

bool UAstralLocalPlayer::SpawnPlayActor(const FString& URL, FString& OutError, UWorld* InWorld)
{
    const bool bResult = Super::SpawnPlayActor(URL, OutError, InWorld);

    OnPlayerControllerChanged(PlayerController);

    return bResult;
}

void UAstralLocalPlayer::InitOnlineSession()
{
    OnPlayerControllerChanged(PlayerController);

    Super::InitOnlineSession();
}

void UAstralLocalPlayer::OnPlayerControllerChanged(APlayerController* NewController)
{
    // 현재는 PC 캐싱만 수행
    // 추후 설정 컨텍스트 갱신 등이 여기에 추가

    LastBoundPC = NewController;
}

// =============================================================
// TODO(Settings): 설정 시스템 구현
// =============================================================
//
// UAstralSettingsLocal* UAstralLocalPlayer::GetLocalSettings() const
// {
//     return UAstralSettingsLocal::Get();
// }
//
// UAstralSettingsShared* UAstralLocalPlayer::GetSharedSettings() const
// {
//     if (!SharedSettings)
//     {
//         const bool bCanLoadBeforeLogin = PLATFORM_DESKTOP;
//         if (bCanLoadBeforeLogin)
//         {
//             SharedSettings = UAstralSettingsShared::LoadOrCreateSettings(this);
//         }
//         else
//         {
//             SharedSettings = UAstralSettingsShared::CreateTemporarySettings(this);
//         }
//     }
//     return SharedSettings;
// }
//
// void UAstralLocalPlayer::LoadSharedSettingsFromDisk(bool bForceLoad)
// {
//     FUniqueNetIdRepl CurrentNetId = GetCachedUniqueNetId();
//     if (!bForceLoad && SharedSettings && CurrentNetId == NetIdForSharedSettings)
//     {
//         return;
//     }
//
//     ensure(UAstralSettingsShared::AsyncLoadOrCreateSettings(
//         this,
//         UAstralSettingsShared::FOnSettingsLoadedEvent::CreateUObject(
//             this, &UAstralLocalPlayer::OnSharedSettingsLoaded)));
// }
//
// void UAstralLocalPlayer::OnSharedSettingsLoaded(UAstralSettingsShared* LoadedOrCreatedSettings)
// {
//     if (ensure(LoadedOrCreatedSettings))
//     {
//         SharedSettings = LoadedOrCreatedSettings;
//         NetIdForSharedSettings = GetCachedUniqueNetId();
//     }
// }
//
// void UAstralLocalPlayer::OnAudioOutputDeviceChanged(const FString& InAudioOutputDeviceId)
// {
//     FOnCompletedDeviceSwap DevicesSwappedCallback;
//     DevicesSwappedCallback.BindUFunction(this, FName("OnCompletedAudioDeviceSwap"));
//     UAudioMixerBlueprintLibrary::SwapAudioOutputDevice(
//         GetWorld(), InAudioOutputDeviceId, DevicesSwappedCallback);
// }
//
// void UAstralLocalPlayer::OnCompletedAudioDeviceSwap(const FSwapAudioOutputResult& SwapResult)
// {
//     if (SwapResult.Result == ESwapAudioOutputDeviceResultState::Failure)
//     {
//         // 실패 처리 - 로그/UI 토스트 등
//     }
// }