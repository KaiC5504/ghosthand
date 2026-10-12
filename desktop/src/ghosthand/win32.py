from __future__ import annotations

import ctypes
import io
import os
import subprocess
from ctypes import wintypes
from pathlib import Path

from PIL import Image

from ghosthand.keys import KeyStroke, key_lparam
from ghosthand.model import GhostError, WindowInfo

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
GA_ROOT = 2
DWMWA_CLOAKED = 14
PW_RENDERFULLCONTENT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
INPUT_KEYBOARD, KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 1, 0x1, 0x2


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _InputUnion(ctypes.Union):
    # MOUSEINPUT is only here because it is the largest member; SendInput rejects an INPUT of the wrong size.
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _InputUnion)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


def _title(hwnd: int) -> str:
    size = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(size + 1)
    user32.GetWindowTextW(hwnd, buffer, size + 1)
    return buffer.value


def _pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _app(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return "unknown"
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return "unknown"
        return Path(buffer.value).stem
    finally:
        kernel32.CloseHandle(handle)


def _cloaked(hwnd: int) -> bool:
    value = wintypes.DWORD()
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value))
    return value.value != 0


class Win32:
    def list_windows(self) -> list[WindowInfo]:
        front = self.foreground()
        rows: list[WindowInfo] = []

        @WNDENUMPROC
        def visit(hwnd, _):
            if user32.IsWindowVisible(hwnd) and not _cloaked(hwnd):
                title = _title(hwnd)
                if title:
                    pid = _pid(hwnd)
                    rows.append(WindowInfo(hwnd=hwnd, title=title, app=_app(pid), pid=pid, front=hwnd == front))
            return True

        user32.EnumWindows(visit, 0)
        return rows

    def is_window(self, hwnd: int) -> bool:
        return bool(user32.IsWindow(hwnd))

    def info(self, hwnd: int) -> WindowInfo:
        if not self.is_window(hwnd):
            raise GhostError(f"window {hwnd} closed: call windows")
        pid = _pid(hwnd)
        return WindowInfo(hwnd=hwnd, title=_title(hwnd), app=_app(pid), pid=pid, front=hwnd == self.foreground())

    def foreground(self) -> int:
        # After Kazumi restores itself, Windows can name its inner FLUTTERVIEW child as the foreground window.
        hwnd = user32.GetForegroundWindow()
        return (user32.GetAncestor(hwnd, GA_ROOT) or hwnd) if hwnd else 0

    def set_foreground(self, hwnd: int) -> bool:
        # Windows lets only the foreground thread move the foreground, so borrow its input
        # state for the call instead of faking a keypress.
        current = user32.GetForegroundWindow()
        theirs = user32.GetWindowThreadProcessId(current, None) if current else 0
        ours = kernel32.GetCurrentThreadId()
        attached = bool(theirs) and theirs != ours and bool(user32.AttachThreadInput(ours, theirs, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(ours, theirs, False)
        return self.foreground() == hwnd

    def post_keys(self, hwnd: int, strokes: list[KeyStroke]) -> None:
        for stroke in strokes:
            scan = user32.MapVirtualKeyW(stroke.vk, 0)
            user32.PostMessageW(hwnd, WM_KEYDOWN, stroke.vk, key_lparam(scan, stroke.extended, up=False))
            user32.PostMessageW(hwnd, WM_KEYUP, stroke.vk, key_lparam(scan, stroke.extended, up=True))

    def send_keys_focused(self, hwnd: int, strokes: list[KeyStroke]) -> None:
        if not self.set_foreground(hwnd):
            raise GhostError("Windows would not bring the window to the front; ask KaiC to click it once, then try again")
        events = []
        for stroke in strokes:
            events += [(vk, False, False) for vk in stroke.modifiers]
            events += [(stroke.vk, stroke.extended, False), (stroke.vk, stroke.extended, True)]
            events += [(vk, False, True) for vk in reversed(stroke.modifiers)]
        inputs = (INPUT * len(events))()
        for slot, (vk, extended, up) in zip(inputs, events):
            slot.type = INPUT_KEYBOARD
            slot.ki = KEYBDINPUT(wVk=vk, dwFlags=(KEYEVENTF_EXTENDEDKEY if extended else 0) | (KEYEVENTF_KEYUP if up else 0))
        user32.SendInput(len(events), inputs, ctypes.sizeof(INPUT))

    def capture(self, hwnd: int) -> bytes:
        if user32.IsIconic(hwnd):
            raise GhostError("the window is minimised; ask KaiC to restore it, then take the screenshot")
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise GhostError("the window has no size to capture")
        screen = user32.GetDC(None)
        memory = gdi32.CreateCompatibleDC(screen)
        bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
        previous = gdi32.SelectObject(memory, bitmap)
        try:
            # PW_RENDERFULLCONTENT makes covered and GPU-drawn windows paint into the bitmap too.
            if not user32.PrintWindow(hwnd, memory, PW_RENDERFULLCONTENT):
                raise GhostError("the window would not draw itself for a screenshot")
            header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=width, biHeight=-height, biPlanes=1, biBitCount=32)
            pixels = ctypes.create_string_buffer(width * height * 4)
            gdi32.GetDIBits(memory, bitmap, 0, height, pixels, ctypes.byref(header), 0)
        finally:
            gdi32.SelectObject(memory, previous)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory)
            user32.ReleaseDC(None, screen)
        image = Image.frombuffer("RGB", (width, height), pixels.raw, "raw", "BGRX", 0, 1)
        out = io.BytesIO()
        image.save(out, "PNG")
        return out.getvalue()

    def launch(self, target: str, args: list[str]) -> int | None:
        path = Path(target)
        if path.suffix.lower() == ".exe" and path.is_file():
            # DEVNULL: the child must not inherit the MCP server's stdio pipes.
            process = subprocess.Popen(
                [str(path), *args], cwd=str(path.parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            return process.pid
        try:
            os.startfile(target, arguments=subprocess.list2cmdline(args))
        except OSError as error:
            raise GhostError(f'could not start "{target}": {error.strerror or error}') from None
        return None
