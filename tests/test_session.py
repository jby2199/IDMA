"""감시 세션 시작 점검(SRS-F033), 무GUI 종료 코드(SRS 8.1), 직렬 처리(SRS-F008)를 검증한다."""

import hashlib
import re
import stat
import sys
import threading
import time
import types
from pathlib import Path

import pytest

from app import main as app_main
from app.adapters.excel_repo import OpenpyxlLedgerRepository
from app.core.entities import LedgerRecord, ProcessOutcome
from app.core.validation import PreflightValidator
from app.main import (
    AppController,
    LedgerSessionGuard,
    SessionStartError,
    new_run_id,
)

openpyxl = pytest.importorskip("openpyxl")

SHEET = "관리대장"
BUSINESS = ["제출물명"]
SYSTEM = ["phase", "status"]
HEADERS = BUSINESS + SYSTEM


class MemoryLogger:
    def __init__(self):
        self.events = []

    def log(self, event):
        self.events.append(event)


def _make_workbook(path: Path, headers: list[str] | None, sheet: str = SHEET) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    if headers is not None:
        for idx, name in enumerate(headers, start=1):
            ws.cell(row=1, column=idx, value=name)
    ws.cell(row=2, column=1, value="기존 행")
    wb.save(path)
    wb.close()


def _repo(path: Path) -> OpenpyxlLedgerRepository:
    return OpenpyxlLedgerRepository(path, SHEET, BUSINESS, SYSTEM)


def _guard(tmp_path: Path, workbook: Path, logger: MemoryLogger | None = None) -> LedgerSessionGuard:
    repo = _repo(workbook)
    return LedgerSessionGuard(repo, PreflightValidator(), tmp_path / "backup", repo.required_headers(), logger or MemoryLogger())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lock_exclusively(path: Path):
    """Windows에서 다른 프로세스(Excel)가 건 것과 같은 공유 거부 핸들을 연다."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    handle = kernel32.CreateFileW(str(path), 0x80000000 | 0x40000000, 0, None, 3, 0x80, None)
    assert handle not in (None, wintypes.HANDLE(-1).value), ctypes.get_last_error()
    return kernel32, handle


# ---------- 세션 시작 점검 ----------


def test_run_id_format() -> None:
    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{6}", new_run_id())
    assert new_run_id() != new_run_id()


def test_guard_passes_and_backs_up_without_changing_original(tmp_path: Path) -> None:
    wb = tmp_path / "ledger.xlsx"
    _make_workbook(wb, HEADERS)
    before = _sha(wb)
    logger = MemoryLogger()

    _guard(tmp_path, wb, logger).check("20261010-120000-abcdef")

    backup = tmp_path / "backup" / "ledger_20261010-120000-abcdef.xlsx"
    assert backup.exists()
    assert _sha(backup) == before
    assert _sha(wb) == before
    assert any(e["event"] == "ledger_backup_done" for e in logger.events)


def test_guard_missing_workbook_is_skipped(tmp_path: Path) -> None:
    # 가정 A1: 워크북이 없으면 점검할 것이 없고 백업도 만들지 않는다.
    _guard(tmp_path, tmp_path / "none.xlsx").check("run1")
    assert not (tmp_path / "backup").exists()


def test_guard_missing_header_exits_1_after_backup(tmp_path: Path) -> None:
    wb = tmp_path / "ledger.xlsx"
    _make_workbook(wb, ["제출물명", "phase"])  # status 없음
    logger = MemoryLogger()

    with pytest.raises(SessionStartError) as info:
        _guard(tmp_path, wb, logger).check("run1")

    assert info.value.exit_code == 1
    assert "status" in info.value.message
    assert (tmp_path / "backup" / "ledger_run1.xlsx").exists()  # 순서: 잠금 -> 백업 -> 헤더
    assert any(e["event"] == "ledger_header_missing" and e["severity"] == "error" for e in logger.events)


def test_guard_missing_sheet_exits_1(tmp_path: Path) -> None:
    wb = tmp_path / "ledger.xlsx"
    _make_workbook(wb, HEADERS, sheet="다른시트")
    with pytest.raises(SessionStartError) as info:
        _guard(tmp_path, wb).check("run1")
    assert info.value.exit_code == 1


def test_guard_does_not_modify_workbook_on_header_failure(tmp_path: Path) -> None:
    wb = tmp_path / "ledger.xlsx"
    _make_workbook(wb, ["제출물명"])
    before = _sha(wb)
    with pytest.raises(SessionStartError):
        _guard(tmp_path, wb).check("run1")
    assert _sha(wb) == before  # 어댑터가 헤더를 자동 추가하지 않는다


@pytest.mark.skipif(sys.platform != "win32", reason="공유 거부 잠금은 Windows 전용")
def test_guard_locked_workbook_exits_2_without_backup(tmp_path: Path) -> None:
    wb = tmp_path / "ledger.xlsx"
    _make_workbook(wb, HEADERS)
    logger = MemoryLogger()
    kernel32, handle = _lock_exclusively(wb)
    try:
        with pytest.raises(SessionStartError) as info:
            _guard(tmp_path, wb, logger).check("run1")
    finally:
        kernel32.CloseHandle(handle)

    assert info.value.exit_code == 2
    assert "관리대장을 닫은 뒤 다시 시작" in info.value.message
    assert not (tmp_path / "backup").exists()  # 잠금이면 백업 전에 멈춘다
    assert any(e["event"] == "ledger_locked" for e in logger.events)


def test_guard_readonly_workbook_exits_2(tmp_path: Path) -> None:
    wb = tmp_path / "ledger.xlsx"
    _make_workbook(wb, HEADERS)
    wb.chmod(stat.S_IREAD)
    try:
        if _can_open_for_write(wb):
            pytest.skip("이 환경은 읽기 전용 파일도 쓰기 열기가 가능하다(권한 상승 계정)")
        with pytest.raises(SessionStartError) as info:
            _guard(tmp_path, wb).check("run1")
        assert info.value.exit_code == 2
    finally:
        wb.chmod(stat.S_IWRITE | stat.S_IREAD)


def _can_open_for_write(path: Path) -> bool:
    try:
        with path.open("r+b"):
            return True
    except OSError:
        return False


def test_backup_failure_exits_2(tmp_path: Path) -> None:
    wb = tmp_path / "ledger.xlsx"
    _make_workbook(wb, HEADERS)
    (tmp_path / "backup").write_text("폴더 자리에 파일", encoding="utf-8")  # mkdir 불가
    with pytest.raises(SessionStartError) as info:
        _guard(tmp_path, wb).check("run1")
    assert info.value.exit_code == 2


def test_validator_check_ledger_headers() -> None:
    v = PreflightValidator()
    assert v.check_ledger_headers(["a", "b"], ["b", "a", "c"]) == []
    issues = v.check_ledger_headers(["a", "b", "c"], ["a"])
    assert [i.message for i in issues] == ["Ledger header is missing: b", "Ledger header is missing: c"]


# ---------- 컨트롤러: 시작 차단 / 직렬 처리 / 종료 코드 ----------


def _record(method: str = "Rule-ABBR", status: str = "Filed") -> LedgerRecord:
    return LedgerRecord("f.pdf", "Design", "SDD", method, None, "", status, "", "2026-10-10T00:00:00")


class FakeWatcher:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.callback = None

    def start(self, callback):
        self.started = True
        self.callback = callback

    def stop(self):
        self.stopped = True


class FakeUsecase:
    """동시 실행 수와 처리 순서를 기록한다."""

    def __init__(self, delay: float = 0.0, statuses: dict[str, str] | None = None, raise_on: set[str] | None = None):
        self.delay = delay
        self.statuses = statuses or {}
        self.raise_on = raise_on or set()
        self.active = 0
        self.max_active = 0
        self.order: list[str] = []
        self._lock = threading.Lock()

    def run(self, path: Path):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            self.order.append(path.name)
            if path.name in self.raise_on:
                raise RuntimeError("boom")
            status = self.statuses.get(path.name, "Filed")
            return ProcessOutcome(status == "Filed", status, None, _record(status=status))
        finally:
            with self._lock:
                self.active -= 1


class BlockingGuard:
    def __init__(self, exit_code: int):
        self.exit_code = exit_code
        self.calls = 0

    def check(self, run_id):
        self.calls += 1
        raise SessionStartError(self.exit_code, "차단")


def test_controller_does_not_start_watcher_when_guard_blocks() -> None:
    watcher = FakeWatcher()
    usecase = FakeUsecase()
    guard = BlockingGuard(2)
    controller = AppController(usecase, watcher, MemoryLogger(), guard)

    with pytest.raises(SessionStartError) as info:
        controller.start()

    assert info.value.exit_code == 2
    assert guard.calls == 1
    assert watcher.started is False
    assert usecase.order == []
    controller.stop()  # 시작 안 한 세션의 중지는 무동작


def test_controller_session_logs_carry_run_id() -> None:
    logger = MemoryLogger()
    controller = AppController(FakeUsecase(), FakeWatcher(), logger)
    controller.start()
    controller.stop()
    started = [e for e in logger.events if e["event"] == "watch_started"][0]
    stopped = [e for e in logger.events if e["event"] == "watch_stopped"][0]
    assert started["context"]["run_id"] == stopped["context"]["run_id"] == controller.run_id


def test_files_are_processed_one_at_a_time_in_detection_order() -> None:
    watcher = FakeWatcher()
    usecase = FakeUsecase(delay=0.02)
    controller = AppController(usecase, watcher, MemoryLogger())
    controller.start()

    # 감시기 쪽에서 여러 스레드가 동시에 콜백을 호출하는 상황(watchdog 이벤트당 스레드)을 흉내낸다.
    names = [f"f{i}.pdf" for i in range(8)]
    threads = []
    for name in names:
        t = threading.Thread(target=watcher.callback, args=(Path(name),))
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    controller.stop()  # 대기열을 비운 뒤 끝난다

    assert usecase.max_active == 1
    assert sorted(usecase.order) == sorted(names)  # 전부 처리, 유실 없음


def test_stop_processes_every_file_already_queued() -> None:
    """<SRS-F009>: 중지 시 이미 대기열에 든 안정화 완료 파일은 모두 처리한 뒤 끝난다."""
    watcher = FakeWatcher()
    first_started = threading.Event()
    release = threading.Event()

    class GatedUsecase(FakeUsecase):
        def run(self, path: Path):
            if path.name == "q0.pdf":
                first_started.set()
                assert release.wait(5)  # 첫 파일 처리 중에 나머지를 대기열에 쌓는다
            return super().run(path)

    usecase = GatedUsecase()
    controller = AppController(usecase, watcher, MemoryLogger())
    controller.start()
    names = [f"q{i}.pdf" for i in range(4)]
    watcher.callback(Path(names[0]))
    assert first_started.wait(5)
    for name in names[1:]:
        watcher.callback(Path(name))  # q0 처리 중이므로 q1~q3은 대기열에 남아 있다

    stopper = threading.Thread(target=controller.stop)
    stopper.start()
    time.sleep(0.05)  # stop이 대기열 소진을 기다리는 상태가 되게 한다
    assert usecase.order == []  # 중지 요청 시점에 아무것도 끝나지 않았다
    assert watcher.stopped is True  # 작업자를 풀어주기 전에 감시기가 이미 중지됐다
    assert stopper.is_alive()  # stop은 대기열 소진을 기다리는 중이다
    release.set()
    stopper.join(5)

    assert not stopper.is_alive()
    assert watcher.stopped is True
    assert usecase.order == names  # 대기열 전부 감지 순서대로 처리, 유실 없음


def test_callback_delivered_while_watcher_stops_is_processed() -> None:
    """감시기 중지 중(진행 중 emit이 끝나는 동안) 전달된 콜백은 버려지지 않고 처리된다."""
    watcher = FakeWatcher()
    usecase = FakeUsecase()
    controller = AppController(usecase, watcher, MemoryLogger())
    controller.start()

    def stop_with_inflight_emit():
        watcher.stopped = True
        watcher.callback(Path("inflight.pdf"))  # watcher.stop()이 끝나기 전에 끝나는 emit

    watcher.stop = stop_with_inflight_emit
    controller.stop()

    assert usecase.order == ["inflight.pdf"]


def test_nothing_enqueued_after_stop_marker() -> None:
    """_STOP 이후에는 어떤 경로도 대기열에 들어가지 않는다(수락 종료와 _STOP 적재가 원자적)."""
    watcher = FakeWatcher()
    controller = AppController(FakeUsecase(), watcher, MemoryLogger())
    controller.start()
    controller.stop()
    watcher.callback(Path("late.pdf"))
    assert controller._queue.empty()


def test_queue_order_is_fifo() -> None:
    watcher = FakeWatcher()
    usecase = FakeUsecase(delay=0.01)
    controller = AppController(usecase, watcher, MemoryLogger())
    controller.start()
    names = [f"f{i}.pdf" for i in range(6)]
    for name in names:
        watcher.callback(Path(name))
    controller.stop()
    assert usecase.order == names


def test_one_file_exception_does_not_stop_next_and_counts_error() -> None:
    watcher = FakeWatcher()
    usecase = FakeUsecase(raise_on={"bad.pdf"})
    logger = MemoryLogger()
    controller = AppController(usecase, watcher, logger)
    controller.start()
    for name in ("a.pdf", "bad.pdf", "c.pdf"):
        watcher.callback(Path(name))
    controller.stop()

    assert usecase.order == ["a.pdf", "bad.pdf", "c.pdf"]
    assert controller.error_count == 1
    assert controller.exit_code() == 3
    assert any(e["event"] == "file_error" and e["context"]["run_id"] == controller.run_id for e in logger.events)


def test_exit_code_3_when_error_outcome_and_summary_counts() -> None:
    watcher = FakeWatcher()
    usecase = FakeUsecase(statuses={"e.pdf": "Error"})
    controller = AppController(usecase, watcher, MemoryLogger())
    controller.start()
    for name in ("a.pdf", "e.pdf"):
        watcher.callback(Path(name))
    controller.stop()

    assert controller.exit_code() == 3
    summary = controller.format_summary()
    assert "대상 2건" in summary and "Rule-ABBR 1건" in summary and "Error 1건" in summary


def test_exit_code_0_without_errors() -> None:
    watcher = FakeWatcher()
    controller = AppController(FakeUsecase(), watcher, MemoryLogger())
    controller.start()
    watcher.callback(Path("a.pdf"))
    controller.stop()
    assert controller.exit_code() == 0
    assert controller.error_count == 0


def test_counters_reset_on_new_session() -> None:
    watcher = FakeWatcher()
    controller = AppController(FakeUsecase(statuses={"e.pdf": "Error"}), watcher, MemoryLogger())
    controller.start()
    watcher.callback(Path("e.pdf"))
    controller.stop()
    assert controller.error_count == 1
    controller.start()
    controller.stop()
    assert controller.error_count == 0


# ---------- main(): --nogui 종료 코드 ----------


def _run_main_nogui(monkeypatch, controller_parts, stop_after: float | None = None) -> int:
    """_build_runtime을 가짜로 바꾸고 --nogui를 실행한다. Ctrl+C는 time.sleep에서 발생시킨다."""
    watcher, usecase, guard = controller_parts

    def fake_build(*_args):
        return object(), usecase, watcher, MemoryLogger(), guard

    def fake_sleep(_seconds):
        if watcher.callback is not None:
            for name in getattr(watcher, "emit", []):
                watcher.callback(Path(name))
        raise KeyboardInterrupt

    monkeypatch.setattr(app_main, "_build_runtime", fake_build)
    monkeypatch.setattr(app_main, "time", types.SimpleNamespace(sleep=fake_sleep))  # 전역 time.sleep은 건드리지 않는다
    monkeypatch.setattr(sys, "argv", ["idma", "--nogui"])
    return app_main.main()


def test_main_nogui_exit_2_on_locked_ledger(monkeypatch, capsys) -> None:
    code = _run_main_nogui(monkeypatch, (FakeWatcher(), FakeUsecase(), _GuardWithMessage(2)))
    assert code == 2
    assert "관리대장을 닫은 뒤 다시 시작" in capsys.readouterr().err


def test_main_nogui_exit_1_on_missing_header(monkeypatch, capsys) -> None:
    code = _run_main_nogui(monkeypatch, (FakeWatcher(), FakeUsecase(), _GuardWithMessage(1)))
    assert code == 1


def test_main_nogui_exit_3_when_error_file(monkeypatch, capsys) -> None:
    watcher = FakeWatcher()
    watcher.emit = ["ok.pdf", "e.pdf"]
    code = _run_main_nogui(monkeypatch, (watcher, FakeUsecase(statuses={"e.pdf": "Error"}), None))
    out = capsys.readouterr()
    assert code == 3
    assert "Error 1건" in out.out
    assert watcher.stopped is True


def test_main_nogui_exit_0_when_clean(monkeypatch, capsys) -> None:
    watcher = FakeWatcher()
    watcher.emit = ["ok.pdf"]
    code = _run_main_nogui(monkeypatch, (watcher, FakeUsecase(), None))
    assert code == 0
    assert "대상 1건" in capsys.readouterr().out


class _GuardWithMessage:
    def __init__(self, exit_code: int):
        self.exit_code = exit_code

    def check(self, run_id):
        raise SessionStartError(self.exit_code, "관리대장을 닫은 뒤 다시 시작하십시오.")


def test_main_nogui_real_guard_missing_header_exits_1(tmp_path: Path, monkeypatch) -> None:
    """실제 가드·실제 xlsx로 헤더 누락이 종료 코드 1이 되고 파일이 감시되지 않음을 확인한다."""
    wb = tmp_path / "ledger.xlsx"
    _make_workbook(wb, ["제출물명"])
    watcher = FakeWatcher()
    usecase = FakeUsecase()
    logger = MemoryLogger()
    repo = _repo(wb)
    guard = LedgerSessionGuard(repo, PreflightValidator(), tmp_path / "backup", repo.required_headers(), logger)

    monkeypatch.setattr(app_main, "_build_runtime", lambda *a: (object(), usecase, watcher, logger, guard))
    monkeypatch.setattr(sys, "argv", ["idma", "--nogui"])
    assert app_main.main() == 1
    assert watcher.started is False


# ---------- 리뷰 반영: 중지 경합·시작 실패 ----------


def test_late_callback_after_stop_is_dropped() -> None:
    watcher = FakeWatcher()
    usecase = FakeUsecase()
    controller = AppController(usecase, watcher, MemoryLogger())
    controller.start()
    watcher.callback(Path("a.pdf"))
    controller.stop()
    watcher.callback(Path("late.pdf"))  # 중지 뒤 늦게 도착
    controller.start()  # 새 세션
    controller.stop()
    assert usecase.order == ["a.pdf"]


def test_watcher_start_failure_leaks_no_worker() -> None:
    class BrokenWatcher(FakeWatcher):
        def start(self, callback):
            raise RuntimeError("watch fail")

    before = {t for t in threading.enumerate() if t.name == "idma-serial-worker"}
    controller = AppController(FakeUsecase(), BrokenWatcher(), MemoryLogger())
    for _ in range(3):
        with pytest.raises(RuntimeError):
            controller.start()
    after = {t for t in threading.enumerate() if t.name == "idma-serial-worker"}
    assert after == before


def test_main_nogui_ctrl_c_during_start_is_clean(monkeypatch) -> None:
    class InterruptingGuard:
        def check(self, run_id):
            raise KeyboardInterrupt

    monkeypatch.setattr(app_main, "_build_runtime", lambda *a: (object(), FakeUsecase(), FakeWatcher(), MemoryLogger(), InterruptingGuard()))
    monkeypatch.setattr(sys, "argv", ["idma", "--nogui"])
    assert app_main.main() == 0
