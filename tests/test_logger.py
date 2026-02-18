from pathlib import Path

from app.adapters.logger import JsonLineLogger


def test_logger_subscribe_and_emit(tmp_path: Path) -> None:
    logger = JsonLineLogger(tmp_path)
    events = []

    logger.subscribe(events.append)
    logger.log({"event": "sample", "message": "hello"})

    assert len(events) == 1
    assert events[0]["event"] == "sample"


def test_logger_writes_file(tmp_path: Path) -> None:
    logger = JsonLineLogger(tmp_path)
    logger.log({"event": "file_error", "severity": "error", "message": "failed"})

    files = list(tmp_path.glob("submission_automation_*.jsonl"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert '"file_error"' in content
    assert '"severity": "error"' in content
