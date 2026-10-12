from __future__ import annotations

from ghosthand.model import Node, Snapshot


def identity(node: Node) -> tuple:
    info = node.info
    if info.runtime_id:
        return ("rid", info.runtime_id)
    # Flutter elements have no runtime id, so they are known by where they sit and what they are.
    parent_key = node.parent.key if node.parent else ()
    return ("fp", parent_key, info.role, info.name, info.automation_id, node.sibling_index)


class RefTable:
    """Gives each element a short ref that stays the same for as long as the element exists."""

    def __init__(self) -> None:
        self._by_key: dict[tuple, str] = {}
        self._window: dict[str, int] = {}

    def assign(self, snapshot: Snapshot) -> None:
        # Reading order puts parents first, so a parent's key exists before its children need it.
        for node in snapshot.nodes:
            node.key = identity(node)
            full_key = (snapshot.hwnd, node.key)
            ref = self._by_key.get(full_key)
            if ref is None:
                ref = f"e{len(self._by_key) + 1}"
                self._by_key[full_key] = ref
                self._window[ref] = snapshot.hwnd
            node.ref = ref

    def window_of(self, ref: str) -> int | None:
        return self._window.get(ref)
