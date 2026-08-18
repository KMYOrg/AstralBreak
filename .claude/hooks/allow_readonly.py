#!/usr/bin/env python3
"""
Claude Code PreToolUse hook - 읽기 전용 Bash 명령 자동 승인

동작:
  - 화이트리스트에 해당하면 permissionDecision: "allow" 를 출력 -> 프롬프트 없이 실행
  - 그 외에는 아무것도 출력하지 않고 exit 0 -> 평소대로 권한 프롬프트

주의:
  - 판단이 조금이라도 애매하면 무조건 보류(fail-safe)한다.
  - ⚠️ PreToolUse 의 permissionDecision "allow" 는 권한 시스템을 우회한다.
    settings.json 의 deny / ask 규칙이 백스톱이 되어준다고 가정하지 말 것 —
    이 화이트리스트가 사실상 유일한 방어선이다. 항목 추가 시 그 전제로 검토한다.
  - 래퍼 명령(xargs / env 처럼 뒤에 오는 명령을 실행하는 것)은 READ_ONLY 에 넣지 말고
    반드시 안쪽 명령을 재귀 검증할 것. 넣는 순간 `env rm -rf` 로 전부 무력화된다.
"""

import json
import re
import sys

# ---------------------------------------------------------------- 화이트리스트

READ_ONLY = {
    "ls", "cat", "echo", "pwd", "head", "tail", "grep", "egrep", "fgrep",
    "rg", "find", "fd", "wc", "which", "file", "stat", "du", "df", "tree",
    "cd", "sort", "uniq", "cut", "diff", "basename", "dirname", "realpath",
    "printf", "true", "cloc", "nl", "column", "jq", "xxd", "strings",
    "ripgrep", "date", "hostname", "uname", "wslpath",
    "nm", "objdump", "readelf", "size", "ldd", "comm", "paste",
    "md5sum", "sha256sum", "readlink", "seq", "expr",
}
# 주의: "env" 는 여기 없다 — 래퍼라서 아래 segment_is_safe 에서 별도 처리한다.

# 항상 안전한 git 서브커맨드
GIT_READ = {
    "status", "log", "diff", "show", "blame", "ls-files", "ls-tree",
    "rev-parse", "describe", "shortlog", "cat-file", "count-objects",
    "grep", "show-ref", "for-each-ref", "whatchanged", "reflog",
    "check-ignore", "check-attr", "rev-list", "merge-base",
    "diff-tree", "diff-index", "name-rev", "verify-pack", "var",
}

# 플래그에 따라 쓰기가 되는 서브커맨드 -> 플래그만 있을 때에 한해 허용
GIT_FLAG_ONLY = {
    "branch": {"-a", "-r", "-l", "-v", "-vv", "--list", "--all",
               "--remotes", "--verbose", "--show-current", "--sort"},
    "tag": {"-l", "-n", "--list", "--sort"},
}

# 셸 제어 키워드 (명령이 아님) -> 벗겨내고 뒤에 오는 명령을 계속 검사한다.
# while / until 은 뒤에 "조건 명령"이 오므로 반드시 여기에 있어야 한다
# (HEADER_KEYWORDS 에 두면 `while rm -rf x; do ...` 의 rm 이 검증 없이 통과한다)
STRIP_KEYWORDS = {
    "do", "done", "then", "else", "elif", "fi", "esac", "if",
    "while", "until",
    "{", "}", "(", ")", "!", "time", "exec",
}

# 세그먼트 전체가 제어 구문 헤더인 경우.
# for / case / select 는 뒤에 "단어 목록"이 올 뿐 명령을 실행하지 않는다
HEADER_KEYWORDS = {"for", "case", "select"}

SEPARATORS = re.compile(r"&&|\|\||\||;|\n|&")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
NULL_REDIRECT = re.compile(r"\d?>\s*/dev/null")
DANGEROUS_SYNTAX = re.compile(r"[<>]|\$\(|`|\beval\b|\bsudo\b|\bsource\b|\bexport\b")

# 래퍼 재귀 깊이 상한 (xargs xargs xargs ... 같은 병적 입력 차단)
MAX_WRAPPER_DEPTH = 8


def bail():
    """판단 보류 -> 일반 권한 흐름으로 넘김"""
    sys.exit(0)


# ---------------------------------------------------------------- git 판정

def is_git_read_only(tokens):
    # --output= 계열은 파일을 쓴다
    for t in tokens:
        if t.startswith("--output"):
            return False

    sub = None
    rest = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        sub = tok
        rest = tokens[i + 1:]
        break

    if sub is None:
        # git --version, git --help 등
        return all(t in ("--version", "--help", "-v", "-h") for t in tokens)

    if sub in GIT_READ:
        return True

    if sub in GIT_FLAG_ONLY:
        # 위치 인자가 하나라도 있으면 생성/삭제일 수 있으므로 거부
        allowed = GIT_FLAG_ONLY[sub]
        for a in rest:
            if not a.startswith("-"):
                return False
            if a.split("=")[0] not in allowed:
                return False
        return True

    if sub == "remote":
        if not rest:
            return True
        if rest[0] in ("-v", "--verbose"):
            return len(rest) == 1
        if rest[0] in ("show", "get-url"):
            return True
        return False

    if sub == "config":
        return bool(rest) and rest[0] in ("--get", "--get-all", "--get-regexp",
                                          "--list", "-l")

    return False


# ---------------------------------------------------------------- 세그먼트 판정

def segment_is_safe(seg, depth=0):
    if depth > MAX_WRAPPER_DEPTH:
        return False

    tokens = seg.split()

    # 선행 환경변수 대입과 제어 키워드 제거
    while tokens:
        head = tokens[0]
        if head in HEADER_KEYWORDS:
            return True          # for/case/select 헤더는 단어 목록만 받는다
        if head in STRIP_KEYWORDS or ASSIGNMENT.match(head):
            tokens.pop(0)
            continue
        break

    if not tokens:
        return True

    head = tokens[0].split("/")[-1].split("\\")[-1].strip("\"'")
    args = tokens[1:]

    if head == "xargs":
        # 플래그 없는 xargs 만 벗겨내고 안쪽 명령을 재귀 검사
        if not args or args[0].startswith("-"):
            return False
        return segment_is_safe(" ".join(args), depth + 1)

    if head == "env":
        # env 는 래퍼다. 인자 없이 쓰면 환경변수 출력(안전),
        # 뒤에 명령이 오면 그 명령을 재귀 검사해야 한다 (`env rm -rf` 차단)
        rest = list(args)
        while rest and ASSIGNMENT.match(rest[0]):
            rest.pop(0)
        if not rest:
            return True                       # env / env FOO=1 -> 출력만
        if rest[0].startswith("-"):
            return False                      # -i, -u, -S 등은 보류
        return segment_is_safe(" ".join(rest), depth + 1)

    if head == "git":
        return is_git_read_only(args)

    if head == "find":
        if any(a in ("-exec", "-execdir", "-delete", "-ok", "-okdir",
                     "-fprint", "-fprint0", "-fls") for a in args):
            return False

    if head in ("sort", "uniq", "split", "tee"):
        if any(a in ("-o", "--output") or a.startswith("--output=") for a in args):
            return False
        positionals = [a for a in args if not a.startswith("-")]
        if len(positionals) > 1:      # uniq in.txt out.txt -> 두 번째가 출력 파일
            return False

    return head in READ_ONLY


# ---------------------------------------------------------------- 진입점

def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        bail()

    if payload.get("tool_name") != "Bash":
        bail()

    cmd = (payload.get("tool_input") or {}).get("command", "")
    if not cmd or len(cmd) > 4000:
        bail()

    # /dev/null 리다이렉트는 무해하므로 제거한 뒤 검사
    probe = NULL_REDIRECT.sub(" ", cmd)

    if DANGEROUS_SYNTAX.search(probe):
        bail()

    for seg in SEPARATORS.split(probe):
        if not segment_is_safe(seg):
            bail()

    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "read-only analysis command",
        }
    }, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
