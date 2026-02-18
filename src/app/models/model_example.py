"""데이터 모델 정의 예시 모듈."""

from dataclasses import dataclass


@dataclass
class ModelExample:
    """샘플 데이터 모델."""

    id: int
    name: str
