"""StableFileWatcher의 중지 경합(서명 기록 부작용)과 AppController 연동을 검증한다. <SRS-F009>"""

import threading
from pathlib import Path

from app.adapters.file_watcher import StableFileWatcher
from app.core.entities import LedgerRecord, ProcessOutcome
from app.main import AppController


def _watcher(tmp_path: Path) -> StableFileWatcher:
    # file_stable_seconds=0이면 안정화 대기 없이 곧바로 통과한다.
    return StableFileWatcher(tmp_path, 0, 1)


def _touch(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"x")
    return path


def test_emit_after_stop_is_dropped_without_recording_signature(tmp_path: Path) -> None:
    watcher = _watcher(tmp_path)
    got: list[Path] = []
    watcher._callback = got.append
    path = _touch(tmp_path, "a.pdf")

    watcher.stop()
    watcher._attempt_emit(path)

    assert got == []
    assert watcher._known_signatures == set()  # 서명 미기록 -> 다음 세션에서 다시 후보가 된다
    watcher._stop_event.clear()  # start()가 하는 재시작
    watcher._attempt_emit(path)
    assert got == [path]


def test_stop_waits_for_inflight_emit_and_signature_matches_delivery(tmp_path: Path) -> None:
    watcher = _watcher(tmp_path)
    in_callback = threading.Event()
    release = threading.Event()
    got: list[Path] = []

    def callback(path: Path) -> None:
        in_callback.set()
        assert release.wait(5)
        got.append(path)

    watcher._callback = callback
    path = _touch(tmp_path, "a.pdf")
    emitter = threading.Thread(target=watcher._attempt_emit, args=(path,))
    emitter.start()
    assert in_callback.wait(5)

    stopper = threading.Thread(target=watcher.stop)
    stopper.start()
    stopper.join(0.2)
    assert stopper.is_alive()  # 진행 중 emit이 끝나기 전에는 stop이 반환하지 않는다

    release.set()
    stopper.join(5)
    emitter.join(5)
    assert not stopper.is_alive()
    assert got == [path]
    assert len(watcher._known_signatures) == 1  # 서명이 기록된 파일은 반드시 전달됐다


def test_emit_started_during_stop_never_leaves_signature_without_delivery(tmp_path: Path) -> None:
    """서명이 기록된 모든 파일은 콜백으로 전달됐고, 중지 뒤 emit은 서명도 전달도 없다."""
    for round_no in range(20):
        watcher = _watcher(tmp_path)
        got: list[Path] = []
        watcher._callback = got.append
        paths = [_touch(tmp_path, f"r{round_no}_{i}.pdf") for i in range(10)]
        start = threading.Barrier(len(paths) + 1)

        def emit(p: Path) -> None:
            start.wait()
            watcher._attempt_emit(p)

        threads = [threading.Thread(target=emit, args=(p,)) for p in paths]
        for t in threads:
            t.start()
        start.wait()
        watcher.stop()
        for t in threads:
            t.join(5)

        recorded = {Path(sig[0]) for sig in watcher._known_signatures}
        assert recorded == {p.resolve() for p in got}


class _NoObserverWatcher(StableFileWatcher):
    """Observer·폴링 스레드 없이 콜백 등록만 한다(emit은 테스트가 직접 호출)."""

    def start(self, callback) -> None:
        self._callback = callback
        self._stop_event.clear()


def test_controller_stop_processes_every_signature_recorded_file(tmp_path: Path) -> None:
    """컨트롤러+실제 감시기: 서명이 기록된 파일은 모두 처리된다(중지 경합 중에도 유실 없음)."""
    processed: list[str] = []
    lock = threading.Lock()

    class Usecase:
        def run(self, path: Path):
            with lock:
                processed.append(path.resolve().name)
            record = LedgerRecord("f.pdf", "Design", "SDD", "Rule-ABBR", None, "", "Filed", "", "2026-10-10T00:00:00")
            return ProcessOutcome(True, "Filed", None, record)

    class Logger:
        def log(self, event):
            pass

    for round_no in range(20):
        watcher = _NoObserverWatcher(tmp_path, 0, 1)
        controller = AppController(Usecase(), watcher, Logger())
        processed.clear()
        controller.start()
        paths = [_touch(tmp_path, f"c{round_no}_{i}.pdf") for i in range(10)]
        start = threading.Barrier(len(paths) + 1)

        def emit(p: Path) -> None:
            start.wait()
            watcher._attempt_emit(p)

        threads = [threading.Thread(target=emit, args=(p,)) for p in paths]
        for t in threads:
            t.start()
        start.wait()
        controller.stop()
        for t in threads:
            t.join(5)

        recorded = {Path(sig[0]).name for sig in watcher._known_signatures}
        assert recorded == set(processed)
