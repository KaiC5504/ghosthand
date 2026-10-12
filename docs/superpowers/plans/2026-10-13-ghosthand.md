# ghosthand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One Claude Code plugin that operates and tests Windows apps and a DevTools test Chrome without ever touching KaiC's mouse or keyboard.

**Architecture:** A Python MCP server (`desktop/`) reads one window at a time through the COM `IUIAutomation` client, gives elements stable short refs, and acts only through accessibility patterns. Microsoft's Playwright MCP is bundled for the test Chrome, a tiny MV3 extension exports cookies from the real Chrome, and a skill tells Claude how to use it all. The 2026-10-12 benchmark harness becomes the acceptance test.

**Tech Stack:** Python 3.14 + uv, `mcp==2.3.0` (`MCPServer`), `comtypes==1.4.17`, `pillow==12.3.0`, `pytest==9.1.1`; `@playwright/mcp@0.0.83`; Node 24 for the extension tests and the benchmark (`@modelcontextprotocol/sdk@1.32.1`).

**Spec:** `docs/superpowers/specs/2026-10-12-ghosthand-design.md`

## Global Constraints

- Windows 11 only. Python `>=3.14` (`.python-version` = `3.14`), managed with uv.
- Pinned versions: `mcp==2.3.0`, `comtypes==1.4.17`, `pillow==12.3.0`, `pytest==9.1.1`, `@playwright/mcp@0.0.83`, `@modelcontextprotocol/sdk@1.32.1`.
- mcp 2.x API: `from mcp.server.mcpserver import MCPServer, Image`; errors are `mcp.server.mcpserver.exceptions.ToolError`; tool objects use snake_case (`input_schema`, `mime_type`). `mcp.server.fastmcp` does not exist in 2.x.
- Never move the mouse. `SendInput` is used only by `keys` with `allow_focus=true`.
- A read covers one window only; never the taskbar or other windows.
- Read caps: depth 64, 2000 elements; the output says when a cap was hit.
- All COM/UIA work runs on one dedicated thread (the SDK runs each tool call on whichever worker thread is free).
- UIA client is COM `CUIAutomation8` / `IUIAutomation2` with `ConnectionTimeout = 2000` and `TransactionTimeout = 2000` ms; never the managed .NET client.
- Speed targets: typical `read` < 0.5 s, `act` including its fresh read < 0.7 s, server start < 1 s.
- Test Chrome profile: `%LOCALAPPDATA%\ghosthand\chrome-profile`. Cookie file: `Downloads\ghosthand\cookies.json`, deleted right after import. Claude never prints cookie values. Never commit secrets.
- Screenshots only on request, only of the target window, never stored.
- Every error message names the problem and the next step.
- Code comments: only for the non-obvious why; no section dividers, no "Note:".

## Review Focus

1. **An action that closes its own window** (Close, Exit, OK on a dialog) must report success plus "the window closed", not an error. Pinned in Task 6 (`test_action_that_closes_the_window_still_reports_success`).
2. **The window closes between a read and an act** must give "the window holding eN closed: call windows". Pinned in Task 6 (`test_window_closed_between_read_and_act`). A hung app must time out (UIA timeouts, Task 8) instead of hanging ghosthand.
3. **Two windows matching the same name** (two Chrome windows) must give an "ambiguous" error listing the numbers, never pick one silently. Pinned in Task 6 (`test_ambiguous_and_missing_windows_are_explained`).
4. **Names with newlines, very long text or Chinese** must render as one clean line each. Pinned in Task 4 (`test_render_cleans_newlines_and_long_names`).
5. **A read cut short on a huge page** must say so and tell Claude to use `query` or a subtree. Pinned in Task 2 (`test_element_count_is_capped`) and Task 4 (`test_cut_short_read_says_so`).

## File Structure

```
ghosthand/
├── .claude-plugin/plugin.json        plugin manifest                          (Task 12)
├── .claude-plugin/marketplace.json   local marketplace (source "./")          (Task 12)
├── .mcp.json                         desktop server + Playwright MCP          (Task 12)
├── .gitignore, LICENSE                                                         (Task 1)
├── README.md                         install, use, test, results              (Task 13)
├── skills/ghosthand/SKILL.md         how Claude uses ghosthand                (Task 12)
├── cookie-export/                    MV3 extension for the real Chrome        (Task 11)
│   ├── manifest.json, popup.html, popup.js, cookies.js, cookies.test.mjs, package.json
├── scripts/browser-smoke.mjs         Playwright MCP + cookie import smoke     (Task 12)
├── bench/                            acceptance benchmark (ported harness)    (Task 13)
└── desktop/                          Python MCP server
    ├── pyproject.toml, .python-version, uv.lock                               (Task 1)
    ├── src/ghosthand/__init__.py                                              (Task 1)
    ├── src/ghosthand/model.py        ElementInfo, Node, Snapshot, WindowInfo, GhostError, Backend (Task 1)
    ├── src/ghosthand/reader.py       walk (loop-safe, capped), render         (Tasks 2, 4)
    ├── src/ghosthand/refs.py         identity + RefTable                       (Task 3)
    ├── src/ghosthand/actions.py      choose an action                          (Task 5)
    ├── src/ghosthand/keys.py         parse_keys, key_lparam                    (Task 5)
    ├── src/ghosthand/desktop.py      Desktop service (all commands)            (Task 6)
    ├── src/ghosthand/win32.py        windows, focus, keys, screenshot, launch  (Task 7)
    ├── src/ghosthand/uia.py          COM IUIAutomation backend                 (Task 8)
    ├── src/ghosthand/server.py       MCPServer tools on one UIA thread         (Task 9)
    └── tests/
        ├── fakes.py                  FakeElement, FakeBackend, FakeWin         (Tasks 1, 6)
        ├── test_model.py, test_reader.py, test_refs.py, test_render.py,
        ├── test_actions.py, test_keys.py, test_desktop.py, test_server.py
        ├── test_win32_real.py, test_uia_real.py                                (Tasks 7, 8; marked real)
        └── test_acceptance_real.py                                             (Task 10; marked real)
```

All Python commands run from `D:\Repos\Tools\ghosthand\desktop`. `uv run pytest` skips tests marked `real`; `uv run pytest -m real` runs them on the live desktop.

---

### Task 1: Python project, data model and test fakes

**Files:**
- Create: `.gitignore`, `LICENSE`
- Create: `desktop/pyproject.toml`, `desktop/.python-version`
- Create: `desktop/src/ghosthand/__init__.py`, `desktop/src/ghosthand/model.py`
- Create: `desktop/tests/fakes.py`, `desktop/tests/test_model.py`

**Interfaces:**
- Produces: `ghosthand.model` with `GhostError(Exception)`; `ElementInfo(role: str, name: str = "", automation_id: str = "", runtime_id: tuple[int, ...] | None = None, rect: tuple[int, int, int, int] = (0, 0, 0, 0), actions: tuple[str, ...] = (), value: str | None = None)` (frozen); `Node(info, handle, parent, depth, sibling_index=0, children=[], key=(), ref="")`; `Snapshot(hwnd, title, app, nodes, truncated)` with `.root` and `.find(ref) -> Node | None`; `WindowInfo(hwnd, title, app, pid, front=False)` (frozen); `Backend` protocol: `root(hwnd)`, `info(el) -> ElementInfo`, `children(el) -> list`, `same(a, b) -> bool`, `perform(el, action) -> None`, `set_value(el, text) -> bool`.
- Produces (tests): `fakes.FakeElement(role, name="", *, rid=None, actions=(), value=None, aid="", rect=(0, 0, 10, 10), settable=False)` with `.data`, `.children`, `.performed`, `.on_perform`, `.add(*kids)`; `fakes.FakeBackend(windows: dict[int, FakeElement])` with `.compares`.

- [ ] **Step 1: Create the repo files**

`.gitignore`:

```
desktop/.venv/
__pycache__/
*.pyc
node_modules/
bench/out/
# Logins: never commit these
chrome-profile/
*.storage.json
cookies.json
```

`LICENSE`:

```
MIT License

Copyright (c) 2026 KaiC5504

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

`desktop/.python-version`:

```
3.14
```

`desktop/pyproject.toml`:

```toml
[project]
name = "ghosthand"
version = "0.1.0"
description = "Mouse-free Windows desktop automation for Claude Code"
requires-python = ">=3.14"
dependencies = [
    "comtypes==1.4.17",
    "mcp==2.3.0",
    "pillow==12.3.0",
]

[project.scripts]
ghosthand = "ghosthand.server:main"

[dependency-groups]
dev = ["pytest==9.1.1"]

[build-system]
requires = ["uv_build>=0.13.0,<0.14"]
build-backend = "uv_build"

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["real: drives real apps on this PC; run with: uv run pytest -m real"]
addopts = "-m \"not real\""
```

`desktop/src/ghosthand/__init__.py`:

```python
"""Mouse-free Windows desktop automation for Claude Code."""
```

- [ ] **Step 2: Write the failing test**

`desktop/tests/test_model.py`:

```python
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
```

- [ ] **Step 3: Run it to see it fail**

Run: `uv sync` then `uv run pytest tests/test_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fakes'` (or `ghosthand.model`).

- [ ] **Step 4: Write the model and the fakes**

`desktop/src/ghosthand/model.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class GhostError(Exception):
    """A failure whose message tells Claude what happened and what to do next."""


@dataclass(frozen=True)
class ElementInfo:
    role: str
    name: str = ""
    automation_id: str = ""
    runtime_id: tuple[int, ...] | None = None
    rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    actions: tuple[str, ...] = ()
    value: str | None = None


@dataclass(eq=False)
class Node:
    info: ElementInfo
    handle: object
    parent: Node | None
    depth: int
    sibling_index: int = 0
    children: list[Node] = field(default_factory=list)
    key: tuple = ()
    ref: str = ""


@dataclass(eq=False)
class Snapshot:
    hwnd: int
    title: str
    app: str
    nodes: list[Node]
    truncated: bool

    @property
    def root(self) -> Node:
        return self.nodes[0]

    def find(self, ref: str) -> Node | None:
        return next((node for node in self.nodes if node.ref == ref), None)


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    app: str
    pid: int
    front: bool = False


class Backend(Protocol):
    def root(self, hwnd: int) -> object: ...
    def info(self, element: object) -> ElementInfo: ...
    def children(self, element: object) -> list[object]: ...
    def same(self, a: object, b: object) -> bool: ...
    def perform(self, element: object, action: str) -> None: ...
    def set_value(self, element: object, text: str) -> bool: ...
```

`desktop/tests/fakes.py`:

```python
from dataclasses import replace

from ghosthand.model import ElementInfo


class FakeElement:
    def __init__(self, role, name="", *, rid=None, actions=(), value=None, aid="", rect=(0, 0, 10, 10), settable=False):
        self.data = ElementInfo(role=role, name=name, automation_id=aid, runtime_id=rid, rect=rect, actions=tuple(actions), value=value)
        self.children = []
        self.settable = settable
        self.performed = []
        self.on_perform = None

    def add(self, *kids):
        self.children.extend(kids)
        return self


class FakeBackend:
    def __init__(self, windows):
        self.windows = windows
        self.compares = 0

    def root(self, hwnd):
        return self.windows[hwnd]

    def info(self, element):
        return element.data

    def children(self, element):
        return list(element.children)

    def same(self, a, b):
        self.compares += 1
        return a is b

    def perform(self, element, action):
        element.performed.append(action)
        if element.on_perform:
            element.on_perform(action)

    def set_value(self, element, text):
        if not element.settable:
            return False
        element.data = replace(element.data, value=text)
        return True
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `uv run pytest -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add .gitignore LICENSE desktop/pyproject.toml desktop/.python-version desktop/uv.lock desktop/src desktop/tests
git commit -m "Add ghosthand Python project, data model and test fakes"
```

---

### Task 2: Loop-safe, capped tree walk

**Files:**
- Create: `desktop/src/ghosthand/reader.py`
- Test: `desktop/tests/test_reader.py`

**Interfaces:**
- Consumes: `Backend`, `ElementInfo`, `Node` (Task 1).
- Produces: `reader.MAX_DEPTH = 64`, `reader.MAX_NODES = 2000`, `walk(backend, root, *, max_depth=MAX_DEPTH, max_nodes=MAX_NODES) -> tuple[list[Node], bool]` (nodes in reading order, root first; bool = a cap cut it short), `preorder(node) -> list[Node]`.

- [ ] **Step 1: Write the failing tests**

`desktop/tests/test_reader.py`:

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_reader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ghosthand.reader'`.

- [ ] **Step 3: Write the walk**

`desktop/src/ghosthand/reader.py`:

```python
from __future__ import annotations

from ghosthand.model import Backend, ElementInfo, Node

MAX_DEPTH = 64
MAX_NODES = 2000


def walk(backend: Backend, root: object, *, max_depth: int = MAX_DEPTH, max_nodes: int = MAX_NODES) -> tuple[list[Node], bool]:
    """Read the tree under root; returns the nodes in reading order and whether a cap cut it short."""
    top = Node(info=backend.info(root), handle=root, parent=None, depth=0)
    seen_runtime_ids = {top.info.runtime_id} if top.info.runtime_id else set()
    count = 1
    truncated = False
    pending = [top]
    while pending:
        node = pending.pop()
        handles = backend.children(node.handle)
        if handles and node.depth >= max_depth:
            truncated = True
            continue
        siblings: dict[tuple, int] = {}
        added = []
        for handle in handles:
            if count >= max_nodes:
                truncated = True
                break
            info = backend.info(handle)
            if _loops_back(backend, info, handle, node, seen_runtime_ids):
                continue
            kind = (info.role, info.name, info.automation_id)
            child = Node(info=info, handle=handle, parent=node, depth=node.depth + 1, sibling_index=siblings.get(kind, 0))
            siblings[kind] = child.sibling_index + 1
            if info.runtime_id:
                seen_runtime_ids.add(info.runtime_id)
            node.children.append(child)
            added.append(child)
            count += 1
        # First child next, so when the element cap hits, it cuts the end of the window.
        pending.extend(reversed(added))
    return preorder(top), truncated


def _loops_back(backend: Backend, info: ElementInfo, handle: object, parent: Node, seen_runtime_ids: set) -> bool:
    # Chrome tooltips point back at their own window. Flutter elements have no runtime id,
    # so for those the only proof of a loop is UIA saying the element is one of its ancestors.
    if info.runtime_id:
        return info.runtime_id in seen_runtime_ids
    ancestor = parent
    while ancestor is not None:
        if ancestor.info == info and backend.same(ancestor.handle, handle):
            return True
        ancestor = ancestor.parent
    return False


def preorder(node: Node) -> list[Node]:
    ordered, stack = [], [node]
    while stack:
        current = stack.pop()
        ordered.append(current)
        stack.extend(reversed(current.children))
    return ordered
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_reader.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/ghosthand/reader.py desktop/tests/test_reader.py
git commit -m "Add loop-safe, capped UI tree walk"
```

---

### Task 3: Stable element refs

**Files:**
- Create: `desktop/src/ghosthand/refs.py`
- Test: `desktop/tests/test_refs.py`

**Interfaces:**
- Consumes: `Node`, `Snapshot` (Task 1); `walk` (Task 2).
- Produces: `identity(node) -> tuple`; `RefTable()` with `assign(snapshot) -> None` (sets `node.key` and `node.ref` on every node; refs look like `e12` and are unique across all windows) and `window_of(ref) -> int | None`.

- [ ] **Step 1: Write the failing tests**

`desktop/tests/test_refs.py`:

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_refs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ghosthand.refs'`.

- [ ] **Step 3: Write the ref table**

`desktop/src/ghosthand/refs.py`:

```python
from __future__ import annotations

from ghosthand.model import Node, Snapshot


def identity(node: Node) -> tuple:
    info = node.info
    if info.runtime_id:
        return ("rid", info.runtime_id)
    # Flutter elements have no runtime id, so they are known by where they sit and what they are.
    parent_key = node.parent.key if node.parent else ()
    return ("fp", parent_key, info.role, info.name, info.automation_id, node.sibling_index)


class RefTable:
    """Gives each element a short ref that stays the same for as long as the element exists."""

    def __init__(self) -> None:
        self._by_key: dict[tuple, str] = {}
        self._window: dict[str, int] = {}

    def assign(self, snapshot: Snapshot) -> None:
        # Reading order puts parents first, so a parent's key exists before its children need it.
        for node in snapshot.nodes:
            node.key = identity(node)
            full_key = (snapshot.hwnd, node.key)
            ref = self._by_key.get(full_key)
            if ref is None:
                ref = f"e{len(self._by_key) + 1}"
                self._by_key[full_key] = ref
                self._window[ref] = snapshot.hwnd
            node.ref = ref

    def window_of(self, ref: str) -> int | None:
        return self._window.get(ref)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_refs.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/ghosthand/refs.py desktop/tests/test_refs.py
git commit -m "Add stable element refs across reads"
```

---

### Task 4: Compact window rendering

**Files:**
- Modify: `desktop/src/ghosthand/reader.py` (append rendering)
- Test: `desktop/tests/test_render.py`

**Interfaces:**
- Consumes: `Snapshot`, `GhostError` (Task 1); `walk`, `preorder`, `MAX_NODES`, `MAX_DEPTH` (Task 2); `RefTable` (Task 3).
- Produces: `render(snapshot, *, query: str | None = None, subtree: str | None = None) -> str`. First line `window <hwnd> "<title>" (<app>)`; then one line per shown element: `<indent><ref> <role> "<name>"`, or `@x,y` for an unnamed usable element, then ` = "<value>"` when the value differs from the name, then ` [<actions>]`. Indent is two spaces per level; children of folded elements move up.

- [ ] **Step 1: Write the failing tests**

`desktop/tests/test_render.py`:

```python
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
    assert render(snapshot_of(window)).endswith("read a subtree ref or use query)")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL with `ImportError: cannot import name 'render'`.

- [ ] **Step 3: Write the rendering**

In `desktop/src/ghosthand/reader.py`, change the model import to:

```python
from ghosthand.model import Backend, ElementInfo, GhostError, Node, Snapshot
```

and append:

```python
CONTAINER_ROLES = {"group", "pane", "custom"}
NAME_LIMIT = 120


def folded(node: Node) -> bool:
    info = node.info
    if node.parent is None or info.name or info.value:
        return False
    actions = set(info.actions)
    return not actions or (actions <= {"default"} and info.role in CONTAINER_ROLES)


def clean(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= NAME_LIMIT else text[: NAME_LIMIT - 1] + "…"


def line(node: Node, indent: int) -> str:
    info = node.info
    parts = [f"{'  ' * indent}{node.ref} {info.role}"]
    if info.name:
        parts.append(f'"{clean(info.name)}"')
    elif info.actions:
        # Unnamed controls such as Kazumi's back arrow are told apart by where they are.
        parts.append(f"@{info.rect[0]},{info.rect[1]}")
    if info.value and info.value != info.name:
        parts.append(f'= "{clean(info.value)}"')
    if info.actions:
        parts.append(f"[{', '.join(info.actions)}]")
    return " ".join(parts)


def render(snapshot: Snapshot, *, query: str | None = None, subtree: str | None = None) -> str:
    lines = [f'window {snapshot.hwnd} "{clean(snapshot.title)}" ({snapshot.app})']
    top = snapshot.root
    if subtree:
        top = snapshot.find(subtree)
        if top is None:
            raise GhostError(f"stale: {subtree} is no longer on screen. Read the window again.")
    nodes = preorder(top)
    if query:
        needle = query.lower()
        hits = [node for node in nodes if needle in f"{node.info.name} {node.info.value or ''}".lower()]
        lines += [line(node, 1) for node in hits] or [f'  nothing matches "{query}"']
    else:
        level = {id(top): 0}
        if subtree:
            lines.append(line(top, 1))
            level[id(top)] = 1
        for node in nodes[1:]:
            depth = level[id(node.parent)]
            if not folded(node):
                depth += 1
                lines.append(line(node, depth))
            level[id(node)] = depth
    if snapshot.truncated:
        lines.append(f"(read stopped early: over {MAX_NODES} elements or {MAX_DEPTH} levels; read a subtree ref or use query)")
    return "\n".join(lines)
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: all passed (4 + 6 + 5 + 7 = 22).

- [ ] **Step 5: Commit**

```bash
git add desktop/src/ghosthand/reader.py desktop/tests/test_render.py
git commit -m "Render a window as one compact line per element"
```

---

### Task 5: Action choice and key parsing

**Files:**
- Create: `desktop/src/ghosthand/actions.py`, `desktop/src/ghosthand/keys.py`
- Test: `desktop/tests/test_actions.py`, `desktop/tests/test_keys.py`

**Interfaces:**
- Consumes: `Node`, `ElementInfo`, `GhostError` (Task 1).
- Produces: `actions.AUTO_ORDER = ("press", "toggle", "select", "expand", "default")`, `actions.ALL_ACTIONS = AUTO_ORDER + ("collapse",)`, `choose(node, requested="auto") -> str`; `keys.KeyStroke(vk: int, modifiers: tuple[int, ...] = (), extended: bool = False)` (frozen), `parse_keys(spec: str) -> list[KeyStroke]`, `key_lparam(scan: int, extended: bool, up: bool) -> int`.

- [ ] **Step 1: Write the failing tests**

`desktop/tests/test_actions.py`:

```python
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
```

`desktop/tests/test_keys.py`:

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_actions.py tests/test_keys.py -v`
Expected: FAIL with `ModuleNotFoundError` for `ghosthand.actions` and `ghosthand.keys`.

- [ ] **Step 3: Write both modules**

`desktop/src/ghosthand/actions.py`:

```python
from __future__ import annotations

from ghosthand.model import GhostError, Node

AUTO_ORDER = ("press", "toggle", "select", "expand", "default")
ALL_ACTIONS = AUTO_ORDER + ("collapse",)


def choose(node: Node, requested: str = "auto") -> str:
    supported = node.info.actions
    if requested == "auto":
        for action in AUTO_ORDER:
            if action in supported:
                return action
        raise GhostError(
            f'needs a real click: {node.ref} {node.info.role} "{node.info.name}" has no mouse-free action. '
            "Take a screenshot and tell KaiC; ghosthand never moves the mouse."
        )
    if requested not in ALL_ACTIONS:
        raise GhostError(f'unknown action "{requested}"; use one of: auto, {", ".join(ALL_ACTIONS)}')
    if requested not in supported:
        raise GhostError(f'{node.ref} cannot "{requested}"; it supports: {", ".join(supported) or "nothing"}')
    return requested
```

`desktop/src/ghosthand/keys.py`:

```python
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


@dataclass(frozen=True)
class KeyStroke:
    vk: int
    modifiers: tuple[int, ...] = ()
    extended: bool = False


def parse_keys(spec: str) -> list[KeyStroke]:
    strokes = []
    for token in spec.split():
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
        else:
            raise GhostError(f'unknown key "{key}" in "{token}"; use a letter, a digit or a name like enter, tab, esc, up, f5')
        strokes.append(KeyStroke(vk, tuple(modifiers), extended))
    if not strokes:
        raise GhostError("no keys given")
    return strokes


def key_lparam(scan: int, extended: bool, up: bool) -> int:
    value = 1 | (scan << 16) | (int(extended) << 24)
    if up:
        value |= (1 << 30) | (1 << 31)
    return value
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_actions.py tests/test_keys.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/ghosthand/actions.py desktop/src/ghosthand/keys.py desktop/tests/test_actions.py desktop/tests/test_keys.py
git commit -m "Add mouse-free action choice and key parsing"
```

---

### Task 6: Desktop service (every command, on fakes)

**Files:**
- Create: `desktop/src/ghosthand/desktop.py`
- Modify: `desktop/tests/fakes.py` (append `window_info`, `FakeWin`)
- Test: `desktop/tests/test_desktop.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Consumes (window layer, implemented for real in Task 7): an object with `list_windows() -> list[WindowInfo]`, `is_window(hwnd) -> bool`, `info(hwnd) -> WindowInfo`, `foreground() -> int`, `set_foreground(hwnd) -> bool`, `post_keys(hwnd, strokes) -> None`, `send_keys_focused(hwnd, strokes) -> None`, `capture(hwnd) -> bytes`, `launch(target: str, args: list[str]) -> int | None`.
- Produces: `Desktop(backend, win, *, sleep=time.sleep, clock=time.monotonic)` with `windows() -> str`, `resolve(window) -> int`, `snapshot(hwnd) -> Snapshot`, `read(window, ref=None, query=None) -> str`, `act(ref, action="auto") -> str`, `set_text(ref, text, submit=False) -> str`, `keys(window, keys, allow_focus=False) -> str`, `wait_for(window, text, gone=False, timeout=10.0) -> str`, `launch(target, args=(), timeout=20.0) -> str`, `screenshot(window) -> bytes`. Action results start with a headline (`press e4: done`, `text set on e7 and submitted`, `sent tab enter`, `launched kazumi, window 900`), optionally ` (focus handed back)`, then the fresh render, or end with `; the window closed`.

- [ ] **Step 1: Add the fake window layer**

Append to `desktop/tests/fakes.py`:

```python
from ghosthand.model import WindowInfo


def window_info(hwnd, title, app, pid=1):
    return WindowInfo(hwnd=hwnd, title=title, app=app, pid=pid)


class FakeWin:
    def __init__(self, *rows):
        self.rows = list(rows)
        self.front = rows[0].hwnd if rows else 0
        self.posted = []
        self.focused = []
        self.allow_focus_change = True
        self.on_launch = None

    def list_windows(self):
        return [WindowInfo(row.hwnd, row.title, row.app, row.pid, row.hwnd == self.front) for row in self.rows]

    def is_window(self, hwnd):
        return any(row.hwnd == hwnd for row in self.rows)

    def info(self, hwnd):
        return next(row for row in self.list_windows() if row.hwnd == hwnd)

    def foreground(self):
        return self.front

    def set_foreground(self, hwnd):
        if not self.allow_focus_change:
            return False
        self.front = hwnd
        return True

    def post_keys(self, hwnd, strokes):
        self.posted.append((hwnd, strokes))

    def send_keys_focused(self, hwnd, strokes):
        self.front = hwnd
        self.focused.append((hwnd, strokes))

    def capture(self, hwnd):
        return b"\x89PNG fake " + str(hwnd).encode()

    def launch(self, target, args):
        if self.on_launch:
            self.on_launch()
        return 4242
```

- [ ] **Step 2: Write the failing tests**

`desktop/tests/test_desktop.py`:

```python
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
```

- [ ] **Step 3: Run them to see them fail**

Run: `uv run pytest tests/test_desktop.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ghosthand.desktop'`.

- [ ] **Step 4: Write the service**

`desktop/src/ghosthand/desktop.py`:

```python
from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from ghosthand.actions import choose
from ghosthand.keys import parse_keys
from ghosthand.model import Backend, GhostError, Node, Snapshot
from ghosthand.reader import render, walk
from ghosthand.refs import RefTable

SETTLE = 0.15
POLL = 0.25


class Desktop:
    def __init__(self, backend: Backend, win, *, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.backend = backend
        self.win = win
        self.refs = RefTable()
        self.sleep = sleep
        self.clock = clock

    def windows(self) -> str:
        rows = self.win.list_windows()
        if not rows:
            return "no windows open"
        return "\n".join(f'{row.hwnd} {row.app} "{row.title}"' + ("  (in front)" if row.front else "") for row in rows)

    def resolve(self, window: str | int) -> int:
        text = str(window).strip()
        if text.isdigit():
            hwnd = int(text)
            if not self.win.is_window(hwnd):
                raise GhostError(f"window {hwnd} closed: call windows")
            return hwnd
        rows = self.win.list_windows()
        needle = text.lower()
        hits = [row for row in rows if row.app.lower() == needle] or [row for row in rows if needle in row.title.lower()]
        if not hits:
            raise GhostError(f'no open window matches "{text}": call windows')
        if len(hits) > 1:
            listing = "; ".join(f'{row.hwnd} "{row.title}"' for row in hits[:6])
            raise GhostError(f'"{text}" matches {len(hits)} windows ({listing}); pass the number instead')
        return hits[0].hwnd

    def snapshot(self, hwnd: int) -> Snapshot:
        info = self.win.info(hwnd)
        nodes, truncated = walk(self.backend, self.backend.root(hwnd))
        snapshot = Snapshot(hwnd=hwnd, title=info.title, app=info.app, nodes=nodes, truncated=truncated)
        self.refs.assign(snapshot)
        return snapshot

    def read(self, window: str | int, ref: str | None = None, query: str | None = None) -> str:
        return render(self.snapshot(self.resolve(window)), query=query, subtree=ref)

    def act(self, ref: str, action: str = "auto") -> str:
        snapshot, node = self._node(ref)
        chosen = choose(node, action)
        note = self._guarded(snapshot.hwnd, lambda: self.backend.perform(node.handle, chosen))
        return self._after(snapshot.hwnd, f"{chosen} {ref}: done", note)

    def set_text(self, ref: str, text: str, submit: bool = False) -> str:
        snapshot, node = self._node(ref)

        def work() -> None:
            if not self.backend.set_value(node.handle, text):
                raise GhostError(f"{ref} {node.info.role} takes no direct text. Ask KaiC before using keys with allow_focus.")
            if submit:
                self.win.post_keys(snapshot.hwnd, parse_keys("enter"))

        note = self._guarded(snapshot.hwnd, work)
        return self._after(snapshot.hwnd, f"text set on {ref}" + (" and submitted" if submit else ""), note)

    def keys(self, window: str | int, keys: str, allow_focus: bool = False) -> str:
        hwnd = self.resolve(window)
        strokes = parse_keys(keys)
        if allow_focus:
            note = self._guarded(hwnd, lambda: self.win.send_keys_focused(hwnd, strokes))
        else:
            if any(stroke.modifiers for stroke in strokes):
                raise GhostError(
                    "ctrl/alt/shift/win combinations only work with the window in front. "
                    "Ask KaiC, then call keys again with allow_focus=true."
                )
            note = self._guarded(hwnd, lambda: self.win.post_keys(hwnd, strokes))
        return self._after(hwnd, f"sent {keys}", note)

    def wait_for(self, window: str | int, text: str, gone: bool = False, timeout: float = 10.0) -> str:
        hwnd = self.resolve(window)
        needle = text.lower()
        deadline = self.clock() + timeout
        while True:
            snapshot = self.snapshot(hwnd)
            present = any(needle in f"{node.info.name} {node.info.value or ''}".lower() for node in snapshot.nodes)
            if present != gone:
                return render(snapshot)
            if self.clock() >= deadline:
                raise GhostError(f'timed out after {timeout:g}s waiting for "{text}" to {"disappear" if gone else "appear"}')
            self.sleep(POLL)

    def launch(self, target: str, args: Sequence[str] = (), timeout: float = 20.0) -> str:
        before = {row.hwnd for row in self.win.list_windows()}
        front = self.win.foreground()
        pid = self.win.launch(target, list(args))
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            fresh = [row for row in self.win.list_windows() if row.hwnd not in before]
            mine = [row for row in fresh if pid is None or row.pid == pid] or fresh
            if mine:
                self.sleep(SETTLE)
                return self._after(mine[0].hwnd, f"launched {mine[0].app}, window {mine[0].hwnd}", self._hand_back(front, mine[0].hwnd))
            self.sleep(POLL)
        raise GhostError(f'started "{target}" but no new window appeared within {timeout:g}s: call windows')

    def screenshot(self, window: str | int) -> bytes:
        return self.win.capture(self.resolve(window))

    def _node(self, ref: str) -> tuple[Snapshot, Node]:
        hwnd = self.refs.window_of(ref)
        if hwnd is None:
            raise GhostError(f"unknown ref {ref}: read the window first")
        if not self.win.is_window(hwnd):
            raise GhostError(f"the window holding {ref} closed: call windows")
        snapshot = self.snapshot(hwnd)
        node = snapshot.find(ref)
        if node is None:
            raise GhostError(f"stale: {ref} is no longer on screen. Read the window again.")
        return snapshot, node

    def _guarded(self, hwnd: int, work: Callable[[], None]) -> str:
        front = self.win.foreground()
        work()
        self.sleep(SETTLE)
        return self._hand_back(front, hwnd)

    def _hand_back(self, front: int, target: int) -> str:
        # Apps such as Kazumi pull themselves forward when used; KaiC's window gets focus back.
        if not front or front == target or self.win.foreground() == front:
            return ""
        if self.win.set_foreground(front):
            return "focus handed back"
        return "the app took focus and Windows would not let ghosthand hand it back"

    def _after(self, hwnd: int, headline: str, note: str) -> str:
        if note:
            headline += f" ({note})"
        if not self.win.is_window(hwnd):
            return f"{headline}; the window closed"
        return f"{headline}\n{render(self.snapshot(hwnd))}"
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest -v`
Expected: all passed (22 + 9 + 19 = 50).

- [ ] **Step 6: Commit**

```bash
git add desktop/src/ghosthand/desktop.py desktop/tests/fakes.py desktop/tests/test_desktop.py
git commit -m "Add the Desktop service: read, act, text, keys, wait, launch, screenshot"
```

---

### Task 7: Real window layer (Win32)

**Files:**
- Create: `desktop/src/ghosthand/win32.py`
- Test: `desktop/tests/test_win32_real.py` (marked `real`)

**Interfaces:**
- Consumes: `WindowInfo`, `GhostError` (Task 1); `KeyStroke`, `key_lparam` (Task 5).
- Produces: `Win32()` implementing the window layer from Task 6 exactly: `list_windows`, `is_window`, `info`, `foreground`, `set_foreground`, `post_keys`, `send_keys_focused`, `capture`, `launch`.

- [ ] **Step 1: Write the failing real tests**

`desktop/tests/test_win32_real.py`:

```python
import pytest

from ghosthand.win32 import Win32

pytestmark = pytest.mark.real


def test_lists_visible_windows_with_their_apps():
    rows = Win32().list_windows()
    assert rows
    assert all(row.title and row.app for row in rows)
    assert sum(row.front for row in rows) <= 1


def test_captures_the_front_window_as_png():
    win = Win32()
    assert win.capture(win.foreground()).startswith(b"\x89PNG")


def test_resolves_the_front_window_info():
    win = Win32()
    front = win.foreground()
    info = win.info(front)
    assert info.hwnd == front and info.front and info.app != "unknown"


def test_posting_no_keys_is_safe():
    win = Win32()
    win.post_keys(win.foreground(), [])
```

Run: `uv run pytest -m real tests/test_win32_real.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ghosthand.win32'`.

- [ ] **Step 2: Write the window layer**

`desktop/src/ghosthand/win32.py`:

```python
from __future__ import annotations

import ctypes
import io
import os
import subprocess
from ctypes import wintypes
from pathlib import Path

from PIL import Image

from ghosthand.keys import KeyStroke, key_lparam
from ghosthand.model import GhostError, WindowInfo

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
DWMWA_CLOAKED = 14
PW_RENDERFULLCONTENT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
INPUT_KEYBOARD, KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 1, 0x1, 0x2


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _InputUnion(ctypes.Union):
    # MOUSEINPUT is only here because it is the largest member; SendInput rejects an INPUT of the wrong size.
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _InputUnion)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


def _title(hwnd: int) -> str:
    size = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(size + 1)
    user32.GetWindowTextW(hwnd, buffer, size + 1)
    return buffer.value


def _pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _app(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return "unknown"
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return "unknown"
        return Path(buffer.value).stem
    finally:
        kernel32.CloseHandle(handle)


def _cloaked(hwnd: int) -> bool:
    value = wintypes.DWORD()
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value))
    return value.value != 0


class Win32:
    def list_windows(self) -> list[WindowInfo]:
        front = self.foreground()
        rows: list[WindowInfo] = []

        @WNDENUMPROC
        def visit(hwnd, _):
            if user32.IsWindowVisible(hwnd) and not _cloaked(hwnd):
                title = _title(hwnd)
                if title:
                    pid = _pid(hwnd)
                    rows.append(WindowInfo(hwnd=hwnd, title=title, app=_app(pid), pid=pid, front=hwnd == front))
            return True

        user32.EnumWindows(visit, 0)
        return rows

    def is_window(self, hwnd: int) -> bool:
        return bool(user32.IsWindow(hwnd))

    def info(self, hwnd: int) -> WindowInfo:
        if not self.is_window(hwnd):
            raise GhostError(f"window {hwnd} closed: call windows")
        pid = _pid(hwnd)
        return WindowInfo(hwnd=hwnd, title=_title(hwnd), app=_app(pid), pid=pid, front=hwnd == self.foreground())

    def foreground(self) -> int:
        return user32.GetForegroundWindow() or 0

    def set_foreground(self, hwnd: int) -> bool:
        # Windows lets only the foreground thread move the foreground, so borrow its input
        # state for the call instead of faking a keypress.
        current = user32.GetForegroundWindow()
        theirs = user32.GetWindowThreadProcessId(current, None) if current else 0
        ours = kernel32.GetCurrentThreadId()
        attached = bool(theirs) and theirs != ours and bool(user32.AttachThreadInput(ours, theirs, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(ours, theirs, False)
        return self.foreground() == hwnd

    def post_keys(self, hwnd: int, strokes: list[KeyStroke]) -> None:
        for stroke in strokes:
            scan = user32.MapVirtualKeyW(stroke.vk, 0)
            user32.PostMessageW(hwnd, WM_KEYDOWN, stroke.vk, key_lparam(scan, stroke.extended, up=False))
            user32.PostMessageW(hwnd, WM_KEYUP, stroke.vk, key_lparam(scan, stroke.extended, up=True))

    def send_keys_focused(self, hwnd: int, strokes: list[KeyStroke]) -> None:
        if not self.set_foreground(hwnd):
            raise GhostError("Windows would not bring the window to the front; ask KaiC to click it once, then try again")
        events = []
        for stroke in strokes:
            events += [(vk, False, False) for vk in stroke.modifiers]
            events += [(stroke.vk, stroke.extended, False), (stroke.vk, stroke.extended, True)]
            events += [(vk, False, True) for vk in reversed(stroke.modifiers)]
        inputs = (INPUT * len(events))()
        for slot, (vk, extended, up) in zip(inputs, events):
            slot.type = INPUT_KEYBOARD
            slot.ki = KEYBDINPUT(wVk=vk, dwFlags=(KEYEVENTF_EXTENDEDKEY if extended else 0) | (KEYEVENTF_KEYUP if up else 0))
        user32.SendInput(len(events), inputs, ctypes.sizeof(INPUT))

    def capture(self, hwnd: int) -> bytes:
        if user32.IsIconic(hwnd):
            raise GhostError("the window is minimised; ask KaiC to restore it, then take the screenshot")
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise GhostError("the window has no size to capture")
        screen = user32.GetDC(None)
        memory = gdi32.CreateCompatibleDC(screen)
        bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
        previous = gdi32.SelectObject(memory, bitmap)
        try:
            # PW_RENDERFULLCONTENT makes covered and GPU-drawn windows paint into the bitmap too.
            if not user32.PrintWindow(hwnd, memory, PW_RENDERFULLCONTENT):
                raise GhostError("the window would not draw itself for a screenshot")
            header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=width, biHeight=-height, biPlanes=1, biBitCount=32)
            pixels = ctypes.create_string_buffer(width * height * 4)
            gdi32.GetDIBits(memory, bitmap, 0, height, pixels, ctypes.byref(header), 0)
        finally:
            gdi32.SelectObject(memory, previous)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory)
            user32.ReleaseDC(None, screen)
        image = Image.frombuffer("RGB", (width, height), pixels.raw, "raw", "BGRX", 0, 1)
        out = io.BytesIO()
        image.save(out, "PNG")
        return out.getvalue()

    def launch(self, target: str, args: list[str]) -> int | None:
        path = Path(target)
        if path.suffix.lower() == ".exe" and path.is_file():
            # DEVNULL: the child must not inherit the MCP server's stdio pipes.
            process = subprocess.Popen(
                [str(path), *args], cwd=str(path.parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            return process.pid
        try:
            os.startfile(target, arguments=subprocess.list2cmdline(args))
        except OSError as error:
            raise GhostError(f'could not start "{target}": {error.strerror or error}') from None
        return None
```

- [ ] **Step 3: Run the real tests and the unit tests**

Run: `uv run pytest -m real tests/test_win32_real.py -v` then `uv run pytest -v`
Expected: 4 passed (real); 50 passed (unit).

- [ ] **Step 4: Commit**

```bash
git add desktop/src/ghosthand/win32.py desktop/tests/test_win32_real.py
git commit -m "Add the Win32 window layer: windows, focus, background keys, screenshots, launch"
```

---

### Task 8: COM UI Automation backend

**Files:**
- Create: `desktop/src/ghosthand/uia.py`
- Test: `desktop/tests/test_uia_real.py` (marked `real`)

**Interfaces:**
- Consumes: `ElementInfo`, `GhostError` (Task 1); `walk` (Task 2); `Win32` (Task 7, tests only).
- Produces: `UiaBackend()` implementing `Backend`: `root(hwnd)`, `info(el)`, `children(el)`, `same(a, b)`, `perform(el, action)`, `set_value(el, text)`. Roles are lower-case words from the UIA control type names (`button`, `list item`, `tool tip`, `title bar`, …). Actions: `press` (Invoke), `toggle`, `select` (SelectionItem), `expand`/`collapse` (ExpandCollapse), and `default` (LegacyIAccessible.DoDefaultAction) only when none of the others apply and the element has a default action name or is keyboard-focusable. Must be created and used on one thread with COM initialised.

- [ ] **Step 1: Write the failing real tests**

`desktop/tests/test_uia_real.py`:

```python
import time

import pytest

from ghosthand.reader import walk
from ghosthand.uia import UiaBackend
from ghosthand.win32 import Win32

pytestmark = pytest.mark.real


def window_titled(win, title):
    return next((row.hwnd for row in win.list_windows() if row.title == title), None)


@pytest.fixture(scope="module")
def calculator():
    win = Win32()
    hwnd = window_titled(win, "Calculator")
    if hwnd is None:
        win.launch("calculator:", [])
        for _ in range(40):
            time.sleep(0.25)
            hwnd = window_titled(win, "Calculator")
            if hwnd:
                break
    assert hwnd, "Calculator did not open"
    return hwnd


def test_reads_calculator_buttons_with_actions(calculator):
    backend = UiaBackend()
    nodes, truncated = walk(backend, backend.root(calculator))
    seven = next(node for node in nodes if node.info.name == "Seven")
    assert seven.info.role == "button" and "press" in seven.info.actions and seven.info.runtime_id
    assert not truncated


def test_press_changes_the_display(calculator):
    backend = UiaBackend()
    nodes, _ = walk(backend, backend.root(calculator))
    by_name = {node.info.name: node for node in nodes}
    backend.perform(by_name["Clear"].handle, "press")
    backend.perform(by_name["Seven"].handle, "press")
    nodes, _ = walk(backend, backend.root(calculator))
    assert any(node.info.name == "Display is 7" for node in nodes)


def test_flutter_cards_have_no_runtime_id_but_a_default_action():
    win = Win32()
    hwnd = next((row.hwnd for row in win.list_windows() if row.app == "kazumi"), None)
    if hwnd is None:
        pytest.skip("Kazumi is not open")
    backend = UiaBackend()
    nodes, _ = walk(backend, backend.root(hwnd))
    images = [node for node in nodes if node.info.role == "image" and node.info.name]
    assert images
    assert all(node.info.runtime_id is None and "default" in node.info.actions for node in images)
```

Run: `uv run pytest -m real tests/test_uia_real.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ghosthand.uia'`.

- [ ] **Step 2: Write the backend**

`desktop/src/ghosthand/uia.py`:

```python
from __future__ import annotations

import re

import comtypes
import comtypes.client

comtypes.client.GetModule("UIAutomationCore.dll")
from comtypes.gen import UIAutomationClient as U  # noqa: E402  (generated by the line above)

from ghosthand.model import ElementInfo, GhostError  # noqa: E402

ROLES = {
    getattr(U, name): re.sub(r"(?<!^)(?=[A-Z])", " ", name[4 : -len("ControlTypeId")]).lower()
    for name in dir(U)
    if name.startswith("UIA_") and name.endswith("ControlTypeId")
}

CACHED = (
    U.UIA_NamePropertyId, U.UIA_ControlTypePropertyId, U.UIA_AutomationIdPropertyId,
    U.UIA_BoundingRectanglePropertyId, U.UIA_RuntimeIdPropertyId, U.UIA_IsKeyboardFocusablePropertyId,
    U.UIA_IsInvokePatternAvailablePropertyId, U.UIA_IsTogglePatternAvailablePropertyId,
    U.UIA_IsSelectionItemPatternAvailablePropertyId, U.UIA_IsExpandCollapsePatternAvailablePropertyId,
    U.UIA_IsLegacyIAccessiblePatternAvailablePropertyId, U.UIA_LegacyIAccessibleDefaultActionPropertyId,
    U.UIA_IsValuePatternAvailablePropertyId, U.UIA_ValueValuePropertyId,
)

PATTERNS = {
    "press": (U.UIA_InvokePatternId, U.IUIAutomationInvokePattern, "Invoke"),
    "toggle": (U.UIA_TogglePatternId, U.IUIAutomationTogglePattern, "Toggle"),
    "select": (U.UIA_SelectionItemPatternId, U.IUIAutomationSelectionItemPattern, "Select"),
    "expand": (U.UIA_ExpandCollapsePatternId, U.IUIAutomationExpandCollapsePattern, "Expand"),
    "collapse": (U.UIA_ExpandCollapsePatternId, U.IUIAutomationExpandCollapsePattern, "Collapse"),
    "default": (U.UIA_LegacyIAccessiblePatternId, U.IUIAutomationLegacyIAccessiblePattern, "DoDefaultAction"),
}


class UiaBackend:
    """Reads and acts through the COM IUIAutomation client; the managed .NET client cannot see inside Flutter."""

    def __init__(self) -> None:
        self.uia = comtypes.client.CreateObject(U.CUIAutomation8, interface=U.IUIAutomation2)
        # A hung app must not hang ghosthand.
        self.uia.ConnectionTimeout = 2000
        self.uia.TransactionTimeout = 2000
        self.cache = self.uia.CreateCacheRequest()
        for prop in CACHED:
            self.cache.AddProperty(prop)
        self.walker = self.uia.ControlViewWalker

    def root(self, hwnd: int) -> object:
        try:
            return self.uia.ElementFromHandleBuildCache(hwnd, self.cache)
        except comtypes.COMError:
            raise GhostError(f"window {hwnd} closed or stopped responding: call windows") from None

    def info(self, element) -> ElementInfo:
        get = element.GetCachedPropertyValue
        actions = []
        if get(U.UIA_IsInvokePatternAvailablePropertyId):
            actions.append("press")
        if get(U.UIA_IsTogglePatternAvailablePropertyId):
            actions.append("toggle")
        if get(U.UIA_IsSelectionItemPatternAvailablePropertyId):
            actions.append("select")
        if get(U.UIA_IsExpandCollapsePatternAvailablePropertyId):
            actions += ["expand", "collapse"]
        # Flutter's cards report an empty default action name, yet DoDefaultAction opens them.
        if not actions and get(U.UIA_IsLegacyIAccessiblePatternAvailablePropertyId) and (
            get(U.UIA_LegacyIAccessibleDefaultActionPropertyId) or get(U.UIA_IsKeyboardFocusablePropertyId)
        ):
            actions.append("default")
        value = get(U.UIA_ValueValuePropertyId) if get(U.UIA_IsValuePatternAvailablePropertyId) else None
        runtime_id = get(U.UIA_RuntimeIdPropertyId)
        rect = element.CachedBoundingRectangle
        return ElementInfo(
            role=ROLES.get(element.CachedControlType, "element"),
            name=element.CachedName or "",
            automation_id=element.CachedAutomationId or "",
            runtime_id=tuple(runtime_id) if runtime_id else None,
            rect=(rect.left, rect.top, rect.right, rect.bottom),
            actions=tuple(actions),
            value=value if isinstance(value, str) else None,
        )

    def children(self, element) -> list[object]:
        kids = []
        try:
            child = self.walker.GetFirstChildElementBuildCache(element, self.cache)
            while child:
                kids.append(child)
                child = self.walker.GetNextSiblingElementBuildCache(child, self.cache)
        except comtypes.COMError:
            pass  # the element went away mid-read; what was read so far is still useful
        return kids

    def same(self, a, b) -> bool:
        return bool(self.uia.CompareElements(a, b))

    def perform(self, element, action: str) -> None:
        pattern_id, interface, method = PATTERNS[action]
        try:
            getattr(element.GetCurrentPattern(pattern_id).QueryInterface(interface), method)()
        except comtypes.COMError as error:
            raise GhostError(f"{action} failed: the app refused it ({error.text or hex(error.hresult)}). Read the window again.") from None

    def set_value(self, element, text: str) -> bool:
        if not element.GetCachedPropertyValue(U.UIA_IsValuePatternAvailablePropertyId):
            return False
        try:
            element.GetCurrentPattern(U.UIA_ValuePatternId).QueryInterface(U.IUIAutomationValuePattern).SetValue(text)
        except comtypes.COMError as error:
            raise GhostError(f"setting the text failed: the app refused it ({error.text or hex(error.hresult)})") from None
        return True
```

- [ ] **Step 3: Run the real tests and the unit tests**

Open Kazumi first (`D:\Tools\Kazumi\kazumi.exe`) so the Flutter test runs instead of skipping.
Run: `uv run pytest -m real tests/test_uia_real.py -v` then `uv run pytest -v`
Expected: 3 passed (real); 50 passed (unit).

- [ ] **Step 4: Commit**

```bash
git add desktop/src/ghosthand/uia.py desktop/tests/test_uia_real.py
git commit -m "Add the COM UI Automation backend"
```

---

### Task 9: MCP server on one UIA thread

**Files:**
- Create: `desktop/src/ghosthand/server.py`
- Test: `desktop/tests/test_server.py`

**Interfaces:**
- Consumes: `Desktop` (Task 6), `UiaBackend` (Task 8), `Win32` (Task 7), `GhostError` (Task 1).
- Produces: module `ghosthand.server` with `server: MCPServer` named `ghosthand` exposing exactly eight tools — `windows()`, `launch(target, args=None, timeout=20.0)`, `read(window, ref=None, query=None)`, `act(ref, action="auto")`, `set_text(ref, text, submit=False)`, `keys(window, keys, allow_focus=False)`, `wait_for(window, text, gone=False, timeout=10.0)`, `screenshot(window) -> Image`; module global `_desktop` (tests replace it); `main()` (the `ghosthand` console script).

- [ ] **Step 1: Write the failing tests**

`desktop/tests/test_server.py`:

```python
import asyncio

import pytest
from fakes import FakeBackend, FakeElement, FakeWin, window_info
from mcp.server.mcpserver.exceptions import ToolError

from ghosthand import server
from ghosthand.desktop import Desktop


@pytest.fixture
def desktop(monkeypatch):
    editor = FakeElement("window", "Editor", rid=(1,)).add(FakeElement("button", "Save", rid=(1, 1), actions=("press",)))
    desk = Desktop(FakeBackend({100: editor}), FakeWin(window_info(100, "Editor", "notepad")), sleep=lambda seconds: None)
    monkeypatch.setattr(server, "_desktop", desk)
    return desk


def call(name, arguments):
    return asyncio.run(server.server.call_tool(name, arguments)).content


def test_all_eight_tools_are_offered():
    names = {tool.name for tool in asyncio.run(server.server.list_tools())}
    assert names == {"windows", "launch", "read", "act", "set_text", "keys", "wait_for", "screenshot"}


def test_read_and_act_go_through_the_desktop(desktop):
    assert 'e2 button "Save" [press]' in call("read", {"window": "notepad"})[0].text
    assert call("act", {"ref": "e2"})[0].text.startswith("press e2: done")


def test_errors_come_back_as_plain_messages(desktop):
    with pytest.raises(ToolError, match="unknown ref e99: read the window first"):
        asyncio.run(server.server.call_tool("act", {"ref": "e99"}))


def test_screenshot_is_a_png_image(desktop):
    content = call("screenshot", {"window": "notepad"})
    assert content[0].type == "image" and content[0].mime_type == "image/png"
```

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL with `ImportError: cannot import name 'server' from 'ghosthand'`.

- [ ] **Step 2: Write the server**

`desktop/src/ghosthand/server.py`:

```python
from __future__ import annotations

import asyncio
import ctypes
from concurrent.futures import ThreadPoolExecutor

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ghosthand.desktop import Desktop
from ghosthand.model import GhostError

INSTRUCTIONS = (
    "Mouse-free control of Windows apps. Call read on a window, then act/set_text on the refs it "
    "shows; each action returns the window's fresh state. Use wait_for instead of sleeping. "
    "ghosthand never moves the mouse: on 'needs a real click', take a screenshot and tell KaiC."
)

server = MCPServer("ghosthand", instructions=INSTRUCTIONS)
_desktop: Desktop | None = None


def _start_com() -> None:
    import comtypes

    comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)


# COM objects belong to the thread that made them, and the SDK runs each call on whichever
# worker thread is free, so every UI Automation call goes through this one thread.
_uia_thread = ThreadPoolExecutor(max_workers=1, initializer=_start_com, thread_name_prefix="uia")


def _make_desktop() -> Desktop:
    from ghosthand.uia import UiaBackend
    from ghosthand.win32 import Win32

    return Desktop(UiaBackend(), Win32())


async def _call(method: str, *args):
    def work():
        global _desktop
        if _desktop is None:
            _desktop = _make_desktop()
        return getattr(_desktop, method)(*args)

    try:
        return await asyncio.get_running_loop().run_in_executor(_uia_thread, work)
    except GhostError as error:
        raise ToolError(str(error)) from None


@server.tool()
async def windows() -> str:
    """List open windows: number, app, title, and which one is in front."""
    return await _call("windows")


@server.tool()
async def launch(target: str, args: list[str] | None = None, timeout: float = 20.0) -> str:
    """Start an app (an .exe path, a name like notepad, or a URI like calculator:) and read its new window."""
    return await _call("launch", target, args or [], timeout)


@server.tool()
async def read(window: str, ref: str | None = None, query: str | None = None) -> str:
    """Read one window, one line per element: e12 button "Save" [press].

    window is a number from windows, an app name or part of a title. ref reads only that
    element's subtree; query lists only elements whose text contains it.
    """
    return await _call("read", window, ref, query)


@server.tool()
async def act(ref: str, action: str = "auto") -> str:
    """Use an element without the mouse. auto picks press, toggle, select, expand or default. Returns the fresh window."""
    return await _call("act", ref, action)


@server.tool()
async def set_text(ref: str, text: str, submit: bool = False) -> str:
    """Put text straight into a field; submit=true then presses Enter in the background."""
    return await _call("set_text", ref, text, submit)


@server.tool()
async def keys(window: str, keys: str, allow_focus: bool = False) -> str:
    """Send keys such as "enter", "tab tab", "f5" in the background.

    Combinations like ctrl+s need allow_focus=true, which brings the window to the front:
    ask KaiC before using it.
    """
    return await _call("keys", window, keys, allow_focus)


@server.tool()
async def wait_for(window: str, text: str, gone: bool = False, timeout: float = 10.0) -> str:
    """Wait until text appears in a window (or disappears with gone=true), then return the fresh window."""
    return await _call("wait_for", window, text, gone, timeout)


@server.tool()
async def screenshot(window: str) -> Image:
    """A picture of one window, even when other windows cover it."""
    return Image(data=await _call("screenshot", window), format="png")


def main() -> None:
    # Physical pixels everywhere, so element positions and screenshots match the screen.
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    server.run("stdio")
```

- [ ] **Step 3: Run the tests**

Run: `uv run pytest -v`
Expected: 54 passed.

- [ ] **Step 4: Check the server starts and answers over stdio**

Run (from `desktop/`): `uv run python -c "import subprocess,json,time; p=subprocess.Popen(['uv','run','ghosthand'],stdin=subprocess.PIPE,stdout=subprocess.PIPE); t=time.time(); p.stdin.write((json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'t','version':'1'}}})+'\n').encode()); p.stdin.flush(); print(p.stdout.readline()[:120], round(time.time()-t,2),'s'); p.kill()"`
Expected: a JSON line containing `"serverInfo"` and `ghosthand`, printed within about 1 s once the venv exists.

- [ ] **Step 5: Commit**

```bash
git add desktop/src/ghosthand/server.py desktop/tests/test_server.py
git commit -m "Add the ghosthand MCP server, all UI Automation work on one thread"
```

---

### Task 10: Real-app acceptance checks

**Files:**
- Test: `desktop/tests/test_acceptance_real.py` (marked `real`)

**Interfaces:**
- Consumes: `Desktop`, `UiaBackend`, `Win32`.
- Produces: the live-desktop proof of the spec's promises: no cursor movement, focus handed back, Flutter open/back by refs, Chrome's address bar submitted in the background while another window is in front, and the chrome://extensions tooltip loop read without hanging.

- [ ] **Step 1: Write the acceptance tests**

`desktop/tests/test_acceptance_real.py`:

```python
import ctypes
import re
import subprocess
import time

import pytest

from ghosthand.desktop import Desktop
from ghosthand.uia import UiaBackend
from ghosthand.win32 import Win32

pytestmark = pytest.mark.real

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
KAZUMI = r"D:\Tools\Kazumi\kazumi.exe"
BTR_ID = "jcfakgmhohdhbmbcifhlfmiakenjlpcm"


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def cursor():
    point = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def refs(text, pattern):
    return [row.split()[0] for row in text.splitlines() if re.search(pattern, row.strip())]


@pytest.fixture(scope="module")
def desk():
    return Desktop(UiaBackend(), Win32())


def calculator(desk):
    hwnd = next((row.hwnd for row in desk.win.list_windows() if row.title == "Calculator"), None)
    if hwnd is None:
        desk.launch("calculator:")
        hwnd = next(row.hwnd for row in desk.win.list_windows() if row.title == "Calculator")
    return hwnd


@pytest.fixture
def chrome_window(desk):
    before = {row.hwnd for row in desk.win.list_windows()}
    subprocess.Popen([CHROME, "--new-window", "about:blank"])
    fresh = []
    for _ in range(40):
        time.sleep(0.25)
        fresh = [row for row in desk.win.list_windows() if row.hwnd not in before and row.app == "chrome"]
        if fresh:
            break
    assert fresh, "no new Chrome window"
    time.sleep(1)
    yield fresh[0].hwnd
    ctypes.windll.user32.PostMessageW(fresh[0].hwnd, 0x0010, 0, 0)


def test_calculator_without_the_mouse(desk):
    start = cursor()
    text = desk.read(calculator(desk))
    for key in ("Clear", "Seven", "Multiply by", "Six", "Equals"):
        text = desk.act(refs(text, rf'^e\d+ button "{key}"')[0])
    assert "Display is 42" in text
    assert cursor() == start


def test_kazumi_open_a_card_and_go_back(desk):
    start, front = cursor(), desk.win.foreground()
    if not any(row.app == "kazumi" for row in desk.win.list_windows()):
        desk.launch(KAZUMI)
    home = desk.wait_for("kazumi", "热门番组")
    card_row = next(row.strip() for row in home.splitlines() if re.match(r'^e\d+ image "', row.strip()))
    card, title = card_row.split()[0], card_row.split('"')[1]
    desk.act(card)
    detail = desk.wait_for("kazumi", "更多操作")
    unnamed = [re.match(r"^(e\d+) button @(\d+),(\d+)", row.strip()) for row in detail.splitlines()]
    back = min((match for match in unnamed if match), key=lambda match: int(match[2]) + int(match[3]))[1]
    desk.act(back)
    assert title in desk.wait_for("kazumi", title)
    assert cursor() == start
    assert desk.win.foreground() == front
    assert any(row.app == "kazumi" for row in desk.win.list_windows())


def test_chrome_address_bar_works_while_another_window_is_in_front(desk, chrome_window):
    start = cursor()
    calc = calculator(desk)
    assert desk.win.set_foreground(calc)
    bar = refs(desk.read(chrome_window), r'^e\d+ edit "Address and search bar"')[0]
    desk.set_text(bar, "https://example.com/", submit=True)
    assert "Example Domain" in desk.wait_for(chrome_window, "Example Domain")
    assert desk.win.foreground() == calc
    assert cursor() == start


def test_extensions_page_survives_the_tooltip_loop(desk, chrome_window):
    bar = refs(desk.read(chrome_window), r'^e\d+ edit "Address and search bar"')[0]
    desk.set_text(bar, f"chrome://extensions/?id={BTR_ID}", submit=True)
    page = desk.wait_for(chrome_window, "Inspect views")
    reload_ref = refs(page, r'^e\d+ button "Reload"')[-1]
    started = time.perf_counter()
    after = desk.act(reload_ref)
    if "Reloaded" not in after:
        after = desk.wait_for(chrome_window, "Reloaded", timeout=3)
    assert "Reloaded" in after
    assert time.perf_counter() - started < 5
```

- [ ] **Step 2: Run them on the live desktop**

Kazumi may be open or closed; Chrome's main window stays untouched (the tests use their own windows).
Run: `uv run pytest -m real tests/test_acceptance_real.py -v`
Expected: 4 passed. If `test_kazumi_open_a_card_and_go_back` fails only on the last focus assertion, Windows refused the hand-back: record it in the README's known limits rather than weakening the test.

- [ ] **Step 3: Commit**

```bash
git add desktop/tests/test_acceptance_real.py
git commit -m "Add live-desktop acceptance checks"
```

---

### Task 11: Cookie-export extension

**Files:**
- Create: `cookie-export/manifest.json`, `cookie-export/popup.html`, `cookie-export/popup.js`, `cookie-export/cookies.js`, `cookie-export/package.json`
- Test: `cookie-export/cookies.test.mjs`

**Interfaces:**
- Produces: `toPlaywrightCookies(chromeCookies) -> Array<{name, value, domain, path, expires, httpOnly, secure, sameSite}>` (Playwright `addCookies` shape: session cookies get `expires: -1`, `sameSite` mapped `no_restriction→None`, `lax→Lax`, `strict→Strict`, `unspecified→Lax`); an MV3 popup that, for the sites KaiC types, requests host access, reads `chrome.cookies.getAll`, and downloads `Downloads\ghosthand\cookies.json`.

- [ ] **Step 1: Write the failing test**

`cookie-export/package.json`:

```json
{
  "private": true,
  "type": "module"
}
```

`cookie-export/cookies.test.mjs`:

```js
import assert from "node:assert/strict";
import { test } from "node:test";
import { toPlaywrightCookies } from "./cookies.js";

test("session and persistent cookies keep their meaning", () => {
  const out = toPlaywrightCookies([
    { name: "SESSDATA", value: "v1", domain: ".bilibili.com", path: "/", session: false, expirationDate: 1790000000.5, httpOnly: true, secure: true, sameSite: "no_restriction" },
    { name: "buvid3", value: "v2", domain: "www.bilibili.com", path: "/", session: true, httpOnly: false, secure: false, sameSite: "unspecified" },
  ]);
  assert.deepEqual(out, [
    { name: "SESSDATA", value: "v1", domain: ".bilibili.com", path: "/", expires: 1790000000, httpOnly: true, secure: true, sameSite: "None" },
    { name: "buvid3", value: "v2", domain: "www.bilibili.com", path: "/", expires: -1, httpOnly: false, secure: false, sameSite: "Lax" },
  ]);
});

test("strict and lax map straight across", () => {
  const out = toPlaywrightCookies([
    { name: "a", value: "", domain: "x.com", path: "/", session: true, httpOnly: false, secure: true, sameSite: "strict" },
    { name: "b", value: "", domain: "x.com", path: "/", session: true, httpOnly: false, secure: true, sameSite: "lax" },
  ]);
  assert.deepEqual(out.map((c) => c.sameSite), ["Strict", "Lax"]);
});
```

Run (from `cookie-export/`): `node --test`
Expected: FAIL with `Cannot find module '.../cookies.js'`.

- [ ] **Step 2: Write the extension**

`cookie-export/cookies.js`:

```js
const SAME_SITE = { no_restriction: "None", lax: "Lax", strict: "Strict", unspecified: "Lax" };

export function toPlaywrightCookies(cookies) {
  return cookies.map((c) => ({
    name: c.name,
    value: c.value,
    domain: c.domain,
    path: c.path,
    expires: c.session ? -1 : Math.floor(c.expirationDate),
    httpOnly: c.httpOnly,
    secure: c.secure,
    sameSite: SAME_SITE[c.sameSite] ?? "Lax",
  }));
}
```

`cookie-export/manifest.json`:

```json
{
  "manifest_version": 3,
  "name": "ghosthand cookie export",
  "version": "0.1.0",
  "description": "Exports the cookies of sites you pick, for ghosthand's test Chrome. Runs only while its popup is open.",
  "permissions": ["cookies", "downloads"],
  "optional_host_permissions": ["https://*/*", "http://*/*"],
  "action": { "default_popup": "popup.html", "default_title": "Export cookies for ghosthand" }
}
```

`cookie-export/popup.html`:

```html
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      body { font: 13px system-ui, sans-serif; width: 300px; margin: 12px; }
      input { width: 100%; box-sizing: border-box; padding: 6px; }
      button { margin-top: 8px; padding: 6px 12px; }
      #status { margin-top: 8px; white-space: pre-wrap; }
    </style>
  </head>
  <body>
    <label for="sites">Sites (space or comma separated)</label>
    <input id="sites" value="bilibili.com" />
    <button id="export">Export cookies</button>
    <div id="status"></div>
    <script type="module" src="popup.js"></script>
  </body>
</html>
```

`cookie-export/popup.js`:

```js
import { toPlaywrightCookies } from "./cookies.js";

const sites = document.getElementById("sites");
const status = document.getElementById("status");

document.getElementById("export").addEventListener("click", async () => {
  const domains = sites.value.split(/[\s,]+/).map((d) => d.trim().replace(/^\.+/, "")).filter(Boolean);
  if (!domains.length) {
    status.textContent = "Type at least one site.";
    return;
  }
  // Must be the first await: Chrome only shows the permission prompt during the click.
  const origins = domains.flatMap((d) => [`https://${d}/*`, `https://*.${d}/*`, `http://${d}/*`, `http://*.${d}/*`]);
  if (!(await chrome.permissions.request({ origins }))) {
    status.textContent = "Permission refused; nothing exported.";
    return;
  }
  const cookies = (await Promise.all(domains.map((domain) => chrome.cookies.getAll({ domain })))).flat();
  const json = JSON.stringify(toPlaywrightCookies(cookies));
  const binary = Array.from(new TextEncoder().encode(json), (byte) => String.fromCharCode(byte)).join("");
  const url = "data:application/json;base64," + btoa(binary);
  await chrome.downloads.download({ url, filename: "ghosthand/cookies.json", conflictAction: "overwrite", saveAs: false });
  status.textContent = `Exported ${cookies.length} cookies from ${domains.join(", ")} to Downloads\\ghosthand\\cookies.json.\nAsk Claude to import them; the file is deleted after.`;
});
```

- [ ] **Step 3: Run the test**

Run (from `cookie-export/`): `node --test`
Expected: 2 passed.

- [ ] **Step 4: Manual check in the real Chrome (KaiC)**

1. Open `chrome://extensions` in your real Chrome, Developer mode on, **Load unpacked** → `D:\Repos\Tools\ghosthand\cookie-export`.
2. Click the extension's icon, keep `bilibili.com`, click **Export cookies**, allow the permission prompt.
Expected: the popup says "Exported N cookies from bilibili.com …" and `Downloads\ghosthand\cookies.json` exists. Claude checks the file's cookie count and names only (never values) with `node -e "const c=require(process.env.USERPROFILE+'/Downloads/ghosthand/cookies.json');console.log(c.length, c.map(x=>x.name).join(','))"` and then deletes it with `Remove-Item "$env:USERPROFILE\Downloads\ghosthand\cookies.json"`.

- [ ] **Step 5: Commit**

```bash
git add cookie-export
git commit -m "Add the cookie-export extension for the test Chrome"
```

---

### Task 12: Plugin packaging, skill and browser smoke test

**Files:**
- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.mcp.json`
- Create: `skills/ghosthand/SKILL.md`
- Create: `scripts/package.json`, `scripts/browser-smoke.mjs`

**Interfaces:**
- Consumes: the `ghosthand` console script (Task 9); `toPlaywrightCookies` output format (Task 11).
- Produces: an installable plugin `ghosthand@ghosthand` whose MCP servers are `ghosthand` (desktop) and `ghosthand-browser` (Playwright MCP 0.0.83 with the permanent profile); the skill `ghosthand`.

- [ ] **Step 1: Write the plugin files**

`.claude-plugin/plugin.json`:

```json
{
  "name": "ghosthand",
  "version": "0.1.0",
  "description": "Mouse-free control of Windows apps plus a DevTools test Chrome, for building and testing apps without touching KaiC's mouse.",
  "author": { "name": "KaiC5504" },
  "license": "MIT",
  "keywords": ["windows", "ui-automation", "testing", "playwright", "mcp"]
}
```

`.claude-plugin/marketplace.json`:

```json
{
  "name": "ghosthand",
  "description": "KaiC's mouse-free desktop and browser automation",
  "owner": { "name": "KaiC5504" },
  "plugins": [
    {
      "name": "ghosthand",
      "source": "./",
      "description": "Mouse-free control of Windows apps plus a DevTools test Chrome."
    }
  ]
}
```

`.mcp.json`:

```json
{
  "mcpServers": {
    "ghosthand": {
      "command": "uv",
      "args": ["--directory", "${CLAUDE_PLUGIN_ROOT}/desktop", "run", "--frozen", "--no-dev", "ghosthand"]
    },
    "ghosthand-browser": {
      "command": "cmd",
      "args": [
        "/c", "npx", "-y", "@playwright/mcp@0.0.83",
        "--browser", "chrome",
        "--user-data-dir", "%LOCALAPPDATA%\\ghosthand\\chrome-profile",
        "--allow-unrestricted-file-access",
        "--caps", "devtools"
      ]
    }
  }
}
```

`skills/ghosthand/SKILL.md`:

````markdown
---
name: ghosthand
description: Use when operating or testing anything on KaiC's Windows PC — native apps (Win32, WinUI, Flutter like Kazumi, Tauri), the real Chrome's own pages such as chrome://extensions, or web pages under development in the ghosthand test Chrome. Covers which tool to use, the read-act loop, never using the mouse, asking before focus, and importing cookies into the test Chrome.
---

# ghosthand

Two MCP servers come with this plugin:

- **ghosthand** (desktop): `windows`, `launch`, `read`, `act`, `set_text`, `keys`, `wait_for`, `screenshot`. Works on any Windows app and on the real Chrome's own UI.
- **ghosthand-browser** (Playwright MCP 0.0.83): a separate test Chrome with its own permanent profile, with console messages, network requests, JavaScript and page snapshots.

## Which one

- A web page you are building or debugging, or anything needing console/network/JS → **ghosthand-browser**.
- Native apps, the real Chrome's own pages (chrome://extensions, settings), Kazumi, Calculator, installers → **ghosthand**.

## The desktop loop

1. `read` the window (a number from `windows`, an app name like `kazumi`, or part of a title). Lines look like `e12 button "Save" [press]`; unnamed controls show their position, e.g. `e8 button @219,27 [press]`.
2. `act` on a ref (or `set_text` for fields). Each action returns the window's fresh state — read that instead of calling `read` again.
3. Use `wait_for` for anything that loads or animates. Never sleep.
4. Confirm the outcome from the tool's own output before saying something worked.

Refs stay valid while their element exists. `stale: … Read the window again` means the element changed or went away: read again and pick the new ref.

## Hard rules

- ghosthand never moves the mouse. On `needs a real click`, take a `screenshot`, show KaiC, and say what needs clicking.
- `keys` with `allow_focus=true` brings a window to the front. Ask KaiC before every use.
- In Kazumi, `关闭` and `退出` in the title bar close the whole app. The way back from a detail page is the unlabeled button at the top left.

## Test Chrome

- The profile lives in `%LOCALAPPDATA%\ghosthand\chrome-profile` and keeps logins between sessions.
- To test BTR there, KaiC loads `Downloads\BTR` once on the test Chrome's `chrome://extensions` (Load unpacked); the profile keeps it.

## Importing cookies from KaiC's real Chrome

1. KaiC clicks the "ghosthand cookie export" extension in his real Chrome and exports the sites he wants. The file lands at `Downloads\ghosthand\cookies.json`.
2. Find the Downloads folder: `(New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path`.
3. Import with `browser_run_code_unsafe`, using this code with the real path in forward slashes:

```js
async (page) => {
  const tmp = await page.context().newPage();
  await tmp.goto("file:///C:/Users/KaiChuan/Downloads/ghosthand/cookies.json");
  const cookies = JSON.parse(await tmp.locator("body").innerText());
  await tmp.close();
  await page.context().addCookies(cookies);
  return `imported ${cookies.length} cookies`;
}
```

4. Delete the file at once: `Remove-Item "<Downloads>\ghosthand\cookies.json"` and confirm it is gone.

Never open, read, print or return the cookie file's contents or any cookie value. The code above returns only a count, and Playwright echoes only the code, which holds no cookies.
````

- [ ] **Step 2: Write the browser smoke test**

`scripts/package.json`:

```json
{
  "private": true,
  "type": "module",
  "dependencies": {
    "@modelcontextprotocol/sdk": "1.32.1",
    "@playwright/mcp": "0.0.83"
  }
}
```

`scripts/browser-smoke.mjs`:

```js
// Checks the Playwright MCP side of the plugin without touching the real profile: console
// messages, and the cookie import path the skill documents (a value never leaves the browser).
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const dir = mkdtempSync(join(tmpdir(), "ghosthand-smoke-"));
const file = join(dir, "cookies.json");
writeFileSync(file, JSON.stringify([{ name: "ghosthand_smoke", value: "SMOKE-SECRET-VALUE", domain: "example.com", path: "/", expires: -1, httpOnly: false, secure: false, sameSite: "Lax" }]));

const client = new Client({ name: "ghosthand-smoke", version: "1" });
await client.connect(new StdioClientTransport({
  command: "node",
  args: ["node_modules/@playwright/mcp/cli.js", "--browser", "chrome", "--isolated", "--headless", "--allow-unrestricted-file-access", "--caps", "devtools"],
}));
const text = (result) => result.content.map((part) => part.text ?? "").join("\n");
let failed = false;
const check = (label, ok) => { console.log(`${ok ? "ok  " : "FAIL"} ${label}`); failed ||= !ok; };

await client.callTool({ name: "browser_navigate", arguments: { url: "https://example.com/" } });
await client.callTool({ name: "browser_evaluate", arguments: { function: "() => console.error('ghosthand smoke console')" } });
check("console messages are readable", text(await client.callTool({ name: "browser_console_messages", arguments: { level: "error" } })).includes("ghosthand smoke console"));

const url = "file:///" + file.replace(/\\/g, "/");
const code = `async (page) => { const tmp = await page.context().newPage(); await tmp.goto(${JSON.stringify(url)}); const cookies = JSON.parse(await tmp.locator("body").innerText()); await tmp.close(); await page.context().addCookies(cookies); return "imported " + cookies.length + " cookies"; }`;
const imported = text(await client.callTool({ name: "browser_run_code_unsafe", arguments: { code } }));
check("cookie import reports a count", imported.includes("imported 1 cookies"));
check("cookie value never appears in the response", !imported.includes("SMOKE-SECRET-VALUE"));
const names = text(await client.callTool({ name: "browser_run_code_unsafe", arguments: { code: "async (page) => (await page.context().cookies('https://example.com')).map((c) => c.name).join(',')" } }));
check("cookie is in the browser", names.includes("ghosthand_smoke"));

await client.close();
rmSync(dir, { recursive: true, force: true });
process.exit(failed ? 1 : 0);
```

- [ ] **Step 3: Run the smoke test**

Run (from `scripts/`): `npm install` then `node browser-smoke.mjs`
Expected: four `ok` lines, exit code 0.

- [ ] **Step 4: Validate, install and warm up the plugin**

Run:

```bash
claude plugin validate D:/Repos/Tools/ghosthand
claude plugin marketplace add D:/Repos/Tools/ghosthand
claude plugin install ghosthand@ghosthand
```

Expected: validation passes; the install reports `ghosthand` installed. Then create the plugin copy's venv so the first start is fast:

```bash
uv --directory "$HOME/.claude/plugins/cache/ghosthand/ghosthand/0.1.0/desktop" sync --frozen --no-dev
claude mcp list
```

Expected: both `plugin:ghosthand:ghosthand` and `plugin:ghosthand:ghosthand-browser` show `✔ Connected`. If the cache path differs, find it with `ls ~/.claude/plugins/cache/ghosthand`.

The profile path is written as `%LOCALAPPDATA%` on purpose: the browser server starts through `cmd /c`, which expands it whether or not Claude Code expands variables in `.mcp.json`. After the first `browser_navigate` in a Claude session, check it landed in the right place:

```bash
ls "$LOCALAPPDATA/ghosthand/chrome-profile"
```

Expected: Chrome profile files such as `Local State` and `Default/`. If instead a folder literally named `%LOCALAPPDATA%` appears in the plugin cache, replace the argument with the absolute path `C:\\Users\\KaiChuan\\AppData\\Local\\ghosthand\\chrome-profile`, reinstall, and check again.

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin .mcp.json skills scripts/package.json scripts/package-lock.json scripts/browser-smoke.mjs
git commit -m "Package ghosthand as a plugin with its skill and a browser smoke test"
```

---

### Task 13: Acceptance benchmark and README

**Files:**
- Create: `bench/` (copied from the 2026-10-12 harness, then extended)
- Create: `bench/results/2026-10-12/*.jsonl` (baseline runs)
- Create: `README.md`

**Interfaces:**
- Consumes: the `ghosthand` console script (Task 9); the four benchmark tasks and their baselines.
- Produces: `node bench.mjs <calc|kazumi|ext|bili> <runs> [tool]` with a fourth contender `gh`; `node summarize.mjs <results dir>...`; the README with install, use, tests, results and known limits.

- [ ] **Step 1: Copy the harness and the baseline results**

```bash
SRC="C:/Users/KaiChuan/AppData/Local/Temp/claude/D--Repos-Apps-Bilibili-thread-ripper/a65d04db-33c0-46ea-9392-d1459027eca1/scratchpad/bench"
mkdir -p bench/results/2026-10-12 bench/out
cp "$SRC"/{servers.mjs,orca.mjs,util.mjs,win.ps1,watch.ps1,bench.mjs,summarize.mjs} bench/
cp "$SRC"/out/{calc,kazumi,ext,bili}.jsonl bench/results/2026-10-12/
```

`bench/package.json`:

```json
{
  "private": true,
  "type": "module",
  "dependencies": {
    "@modelcontextprotocol/sdk": "1.32.1",
    "terminator-mcp-agent": "0.24.28"
  }
}
```

Run (from `bench/`): `npm install`

- [ ] **Step 2: Add ghosthand as a contender**

In `bench/servers.mjs`, add to `SERVERS` (after `term`):

```js
  gh: { command: "uv", args: ["--directory", `${here}/../desktop`, "run", "--frozen", "--no-dev", "ghosthand"], env: { ...process.env } },
```

In `bench/bench.mjs`:

Replace line `const TOOLS = onlyTool ? [onlyTool] : ["orca", "wmcp", "term"];` with:

```js
const TOOLS = onlyTool ? [onlyTool] : ["orca", "wmcp", "term", "gh"];
```

Replace line `const KAZUMI_CARD = "药屋少女的呢喃 第三季";` with:

```js
// Kazumi's popular list changes; set BENCH_KAZUMI_CARD to a card that is on screen today.
const KAZUMI_CARD = process.env.BENCH_KAZUMI_CARD || "药屋少女的呢喃 第三季";
```

Replace the `let wmcp = null, term = null;` line and `ensure` function with:

```js
let wmcp = null, term = null, gh = null;
async function ensure(which) {
  if (which === "wmcp" && !wmcp) wmcp = await connect("wmcp");
  if (which === "term" && !term) term = await connect("term");
  if (which === "gh" && !gh) gh = await connect("gh");
}
```

After the `termClick` function, add:

```js
async function G(r, name, args = {}, timeout = 30000) {
  const res = await call(gh.client, name, args, timeout);
  r.calls++; r.outBytes += res.bytes;
  if (res.text.startsWith("THROW")) { gh = null; throw new Fail(`gh ${name}: ${res.text.slice(6, 160)}`); }
  if (res.isError) throw new Fail(`gh ${name}: ${res.text.slice(0, 160)}`);
  return res.text;
}
const ghRef = (text, re) => (text.split("\n").map((l) => l.trim()).find((l) => re.test(l)) || "").split(" ")[0] || null;
```

In the `calc` object, add a `gh` method after `term`:

```js
  async gh(r) {
    let text = await G(r, "read", { window: "Calculator" });
    for (const k of CALC_KEYS) {
      const ref = ghRef(text, new RegExp(`^e\\d+ button "${k}"`));
      if (!ref) throw new Fail(`no ${k}`);
      text = await G(r, "act", { ref });
    }
    return /Display is 42\b/.test(text);
  },
```

In the `kazumi` object, add a `gh` method after `term`:

```js
  async gh(r) {
    const text = await G(r, "read", { window: "kazumi" });
    const card = ghRef(text, new RegExp(`^e\\d+ image "${KAZUMI_CARD}"`));
    if (!card) throw new Fail("card not in read");
    await G(r, "act", { ref: card });
    const detail = await G(r, "wait_for", { window: "kazumi", text: "更多操作", timeout: 5 });
    const back = detail.split("\n").map((l) => l.trim().match(/^(e\d+) button @(\d+),(\d+)/)).filter(Boolean)
      .sort((a, b) => (+a[2] + +a[3]) - (+b[2] + +b[3]))[0];
    if (!back) throw new Fail("no unlabeled back button");
    await sleep(KAZUMI_SETTLE_MS);
    await G(r, "act", { ref: back[1] });
    await G(r, "wait_for", { window: "kazumi", text: KAZUMI_CARD, timeout: 5 });
    return true;
  },
```

In `chromeTask`, add `ghWait, ghMarker, ghVerify` to the destructured parameters and a `gh` method after `term`:

```js
    async gh(r, w) {
      const win = String(w.h);
      const bar = ghRef(await G(r, "read", { window: win }), /^e\d+ edit "Address and search bar"/);
      if (!bar) throw new Fail("no address bar");
      await G(r, "set_text", { ref: bar, text: url, submit: true });
      const page = await G(r, "wait_for", { window: win, text: ghWait, timeout: 10 });
      const hits = page.split("\n").map((l) => l.trim()).filter((l) => ghMarker.test(l));
      const target = pickLast ? (hits.length > 1 && hits.pop()) : hits[0];
      if (!target) throw new Fail("marker never appeared");
      const after = await G(r, "act", { ref: target.split(" ")[0] });
      if (ghVerify.test(after)) return true;
      try {
        await G(r, "wait_for", { window: win, text: ghVerify.source, timeout: 2 });
        return true;
      } catch {
        return false;
      }
    },
```

Extend the two `chromeTask` calls:

```js
const ext = chromeTask({
  url: EXT_URL,
  orcaMarker: /button Reload$/, orcaVerify: /text Reloaded/, pickLast: true,
  wmcpMarker: (e) => e.type === "Button" && e.name === "Reload", wmcpVerify: (v) => /Reloaded/.test(v.text),
  termMarker: "Reload", termTitle: "Extensions", termVerify: /Reloaded/,
  ghWait: "Inspect views", ghMarker: /^e\d+ button "Reload"/, ghVerify: /Reloaded/
});
const bili = chromeTask({
  url: BILI_URL,
  orcaMarker: /button 线程撕裂者设置$/, orcaVerify: /目前总线程/,
  wmcpMarker: (e) => e.type === "Button" && e.name === "线程撕裂者设置", wmcpVerify: (v) => v.els.some((e) => /Debug 模式/.test(e.name)),
  termMarker: "线程撕裂者设置", termTitle: "bilibili", termVerify: /目前总线程/,
  ghWait: "线程撕裂者设置", ghMarker: /^e\d+ button "线程撕裂者设置"/, ghVerify: /目前总线程/
});
```

At the end, after `await term?.client.close().catch(() => {});`, add:

```js
await gh?.client.close().catch(() => {});
```

Replace `bench/summarize.mjs` with:

```js
// node summarize.mjs <results dir>...   e.g. node summarize.mjs results/2026-10-12 out
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const med = (a) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor((s.length - 1) / 2)] : NaN; };
const rows = process.argv.slice(2).flatMap((dir) => readdirSync(dir).filter((f) => f.endsWith(".jsonl"))
  .flatMap((f) => readFileSync(join(dir, f), "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l))));
for (const task of ["calc", "kazumi", "ext", "bili"]) {
  const forTask = rows.filter((r) => r.task === task);
  if (!forTask.length) continue;
  console.log(`\n== ${task}`);
  for (const tool of [...new Set(forTask.map((r) => r.tool))]) {
    const r = forTask.filter((x) => x.tool === tool);
    const done = r.filter((x) => x.ok === true || (x.ok === null && x.neutralOk));
    console.log(tool.padEnd(5), `done ${done.length}/${r.length}`, `self-verified ${r.filter((x) => x.ok === true).length}/${r.length}`,
      `median ${(med(r.map((x) => x.ms)) / 1000).toFixed(1)}s`, `ok-median ${(med(done.map((x) => x.ms)) / 1000).toFixed(1)}s`,
      `calls ${med(r.map((x) => x.calls))}`, `out ${(med(r.map((x) => x.outBytes)) / 1024).toFixed(1)}KB`,
      `mouse ${r.filter((x) => x.mouseMoved).length}/${r.length}`, `focus ${r.filter((x) => x.focusChanges).length}/${r.length}`);
  }
}
```

In `bench/bench.mjs`, make sure the output folder exists by adding after the imports:

```js
import { mkdirSync } from "node:fs";
mkdirSync("out", { recursive: true });
```

- [ ] **Step 3: Run ghosthand through the four tasks**

Close the cookie and test windows; keep Kazumi open on its home page. Pick a Kazumi card that is on screen today and set it, then run (from `bench/`):

```bash
export BENCH_KAZUMI_CARD="<a card title from Kazumi's home page>"
node bench.mjs calc 5 gh
node bench.mjs kazumi 3 gh
node bench.mjs ext 3 gh
node bench.mjs bili 3 gh
node summarize.mjs results/2026-10-12 out
```

Expected (the spec's done criteria): `gh` done 5/5 calc (self-verified 5/5), 3/3 kazumi, 3/3 ext, 3/3 bili (≥ 13/14 overall); `mouse 0/n` and `focus` hand-backs on every row; median times at or under calc 3.1 s, kazumi 3.3 s, ext 8.6 s, bili 4.8 s (speed is a target, not a blocker).

- [ ] **Step 4: Write the README**

`README.md`:

````markdown
# ghosthand

Mouse-free control of Windows apps and a DevTools test Chrome, as one Claude Code plugin.
It reads one window at a time through Windows UI Automation, gives every element a short
ref, and uses apps only through accessibility actions — it never moves your mouse.

## Install

```bash
claude plugin marketplace add D:/Repos/Tools/ghosthand
claude plugin install ghosthand@ghosthand
uv --directory "$HOME/.claude/plugins/cache/ghosthand/ghosthand/0.1.0/desktop" sync --frozen --no-dev
claude mcp list
```

Both `ghosthand` and `ghosthand-browser` should show as connected. The first browser start
creates the test Chrome profile in `%LOCALAPPDATA%\ghosthand\chrome-profile`.

## What Claude gets

- **ghosthand**: `windows`, `launch`, `read`, `act`, `set_text`, `keys`, `wait_for`, `screenshot`.
- **ghosthand-browser**: Playwright MCP 0.0.83 on a separate Chrome with its own permanent
  profile (console, network, JavaScript, snapshots).
- **cookie-export/**: load it unpacked in your real Chrome to copy a site's logins into the
  test Chrome. The exported file is deleted as soon as it is imported.

## Tests

```bash
cd desktop
uv run pytest            # unit tests, no real apps
uv run pytest -m real    # live desktop: Calculator, Kazumi, Chrome windows
cd ../cookie-export && node --test
cd ../scripts && npm install && node browser-smoke.mjs
```

## Benchmark

`bench/` is the 2026-10-12 comparison of Orca, Windows-MCP and Terminator, with ghosthand
added. `node bench.mjs <calc|kazumi|ext|bili> <runs> [tool]`, then
`node summarize.mjs results/2026-10-12 out`.

<paste the summarize output from Task 13 Step 3 here, as a fenced block>

## Known limits

- Apps that offer no accessibility action for an element get "needs a real click"; ghosthand
  never falls back to the mouse.
- Key combinations (ctrl+s) need the window in front: Claude asks before doing that.
- Some apps pull themselves to the front when used; ghosthand hands focus back, and says so
  when Windows refuses.
````

Replace the `<paste …>` line with the actual summary output from Step 3 before committing.

- [ ] **Step 5: Commit**

```bash
git add bench/servers.mjs bench/orca.mjs bench/util.mjs bench/win.ps1 bench/watch.ps1 bench/bench.mjs bench/summarize.mjs bench/package.json bench/package-lock.json bench/results README.md
git commit -m "Add the acceptance benchmark with ghosthand as a contender, and the README"
```
````
