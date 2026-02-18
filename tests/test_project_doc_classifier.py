from pathlib import Path

from app.adapters.project_doc_classifier import ProjectDocumentClassifier
from app.core.entities import ArtifactEntry, Knowledge


def _knowledge() -> Knowledge:
    return Knowledge(
        phases=("Design", "Implementation"),
        artifacts=(
            ArtifactEntry(phase="Design", abbr="SDD", full_name="Software Design Description"),
            ArtifactEntry(phase="Implementation", abbr="STP", full_name="System Test Procedure"),
        ),
    )


def test_project_doc_classifier_postfix_tolerant(tmp_path: Path) -> None:
    import openpyxl

    book = tmp_path / "project.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "두산문서목록"
    ws.append(["문서번호", "문서구분"])
    ws.append(["ABC-123-0001", "STP_revA"])
    wb.save(book)
    wb.close()

    classifier = ProjectDocumentClassifier(
        workbook_path=book,
        sheet_name="두산문서목록",
        column_title_doc_no="문서번호",
        column_title_abbr="문서구분",
    )

    result = classifier.classify("Client_ABC1230001_received.pdf", _knowledge())

    assert result is not None
    assert result.artifact_abbr == "STP"
    assert result.phase == "Implementation"


def test_project_doc_classifier_returns_none_on_no_match(tmp_path: Path) -> None:
    import openpyxl

    book = tmp_path / "project.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "두산문서목록"
    ws.append(["문서번호", "문서구분"])
    ws.append(["XYZ-999", "SDD"])
    wb.save(book)
    wb.close()

    classifier = ProjectDocumentClassifier(
        workbook_path=book,
        sheet_name="두산문서목록",
        column_title_doc_no="문서번호",
        column_title_abbr="문서구분",
    )

    result = classifier.classify("another_file.pdf", _knowledge())
    assert result is None
