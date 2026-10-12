import pytest

from ghosthand.win32 import Win32

pytestmark = pytest.mark.real


def test_lists_visible_windows_with_their_apps():
    rows = Win32().list_windows()
    assert rows
    assert all(row.title and row.app for row in rows)
    assert sum(row.front for row in rows) <= 1


def test_captures_the_front_window_as_png():
    win = Win32()
    assert win.capture(win.foreground()).startswith(b"\x89PNG")


def test_resolves_the_front_window_info():
    win = Win32()
    front = win.foreground()
    info = win.info(front)
    assert info.hwnd == front and info.front and info.app != "unknown"


def test_posting_no_keys_is_safe():
    win = Win32()
    win.post_keys(win.foreground(), [])
