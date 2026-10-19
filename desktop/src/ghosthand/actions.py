from __future__ import annotations

from ghosthand.model import GhostError, Node

AUTO_ORDER = ("press", "toggle", "select", "expand", "default")
SCROLLS = ("scroll", "scroll_up")
ALL_ACTIONS = AUTO_ORDER + ("collapse",) + SCROLLS


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


def scroll_target(node: Node) -> Node | None:
    current: Node | None = node
    while current is not None and "scroll" not in current.info.actions:
        current = current.parent
    return current


UIA_E_ELEMENTNOTENABLED = 0x80040200
UIA_E_ELEMENTNOTAVAILABLE = 0x80040201
UIA_E_INVALIDOPERATION = 0x80131509
UIA_E_TIMEOUT = 0x80131505
# set_text refusals that typing would not get past.
NOT_TYPED_INTO = (UIA_E_ELEMENTNOTENABLED, UIA_E_ELEMENTNOTAVAILABLE, UIA_E_TIMEOUT)


def refusal(code: int, action: str, ref: str, text: str = "") -> str:
    if code == UIA_E_ELEMENTNOTENABLED:
        return f"{ref} is disabled right now, so {action} did nothing. Read the window to see what it waits for (a required field, loading)."
    if code == UIA_E_ELEMENTNOTAVAILABLE:
        return f"stale: {ref} went away during {action}. Read the window again."
    if code == UIA_E_INVALIDOPERATION:
        if action in SCROLLS:
            return f"{ref} cannot scroll further that way."
        return f"the app says {action} is not possible on {ref} in its current state. Read the window again."
    if code == UIA_E_TIMEOUT:
        return f"the app did not answer {action} within 2 s; it may be busy. Wait, then read the window again."
    detail = f"{text}, 0x{code:08X}" if text else f"0x{code:08X}"
    return f"{action} failed: the app refused it ({detail}). Read the window again."
