"""First-run setup wizard: firmware, dongle driver, and pairing guidance."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable

from .. import driver


class SetupWizard:
    def __init__(self, root: tk.Tk, on_done: Callable[[], None] | None = None) -> None:
        self.on_done = on_done
        self.win = tk.Toplevel(root)
        self.win.title("WinUC Setup")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        self._dongle: driver.Dongle | None = None

        frm = ttk.Frame(self.win, padding=16)
        frm.grid(sticky="nsew")

        ttk.Label(frm, text="WinUC — first-time setup", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        self.status_var = tk.StringVar(value="Detecting Bluetooth dongle …")
        ttk.Label(frm, textvariable=self.status_var, wraplength=440, justify="left").grid(
            row=1, column=0, columnspan=2, sticky="w")

        self.detail = tk.Text(frm, height=8, width=60, state="disabled", wrap="word")
        self.detail.grid(row=2, column=0, columnspan=2, pady=10)

        self.action_btn = ttk.Button(frm, text="Refresh", command=self.refresh)
        self.action_btn.grid(row=3, column=0, sticky="w")
        ttk.Button(frm, text="Close", command=self._close).grid(row=3, column=1, sticky="e")

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

    def refresh(self) -> None:
        self._dongle = driver.find_dongle()
        if self._dongle is None:
            self.status_var.set(
                "No Bluetooth USB dongle detected. Plug in a supported dongle "
                "(Realtek RTL8761B recommended) and press Refresh."
            )
            self._set_action("Refresh", self.refresh)
            return

        d = self._dongle
        self._log(f"Found: {d.label}  (VID_{d.vid:04X}&PID_{d.pid:04X}, driver={d.driver})")
        if d.is_winusb:
            self.status_var.set(
                f"✓ {d.label} is bound to WinUSB and ready for WinUC.\n"
                "You can close this window and connect from your iPad's "
                "Settings › Bluetooth."
            )
            self._set_action("Restore normal Bluetooth", self._restore)
        else:
            self.status_var.set(
                f"{d.label} is currently on the standard Windows Bluetooth driver.\n\n"
                "To let WinUC use it, switch it to WinUSB. While switched, this "
                "dongle can't be used for normal Bluetooth (earbuds, controllers). "
                "Use a dedicated dongle if you want both.\n\n"
                "This needs administrator rights (one UAC prompt)."
            )
            self._set_action("Switch to WinUSB", self._install)

    def _install(self) -> None:
        d = self._dongle
        if d is None:
            return
        if not messagebox.askyesno(
            "Switch driver",
            f"Switch {d.label} to the WinUSB driver now?\n\n"
            "Normal Bluetooth on this dongle will stop working until you restore it.",
            parent=self.win,
        ):
            return
        self._run_async(
            lambda: driver.install_winusb_elevated(d.vid, d.pid),
            busy="Switching to WinUSB … approve the UAC prompt.",
            done="Driver switched. Re-detecting …",
        )

    def _restore(self) -> None:
        d = self._dongle
        if d is None:
            return
        self._run_async(
            lambda: driver.restore_inbox_elevated(d.vid, d.pid),
            busy="Restoring the standard Bluetooth driver …",
            done="Restore requested. Re-detecting …",
        )

    def _run_async(self, fn: Callable[[], None], busy: str, done: str) -> None:
        self.status_var.set(busy)
        self.action_btn.configure(state="disabled")

        def worker():
            error = None
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                error = str(exc)
            self.win.after(0, lambda: self._after(error, done))

        threading.Thread(target=worker, daemon=True).start()

    def _after(self, error: str | None, done: str) -> None:
        self.action_btn.configure(state="normal")
        if error:
            self._log("Error: " + error)
            messagebox.showerror("WinUC", error, parent=self.win)
        else:
            self._log(done)
        self.refresh()

    def _close(self) -> None:
        self.win.destroy()
        if self.on_done is not None:
            self.on_done()
