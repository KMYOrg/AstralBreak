"""uigen pytest 공통 — 에디터 · 네트워크 · LLM 없이 돈다.

    Tools/mcp/.venv/Scripts/python.exe -X utf8 -B -m pytest Tools/uigen/tests -q -p no:cacheprovider
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys

import pytest

UIGEN = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UIGEN))

FIXTURE_DIR = UIGEN / "fixtures" / "m4_combat_hud"
_BRIEF = json.loads((FIXTURE_DIR / "brief.json").read_text(encoding="utf-8"))
_SPEC = json.loads((FIXTURE_DIR / "spec.json").read_text(encoding="utf-8"))


def fixture_brief() -> dict:
    return copy.deepcopy(_BRIEF)


def fixture_spec() -> dict:
    return copy.deepcopy(_SPEC)


def widget(spec: dict, wid: str) -> dict:
    return next(w for w in spec["widgets"] if w["id"] == wid)


def write_fixture(dest: pathlib.Path, brief: dict, spec: dict) -> pathlib.Path:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "brief.json").write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
    (dest / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return dest


@pytest.fixture
def brief() -> dict:
    return fixture_brief()


@pytest.fixture
def spec() -> dict:
    return fixture_spec()


class FakeToolchain:
    """core.ue.Toolchain 의 가짜 — 에디터 · UBT 없이 codegen · build · verify · finalize 흐름을 돈다.

    '바이너리' = 마지막으로 빌드가 성공했을 때 생성 헤더에 적힌 계약(list_bind_widgets 가 그것을 돌려준다).
    브리지 Tool(call)은 tests/fake_editor.FakeEditor 가 받는다. 에디터 세션 = pid — quit 하면 저장 안 한 패키지가 사라지고, 기동하면 pid 가 바뀐다.
    """

    def __init__(self, module_root: pathlib.Path, running: bool = True, build_ok: bool = True, quit_error: str | None = None):
        from fake_editor import FakeEditor
        self.module_root = pathlib.Path(module_root)
        self.running = running
        self.build_ok = build_ok
        self.quit_error = quit_error
        self.calls: list[str] = []
        self.binary: list[dict] = []
        self.pid = 4242
        self.launches = 0
        self.editor = FakeEditor(self)

    def editor_status(self):
        self.calls.append("status")
        return {"process_id": self.pid} if self.running else None

    def call(self, tool, params=None, timeout=180.0):
        from core.ue import ToolchainError
        from fake_editor import FakeBridgeError
        self.calls.append(tool)
        if not self.running:
            raise ToolchainError("EDITOR_GONE", f"{tool}: editor not running", error={"code": "EDITOR_GONE"}, tool=tool)
        try:
            return self.editor.call(tool, params or {})
        except FakeBridgeError as exc:
            raise ToolchainError(exc.code, f"{tool}: {exc}", error={"code": exc.code, "message": str(exc)}, tool=tool) from exc

    def list_bind_widgets(self, class_path):
        self.calls.append("list")
        return [dict(b) for b in self.binary]

    def quit_editor(self):
        self.calls.append("quit")
        if self.quit_error:
            from core.ue import ToolchainError
            raise ToolchainError("QUIT_REFUSED", self.quit_error, error={"code": "DIRTY_PACKAGES"})
        self.running = False
        self.editor.end_session()
        return {"process_id": self.pid, "discarded_packages": []}

    def wait_exit(self, pid):
        self.calls.append("wait_exit")
        return 0.1

    def editor_processes(self):
        self.calls.append("processes")
        return []

    def build(self, log_path):
        self.calls.append("build")
        pathlib.Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        line = "Result: Succeeded" if self.build_ok else "Result: Failed (OtherCompilationError)"
        pathlib.Path(log_path).write_text(f"fake build\n{line}\n", encoding="utf-8")
        if self.build_ok:
            from core import cppgen
            header = self.module_root / "UI" / "HUD" / "AutoGen" / "AstralCombatHUDViewBase.h"
            contract = cppgen.read_generated(header)["contract"] or {"bindings": []}
            self.binary = [{"name": b["name"], "widget_class": b["widget_class"], "optional": b["optional"]} for b in contract["bindings"]]
        return {"ok": self.build_ok, "exit_code": 0 if self.build_ok else 6, "result_line": line, "duration_s": 0.01, "command": ["Build.bat"],
                "errors": [] if self.build_ok else ["AstralCombatHUDViewBase.cpp(1): error C2065: fake"]}

    def launch_editor(self, log_path):
        self.calls.append("launch")
        self.running = True
        self.launches += 1
        self.pid = 5151 if self.launches == 1 else 5151 + self.launches
        if not self.binary:   # 떠 있지 않던 에디터를 처음 띄움 — 이미 빌드된 생성 헤더가 있으면 그것이 바이너리다
            from core import cppgen
            header = self.module_root / "UI" / "HUD" / "AutoGen" / "AstralCombatHUDViewBase.h"
            contract = cppgen.read_generated(header)["contract"] if header.is_file() else None
            if contract:
                self.binary = [{"name": b["name"], "widget_class": b["widget_class"], "optional": b["optional"]} for b in contract["bindings"]]
        return self.pid

    def wait_bridge(self, pid=None):
        self.calls.append("wait_bridge")
        return 0.1


@pytest.fixture(autouse=True)
def no_toolchain(monkeypatch):
    """실제 에디터 · UBT 금지 — codegen 을 부르는 시험은 FakeToolchain 을 넘긴다."""
    from stages import codegen

    def refuse(run):
        raise AssertionError("real UE toolchain (editor · UBT) in a uigen unit test — pass a FakeToolchain")

    monkeypatch.setattr(codegen, "default_toolchain", refuse)


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    """실제 claude CLI 금지 — LLM 단계 시험은 가짜 CLI(tests/fake_claude.py)를 cli= 로 넘긴다."""
    from core import llm

    def refuse(llm_cfg):
        raise AssertionError("real claude CLI in a uigen unit test — pass cli=[python, fake_claude.py]")

    monkeypatch.setattr(llm, "default_cli", refuse)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """브리지 · HTTP 호출 금지 — 1a-1 시험은 에디터 없이 돈다."""
    import httpx

    def refuse(*args, **kwargs):
        raise AssertionError("real HTTP call in a uigen unit test")

    monkeypatch.setattr(httpx, "post", refuse)
    monkeypatch.setattr(httpx, "get", refuse)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
