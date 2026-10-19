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

SHIFT = 0x10
# Punctuation as it sits on a US keyboard: (virtual key, needs shift).
CHARACTERS = {
    "`": (0xC0, False), "-": (0xBD, False), "=": (0xBB, False), "[": (0xDB, False), "]": (0xDD, False),
    "\\": (0xDC, False), ";": (0xBA, False), "'": (0xDE, False), ",": (0xBC, False), ".": (0xBE, False), "/": (0xBF, False),
    "~": (0xC0, True), "_": (0xBD, True), "+": (0xBB, True), "{": (0xDB, True), "}": (0xDD, True),
    "|": (0xDC, True), ":": (0xBA, True), '"': (0xDE, True), "<": (0xBC, True), ">": (0xBE, True), "?": (0xBF, True),
}
CHARACTERS.update({symbol: (ord(digit), True) for symbol, digit in zip("!@#$%^&*()", "1234567890")})
CHARACTERS.update({
    name: CHARACTERS[symbol] for name, symbol in {
        "slash": "/", "backslash": "\\", "comma": ",", "period": ".", "minus": "-", "equals": "=", "semicolon": ";",
        "quote": "'", "backquote": "`", "bracketleft": "[", "bracketright": "]", "plus": "+",
    }.items()
})


@dataclass(frozen=True)
class KeyStroke:
    vk: int
    modifiers: tuple[int, ...] = ()
    extended: bool = False


def parse_keys(spec: str) -> list[KeyStroke]:
    strokes = []
    for token in spec.split():
        if token == "+" or token.endswith("++"):
            raise GhostError('write the + key as "plus"')
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
        elif key in CHARACTERS:
            vk, shifted = CHARACTERS[key]
            extended = False
            if shifted and SHIFT not in modifiers:
                modifiers.insert(0, SHIFT)
        elif len(key) == 1:
            raise GhostError(f'"{key}" is not a key; to type text into a field use set_text')
        else:
            raise GhostError(f'unknown key "{key}" in "{token}"; use a letter, a digit or a name like enter, tab, esc, up, f5')
        strokes.append(KeyStroke(vk, tuple(modifiers), extended))
    if not strokes:
        raise GhostError("no keys given")
    return strokes


def utf16_units(text: str) -> list[int]:
    data = text.encode("utf-16-le")
    return [int.from_bytes(data[index : index + 2], "little") for index in range(0, len(data), 2)]


def key_lparam(scan: int, extended: bool, up: bool) -> int:
    value = 1 | (scan << 16) | (int(extended) << 24)
    if up:
        value |= (1 << 30) | (1 << 31)
    return value
