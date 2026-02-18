"""phase 해석 보조 유틸 모듈."""

from __future__ import annotations

from app.core.entities import Knowledge


class PhaseResolver:
    """약어(abbr) 기준으로 phase를 조회하는 단순 해석기."""

    @staticmethod
    # knowledge에서 약어를 찾아 대응 phase를 반환한다.
    def resolve_phase(artifact_abbr: str, knowledge: Knowledge) -> str | None:
        """artifact 약어에 대응하는 phase를 반환한다."""
        artifact = knowledge.find_by_abbr(artifact_abbr)
        return artifact.phase if artifact else None
