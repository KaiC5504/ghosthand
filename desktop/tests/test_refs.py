from dataclasses import replace

from fakes import FakeBackend, FakeElement

from ghosthand.model import Snapshot
from ghosthand.reader import walk
from ghosthand.refs import RefTable


def read(table, backend, hwnd):
    nodes, truncated = walk(backend, backend.root(hwnd))
    snapshot = Snapshot(hwnd=hwnd, title="t", app="a", nodes=nodes, truncated=truncated)
    table.assign(snapshot)
    return snapshot


def ref_of(snapshot, name):
    return next(node.ref for node in snapshot.nodes if node.info.name == name)


def test_element_with_runtime_id_keeps_its_ref_when_the_ui_changes():
    save = FakeElement("button", "Save", rid=(1, 5))
    window = FakeElement("window", "Editor", rid=(1,)).add(save)
    backend, table = FakeBackend({7: window}), RefTable()
    first = ref_of(read(table, backend, 7), "Save")
    window.children.insert(0, FakeElement("text", "Unsaved changes", rid=(1, 9)))
    assert ref_of(read(table, backend, 7), "Save") == first


def test_flutter_elements_keep_refs_across_reads():
    window = FakeElement("window", "Kazumi", rid=(1,)).add(
        FakeElement("pane").add(FakeElement("image", "药屋少女的呢喃"), FakeElement("button", "历史记录", actions=("press",)))
    )
    backend, table = FakeBackend({3: window}), RefTable()
    first, second = read(table, backend, 3), read(table, backend, 3)
    assert [node.ref for node in first.nodes] == [node.ref for node in second.nodes]


def test_removed_element_is_no_longer_found():
    card = FakeElement("image", "card")
    window = FakeElement("window", "Kazumi", rid=(1,)).add(card)
    backend, table = FakeBackend({3: window}), RefTable()
    ref = ref_of(read(table, backend, 3), "card")
    window.children.remove(card)
    assert read(table, backend, 3).find(ref) is None


def test_renamed_element_without_id_gets_a_new_ref():
    label = FakeElement("text", "Display is 0")
    window = FakeElement("window", "Calc", rid=(1,)).add(label)
    backend, table = FakeBackend({3: window}), RefTable()
    old = ref_of(read(table, backend, 3), "Display is 0")
    label.data = replace(label.data, name="Display is 42")
    snapshot = read(table, backend, 3)
    assert snapshot.find(old) is None and ref_of(snapshot, "Display is 42") != old


def test_refs_are_unique_across_windows_and_remember_their_window():
    a = FakeElement("window", "A", rid=(1,)).add(FakeElement("button", "OK", rid=(1, 1)))
    b = FakeElement("window", "B", rid=(2,)).add(FakeElement("button", "OK", rid=(1, 1)))
    backend, table = FakeBackend({10: a, 20: b}), RefTable()
    in_a, in_b = ref_of(read(table, backend, 10), "OK"), ref_of(read(table, backend, 20), "OK")
    assert in_a != in_b
    assert table.window_of(in_a) == 10 and table.window_of(in_b) == 20 and table.window_of("e999") is None
