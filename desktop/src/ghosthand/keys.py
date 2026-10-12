from __future__ import annotations

from dataclasses import dataclass

from ghosthand.model import GhostError

MODIFIERS = {"ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B}
NAMED = {
    "enter": (0x0D, False), "return": (0x0D, False), "tab": (0x09, False), "esc": (0x1B, False),
    "escape": (0x1B, False), "backspace": (0x08, False), "space": (0x20, False),
    "delete": (0x2E, True), "insert": (0x2D, True), "home": (0x24, True), "end": (0x23, True),
    "pageup": (0x21, True), "pagedown": (0x22, True),
    "up": (0x26, True), "down": (0x28, True), "left": (0x25, True), "right": (0x27, True),
}
NAMED.update({f"f{number}": (0x6F + number, False) for number in range(1, 13)})


@dataclass(frozen=True)
class KeyStroke:
    vk: int
    modifiers: tuple[int, ...] = ()
    extended: bool = False


def parse_keys(spec: str) -> list[KeyStroke]:
    strokes = []
    for token in spec.split():
        *mods, key = token.lower().split("+")
        modifiers = []
        for mod in mods:
            if mod not in MODIFIERS:
                raise GhostError(f'unknown modifier "{mod}" in "{token}"; use ctrl, shift, alt or win')
            modifiers.append(MODIFIERS[mod])
        if key in NAMED:
            vk, extended = NAMED[key]
        elif len(key) == 1 and key.isascii() and key.isalnum():
            vk, extended = ord(key.upper()), False
        else:
            raise GhostError(f'unknown key "{key}" in "{token}"; use a letter, a digit or a name like enter, tab, esc, up, f5')
        strokes.append(KeyStroke(vk, tuple(modifiers), extended))
    if not strokes:
        raise GhostError("no keys given")
    return strokes


def key_lparam(scan: int, extended: bool, up: bool) -> int:
    value = 1 | (scan << 16) | (int(extended) << 24)
    if up:
        value |= (1 << 30) | (1 << 31)
    return value
