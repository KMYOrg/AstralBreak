// uigen 이 처음 한 번 만든 스텁 — 이제 사람 소유다. uigen 은 이 파일을 다시 쓰지 않는다(설계 Docs/Design/ui-autogen-pipeline.md §3-3).
// 게임 연결(GAS 속성 변화 · 컴포넌트 통지 → 생성 베이스의 setter 호출)은 여기에 쓴다.

#pragma once

#include "CoreMinimal.h"
#include "UI/Screens/AutoGen/AstralHubMemberRowViewBase.h"
#include "AstralHubMemberRowWidget.generated.h"

/**
 * HubMemberRow 화면 위젯 — WBP 의 부모 클래스. 바인딩 위젯과 setter 는 생성 베이스 UAstralHubMemberRowViewBase 에 있다.
 * 허브 준비 화면(UAstralHubReadyWidget)이 파티원 한 사람씩 채운다. 값의 원천을 스스로 붙잡지 않는다 — 놓는 화면이 통지를 받아 다시 부른다.
 * WBP 의 처음 상태는 컨셉 상태(초승달 · '준비 완료' 켬 · 보기 이름)라, 게임에서는 놓는 화면이 첫 갱신에서 네 줄을 모두 정한다
 */
UCLASS()
class ASTRALBREAK_API UAstralHubMemberRowWidget : public UAstralHubMemberRowViewBase
{
	GENERATED_BODY()

public:
	/** 한 사람 — 이름 · 방장 표시 · 준비 완료 */
	void ShowMember(const FText& MemberName, bool bIsLeader, bool bIsReady);

	/** 빈 자리 — 줄을 접는다. 화면은 캔버스라 다른 줄은 움직이지 않는다 */
	void ShowEmpty();

	/** 사람이 앉아 있는 줄인가 */
	bool IsShowingMember() const { return GetVisibility() != ESlateVisibility::Collapsed; }
};
