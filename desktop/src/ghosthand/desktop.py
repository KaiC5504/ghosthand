from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from ghosthand.actions import choose
from ghosthand.keys import parse_keys
from ghosthand.model import Backend, GhostError, Node, Snapshot
from ghosthand.reader import render, walk
from ghosthand.refs import RefTable

SETTLE = 0.15
SETTLE_LIMIT = 1.5
POLL = 0.25


class Desktop:
    def __init__(self, backend: Backend, win, *, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.backend = backend
        self.win = win
        self.refs = RefTable()
        self.sleep = sleep
        self.clock = clock

    def windows(self) -> str:
        rows = self.win.list_windows()
        if not rows:
            return "no windows open"
        return "\n".join(f'{row.hwnd} {row.app} "{row.title}"' + ("  (in front)" if row.front else "") for row in rows)

    def resolve(self, window: str | int) -> int:
        text = str(window).strip()
        if text.isdigit():
            hwnd = int(text)
            if not self.win.is_window(hwnd):
                raise GhostError(f"window {hwnd} closed: call windows")
            return hwnd
        rows = self.win.list_windows()
        needle = text.lower()
        hits = [row for row in rows if row.app.lower() == needle] or [row for row in rows if needle in row.title.lower()]
        if not hits:
            raise GhostError(f'no open window matches "{text}": call windows')
        if len(hits) > 1:
            listing = "; ".join(f'{row.hwnd} "{row.title}"' for row in hits[:6])
            raise GhostError(f'"{text}" matches {len(hits)} windows ({listing}); pass the number instead')
        return hits[0].hwnd

    def snapshot(self, hwnd: int) -> Snapshot:
        info = self.win.info(hwnd)
        nodes, truncated = walk(self.backend, self.backend.root(hwnd))
        snapshot = Snapshot(hwnd=hwnd, title=info.title, app=info.app, nodes=nodes, truncated=truncated)
        self.refs.assign(snapshot)
        return snapshot

    def read(self, window: str | int, ref: str | None = None, query: str | None = None) -> str:
        snapshot = self.snapshot(self.resolve(window))
        if ref:
            node = snapshot.find(ref) or self.refs.rebind(snapshot, ref)
            if node is None:
                raise GhostError(f"stale: {ref} is no longer on screen. Read the window again.")
            snapshot = self._subtree(snapshot, node)
        return render(snapshot, query=query, subtree=ref)

    def _subtree(self, snapshot: Snapshot, node: Node) -> Snapshot:
        # A fresh walk from the element, with its own element budget, reaches what a whole-window
        # read cut off; the top keeps its place in the tree so every ref stays the same.
        nodes, truncated = walk(self.backend, node.handle)
        top = nodes[0]
        top.parent, top.sibling_index, top.info = node.parent, node.sibling_index, node.info
        part = Snapshot(hwnd=snapshot.hwnd, title=snapshot.title, app=snapshot.app, nodes=nodes, truncated=truncated)
        self.refs.assign(part)
        return part

    def act(self, ref: str, action: str = "auto") -> str:
        snapshot, node = self._node(ref)
        chosen = choose(node, action)
        note = self._guarded(snapshot.hwnd, lambda: self.backend.perform(node.handle, chosen))
        return self._after(snapshot.hwnd, f"{chosen} {ref}: done", note)

    def set_text(self, ref: str, text: str, submit: bool = False) -> str:
        snapshot, node = self._node(ref)

        def work() -> None:
            if not self.backend.set_value(node.handle, text):
                raise GhostError(f"{ref} {node.info.role} takes no direct text. Ask the user before using keys with allow_focus.")
            if submit:
                self.win.post_keys(snapshot.hwnd, parse_keys("enter"))

        note = self._guarded(snapshot.hwnd, work)
        return self._after(snapshot.hwnd, f"text set on {ref}" + (" and submitted" if submit else ""), note)

    def keys(self, window: str | int, keys: str, allow_focus: bool = False) -> str:
        hwnd = self.resolve(window)
        strokes = parse_keys(keys)
        if allow_focus:
            note = self._guarded(hwnd, lambda: self.win.send_keys_focused(hwnd, strokes))
        else:
            if any(stroke.modifiers for stroke in strokes):
                raise GhostError(
                    "ctrl/alt/shift/win combinations only work with the window in front. "
                    "Ask the user, then call keys again with allow_focus=true."
                )
            note = self._guarded(hwnd, lambda: self.win.post_keys(hwnd, strokes))
        return self._after(hwnd, f"sent {keys}", note)

    def wait_for(self, window: str | int, text: str, gone: bool = False, timeout: float = 10.0) -> str:
        hwnd = self.resolve(window)
        needle = text.lower()

        def holds(snapshot: Snapshot) -> bool:
            return any(needle in f"{node.info.name} {node.info.value or ''}".lower() for node in snapshot.nodes) != gone

        deadline = self.clock() + timeout
        while True:
            snapshot = self.snapshot(hwnd)
            if holds(snapshot):
                return render(self._settled(hwnd, snapshot, holds))
            if self.clock() >= deadline:
                raise GhostError(f'timed out after {timeout:g}s waiting for "{text}" to {"disappear" if gone else "appear"}')
            self.sleep(POLL)

    def _settled(self, hwnd: int, snapshot: Snapshot, holds: Callable[[Snapshot], bool]) -> Snapshot:
        # A page that is still animating in hands out refs whose elements are about to move or be
        # re-wrapped, so wait until the usable elements stay put between two reads.
        deadline = self.clock() + SETTLE_LIMIT
        while self.clock() < deadline:
            self.sleep(SETTLE)
            again = self.snapshot(hwnd)
            if not holds(again):
                return snapshot
            if _layout(again) == _layout(snapshot):
                return again
            snapshot = again
        return snapshot

    def launch(self, target: str, args: Sequence[str] = (), timeout: float = 20.0) -> str:
        before = {row.hwnd for row in self.win.list_windows()}
        front = self.win.foreground()
        pid = self.win.launch(target, list(args))
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            fresh = [row for row in self.win.list_windows() if row.hwnd not in before]
            mine = [row for row in fresh if pid is None or row.pid == pid] or fresh
            if mine:
                self.sleep(SETTLE)
                return self._after(mine[0].hwnd, f"launched {mine[0].app}, window {mine[0].hwnd}", self._hand_back(front, mine[0].hwnd))
            self.sleep(POLL)
        raise GhostError(f'started "{target}" but no new window appeared within {timeout:g}s: call windows')

    def screenshot(self, window: str | int) -> bytes:
        return self.win.capture(self.resolve(window))

    def _node(self, ref: str) -> tuple[Snapshot, Node]:
        hwnd = self.refs.window_of(ref)
        if hwnd is None:
            raise GhostError(f"unknown ref {ref}: read the window first")
        if not self.win.is_window(hwnd):
            raise GhostError(f"the window holding {ref} closed: call windows")
        snapshot = self.snapshot(hwnd)
        node = snapshot.find(ref) or self.refs.rebind(snapshot, ref)
        if node is None:
            raise GhostError(f"stale: {ref} is no longer on screen. Read the window again.")
        return snapshot, node

    def _guarded(self, hwnd: int, work: Callable[[], None]) -> str:
        front = self.win.foreground()
        try:
            work()
        except GhostError:
            # OK and Close buttons can tear their window down mid-call, and the app then reports an error.
            if self.win.is_window(hwnd):
                raise
        self.sleep(SETTLE)
        return self._hand_back(front, hwnd)

    def _hand_back(self, front: int, target: int) -> str:
        # Apps such as Kazumi pull themselves forward when used; the user's window gets focus back.
        # If something else is in front, the user switched windows themselves and stays there.
        now = self.win.foreground()
        if not front or front == target or now == front or not self._same_app(now, target):
            return ""
        if self.win.set_foreground(front):
            return "focus handed back"
        return "the app took focus and Windows would not let ghosthand hand it back"

    def _same_app(self, a: int, b: int) -> bool:
        if a == b:
            return True
        if not (a and self.win.is_window(a) and self.win.is_window(b)):
            return False
        return self.win.info(a).pid == self.win.info(b).pid

    def _after(self, hwnd: int, headline: str, note: str) -> str:
        if note:
            headline += f" ({note})"
        if not self.win.is_window(hwnd):
            return f"{headline}; the window closed"
        return f"{headline}\n{render(self._settled(hwnd, self.snapshot(hwnd), lambda snapshot: True))}"


def _layout(snapshot: Snapshot) -> list[tuple]:
    return [(node.key, node.info.rect) for node in snapshot.nodes if node.info.actions]
