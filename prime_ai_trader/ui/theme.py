from __future__ import annotations

from tkinter import ttk


COLORS = {
    "bg": "#070B12", "panel": "#0D1420", "card": "#111B2A", "card_alt": "#0B1220",
    "border": "#223047", "text": "#EDF4FF", "muted": "#8290A7", "accent": "#2E7DFF",
    "accent2": "#51A7FF", "green": "#29D391", "red": "#FF5E6C", "amber": "#F5B544",
    "grid": "#1A2638", "purple": "#9D7BFF",
}


def configure_style(root) -> ttk.Style:
    root.configure(bg=COLORS["bg"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TFrame", background=COLORS["bg"])
    style.configure("Panel.TFrame", background=COLORS["panel"])
    style.configure("Card.TFrame", background=COLORS["card"], borderwidth=1, relief="solid")
    style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 10))
    style.configure("Panel.TLabel", background=COLORS["panel"], foreground=COLORS["text"])
    style.configure("Card.TLabel", background=COLORS["card"], foreground=COLORS["text"])
    style.configure("Muted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], font=("Segoe UI", 9))
    style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI Semibold", 15))
    style.configure("Signal.TLabel", background=COLORS["card"], foreground=COLORS["green"], font=("Segoe UI Semibold", 24))
    style.configure("TButton", background=COLORS["card"], foreground=COLORS["text"], padding=(12, 9), borderwidth=1, font=("Segoe UI Semibold", 9))
    style.map("TButton", background=[("active", COLORS["border"]), ("disabled", COLORS["card_alt"])], foreground=[("disabled", COLORS["muted"])])
    style.configure("Accent.TButton", background=COLORS["accent"], foreground="white")
    style.map("Accent.TButton", background=[("active", COLORS["accent2"])])
    style.configure("Danger.TButton", background="#3A1C27", foreground=COLORS["red"])
    style.configure("TCombobox", fieldbackground=COLORS["card_alt"], background=COLORS["card"], foreground=COLORS["text"], arrowcolor=COLORS["text"], padding=6)
    style.map("TCombobox", fieldbackground=[("readonly", COLORS["card_alt"])], foreground=[("readonly", COLORS["text"])])
    style.configure("TCheckbutton", background=COLORS["panel"], foreground=COLORS["text"])
    style.map("TCheckbutton", background=[("active", COLORS["panel"])])
    style.configure("Treeview", background=COLORS["card_alt"], foreground=COLORS["text"], fieldbackground=COLORS["card_alt"], rowheight=28, borderwidth=0)
    style.configure("Treeview.Heading", background=COLORS["card"], foreground=COLORS["text"], font=("Segoe UI Semibold", 9))
    style.map("Treeview", background=[("selected", COLORS["accent"])])
    return style

