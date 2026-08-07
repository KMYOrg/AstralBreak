"""UE 에디터 원격 실행 브릿지. 에디터 밖(일반 python)에서 실행한다."""
import sys, time, pathlib, argparse

RE_PATH = r"D:/UnrealSource/UnrealEngine-5.7.4-release/Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python"
sys.path.append(RE_PATH)

from remote_execution import RemoteExecution, MODE_EXEC_FILE, MODE_EVAL_STATEMENT


def run(source: str, mode: str = MODE_EXEC_FILE, discover_timeout: float = 5.0) -> dict:
    rx = RemoteExecution()
    rx.start()
    try:
        deadline = time.time() + discover_timeout
        while not rx.remote_nodes and time.time() < deadline:
            time.sleep(0.2)
        if not rx.remote_nodes:
            raise RuntimeError(
                "UE 에디터를 찾지 못했습니다.\n"
                "  1) 에디터 실행 중인지\n"
                "  2) Enable Remote Execution 체크\n"
                "  3) Multicast Time-To-Live 0 -> 1\n"
                "  4) VPN/가상 어댑터 비활성화, 방화벽 UDP 6766 허용"
            )
        rx.open_command_connection(rx.remote_nodes)
        return rx.run_command(source, exec_mode=mode, unattended=True)
    finally:
        rx.stop()


def main() -> int:
    ap = argparse.ArgumentParser(description="Run python inside the running UE editor.")
    ap.add_argument("target", help="스크립트 경로 (또는 -c 사용 시 표현식)")
    ap.add_argument("-c", "--code", action="store_true", help="표현식을 즉시 평가")
    args = ap.parse_args()

    if args.code:
        source, mode = args.target, MODE_EVAL_STATEMENT
    else:
        p = pathlib.Path(args.target)
        if not p.is_file():
            print(f"[FAIL] 파일 없음: {p}", file=sys.stderr)
            return 2
        source, mode = p.read_text(encoding="utf-8"), MODE_EXEC_FILE

    res = run(source, mode)

    for line in res.get("output", []):
        print(f"[{line['type']}] {line['output']}")
    if res.get("result") not in (None, "None", ""):
        print(f"[result] {res['result']}")
    if not res.get("success"):
        print("[FAIL] 실행 실패", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())