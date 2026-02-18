"""설정 모델과 경로 해석 유틸을 제공하는 모듈."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimeConfig:
    """런타임 동작에 필요한 설정값을 담는 불변 데이터 모델."""

    version: str
    project_root: Path
    workbook_path: str
    source_root: str
    phase_folders: dict[str, str]
    project_doc_info_path: str | None = None
    project_doc_info_sheet_name: str | None = None
    project_doc_info_column_title_doc_no: str | None = None
    project_doc_info_column_title_abbr: str | None = None
    full_name_min_ratio: float = 0.5
    ai_confidence_threshold: float = 0.8
    fallback_enabled: bool = True
    duplicate_suffix_start: int = 1
    scan_interval_seconds: int = 60
    file_stable_seconds: int = 3
    submission_sheet_name: str = "제출물 관리대장"
    submission_business_columns: tuple[str, ...] = ("제출물명", "제출물 형태", "접수일")
    submission_system_columns: tuple[str, ...] = (
        "phase",
        "artifact_abbr",
        "classification_method",
        "ai_confidence",
        "result_path",
        "status",
        "error_message",
        "processed_at",
    )

    # YAML dict를 RuntimeConfig 객체로 변환한다.
    @classmethod
    def from_dict(cls, ledger_data: dict[str, Any], app_data: dict[str, Any] | None = None) -> "RuntimeConfig":
        """ledger/app 설정 dict를 통합해 RuntimeConfig를 생성한다."""
        app_data = app_data or {}
        watch = app_data.get("watch", {})

        full_name_min_ratio = ledger_data.get("rule", {}).get("full_name_min_ratio") if isinstance(ledger_data.get("rule"), dict) else None
        ai_threshold = ledger_data.get("ai", {}).get("confidence_threshold") if isinstance(ledger_data.get("ai"), dict) else None
        fallback_enabled = ledger_data.get("fallback", {}).get("enabled") if isinstance(ledger_data.get("fallback"), dict) else None
        suffix_start = ledger_data.get("duplicate", {}).get("suffix_start") if isinstance(ledger_data.get("duplicate"), dict) else None
        project_doc_info = ledger_data.get("project_doc_info", {})
        if not isinstance(project_doc_info, dict):
            project_doc_info = {}

        submission_sheet_name = "제출물 관리대장"
        submission_business_columns: tuple[str, ...] = ("제출물명", "제출물 형태", "접수일")
        submission_system_columns: tuple[str, ...] = (
            "phase",
            "artifact_abbr",
            "classification_method",
            "ai_confidence",
            "result_path",
            "status",
            "error_message",
            "processed_at",
        )
        ledgers = ledger_data.get("ledgers", {})
        if isinstance(ledgers, dict):
            submission = ledgers.get("submission", {})
            if isinstance(submission, dict):
                submission_sheet_name = submission.get("sheet_name", submission_sheet_name)
                columns = submission.get("columns", [])
                if isinstance(columns, list):
                    names = []
                    for item in columns:
                        if isinstance(item, dict) and "name" in item:
                            names.append(str(item["name"]).strip())
                        elif isinstance(item, str):
                            names.append(item.strip())
                    names = [name for name in names if name]
                    if names:
                        submission_business_columns = tuple(names)

                system_columns = submission.get("system_columns", [])
                if isinstance(system_columns, list):
                    names = []
                    for item in system_columns:
                        if isinstance(item, dict) and "name" in item:
                            names.append(str(item["name"]).strip())
                        elif isinstance(item, str):
                            names.append(item.strip())
                    names = [name for name in names if name]
                    if names:
                        submission_system_columns = tuple(names)

        return cls(
            version=str(ledger_data.get("version", "1.0.0")),
            project_root=Path(str(ledger_data.get("project_root", "."))),
            workbook_path=str(ledger_data.get("workbook", {}).get("path", "")),
            source_root=str(ledger_data.get("roots", {}).get("source_root", "")),
            phase_folders={str(k): str(v) for k, v in ledger_data.get("roots", {}).get("phase_folders", {}).items()},
            project_doc_info_path=(
                str(project_doc_info.get("path")).strip() if project_doc_info.get("path") is not None else None
            ),
            project_doc_info_sheet_name=(
                str(project_doc_info.get("sheet_name")).strip()
                if project_doc_info.get("sheet_name") is not None
                else None
            ),
            project_doc_info_column_title_doc_no=(
                str(project_doc_info.get("column_title_doc_no")).strip()
                if project_doc_info.get("column_title_doc_no") is not None
                else None
            ),
            project_doc_info_column_title_abbr=(
                str(project_doc_info.get("column_title_abbr")).strip()
                if project_doc_info.get("column_title_abbr") is not None
                else None
            ),
            full_name_min_ratio=float(full_name_min_ratio if full_name_min_ratio is not None else 0.5),
            ai_confidence_threshold=float(ai_threshold if ai_threshold is not None else 0.8),
            fallback_enabled=bool(True if fallback_enabled is None else fallback_enabled),
            duplicate_suffix_start=int(suffix_start if suffix_start is not None else 1),
            scan_interval_seconds=int(watch.get("scan_interval_seconds", 60)),
            file_stable_seconds=int(watch.get("file_stable_seconds", 3)),
            submission_sheet_name=str(submission_sheet_name),
            submission_business_columns=submission_business_columns,
            submission_system_columns=submission_system_columns,
        )

    # project_root 기준 상대/절대 경로를 모두 해석한다.
    def resolve_path(self, raw: str | Path) -> Path:
        """입력 경로를 절대경로로 변환한다(상대경로는 project_root 기준)."""
        raw_path = Path(raw)
        if raw_path.is_absolute():
            return raw_path
        return (self.project_root / raw_path).resolve()

    # 관리대장 파일 절대경로를 반환한다.
    def workbook_abs_path(self) -> Path:
        """관리대장 워크북의 절대경로를 반환한다."""
        return self.resolve_path(self.workbook_path)

    # source_root는 절대경로 전용으로 처리한다.
    def source_root_abs_path(self) -> Path:
        """감시 대상 source_root 절대경로를 반환한다."""
        return Path(self.source_root)

    # 단계별 배치 폴더 절대경로를 계산한다.
    def phase_folder_abs_path(self, phase: str) -> Path:
        """주어진 phase의 배치 폴더 절대경로를 반환한다."""
        return self.resolve_path(self.phase_folders[phase])
