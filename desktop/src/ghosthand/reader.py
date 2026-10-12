from __future__ import annotations

from ghosthand.model import Backend, ElementInfo, GhostError, Node, Snapshot

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


CONTAINER_ROLES = {"group", "pane", "custom"}
NAME_LIMIT = 120


def folded(node: Node) -> bool:
    info = node.info
    if node.parent is None or info.name or info.value:
        return False
    actions = set(info.actions)
    return not actions or (actions <= {"default"} and info.role in CONTAINER_ROLES)


def clean(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= NAME_LIMIT else text[: NAME_LIMIT - 1] + "…"


def line(node: Node, indent: int) -> str:
    info = node.info
    parts = [f"{'  ' * indent}{node.ref} {info.role}"]
    if info.name:
        parts.append(f'"{clean(info.name)}"')
    elif info.actions:
        # Unnamed controls such as Kazumi's back arrow are told apart by where they are.
        parts.append(f"@{info.rect[0]},{info.rect[1]}")
    if info.value and info.value != info.name:
        parts.append(f'= "{clean(info.value)}"')
    if info.actions:
        parts.append(f"[{', '.join(info.actions)}]")
    return " ".join(parts)


def render(snapshot: Snapshot, *, query: str | None = None, subtree: str | None = None) -> str:
    lines = [f'window {snapshot.hwnd} "{clean(snapshot.title)}" ({snapshot.app})']
    top = snapshot.root
    if subtree:
        top = snapshot.find(subtree)
        if top is None:
            raise GhostError(f"stale: {subtree} is no longer on screen. Read the window again.")
    nodes = preorder(top)
    if query:
        needle = query.lower()
        hits = [node for node in nodes if needle in f"{node.info.name} {node.info.value or ''}".lower()]
        lines += [line(node, 1) for node in hits] or [f'  nothing matches "{query}"']
    else:
        level = {id(top): 0}
        if subtree:
            lines.append(line(top, 1))
            level[id(top)] = 1
        for node in nodes[1:]:
            depth = level[id(node.parent)]
            if not folded(node):
                depth += 1
                lines.append(line(node, depth))
            level[id(node)] = depth
    if snapshot.truncated:
        lines.append(f"(read stopped early: over {MAX_NODES} elements or {MAX_DEPTH} levels; read a subtree ref or use query)")
    return "\n".join(lines)
