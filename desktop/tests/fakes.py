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
