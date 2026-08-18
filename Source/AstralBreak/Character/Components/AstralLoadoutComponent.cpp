#include "AstralLoadoutComponent.h"

#include "AbilitySystemGlobals.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AstralLogChannels.h"
#include "Character/AstralCharacterDefinition.h"
#include "Character/AstralPawnData.h"
#include "Character/Components/AstralPawnExtensionComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Equipment/AstralEquipmentManagerComponent.h"
#include "GameFramework/Character.h"
#include "Player/AstralPlayerState.h"
#include "System/AstralAssetManager.h"
#include "System/AstralPartySubsystem.h"

UAstralLoadoutComponent::UAstralLoadoutComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	PrimaryComponentTick.bCanEverTick = false;
}

AAstralPlayerState* UAstralLoadoutComponent::GetAstralPlayerState() const
{
	const APawn* OwnerPawn = GetPawn<APawn>();
	return OwnerPawn ? OwnerPawn->GetPlayerState<AAstralPlayerState>() : nullptr;
}

void UAstralLoadoutComponent::HandleAbilitySystemInitialized()
{
	// PS.OnLoadoutChanged 구독 (push — 이후 변경 통지) + 초기 1회 적용 (pull — 구독 전에 지나간 변경 커버).
	// PS 교체(travel/재빙의) 시 재구독
	AAstralPlayerState* AstralPS = GetAstralPlayerState();
	if (BoundPlayerState.Get() != AstralPS)
	{
		UnbindLoadoutChanged();
		BoundPlayerState = AstralPS;

		if (AstralPS)
		{
			LoadoutChangedHandle = AstralPS->OnLoadoutChanged.AddUObject(this, &ThisClass::HandleLoadoutChanged);
		}
	}

	ApplyLoadout(/*bReapplyEquipment=*/false);
}

void UAstralLoadoutComponent::HandleAbilitySystemUninitialized()
{
	UnbindLoadoutChanged();
}

void UAstralLoadoutComponent::ApplyLoadout(bool bReapplyEquipment)
{
	// 순서 계약 — 외형이 항상 먼저 (장비 액터는 GetMesh() 소켓 부착이라 메시 교체 후 장착해야 한다)
	RefreshAppearanceFromLoadout();

	if (GetOwner() && GetOwner()->HasAuthority())
	{
		RestoreEquipmentFromLoadout(bReapplyEquipment);
	}
}

void UAstralLoadoutComponent::HandleLoadoutChanged()
{
	ApplyLoadout(/*bReapplyEquipment=*/true);
}

void UAstralLoadoutComponent::UnbindLoadoutChanged()
{
	if (AAstralPlayerState* BoundPS = BoundPlayerState.Get(); BoundPS && LoadoutChangedHandle.IsValid())
	{
		BoundPS->OnLoadoutChanged.Remove(LoadoutChangedHandle);
	}
	LoadoutChangedHandle.Reset();
	BoundPlayerState.Reset();
}

void UAstralLoadoutComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	// 안전망 — 폰의 OnAbilitySystemUninitialized 경로가 먼저 해제했으면 no-op (멱등)
	UnbindLoadoutChanged();

	Super::EndPlay(EndPlayReason);
}

void UAstralLoadoutComponent::RefreshAppearanceFromLoadout()
{
	const AAstralPlayerState* AstralPS = GetAstralPlayerState();
	if (!AstralPS || !AstralPS->GetLoadout().CharacterId.IsValid())
	{
		return;
	}

	const FSoftObjectPath DefinitionPath = UAstralAssetManager::Get().GetPrimaryAssetPath(AstralPS->GetLoadout().CharacterId);
	const UAstralCharacterDefinition* CharacterDef = Cast<UAstralCharacterDefinition>(DefinitionPath.TryLoad());
	if (!CharacterDef)
	{
		UE_LOG(LogAstral, Warning, TEXT("RefreshAppearance: CharacterDefinition 해석 실패 %s"), *AstralPS->GetLoadout().CharacterId.ToString());
		return;
	}

	const ACharacter* OwnerCharacter = Cast<ACharacter>(GetOwner());
	USkeletalMeshComponent* MeshComp = OwnerCharacter ? OwnerCharacter->GetMesh() : nullptr;
	if (!MeshComp || CharacterDef->Mesh.IsNull())
	{
		return;
	}

	// 이미 같은 메시면 스킵 (초기화·OnLoadoutChanged 등 여러 지점에서 호출된다)
	USkeletalMesh* TargetMesh = CharacterDef->Mesh.LoadSynchronous();
	if (TargetMesh && MeshComp->GetSkeletalMeshAsset() != TargetMesh)
	{
		MeshComp->SetSkeletalMesh(TargetMesh);
		if (CharacterDef->AnimInstanceClass)
		{
			MeshComp->SetAnimInstanceClass(CharacterDef->AnimInstanceClass);
		}
	}
}

void UAstralLoadoutComponent::RestoreEquipmentFromLoadout(bool bReapply)
{
	AActor* Owner = GetOwner();
	UAstralEquipmentManagerComponent* EquipmentManager = Owner ? Owner->FindComponentByClass<UAstralEquipmentManagerComponent>() : nullptr;
	if (!Owner || !Owner->HasAuthority() || !EquipmentManager)
	{
		return;
	}

	// ASC 준비 전이면 장착 금지 — 부여 없는 반쪽 장착이 생기고, 그게 HasAnyEquipment 가드를 오염시켜
	// 이후 정상 초기화 경로까지 막는다 (seamless 도착 직후 로드아웃 재발신이 InitState 완료보다 빠른 케이스).
	// 초기화 완료 시 이 함수가 다시 불린다
	if (!UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Owner))
	{
		return;
	}

	// None(관전 등)이면 3단 해석 비용 자체를 아낀다. VisualOnly(로비)는 통과 — 홀스터 표시용 장착
	// (부여 차단은 AddEntry의 정책 게이트 = 로비 전투 불가의 실차단 지점)
	if (EquipmentManager->GetEquipmentPolicy() == EAstralEquipmentPolicy::None)
	{
		return;
	}

	const UAstralPawnExtensionComponent* PawnExt = UAstralPawnExtensionComponent::FindPawnExtensionComponent(Owner);
	const UAstralPawnData* PawnData = PawnExt ? PawnExt->GetPawnData<UAstralPawnData>() : nullptr;
	if (!PawnData)
	{
		return;
	}

	if (!bReapply && EquipmentManager->HasAnyEquipment())
	{
		return;
	}

	// 3단 소스 해석 — PlayerState 우선. 캐시를 앞에 두면 "PS 갱신 → 재적용 → 아직 안 갱신된 캐시 조회"로
	// 레이드 중 로드아웃 변경이 이전 값으로 되돌아간다 (호출 순서 의존 버그). 캐시의 존재 이유는
	// travel 직후 PS.Loadout이 빈 창을 메우는 폴백이므로 2단이 맞다.
	const TArray<FPrimaryAssetId>* EquipmentIds = nullptr;
	LastLoadoutSource = EAstralLoadoutSource::None;

	const AAstralPlayerState* AstralPS = GetAstralPlayerState();
	if (AstralPS)
	{
		if (AstralPS->GetLoadout().Equipment.Num() > 0)
		{
			EquipmentIds = &AstralPS->GetLoadout().Equipment;
			LastLoadoutSource = EAstralLoadoutSource::PlayerState;
		}
		if (!EquipmentIds)
		{
			const UGameInstance* GameInstance = GetWorld() ? GetWorld()->GetGameInstance() : nullptr;
			if (const UAstralPartySubsystem* Party = GameInstance ? GameInstance->GetSubsystem<UAstralPartySubsystem>() : nullptr)
			{
				if (const FAstralPlayerLoadout* Cached = Party->FindLoadout(AstralPS->GetUniqueId()); Cached && Cached->Equipment.Num() > 0)
				{
					EquipmentIds = &Cached->Equipment;
					LastLoadoutSource = EAstralLoadoutSource::PartyCache;
				}
			}
		}
	}
	if (!EquipmentIds)
	{
		if (EquipmentManager->GetEquipmentPolicy() != EAstralEquipmentPolicy::Full)
		{
			if (bReapply)
			{
				EquipmentManager->UnequipAll();
			}
			return;
		}
		EquipmentIds = &PawnData->DefaultEquipment;
		LastLoadoutSource = EAstralLoadoutSource::PawnDataFallback;
	}

	if (bReapply)
	{
		if (EquipmentManager->MatchesEquippedItems(*EquipmentIds))
		{
			return;
		}
		EquipmentManager->UnequipAll();
	}

	for (const FPrimaryAssetId& ItemId : *EquipmentIds)
	{
		EquipmentManager->EquipItemById(ItemId);
	}

	// 스타일↔장비 정합 — 현재 스타일 유지 시도, 현 스타일 장비가 없으면(총만 든 로드아웃 등) 장비 있는 쪽으로 폴백
	if (const UAstralAbilitySystemComponent* AstralASC = Cast<UAstralAbilitySystemComponent>(UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Owner)))
	{
		UAstralCombatStatics::ApplyCombatStyle(Owner, AstralASC->GetCombatStyle());
	}
}
