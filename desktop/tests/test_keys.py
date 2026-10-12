import pytest

from ghosthand.keys import KeyStroke, key_lparam, parse_keys
from ghosthand.model import GhostError


def test_named_keys_letters_digits_and_function_keys():
    assert parse_keys("enter tab f5 a 7") == [KeyStroke(0x0D), KeyStroke(0x09), KeyStroke(0x74), KeyStroke(ord("A")), KeyStroke(ord("7"))]


def test_arrows_are_extended_keys():
    assert parse_keys("up") == [KeyStroke(0x26, extended=True)]


def test_combinations_carry_modifiers():
    assert parse_keys("ctrl+shift+t") == [KeyStroke(ord("T"), (0x11, 0x10))]


def test_bad_keys_say_what_to_use():
    with pytest.raises(GhostError, match='unknown key "boom"'):
        parse_keys("boom")
    with pytest.raises(GhostError, match='unknown modifier "hyper"'):
        parse_keys("hyper+a")
    with pytest.raises(GhostError, match="no keys given"):
        parse_keys("   ")


def test_lparam_bits():
    assert key_lparam(0x1C, extended=False, up=False) == 1 | (0x1C << 16)
    up = key_lparam(0x48, extended=True, up=True)
    assert up & (1 << 24) and up & (1 << 30) and up & (1 << 31)
