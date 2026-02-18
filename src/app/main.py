"""애플리케이션 부트스트랩과 실행 진입점을 담당한다."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from app.adapters.ai_client import StubAIClassifier
from app.adapters.config_loader import load_knowledge, load_runtime_config
from app.adapters.excel_repo import OpenpyxlLedgerRepository
from app.adapters.file_ops import FileSystemRepository
from app.adapters.file_watcher import StableFileWatcher
from app.adapters.logger import JsonLineLogger
from app.adapters.project_doc_classifier import ProjectDocumentClassifier
from app.core.rule_engine import ClassificationService
from app.core.usecases import ProcessFileUseCase
from app.core.validation import PreflightValidator
from app.ui.settings_window import SettingsWindow


# models 폴더 내 기본 파일 경로를 조합한다.
def _default_model_path(name: str) -> Path:
    """`src/app/models` 아래 기본 설정 파일의 절대 경로를 만든다."""
    return Path(__file__).resolve().parent / "models" / name


class AppController:
    """감시 서비스 시작/중지와 파일 처리 콜백 연결을 담당한다."""

    def __init__(self, usecase: ProcessFileUseCase, watcher: StableFileWatcher, logger: JsonLineLogger):
        """실행에 필요한 유스케이스/감시기/로거 의존성을 보관한다."""
        self._usecase = usecase
        self._watcher = watcher
        self._logger = logger
        self._running = False

    # 감시기를 시작하고 상태 이벤트를 남긴다.
    def start(self, _cfg=None) -> None:
        """감시기를 시작하고 상태 이벤트를 남긴다."""
        if self._running:
            return
        self._watcher.start(self._on_file)
        self._running = True
        self._logger.log({"event": "watch_started", "severity": "info", "message": "Watch service started"})

    # 감시기를 중지하고 상태 이벤트를 남긴다.
    def stop(self) -> None:
        """감시기를 중지하고 상태 이벤트를 남긴다."""
        if not self._running:
            return
        self._watcher.stop()
        self._running = False
        self._logger.log({"event": "watch_stopped", "severity": "info", "message": "Watch service stopped"})

    # 감지된 파일을 단일 처리 유스케이스로 위임한다.
    def _on_file(self, path: Path) -> None:
        """감지된 파일을 단일 처리 유스케이스로 위임한다."""
        self._usecase.run(path)


# 설정/지식/어댑터를 조립해 실행 가능한 런타임 객체를 만든다.
def _build_runtime(ledger_config_path: Path, app_config_path: Path, knowledge_path: Path):
    """설정/지식/어댑터를 조립해 실행 가능한 런타임 객체를 만든다."""
    cfg = load_runtime_config(ledger_config_path, app_config_path)
    knowledge = load_knowledge(knowledge_path)

    # 실행 전에 설정/경로/스키마 불일치를 차단한다.
    issues = PreflightValidator().validate(cfg, knowledge)
    if issues:
        details = "\n".join(f"- {issue.field}: {issue.message}" for issue in issues)
        raise RuntimeError(f"Preflight validation failed:\n{details}")

    project_doc_classifier = None
    # 문서번호 분류 설정이 완비된 경우에만 확장 분류기를 주입한다.
    if (
        cfg.project_doc_info_path
        and cfg.project_doc_info_sheet_name
        and cfg.project_doc_info_column_title_doc_no
        and cfg.project_doc_info_column_title_abbr
    ):
        project_doc_classifier = ProjectDocumentClassifier(
            workbook_path=cfg.resolve_path(cfg.project_doc_info_path),
            sheet_name=cfg.project_doc_info_sheet_name,
            column_title_doc_no=cfg.project_doc_info_column_title_doc_no,
            column_title_abbr=cfg.project_doc_info_column_title_abbr,
        )

    classifier = ClassificationService(StubAIClassifier(), project_doc_classifier=project_doc_classifier)
    file_repo = FileSystemRepository()
    ledger_repo = OpenpyxlLedgerRepository(
        cfg.workbook_abs_path(),
        cfg.submission_sheet_name,
        list(cfg.submission_business_columns),
        list(cfg.submission_system_columns),
    )
    logger = JsonLineLogger(cfg.resolve_path("logs"))
    usecase = ProcessFileUseCase(cfg, knowledge, classifier, file_repo, ledger_repo, logger)
    watcher = StableFileWatcher(cfg.source_root_abs_path(), cfg.file_stable_seconds, cfg.scan_interval_seconds)
    return cfg, usecase, watcher, logger


# CLI 옵션에 따라 GUI 모드 또는 무GUI 감시 모드로 실행한다.
def main() -> None:
    """CLI 옵션에 따라 GUI 모드 또는 무GUI 감시 모드로 실행한다."""
    parser = argparse.ArgumentParser(description="Submission automation app")
    parser.add_argument("--nogui", action="store_true", help="Run watcher without GUI")
    parser.add_argument("--ledger-config", default=str(_default_model_path("ledger.config.yaml")))
    parser.add_argument("--app-config", default=str(_default_model_path("app.config.yaml")))
    parser.add_argument("--knowledge", default=str(_default_model_path("문서 목록.json")))
    args = parser.parse_args()

    cfg, usecase, watcher, logger = _build_runtime(Path(args.ledger_config), Path(args.app_config), Path(args.knowledge))
    controller = AppController(usecase, watcher, logger)

    if args.nogui:
        # 무GUI 모드는 Ctrl+C까지 루프를 유지한다.
        controller.start(cfg)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            controller.stop()
        return

    import tkinter as tk

    root = tk.Tk()
    window = SettingsWindow(
        root=root,
        cfg=cfg,
        config_path=Path(args.ledger_config),
        on_start=controller.start,
        on_stop=controller.stop,
    )
    window.bind_logger(logger)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
