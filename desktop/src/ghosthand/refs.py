from __future__ import annotations

from ghosthand.model import ElementInfo, Node, Snapshot

NEAR = 8
KEEP_READS = 64


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
        self._read_of: dict[str, int] = {}
        self._reads: dict[int, set[str]] = {}
        self._history: dict[int, list[int]] = {}
        self._count = 0

    def assign(self, snapshot: Snapshot) -> None:
        self._count += 1
        present: set[str] = set()
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
            self._seen[ref] = node.info
            self._read_of[ref] = self._count
            present.add(ref)
        self._reads[self._count] = present
        self._reads.pop(self._count - KEEP_READS, None)
        self._history[snapshot.hwnd] = self._history.get(snapshot.hwnd, [])[-1:] + [self._count]

    def rebind(self, snapshot: Snapshot, ref: str) -> Node | None:
        """Gives a ref back to its element when only the element's ancestors changed.

        Flutter rebuilds the wrappers above a page while it animates in. Only an element that was
        never on screen together with the old one, alike in its own properties, at the same place
        and size, and the only such one counts, and only if the old one was in the window's
        previous read, so a ref from a page left long ago never lands on a later page.
        """
        last = self._seen.get(ref)
        seen_in = self._read_of.get(ref, 0)
        together = self._reads.get(seen_in)
        if last is None or last.runtime_id or together is None or seen_in not in self._history.get(snapshot.hwnd, []):
            return None
        matches = [
            node for node in snapshot.nodes
            if node.ref not in together
            and node.info.runtime_id is None
            and (node.info.role, node.info.name, node.info.automation_id) == (last.role, last.name, last.automation_id)
            and abs(node.info.rect[0] - last.rect[0]) <= NEAR
            and abs(node.info.rect[1] - last.rect[1]) <= NEAR
            and abs((node.info.rect[2] - node.info.rect[0]) - (last.rect[2] - last.rect[0])) <= NEAR
            and abs((node.info.rect[3] - node.info.rect[1]) - (last.rect[3] - last.rect[1])) <= NEAR
        ]
        if len(matches) != 1:
            return None
        node = matches[0]
        self._by_key[(snapshot.hwnd, node.key)] = ref
        self._reads[self._count].add(ref)
        node.ref = ref
        self._seen[ref] = node.info
        self._read_of[ref] = self._count
        return node

    def window_of(self, ref: str) -> int | None:
        return self._window.get(ref)
