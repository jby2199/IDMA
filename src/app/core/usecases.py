"""파일 1건 처리(분류/복사/대장/로그) 유스케이스를 담당한다."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.core.entities import EventLogger, FileRepository, Knowledge, LedgerRecord, LedgerRepository, ProcessOutcome
from app.core.rule_engine import ClassificationService
from app.models.config_schema import RuntimeConfig


class ProcessFileUseCase:
    """입력 파일 1건을 끝까지 처리하는 애플리케이션 유스케이스."""

    def __init__(self, cfg: RuntimeConfig, knowledge: Knowledge, classifier: ClassificationService, file_repo: FileRepository, ledger_repo: LedgerRepository, logger: EventLogger):
        """실행에 필요한 설정/지식/어댑터를 주입받는다."""
        self._cfg = cfg
        self._knowledge = knowledge
        self._classifier = classifier
        self._file_repo = file_repo
        self._ledger_repo = ledger_repo
        self._logger = logger

    # 감지 -> 분류 -> 복사 -> 대장기록 -> 결과로그 순서로 처리한다.
    def run(self, file_path: Path) -> ProcessOutcome:
        """파일 1건을 처리하고 최종 결과를 반환한다."""
        processed_at = datetime.now().isoformat(timespec="seconds")
        self._logger.log(
            {
                "event": "file_detected",
                "severity": "info",
                "message": f"Detected file: {file_path.name}",
                "context": {"input_path": str(file_path)},
            }
        )

        try:
            result = self._classifier.classify(
                filename=file_path.name,
                knowledge=self._knowledge,
                full_name_min_ratio=self._cfg.full_name_min_ratio,
                ai_threshold=self._cfg.ai_confidence_threshold,
            )
            self._logger.log(
                {
                    "event": "classification_done",
                    "severity": "info",
                    "message": f"Classification: {result.method}",
                    "context": {
                        "input_path": str(file_path),
                        "method": result.method,
                        "phase": result.phase,
                        "artifact_abbr": result.artifact_abbr,
                        "confidence": result.confidence,
                    },
                }
            )

            # 분류 실패 시 Fallback 정책으로 project_root에 안전 배치한다.
            if result.phase is None or result.artifact_abbr is None:
                if not self._cfg.fallback_enabled:
                    raise RuntimeError("Classification failed and fallback is disabled")
                target_dir = self._cfg.project_root
                phase = "Fallback"
                artifact_abbr = "Fallback"
                method = "Fallback"
                error_message = result.reason
                target_folder = "project_root"
            else:
                target_dir = self._cfg.phase_folder_abs_path(result.phase)
                phase = result.phase
                artifact_abbr = result.artifact_abbr
                method = result.method
                error_message = ""
                target_folder = self._cfg.phase_folders.get(result.phase, result.phase)

            copied_path = self._file_repo.copy_with_suffix(file_path, target_dir, self._cfg.duplicate_suffix_start)
            self._logger.log(
                {
                    "event": "file_copied",
                    "severity": "info",
                    "message": f"Copied file to {copied_path}",
                    "context": {"input_path": str(file_path), "result_path": str(copied_path)},
                }
            )

            record = LedgerRecord(
                original_filename=file_path.name,
                phase=phase,
                artifact_abbr=artifact_abbr,
                classification_method=method,
                ai_confidence=result.ai_confidence,
                result_path=str(copied_path),
                status="Filed",
                error_message=error_message,
                processed_at=processed_at,
            )
            try:
                self._ledger_repo.append_submission(record)
                self._logger.log(
                    {
                        "event": "ledger_write_succeeded",
                        "severity": "info",
                        "message": "Ledger row appended",
                        "context": {
                            "input_path": str(file_path),
                            "result_path": str(copied_path),
                            "sheet": self._cfg.submission_sheet_name,
                        },
                    }
                )
            except Exception as exc:
                # 대장 기록 실패는 별도 이벤트로 먼저 남긴 뒤 상위 예외 처리로 넘긴다.
                self._logger.log(
                    {
                        "event": "ledger_write_failed",
                        "severity": "error",
                        "message": f"Failed to append ledger row: {exc}",
                        "context": {
                            "input_path": str(file_path),
                            "result_path": str(copied_path),
                            "sheet": self._cfg.submission_sheet_name,
                            "error": str(exc),
                        },
                    }
                )
                raise

            self._logger.log(
                {
                    "event": "file_processed",
                    "severity": "info",
                    "message": "File processed successfully",
                    "context": {
                        "input_path": str(file_path),
                        "classification_method": method,
                        "phase": phase,
                        "artifact_abbr": artifact_abbr,
                        "target_folder": target_folder,
                        "result_path": str(copied_path),
                        "fallback": method == "Fallback",
                    },
                }
            )
            return ProcessOutcome(success=True, status="Filed", result_path=copied_path, record=record)
        except Exception as exc:
            record = LedgerRecord(
                original_filename=file_path.name,
                phase="Error",
                artifact_abbr="Error",
                classification_method="Fallback",
                ai_confidence=None,
                result_path="",
                status="Error",
                error_message=str(exc),
                processed_at=processed_at,
            )
            self._logger.log(
                {
                    "event": "file_error",
                    "severity": "error",
                    "message": f"File processing failed: {exc}",
                    "context": {"input_path": str(file_path), "error": str(exc)},
                }
            )
            return ProcessOutcome(success=False, status="Error", result_path=None, record=record)
