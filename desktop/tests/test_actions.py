import pytest

from ghosthand.actions import choose, refusal
from ghosthand.model import ElementInfo, GhostError, Node


def node(*actions, name="Save", role="button"):
    return Node(info=ElementInfo(role=role, name=name, actions=actions), handle=None, parent=None, depth=1, ref="e4")


def test_auto_prefers_press_then_the_rest():
    assert choose(node("toggle", "press")) == "press"
    assert choose(node("select", "expand", "collapse")) == "select"
    assert choose(node("default"), "auto") == "default"


def test_explicit_action_must_be_supported():
    assert choose(node("expand", "collapse"), "collapse") == "collapse"
    with pytest.raises(GhostError, match='e4 cannot "toggle"; it supports: press'):
        choose(node("press"), "toggle")


def test_unknown_action_lists_the_choices():
    with pytest.raises(GhostError, match='unknown action "click"'):
        choose(node("press"), "click")


def test_nothing_mouse_free_means_needs_a_real_click():
    with pytest.raises(GhostError, match="needs a real click: e4 image"):
        choose(node(name="canvas", role="image"))


def test_refusal_codes_are_explained():
    assert "e4 is disabled right now" in refusal(0x80040200, "press", "e4")
    assert refusal(0x80040201, "press", "e4").startswith("stale: e4")
    assert "not possible on e4" in refusal(0x80131509, "press", "e4")
    assert "e4 cannot scroll further that way" in refusal(0x80131509, "scroll", "e4")
    assert "did not answer press within 2 s" in refusal(0x80131505, "press", "e4")
    odd = refusal(0x8000FFFF, "press", "e4", "Catastrophic failure")
    assert "Catastrophic failure, 0x8000FFFF" in odd and "-0x" not in odd
