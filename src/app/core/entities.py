"""제출물 자동화 도메인의 공통 타입/엔티티/프로토콜을 정의한다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, Protocol

ClassificationMethod = Literal["Rule-ABBR", "Rule-FULL", "AI", "Fallback"]
Status = Literal["Ready", "Rule-Classified", "AI-Classified", "Fallback", "Filed", "Error"]


@dataclass(frozen=True)
class ArtifactEntry:
    """문서 산출물(약어/전문명/단계) 1건 정보."""

    phase: str
    abbr: str
    full_name: str


@dataclass(frozen=True)
class Knowledge:
    """문서 분류 지식(phase 목록 + artifact 목록)."""

    phases: tuple[str, ...]
    artifacts: tuple[ArtifactEntry, ...]

    # 약어를 대소문자 무시로 조회한다.
    def find_by_abbr(self, abbr: str) -> Optional[ArtifactEntry]:
        """약어에 해당하는 artifact를 반환한다."""
        lowered = abbr.lower()
        for artifact in self.artifacts:
            if artifact.abbr.lower() == lowered:
                return artifact
        return None


@dataclass(frozen=True)
class AIResult:
    """AI 분류기가 반환하는 결과 모델."""

    artifact_abbr: str
    phase: str
    ai_confidence: float
    reason: str = ""


@dataclass(frozen=True)
class ClassificationResult:
    """최종 분류 결과(phase/약어/방식/confidence)."""

    phase: Optional[str]
    artifact_abbr: Optional[str]
    method: ClassificationMethod
    confidence: float
    reason: str
    ai_confidence: Optional[float] = None


@dataclass(frozen=True)
class LedgerRecord:
    """관리대장 기록에 사용되는 레코드 모델."""

    original_filename: str
    phase: str
    artifact_abbr: str
    classification_method: ClassificationMethod
    ai_confidence: Optional[float]
    result_path: str
    status: Status
    error_message: str
    processed_at: str


@dataclass(frozen=True)
class ProcessOutcome:
    """파일 1건 처리의 최종 결과 모델."""

    success: bool
    status: Status
    result_path: Optional[Path]
    record: LedgerRecord


@dataclass(frozen=True)
class ValidationIssue:
    """사전검증에서 발견된 오류 1건."""

    field: str
    message: str


class AIClassifier(Protocol):
    """AI 분류기 어댑터 인터페이스."""

    def classify(self, filename: str, knowledge: Knowledge) -> Optional[AIResult]:
        """파일명 기반 AI 분류 결과를 반환한다."""
        ...


class FileRepository(Protocol):
    """파일 복사/배치 어댑터 인터페이스."""

    def copy_with_suffix(self, src: Path, dst_dir: Path, suffix_start: int) -> Path:
        """중복명 충돌을 피하며 파일을 복사한다."""
        ...


class LedgerRepository(Protocol):
    """관리대장 기록 어댑터 인터페이스."""

    def append_submission(self, record: LedgerRecord) -> None:
        """관리대장에 제출물 행을 추가한다."""
        ...


class EventLogger(Protocol):
    """이벤트 로깅 어댑터 인터페이스."""

    def log(self, event: dict[str, Any]) -> None:
        """구조화 이벤트를 기록한다."""
        ...


class EventSource(Protocol):
    """파일 감시 이벤트 소스 인터페이스."""

    def start(self, callback: Any) -> None:
        """감시를 시작하고 콜백을 등록한다."""
        ...

    def stop(self) -> None:
        """감시를 중지한다."""
        ...
