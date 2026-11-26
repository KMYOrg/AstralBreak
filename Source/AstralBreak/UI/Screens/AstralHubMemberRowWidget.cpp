// uigen 이 처음 한 번 만든 스텁 — 이제 사람 소유다. uigen 은 이 파일을 다시 쓰지 않는다.

#include "AstralHubMemberRowWidget.h"

void UAstralHubMemberRowWidget::ShowMember(const FText& MemberName, bool bIsLeader, bool bIsReady)
{
	// 줄은 클릭을 받지 않는다 — uigen 메뉴 규칙의 '버튼 아닌 칸' 보이기(hit_test_invisible)와 같게
	SetVisibility(ESlateVisibility::HitTestInvisible);
	SetMemberName(MemberName);
	SetLeaderVisible(bIsLeader);
	SetReadyVisible(bIsReady);
}

void UAstralHubMemberRowWidget::ShowEmpty()
{
	SetVisibility(ESlateVisibility::Collapsed);
	SetMemberName(FText::GetEmpty());
	SetLeaderVisible(false);
	SetReadyVisible(false);
}
