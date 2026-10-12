import pytest

from ghosthand.actions import choose
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
