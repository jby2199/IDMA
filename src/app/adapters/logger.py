"""JSONL 파일 기록과 UI 구독 알림을 담당하는 로거 어댑터."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class JsonLineLogger:
    """이벤트를 JSONL로 저장하고 구독자에게 브로드캐스트한다."""

    def __init__(self, log_dir: Path):
        """로그 저장 폴더를 준비하고 내부 상태를 초기화한다."""
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._subscribers: list = []

    # 일자별 로그 파일명을 생성한다.
    def _log_path(self) -> Path:
        """오늘 날짜 기준 JSONL 로그 파일 경로를 반환한다."""
        stamp = datetime.now().strftime("%Y%m%d")
        return self._log_dir / f"submission_automation_{stamp}.jsonl"

    # 파일 저장 후 구독자 콜백을 호출한다.
    def log(self, event: dict[str, Any]) -> None:
        """이벤트를 기록하고 구독자에게 전달한다."""
        payload = dict(event)
        payload.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
        payload.setdefault("severity", "info")
        payload.setdefault("message", payload.get("event", "event"))
        with self._lock:
            with self._log_path().open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            subscribers = list(self._subscribers)

        for callback in subscribers:
            try:
                callback(payload)
            except Exception:
                # 구독자 오류는 로깅 자체를 중단시키지 않는다.
                continue

    def subscribe(self, callback) -> None:
        """로그 이벤트를 받을 구독자를 등록한다."""
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback) -> None:
        """등록된 구독자를 해제한다."""
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)
