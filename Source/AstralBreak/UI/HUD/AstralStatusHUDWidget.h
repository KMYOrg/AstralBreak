// uigen 스텁 자리(사람 소유 — uigen 은 이 파일을 다시 쓰지 않는다, 설계 Docs/Design/ui-autogen-pipeline.md §3-3).
// 게임 연결(GAS 속성 변화 · 명단 통지 → 생성 베이스의 setter 호출)은 여기에 쓴다.

#pragma once

#include "CoreMinimal.h"
#include "AttributeSet.h"
#include "Misc/CoreMiscDefines.h"
#include "UI/HUD/AutoGen/AstralStatusHUDViewBase.h"
#include "AstralStatusHUDWidget.generated.h"

class AAstralGameState;
class AAstralPlayerState;
class AGameStateBase;
class APawn;
class APlayerState;
class UAbilitySystemComponent;
struct FOnAttributeChangeData;

/**
 * StatusHUD 화면 위젯 — 내 상태와 동료 3 줄. WBP 의 부모 클래스, 바인딩 위젯과 setter 는 생성 베이스 UAstralStatusHUDViewBase 에 있다.
 * 메인 HUD 설계(Docs/Design/ui-autogen-pipeline.md §11 '메인 HUD 설계'). 화면은 상태를 갖지 않는다 — 전부 원천의 통지를 받아 setter 로 옮긴다.
 *
 *   칸 4   나(0) · 동료(1 ~ 3) — 칸마다 PlayerState 하나. 나와 동료를 같은 틀로 본다(폰이 없어도 · 멀어도 PlayerState 의 ASC 는 복제된다)
 *   명단   AAstralGameState::OnPlayerRosterChanged → 나 = 소유 컨트롤러의 PlayerState, 동료 = 나머지를 PlayerId 순(AstralParty::SelectAllyIndices)
 *   값     칸의 ASC 속성 변화 통지 — HP · 오의(동료의 얇은 막대), 나는 + 스태미나 · 표식. 비율은 매번 지금 값 둘로(최대치가 기본값 그대로면 통지가 없다)
 *   늦게   속성 세트(AbilitySet 이 줌)는 클라이언트에 늦게 올 수 있다 — 칸의 OnPawnSet → 그 폰의 PawnExtension 이 ASC 준비를 알리면 다시 읽는다
 *   보이기 어느 맵에 뜨는가는 그 맵의 목록(AAstralGameState::ContextHUDWidgets — 레이드만)이 정한다. 허브 폰에는 전투 자원이 없다
 *
 * 게임 월드에서 소유 플레이어가 있을 때만 동작한다 — 에디터 렌더(uigen 검증의 render_widget)는 spec 상태 · 덮어쓰기 그대로 그린다.
 */
UCLASS()
class ASTRALBREAK_API UAstralStatusHUDWidget : public UAstralStatusHUDViewBase
{
	GENERATED_BODY()

public:
	/** 동료 줄 수 — 바인딩 계약(Ally1 ~ Ally3)과 같다 */
	static constexpr int32 MaxAllies = 3;

	/** 지금 칸에 앉은 사람 — 0 = 나, 1 ~ MaxAllies = 동료. 자동 시험이 읽는다 */
	AAstralPlayerState* GetSlotPlayerState(int32 SlotIndex) const;

protected:
	virtual void NativeConstruct() override;
	virtual void NativeDestruct() override;

private:
	static constexpr int32 NumSlots = 1 + MaxAllies;

	struct FPlayerSlot
	{
		TWeakObjectPtr<AAstralPlayerState> PlayerState;
		TWeakObjectPtr<UAbilitySystemComponent> ASC;
		TArray<TPair<FGameplayAttribute, FDelegateHandle>> Handles;
	};

	// ─── 연결 ───

	void HandleGameStateSet(AGameStateBase* GameState);
	void HandleRosterChanged();

	/** 칸에 앉은 사람을 바꾼다 — 같은 사람이면 값만 다시 그린다 */
	void SetSlot(int32 SlotIndex, AAstralPlayerState* PlayerState);
	void ClearSlot(int32 SlotIndex);

	UFUNCTION()
	void HandlePawnSet(APlayerState* Player, APawn* NewPawn, APawn* OldPawn);

	/** 그 폰이 자기 ASC 의 아바타가 되면(이미 됐으면 바로) 값을 다시 읽는다 — 이때는 속성 세트가 와 있다 */
	void WatchPawn(APawn* Pawn);
	void HandleAbilitySystemInitialized();

	// ─── 원천 → 화면 ───

	void HandleSlotAttributeChanged(const FOnAttributeChangeData& Data, int32 SlotIndex);
	void RefreshSlot(int32 SlotIndex);
	void RefreshSelf(const UAbilitySystemComponent* ASC);
	void RefreshAlly(int32 AllyIndex, const AAstralPlayerState* PlayerState, const UAbilitySystemComponent* ASC);

	// 동료 줄의 setter — 바인딩이 줄마다 따로라(Phase 1 어휘에 list · 하위 WBP 가 없다) 번호로 고른다
	void SetAllyVisible(int32 AllyIndex, bool bVisible);
	void SetAllyName(int32 AllyIndex, const FText& Name);
	void SetAllyHp(int32 AllyIndex, float Percent);
	void SetAllyUlt(int32 AllyIndex, float Percent);

	FPlayerSlot Slots[NumSlots];

	TWeakObjectPtr<AAstralGameState> BoundGameState;
	FDelegateHandle GameStateSetHandle;
	FDelegateHandle RosterChangedHandle;
};
