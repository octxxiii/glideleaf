"""Settings dialog (Tkinter) bound to a Config object."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..config import Config

_EDGES = ["right", "left", "top", "bottom"]
_BUTTON_ACTIONS = ["(none)", "drag_scroll", "wheel_up", "wheel_down"]
_ACTION_BUTTONS = ["x1", "x2", "middle"]


class SettingsWindow:
    """Modeless settings editor. Calls on_apply(new_config) when saved."""

    def __init__(
        self,
        root: tk.Tk,
        config: Config,
        on_apply: Callable[[Config], None],
    ) -> None:
        self.config = config
        self.on_apply = on_apply
        self.win = tk.Toplevel(root)
        self.win.title("WinUC Settings")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)

        self.vars: dict[str, tk.Variable] = {}
        nb = ttk.Notebook(self.win)
        nb.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self._build_movement_tab(nb)
        self._build_keyboard_tab(nb)
        self._build_buttons_tab(nb)
        self._build_device_tab(nb)

        bar = ttk.Frame(self.win)
        bar.grid(row=1, column=0, sticky="e", padx=10, pady=(0, 10))
        ttk.Button(bar, text="Cancel", command=self.win.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(bar, text="Save & Apply", command=self._save).grid(row=0, column=1, padx=4)

    # --------------------------------------------------------------- tabs

    def _row(self, parent, r, label, widget):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=6, pady=4)
        widget.grid(row=r, column=1, sticky="ew", padx=6, pady=4)
        parent.columnconfigure(1, weight=1)

    def _build_movement_tab(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="Movement")

        self.vars["edge"] = tk.StringVar(value=self.config.edge)
        self._row(f, 0, "iPad is on the …", ttk.Combobox(
            f, textvariable=self.vars["edge"], values=_EDGES, state="readonly", width=12))

        self.vars["speed"] = tk.DoubleVar(value=self.config.speed)
        self._row(f, 1, "Pointer speed", ttk.Spinbox(
            f, textvariable=self.vars["speed"], from_=0.2, to=5.0, increment=0.1, width=8))

        self.vars["push_threshold_px"] = tk.IntVar(value=self.config.push_threshold_px)
        self._row(f, 2, "Push-through distance (px)", ttk.Spinbox(
            f, textvariable=self.vars["push_threshold_px"], from_=10, to=400, increment=10, width=8))

        self.vars["return_threshold_px"] = tk.IntVar(value=self.config.return_threshold_px)
        self._row(f, 3, "Push-back distance (px)", ttk.Spinbox(
            f, textvariable=self.vars["return_threshold_px"], from_=10, to=400, increment=10, width=8))

        self.vars["natural_scroll"] = tk.BooleanVar(value=self.config.natural_scroll)
        self._row(f, 4, "Natural scrolling", ttk.Checkbutton(
            f, variable=self.vars["natural_scroll"]))

        self.vars["ipad_w"] = tk.IntVar(value=int(self.config.ipad_screen[0]))
        self.vars["ipad_h"] = tk.IntVar(value=int(self.config.ipad_screen[1]))
        size = ttk.Frame(f)
        ttk.Spinbox(size, textvariable=self.vars["ipad_w"], from_=640, to=4000, width=7).grid(row=0, column=0)
        ttk.Label(size, text=" × ").grid(row=0, column=1)
        ttk.Spinbox(size, textvariable=self.vars["ipad_h"], from_=480, to=4000, width=7).grid(row=0, column=2)
        self._row(f, 5, "iPad screen (pt)", size)

    def _build_keyboard_tab(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="Keyboard")

        self.vars["swap_alt_win"] = tk.BooleanVar(value=self.config.swap_alt_win)
        self._row(f, 0, "Swap Alt / Win (use Alt as ⌘)", ttk.Checkbutton(
            f, variable=self.vars["swap_alt_win"]))

        self.vars["jis_mac_style"] = tk.BooleanVar(value=self.config.jis_mac_style)
        self._row(f, 1, "JIS 変換/無変換 → かな/英数", ttk.Checkbutton(
            f, variable=self.vars["jis_mac_style"]))

        self.vars["release_hotkey"] = tk.StringVar(value=self.config.release_hotkey)
        self._row(f, 2, "Force-return hotkey", ttk.Entry(
            f, textvariable=self.vars["release_hotkey"], width=16))

    def _build_buttons_tab(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="Mouse buttons")
        ttk.Label(
            f,
            text="Assign scroll actions to extra mouse buttons\n"
                 "(applied only while controlling the iPad).",
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self._btn_vars: dict[str, tk.StringVar] = {}
        for i, name in enumerate(_ACTION_BUTTONS, start=1):
            current = self.config.button_actions.get(name, "(none)")
            var = tk.StringVar(value=current if current in _BUTTON_ACTIONS else "(none)")
            self._btn_vars[name] = var
            self._row(f, i, f"Button {name}", ttk.Combobox(
                f, textvariable=var, values=_BUTTON_ACTIONS, state="readonly", width=14))

        self.vars["drag_scroll_px"] = tk.IntVar(value=self.config.drag_scroll_px)
        self._row(f, len(_ACTION_BUTTONS) + 1, "Drag-scroll sensitivity (px/notch)",
                  ttk.Spinbox(f, textvariable=self.vars["drag_scroll_px"], from_=5, to=200, width=8))

        self.vars["drag_scroll_invert"] = tk.BooleanVar(value=self.config.drag_scroll_invert)
        self._row(f, len(_ACTION_BUTTONS) + 2, "Invert drag-scroll",
                  ttk.Checkbutton(f, variable=self.vars["drag_scroll_invert"]))

    def _build_device_tab(self, nb):
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="Device")

        self.vars["device_name"] = tk.StringVar(value=self.config.device_name)
        self._row(f, 0, "Bluetooth name", ttk.Entry(
            f, textvariable=self.vars["device_name"], width=28))

        self.vars["transport"] = tk.StringVar(value=self.config.transport)
        self._row(f, 1, "bumble transport", ttk.Entry(
            f, textvariable=self.vars["transport"], width=28))

        self.vars["address"] = tk.StringVar(value=self.config.address)
        self._row(f, 2, "Static BLE address", ttk.Entry(
            f, textvariable=self.vars["address"], width=28))

    # -------------------------------------------------------------- apply

    def _save(self):
        c = self.config
        c.edge = self.vars["edge"].get()
        c.speed = float(self.vars["speed"].get())
        c.push_threshold_px = int(self.vars["push_threshold_px"].get())
        c.return_threshold_px = int(self.vars["return_threshold_px"].get())
        c.natural_scroll = bool(self.vars["natural_scroll"].get())
        c.ipad_screen = (int(self.vars["ipad_w"].get()), int(self.vars["ipad_h"].get()))
        c.swap_alt_win = bool(self.vars["swap_alt_win"].get())
        c.jis_mac_style = bool(self.vars["jis_mac_style"].get())
        c.release_hotkey = self.vars["release_hotkey"].get().strip() or "ctrl+alt+q"
        c.button_actions = {
            name: var.get()
            for name, var in self._btn_vars.items()
            if var.get() != "(none)"
        }
        c.drag_scroll_px = int(self.vars["drag_scroll_px"].get())
        c.drag_scroll_invert = bool(self.vars["drag_scroll_invert"].get())
        c.device_name = self.vars["device_name"].get().strip() or "Windows Pointer & Keyboard"
        c.transport = self.vars["transport"].get().strip()
        c.address = self.vars["address"].get().strip()

        self.on_apply(c)
        self.win.destroy()
