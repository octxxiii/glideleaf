"""Shared, dependency-free desktop palette."""
from tkinter import ttk

BG = "#F5F5F7"
INK = "#1D1D1F"
MUTED = "#6E6E73"
BLUE = "#187566"
LINE = "#E5E5E8"


def font_family():
    from ..i18n import get_language
    return {"ko": "Malgun Gothic", "ja": "Yu Gothic UI", "zh-Hans": "Microsoft YaHei UI", "zh-Hant": "Microsoft JhengHei UI"}.get(get_language(), "Segoe UI")


def configure(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=(font_family(), 10), background=BG, foreground=INK)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG)
    style.configure("TButton", padding=(15, 9), background="#FFFFFF", foreground=INK,
                    borderwidth=1, relief="flat", bordercolor=LINE)
    style.map("TButton", background=[("active", "#ECECEF"), ("disabled", "#F5F5F7")],
              foreground=[("disabled", "#A1A1A6"), ("active", INK)])
    style.configure("Primary.TButton", background=BLUE, foreground="white", borderwidth=0)
    style.map("Primary.TButton", background=[("disabled", "#ABCFC7"), ("active", "#115E52")], foreground=[("disabled", "#FFFFFF"), ("active", "#FFFFFF")])
    style.configure("TLabel", foreground=INK)
    style.configure("Treeview", font=(font_family(), 10), rowheight=34, background="#FFFFFF",
                    fieldbackground="#FFFFFF", foreground=INK, borderwidth=0)
    style.configure("Treeview.Heading", font=(font_family(), 9, "bold"), padding=(10, 11),
                    background="#F5F5F7", foreground=MUTED, borderwidth=0)
    style.map("Treeview", background=[("selected", "#E1F2ED")], foreground=[("selected", INK)])
    style.map("Treeview.Heading", background=[("active", "#EBEBEE")])
    style.configure("TNotebook", borderwidth=0)
    style.configure("TNotebook.Tab", padding=(16, 9), background=BG, foreground=MUTED)
    style.map("TNotebook.Tab", background=[("selected", "white"), ("active", "#EBEBEE")],
              foreground=[("selected", INK), ("active", INK)])
    style.configure("TEntry", padding=7, fieldbackground="white")
    style.configure("TSpinbox", padding=6, fieldbackground="white")
    root.configure(bg=BG)
