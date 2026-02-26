"""Tkinter UI for editing config and controlling watch service."""

from __future__ import annotations

import json
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from app.adapters.config_loader import dump_runtime_config
from app.models.config_schema import RuntimeConfig

try:
    import pystray
    from PIL import Image, ImageDraw
    _TRAY_IMPORT_ERROR: str | None = None
except ImportError as exc:
    pystray = None
    Image = None
    ImageDraw = None
    _TRAY_IMPORT_ERROR = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


class SettingsWindow:
    # UI ?? ??? ?/?? ????? ?????.
    def __init__(self, root: tk.Tk, cfg: RuntimeConfig, config_path: Path, on_start, on_stop):
        self._root = root
        self._cfg = cfg
        self._config_path = config_path
        self._on_start = on_start
        self._on_stop = on_stop

        self._root.title("제출물 관리 자동화 설정")
        self._root.geometry("1100x700")
        self._vars: dict[str, tk.StringVar] = {}

        self._status_var = tk.StringVar(value="Stopped")
        self._last_processed_var = tk.StringVar(value="-")
        self._success_count_var = tk.StringVar(value="0")
        self._failure_count_var = tk.StringVar(value="0")

        # Log aggregation state: one summary row per processed file.
        self._run_traces: dict[str, list[dict[str, str]]] = {}
        self._active_run_by_input: dict[str, str] = {}
        self._row_to_run: dict[str, str] = {}

        self._log_columns = ("file_name", "folder", "timestamp", "result")
        self._detail_columns = ("timestamp", "level", "event", "message")
        self._log_max_rows = 500
        self._resize_job: str | None = None
        self._tray_icon = None
        self._tray_thread: threading.Thread | None = None

        notebook = ttk.Notebook(self._root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_dashboard_tab(notebook)
        self._build_paths_tab(notebook)
        self._build_classification_tab(notebook)
        self._build_execution_tab(notebook)

        footer = ttk.Frame(self._root)
        footer.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(footer, text="설정 저장", command=self._save).pack(side="left")
        ttk.Button(footer, text="감시 시작", command=self._start).pack(side="left", padx=8)
        ttk.Button(footer, text="감시 중지", command=self._stop).pack(side="left")

        self._root.bind("<Configure>", self._on_root_resize)
        self._root.protocol("WM_DELETE_WINDOW", self._exit_program)

    # ???? ?(?? ??/?? ??/?? ??)? ????.
    def _build_dashboard_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="대시보드")

        header = ttk.Frame(frame)
        header.pack(fill="x", padx=8, pady=(8, 0))
        ttk.Button(header, text="트레이로 최소화", command=self._minimize_to_tray).pack(side="right")

        status_box = ttk.LabelFrame(frame, text="감시 상태")
        status_box.pack(fill="x", padx=8, pady=(8, 8))

        ttk.Label(status_box, text="상태").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Label(status_box, textvariable=self._status_var).grid(row=0, column=1, sticky="w", padx=8, pady=4)

        ttk.Label(status_box, text="최근 처리 시각").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Label(status_box, textvariable=self._last_processed_var).grid(row=1, column=1, sticky="w", padx=8, pady=4)

        ttk.Label(status_box, text="성공 건수").grid(row=0, column=2, sticky="w", padx=8, pady=4)
        ttk.Label(status_box, textvariable=self._success_count_var).grid(row=0, column=3, sticky="w", padx=8, pady=4)

        ttk.Label(status_box, text="실패 건수").grid(row=1, column=2, sticky="w", padx=8, pady=4)
        ttk.Label(status_box, textvariable=self._failure_count_var).grid(row=1, column=3, sticky="w", padx=8, pady=4)

        log_box = ttk.LabelFrame(frame, text="감시/행동 로그")
        log_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        split = ttk.PanedWindow(log_box, orient="horizontal")
        split.pack(fill="both", expand=True, padx=6, pady=6)

        # Keep summary table area under 50% of window width while allowing manual column resize.
        self._log_table_holder = ttk.Frame(split, width=520)
        self._log_table_holder.pack_propagate(False)

        self._log_table = ttk.Treeview(
            self._log_table_holder,
            columns=self._log_columns,
            show="headings",
            height=18,
        )
        for col, title, width in (
            ("file_name", "파일명", 220),
            ("folder", "배치폴더", 260),
            ("timestamp", "시각", 145),
            ("result", "결과", 60),
        ):
            self._log_table.heading(col, text=title)
            self._log_table.column(col, width=width, minwidth=60, stretch=True, anchor="w")

        vsb = ttk.Scrollbar(self._log_table_holder, orient="vertical", command=self._log_table.yview)
        hsb = ttk.Scrollbar(self._log_table_holder, orient="horizontal", command=self._log_table.xview)
        self._log_table.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._log_table.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self._log_table_holder.grid_rowconfigure(0, weight=1)
        self._log_table_holder.grid_columnconfigure(0, weight=1)

        detail_frame = ttk.Frame(split)
        detail_frame.pack_propagate(False)
        ttk.Label(detail_frame, text="선택 로그 상세").pack(anchor="w")

        self._detail_table = ttk.Treeview(
            detail_frame,
            columns=self._detail_columns,
            show="headings",
            height=18,
        )
        for col, title, width in (
            ("timestamp", "시각", 140),
            ("level", "레벨", 70),
            ("event", "이벤트", 160),
            ("message", "메시지", 320),
        ):
            self._detail_table.heading(col, text=title)
            self._detail_table.column(col, width=width, minwidth=60, stretch=True, anchor="w")
        self._detail_table.tag_configure("error", foreground="red")

        d_vsb = ttk.Scrollbar(detail_frame, orient="vertical", command=self._detail_table.yview)
        d_hsb = ttk.Scrollbar(detail_frame, orient="horizontal", command=self._detail_table.xview)
        self._detail_table.configure(yscrollcommand=d_vsb.set, xscrollcommand=d_hsb.set)
        self._detail_table.pack(fill="both", expand=True, side="left")
        d_vsb.pack(fill="y", side="right")
        d_hsb.pack(fill="x", side="bottom")

        split.add(self._log_table_holder, weight=1)
        split.add(detail_frame, weight=1)

        self._log_table.tag_configure("error", foreground="red")
        self._log_table.bind("<<TreeviewSelect>>", self._on_log_select)

        controls = ttk.Frame(frame)
        controls.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(controls, text="로그 복사", command=self._copy_logs).pack(side="left")

    # ?? ?? ?? ?? ?? ????.
    def _build_paths_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="경로")

        fields = [
            ("project_root", str(self._cfg.project_root)),
            ("source_root", self._cfg.source_root),
            ("workbook_path", self._cfg.workbook_path),
            ("project_doc_info_path", self._cfg.project_doc_info_path or ""),
            ("project_doc_info_sheet_name", self._cfg.project_doc_info_sheet_name or ""),
            ("project_doc_info_column_title_doc_no", self._cfg.project_doc_info_column_title_doc_no or ""),
            ("project_doc_info_column_title_abbr", self._cfg.project_doc_info_column_title_abbr or ""),
        ]
        for idx, (key, value) in enumerate(fields):
            ttk.Label(frame, text=key).grid(row=idx, column=0, sticky="w", padx=8, pady=6)
            var = tk.StringVar(value=value)
            self._vars[key] = var
            ttk.Entry(frame, textvariable=var, width=90).grid(row=idx, column=1, sticky="ew", padx=8, pady=6)

        phase_row = len(fields)
        ttk.Label(frame, text="phase_folders").grid(row=phase_row, column=0, sticky="nw", padx=8, pady=6)
        phase_frame = ttk.Frame(frame)
        phase_frame.grid(row=phase_row, column=1, sticky="ew")

        for idx, (phase, value) in enumerate(self._cfg.phase_folders.items()):
            key = f"phase::{phase}"
            var = tk.StringVar(value=value)
            self._vars[key] = var
            ttk.Label(phase_frame, text=phase, width=24).grid(row=idx, column=0, sticky="w", padx=4, pady=2)
            ttk.Entry(phase_frame, textvariable=var, width=62).grid(row=idx, column=1, sticky="ew", padx=4, pady=2)

        frame.columnconfigure(1, weight=1)

    # ?? ??/??? ?? ?? ????.
    def _build_classification_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="분류")

        fields = [
            ("full_name_min_ratio", str(self._cfg.full_name_min_ratio)),
            ("ai_confidence_threshold", str(self._cfg.ai_confidence_threshold)),
            ("fallback_enabled", str(self._cfg.fallback_enabled)),
            ("duplicate_suffix_start", str(self._cfg.duplicate_suffix_start)),
        ]
        for idx, (key, value) in enumerate(fields):
            ttk.Label(frame, text=key).grid(row=idx, column=0, sticky="w", padx=8, pady=8)
            var = tk.StringVar(value=value)
            self._vars[key] = var
            ttk.Entry(frame, textvariable=var, width=30).grid(row=idx, column=1, sticky="w", padx=8, pady=8)

    # ?? ?? ?? ?? ?? ????.
    def _build_execution_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="실행")

        fields = [
            ("scan_interval_seconds", str(self._cfg.scan_interval_seconds)),
            ("file_stable_seconds", str(self._cfg.file_stable_seconds)),
        ]
        for idx, (key, value) in enumerate(fields):
            ttk.Label(frame, text=key).grid(row=idx, column=0, sticky="w", padx=8, pady=8)
            var = tk.StringVar(value=value)
            self._vars[key] = var
            ttk.Entry(frame, textvariable=var, width=30).grid(row=idx, column=1, sticky="w", padx=8, pady=8)

    # ??? ?? ??? ?? ?? ??? ????.
    def bind_logger(self, logger) -> None:
        logger.subscribe(self.on_log_event)

    # ????? ?? ???? ?? ??? ??? ????.
    def on_log_event(self, payload: dict) -> None:
        self._root.after(0, lambda: self._handle_log_event(payload))

    # ???? ?? ??? ???? ??/?? ?? ????.
    def _handle_log_event(self, payload: dict) -> None:
        timestamp = str(payload.get("timestamp", datetime.now().isoformat(timespec="seconds")))
        severity = str(payload.get("severity", "info")).lower()
        event = str(payload.get("event", "event"))
        message = str(payload.get("message", ""))
        context = payload.get("context", {})
        if not isinstance(context, dict):
            context = {}

        if event == "watch_started":
            self._status_var.set("Running")
            return
        if event == "watch_stopped":
            self._status_var.set("Stopped")
            return

        run_id, input_path = self._resolve_run(event, timestamp, context)
        if run_id is None:
            return

        trace_entry = {
            "timestamp": timestamp,
            "level": severity.upper(),
            "event": event,
            "message": message,
        }
        self._run_traces.setdefault(run_id, []).append(trace_entry)

        if event in {"file_processed", "file_error"}:
            if event == "file_processed":
                self._success_count_var.set(str(int(self._success_count_var.get()) + 1))
            else:
                self._failure_count_var.set(str(int(self._failure_count_var.get()) + 1))
            self._last_processed_var.set(timestamp)

            self._append_summary_row(run_id, event, timestamp, context)

            if input_path in self._active_run_by_input:
                del self._active_run_by_input[input_path]

    # ???? ?? ?? ?? run?? ?? ?? ?? ????.
    def _resolve_run(self, event: str, timestamp: str, context: dict) -> tuple[str | None, str | None]:
        input_path = context.get("input_path")
        if not input_path:
            return None, None

        input_path = str(input_path)

        if event == "file_detected":
            run_id = f"{input_path}|{timestamp}"
            self._active_run_by_input[input_path] = run_id
            self._run_traces.setdefault(run_id, [])
            return run_id, input_path

        run_id = self._active_run_by_input.get(input_path)
        if run_id is None:
            run_id = f"{input_path}|{timestamp}"
            self._active_run_by_input[input_path] = run_id
            self._run_traces.setdefault(run_id, [])
        return run_id, input_path

    # ?? ??/?? ? ?? ?? ?? ?? 1?? ????.
    def _append_summary_row(self, run_id: str, event: str, timestamp: str, context: dict) -> None:
        input_path = str(context.get("input_path", ""))
        file_name = Path(input_path).name if input_path else "-"

        if event == "file_processed":
            result = "성공"
            folder = str(context.get("target_folder") or "-")
            tags = ()
        else:
            result = "실패"
            folder = "-"
            tags = ("error",)

        values = (file_name, folder, timestamp, result)
        item_id = self._log_table.insert("", "end", values=values, tags=tags)
        self._row_to_run[item_id] = run_id

        rows = self._log_table.get_children("")
        if len(rows) > self._log_max_rows:
            oldest = rows[0]
            self._log_table.delete(oldest)
            self._row_to_run.pop(oldest, None)

        self._auto_size_log_columns(values)
        self._log_table.see(item_id)

    # ?? ?? ? ?? ?? ?? ????.
    def _auto_size_log_columns(self, latest_values: tuple[str, ...]) -> None:
        root_width = max(self._root.winfo_width(), 800)
        max_total = int(root_width * 0.5)
        if max_total < 420:
            max_total = 420

        self._log_table_holder.configure(width=max_total)

        desired = {}
        for idx, col in enumerate(self._log_columns):
            value = str(latest_values[idx]) if idx < len(latest_values) else ""
            prev = int(self._log_table.column(col, "width"))
            desired[col] = min(max(prev, len(value) * 7 + 24), max_total)

        current_total = sum(desired.values())
        if current_total > max_total:
            scale = max_total / float(current_total)
            for col in desired:
                desired[col] = max(60, int(desired[col] * scale))

        for col in self._log_columns:
            self._log_table.column(col, width=desired[col], minwidth=60, stretch=True)

    # ??? ?? ?? ?? ????? ?? ???.
    def _on_log_select(self, _event=None) -> None:
        selection = self._log_table.selection()
        if not selection:
            return

        run_id = self._row_to_run.get(selection[0])
        if run_id is None:
            return

        traces = self._run_traces.get(run_id, [])
        for row_id in self._detail_table.get_children(""):
            self._detail_table.delete(row_id)
        for trace in traces:
            tags = ("error",) if str(trace.get("level", "")).upper() == "ERROR" else ()
            self._detail_table.insert(
                "",
                "end",
                values=(
                    trace.get("timestamp", ""),
                    trace.get("level", ""),
                    trace.get("event", ""),
                    trace.get("message", ""),
                ),
                tags=tags,
            )

    # ?? ?? ?? ???? ??? ????? ????.
    def _copy_logs(self) -> None:
        lines: list[str] = []
        for item_id in self._log_table.get_children(""):
            file_name, folder, ts, result = self._log_table.item(item_id, "values")
            lines.append(f"[{ts}] [{result}] {file_name} | {folder}")

        text = "\n".join(lines)
        self._root.clipboard_clear()
        self._root.clipboard_append(text)
        messagebox.showinfo("복사", "로그를 클립보드에 복사했습니다.")

    # ???? ???? ????? UI ??? ????.
    def _on_root_resize(self, _event=None) -> None:
        # Debounce configure events to avoid geometry feedback loops.
        if self._resize_job is not None:
            try:
                self._root.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self._root.after(40, self._apply_resize)

    # ?? ??? ?? ? ?? ??? ????.
    def _apply_resize(self) -> None:
        self._resize_job = None
        try:
            max_width = int(max(self._root.winfo_width(), 800) * 0.5)
            current = int(self._log_table_holder.winfo_width())
            if abs(current - max_width) > 4:
                self._log_table_holder.configure(width=max_width)
        except Exception:
            # Guard UI resize path so tab switching never terminates the app.
            return

    # UI ???? RuntimeConfig? ????.
    def _materialize(self) -> RuntimeConfig:
        phase_folders = {k.replace("phase::", ""): v.get() for k, v in self._vars.items() if k.startswith("phase::")}

        # _empty_to_none ??? ??? ????.
        def _empty_to_none(value: str) -> str | None:
            value = value.strip()
            return value if value else None

        return RuntimeConfig(
            version=self._cfg.version,
            project_root=Path(self._vars["project_root"].get()),
            workbook_path=self._vars["workbook_path"].get(),
            source_root=self._vars["source_root"].get(),
            phase_folders=phase_folders,
            project_doc_info_path=_empty_to_none(self._vars["project_doc_info_path"].get()),
            project_doc_info_sheet_name=_empty_to_none(self._vars["project_doc_info_sheet_name"].get()),
            project_doc_info_column_title_doc_no=_empty_to_none(self._vars["project_doc_info_column_title_doc_no"].get()),
            project_doc_info_column_title_abbr=_empty_to_none(self._vars["project_doc_info_column_title_abbr"].get()),
            full_name_min_ratio=float(self._vars["full_name_min_ratio"].get()),
            ai_confidence_threshold=float(self._vars["ai_confidence_threshold"].get()),
            fallback_enabled=self._vars["fallback_enabled"].get().lower() in {"1", "true", "yes", "y"},
            duplicate_suffix_start=int(self._vars["duplicate_suffix_start"].get()),
            scan_interval_seconds=int(self._vars["scan_interval_seconds"].get()),
            file_stable_seconds=int(self._vars["file_stable_seconds"].get()),
            submission_sheet_name=self._cfg.submission_sheet_name,
            submission_business_columns=self._cfg.submission_business_columns,
            submission_system_columns=self._cfg.submission_system_columns,
        )

    # ?? UI ?? ?? ??? ????.
    def _save(self) -> None:
        try:
            self._cfg = self._materialize()
            dump_runtime_config(self._config_path, self._cfg)
            messagebox.showinfo("완료", "설정이 저장되었습니다.")
        except Exception as exc:
            messagebox.showerror("오류", str(exc))

    # ?? UI ??? ?? ???? ????.
    def _start(self) -> None:
        try:
            self._cfg = self._materialize()
            self._on_start(self._cfg)
            self._status_var.set("Running")
            messagebox.showinfo("상태", "감시 서비스 시작")
        except Exception as exc:
            messagebox.showerror("오류", str(exc))

    # ?? ???? ????.
    def _stop(self) -> None:
        self._on_stop()
        self._status_var.set("Stopped")
        messagebox.showinfo("상태", "감시 서비스 중지")

    # 대시보드에서 메인 창을 숨기고 시스템 트레이 아이콘을 띄운다.
    def _minimize_to_tray(self) -> None:
        if pystray is None or Image is None or ImageDraw is None:
            details = _TRAY_IMPORT_ERROR or "원인을 확인할 수 없는 ImportError가 발생했습니다."
            messagebox.showerror(
                "오류",
                "트레이 기능 초기화에 실패했습니다.\n"
                "pystray/Pillow 설치 또는 실행 환경 문제일 수 있습니다.\n\n"
                f"원인: {details}",
            )
            return
        if self._tray_icon is not None:
            self._root.withdraw()
            return

        icon = pystray.Icon(
            "submission_automation",
            self._build_tray_image(),
            "제출물 관리 자동화",
            menu=pystray.Menu(
                pystray.MenuItem("열기", self._on_tray_open, default=True),
                pystray.MenuItem("프로그램 종료", self._on_tray_exit),
            ),
        )
        self._tray_icon = icon
        self._tray_thread = threading.Thread(target=icon.run, daemon=True, name="tray-icon")
        self._tray_thread.start()
        self._root.withdraw()

    # 트레이 아이콘 그림을 코드로 생성한다.
    def _build_tray_image(self):
        image = Image.new("RGB", (64, 64), color="#1976d2")
        draw = ImageDraw.Draw(image)
        draw.rectangle((12, 12, 52, 52), outline="white", width=4)
        draw.line((20, 22, 32, 34), fill="white", width=4)
        draw.line((32, 34, 46, 20), fill="white", width=4)
        return image

    # 트레이 기본 동작(더블클릭)으로 창을 다시 연다.
    def _on_tray_open(self, _icon=None, _item=None) -> None:
        self._root.after(0, self._restore_from_tray)

    # 트레이 메뉴의 프로그램 종료를 처리한다.
    def _on_tray_exit(self, _icon=None, _item=None) -> None:
        self._root.after(0, self._exit_program)

    # 트레이 모드에서 메인 창을 복원한다.
    def _restore_from_tray(self) -> None:
        self._stop_tray_icon()
        self._root.deiconify()
        self._root.lift()
        try:
            self._root.focus_force()
        except Exception:
            pass

    # 트레이 아이콘 스레드를 안전하게 정리한다.
    def _stop_tray_icon(self) -> None:
        icon = self._tray_icon
        self._tray_icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

        thread = self._tray_thread
        self._tray_thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1)

    # 앱 종료 시 감시와 트레이를 정리하고 창을 닫는다.
    def _exit_program(self) -> None:
        try:
            self._on_stop()
        except Exception:
            pass
        self._stop_tray_icon()
        self._root.destroy()
