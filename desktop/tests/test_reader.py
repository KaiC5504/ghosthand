from fakes import FakeBackend, FakeElement

from ghosthand.reader import MAX_DEPTH, MAX_NODES, walk


def names(nodes):
    return [node.info.name for node in nodes]


def test_walk_returns_elements_in_reading_order():
    window = FakeElement("window", "Editor", rid=(1,)).add(
        FakeElement("group", rid=(2,)).add(FakeElement("button", "Save", rid=(3,)), FakeElement("button", "Open", rid=(4,))),
        FakeElement("text", "Ready", rid=(5,)),
    )
    nodes, truncated = walk(FakeBackend({1: window}), window)
    assert names(nodes) == ["Editor", "", "Save", "Open", "Ready"]
    assert not truncated
    assert nodes[2].parent is nodes[1] and nodes[2].depth == 2


def test_chrome_tooltip_loop_is_cut():
    window = FakeElement("window", "Extensions", rid=(10,))
    tooltip = FakeElement("tool tip", "Reload", rid=(11,))
    window.add(FakeElement("button", "Reload", rid=(12,)), tooltip)
    tooltip.add(window)
    nodes, truncated = walk(FakeBackend({1: window}), window)
    assert names(nodes) == ["Extensions", "Reload", "Reload"]
    assert not truncated


def test_flutter_elements_without_ids_are_all_kept():
    pane = FakeElement("pane").add(*[FakeElement("image", f"card {i}") for i in range(5)], FakeElement("image", "card 0"))
    window = FakeElement("window", "Kazumi", rid=(1,)).add(pane)
    nodes, _ = walk(FakeBackend({1: window}), window)
    cards = [node for node in nodes if node.info.role == "image"]
    assert len(cards) == 6
    assert [node.sibling_index for node in cards if node.info.name == "card 0"] == [0, 1]


def test_loop_through_elements_without_ids_is_cut():
    group = FakeElement("group")
    group.add(FakeElement("image", "card"), group)
    window = FakeElement("window", "Kazumi", rid=(1,)).add(group)
    backend = FakeBackend({1: window})
    nodes, _ = walk(backend, window)
    assert names(nodes) == ["Kazumi", "", "card"]
    assert backend.compares >= 1


def test_depth_is_capped():
    window = FakeElement("window", "Deep", rid=(1,))
    level = window
    for i in range(MAX_DEPTH + 10):
        child = FakeElement("group", f"level {i}", rid=(2, i))
        level.add(child)
        level = child
    nodes, truncated = walk(FakeBackend({1: window}), window)
    assert truncated
    assert max(node.depth for node in nodes) == MAX_DEPTH


def test_element_count_is_capped():
    window = FakeElement("window", "Huge", rid=(1,)).add(*[FakeElement("text", f"row {i}", rid=(3, i)) for i in range(MAX_NODES + 500)])
    nodes, truncated = walk(FakeBackend({1: window}), window)
    assert truncated and len(nodes) == MAX_NODES
    assert nodes[-1].info.name == f"row {MAX_NODES - 2}"
