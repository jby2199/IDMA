"""SettingsWindow 로그 대기열: 작업자 스레드는 Tk를 호출하지 않고, Tk 스레드가 대기열을 비운다. <SRS-F009>"""

import queue
import threading
from pathlib import Path

import pytest

from app.ui.settings_window import SettingsWindow


class FakeRoot:
    """after/after_cancel 호출을 기록한다. Tk 스레드 밖 호출도 기록한다."""

    def __init__(self):
        self.owner = threading.get_ident()
        self.after_calls: list[tuple[int, object]] = []
        self.cancelled: list[str] = []
        self.foreign_calls = 0

    def after(self, ms, func=None):
        if threading.get_ident() != self.owner:
            self.foreign_calls += 1
        self.after_calls.append((ms, func))
        return f"job{len(self.after_calls)}"

    def after_cancel(self, job):
        self.cancelled.append(job)


def _window(root: FakeRoot) -> SettingsWindow:
    window = object.__new__(SettingsWindow)  # Tk 위젯 없이 대기열 로직만 시험한다
    window._root = root
    window._log_queue = queue.Queue()
    window._log_poll_job = None
    window._closed = False
    window.handled = []
    window._handle_log_event = window.handled.append
    return window


def test_on_log_event_from_worker_thread_never_touches_tk() -> None:
    root = FakeRoot()
    window = _window(root)
    worker = threading.Thread(target=lambda: [window.on_log_event({"event": f"e{i}"}) for i in range(5)])
    worker.start()
    worker.join(5)

    assert root.after_calls == []
    assert root.foreign_calls == 0
    assert window._log_queue.qsize() == 5
    assert window.handled == []  # Tk 스레드가 비우기 전에는 반영되지 않는다


def test_poll_drains_in_order_and_reschedules() -> None:
    root = FakeRoot()
    window = _window(root)
    for i in range(3):
        window.on_log_event({"event": f"e{i}"})

    window._poll_log_queue()

    assert [p["event"] for p in window.handled] == ["e0", "e1", "e2"]
    assert root.after_calls[-1][0] == 100
    assert root.after_calls[-1][1] == window._poll_log_queue
    assert window._log_poll_job == "job1"


def test_poll_survives_handler_error_and_keeps_draining() -> None:
    root = FakeRoot()
    window = _window(root)

    def handler(payload):
        if payload["event"] == "bad":
            raise ValueError("x")
        window.handled.append(payload)

    window._handle_log_event = handler
    for name in ("a", "bad", "b"):
        window.on_log_event({"event": name})
    window._poll_log_queue()

    assert [p["event"] for p in window.handled] == ["a", "b"]


def test_stop_polling_cancels_job_and_stops_rescheduling() -> None:
    root = FakeRoot()
    window = _window(root)
    window._poll_log_queue()
    scheduled = len(root.after_calls)

    window._stop_log_polling()
    window._poll_log_queue()  # 이미 예약돼 있던 호출이 뒤늦게 실행돼도

    assert root.cancelled == ["job1"]
    assert len(root.after_calls) == scheduled  # 더 예약하지 않는다


def test_events_logged_by_worker_during_join_reach_ui_after_drain() -> None:
    """Tk 스레드가 worker.join()으로 기다리는 동안 워커는 막히지 않고, join 뒤 이벤트가 UI에 반영된다."""
    root = FakeRoot()
    window = _window(root)

    def worker():
        for i in range(3):
            window.on_log_event({"event": f"drain{i}"})  # 로거 구독자와 같은 경로

    t = threading.Thread(target=worker)
    t.start()
    t.join(2)  # AppController.stop의 join 역할
    assert not t.is_alive()
    window._drain_log_queue()  # _stop이 on_stop 뒤에 호출하는 비우기
    assert [p["event"] for p in window.handled] == ["drain0", "drain1", "drain2"]


def _real_root():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # 디스플레이 없는 환경
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()
    return root


def test_real_tk_stop_joining_worker_that_logs_does_not_hang(tmp_path: Path) -> None:
    """실제 Tk: Tk 스레드가 join으로 기다리는 중 워커가 로그를 남겨도 교착하지 않는다."""
    from app.models.config_schema import RuntimeConfig

    root = _real_root()
    try:
        cfg = RuntimeConfig(version="1", project_root=tmp_path, workbook_path="x.xlsx", source_root="in", phase_folders={})
        window = SettingsWindow(root, cfg, tmp_path / "ledger.config.yaml", on_start=lambda c: None, on_stop=lambda: None)
        result: dict = {}

        def worker():
            for _ in range(3):
                window.on_log_event({"event": "watch_started", "severity": "info", "message": "m", "context": {}})
            result["worker_done"] = True

        def on_stop():  # AppController.stop이 Tk 스레드에서 하는 일: 워커를 join
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            t.join(timeout=3)
            result["alive_after_3s"] = t.is_alive()
            window._drain_log_queue()
            result["status"] = window._status_var.get()

        window._on_stop = on_stop

        def close():
            window._on_stop()
            window._exit_program()

        root.after(50, close)
        root.mainloop()
        assert result == {"worker_done": True, "alive_after_3s": False, "status": "Running"}
    finally:
        try:
            root.destroy()
        except Exception:
            pass
