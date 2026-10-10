"""애플리케이션 부트스트랩과 실행 진입점을 담당한다."""

from __future__ import annotations

import argparse
import queue
import secrets
import sys
import threading
import time
from collections import Counter
from datetime import datetime
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
    """기본 설정 파일 경로를 실행 환경(개발/패키징)에 맞춰 찾는다."""
    # PyInstaller onefile에서는 임시 풀림 경로(sys._MEIPASS)를 우선 사용한다.
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = (
        bundle_root / "models" / name,
        bundle_root / "app" / "models" / name,
        Path(__file__).resolve().parent / "models" / name,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # 후보가 모두 없으면 첫 번째 기본 경로를 반환해 호출부에서 명확한 에러를 내게 한다.
    return candidates[0]


# 종료 코드 체계(SRS 8.1): 0 정상, 1 검증·헤더 실패, 2 대장 접근 불가, 3 무GUI 세션 중 Error 발생.
EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_LEDGER_INACCESSIBLE = 2
EXIT_FILE_ERRORS = 3

_STOP = object()


class SessionStartError(Exception):
    """감시 세션을 시작하지 못한 이유와 무GUI 종료 코드를 담는다."""

    def __init__(self, exit_code: int, message: str):
        super().__init__(message)
        self.exit_code = exit_code
        self.message = message


# run_id 형식: <YYYYMMDD>-<HHMMSS>-<임의 6자>.
def new_run_id(now: datetime | None = None) -> str:
    """감시 세션 1회의 고유 run_id를 만든다."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(3)}"


class LedgerSessionGuard:
    """감시 세션 시작 시 관리대장의 잠금 확인 -> 백업 -> 헤더 확인을 순서대로 수행한다."""

    def __init__(self, ledger_repo, validator: PreflightValidator, backup_dir: Path, required_headers: list[str], logger: JsonLineLogger):
        """점검에 필요한 대장 어댑터·검증기·백업 폴더·필수 헤더를 보관한다."""
        self._ledger = ledger_repo
        self._validator = validator
        self._backup_dir = backup_dir
        self._required_headers = list(required_headers)
        self._logger = logger

    def check(self, run_id: str) -> None:
        """통과하면 반환하고, 실패하면 SessionStartError를 올린다. 이 단계까지 파일은 이동하지 않는다."""
        # 워크북이 아직 없으면 점검 대상이 없다(첫 행 기록 때 어댑터가 만든다). [가정 A1]
        if not self._ledger.workbook_exists():
            return

        try:
            self._ledger.check_writable()
        except OSError as exc:
            self._fail(run_id, "ledger_locked", EXIT_LEDGER_INACCESSIBLE, f"관리대장에 접근할 수 없습니다(잠김·권한). 관리대장을 닫은 뒤 다시 시작하십시오. 원인: {exc}")

        try:
            backup_path = self._ledger.backup(self._backup_dir, run_id)
        except OSError as exc:
            # 백업 실패의 종료 코드는 SRS에 없다. 접근 불가로 보고 2로 처리한다. [가정 A2]
            self._fail(run_id, "ledger_backup_failed", EXIT_LEDGER_INACCESSIBLE, f"관리대장 백업에 실패했습니다. 원인: {exc}")
        self._logger.log({"event": "ledger_backup_done", "severity": "info", "message": f"Ledger backup: {backup_path}", "context": {"run_id": run_id, "backup_path": str(backup_path)}})

        try:
            found = self._ledger.read_headers()
        except Exception as exc:
            self._fail(run_id, "ledger_header_unreadable", EXIT_BLOCKED, f"관리대장 헤더를 읽지 못했습니다. 원인: {exc}")
        issues = self._validator.check_ledger_headers(self._required_headers, found)
        if issues:
            detail = "; ".join(issue.message for issue in issues)
            self._fail(run_id, "ledger_header_missing", EXIT_BLOCKED, f"관리대장 헤더 검사에 실패했습니다. {detail}")

    def _fail(self, run_id: str, event: str, exit_code: int, message: str) -> None:
        """원인을 로그에 남기고 SessionStartError를 올린다."""
        self._logger.log({"event": event, "severity": "error", "message": message, "context": {"run_id": run_id, "exit_code": exit_code}})
        raise SessionStartError(exit_code, message)


class AppController:
    """감시 세션 시작/중지와 파일 처리 콜백 연결을 담당한다. 파일은 1건씩 직렬로 처리한다."""

    def __init__(self, usecase: ProcessFileUseCase, watcher: StableFileWatcher, logger: JsonLineLogger, session_guard: LedgerSessionGuard | None = None):
        """실행에 필요한 유스케이스/감시기/로거 의존성을 보관한다."""
        self._usecase = usecase
        self._watcher = watcher
        self._logger = logger
        self._guard = session_guard
        self._running = False
        self._accepting = False
        self._queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._run_id = ""
        self._total = 0
        self._error_count = 0
        self._method_counts: Counter = Counter()

    @property
    def run_id(self) -> str:
        """현재(또는 마지막) 감시 세션의 run_id."""
        return self._run_id

    @property
    def error_count(self) -> int:
        """현재(또는 마지막) 세션에서 Error로 끝난 파일 수."""
        return self._error_count

    # 세션 시작 점검을 통과한 뒤에만 처리 작업자와 감시기를 시작한다.
    def start(self, _cfg=None) -> None:
        """세션 시작 점검 후 감시기를 시작하고 상태 이벤트를 남긴다."""
        if self._running:
            return
        run_id = new_run_id()
        if self._guard is not None:
            self._guard.check(run_id)
        self._run_id = run_id
        self._total = 0
        self._error_count = 0
        self._method_counts = Counter()
        self._queue = queue.Queue()
        # 감시기 시작이 실패하면 작업자를 만들지 않는다(콜백은 대기열에 넣기만 하므로 순서가 안전하다).
        self._accepting = True
        try:
            self._watcher.start(self._on_file)
        except Exception:
            self._accepting = False
            raise
        self._worker = threading.Thread(target=self._work, name="idma-serial-worker", daemon=True)
        self._worker.start()
        self._running = True
        self._logger.log({"event": "watch_started", "severity": "info", "message": "Watch service started", "context": {"run_id": run_id}})

    # 감시기를 중지하고, 이미 안정화되어 대기열에 든 파일까지 처리한 뒤 상태 이벤트를 남긴다.
    def stop(self) -> None:
        """감시기를 중지하고 대기열을 비운 뒤 상태 이벤트를 남긴다."""
        if not self._running:
            return
        self._accepting = False  # 중지 뒤 늦게 도착한 콜백은 버린다(대기열 유실·세션 혼입 방지)
        self._watcher.stop()
        self._queue.put(_STOP)
        if self._worker is not None:
            self._worker.join()
            self._worker = None
        self._running = False
        self._logger.log({"event": "watch_stopped", "severity": "info", "message": "Watch service stopped", "context": {"run_id": self._run_id}})

    # 감시기 스레드에서는 대기열에 넣기만 한다. 실제 처리는 작업자 1개가 감지 순서대로 수행한다.
    def _on_file(self, path: Path) -> None:
        """안정화된 파일을 대기열에 넣는다. 세션이 중지 중이면 버린다."""
        if self._accepting:
            self._queue.put(path)

    def _work(self) -> None:
        """대기열의 파일을 1건씩 처리한다. 한 파일의 예외는 다음 파일 처리를 막지 않는다."""
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            self._total += 1
            try:
                outcome = self._usecase.run(item)
            except Exception as exc:
                self._error_count += 1
                self._method_counts["Error"] += 1
                self._logger.log({"event": "file_error", "severity": "error", "message": f"File processing failed: {exc}", "context": {"input_path": str(item), "error": str(exc), "run_id": self._run_id}})
                continue
            if outcome.status == "Error":
                self._error_count += 1
                self._method_counts["Error"] += 1
            else:
                self._method_counts[outcome.record.classification_method] += 1

    def format_summary(self) -> str:
        """무GUI 중단 시 stdout 처리 요약(대상 건수, method별 건수, Error 건수)."""
        methods = ", ".join(f"{name} {self._method_counts.get(name, 0)}건" for name in ("Rule-ABBR", "Rule-FULL", "AI", "Fallback"))
        return f"처리 요약: 대상 {self._total}건, {methods}, Error {self._error_count}건"

    def exit_code(self) -> int:
        """세션 종료 코드: Error 파일이 1건 이상이면 3, 아니면 0."""
        return EXIT_FILE_ERRORS if self._error_count > 0 else EXIT_OK


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
    session_guard = LedgerSessionGuard(
        ledger_repo,
        PreflightValidator(),
        cfg.project_root / "backup",
        ledger_repo.required_headers(),
        logger,
    )
    return cfg, usecase, watcher, logger, session_guard


# CLI 옵션에 따라 GUI 모드 또는 무GUI 감시 모드로 실행한다.
def main() -> int:
    """CLI 옵션에 따라 GUI 모드 또는 무GUI 감시 모드로 실행한다."""
    parser = argparse.ArgumentParser(description="Submission automation app")
    parser.add_argument("--nogui", action="store_true", help="Run watcher without GUI")
    parser.add_argument("--ledger-config", default=str(_default_model_path("ledger.config.yaml")))
    parser.add_argument("--app-config", default=str(_default_model_path("app.config.yaml")))
    parser.add_argument("--knowledge", default=str(_default_model_path("문서 목록.json")))
    args = parser.parse_args()

    cfg, usecase, watcher, logger, session_guard = _build_runtime(Path(args.ledger_config), Path(args.app_config), Path(args.knowledge))
    controller = AppController(usecase, watcher, logger, session_guard)

    if args.nogui:
        # 무GUI 모드는 세션 시작 점검을 통과하면 Ctrl+C까지 루프를 유지한다.
        try:
            controller.start(cfg)
            while True:
                time.sleep(1)
        except SessionStartError as exc:
            print(exc.message, file=sys.stderr)
            return exc.exit_code
        except KeyboardInterrupt:
            pass
        controller.stop()
        print(controller.format_summary())
        code = controller.exit_code()
        if code == EXIT_FILE_ERRORS:
            print(f"Error 상태 파일 {controller.error_count}건이 있어 종료 코드 {code}로 끝냅니다.", file=sys.stderr)
        return code

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
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
