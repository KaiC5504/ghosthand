import pytest
from fakes import FakeBackend, FakeElement

from ghosthand.model import GhostError, Snapshot
from ghosthand.reader import MAX_NODES, render, walk
from ghosthand.refs import RefTable


def snapshot_of(window, hwnd=5, title="Editor", app="notepad"):
    nodes, truncated = walk(FakeBackend({hwnd: window}), window)
    snapshot = Snapshot(hwnd=hwnd, title=title, app=app, nodes=nodes, truncated=truncated)
    RefTable().assign(snapshot)
    return snapshot


def test_render_folds_wrappers_and_lists_actions():
    window = FakeElement("window", "Editor", rid=(1,)).add(
        FakeElement("pane", rid=(2,)).add(FakeElement("group", rid=(3,)).add(FakeElement("button", "Save", rid=(4,), actions=("press",)))),
        FakeElement("text", "Ready", rid=(5,)),
    )
    assert render(snapshot_of(window)) == 'window 5 "Editor" (notepad)\n  e4 button "Save" [press]\n  e5 text "Ready"'


def test_render_shows_values_and_positions_of_unnamed_controls():
    window = FakeElement("window", "Chrome", rid=(1,)).add(
        FakeElement("edit", "Address and search bar", rid=(2,), value="https://example.com/"),
        FakeElement("button", rid=(3,), actions=("press",), rect=(219, 27, 276, 84)),
    )
    text = render(snapshot_of(window, title="Chrome", app="chrome"))
    assert 'e2 edit "Address and search bar" = "https://example.com/"' in text
    assert "e3 button @219,27 [press]" in text


def test_render_cleans_newlines_and_long_names():
    window = FakeElement("window", "Kazumi", rid=(1,)).add(
        FakeElement("text", "概览\n第 1 个标签，共 5 个"), FakeElement("text", "x" * 300)
    )
    text = render(snapshot_of(window))
    assert '"概览 第 1 个标签，共 5 个"' in text
    assert "x" * 119 + "…" in text and "x" * 121 not in text


def test_query_lists_only_matching_elements():
    window = FakeElement("window", "Calc", rid=(1,)).add(
        FakeElement("button", "Seven", rid=(2,), actions=("press",)), FakeElement("text", "Display is 42", rid=(3,))
    )
    assert render(snapshot_of(window), query="display") == 'window 5 "Editor" (notepad)\n  e3 text "Display is 42"'
    assert 'nothing matches "zebra"' in render(snapshot_of(window), query="zebra")


def test_subtree_starts_at_the_ref():
    window = FakeElement("window", "Editor", rid=(1,)).add(
        FakeElement("group", "Toolbar", rid=(2,)).add(FakeElement("button", "Save", rid=(3,), actions=("press",))),
        FakeElement("text", "Ready", rid=(4,)),
    )
    assert render(snapshot_of(window), subtree="e2") == 'window 5 "Editor" (notepad)\n  e2 group "Toolbar"\n    e3 button "Save" [press]'


def test_unknown_subtree_ref_is_stale():
    with pytest.raises(GhostError, match="stale: e9"):
        render(snapshot_of(FakeElement("window", "Editor", rid=(1,))), subtree="e9")


def test_cut_short_read_says_so():
    window = FakeElement("window", "Huge", rid=(1,)).add(*[FakeElement("text", f"row {i}", rid=(3, i)) for i in range(MAX_NODES + 1)])
    assert render(snapshot_of(window)).endswith("read again with one of the refs above to see that part in full)")


def test_render_says_when_part_of_the_window_did_not_answer():
    pane = FakeElement("pane", rid=(2,)).add(FakeElement("button", "Save", rid=(3,), actions=("press",)))
    pane.fails = "0x80040201"
    text = render(snapshot_of(FakeElement("window", "Kazumi", rid=(1,)).add(pane)))
    assert 'e3 button "Save" [press]' in text
    assert "did not answer (0x80040201)" in text and "screenshot" in text


def test_render_of_a_whole_answer_has_no_warning():
    window = FakeElement("window", "Editor", rid=(1,)).add(FakeElement("text", "Ready", rid=(2,)))
    assert "did not answer" not in render(snapshot_of(window))
