"""First-run setup wizard: firmware, dongle driver, and pairing guidance."""

from __future__ import annotations

from ..i18n import t

import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable

from .. import driver
from ..diagnostics import build_report, report_text
from .theme import configure


class SetupWizard:
    def __init__(self, root: tk.Tk, on_done: Callable[[], None] | None = None) -> None:
        configure(root)
        self.on_done = on_done
        self._results = queue.SimpleQueue()
        self._closed = False
        self._busy = False
        self._diagnostic_text = ""
        self.win = tk.Toplevel(root)
        self.win.title(t("Glideleaf 동글 설정"))
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self._close)
        self._dongle: driver.Dongle | None = None

        frm = ttk.Frame(self.win, padding=16)
        frm.grid(sticky="nsew")

        ttk.Label(frm, text=t("전용 동글 연결하기"), font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        self.status_var = tk.StringVar(value=t("블루투스 동글 검색 중…"))
        ttk.Label(frm, textvariable=self.status_var, wraplength=440, justify="left").grid(
            row=1, column=0, columnspan=2, sticky="w")

        self.detail = tk.Text(frm, height=8, width=60, state="disabled", wrap="word")
        self.detail.grid(row=2, column=0, columnspan=2, pady=10)

        self.action_btn = ttk.Button(frm, text=t("다시 검색"), command=self.refresh)
        self.action_btn.grid(row=3, column=0, sticky="w")
        ttk.Button(frm, text=t("닫기"), command=self._close).grid(row=3, column=1, sticky="e")
        self.copy_btn = ttk.Button(frm, text=t("USB 진단 정보 복사"), command=self._copy_diagnostics, state="disabled")
        self.copy_btn.grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))

        self._poll()
        self.refresh()

    # ----------------------------------------------------------- helpers

    def _log(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.insert("end", text + "\n")
        self.detail.see("end")
        self.detail.configure(state="disabled")

    def _set_action(self, label: str, command) -> None:
        self.action_btn.configure(text=label, command=command)

    # ------------------------------------------------------------- steps

    def _poll(self):
        if self._closed:
            return
        try:
            while True:
                kind, result = self._results.get_nowait()
                self._busy = False
                self.action_btn.configure(state="normal")
                if kind == "scan":
                    devices, error = result
                    self._diagnostic_text = report_text(build_report(devices, error))
                    self.copy_btn.configure(state="normal")
                    if error:
                        self.status_var.set(t("동글을 검색하지 못했습니다. 다시 시도해 주세요."))
                        self._dongle = None
                        self._log(error)
                        self._set_action(t("다시 검색"), self.refresh)
                    else:
                        candidates = driver.list_dongles(devices=devices)
                        self._dongle = next((d for d in candidates if d.vidpid in driver.KNOWN_DONGLES), candidates[0] if candidates else None)
                        self._log(t("USB 장치 {count}개, Bluetooth 후보 {adapters}개", count=len(devices), adapters=len(candidates)))
                        if not candidates:
                            for entry in devices:
                                match = driver._VIDPID_RE.match(entry.get("InstanceId") or "")
                                if match:
                                    self._log(f"USB {match[1]}:{match[2]} · {entry.get('FriendlyName') or ''} · {entry.get('Class') or ''} · {entry.get('Service') or ''}")
                        self._show_dongle()
                else:
                    self._after(*result)
        except queue.Empty:
            pass
        self._timer = self.win.after(100, self._poll)

    def refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.action_btn.configure(state="disabled")
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
        if self._dongle is None:
            self.status_var.set(
                t("USB 블루투스 동글을 찾지 못했습니다.\n"
                "지원 동글을 연결하고 다시 검색하세요. Realtek RTL8761B 계열을 권장합니다.")
            )
            self._set_action(t("다시 검색"), self.refresh)
            return

        d = self._dongle
        self._log(t("발견: {name} (VID_{vid}&PID_{pid}, 드라이버={driver})", name=d.label, vid=f"{d.vid:04X}", pid=f"{d.pid:04X}", driver=d.driver))
        if d.is_winusb:
            self.status_var.set(
                t("{name} · WinUSB 준비 완료\n"
                "이 창을 닫고 연결 패널에서 연결을 시작하세요.\n"
                "iPad의 설정 → Bluetooth에서 페어링할 수 있습니다.", name=d.label)
            )
            self._set_action(t("일반 Bluetooth로 복원"), self._restore)
        elif d.driver == "unknown":
            self.status_var.set(t("{name}: 장치는 발견했지만 드라이버를 확인하지 못했습니다. USB 진단 정보를 복사해 주세요.", name=d.label))
            self._set_action(t("다시 검색"), self.refresh)
        else:
            self.status_var.set(
                t("{name} · 기본 Bluetooth 드라이버 사용 중\n\n"
                "입력 공유를 사용하려면 WinUSB로 전환해야 합니다.\n"
                "전환 중에는 이 동글로 이어폰·게임패드 등 일반 Bluetooth 기기를 사용할 수 없습니다.\n"
                "전용 동글 사용을 권장합니다.\n\n"
                "관리자 권한 요청이 한 번 표시됩니다.", name=d.label)
            )
            self._set_action(t("WinUSB로 전환"), self._install)

    def _install(self) -> None:
        d = self._dongle
        if d is None:
            return
        if not messagebox.askyesno(
            t("동글 드라이버 전환"),
            t("{name}을 WinUSB로 전환할까요?\n\n"
            "복원하기 전까지 이 동글의 일반 Bluetooth 기능을 사용할 수 없습니다.", name=d.label),
            parent=self.win,
        ):
            return
        self._run_async(
            lambda: driver.install_winusb_elevated(d.vid, d.pid),
            busy=t("WinUSB로 전환 중… 관리자 권한 요청을 확인하세요."),
            done=t("전환 완료. 동글을 다시 검색합니다…"),
        )

    def _restore(self) -> None:
        d = self._dongle
        if d is None:
            return
        self._run_async(
            lambda: driver.restore_inbox_elevated(d.vid, d.pid),
            busy=t("기존 Bluetooth 드라이버로 복원 중…"),
            done=t("복원을 요청했습니다. 동글을 다시 검색합니다…"),
        )

    def _run_async(self, fn: Callable[[], None], busy: str, done: str) -> None:
        self._busy = True
        self.status_var.set(busy)
        self.action_btn.configure(state="disabled")

        def worker():
            error = None
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                error = str(exc)
            self._results.put(("operation", (error, done)))

        threading.Thread(target=worker, daemon=True).start()

    def _after(self, error: str | None, done: str) -> None:
        self.action_btn.configure(state="normal")
        if error:
            self._log("Error: " + error)
            messagebox.showerror("Glideleaf", error, parent=self.win)
        else:
            self._log(done)
        self.refresh()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.win.after_cancel(self._timer)
        self.win.destroy()
        if self.on_done is not None:
            self.on_done()
