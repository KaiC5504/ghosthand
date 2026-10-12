import asyncio
import subprocess
import sys

import pytest
from fakes import FakeBackend, FakeElement, FakeWin, window_info
from mcp.server.mcpserver.exceptions import ToolError

from ghosthand import server
from ghosthand.desktop import Desktop


@pytest.fixture
def desktop(monkeypatch):
    editor = FakeElement("window", "Editor", rid=(1,)).add(FakeElement("button", "Save", rid=(1, 1), actions=("press",)))
    desk = Desktop(FakeBackend({100: editor}), FakeWin(window_info(100, "Editor", "notepad")), sleep=lambda seconds: None)
    monkeypatch.setattr(server, "_desktop", desk)
    return desk


def call(name, arguments):
    return asyncio.run(server.server.call_tool(name, arguments)).content


def test_all_eight_tools_are_offered():
    names = {tool.name for tool in asyncio.run(server.server.list_tools())}
    assert names == {"windows", "launch", "read", "act", "set_text", "keys", "wait_for", "screenshot"}


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
    def broken(*args):
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
