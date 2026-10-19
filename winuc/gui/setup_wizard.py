"""Explicit USB adapter selection, driver setup and read-only diagnostics."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable

from .. import driver
from ..diagnostics import build_report, report_text
from ..i18n import t
from ..native_driver import RebootRequired
from .theme import configure, font_family
from .icons import apply_window_icon, make_icon


class SetupWizard:
    def __init__(self, root: tk.Tk, on_done: Callable[[], None] | None = None,
                 *, on_apply: Callable[[driver.Dongle], None] | None = None,
                 active_adapter_id: str = "",
                 prepare_driver: Callable[[driver.Dongle], None] | None = None,
                 on_ready: Callable[[], None] | None = None) -> None:
        configure(root)
        self.on_done, self.on_apply = on_done, on_apply
        self.prepare_driver = prepare_driver
        self.on_ready = on_ready
        self._active_adapter_id = active_adapter_id
        self._preview_id = active_adapter_id
        self._results = queue.SimpleQueue()
        self._closed = self._busy = False
        self._diagnostic_text = ""
        self._dongle: driver.Dongle | None = None
        self._candidates: list[driver.Dongle] = []
        self._rows: dict[str, driver.Dongle] = {}
        self.win = tk.Toplevel(root)
        self.win.title(t("Glideleaf 동글 설정"))
        apply_window_icon(self.win)
        self.win.geometry("920x680")
        self.win.minsize(820, 620)
        self.win.protocol("WM_DELETE_WINDOW", self._close)
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(0, weight=1)
        frm = ttk.Frame(self.win, padding=24)
        frm.grid(sticky="nsew")
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(2, weight=1)
        from PIL import ImageTk
        self.brand_icon = ImageTk.PhotoImage(make_icon(None, 40), master=self.win)
        heading = ttk.Frame(frm)
        heading.grid(row=0, column=0, sticky="w", pady=(0, 7))
        ttk.Label(heading, image=self.brand_icon).pack(side="left", padx=(0, 10))
        ttk.Label(heading, text=t("전용 동글 연결하기"), font=(font_family(), 18, "bold")).pack(side="left")
        ttk.Label(frm, text=t("목록에서 동글을 선택하고 동글 연결을 누르세요. 이미 준비된 동글은 적용 후 바로 사용할 수 있습니다."), wraplength=830).grid(row=1, column=0, sticky="w", pady=(0, 17))
        table_frame = ttk.Frame(frm)
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.devices = ttk.Treeview(table_frame, columns=("name", "usb", "driver", "location", "applied"), show="headings", selectmode="browse", height=6)
        for key, text, width in (("name", t("어댑터"), 240), ("usb", "USB ID", 110), ("driver", t("드라이버"), 180), ("location", t("연결 위치"), 180), ("applied", t("적용 상태"), 110)):
            self.devices.heading(key, text=text)
            self.devices.column(key, width=width, minwidth=80, stretch=key in ("name", "location"))
        self.devices.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.devices.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.devices.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.devices.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        self.devices.tag_configure("alternate", background="#F7FAFA")
        self.devices.bind("<<TreeviewSelect>>", self._select)
        self.status_var = tk.StringVar(value=t("블루투스 동글 검색 중…"))
        ttk.Label(frm, textvariable=self.status_var, wraplength=830, justify="left", font=(font_family(), 10, "bold")).grid(row=3, column=0, sticky="w", pady=(15, 12))
        self.detail = tk.Text(frm, height=4, width=80, state="disabled", wrap="word", bg="#FFFFFF", fg="#53697A", relief="flat", padx=11, pady=9, font=(font_family(), 9))
        self.detail.grid(row=4, column=0, sticky="ew", pady=(0, 15))
        actions = ttk.Frame(frm)
        actions.grid(row=5, column=0, sticky="ew")
        self.apply_btn = ttk.Button(actions, text=t("선택한 동글 적용"), command=self._apply_selected, state="disabled", style="Primary.TButton")
        self.apply_btn.pack(side="left")
        self.action_btn = ttk.Button(actions, text=t("동글 연결"), command=self._install, state="disabled")
        self.action_btn.pack(side="left", padx=10)
        self.refresh_btn = ttk.Button(actions, text=t("다시 검색"), command=self.refresh)
        self.refresh_btn.pack(side="left")
        ttk.Button(actions, text=t("닫기"), command=self._close).pack(side="right")
        self.copy_btn = ttk.Button(frm, text=t("USB 진단 정보 복사"), command=self._copy_diagnostics, state="disabled")
        self.copy_btn.grid(row=6, column=0, sticky="w", pady=(12, 0))
        self._poll()
        self.refresh()

    def _log(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.insert("end", text + "\n")
        self.detail.see("end")
        self.detail.configure(state="disabled")

    def _ambiguous(self) -> bool:
        return self._dongle is not None and sum(d.vidpid == self._dongle.vidpid for d in self._candidates) > 1

    def _controls(self):
        self.refresh_btn.configure(state="disabled" if self._busy else "normal")
        chosen = self._dongle is not None and not self._busy and not self._ambiguous()
        self.apply_btn.configure(state="normal" if chosen and self.on_apply is not None and self._dongle.identity != self._active_adapter_id else "disabled")
        self.action_btn.configure(state="normal" if chosen and self._dongle.driver != "unknown" else "disabled")
        self.devices.configure(selectmode="none" if self._busy else "browse")

    def _render_devices(self):
        self.devices.delete(*self.devices.get_children())
        self._rows.clear()
        self._dongle = None
        for index, dongle in enumerate(self._candidates):
            row = str(index)
            self._rows[row] = dongle
            binding = {"winusb": "WinUSB", "inbox": t("Windows Bluetooth"), "unknown": t("확인 필요")}[dongle.driver]
            applied = t("적용됨") if dongle.identity == self._active_adapter_id else ""
            self.devices.insert("", "end", iid=row, values=(dongle.label, f"{dongle.vid:04X}:{dongle.pid:04X}", binding, dongle.location or "—", applied), tags=("alternate",) if index % 2 else ())
            if dongle.identity == self._preview_id:
                self.devices.selection_set(row)
                self.devices.focus(row)
                self._dongle = dongle
        self._show_dongle()

    def _select(self, _event=None):
        if self._busy:
            return
        selected = self.devices.selection()
        self._dongle = self._rows.get(selected[0]) if selected else None
        self._preview_id = self._dongle.identity if self._dongle else ""
        self._show_dongle()

    def set_active_adapter(self, identity: str):
        """Update the saved marker without changing the user's preview selection."""
        self._active_adapter_id = identity
        for row, dongle in self._rows.items():
            self.devices.set(row, "applied", t("적용됨") if dongle.identity == identity else "")

    def _poll(self):
        if self._closed:
            return
        try:
            while True:
                kind, result = self._results.get_nowait()
                self._busy = False
                if kind == "scan":
                    devices, error = result
                    self._diagnostic_text = report_text(build_report(devices, error))
                    self.copy_btn.configure(state="normal")
                    self._candidates = driver.list_dongles(devices=devices) if not error else []
                    self._render_devices()
                    if error:
                        self.status_var.set(t("동글을 검색하지 못했습니다. 다시 시도해 주세요."))
                        self._log(error)
                    else:
                        self._log(t("USB 장치 {count}개, Bluetooth 후보 {adapters}개", count=len(devices), adapters=len(self._candidates)))
                        if not self._candidates:
                            for entry in devices:
                                match = driver._VIDPID_RE.match(entry.get("InstanceId") or "")
                                if match:
                                    self._log(f"USB {match[1]}:{match[2]} · {entry.get('FriendlyName') or ''} · {entry.get('Class') or ''} · {entry.get('Service') or ''}")
                    self._controls()
                elif kind == "apply":
                    dongle, error = result
                    if error:
                        self._log(error)
                        messagebox.showerror(t("설정을 저장할 수 없습니다"), error, parent=self.win)
                        self._show_dongle()
                    else:
                        self._active_adapter_id = dongle.identity
                        self._preview_id = dongle.identity
                        self._render_devices()
                        self._log(t("{name} 동글을 적용했습니다.", name=dongle.label))
                        self.refresh()
                    self._controls()
                else:
                    error, done = result
                    if error:
                        self._log(error)
                        messagebox.showerror("Glideleaf", error, parent=self.win)
                    else:
                        self._log(done)
                        if kind == "reboot":
                            messagebox.showinfo("Glideleaf", done, parent=self.win)
                    self.refresh()
        except queue.Empty:
            pass
        self._timer = self.win.after(100, self._poll)

    def refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._controls()
        self.copy_btn.configure(state="disabled")
        self.status_var.set(t("USB 블루투스 동글을 찾고 있습니다…"))
        def worker():
            try:
                result = (driver._pnp_query(), None)
            except Exception as exc:
                result = ([], str(exc))
            self._results.put(("scan", result))
        threading.Thread(target=worker, daemon=True).start()

    def _copy_diagnostics(self):
        self.win.clipboard_clear()
        self.win.clipboard_append(self._diagnostic_text)
        self._log(t("USB 진단 정보를 복사했습니다."))

    def _show_dongle(self):
        d = self._dongle
        if d is None:
            self.status_var.set(t("목록에서 사용할 동글을 선택해 주세요.") if self._candidates else t("USB 블루투스 동글을 찾지 못했습니다.\n지원 동글을 연결하고 다시 검색하세요. Realtek RTL8761B 계열을 권장합니다."))
            self._controls()
            return
        if self._ambiguous():
            self.status_var.set(t("같은 USB ID의 동글이 여러 개입니다. 사용할 동글 하나만 연결한 뒤 다시 검색해 주세요."))
        elif d.is_winusb:
            self.status_var.set(t("{name}: 적용된 동글입니다. 연결 패널에서 연결을 시작하세요.", name=d.label) if d.identity == self._active_adapter_id else t("{name}: WinUSB 준비 완료. 선택한 동글을 적용한 뒤 연결 패널에서 시작하세요.", name=d.label))
            self.action_btn.configure(text=t("일반 Bluetooth로 복원"), command=self._restore)
        elif d.driver == "unknown":
            self.status_var.set(t("{name}: 장치는 발견했지만 드라이버를 확인하지 못했습니다. USB 진단 정보를 복사해 주세요.", name=d.label))
        else:
            self.status_var.set(t("{name}: Windows Bluetooth 사용 중. 동글 연결을 누르면 설정과 연결을 진행합니다. 복원하기 전까지 이 동글의 일반 Bluetooth 기능을 사용할 수 없습니다.", name=d.label))
            self.action_btn.configure(text=t("동글 연결"), command=self._install)
        self._controls()

    def _apply_selected(self):
        d = self._dongle
        if d is None or self.on_apply is None or self._busy or self._ambiguous():
            return
        self._busy = True
        self._controls()
        self.status_var.set(t("선택한 동글을 적용하고 있습니다…"))
        def worker():
            error = None
            try:
                self.on_apply(d)
            except Exception as exc:
                error = str(exc)
            self._results.put(("apply", (d, error)))
        threading.Thread(target=worker, daemon=True).start()

    def _install(self) -> None:
        d = self._dongle
        if d is None or self._busy or self._ambiguous():
            return
        if not messagebox.askyesno(t("동글 드라이버 전환"), t("{name}을 WinUSB로 전환할까요?\n\n복원하기 전까지 이 동글의 일반 Bluetooth 기능을 사용할 수 없습니다.", name=d.label) + "\n\n" + t("USB ID {usb_id}인 선택한 동글을 앱에서 설정하고 연결합니다. Windows 관리자 권한 요청을 확인해 주세요.", usb_id=f"{d.vid:04X}:{d.pid:04X}"), parent=self.win):
            return
        def action():
            if self.on_apply is not None:
                self.on_apply(d)
            driver.install_winusb_elevated(d.vid, d.pid, adapter_id=d.identity)
            if self.on_ready is not None:
                self.on_ready()
        from ..inbox_driver import probe
        self._run_driver(d, action, t("선택한 동글을 설정하고 있습니다… Windows 관리자 권한 요청을 확인하세요."), t("동글 설정을 완료했습니다. 연결 상태를 확인해 주세요."), preflight=lambda: probe(d.instance_id))

    def _restore(self) -> None:
        d = self._dongle
        if d is None or self._busy or self._ambiguous():
            return
        self._run_driver(d, lambda: driver.restore_inbox_elevated(d.vid, d.pid, adapter_id=d.identity), t("기존 Bluetooth 드라이버로 복원 중…"), t("복원을 요청했습니다. 동글을 다시 검색합니다…"))

    def _run_driver(self, dongle, action, busy, done, *, preflight=None):
        self._busy = True
        self._controls()
        self.status_var.set(busy)
        def worker():
            error = None
            try:
                if preflight is not None:
                    preflight()
                if self.prepare_driver is not None:
                    self.prepare_driver(dongle)
                action()
            except RebootRequired as exc:
                self._results.put(("reboot", (None, str(exc))))
                return
            except Exception as exc:
                error = str(exc)
            self._results.put(("operation", (error, done)))
        threading.Thread(target=worker, daemon=True).start()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.win.after_cancel(self._timer)
        self.win.destroy()
        if self.on_done is not None:
            self.on_done()
