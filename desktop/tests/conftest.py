import csv
import subprocess
import time

import pytest

LAUNCHED_BY_TESTS = ("kazumi.exe", "CalculatorApp.exe")


def pids(image):
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return {int(row[1]) for row in csv.reader(out.splitlines()) if len(row) > 1 and row[0].lower() == image.lower()}


def close(pid):
    subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True)
    for _ in range(20):
        if not any(pid in pids(image) for image in LAUNCHED_BY_TESTS):
            return
        time.sleep(0.25)
    # Calculator's window belongs to ApplicationFrameHost, so a polite close can't reach it.
    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)


@pytest.fixture(scope="session", autouse=True)
def close_what_live_tests_opened(request):
    if not any(item.get_closest_marker("real") for item in request.session.items):
        yield
        return
    before = {image: pids(image) for image in LAUNCHED_BY_TESTS}
    yield
    for image, existing in before.items():
        for pid in pids(image) - existing:
            close(pid)
