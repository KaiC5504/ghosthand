import time

import pytest

from ghosthand.win32 import Win32

pytestmark = pytest.mark.real


@pytest.fixture(scope="module")
def calculator():
    # The window in front can be one that refuses to draw or name itself (a system or elevated
    # window), so these checks use a window they open themselves.
    win = Win32()
    hwnd = next((row.hwnd for row in win.list_windows() if row.title == "Calculator"), None)
    if hwnd is None:
        win.launch("calculator:", [])
        for _ in range(40):
            time.sleep(0.25)
            hwnd = next((row.hwnd for row in win.list_windows() if row.title == "Calculator"), None)
            if hwnd:
                break
    assert hwnd, "Calculator did not open"
    return hwnd


def test_lists_visible_windows_with_their_apps():
    rows = Win32().list_windows()
    assert rows
    assert all(row.title and row.app for row in rows)
    assert sum(row.front for row in rows) <= 1


def test_captures_a_window_as_png(calculator):
    assert Win32().capture(calculator).startswith(b"\x89PNG")


def test_resolves_a_window_info(calculator):
    info = Win32().info(calculator)
    assert info.hwnd == calculator and info.title == "Calculator" and info.app != "unknown"


def test_posting_no_keys_is_safe(calculator):
    Win32().post_keys(calculator, [])
