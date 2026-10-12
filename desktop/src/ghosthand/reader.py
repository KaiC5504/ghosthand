from __future__ import annotations

from ghosthand.model import Backend, ElementInfo, Node

MAX_DEPTH = 64
MAX_NODES = 2000


def walk(backend: Backend, root: object, *, max_depth: int = MAX_DEPTH, max_nodes: int = MAX_NODES) -> tuple[list[Node], bool]:
    """Read the tree under root; returns the nodes in reading order and whether a cap cut it short."""
    top = Node(info=backend.info(root), handle=root, parent=None, depth=0)
    seen_runtime_ids = {top.info.runtime_id} if top.info.runtime_id else set()
    count = 1
    truncated = False
    pending = [top]
    while pending:
        node = pending.pop()
        handles = backend.children(node.handle)
        if handles and node.depth >= max_depth:
            truncated = True
            continue
        siblings: dict[tuple, int] = {}
        added = []
        for handle in handles:
            if count >= max_nodes:
                truncated = True
                break
            info = backend.info(handle)
            if _loops_back(backend, info, handle, node, seen_runtime_ids):
                continue
            kind = (info.role, info.name, info.automation_id)
            child = Node(info=info, handle=handle, parent=node, depth=node.depth + 1, sibling_index=siblings.get(kind, 0))
            siblings[kind] = child.sibling_index + 1
            if info.runtime_id:
                seen_runtime_ids.add(info.runtime_id)
            node.children.append(child)
            added.append(child)
            count += 1
        # First child next, so when the element cap hits, it cuts the end of the window.
        pending.extend(reversed(added))
    return preorder(top), truncated


def _loops_back(backend: Backend, info: ElementInfo, handle: object, parent: Node, seen_runtime_ids: set) -> bool:
    # Chrome tooltips point back at their own window. Flutter elements have no runtime id,
    # so for those the only proof of a loop is UIA saying the element is one of its ancestors.
    if info.runtime_id:
        return info.runtime_id in seen_runtime_ids
    ancestor = parent
    while ancestor is not None:
        if ancestor.info == info and backend.same(ancestor.handle, handle):
            return True
        ancestor = ancestor.parent
    return False


def preorder(node: Node) -> list[Node]:
    ordered, stack = [], [node]
    while stack:
        current = stack.pop()
        ordered.append(current)
        stack.extend(reversed(current.children))
    return ordered
