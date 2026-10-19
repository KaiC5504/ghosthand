from dataclasses import replace

from ghosthand.model import ElementInfo, FieldState, Refused, Unanswered, WindowInfo


class FakeElement:
    def __init__(self, role, name="", *, rid=None, actions=(), value=None, aid="", rect=(0, 0, 10, 10), settable=False, refuses=None, refuses_text=None, focusable=False, password=False):
        self.data = ElementInfo(role=role, name=name, automation_id=aid, runtime_id=rid, rect=rect, actions=tuple(actions), value=value)
        self.children = []
        self.settable = settable
        self.performed = []
        self.on_perform = None
        self.fails = None
        self.refuses = refuses
        self.refuses_text = refuses_text
        self.focusable = focusable
        self.password = password
        self.focused = False
        self.gone = False
        self.unreadable = False

    def add(self, *kids):
        self.children.extend(kids)
        return self


class FakeBackend:
    def __init__(self, windows):
        self.windows = windows

    def root(self, hwnd):
        return self.windows[hwnd]

    def info(self, element):
        return element.data

    def children(self, element):
        if element.fails:
            raise Unanswered(list(element.children), element.fails)
        return list(element.children)

    def perform(self, element, action):
        element.performed.append(action)
        if element.on_perform:
            element.on_perform(action)
        if element.refuses:
            raise Refused(element.refuses)

    def set_value(self, element, text):
        if element.refuses_text:
            raise Refused(element.refuses_text)
        if not element.settable:
            return False
        element.data = replace(element.data, value=text)
        return True

    def field_state(self, element):
        if element.gone:
            raise Refused(0x80040201)
        value = None if element.unreadable else element.data.value
        return FieldState(focused=element.focused, value=value, password=element.password)

    def focus(self, element):
        element.focused = element.focusable


def window_info(hwnd, title, app, pid=1):
    return WindowInfo(hwnd=hwnd, title=title, app=app, pid=pid)


class FakeWin:
    def __init__(self, *rows):
        self.rows = list(rows)
        self.front = rows[0].hwnd if rows else 0
        self.posted = []
        self.texts = []
        self.on_text = None
        self.on_keys = None
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
        if self.on_keys:
            self.on_keys(strokes)

    def post_text(self, hwnd, text):
        self.texts.append((hwnd, text))
        if self.on_text:
            self.on_text(text)

    def send_keys_focused(self, hwnd, strokes):
        self.front = hwnd
        self.focused.append((hwnd, strokes))

    def capture(self, hwnd):
        return b"\x89PNG fake " + str(hwnd).encode()

    def launch(self, target, args):
        if self.on_launch:
            self.on_launch()
        return 4242
