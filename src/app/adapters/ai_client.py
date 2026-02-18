"""AI 분류기 인터페이스의 기본(미연동) 구현을 제공한다."""

from __future__ import annotations

from app.core.entities import AIResult, Knowledge


class StubAIClassifier:
    """v1 기본값으로 사용하는 더미 AI 분류기."""

    # 실제 AI 연동 전까지는 항상 분류하지 않음(None)으로 반환한다.
    def classify(self, filename: str, knowledge: Knowledge) -> AIResult | None:
        """AI 분류 결과를 반환한다(현재는 항상 None)."""
        _ = (filename, knowledge)
        return None
