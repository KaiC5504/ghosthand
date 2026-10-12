from fakes import FakeBackend, FakeElement

from ghosthand.model import ElementInfo, GhostError, Node, Snapshot


def test_fake_backend_reports_what_the_fake_ui_holds():
    save = FakeElement("button", "Save", rid=(1, 2), actions=("press",))
    window = FakeElement("window", "Editor", rid=(1,)).add(save)
    backend = FakeBackend({100: window})
    assert backend.info(backend.root(100)).name == "Editor"
    assert backend.children(window) == [save]
    backend.perform(save, "press")
    assert save.performed == ["press"]


def test_fake_backend_sets_values_only_on_settable_fields():
    field = FakeElement("edit", "Name", settable=True)
    label = FakeElement("text", "Hello")
    backend = FakeBackend({})
    assert backend.set_value(field, "葬送的芙莉莲") and field.data.value == "葬送的芙莉莲"
    assert not backend.set_value(label, "x")


def test_snapshot_finds_nodes_by_ref():
    node = Node(info=ElementInfo(role="window"), handle=None, parent=None, depth=0, ref="e1")
    snapshot = Snapshot(hwnd=1, title="t", app="a", nodes=[node], truncated=False)
    assert snapshot.root is node
    assert snapshot.find("e1") is node and snapshot.find("e9") is None


def test_ghost_error_carries_the_message():
    assert str(GhostError("stale: read again")) == "stale: read again"
