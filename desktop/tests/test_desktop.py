import pytest
from fakes import FakeBackend, FakeElement, FakeWin, window_info

from ghosthand.desktop import Desktop
from ghosthand.keys import KeyStroke, parse_keys
from ghosthand.model import GhostError

EDITOR, CALC, OTHER = 100, 200, 300


def setup():
    save = FakeElement("button", "Save", rid=(1, 1), actions=("press",))
    field = FakeElement("edit", "Name", rid=(1, 2), settable=True)
    canvas = FakeElement("image", "Canvas", rid=(1, 3))
    editor = FakeElement("window", "Editor", rid=(1,)).add(save, field, canvas)
    calc = FakeElement("window", "Calculator", rid=(2,))
    win = FakeWin(
        window_info(EDITOR, "Editor - notes.txt", "notepad"),
        window_info(CALC, "Calculator", "ApplicationFrameHost"),
        window_info(OTHER, "Claude", "claude"),
    )
    win.front = OTHER
    desk = Desktop(FakeBackend({EDITOR: editor, CALC: calc}), win, sleep=lambda seconds: None)
    return desk, win, save, field, canvas, editor


def ref_of(text, name):
    return next(row.split()[0] for row in text.splitlines() if row.startswith("  ") and f'"{name}"' in row)


def test_windows_lists_and_marks_the_front_one():
    desk, *_ = setup()
    assert desk.windows().splitlines() == [
        '100 notepad "Editor - notes.txt"',
        '200 ApplicationFrameHost "Calculator"',
        '300 claude "Claude"  (in front)',
    ]


def test_window_can_be_named_by_number_app_or_title():
    desk, *_ = setup()
    assert desk.resolve("100") == EDITOR
    assert desk.resolve("notepad") == EDITOR
    assert desk.resolve("calcul") == CALC


def test_ambiguous_and_missing_windows_are_explained():
    desk, win, *_ = setup()
    win.rows.append(window_info(400, "Calculator", "ApplicationFrameHost"))
    with pytest.raises(GhostError, match='"Calculator" matches 2 windows'):
        desk.resolve("Calculator")
    with pytest.raises(GhostError, match='no open window matches "zebra"'):
        desk.resolve("zebra")
    with pytest.raises(GhostError, match="window 999 closed"):
        desk.resolve("999")


def test_act_presses_and_returns_the_fresh_window():
    desk, win, save, *_ = setup()
    ref = ref_of(desk.read("notepad"), "Save")
    out = desk.act(ref)
    assert save.performed == ["press"]
    assert out.startswith(f"press {ref}: done\nwindow 100")


def test_act_refuses_stale_and_unknown_refs():
    desk, win, save, field, canvas, editor = setup()
    ref = ref_of(desk.read("notepad"), "Save")
    editor.children.remove(save)
    with pytest.raises(GhostError, match=f"stale: {ref}"):
        desk.act(ref)
    with pytest.raises(GhostError, match="unknown ref e999"):
        desk.act("e999")
    assert save.performed == []


def test_act_without_a_mouse_free_action_never_performs():
    desk, win, save, field, canvas, editor = setup()
    with pytest.raises(GhostError, match="needs a real click"):
        desk.act(ref_of(desk.read("notepad"), "Canvas"))
    assert canvas.performed == []


def test_focus_taken_by_the_app_is_handed_back():
    desk, win, save, *_ = setup()
    save.on_perform = lambda action: setattr(win, "front", EDITOR)
    out = desk.act(ref_of(desk.read("notepad"), "Save"))
    assert win.front == OTHER
    assert "(focus handed back)" in out.splitlines()[0]


def test_focus_that_cannot_be_handed_back_is_reported():
    desk, win, save, *_ = setup()
    save.on_perform = lambda action: setattr(win, "front", EDITOR)
    win.allow_focus_change = False
    assert "would not let ghosthand hand it back" in desk.act(ref_of(desk.read("notepad"), "Save"))


def test_action_that_closes_the_window_still_reports_success():
    desk, win, save, *_ = setup()
    save.on_perform = lambda action: win.rows.pop(0)
    assert desk.act(ref_of(desk.read("notepad"), "Save")).endswith("; the window closed")


def test_window_closed_between_read_and_act():
    desk, win, *_ = setup()
    ref = ref_of(desk.read("notepad"), "Save")
    win.rows.pop(0)
    with pytest.raises(GhostError, match=f"the window holding {ref} closed"):
        desk.act(ref)


def test_set_text_fills_the_field_and_can_submit():
    desk, win, save, field, *_ = setup()
    ref = ref_of(desk.read("notepad"), "Name")
    out = desk.set_text(ref, "葬送的芙莉莲", submit=True)
    assert field.data.value == "葬送的芙莉莲"
    assert win.posted == [(EDITOR, [KeyStroke(0x0D)])]
    assert out.startswith(f"text set on {ref} and submitted")


def test_set_text_on_a_field_without_direct_text_input():
    desk, *_ = setup()
    with pytest.raises(GhostError, match="takes no direct text"):
        desk.set_text(ref_of(desk.read("notepad"), "Save"), "x")


def test_keys_go_in_the_background_but_combinations_need_permission():
    desk, win, *_ = setup()
    desk.keys("notepad", "tab enter")
    assert win.posted == [(EDITOR, parse_keys("tab enter"))]
    with pytest.raises(GhostError, match="Ask KaiC"):
        desk.keys("notepad", "ctrl+s")
    assert win.focused == []
    desk.keys("notepad", "ctrl+s", allow_focus=True)
    assert win.focused == [(EDITOR, parse_keys("ctrl+s"))]
    assert win.front == OTHER


def test_wait_for_returns_once_text_appears():
    desk, win, save, field, canvas, editor = setup()
    naps = []

    def sleep(seconds):
        naps.append(seconds)
        if len(naps) == 2:
            editor.add(FakeElement("text", "Saved", rid=(1, 9)))

    desk.sleep = sleep
    assert '"Saved"' in desk.wait_for("notepad", "saved")


def test_wait_for_times_out_with_the_reason():
    desk, *_ = setup()
    now = [0.0]
    desk.clock = lambda: now[0]
    desk.sleep = lambda seconds: now.__setitem__(0, now[0] + seconds)
    with pytest.raises(GhostError, match='timed out after 1s waiting for "Saved" to appear'):
        desk.wait_for("notepad", "Saved", timeout=1)


def test_wait_for_something_to_disappear():
    desk, win, save, field, canvas, editor = setup()
    desk.sleep = lambda seconds: editor.children.remove(canvas) if canvas in editor.children else None
    assert '"Canvas"' not in desk.wait_for("notepad", "Canvas", gone=True)


def test_launch_returns_the_new_window_and_hands_focus_back():
    desk, win, *_ = setup()
    desk.backend.windows[900] = FakeElement("window", "Kazumi", rid=(9,)).add(FakeElement("image", "card"))

    def opened():
        win.rows.append(window_info(900, "Kazumi", "kazumi", pid=4242))
        win.front = 900

    win.on_launch = opened
    out = desk.launch(r"D:\Tools\Kazumi\kazumi.exe")
    assert out.startswith("launched kazumi, window 900 (focus handed back)")
    assert win.front == OTHER


def test_launch_without_a_new_window_times_out():
    desk, *_ = setup()
    now = [0.0]
    desk.clock = lambda: now[0]
    desk.sleep = lambda seconds: now.__setitem__(0, now[0] + seconds)
    with pytest.raises(GhostError, match="no new window appeared within 2s"):
        desk.launch("kazumi.exe", timeout=2)


def test_screenshot_returns_the_window_picture():
    desk, *_ = setup()
    assert desk.screenshot("notepad") == b"\x89PNG fake 100"
