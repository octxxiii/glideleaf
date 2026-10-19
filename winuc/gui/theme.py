"""Shared, dependency-free desktop palette."""
from tkinter import ttk

BG = "#F3F5FA"
INK = "#172238"
MUTED = "#63718A"
BLUE = "#315CE8"


def font_family():
    from ..i18n import get_language
    return {"ko": "Malgun Gothic", "ja": "Yu Gothic UI", "zh-Hans": "Microsoft YaHei UI", "zh-Hant": "Microsoft JhengHei UI"}.get(get_language(), "Segoe UI")


def configure(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=(font_family(), 10), background=BG, foreground=INK)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG)
    style.configure("TButton", padding=(14, 9), background="#FFFFFF", borderwidth=1)
    style.map("TButton", background=[("active", "#E8EDFB")])
    style.configure("Primary.TButton", background=BLUE, foreground="white", borderwidth=0)
    style.map("Primary.TButton", background=[("disabled", "#A9B7E2"), ("active", "#2449C5")], foreground=[("disabled", "#FFFFFF")])
    style.configure("TNotebook", borderwidth=0)
    style.configure("TNotebook.Tab", padding=(16, 10))
    style.map("TNotebook.Tab", background=[("selected", "white")], foreground=[("selected", BLUE)])
    style.configure("TEntry", padding=7, fieldbackground="white")
    style.configure("TSpinbox", padding=6, fieldbackground="white")
    root.configure(bg=BG)
