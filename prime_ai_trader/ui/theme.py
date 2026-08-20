from __future__ import annotations

from tkinter import ttk


COLORS = {
    "bg": "#050B12", "panel": "#09131F", "card": "#0E1D2C", "card_alt": "#07111D",
    "border": "#1C3248", "text": "#F2F7FC", "muted": "#7F93A8", "accent": "#1E78FF",
    "accent2": "#49A6FF", "green": "#20D69B", "red": "#FF5265", "amber": "#F5B942",
    "grid": "#15283A", "purple": "#A77BFF",
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
    style.configure("Toolbar.TFrame", background=COLORS["panel"])
    style.configure("Card.TFrame", background=COLORS["card"], borderwidth=1, relief="solid")
    style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 10))
    style.configure("Panel.TLabel", background=COLORS["panel"], foreground=COLORS["text"])
    style.configure("Card.TLabel", background=COLORS["card"], foreground=COLORS["text"])
    style.configure("CardMuted.TLabel", background=COLORS["card"], foreground=COLORS["muted"], font=("Segoe UI", 9))
    style.configure("Muted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], font=("Segoe UI", 9))
    style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI Semibold", 15))
    style.configure("Section.TLabel", background=COLORS["panel"], foreground=COLORS["text"], font=("Segoe UI Semibold", 10))
    style.configure("Badge.TLabel", background=COLORS["card"], foreground=COLORS["accent2"], padding=(8, 4), font=("Segoe UI Semibold", 8))
    style.configure("Signal.TLabel", background=COLORS["card"], foreground=COLORS["green"], font=("Segoe UI Semibold", 24))
    style.configure("TButton", background=COLORS["card"], foreground=COLORS["text"], padding=(12, 9), borderwidth=1, font=("Segoe UI Semibold", 9))
    style.map("TButton", background=[("active", COLORS["border"]), ("disabled", COLORS["card_alt"])], foreground=[("disabled", COLORS["muted"])])
    style.configure("Accent.TButton", background=COLORS["accent"], foreground="white")
    style.map("Accent.TButton", background=[("active", COLORS["accent2"])])
    style.configure("Secondary.TButton", background=COLORS["card_alt"], foreground=COLORS["text"], padding=(9, 8))
    style.map("Secondary.TButton", background=[("active", COLORS["border"])])
    style.configure("Tool.TButton", background=COLORS["card_alt"], foreground=COLORS["muted"], padding=(7, 5), font=("Segoe UI Semibold", 8))
    style.map("Tool.TButton", background=[("active", COLORS["border"])], foreground=[("active", COLORS["text"])])
    style.configure("Danger.TButton", background="#3A1C27", foreground=COLORS["red"])
    style.configure("Score.Horizontal.TProgressbar", troughcolor=COLORS["card_alt"], background=COLORS["accent2"], bordercolor=COLORS["card_alt"], lightcolor=COLORS["accent2"], darkcolor=COLORS["accent2"])
    style.configure("Horizontal.TProgressbar", troughcolor=COLORS["card_alt"], background=COLORS["accent"], bordercolor=COLORS["panel"])
    style.configure("TCombobox", fieldbackground=COLORS["card_alt"], background=COLORS["card"], foreground=COLORS["text"], arrowcolor=COLORS["text"], padding=6)
    style.map("TCombobox", fieldbackground=[("readonly", COLORS["card_alt"])], foreground=[("readonly", COLORS["text"])])
    style.configure("TCheckbutton", background=COLORS["panel"], foreground=COLORS["text"])
    style.map("TCheckbutton", background=[("active", COLORS["panel"])])
    style.configure("Treeview", background=COLORS["card_alt"], foreground=COLORS["text"], fieldbackground=COLORS["card_alt"], rowheight=28, borderwidth=0)
    style.configure("Treeview.Heading", background=COLORS["card"], foreground=COLORS["text"], font=("Segoe UI Semibold", 9))
    style.map("Treeview", background=[("selected", COLORS["accent"])])
    return style
