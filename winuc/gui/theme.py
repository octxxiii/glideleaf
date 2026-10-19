"""Shared, dependency-free desktop palette."""
from tkinter import ttk

BG = "#F4F7F8"
INK = "#15283D"
MUTED = "#53697A"
BLUE = "#176D67"
LINE = "#DCE6E7"


def font_family():
    from ..i18n import get_language
    return {"ko": "Malgun Gothic", "ja": "Yu Gothic UI", "zh-Hans": "Microsoft YaHei UI", "zh-Hant": "Microsoft JhengHei UI"}.get(get_language(), "Segoe UI")


def configure(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=(font_family(), 10), background=BG, foreground=INK)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG)
    style.configure("TButton", padding=(15, 10), background="#FFFFFF", foreground=INK, borderwidth=1, relief="flat")
    style.map("TButton", background=[("active", "#EAF3F0"), ("disabled", "#F0F3F3")],
              foreground=[("disabled", "#8DA0A8"), ("active", INK)])
    style.configure("Primary.TButton", background=BLUE, foreground="white", borderwidth=0)
    style.map("Primary.TButton", background=[("disabled", "#A9CAC4"), ("active", "#105A55")], foreground=[("disabled", "#FFFFFF"), ("active", "#FFFFFF")])
    style.configure("TLabel", foreground=INK)
    style.configure("Treeview", font=(font_family(), 10), rowheight=35, background="#FFFFFF",
                    fieldbackground="#FFFFFF", foreground=INK, borderwidth=0)
    style.configure("Treeview.Heading", font=(font_family(), 9, "bold"), padding=(10, 11),
                    background="#EAF0F0", foreground=MUTED, borderwidth=0)
    style.map("Treeview", background=[("selected", "#D9EEE8")], foreground=[("selected", INK)])
    style.map("Treeview.Heading", background=[("active", "#DFEAE8")])
    style.configure("TNotebook", borderwidth=0)
    style.configure("TNotebook.Tab", padding=(16, 10))
    style.map("TNotebook.Tab", background=[("selected", "white")], foreground=[("selected", BLUE)])
    style.configure("TEntry", padding=7, fieldbackground="white")
    style.configure("TSpinbox", padding=6, fieldbackground="white")
    root.configure(bg=BG)
