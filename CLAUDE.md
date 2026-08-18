# AstralBreak

UE 5.7.4 기반 4인 협동 액션 RPG. 런타임 모듈 1개(`Source/AstralBreak`), Lyra 아키텍처 미러
(InitState 체인 · AbilitySet · AssetManager/GameData · PawnExtension/HeroComponent 분리).

## 코드 탐색 규칙

- 파일 읽기는 Bash(`cat`)가 아니라 **Read 도구**를 사용할 것
- 검색은 **Grep / Glob 도구** 사용. 여러 파일을 `for` 루프나 파이프 체인으로
  순회하지 말 것
- 명령 출력을 임시 파일로 리다이렉트(`> /tmp/out.txt`)하지 말 것.
  필요하면 여러 번 나눠 읽을 것
- 여러 파일이 필요하면 Read를 병렬로 여러 번 호출할 것
- 분석 단계에서는 git 상태를 변경하지 말 것 (commit/checkout/stash 등)
