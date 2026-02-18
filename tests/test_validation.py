from pathlib import Path

from app.core.entities import ArtifactEntry, Knowledge
from app.core.validation import PreflightValidator
from app.models.config_schema import RuntimeConfig


def _knowledge() -> Knowledge:
    return Knowledge(
        phases=("Design", "Implementation"),
        artifacts=(
            ArtifactEntry(phase="Design", abbr="SDD", full_name="Software Design Description"),
            ArtifactEntry(phase="Implementation", abbr="STP", full_name="System Test Procedure"),
        ),
    )


def test_preflight_phase_mismatch(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "phase_design").mkdir()
    source_root = (tmp_path / "src").resolve()

    cfg = RuntimeConfig(
        version="1.0",
        project_root=tmp_path,
        workbook_path="book.xlsx",
        source_root=str(source_root),
        phase_folders={"Design": "phase_design"},
    )

    issues = PreflightValidator().validate(cfg, _knowledge())
    assert any(i.field == "roots.phase_folders" for i in issues)


def test_resolve_path_uses_project_root(tmp_path: Path) -> None:
    source_root = (tmp_path / "src").resolve()
    cfg = RuntimeConfig(
        version="1.0",
        project_root=tmp_path,
        workbook_path="book.xlsx",
        source_root=str(source_root),
        phase_folders={"Design": "phase_design", "Implementation": "phase_impl"},
    )

    resolved = cfg.resolve_path("data/file.txt")
    assert resolved == (tmp_path / "data" / "file.txt").resolve()


def test_source_root_must_be_absolute(tmp_path: Path) -> None:
    (tmp_path / "phase_design").mkdir()
    (tmp_path / "phase_impl").mkdir()

    cfg = RuntimeConfig(
        version="1.0",
        project_root=tmp_path,
        workbook_path="book.xlsx",
        source_root="relative\\incoming",
        phase_folders={"Design": "phase_design", "Implementation": "phase_impl"},
    )

    issues = PreflightValidator().validate(cfg, _knowledge())
    assert any(i.field == "roots.source_root" and "absolute" in i.message for i in issues)
