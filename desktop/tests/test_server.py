import asyncio
import json
import subprocess
import sys

import pytest
from fakes import FakeBackend, FakeElement, FakeWin, window_info
from mcp.server.mcpserver.exceptions import ToolError

from ghosthand import server
from ghosthand.desktop import Desktop
from ghosthand.failures import FailureLog


@pytest.fixture(autouse=True)
def failure_log(tmp_path, monkeypatch):
    log = FailureLog(tmp_path, "test")
    monkeypatch.setattr(server, "_log", log)
    return log


def logged(log):
    return [json.loads(line) for line in log.path.read_text("utf-8").splitlines()]


@pytest.fixture
def desktop(monkeypatch):
    editor = FakeElement("window", "Editor", rid=(1,)).add(FakeElement("button", "Save", rid=(1, 1), actions=("press",)))
    desk = Desktop(FakeBackend({100: editor}), FakeWin(window_info(100, "Editor", "notepad")), sleep=lambda seconds: None)
    monkeypatch.setattr(server, "_desktop", desk)
    return desk


def call(name, arguments):
    return asyncio.run(server.server.call_tool(name, arguments)).content


def test_all_nine_tools_are_offered():
    names = {tool.name for tool in asyncio.run(server.server.list_tools())}
    assert names == {"windows", "launch", "read", "act", "set_text", "keys", "wait_for", "screenshot", "report_issue"}


def test_read_and_act_go_through_the_desktop(desktop):
    assert 'e2 button "Save" [press]' in call("read", {"window": "notepad"})[0].text
    assert call("act", {"ref": "e2"})[0].text.startswith("press e2: done")


def test_errors_come_back_as_plain_messages(desktop):
    with pytest.raises(ToolError, match="unknown ref e99: read the window first"):
        asyncio.run(server.server.call_tool("act", {"ref": "e99"}))


def test_screenshot_is_a_png_image(desktop):
    content = call("screenshot", {"window": "notepad"})
    assert content[0].type == "image" and content[0].mime_type == "image/png"


def test_unexpected_failures_say_what_broke(desktop, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("the walker fell over")

    monkeypatch.setattr(desktop, "read", broken)
    with pytest.raises(ToolError, match="RuntimeError: the walker fell over"):
        asyncio.run(server.server.call_tool("read", {"window": "notepad"}))


def test_real_server_starts_its_ui_thread_in_a_fresh_process():
    # comtypes sets up COM the moment it is first imported, which in the real server happens on
    # the UI Automation thread; inside pytest it was already imported, so a fresh interpreter is needed.
    code = "import asyncio; from ghosthand import server; print(len(asyncio.run(server.server.call_tool('windows', {})).content[0].text))"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr[-800:]


def test_window_numbers_can_be_sent_as_numbers(desktop):
    assert 'e2 button "Save"' in call("read", {"window": 100})[0].text


def test_failed_calls_are_logged_after_the_calls_before_them(desktop, failure_log):
    call("read", {"window": "notepad"})
    with pytest.raises(ToolError):
        asyncio.run(server.server.call_tool("act", {"ref": "e99"}))

    [record] = logged(failure_log)
    assert (record["tool"], record["args"]) == ("act", {"ref": "e99", "action": "auto"})
    assert record["error"] == "unknown ref e99: read the window first"
    assert [step["tool"] for step in record["recent"]] == ["read"]


def test_internal_errors_are_logged_with_the_traceback(desktop, failure_log, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("the walker fell over")

    monkeypatch.setattr(desktop, "read", broken)
    with pytest.raises(ToolError):
        asyncio.run(server.server.call_tool("read", {"window": "notepad"}))

    trace = logged(failure_log)[0]["traceback"]
    assert "in broken" in trace and "RuntimeError: the walker fell over" in trace


def test_report_issue_writes_an_ai_record(desktop, failure_log):
    text = call("report_issue", {"what_happened": "act said done, page did not change", "expected": "detail page", "tool": "act"})[0].text
    assert str(failure_log.path) in text
    assert logged(failure_log)[0]["source"] == "ai"
