"""A small, live control panel for the tray application."""
from __future__ import annotations

from ..i18n import t

import os
import tkinter as tk
from tkinter import ttk

from ..paths import log_path
from .theme import BG, INK, MUTED, BLUE, configure, font_family


STATUS = {
    "stopped": ("연결 꺼짐", "연결 시작을 눌러 iPad 연결을 준비하세요."),
    "starting": ("연결 준비 중", "블루투스 동글을 준비하고 있습니다."),
    "advertising": ("iPad 연결 대기", "iPad의 설정 → Bluetooth에서 아래 기기 이름을 선택하세요."),
    "connected": ("iPad 연결됨", "키보드와 마우스를 사용할 준비를 하고 있습니다."),
    "ready": ("입력 공유 준비 완료", "설정한 화면 가장자리를 밀면 iPad로 제어가 넘어갑니다."),
    "error": ("연결을 확인해 주세요", "동글 설정과 아래 오류 내용을 확인한 후 다시 연결하세요."),
}
EDGES = {"right": "오른쪽", "left": "왼쪽", "top": "위쪽", "bottom": "아래쪽"}


class Dashboard:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title(t("Glideleaf · 연결 패널"))
        configure(app.root)
        self.win.geometry("740x880")
        self.win.minsize(700, 850)
        self.win.configure(bg=BG)
        self._timer = None
        self._last_log = None
        self._busy = False
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        body = ttk.Frame(self.win, padding=28)
        body.pack(fill="both", expand=True)
        header = ttk.Frame(body)
        header.pack(fill="x")
        ttk.Label(header, text="Glideleaf", font=("Segoe UI", 25, "bold")).pack(side="left")
        ttk.Label(header, text="PC → iPad   /   INPUT SHARING", foreground=MUTED, font=("Segoe UI", 9)).pack(side="right")
        ttk.Label(body, text=t("익숙한 마우스와 키보드, iPad에서도 그대로."), foreground=MUTED, wraplength=650, padding=(0, 4, 0, 22)).pack(anchor="w")
        card = tk.Frame(body, bg="white", padx=22, pady=20, highlightbackground="#E0E6F0", highlightthickness=1)
        card.pack(fill="x")
        self.badge = tk.Label(card, text="●", bg="white", fg=BLUE, font=("Segoe UI", 14))
        self.badge.pack(anchor="w")
        self.title = tk.StringVar()
        self.hint = tk.StringVar()
        tk.Label(card, textvariable=self.title, bg="white", fg=INK, wraplength=580, justify="left", font=(font_family(), 18, "bold")).pack(anchor="w", pady=(4, 6))
        tk.Label(card, textvariable=self.hint, bg="white", fg=MUTED, wraplength=580, justify="left", font=(font_family(), 10)).pack(anchor="w")
        self.toggle = ttk.Button(card, command=self.toggle_service, style="Primary.TButton")
        self.toggle.pack(anchor="w", pady=(18, 0))
        self.error = tk.StringVar()
        self.error_label = tk.Label(body, textvariable=self.error, bg=BG, fg="#B42318", wraplength=620, justify="left")
        self.diagram = tk.Canvas(body, height=132, bg=BG, highlightthickness=0)
        self.diagram.pack(fill="x", pady=(16, 0))
        self.diagram.bind("<Configure>", lambda event: self.draw_devices())
        self.device = tk.StringVar()
        ttk.Label(body, textvariable=self.device, foreground=MUTED, justify="left").pack(anchor="w", pady=(2, 12))
        actions = ttk.Frame(body)
        actions.pack(fill="x")
        ttk.Button(actions, text=t("포인터 · 키보드 설정"), command=app._open_settings).pack(side="left")
        ttk.Button(actions, text=t("동글 설정 / 복원"), command=app._open_wizard).pack(side="left", padx=8)
        ttk.Label(body, text=t("시작하기"), font=(font_family(), 11, "bold")).pack(anchor="w", pady=(20, 6))
        ttk.Label(body, text=t("① 전용 USB 동글 준비   →   ② iPad에서 Bluetooth 페어링\n③ 선택한 화면 가장자리를 밀어 제어 이동"), foreground=MUTED, wraplength=650, justify="left").pack(anchor="w")
        footer = ttk.Frame(body)
        footer.pack(fill="x", pady=(18, 0))
        self.log_toggle = ttk.Button(footer, text=t("진단 로그 펼치기"), command=self.toggle_logs)
        self.log_toggle.pack(side="left")
        ttk.Button(footer, text=t("오픈소스 정보"), command=self.show_about).pack(side="right")
        self.logs = ttk.Frame(body)
        self.log = tk.Text(self.logs, height=4, wrap="word", state="disabled", bg="#E9EDF5", fg=INK, relief="flat", font=("Consolas", 9), padx=10, pady=8)
        self.log.pack(fill="both", expand=True)
        ttk.Button(self.logs, text=t("전체 로그 열기"), command=self.open_log).pack(anchor="e", pady=4)
        self.refresh()

    def draw_devices(self):
        canvas = self.diagram
        canvas.delete("all")
        width = max(600, canvas.winfo_width())
        left, right = ("iPad", "Windows PC") if self.app.config.edge == "left" else ("Windows PC", "iPad")
        for x, label in ((width / 2 - 210, left), (width / 2 + 30, right)):
            canvas.create_rectangle(x, 10, x + 180, 102, fill="white", outline="#CFD8E8", width=2)
            canvas.create_text(x + 90, 52, text=label, fill=INK, font=("Segoe UI", 12, "bold"))
            canvas.create_line(x + 60, 112, x + 120, 112, fill="#B5C2D8", width=3)
        canvas.create_text(width / 2, 50, text="↔", fill=BLUE, font=("Segoe UI", 24))
        edge = EDGES[self.app.config.edge]
        canvas.create_text(width / 2, 88, text=t("{edge} 연결", edge=t(edge)), fill=MUTED, font=(font_family(), 9))

    def toggle_logs(self):
        if self.logs.winfo_manager():
            self.logs.pack_forget()
            self.log_toggle.configure(text=t("진단 로그 펼치기"))
            self.win.geometry("740x880")
        else:
            self.logs.pack(fill="both", expand=True, pady=(12, 0))
            self.log_toggle.configure(text=t("진단 로그 접기"))
            self.win.geometry("740x1040")

    def show_about(self):
        from tkinter import messagebox
        credits = "Copyright (c) 2026 fuba · MIT License\nBumble · Apache-2.0\npystray · LGPL-3.0 / libusb1 · LGPL-2.1+"
        messagebox.showinfo(t("Glideleaf · 오픈소스"), t("fuba 감사") + "\n\n" + credits + "\n\n" + t("독립 프로젝트 안내"), parent=self.win)

    def open_log(self):
        from tkinter import messagebox
        try:
            path = log_path()
            path.touch(exist_ok=True)
            os.startfile(path)
        except OSError as exc:
            messagebox.showerror(t("로그를 열 수 없습니다"), str(exc), parent=self.win)

    def toggle_service(self):
        # Use the tray's worker action so the main Tk thread remains responsive.
        import threading
        if self._busy:
            return
        self._busy = True
        self.toggle.configure(state="disabled")
        def worker():
            try:
                self.app._toggle_running()
            finally:
                self._busy = False
        threading.Thread(target=worker, daemon=True).start()

    def refresh(self):
        service, config = self.app.service, self.app.config
        title, hint = STATUS.get(service.status, (service.status, ""))
        self.title.set(t(title))
        self.hint.set(t(hint))
        color = "#16845B" if service.status == "ready" else "#C24236" if service.status == "error" else BLUE
        self.badge.configure(fg=color, text="●  " + "Bluetooth LE")
        self.draw_devices()
        self.device.set(t("Bluetooth  ·  {name}\n화면 위치  ·  {edge}\nWindows 긴급 복귀  ·  {hotkey}", name=config.device_name, edge=t(EDGES[config.edge]), hotkey=config.release_hotkey.upper()))
        self.toggle.configure(text=t("연결 중지") if service.running else t("연결 시작"))
        self.toggle.configure(state="disabled" if self._busy else "normal")
        self.error.set(service.last_error or "")
        if service.last_error:
            self.error_label.pack(after=self.toggle.master, fill="x", pady=(10, 0))
        else:
            self.error_label.pack_forget()
        try:
            with log_path().open("rb") as stream:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - 12000))
                text = stream.read().decode("utf-8", errors="replace")
        except OSError:
            text = t("아직 기록된 로그가 없습니다.")
        if text != self._last_log:
            self._last_log = text
            self.log.configure(state="normal")
            self.log.delete("1.0", "end")
            self.log.insert("end", text)
            self.log.see("end")
            self.log.configure(state="disabled")
        self._timer = self.win.after(1000, self.refresh)

    def close(self):
        if self._timer is not None:
            self.win.after_cancel(self._timer)
        self.win.destroy()
