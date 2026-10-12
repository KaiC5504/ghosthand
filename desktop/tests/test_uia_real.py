import time

import pytest

from ghosthand.reader import walk
from ghosthand.uia import UiaBackend
from ghosthand.win32 import Win32

pytestmark = pytest.mark.real


def window_titled(win, title):
    return next((row.hwnd for row in win.list_windows() if row.title == title), None)


@pytest.fixture(scope="module")
def calculator():
    win = Win32()
    hwnd = window_titled(win, "Calculator")
    if hwnd is None:
        win.launch("calculator:", [])
        for _ in range(40):
            time.sleep(0.25)
            hwnd = window_titled(win, "Calculator")
            if hwnd:
                break
    assert hwnd, "Calculator did not open"
    return hwnd


def test_reads_calculator_buttons_with_actions(calculator):
    backend = UiaBackend()
    nodes, truncated = walk(backend, backend.root(calculator))
    seven = next(node for node in nodes if node.info.name == "Seven")
    assert seven.info.role == "button" and "press" in seven.info.actions and seven.info.runtime_id
    assert not truncated


def test_press_changes_the_display(calculator):
    backend = UiaBackend()
    nodes, _ = walk(backend, backend.root(calculator))
    by_name = {node.info.name: node for node in nodes}
    backend.perform(by_name["Clear"].handle, "press")
    backend.perform(by_name["Seven"].handle, "press")
    nodes, _ = walk(backend, backend.root(calculator))
    assert any(node.info.name == "Display is 7" for node in nodes)


def test_flutter_cards_have_no_runtime_id_but_a_default_action():
    win = Win32()
    hwnd = next((row.hwnd for row in win.list_windows() if row.app == "kazumi"), None)
    if hwnd is None:
        pytest.skip("Kazumi is not open")
    backend = UiaBackend()
    nodes, _ = walk(backend, backend.root(hwnd))
    images = [node for node in nodes if node.info.role == "image" and node.info.name]
    assert images
    assert all(node.info.runtime_id is None and "default" in node.info.actions for node in images)
