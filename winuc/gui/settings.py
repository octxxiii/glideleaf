"""Settings dialog (Tkinter) bound to a Config object."""

from __future__ import annotations

from ..i18n import t
from ..i18n import LANGUAGES

import tkinter as tk
from tkinter import ttk, messagebox
from copy import deepcopy
from typing import Callable

from ..config import Config
from .theme import configure, font_family
from .icons import apply_window_icon
from .layout_diagram import clamp_center, draw_layout, layout_from_point

_EDGE_LABELS = {"right": "오른쪽", "left": "왼쪽", "top": "위쪽", "bottom": "아래쪽"}
_ACTION_LABELS = {"(none)": "사용 안 함", "drag_scroll": "누른 채 움직여 스크롤", "wheel_up": "위로 스크롤", "wheel_down": "아래로 스크롤"}
_ACTION_BUTTONS = ["x1", "x2", "middle"]


class SettingsWindow:
    """Modeless settings editor. Calls on_apply(new_config) when saved."""

    def __init__(
        self,
        root: tk.Tk,
        config: Config,
        on_apply: Callable[[Config], None],
    ) -> None:
        configure(root)
        self.config = config
        self._edge_labels = {key: t(value) for key, value in _EDGE_LABELS.items()}
        self._action_labels = {key: t(value) for key, value in _ACTION_LABELS.items()}
        self._language_labels = dict(LANGUAGES)
        self._language_labels["auto"] = t("시스템 언어 자동 선택")
        self.on_apply = on_apply
        self.win = tk.Toplevel(root)
        self.win.title(t("Glideleaf 설정"))
        apply_window_icon(self.win)
        width = min(880, max(700, self.win.winfo_screenwidth() - 80))
        height = min(780, max(640, self.win.winfo_screenheight() - 60))
        self._layout_canvas_height = min(230, max(140, height - 520))
        self.win.geometry(f"{width}x{height}")
        self.win.minsize(width, height)
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(3, weight=1)

        self.vars: dict[str, tk.Variable] = {}
        nb = ttk.Notebook(self.win)
        ttk.Label(self.win, text=t("나에게 맞는 입력 공유"), font=(font_family(), 16, "bold"), padding=(22, 20, 22, 6)).grid(row=0, column=0, sticky="w")
        ttk.Label(self.win, text=t("저장하면 연결을 다시 시작해 설정을 적용합니다."), wraplength=620, padding=(22, 0, 22, 14)).grid(row=1, column=0, sticky="w")
        language_bar = ttk.Frame(self.win, padding=(22, 0, 22, 8))
        language_bar.grid(row=2, column=0, sticky="ew")
        ttk.Label(language_bar, text=t("언어")).pack(side="left", padx=(0, 12))
        self.vars["language"] = tk.StringVar(value=self._language_labels[config.language])
        ttk.Combobox(language_bar, textvariable=self.vars["language"], values=list(self._language_labels.values()), state="readonly", width=30).pack(side="left")
        nb.grid(row=3, column=0, padx=18, pady=10, sticky="nsew")
        self._build_layout_tab(nb)
        self._build_movement_tab(nb)
        self._build_keyboard_tab(nb)
        self._build_buttons_tab(nb)
        self._build_device_tab(nb)

        bar = ttk.Frame(self.win)
        bar.grid(row=4, column=0, sticky="e", padx=10, pady=(0, 10))
        ttk.Button(bar, text=t("취소"), command=self.win.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(bar, text=t("저장 및 적용"), command=self._save, style="Primary.TButton").grid(row=0, column=1, padx=4)

    # --------------------------------------------------------------- tabs

    def _row(self, parent, r, label, widget):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=6, pady=4)
        widget.grid(row=r, column=1, sticky="ew", padx=6, pady=4)
        parent.columnconfigure(1, weight=1)

    def _build_layout_tab(self, nb):
        f = ttk.Frame(nb, padding=(14, 10))
        nb.add(f, text=t("화면 배치"))
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text=t("iPad를 끌어 놓아 PC 주변 위치를 정하세요. 초록색 선이 포인터가 넘어가는 구간입니다."),
                  wraplength=540, foreground="#53697A").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self.vars["edge"] = tk.StringVar(value=self._edge_labels[self.config.edge])
        self._row(f, 1, t("iPad 위치"), ttk.Combobox(
            f, textvariable=self.vars["edge"], values=list(self._edge_labels.values()), state="readonly", width=14))
        self.layout_canvas = tk.Canvas(f, width=540, height=self._layout_canvas_height,
                                       bg="#F4F7F8", highlightthickness=0, cursor="hand2")
        self.layout_canvas.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 11))
        self.layout_canvas.bind("<Configure>", lambda _event: self._render_layout())
        self.layout_canvas.bind("<ButtonPress-1>", self._start_layout_drag)
        self.layout_canvas.bind("<B1-Motion>", self._move_layout_drag)
        self.layout_canvas.bind("<ButtonRelease-1>", lambda _event: setattr(self, "_layout_dragging", False))
        self._layout_dragging = False
        self.vars["layout_center_pct"] = tk.DoubleVar(value=self.config.layout_center_pct)
        self.vars["layout_span_pct"] = tk.DoubleVar(value=self.config.layout_span_pct)
        self._row(f, 3, t("연결 구간 중심 (%)"), ttk.Scale(
            f, variable=self.vars["layout_center_pct"], from_=0, to=100,
            command=lambda _value: self._render_layout()))
        self._row(f, 4, t("연결 구간 길이 (%)"), ttk.Scale(
            f, variable=self.vars["layout_span_pct"], from_=20, to=100,
            command=lambda _value: self._render_layout()))
        self.layout_summary = tk.StringVar()
        ttk.Label(f, textvariable=self.layout_summary, foreground="#53697A").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.vars["edge"].trace_add("write", lambda *_args: self._render_layout())
        self._render_layout()

    def _render_layout(self):
        edge = {v: k for k, v in self._edge_labels.items()}[self.vars["edge"].get()]
        span = round(self.vars["layout_span_pct"].get())
        center = clamp_center(round(self.vars["layout_center_pct"].get()), span)
        if round(self.vars["layout_center_pct"].get()) != center:
            self.vars["layout_center_pct"].set(center)
        self._layout_pc = draw_layout(self.layout_canvas, edge, center, span)
        self.layout_summary.set(t("{side} · 가장자리 {span}% 사용", side=self.vars["edge"].get(), span=span))

    def _start_layout_drag(self, event):
        x1, y1, x2, y2 = self._layout_pc
        self._layout_dragging = not (x1 <= event.x <= x2 and y1 <= event.y <= y2)
        if self._layout_dragging:
            self._move_layout_drag(event)

    def _move_layout_drag(self, event):
        if not self._layout_dragging:
            return
        edge, center = layout_from_point(event.x, event.y, self._layout_pc,
                                         round(self.vars["layout_span_pct"].get()))
        self.vars["edge"].set(self._edge_labels[edge])
        self.vars["layout_center_pct"].set(center)
        self._render_layout()

    def _build_movement_tab(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text=t("포인터"))

        self.vars["speed"] = tk.DoubleVar(value=self.config.speed)
        self._row(f, 0, t("포인터 속도"), ttk.Spinbox(
            f, textvariable=self.vars["speed"], from_=0.2, to=5.0, increment=0.1, width=8))

        self.vars["push_threshold_px"] = tk.IntVar(value=self.config.push_threshold_px)
        self._row(f, 1, t("진입 저항 (px)"), ttk.Spinbox(
            f, textvariable=self.vars["push_threshold_px"], from_=10, to=400, increment=10, width=8))

        self.vars["return_threshold_px"] = tk.IntVar(value=self.config.return_threshold_px)
        self._row(f, 2, t("복귀 저항 (px)"), ttk.Spinbox(
            f, textvariable=self.vars["return_threshold_px"], from_=10, to=400, increment=10, width=8))

        self.vars["natural_scroll"] = tk.BooleanVar(value=self.config.natural_scroll)
        self._row(f, 3, t("자연스러운 스크롤"), ttk.Checkbutton(
            f, variable=self.vars["natural_scroll"]))

        self.vars["ipad_w"] = tk.IntVar(value=int(self.config.ipad_screen[0]))
        self.vars["ipad_h"] = tk.IntVar(value=int(self.config.ipad_screen[1]))
        size = ttk.Frame(f)
        ttk.Spinbox(size, textvariable=self.vars["ipad_w"], from_=640, to=4000, width=7).grid(row=0, column=0)
        ttk.Label(size, text=" × ").grid(row=0, column=1)
        ttk.Spinbox(size, textvariable=self.vars["ipad_h"], from_=480, to=4000, width=7).grid(row=0, column=2)
        self._row(f, 4, t("iPad 화면 크기 (pt)"), size)

    def _build_keyboard_tab(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text=t("키보드"))

        self.vars["swap_alt_win"] = tk.BooleanVar(value=self.config.swap_alt_win)
        self._row(f, 0, t("Alt / Win 교환 (Alt를 ⌘로 사용)"), ttk.Checkbutton(
            f, variable=self.vars["swap_alt_win"]))

        self.vars["jis_mac_style"] = tk.BooleanVar(value=self.config.jis_mac_style)
        self._row(f, 1, t("일본어 JIS 키보드: 변환/무변환 → 일본어/영문 입력"), ttk.Checkbutton(
            f, variable=self.vars["jis_mac_style"]))

        self.vars["release_hotkey"] = tk.StringVar(value=self.config.release_hotkey)
        self._row(f, 2, t("Windows 긴급 복귀 단축키"), ttk.Entry(
            f, textvariable=self.vars["release_hotkey"], width=16))

    def _build_buttons_tab(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text=t("마우스 버튼"))
        ttk.Label(
            f,
            text=t("추가 버튼으로 스크롤을 조작하세요.\n"
                 "iPad를 제어하는 동안에만 적용됩니다."),
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self._btn_vars: dict[str, tk.StringVar] = {}
        for i, name in enumerate(_ACTION_BUTTONS, start=1):
            current = self.config.button_actions.get(name, "(none)")
            var = tk.StringVar(value=self._action_labels.get(current, t("사용 안 함")))
            self._btn_vars[name] = var
            self._row(f, i, {"x1": t("뒤로 버튼 (X1)"), "x2": t("앞으로 버튼 (X2)"), "middle": t("휠 클릭")}[name], ttk.Combobox(
                f, textvariable=var, values=list(self._action_labels.values()), state="readonly", width=32))

        self.vars["drag_scroll_px"] = tk.IntVar(value=self.config.drag_scroll_px)
        self._row(f, len(_ACTION_BUTTONS) + 1, t("드래그 스크롤 감도 (px/칸)"),
                  ttk.Spinbox(f, textvariable=self.vars["drag_scroll_px"], from_=5, to=200, width=8))

        self.vars["drag_scroll_invert"] = tk.BooleanVar(value=self.config.drag_scroll_invert)
        self._row(f, len(_ACTION_BUTTONS) + 2, t("드래그 스크롤 반전"),
                  ttk.Checkbutton(f, variable=self.vars["drag_scroll_invert"]))

    def _build_device_tab(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text=t("고급 연결"))

        self.vars["device_name"] = tk.StringVar(value=self.config.device_name)
        self._row(f, 0, t("블루투스 이름"), ttk.Entry(
            f, textvariable=self.vars["device_name"], width=28))

        self.vars["transport"] = tk.StringVar(value=self.config.transport)
        self._row(f, 1, t("동글 연결 경로"), ttk.Entry(
            f, textvariable=self.vars["transport"], width=28))

        self.vars["address"] = tk.StringVar(value=self.config.address)
        self._row(f, 2, t("고정 BLE 주소"), ttk.Entry(
            f, textvariable=self.vars["address"], width=28))

    # -------------------------------------------------------------- apply

    def _save(self):
        try:
            self._apply_values()
        except (ValueError, TypeError, tk.TclError, OSError) as exc:
            if isinstance(exc, tk.TclError):
                exc = ValueError(t("숫자 입력을 확인해 주세요."))
            messagebox.showerror(t("설정을 저장할 수 없습니다"), str(exc), parent=self.win)

    def _apply_values(self):
        c = deepcopy(self.config)
        c.language = {v: k for k, v in self._language_labels.items()}[self.vars["language"].get()]
        c.edge = {v: k for k, v in self._edge_labels.items()}[self.vars["edge"].get()]
        c.layout_span_pct = round(self.vars["layout_span_pct"].get())
        c.layout_center_pct = clamp_center(round(self.vars["layout_center_pct"].get()), c.layout_span_pct)
        c.speed = float(self.vars["speed"].get())
        c.push_threshold_px = int(self.vars["push_threshold_px"].get())
        c.return_threshold_px = int(self.vars["return_threshold_px"].get())
        c.natural_scroll = bool(self.vars["natural_scroll"].get())
        c.ipad_screen = (int(self.vars["ipad_w"].get()), int(self.vars["ipad_h"].get()))
        c.swap_alt_win = bool(self.vars["swap_alt_win"].get())
        c.jis_mac_style = bool(self.vars["jis_mac_style"].get())
        c.release_hotkey = self.vars["release_hotkey"].get().strip() or "ctrl+alt+q"
        c.button_actions = {
            name: {v: k for k, v in self._action_labels.items()}[var.get()]
            for name, var in self._btn_vars.items()
            if var.get() != self._action_labels["(none)"]
        }
        c.drag_scroll_px = int(self.vars["drag_scroll_px"].get())
        c.drag_scroll_invert = bool(self.vars["drag_scroll_invert"].get())
        c.device_name = self.vars["device_name"].get().strip() or "Windows Pointer & Keyboard"
        c.transport = self.vars["transport"].get().strip()
        if c.transport != self.config.transport:
            c.adapter_id = ""  # An explicit manual transport overrides the saved picker.
        c.address = self.vars["address"].get().strip()

        c.validate()
        self.on_apply(c)
        self.win.destroy()
