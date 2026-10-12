from __future__ import annotations

import asyncio
import ctypes
from concurrent.futures import ThreadPoolExecutor

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ghosthand.desktop import Desktop
from ghosthand.model import GhostError

INSTRUCTIONS = (
    "Mouse-free control of Windows apps. Call read on a window, then act/set_text on the refs it "
    "shows; each action returns the window's fresh state. Use wait_for instead of sleeping. "
    "ghosthand never moves the mouse: on 'needs a real click', take a screenshot and tell KaiC."
)

server = MCPServer("ghosthand", instructions=INSTRUCTIONS)
_desktop: Desktop | None = None


def _start_com() -> None:
    import comtypes

    comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)


# COM objects belong to the thread that made them, and the SDK runs each call on whichever
# worker thread is free, so every UI Automation call goes through this one thread.
_uia_thread = ThreadPoolExecutor(max_workers=1, initializer=_start_com, thread_name_prefix="uia")


def _make_desktop() -> Desktop:
    from ghosthand.uia import UiaBackend
    from ghosthand.win32 import Win32

    return Desktop(UiaBackend(), Win32())


async def _call(method: str, *args):
    def work():
        global _desktop
        if _desktop is None:
            _desktop = _make_desktop()
        return getattr(_desktop, method)(*args)

    try:
        return await asyncio.get_running_loop().run_in_executor(_uia_thread, work)
    except GhostError as error:
        raise ToolError(str(error)) from None


@server.tool()
async def windows() -> str:
    """List open windows: number, app, title, and which one is in front."""
    return await _call("windows")


@server.tool()
async def launch(target: str, args: list[str] | None = None, timeout: float = 20.0) -> str:
    """Start an app (an .exe path, a name like notepad, or a URI like calculator:) and read its new window."""
    return await _call("launch", target, args or [], timeout)


@server.tool()
async def read(window: str, ref: str | None = None, query: str | None = None) -> str:
    """Read one window, one line per element: e12 button "Save" [press].

    window is a number from windows, an app name or part of a title. ref reads only that
    element's subtree; query lists only elements whose text contains it.
    """
    return await _call("read", window, ref, query)


@server.tool()
async def act(ref: str, action: str = "auto") -> str:
    """Use an element without the mouse. auto picks press, toggle, select, expand or default. Returns the fresh window."""
    return await _call("act", ref, action)


@server.tool()
async def set_text(ref: str, text: str, submit: bool = False) -> str:
    """Put text straight into a field; submit=true then presses Enter in the background."""
    return await _call("set_text", ref, text, submit)


@server.tool()
async def keys(window: str, keys: str, allow_focus: bool = False) -> str:
    """Send keys such as "enter", "tab tab", "f5" in the background.

    Combinations like ctrl+s need allow_focus=true, which brings the window to the front:
    ask KaiC before using it.
    """
    return await _call("keys", window, keys, allow_focus)


@server.tool()
async def wait_for(window: str, text: str, gone: bool = False, timeout: float = 10.0) -> str:
    """Wait until text appears in a window (or disappears with gone=true), then return the fresh window."""
    return await _call("wait_for", window, text, gone, timeout)


@server.tool()
async def screenshot(window: str) -> Image:
    """A picture of one window, even when other windows cover it."""
    return Image(data=await _call("screenshot", window), format="png")


def main() -> None:
    # Physical pixels everywhere, so element positions and screenshots match the screen.
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    server.run("stdio")
