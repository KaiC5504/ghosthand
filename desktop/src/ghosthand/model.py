from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class GhostError(Exception):
    """A failure whose message tells Claude what happened and what to do next."""


@dataclass(frozen=True)
class ElementInfo:
    role: str
    name: str = ""
    automation_id: str = ""
    runtime_id: tuple[int, ...] | None = None
    rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    actions: tuple[str, ...] = ()
    value: str | None = None


@dataclass(eq=False)
class Node:
    info: ElementInfo
    handle: object
    parent: Node | None
    depth: int
    sibling_index: int = 0
    children: list[Node] = field(default_factory=list)
    key: tuple = ()
    ref: str = ""


@dataclass(eq=False)
class Snapshot:
    hwnd: int
    title: str
    app: str
    nodes: list[Node]
    truncated: bool

    @property
    def root(self) -> Node:
        return self.nodes[0]

    def find(self, ref: str) -> Node | None:
        return next((node for node in self.nodes if node.ref == ref), None)


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    app: str
    pid: int
    front: bool = False


class Backend(Protocol):
    def root(self, hwnd: int) -> object: ...
    def info(self, element: object) -> ElementInfo: ...
    def children(self, element: object) -> list[object]: ...
    def perform(self, element: object, action: str) -> None: ...
    def set_value(self, element: object, text: str) -> bool: ...
