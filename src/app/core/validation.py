"""실행 전 설정/경로 정합성을 점검하는 검증 모듈."""

from __future__ import annotations

from app.core.entities import Knowledge, ValidationIssue
from app.models.config_schema import RuntimeConfig


class PreflightValidator:
    """애플리케이션 시작 전 필수 조건을 검증한다."""

    # 설정/지식/경로 검증 결과를 오류 목록으로 반환한다.
    def validate(self, cfg: RuntimeConfig, knowledge: Knowledge) -> list[ValidationIssue]:
        """실행 가능 여부를 검증하고 이슈 목록을 반환한다."""
        issues: list[ValidationIssue] = []

        if not cfg.project_root.exists():
            issues.append(ValidationIssue("project_root", "Project root does not exist"))

        source_root = cfg.source_root_abs_path()
        if not source_root.is_absolute():
            issues.append(ValidationIssue("roots.source_root", "Source root must be an absolute path"))
        elif not source_root.exists():
            issues.append(ValidationIssue("roots.source_root", "Source root does not exist"))

        workbook_parent = cfg.workbook_abs_path().parent
        if not workbook_parent.exists():
            issues.append(ValidationIssue("workbook.path", "Workbook parent directory does not exist"))

        # phase 키 집합이 knowledge phase 집합과 정확히 일치해야 한다.
        if set(cfg.phase_folders.keys()) != set(knowledge.phases):
            issues.append(ValidationIssue("roots.phase_folders", "phase_folders keys must match phases in knowledge"))

        if not (0.0 <= cfg.full_name_min_ratio <= 1.0):
            issues.append(ValidationIssue("rule.full_name_min_ratio", "Must be within [0.0, 1.0]"))

        if not (0.0 <= cfg.ai_confidence_threshold <= 1.0):
            issues.append(ValidationIssue("ai.confidence_threshold", "Must be within [0.0, 1.0]"))

        if cfg.duplicate_suffix_start < 1:
            issues.append(ValidationIssue("duplicate.suffix_start", "Must be >= 1"))

        if cfg.file_stable_seconds < 1:
            issues.append(ValidationIssue("watch.file_stable_seconds", "Must be >= 1"))

        if cfg.scan_interval_seconds < 1:
            issues.append(ValidationIssue("watch.scan_interval_seconds", "Must be >= 1"))

        if not cfg.submission_sheet_name.strip():
            issues.append(ValidationIssue("ledgers.submission.sheet_name", "Sheet name must not be empty"))

        if len(cfg.submission_business_columns) == 0:
            issues.append(ValidationIssue("ledgers.submission.columns", "At least one business column is required"))

        project_doc_fields = [
            cfg.project_doc_info_path,
            cfg.project_doc_info_sheet_name,
            cfg.project_doc_info_column_title_doc_no,
            cfg.project_doc_info_column_title_abbr,
        ]
        # project_doc_info는 부분 설정을 허용하지 않는다.
        if any(project_doc_fields) and not all(project_doc_fields):
            issues.append(
                ValidationIssue(
                    "project_doc_info",
                    "path/sheet_name/column_title_doc_no/column_title_abbr must be configured together",
                )
            )
        if cfg.project_doc_info_path:
            if not cfg.resolve_path(cfg.project_doc_info_path).exists():
                issues.append(ValidationIssue("project_doc_info.path", "Project document info workbook does not exist"))

        for phase, rel_path in cfg.phase_folders.items():
            if not cfg.resolve_path(rel_path).exists():
                issues.append(ValidationIssue(f"roots.phase_folders.{phase}", "Target phase folder does not exist"))

        return issues
