import pytest

from ghosthand.keys import KeyStroke, key_lparam, parse_keys, utf16_units
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


def test_punctuation_by_character_and_by_name():
    assert parse_keys("/ slash , period") == [KeyStroke(0xBF), KeyStroke(0xBF), KeyStroke(0xBC), KeyStroke(0xBE)]
    assert parse_keys("ctrl+/") == [KeyStroke(0xBF, (0x11,))]


def test_shifted_characters_carry_shift():
    assert parse_keys("? :") == [KeyStroke(0xBF, (0x10,)), KeyStroke(0xBA, (0x10,))]
    assert parse_keys("plus") == [KeyStroke(0xBB, (0x10,))]


def test_text_that_is_not_a_key_points_to_set_text():
    with pytest.raises(GhostError, match='"中" is not a key; to type text into a field use set_text'):
        parse_keys("中")
    with pytest.raises(GhostError, match=r'write the \+ key as "plus"'):
        parse_keys("+")


def test_text_is_sent_as_utf16_units():
    assert utf16_units("a冰😀") == [0x61, 0x51B0, 0xD83D, 0xDE00]
