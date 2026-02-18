"""분류 규칙(문서번호/약어/전문명/AI 보조)을 담당하는 모듈."""

from __future__ import annotations

import re

from app.core.entities import AIClassifier, ClassificationResult, Knowledge

_TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9]+")


# 파일명/전문명을 토큰 단위로 비교하기 위해 정규화한다.
def _tokenize(value: str) -> list[str]:
    """문자열을 소문자 토큰 목록으로 분해한다."""
    return [token for token in _TOKEN_SPLIT.split(value.lower()) if token]


# 전문명 토큰 대비 파일명 토큰의 포함 비율을 계산한다.
def _full_name_ratio(filename_tokens: set[str], full_name: str) -> float:
    """전문명 매칭 비율(0.0~1.0)을 계산한다."""
    full_tokens = _tokenize(full_name)
    if not full_tokens:
        return 0.0
    matched = sum(1 for token in full_tokens if token in filename_tokens)
    return matched / len(full_tokens)


# PRD 기준 매칭 비율 구간을 confidence로 변환한다.
def _confidence_from_ratio(ratio: float) -> float:
    """전문명 매칭 비율을 룰 confidence 값으로 변환한다."""
    if ratio >= 0.7:
        return 0.8
    if ratio >= 0.5:
        return 0.6
    return 0.0


class ClassificationService:
    """파일명을 받아 최종 분류 결과(phase/abbr/method)를 결정한다."""

    def __init__(self, ai_classifier: AIClassifier | None = None, project_doc_classifier=None):
        """AI 분류기와 프로젝트 문서번호 분류기를 선택적으로 주입한다."""
        self._ai_classifier = ai_classifier
        self._project_doc_classifier = project_doc_classifier

    # 분류 우선순위: 프로젝트문서번호 -> ABBR -> FULL -> AI -> Fallback
    def classify(self, filename: str, knowledge: Knowledge, full_name_min_ratio: float, ai_threshold: float) -> ClassificationResult:
        """파일명에 대해 최종 분류 결과를 반환한다."""
        if self._project_doc_classifier is not None:
            project_doc_result = self._project_doc_classifier.classify(filename, knowledge)
            if project_doc_result is not None:
                return project_doc_result

        filename_tokens = set(_tokenize(filename))

        # 약어는 정확 토큰 일치를 최우선으로 처리한다.
        abbr_matches = [artifact for artifact in knowledge.artifacts if artifact.abbr.lower() in filename_tokens]
        if len(abbr_matches) == 1:
            artifact = abbr_matches[0]
            return ClassificationResult(
                phase=artifact.phase,
                artifact_abbr=artifact.abbr,
                method="Rule-ABBR",
                confidence=1.0,
                reason="ABBR token matched",
            )

        ambiguous = len(abbr_matches) > 1

        # 전문명 매칭 점수를 전체 후보에 대해 계산한다.
        scored: list[tuple[float, str, str]] = []
        for artifact in knowledge.artifacts:
            scored.append((_full_name_ratio(filename_tokens, artifact.full_name), artifact.abbr, artifact.phase))

        # 최고 점수 후보를 앞에 두고 충돌/동률 여부를 판단한다.
        scored.sort(reverse=True, key=lambda item: item[0])

        if scored:
            top_ratio, top_abbr, top_phase = scored[0]
            top_count = sum(1 for ratio, _, _ in scored if ratio == top_ratio)
            if top_ratio >= full_name_min_ratio and top_count == 1:
                return ClassificationResult(
                    phase=top_phase,
                    artifact_abbr=top_abbr,
                    method="Rule-FULL",
                    confidence=_confidence_from_ratio(top_ratio),
                    reason=f"full_name_ratio={top_ratio:.2f}",
                )
            if top_count > 1:
                ambiguous = True

        should_call_ai = ambiguous or not scored or scored[0][0] < full_name_min_ratio
        if self._ai_classifier is not None and should_call_ai:
            ai_result = self._ai_classifier.classify(filename, knowledge)
            if ai_result and ai_result.ai_confidence >= ai_threshold:
                return ClassificationResult(
                    phase=ai_result.phase,
                    artifact_abbr=ai_result.artifact_abbr,
                    method="AI",
                    confidence=ai_result.ai_confidence,
                    reason=ai_result.reason or "AI classified",
                    ai_confidence=ai_result.ai_confidence,
                )

        return ClassificationResult(
            phase=None,
            artifact_abbr=None,
            method="Fallback",
            confidence=0.0,
            reason="No confident match",
        )
