from __future__ import annotations

from tkinter import ttk


COLORS = {
    "bg": "#00050B", "panel": "#070F17", "card": "#0B131C", "card_alt": "#050B12",
    "input": "#171E27", "border": "#24303C", "border_soft": "#17222D", "text": "#ECEDF0",
    "muted": "#969CA5", "accent": "#388FFF", "accent2": "#55A4FF", "green": "#40BF42",
    "green_dark": "#123719", "red": "#E94055", "amber": "#E6AE42", "grid": "#14202A",
    "purple": "#A36DFF",
}


def configure_style(root) -> ttk.Style:
    root.configure(bg=COLORS["bg"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    root.option_add("*TCombobox*Listbox.background", COLORS["card"])
    root.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", COLORS["border"])
    root.option_add("*TCombobox*Listbox.selectForeground", COLORS["text"])
    style.configure("TFrame", background=COLORS["bg"])
    style.configure("Panel.TFrame", background=COLORS["panel"])
    style.configure("Header.TFrame", background=COLORS["bg"])
    style.configure("Footer.TFrame", background=COLORS["panel"])
    style.configure("Toolbar.TFrame", background=COLORS["panel"])
    style.configure("Card.TFrame", background=COLORS["card"], borderwidth=1, relief="solid", bordercolor=COLORS["border"])
    style.configure("Inset.TFrame", background=COLORS["card_alt"], borderwidth=1, relief="solid", bordercolor=COLORS["border"])
    style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 10))
    style.configure("Panel.TLabel", background=COLORS["panel"], foreground=COLORS["text"])
    style.configure("Card.TLabel", background=COLORS["card"], foreground=COLORS["text"])
    style.configure("Inset.TLabel", background=COLORS["card_alt"], foreground=COLORS["text"])
    style.configure("InsetMuted.TLabel", background=COLORS["card_alt"], foreground=COLORS["muted"], font=("Segoe UI", 9))
    style.configure("CardMuted.TLabel", background=COLORS["card"], foreground=COLORS["muted"], font=("Segoe UI", 9))
    style.configure("Muted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], font=("Segoe UI", 9))
    style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 23, "bold"))
    style.configure("Section.TLabel", background=COLORS["panel"], foreground=COLORS["text"], font=("Segoe UI Semibold", 11))
    style.configure("Field.TLabel", background=COLORS["panel"], foreground=COLORS["text"], font=("Segoe UI Semibold", 10))
    style.configure("Badge.TLabel", background=COLORS["card"], foreground=COLORS["accent2"], padding=(7, 3), font=("Segoe UI Semibold", 8))
    style.configure("Status.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 10))
    style.configure("InsightTitle.TLabel", background=COLORS["card"], foreground=COLORS["text"], font=("Segoe UI Semibold", 11))
    style.configure("Signal.TLabel", background=COLORS["card"], foreground=COLORS["green"], font=("Segoe UI Semibold", 24))
    style.configure("TButton", background=COLORS["card"], foreground=COLORS["text"], padding=(9, 7), borderwidth=1, bordercolor=COLORS["border"], focuscolor=COLORS["card"], font=("Segoe UI Semibold", 9))
    style.map("TButton", background=[("active", COLORS["border"]), ("disabled", COLORS["card_alt"])], foreground=[("disabled", COLORS["muted"])])
    style.configure("Accent.TButton", background=COLORS["green"], foreground="white", bordercolor=COLORS["green"], focuscolor=COLORS["green"], padding=(9, 8), font=("Segoe UI", 11, "bold"))
    style.map("Accent.TButton", background=[("active", "#57D85A")])
    style.configure("Secondary.TButton", background=COLORS["card"], foreground=COLORS["text"], bordercolor=COLORS["border"], padding=(8, 7))
    style.map("Secondary.TButton", background=[("active", COLORS["border"])])
    style.configure("Tool.TButton", background=COLORS["panel"], foreground=COLORS["muted"], borderwidth=0, padding=(5, 5), font=("Segoe UI Semibold", 8))
    style.map("Tool.TButton", background=[("active", COLORS["border"])], foreground=[("active", COLORS["text"])])
    style.configure("Timeframe.TButton", background=COLORS["panel"], foreground=COLORS["muted"], borderwidth=0, padding=(7, 6), font=("Segoe UI", 9))
    style.map("Timeframe.TButton", background=[("active", COLORS["card"])], foreground=[("active", COLORS["accent2"])])
    style.configure("ActiveTimeframe.TButton", background=COLORS["card"], foreground=COLORS["accent2"], bordercolor=COLORS["accent2"], padding=(7, 6), font=("Segoe UI Semibold", 9))
    style.configure("Danger.TButton", background=COLORS["card"], foreground=COLORS["text"], bordercolor=COLORS["border"])
    style.configure("Backtest.TButton", background=COLORS["card_alt"], foreground=COLORS["accent2"], bordercolor=COLORS["accent2"], padding=(8, 7), font=("Segoe UI Semibold", 10))
    style.map("Backtest.TButton", background=[("active", "#0D2239")])
    style.configure("Train.TButton", background=COLORS["card_alt"], foreground=COLORS["purple"], bordercolor=COLORS["purple"], padding=(8, 7), font=("Segoe UI Semibold", 10))
    style.map("Train.TButton", background=[("active", "#21142F")])
    style.configure("Score.Horizontal.TProgressbar", troughcolor=COLORS["card_alt"], background=COLORS["green"], bordercolor=COLORS["card_alt"], lightcolor=COLORS["green"], darkcolor=COLORS["green"])
    style.configure("Horizontal.TProgressbar", troughcolor=COLORS["card_alt"], background=COLORS["accent"], bordercolor=COLORS["panel"])
    style.configure("TCombobox", fieldbackground=COLORS["input"], background=COLORS["input"], foreground=COLORS["text"], arrowcolor=COLORS["muted"], bordercolor=COLORS["border"], lightcolor=COLORS["border"], darkcolor=COLORS["border"], padding=(8, 6), font=("Segoe UI", 10))
    style.map("TCombobox", fieldbackground=[("readonly", COLORS["input"])], foreground=[("readonly", COLORS["text"])], selectbackground=[("readonly", COLORS["input"])], selectforeground=[("readonly", COLORS["text"])])
    style.configure("Flat.TCombobox", fieldbackground=COLORS["input"], background=COLORS["input"], foreground=COLORS["text"], arrowcolor=COLORS["muted"], borderwidth=0, bordercolor=COLORS["input"], lightcolor=COLORS["input"], darkcolor=COLORS["input"], padding=(4, 5))
    style.map("Flat.TCombobox", fieldbackground=[("readonly", COLORS["input"])], foreground=[("readonly", COLORS["text"])], selectbackground=[("readonly", COLORS["input"])], selectforeground=[("readonly", COLORS["text"])])
    style.configure("TCheckbutton", background=COLORS["panel"], foreground=COLORS["text"], font=("Segoe UI", 9))
    style.map("TCheckbutton", background=[("active", COLORS["panel"])])
    style.configure("Horizontal.TScrollbar", background=COLORS["card"], troughcolor=COLORS["panel"], bordercolor=COLORS["panel"], arrowcolor=COLORS["muted"])
    style.configure("Vertical.TScrollbar", background=COLORS["card"], troughcolor=COLORS["panel"], bordercolor=COLORS["panel"], arrowcolor=COLORS["muted"])
    style.configure("Treeview", background=COLORS["card_alt"], foreground=COLORS["text"], fieldbackground=COLORS["card_alt"], rowheight=28, borderwidth=0)
    style.configure("Treeview.Heading", background=COLORS["card"], foreground=COLORS["text"], font=("Segoe UI Semibold", 9))
    style.map("Treeview", background=[("selected", COLORS["accent"])])
    return style
