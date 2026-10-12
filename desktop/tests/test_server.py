import asyncio

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
