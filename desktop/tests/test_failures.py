import json

import pytest

from ghosthand.failures import FailureLog


def records(log):
    return [json.loads(line) for line in log.path.read_text("utf-8").splitlines()]


@pytest.fixture
def log(tmp_path):
    return FailureLog(tmp_path / "logs", "9.9.9")


def test_successful_calls_write_nothing(log):
    log.call("read", {"window": "kazumi"}, 0.2)
    assert not log.path.exists()


def test_a_failed_call_is_written_with_the_calls_before_it(log):
    log.call("read", {"window": "kazumi"}, 0.2)
    log.call("act", {"ref": "e7", "action": "auto"}, 0.05, "stale: e7 changed. Read the window again.")

    [record] = records(log)
    assert record["source"] == "ghosthand"
    assert record["version"] == "9.9.9"
    assert record["tool"] == "act"
    assert record["args"] == {"ref": "e7", "action": "auto"}
    assert record["error"].startswith("stale: e7")
    assert "traceback" not in record
    assert [(step["tool"], step["ok"], step["ms"]) for step in record["recent"]] == [("read", True, 200)]


def test_internal_errors_keep_their_traceback(log):
    log.call("read", {"window": 1}, 0.1, "internal error", "Traceback ...\nRuntimeError: boom")
    assert records(log)[0]["traceback"].endswith("RuntimeError: boom")


def test_set_text_logs_only_the_length_of_the_text(log):
    log.call("set_text", {"ref": "e3", "text": "hunter2", "submit": True}, 0.1, "stale")
    log.call("read", {"window": 1}, 0.1, "no window")

    first, second = records(log)
    assert first["args"]["text"] == "<7 chars>"
    assert second["recent"][0]["args"]["text"] == "<7 chars>"
    assert "hunter2" not in log.path.read_text("utf-8")


def test_only_the_last_ten_calls_are_kept(log):
    for number in range(15):
        log.call("read", {"window": number}, 0.01)
    log.call("act", {"ref": "e1"}, 0.01, "stale")

    windows = [step["args"]["window"] for step in records(log)[0]["recent"]]
    assert windows == list(range(5, 15))


def test_a_full_log_rolls_over(tmp_path):
    log = FailureLog(tmp_path, "1", max_bytes=200)
    for number in range(3):
        log.call("act", {"ref": f"e{number}"}, 0.01, "x" * 150)

    assert [r["args"]["ref"] for r in records(log)] == ["e2"]
    older = (tmp_path / "failures.1.jsonl").read_text("utf-8").splitlines()
    assert [json.loads(line)["args"]["ref"] for line in older] == ["e1"]


def test_ai_reports_are_marked_and_carry_the_recent_calls(log):
    log.call("keys", {"window": "notepad", "keys": "enter"}, 0.1)
    path = log.report("enter did nothing", "the dialog closes", "keys")

    [record] = records(log)
    assert path == log.path
    assert (record["source"], record["tool"]) == ("ai", "keys")
    assert (record["what_happened"], record["expected"]) == ("enter did nothing", "the dialog closes")
    assert record["recent"][0]["tool"] == "keys"


def test_an_unwritable_log_never_breaks_a_call_but_a_report_says_so(tmp_path, capsys):
    blocker = tmp_path / "logs"
    blocker.write_text("a file where the folder should be")
    log = FailureLog(blocker, "1")

    log.call("act", {"ref": "e1"}, 0.01, "stale")
    assert "could not write" in capsys.readouterr().err
    with pytest.raises(OSError):
        log.report("x", "y", "")
