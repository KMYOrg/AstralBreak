# AstralBreak

UE 5.7.4 기반 4인 협동 액션 RPG. 런타임 모듈 1개(`Source/AstralBreak`) + 에디터 전용 UncookedOnly 모듈
`Source/AstralBreakEditor`(커스텀 애님 그래프 노드만), Lyra 아키텍처 미러
(InitState 체인 · AbilitySet · AssetManager/GameData · PawnExtension/HeroComponent 분리).

## 코드 탐색 규칙

- 파일 읽기는 Bash(`cat`)가 아니라 **Read 도구**를 사용할 것
- 검색은 **Grep / Glob 도구** 사용. 여러 파일을 `for` 루프나 파이프 체인으로
  순회하지 말 것
- 명령 출력을 임시 파일로 리다이렉트(`> /tmp/out.txt`)하지 말 것.
  필요하면 여러 번 나눠 읽을 것
- 여러 파일이 필요하면 Read를 병렬로 여러 번 호출할 것
- 분석 단계에서는 git 상태를 변경하지 말 것 (commit/checkout/stash 등)

## 명령 실행 규칙 (권한 프롬프트 없이 돌게)

`.claude/settings.local.json` 의 허용 규칙과 **같은 모양**으로 쓸 때만 확인 없이 돈다. 모양이 어긋나면 프롬프트가 뜨고, 그사이 사용자가 없으면 취소된다.

- 스크래치 루트 = `C:/Users/KMY96/AppData/Local/Temp/claude/D--UE5Projects-AstralBreak/` (세션 scratchpad 가 이 아래).
  작업 폴더에 들어 있어 Read · Write · Edit 도구는 확인 없이 된다.
  `mkdir -p <절대 경로>` · `cp -r D:/UE5Projects/AstralBreak/Tools/mcp/anim_gen <스크래치>/…` · 스크래치 안끼리 `cp` · `cmp`
- 읽기 전용 Bash 는 훅 `.claude/hooks/allow_readonly.py` 가 자동 승인한다(목록 안 명령만, `&&` · `|` 로 이어도 됨 —
  따옴표 안의 `|` `;` 는 연산자로 보지 않는다). `$(…)` · 백틱 · `$'…'` · 리다이렉트(`/dev/null` 제외) · 목록 밖 명령이 하나라도 섞이면 보류된다
- UI 파이프라인: `…python.exe -X utf8 -B D:/UE5Projects/AstralBreak/Tools/uigen/run_pipeline.py …`
- Python 은 `D:/UE5Projects/AstralBreak/Tools/mcp/.venv/Scripts/python.exe -X utf8 -B` 로 시작:
  `-m pytest … -p no:cacheprovider` · 스크래치 스크립트 · `-u D:/UE5Projects/AstralBreak/Tools/mcp/anim_gen_phase*_test.py …`.
  다른 사본(기준 사본 등)을 import 하려면 `-o "pythonpath=<사본 루트> D:/UE5Projects/AstralBreak/Tools/mcp"` 를 붙이고
  저장소 루트에서 돌린다(사본이 앞 — `anim_graph_mcp` 는 Tools/mcp 에서)
- 에디터 주기: `tasklist` 로 다른 에디터가 없는지 확인 →
  `D:/UnrealSource/UnrealEngine-5.7.4-release/Engine/Binaries/Win64/UnrealEditor-Win64-DebugGame.exe D:/UE5Projects/AstralBreak/AstralBreak.uproject -log -unattended`
  (백그라운드) → `…python.exe -X utf8 -B D:/UE5Projects/AstralBreak/Tools/mcp/wait_for_bridge.py 540 10` → 끝에 `quit_editor`(이것만 확인 대상 —
  더티면 거절, 테스트 경로뿐일 때만 discard) → `…/wait_for_exit.py <pid> 180 5`
- 파일 만들기는 **Write 도구**(heredoc · `>` 금지). `$VAR` · `$(…)` 대신 절대 경로를 그대로, 환경 변수 접두어
  (`PYTHONIOENCODING=…`) 대신 `-X utf8`. 명령 하나에 한 동작 — 허용 안 된 명령을 `&&` 로 섞지 않는다
- `rm` · `mv` 는 계속 확인 대상이다. 스크래치도 지우지 말고 새 폴더 이름(`…2`, `…3`)을 쓰고, `-B` · `no:cacheprovider` 로
  지울 캐시를 만들지 않는다. 일회성 파일 정리는 끝에 목록 → 사용자 승인 → 휴지통
