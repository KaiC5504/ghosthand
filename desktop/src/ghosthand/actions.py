from __future__ import annotations

from ghosthand.model import GhostError, Node

AUTO_ORDER = ("press", "toggle", "select", "expand", "default")
ALL_ACTIONS = AUTO_ORDER + ("collapse",)


def choose(node: Node, requested: str = "auto") -> str:
    supported = node.info.actions
    if requested == "auto":
        for action in AUTO_ORDER:
            if action in supported:
                return action
        raise GhostError(
            f'needs a real click: {node.ref} {node.info.role} "{node.info.name}" has no mouse-free action. '
            "Take a screenshot and tell the user; ghosthand never moves the mouse."
        )
    if requested not in ALL_ACTIONS:
        raise GhostError(f'unknown action "{requested}"; use one of: auto, {", ".join(ALL_ACTIONS)}')
    if requested not in supported:
        raise GhostError(f'{node.ref} cannot "{requested}"; it supports: {", ".join(supported) or "nothing"}')
    return requested
