# uigen LLM 단계 작업 폴더

`Tools/uigen/run_pipeline.py` 가 `claude -p` 로 부르는 LLM 단계(verifier · fix — Phase 1b 부터)의 cwd 입니다(설계 §10-1 · §10-2).
- 입력 파일은 프롬프트에 절대 경로로 주고, 출력은 `--json-schema` 의 structured_output 으로만 받습니다. 파일을 쓰지 않습니다.
- 권한은 `.claude/settings.json`(Bash · 쓰기 · 웹 거부, auto-memory 끔)과 명령의 `--allowedTools`(Read)로 묶습니다.
