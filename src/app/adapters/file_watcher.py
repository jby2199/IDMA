"""파일 감시(이벤트/폴링), 파일 안정화 확인, 중복 이벤트 제거를 담당한다."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
except Exception:  # pragma: no cover
    FileSystemEvent = object  # type: ignore[assignment]
    FileSystemEventHandler = object  # type: ignore[assignment]
    Observer = None


class StableFileWatcher:
    """파일이 안정화된 뒤 콜백을 호출하는 감시기."""

    def __init__(self, source_root: Path, file_stable_seconds: int, scan_interval_seconds: int):
        """감시 대상 경로와 안정화/스캔 주기를 초기화한다."""
        self._source_root = source_root
        self._file_stable_seconds = file_stable_seconds
        self._scan_interval_seconds = scan_interval_seconds
        self._observer = None
        self._stop_event = threading.Event()
        self._callback: Callable[[Path], None] | None = None
        self._known_signatures: set[tuple[str, int, int]] = set()
        self._debounce: dict[str, float] = {}
        self._thread: threading.Thread | None = None

    # watchdog 가능 시 이벤트 기반, 아니면 폴링 기반으로 시작한다.
    def start(self, callback: Callable[[Path], None]) -> None:
        """감시를 시작하고 파일 처리 콜백을 등록한다."""
        self._callback = callback
        self._stop_event.clear()
        if Observer is not None:
            self._start_watchdog()
        else:
            self._start_polling()

    def stop(self) -> None:
        """감시를 중지하고 백그라운드 자원을 정리한다."""
        self._stop_event.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    # watchdog 이벤트 핸들러를 등록해 파일 생성/수정 이벤트를 받는다.
    def _start_watchdog(self) -> None:
        """watchdog 기반 감시를 시작한다."""
        assert Observer is not None

        class Handler(FileSystemEventHandler):
            def __init__(self, outer: "StableFileWatcher"):
                self._outer = outer

            def on_created(self, event: FileSystemEvent) -> None:
                self._outer._on_event(event)

            def on_modified(self, event: FileSystemEvent) -> None:
                self._outer._on_event(event)

        observer = Observer()
        observer.schedule(Handler(self), str(self._source_root), recursive=False)
        observer.start()
        self._observer = observer

    # watchdog 미사용 환경에서 주기적으로 폴더를 스캔한다.
    def _start_polling(self) -> None:
        """폴링 기반 감시를 시작한다."""

        def run() -> None:
            while not self._stop_event.is_set():
                for file_path in self._source_root.iterdir():
                    if file_path.is_file():
                        self._attempt_emit(file_path)
                self._stop_event.wait(self._scan_interval_seconds)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    # 이벤트 디바운스를 적용해 중복 이벤트 폭주를 줄인다.
    def _on_event(self, event: FileSystemEvent) -> None:
        """watchdog 이벤트를 받아 안정화 검사 루틴으로 넘긴다."""
        if getattr(event, "is_directory", False):
            return
        path = Path(str(getattr(event, "src_path", "")))
        if not path.exists() or not path.is_file():
            return

        now = time.monotonic()
        key = str(path.resolve())
        if now - self._debounce.get(key, 0) < 0.3:
            return
        self._debounce[key] = now

        threading.Thread(target=self._attempt_emit, args=(path,), daemon=True).start()

    # 파일 안정화/중복 시그니처 검사를 통과하면 콜백을 호출한다.
    def _attempt_emit(self, file_path: Path) -> None:
        """처리 가능한 파일이면 콜백을 실행한다."""
        if self._callback is None:
            return
        if not self._wait_until_stable(file_path):
            return

        stat = file_path.stat()
        signature = (str(file_path.resolve()), stat.st_size, stat.st_mtime_ns)
        if signature in self._known_signatures:
            return

        self._known_signatures.add(signature)
        self._callback(file_path)

    # 일정 시간 동안 파일 크기/mtime이 변하지 않으면 안정화로 본다.
    def _wait_until_stable(self, file_path: Path) -> bool:
        """파일이 일정 시간 변경되지 않았는지 확인한다."""
        stable_for = 0.0
        previous = None

        while stable_for < self._file_stable_seconds:
            if self._stop_event.is_set():
                return False
            if not file_path.exists() or not file_path.is_file():
                return False

            stat = file_path.stat()
            current = (stat.st_size, stat.st_mtime_ns)
            if current == previous:
                stable_for += 0.5
            else:
                stable_for = 0.0
                previous = current
            time.sleep(0.5)

        return True
