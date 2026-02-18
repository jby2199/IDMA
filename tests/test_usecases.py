from pathlib import Path

from app.core.entities import ArtifactEntry, Knowledge
from app.core.rule_engine import ClassificationService
from app.core.usecases import ProcessFileUseCase
from app.models.config_schema import RuntimeConfig


class DummyLedger:
    def __init__(self):
        self.records = []

    def append_submission(self, record):
        self.records.append(record)


class DummyLogger:
    def __init__(self):
        self.events = []

    def log(self, event):
        self.events.append(event)


class FailingLedger:
    def append_submission(self, record):
        _ = record
        raise RuntimeError("ledger write failed")


def _knowledge() -> Knowledge:
    return Knowledge(
        phases=("Design",),
        artifacts=(ArtifactEntry(phase="Design", abbr="SDD", full_name="Software Design Description"),),
    )


def test_usecase_copies_to_phase_folder(tmp_path: Path) -> None:
    (tmp_path / "incoming").mkdir()
    (tmp_path / "design").mkdir()
    source_root = (tmp_path / "incoming").resolve()

    cfg = RuntimeConfig(
        version="1.0",
        project_root=tmp_path,
        workbook_path="book.xlsx",
        source_root=str(source_root),
        phase_folders={"Design": "design"},
    )

    src = tmp_path / "incoming" / "my_sdd.pdf"
    src.write_text("payload", encoding="utf-8")

    from app.adapters.file_ops import FileSystemRepository

    usecase = ProcessFileUseCase(
        cfg=cfg,
        knowledge=_knowledge(),
        classifier=ClassificationService(),
        file_repo=FileSystemRepository(),
        ledger_repo=DummyLedger(),
        logger=DummyLogger(),
    )

    outcome = usecase.run(src)
    assert outcome.success is True
    assert outcome.result_path is not None
    assert outcome.result_path.parent == (tmp_path / "design")


def test_usecase_fallback(tmp_path: Path) -> None:
    (tmp_path / "incoming").mkdir()
    (tmp_path / "design").mkdir()
    source_root = (tmp_path / "incoming").resolve()

    cfg = RuntimeConfig(
        version="1.0",
        project_root=tmp_path,
        workbook_path="book.xlsx",
        source_root=str(source_root),
        phase_folders={"Design": "design"},
    )

    src = tmp_path / "incoming" / "unknown_file.pdf"
    src.write_text("payload", encoding="utf-8")

    from app.adapters.file_ops import FileSystemRepository

    ledger = DummyLedger()
    usecase = ProcessFileUseCase(
        cfg=cfg,
        knowledge=_knowledge(),
        classifier=ClassificationService(),
        file_repo=FileSystemRepository(),
        ledger_repo=ledger,
        logger=DummyLogger(),
    )

    outcome = usecase.run(src)
    assert outcome.success is True
    assert outcome.record.classification_method == "Fallback"
    assert outcome.result_path is not None
    assert outcome.result_path.parent == tmp_path


def test_usecase_logs_ledger_failure(tmp_path: Path) -> None:
    (tmp_path / "incoming").mkdir()
    (tmp_path / "design").mkdir()
    source_root = (tmp_path / "incoming").resolve()

    cfg = RuntimeConfig(
        version="1.0",
        project_root=tmp_path,
        workbook_path="book.xlsx",
        source_root=str(source_root),
        phase_folders={"Design": "design"},
    )

    src = tmp_path / "incoming" / "my_sdd.pdf"
    src.write_text("payload", encoding="utf-8")

    from app.adapters.file_ops import FileSystemRepository

    logger = DummyLogger()
    usecase = ProcessFileUseCase(
        cfg=cfg,
        knowledge=_knowledge(),
        classifier=ClassificationService(),
        file_repo=FileSystemRepository(),
        ledger_repo=FailingLedger(),
        logger=logger,
    )

    outcome = usecase.run(src)
    assert outcome.success is False
    assert any(event.get("event") == "ledger_write_failed" for event in logger.events)
    assert any(event.get("event") == "file_error" for event in logger.events)
