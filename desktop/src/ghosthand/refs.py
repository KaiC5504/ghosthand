from __future__ import annotations

from ghosthand.model import ElementInfo, Node, Snapshot

NEAR = 8


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
        self._seen: dict[str, ElementInfo] = {}
        self._new: set[str] = set()

    def assign(self, snapshot: Snapshot) -> None:
        self._new = set()
        # Reading order puts parents first, so a parent's key exists before its children need it.
        for node in snapshot.nodes:
            node.key = identity(node)
            full_key = (snapshot.hwnd, node.key)
            ref = self._by_key.get(full_key)
            if ref is None:
                ref = f"e{len(self._by_key) + 1}"
                self._by_key[full_key] = ref
                self._window[ref] = snapshot.hwnd
                self._new.add(ref)
            node.ref = ref
            self._seen[ref] = node.info

    def rebind(self, snapshot: Snapshot, ref: str) -> Node | None:
        """Gives a ref back to its element when only the element's ancestors changed.

        Flutter rebuilds the wrappers above a page while it animates in. Only an element first seen
        in this read, alike in its own properties, at the same place, and the only such one counts.
        """
        last = self._seen.get(ref)
        if last is None or last.runtime_id:
            return None
        matches = [
            node for node in snapshot.nodes
            if node.ref in self._new
            and node.info.runtime_id is None
            and (node.info.role, node.info.name, node.info.automation_id) == (last.role, last.name, last.automation_id)
            and abs(node.info.rect[0] - last.rect[0]) <= NEAR
            and abs(node.info.rect[1] - last.rect[1]) <= NEAR
        ]
        if len(matches) != 1:
            return None
        node = matches[0]
        self._new.discard(node.ref)
        self._window.pop(node.ref, None)
        self._by_key[(snapshot.hwnd, node.key)] = ref
        node.ref = ref
        self._seen[ref] = node.info
        return node

    def window_of(self, ref: str) -> int | None:
        return self._window.get(ref)
