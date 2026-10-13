import ctypes
import re
import subprocess
import threading
import time
from ctypes import wintypes

import pytest

from ghosthand.desktop import Desktop
from ghosthand.uia import UiaBackend
from ghosthand.win32 import Win32

pytestmark = pytest.mark.real

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
KAZUMI = r"D:\Tools\Kazumi\kazumi.exe"
BTR_ID = "jcfakgmhohdhbmbcifhlfmiakenjlpcm"

WH_MOUSE_LL, WM_QUIT, LLMHF_INJECTED = 14, 0x0012, 0x1

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]


def cursor():
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


class MouseWatch:
    """Tells mouse input injected by software apart from the user's own hand while they keep working."""

    def __enter__(self):
        self.injected = self.physical = 0
        self.start = cursor()
        ready = threading.Event()
        self.thread = threading.Thread(target=self._listen, args=(ready,), daemon=True)
        self.thread.start()
        assert ready.wait(2), "could not watch the mouse"
        return self

    def _listen(self, ready):
        def seen(code, wparam, lparam):
            if code >= 0:
                if ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents.flags & LLMHF_INJECTED:
                    self.injected += 1
                else:
                    self.physical += 1
            return user32.CallNextHookEx(None, code, wparam, lparam)

        self._proc = HOOKPROC(seen)
        self.thread_id = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            return
        ready.set()
        msg = wintypes.MSG()
        # Low-level hooks are called while this thread waits for messages.
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(hook)

    def __exit__(self, *exc):
        self.end = cursor()
        user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        self.thread.join(2)

    def assert_untouched(self):
        assert self.injected == 0, f"software sent {self.injected} mouse events"
        if self.physical == 0:
            assert self.end == self.start


def refs(text, pattern):
    return [row.split()[0] for row in text.splitlines() if re.search(pattern, row.strip())]


@pytest.fixture(scope="module")
def desk():
    return Desktop(UiaBackend(), Win32())


def calculator(desk):
    hwnd = next((row.hwnd for row in desk.win.list_windows() if row.title == "Calculator"), None)
    if hwnd is None:
        desk.launch("calculator:")
        hwnd = next(row.hwnd for row in desk.win.list_windows() if row.title == "Calculator")
    return hwnd


@pytest.fixture
def chrome_window(desk):
    before = {row.hwnd for row in desk.win.list_windows()}
    subprocess.Popen([CHROME, "--new-window", "about:blank"])
    fresh = []
    for _ in range(40):
        time.sleep(0.25)
        fresh = [row for row in desk.win.list_windows() if row.hwnd not in before and row.app == "chrome"]
        if fresh:
            break
    assert fresh, "no new Chrome window"
    time.sleep(1)
    yield fresh[0].hwnd
    ctypes.windll.user32.PostMessageW(fresh[0].hwnd, 0x0010, 0, 0)


def test_calculator_without_the_mouse(desk):
    with MouseWatch() as mouse:
        text = desk.read(calculator(desk))
        for key in ("Clear", "Seven", "Multiply by", "Six", "Equals"):
            text = desk.act(refs(text, rf'^e\d+ button "{key}"')[0])
    assert "Display is 42" in text
    mouse.assert_untouched()


def test_kazumi_open_a_card_and_go_back(desk):
    with MouseWatch() as mouse:
        if not any(row.app == "kazumi" for row in desk.win.list_windows()):
            desk.launch(KAZUMI)
        home = desk.wait_for("kazumi", "热门番组")
        card_row = next(row.strip() for row in home.splitlines() if re.match(r'^e\d+ image "', row.strip()))
        card, title = card_row.split()[0], card_row.split('"')[1]
        opened = desk.act(card)
        detail = desk.wait_for("kazumi", "更多操作")
        unnamed = [re.match(r"^(e\d+) button @(-?\d+),(-?\d+)", row.strip()) for row in detail.splitlines()]
        back = min((match for match in unnamed if match), key=lambda match: int(match[2]) + int(match[3]))[1]
        returned = desk.act(back)
        assert title in desk.wait_for("kazumi", title)
    mouse.assert_untouched()
    # The user may switch windows themselves meanwhile. The promise: Kazumi does not keep the focus, or
    # ghosthand says Windows refused to hand it back.
    refused = "would not let ghosthand hand it back" in opened + returned
    assert refused or desk.win.info(desk.win.foreground()).app != "kazumi"
    assert any(row.app == "kazumi" for row in desk.win.list_windows())


def test_chrome_address_bar_works_while_another_window_is_in_front(desk, chrome_window):
    calc = calculator(desk)
    assert desk.win.set_foreground(calc)
    with MouseWatch() as mouse:
        bar = refs(desk.read(chrome_window), r'^e\d+ edit "Address and search bar"')[0]
        desk.set_text(bar, "https://example.com/", submit=True)
        assert "Example Domain" in desk.wait_for(chrome_window, "Example Domain")
    assert desk.win.foreground() != chrome_window
    mouse.assert_untouched()


def test_extensions_page_survives_the_tooltip_loop(desk, chrome_window):
    bar = refs(desk.read(chrome_window), r'^e\d+ edit "Address and search bar"')[0]
    desk.set_text(bar, f"chrome://extensions/?id={BTR_ID}", submit=True)
    page = desk.wait_for(chrome_window, "Inspect views")
    reload_ref = refs(page, r'^e\d+ button "Reload"')[-1]
    started = time.perf_counter()
    after = desk.act(reload_ref)
    if "Reloaded" not in after:
        after = desk.wait_for(chrome_window, "Reloaded", timeout=3)
    assert "Reloaded" in after
    assert time.perf_counter() - started < 5


def test_closing_a_window_through_its_own_button(desk):
    with MouseWatch() as mouse:
        text = desk.read(calculator(desk))
        out = desk.act(refs(text, r'^e\d+ button "Close Calculator"')[0])
    assert out.endswith("; the window closed")
    mouse.assert_untouched()


FORM = (
    "Add-Type -AssemblyName System.Windows.Forms; $f = New-Object System.Windows.Forms.Form; "
    "$f.Text = 'ghosthand keys test'; $t = New-Object System.Windows.Forms.TextBox; $f.Controls.Add($t); "
    "$f.Add_Shown({ $t.Focus() }); [System.Windows.Forms.Application]::Run($f)"
)


@pytest.fixture
def classic_form(desk):
    process = subprocess.Popen(["powershell", "-NoProfile", "-Command", FORM])
    hwnd = None
    for _ in range(60):
        time.sleep(0.25)
        hwnd = next((row.hwnd for row in desk.win.list_windows() if row.title == "ghosthand keys test"), None)
        if hwnd:
            break
    assert hwnd, "test form did not open"
    time.sleep(0.5)
    yield hwnd
    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
    process.wait(10)


def test_background_keys_reach_the_focused_control_of_a_classic_window(desk, classic_form):
    with MouseWatch() as mouse:
        out = desk.keys(classic_form, "g h 7")
    assert re.search(r'edit\b.*= "gh7"', out), out
    mouse.assert_untouched()
